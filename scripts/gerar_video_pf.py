"""
Gera o vídeo-base de apresentação (≤ 5 min, 1920x1080, sem áudio):
slides do pitch deck (processo de criação e funcionamento) + capturas reais
da aplicação com legendas. A versão narrada é gravada pelo autor (ver ROTEIRO_VIDEO.md).

    python scripts/gerar_video_pf.py <pasta_com_slides_png>

A pasta deve conter hd-01.png … hd-16.png (slides renderizados a partir do
InsurMinds_Projeto_Final.pptx: LibreOffice → PDF → pdftoppm -r 144).
Requer ffmpeg. Saída: Projeto_Final_Artefatos/InsurMinds_Projeto_Final.mp4
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
CAP = ROOT / "Projeto_Final_Artefatos" / "capturas"
SAIDA = ROOT / "Projeto_Final_Artefatos" / "InsurMinds_Projeto_Final.mp4"
W, H = 1920, 1080

DEMO = [
    ("00_inicio.png", "Um aplicativo só: os alertas de crédito rural do Desafio 5 e o novo módulo de seguros D&O."),
    ("01_ingestao.png", "Ler: escolho apólices da base simulada (120, de 6 seguradoras com modelos diferentes) ou envio PDF, documento escaneado ou foto."),
    ("01b_ingestao_rodando.png", "Cada agente aparece trabalhando: recebe, lê (inclusive imagem), preenche a ficha com IA, entende as cláusulas com IA, confere e guarda."),
    ("02_ingestao_resultado.png", "Resultado: 32 tipos de cláusula com o nível de cobertura e o trecho do documento que comprova."),
    ("02b_ingestao_resultado.png", "Mesmo o documento escaneado, escrito em linguagem simples, é lido e organizado."),
    ("10_documentos_reais.png", "Documento real: as condições gerais públicas da Porto (52 páginas) são reconhecidas como D&O; um Seguro Garantia (exemplo fictício) é recusado."),
    ("03_qualidade.png", "Conferência com o gabarito: quanto o sistema acertou, apólice por apólice."),
    ("05_comparador.png", "Comparar: as 4 propostas que a Grão Norte (Sorriso/MT) recebeu, com pesos ajustados pelos dados de crédito rural da região."),
    ("06_relatorio.png", "A IA escreve o relatório para o público escolhido; um verificador confere cada número."),
    ("07_criticas.png", "As cláusulas que mais pesam num processo, lado a lado."),
    ("07b_diferencas.png", "Só onde as propostas são diferentes, da maior para a menor diferença."),
    ("08_perfil.png", "Perfil da empresa: dados públicos do Banco Central explicam por que cada cláusula pesa mais ou menos."),
    ("09_consulta.png", "Perguntar: em português; o agente consulta a base e mostra a tabela que usou."),
]


def _abrir_imagem(caminho):
    """Abre imagem a partir dos bytes (sem open() de texto — portável)."""
    from PIL import ImageFile

    parser = ImageFile.Parser()
    parser.feed(Path(caminho).read_bytes())
    return parser.close()


def _fonte(t: int):
    candidatos = ["DejaVuSans-Bold.ttf", "arialbd.ttf"]
    try:
        import matplotlib

        candidatos.insert(0, str(Path(matplotlib.get_data_path()) / "fonts" / "ttf"
                                 / "DejaVuSans-Bold.ttf"))
    except ModuleNotFoundError:
        pass
    for nome in candidatos:
        try:
            return ImageFont.truetype(nome, t)
        except OSError:
            continue
    return ImageFont.load_default()


def quadro_demo(caminho: Path, legenda: str, destino: Path) -> None:
    base = Image.new("RGB", (W, H), (31, 77, 54))
    img = _abrir_imagem(caminho).convert("RGB")
    alvo_h = H - 170
    img = img.resize((int(img.width * alvo_h / img.height), alvo_h))
    base.paste(img, ((W - img.width) // 2, 20))
    d = ImageDraw.Draw(base)
    f = _fonte(34)
    # quebra a legenda em até 2 linhas
    palavras, linhas, atual = legenda.split(), [], ""
    for p in palavras:
        teste = (atual + " " + p).strip()
        if d.textlength(teste, font=f) > W - 160:
            linhas.append(atual)
            atual = p
        else:
            atual = teste
    linhas.append(atual)
    y = H - 140 + (0 if len(linhas) > 1 else 22)
    for l in linhas[:2]:
        d.text(((W - d.textlength(l, font=f)) / 2, y), l, font=f, fill=(255, 255, 255))
        y += 46
    d.text((W - 330, 28), "DEMONSTRAÇÃO", font=_fonte(26), fill=(217, 164, 65))
    base.save(destino)


def main() -> None:
    slides = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    tmp = Path(tempfile.mkdtemp())
    seq: list[tuple[Path, float]] = []

    def slide(n: int, dur: float) -> None:
        img = _abrir_imagem(slides / f"hd-{n:02d}.png").convert("RGB").resize((W, H))
        p = tmp / f"s{len(seq):02d}.png"
        img.save(p)
        seq.append((p, dur))

    # slides 1–13 (processo e funcionamento), demonstração em capturas, slides 14–16
    for n in range(1, 14):
        slide(n, 8 if n == 1 else (6 if n == 12 else 11.5))
    for nome, leg in DEMO:
        p = tmp / f"d{len(seq):02d}.png"
        quadro_demo(CAP / nome, leg, p)
        seq.append((p, 7.5))
    for n in (14, 15, 16):
        slide(n, {14: 13, 15: 11, 16: 7}[n])

    lista = tmp / "lista.txt"
    with lista.open("w", encoding="utf-8") as fh:
        for p, dur in seq:
            fh.write(f"file '{p.as_posix()}'\nduration {dur}\n")
        fh.write(f"file '{seq[-1][0].as_posix()}'\n")
    total = sum(d for _, d in seq)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(lista), "-vf", "fps=25,format=yuv420p", "-c:v", "libx264",
                    "-preset", "medium", "-crf", "28", "-movflags", "+faststart", str(SAIDA)],
                   check=True)
    print(f"ok {SAIDA} — {len(seq)} quadros, {total:.0f}s")


if __name__ == "__main__":
    main()
