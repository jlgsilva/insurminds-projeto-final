"""
Gera o acervo de apólices D&O simuladas (PDF, PDF digitalizado e fotos).

    python scripts/gerar_apolices_simuladas.py

Cada seguradora simulada tem arquitetura de documento própria
(``src/agrosentinela/projeto_final/modelos_documento.py``) e identidade visual
própria (fonte, cor, cabeçalho, tabela) definida aqui.

Saída em ``data/apolices_simuladas/``: ``documentos/``, ``gabarito.json``,
``catalogo.csv`` e ``LEIA-ME.md``. Todo documento traz marca d'água e rodapé
de simulação.
"""

from __future__ import annotations

import io
import json
import random
import sys
from collections import Counter
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402
from PIL import Image, ImageFilter  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle  # noqa: E402

from agrosentinela.config import APOLICES_DIR  # noqa: E402
from agrosentinela.projeto_final.modelos_documento import DocumentoApolice  # noqa: E402
from agrosentinela.projeto_final.simulador import (  # noqa: E402
    AVISO_SIMULACAO, SEGURADORAS, SEGURADORAS_POR_CODIGO, TOMADORAS, acervo,
)

DOC_DIR = APOLICES_DIR / "documentos"

FONTES = {
    "Helvetica": ("Helvetica", "Helvetica-Bold"),
    "Times": ("Times-Roman", "Times-Bold"),
    "Courier": ("Courier", "Courier-Bold"),
}

# Identidade visual por seguradora: cabeçalho, alinhamento, tamanho, tabela
VISUAL = {
    "ATA": dict(cab="faixa", corpo=9, alinh=TA_JUSTIFY, tab_fundo="#E8EEF5", sec_caixa=False),
    "IPE": dict(cab="centro", corpo=10, alinh=TA_JUSTIFY, tab_fundo="#F4ECF1", sec_caixa=False),
    "JAC": dict(cab="moldura", corpo=9.5, alinh=TA_JUSTIFY, tab_fundo="#EEF2EC", sec_caixa=True),
    "XIQ": dict(cab="esquerda", corpo=9, alinh=TA_LEFT, tab_fundo="#F7EFE4", sec_caixa=False),
    "MUT": dict(cab="amigavel", corpo=10.5, alinh=TA_LEFT, tab_fundo="#E6F2EA", sec_caixa=True),
    "MIN": dict(cab="maquina", corpo=8.6, alinh=TA_LEFT, tab_fundo="#E9EEF1", sec_caixa=False),
}


def _estilos(s_cod: str):
    seg = SEGURADORAS_POR_CODIGO[s_cod]
    v = VISUAL[s_cod]
    f, fb = FONTES[seg.fonte]
    cor = colors.HexColor(seg.cor)
    t = v["corpo"]
    return {
        "titulo_doc": ParagraphStyle("t", fontName=fb, fontSize=t + 4.5, leading=t + 8, textColor=cor,
                                     alignment=TA_CENTER if v["cab"] in ("centro", "moldura") else TA_LEFT,
                                     spaceAfter=3),
        "subtitulo": ParagraphStyle("s", fontName=f, fontSize=t, leading=t + 3,
                                    textColor=colors.HexColor("#444444"),
                                    alignment=TA_CENTER if v["cab"] in ("centro", "moldura") else TA_LEFT),
        "aviso": ParagraphStyle("a", fontName=f, fontSize=7, leading=8.5, textColor=colors.HexColor("#B71C1C"),
                                spaceBefore=3, spaceAfter=4),
        "secao": ParagraphStyle("h", fontName=fb, fontSize=t + 1.2, leading=t + 4, textColor=cor,
                                spaceBefore=8, spaceAfter=3,
                                backColor=colors.HexColor(v["tab_fundo"]) if v["sec_caixa"] else None,
                                borderPadding=(2, 3, 2, 3) if v["sec_caixa"] else 0),
        "subsecao": ParagraphStyle("hs", fontName=fb, fontSize=t, leading=t + 3,
                                   textColor=colors.HexColor("#222222"), spaceBefore=4, spaceAfter=1),
        "par": ParagraphStyle("p", fontName=f, fontSize=t, leading=t + 3.2, alignment=v["alinh"],
                              spaceAfter=3),
        "item": ParagraphStyle("i", fontName=f, fontSize=t, leading=t + 3.2, alignment=v["alinh"],
                               leftIndent=10, spaceAfter=3),
        "cel": ParagraphStyle("c", fontName=f, fontSize=t - 0.5, leading=t + 2),
        "celb": ParagraphStyle("cb", fontName=fb, fontSize=t - 0.5, leading=t + 2),
    }


_MARCA = None


def _marca_dagua():
    """PNG transparente com o texto diagonal (imagem: fica fora da camada de texto)."""
    global _MARCA
    if _MARCA is None:
        from PIL import ImageDraw, ImageFont
        from reportlab.lib.utils import ImageReader

        img = Image.new("RGBA", (1240, 1754), (0, 0, 0, 0))
        camada = Image.new("RGBA", (1300, 160), (0, 0, 0, 0))
        try:
            import matplotlib

            fonte = ImageFont.truetype(str(Path(matplotlib.get_data_path()) / "fonts" / "ttf"
                                           / "DejaVuSans-Bold.ttf"), 72)
        except Exception:  # noqa: BLE001
            fonte = ImageFont.load_default()
        ImageDraw.Draw(camada).text((20, 40), "SIMULADA · USO ACADÊMICO", font=fonte,
                                    fill=(200, 30, 30, 34))
        camada = camada.rotate(35, expand=True)
        img.alpha_composite(camada, ((1240 - camada.width) // 2, (1754 - camada.height) // 2))
        buf = io.BytesIO()
        img.save(buf, "PNG")
        buf.seek(0)
        _MARCA = ImageReader(buf)
    return _MARCA


def _decoracao(s_cod: str):
    seg = SEGURADORAS_POR_CODIGO[s_cod]
    v = VISUAL[s_cod]
    f, fb = FONTES[seg.fonte]
    cor = colors.HexColor(seg.cor)

    def desenhar(canvas, doc):
        w, h = A4
        canvas.saveState()
        estilo = v["cab"]
        if estilo == "faixa":
            canvas.setFillColor(cor)
            canvas.rect(0, h - 0.9 * cm, w, 0.9 * cm, stroke=0, fill=1)
            canvas.setFillColor(colors.white)
            canvas.setFont(fb, 9)
            canvas.drawRightString(w - 1.5 * cm, h - 0.6 * cm, seg.nome)
        elif estilo == "centro":
            canvas.setFillColor(cor)
            canvas.setFont(fb, 11)
            canvas.drawCentredString(w / 2, h - 1.0 * cm, seg.nome.upper())
            canvas.setStrokeColor(cor)
            canvas.line(3 * cm, h - 1.2 * cm, w - 3 * cm, h - 1.2 * cm)
        elif estilo == "moldura":
            canvas.setStrokeColor(cor)
            canvas.setLineWidth(1.2)
            canvas.rect(1.2 * cm, 1.2 * cm, w - 2.4 * cm, h - 2.4 * cm, stroke=1, fill=0)
            canvas.setFont(fb, 8.5)
            canvas.setFillColor(cor)
            canvas.drawString(1.6 * cm, h - 1.0 * cm, seg.nome)
        elif estilo == "esquerda":
            canvas.setFillColor(cor)
            canvas.circle(1.9 * cm, h - 1.0 * cm, 0.32 * cm, stroke=0, fill=1)
            canvas.setFont(fb, 10)
            canvas.drawString(2.5 * cm, h - 1.15 * cm, seg.nome)
        elif estilo == "amigavel":
            canvas.setFillColor(colors.HexColor(v["tab_fundo"]))
            canvas.roundRect(1.4 * cm, h - 1.55 * cm, w - 2.8 * cm, 1.0 * cm, 8, stroke=0, fill=1)
            canvas.setFillColor(cor)
            canvas.setFont(fb, 11)
            canvas.drawString(1.9 * cm, h - 1.2 * cm, "Mutirão · seguro feito por cooperados (fictício)")
        else:  # maquina
            canvas.setFont(fb, 8)
            canvas.setFillColor(colors.black)
            canvas.drawString(1.5 * cm, h - 1.0 * cm, seg.nome.upper() + "  //  LONDON MARKET FORM (SIMULATED)")
        canvas.drawImage(_marca_dagua(), 0, 0, width=w, height=h, mask="auto")
        canvas.restoreState()
        canvas.setFont(f, 6.5)
        canvas.setFillColor(colors.HexColor("#B71C1C"))
        canvas.drawString(1.5 * cm, 0.75 * cm, "DOCUMENTO SIMULADO — InsurMinds/I2A2 — não é apólice real")
        canvas.setFillColor(colors.HexColor("#666666"))
        rotulo = {"MIN": "Page", "MUT": "Página"}.get(s_cod, "pág.")
        canvas.drawRightString(w - 1.5 * cm, 0.75 * cm, f"{rotulo} {doc.page}")
    return desenhar


def renderizar_pdf(doc: DocumentoApolice) -> bytes:
    e = doc.espec
    seg = SEGURADORAS_POR_CODIGO[e.seguradora_codigo]
    est = _estilos(e.seguradora_codigo)
    v = VISUAL[e.seguradora_codigo]
    buf = io.BytesIO()
    margem = 2.0 if v["cab"] == "moldura" else 1.8
    pdf = SimpleDocTemplate(buf, pagesize=A4, leftMargin=margem * cm, rightMargin=margem * cm,
                            topMargin=1.9 * cm, bottomMargin=1.5 * cm,
                            title=f"Apólice D&O {e.numero_apolice} (SIMULADA)", author=seg.nome)
    fl = []
    for b in doc.blocos:
        if b.tipo in ("tabela", "caixa"):
            dados = [[Paragraph(escape(k), est["celb"]), Paragraph(escape(val), est["cel"])]
                     for k, val in b.linhas]
            larg = (A4[0] - 2 * margem * cm)
            t = Table(dados, colWidths=[larg * 0.36, larg * 0.64])
            estilo = [("VALIGN", (0, 0), (-1, -1), "TOP"),
                      ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
            if b.tipo == "tabela":
                estilo += [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#999999")),
                           ("BACKGROUND", (0, 0), (0, -1), colors.HexColor(v["tab_fundo"]))]
            else:
                estilo += [("BOX", (0, 0), (-1, -1), 1.2, colors.HexColor(seg.cor)),
                           ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(v["tab_fundo"]))]
            t.setStyle(TableStyle(estilo))
            fl += [t, Spacer(1, 5)]
        elif b.tipo == "item":
            fl.append(Paragraph(f"<b>{escape(b.titulo)}:</b> {escape(b.texto)}", est["item"]))
        else:
            fl.append(Paragraph(escape(b.texto), est[b.tipo]))
    deco = _decoracao(e.seguradora_codigo)
    pdf.build(fl, onFirstPage=deco, onLaterPages=deco)
    return buf.getvalue()


def _digitalizar(pdf_bytes: bytes, rng: random.Random, dpi: int = 150, foto: bool = False):
    """Simula digitalização (ou foto de celular): inclina, borra, ruído, sombra."""
    import pypdfium2 as pdfium

    paginas = []
    for pagina in pdfium.PdfDocument(pdf_bytes):
        img = pagina.render(scale=dpi / 72).to_pil().convert("L")
        ang = rng.uniform(-2.2, 2.2) if foto else rng.uniform(-1.2, 1.2)
        img = img.rotate(ang, expand=False, fillcolor=235 if foto else 255, resample=Image.BICUBIC)
        img = img.filter(ImageFilter.GaussianBlur(radius=0.55 if foto else 0.4))
        px = img.load()
        w, h = img.size
        for _ in range(w * h // 400):
            x, y = rng.randrange(w), rng.randrange(h)
            px[x, y] = rng.randint(120, 220)
        if foto:  # gradiente de iluminação lateral
            sombra = Image.linear_gradient("L").rotate(90).resize((w, h))
            img = Image.blend(img, Image.eval(sombra, lambda v: 200 + v // 5), 0.18)
        paginas.append(img)
    return paginas


def main() -> None:
    DOC_DIR.mkdir(parents=True, exist_ok=True)
    # remove só o acervo gerado aqui (AP…); lotes importados (EXT…) são preservados
    for antigo in DOC_DIR.glob("AP*"):
        antigo.unlink()
    caminho_gab = APOLICES_DIR / "gabarito.json"
    externos = []
    if caminho_gab.exists():
        externos = [g for g in json.loads(caminho_gab.read_text(encoding="utf-8"))
                    if str(g.get("fonte", "")).startswith("externa")]
    rng = random.Random(7)
    docs = acervo()
    gabarito, catalogo = [], []
    for d in docs:
        e = d.espec
        pdf = renderizar_pdf(d)
        if e.formato == "pdf":
            arquivos = [f"{e.identificador}.pdf"]
            (DOC_DIR / arquivos[0]).write_bytes(pdf)
        elif e.formato == "pdf_digitalizado":
            paginas = _digitalizar(pdf, rng)
            arquivos = [f"{e.identificador}_digitalizada.pdf"]
            paginas[0].save(DOC_DIR / arquivos[0], "PDF", resolution=150, save_all=True,
                            append_images=paginas[1:])
        else:
            paginas = _digitalizar(pdf, rng, dpi=140, foto=True)
            arquivos = []
            for i, p in enumerate(paginas, 1):
                nome = f"{e.identificador}_foto_p{i}.jpg"
                p.save(DOC_DIR / nome, "JPEG", quality=72)
                arquivos.append(nome)
        g = e.to_dict()
        g["arquivos"] = arquivos
        gabarito.append(g)
        catalogo.append({
            "identificador": e.identificador, "seguradora": e.seguradora,
            "modelo_documento": e.modelo_documento, "tomadora": e.tomadora, "perfil": e.perfil,
            "segmento": e.segmento, "municipio": e.municipio, "uf": e.uf, "regiao": e.regiao,
            "lmg": e.lmg, "premio": e.premio, "franquia": e.franquia, "formato": e.formato,
            "arquivos": ";".join(arquivos),
        })
    (APOLICES_DIR / "gabarito.json").write_text(
        json.dumps(gabarito + externos, ensure_ascii=False, indent=1), encoding="utf-8")
    cat = pd.DataFrame(catalogo)
    cat.to_csv(APOLICES_DIR / "catalogo.csv", index=False)

    por_seg = Counter(e.espec.seguradora for e in docs)
    linhas_seg = "\n".join(
        f"| {s.nome} | `{s.modelo}` | {por_seg[s.nome]} | {s.inspiracao} |" for s in SEGURADORAS)
    (APOLICES_DIR / "LEIA-ME.md").write_text(
        "# Apólices D&O SIMULADAS\n\n" + AVISO_SIMULACAO + "\n\n"
        f"**{len(docs)} apólices**, {len(SEGURADORAS)} seguradoras fictícias (cada uma com "
        f"arquitetura de documento própria), {len(TOMADORAS)} tomadoras fictícias em "
        f"{cat['uf'].nunique()} unidades da federação e nas 5 regiões.\n\n"
        "| Seguradora (fictícia) | Modelo de documento | Apólices | Inspiração estrutural |\n"
        "|---|---|---|---|\n" + linhas_seg + "\n\n"
        "As inspirações referem-se apenas à *organização* de condições gerais públicas de D&O "
        "registradas na SUSEP; nenhum texto foi copiado.\n\n"
        "## Distribuição\n\n" + cat.groupby(["regiao"]).size().to_frame("apólices").to_markdown()
        + "\n\n" + cat.groupby(["perfil"]).size().to_frame("apólices").to_markdown()
        + "\n\n" + cat.groupby(["formato"]).size().to_frame("apólices").to_markdown()
        + "\n\nGerado por `scripts/gerar_apolices_simuladas.py`. `gabarito.json` é a verdade de "
        "referência para medir a extração.\n", encoding="utf-8")
    print(f"{len(docs)} apólices em {DOC_DIR}")
    print(cat.groupby(["seguradora", "formato"]).size().unstack(fill_value=0))
    print(cat.groupby("regiao").size(), cat.groupby("perfil").size(), sep="\n")


if __name__ == "__main__":
    main()
