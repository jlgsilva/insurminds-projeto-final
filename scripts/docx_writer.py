"""
Gerador de arquivos ``.docx`` **sem dependência externa**.

Por que escrever isto em vez de usar ``python-docx``: o projeto inteiro se
apoia numa restrição declarada — tem de rodar de graça, em qualquer máquina,
sem instalação complicada. Um entregável que só existe se a pessoa conseguir
instalar uma biblioteca não é um entregável confiável.

Então há dois caminhos, nesta ordem:

1. **``python-docx``, se estiver instalado** — saída mais rica (estilos
   nativos, tabelas com bordas do tema do Word).
2. **Escrita direta do pacote OOXML com ``zipfile``** — só biblioteca padrão.
   Um ``.docx`` é um ZIP com alguns XML dentro; montá-lo à mão é trabalhoso,
   mas é a diferença entre "funciona aqui" e "funciona em qualquer lugar".

A entrada é Markdown, porque é o formato em que o relatório e o resumo
executivo já são escritos. O subconjunto suportado é o que esses documentos
usam de fato: títulos ``#`` a ``####``, parágrafos, listas com marcador e
numeradas, tabelas com ``|``, ``**negrito**``, ``*itálico*``, ``` `código` ```,
citações ``>`` e linhas horizontais ``---``.

O arquivo gerado abre no Word, no LibreOffice e no Google Docs, e é
**editável** — que é exatamente o pedido: o PDF para enviar, o DOCX para
ajustar.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence
from xml.sax.saxutils import escape

# ==========================================================================
# Partes fixas do pacote OOXML
# ==========================================================================

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>"""

RELS_RAIZ = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""

RELS_DOCUMENTO = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

APP_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
            xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>AgroSentinela</Application>
</Properties>"""

# Paleta alinhada ao tema da aplicação, para que o DOCX pareça o mesmo
# documento do PDF, e não um primo distante.
COR_TITULO = "14532D"      # verde escuro
COR_SUB = "15803D"
COR_TEXTO = "1F2937"
COR_CINZA = "6B7280"
COR_CABECALHO_TABELA = "E8F1EA"

ESTILOS = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault><w:rPr>
      <w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/>
      <w:color w:val="{COR_TEXTO}"/><w:sz w:val="21"/><w:szCs w:val="21"/>
      <w:lang w:val="pt-BR"/>
    </w:rPr></w:rPrDefault>
    <w:pPrDefault><w:pPr>
      <w:spacing w:after="140" w:line="276" w:lineRule="auto"/>
    </w:pPr></w:pPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/><w:qFormat/>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Title">
    <w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:qFormat/>
    <w:pPr><w:spacing w:before="0" w:after="220"/></w:pPr>
    <w:rPr><w:b/><w:color w:val="{COR_TITULO}"/><w:sz w:val="52"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:qFormat/>
    <w:pPr><w:outlineLvl w:val="0"/><w:spacing w:before="320" w:after="140"/>
      <w:pBdr><w:bottom w:val="single" w:sz="6" w:space="4" w:color="{COR_SUB}"/></w:pBdr>
    </w:pPr>
    <w:rPr><w:b/><w:color w:val="{COR_TITULO}"/><w:sz w:val="34"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:qFormat/>
    <w:pPr><w:outlineLvl w:val="1"/><w:spacing w:before="260" w:after="120"/></w:pPr>
    <w:rPr><w:b/><w:color w:val="{COR_SUB}"/><w:sz w:val="27"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading3">
    <w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:qFormat/>
    <w:pPr><w:outlineLvl w:val="2"/><w:spacing w:before="200" w:after="100"/></w:pPr>
    <w:rPr><w:b/><w:color w:val="{COR_TEXTO}"/><w:sz w:val="24"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading4">
    <w:name w:val="heading 4"/><w:basedOn w:val="Normal"/><w:qFormat/>
    <w:pPr><w:outlineLvl w:val="3"/><w:spacing w:before="170" w:after="90"/></w:pPr>
    <w:rPr><w:b/><w:i/><w:color w:val="{COR_CINZA}"/><w:sz w:val="22"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Quote">
    <w:name w:val="Quote"/><w:basedOn w:val="Normal"/><w:qFormat/>
    <w:pPr><w:ind w:left="480"/>
      <w:pBdr><w:left w:val="single" w:sz="18" w:space="8" w:color="{COR_SUB}"/></w:pBdr>
    </w:pPr>
    <w:rPr><w:i/><w:color w:val="{COR_CINZA}"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Legenda">
    <w:name w:val="Legenda"/><w:basedOn w:val="Normal"/><w:qFormat/>
    <w:rPr><w:i/><w:color w:val="{COR_CINZA}"/><w:sz w:val="18"/></w:rPr>
  </w:style>
  <w:style w:type="character" w:styleId="CodigoInline">
    <w:name w:val="Codigo"/><w:qFormat/>
    <w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/>
      <w:color w:val="9A3412"/><w:sz w:val="19"/></w:rPr>
  </w:style>
  <w:style w:type="table" w:styleId="TabelaAgro">
    <w:name w:val="Tabela AgroSentinela"/><w:qFormat/>
    <w:tblPr>
      <w:tblBorders>
        <w:top w:val="single" w:sz="4" w:color="C7D2CB"/>
        <w:left w:val="single" w:sz="4" w:color="C7D2CB"/>
        <w:bottom w:val="single" w:sz="4" w:color="C7D2CB"/>
        <w:right w:val="single" w:sz="4" w:color="C7D2CB"/>
        <w:insideH w:val="single" w:sz="4" w:color="C7D2CB"/>
        <w:insideV w:val="single" w:sz="4" w:color="C7D2CB"/>
      </w:tblBorders>
    </w:tblPr>
  </w:style>
</w:styles>"""


def _core_xml(titulo: str, autor: str, assunto: str) -> str:
    agora = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
  xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>{escape(titulo)}</dc:title>
  <dc:subject>{escape(assunto)}</dc:subject>
  <dc:creator>{escape(autor)}</dc:creator>
  <cp:lastModifiedBy>{escape(autor)}</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{agora}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{agora}</dcterms:modified>
</cp:coreProperties>"""


# ==========================================================================
# Formatação de trecho (negrito, itálico, código, links)
# ==========================================================================

_PADRAO_TRECHO = re.compile(
    r"(\*\*[^*]+\*\*)"          # negrito
    r"|(__[^_]+__)"             # negrito alternativo
    r"|(\*[^*\n]+\*)"           # itálico
    r"|(`[^`]+`)"               # código
    r"|(\[[^\]]+\]\([^)]+\))"   # link
)


def _runs(texto: str) -> str:
    """Converte a formatação em linha do Markdown em ``<w:r>`` do OOXML."""
    partes: list[str] = []
    pos = 0
    for m in _PADRAO_TRECHO.finditer(texto):
        if m.start() > pos:
            partes.append(_run(texto[pos:m.start()]))
        trecho = m.group(0)
        if trecho.startswith("**") or trecho.startswith("__"):
            partes.append(_run(trecho[2:-2], negrito=True))
        elif trecho.startswith("`"):
            partes.append(_run(trecho[1:-1], codigo=True))
        elif trecho.startswith("["):
            rotulo = trecho[1:trecho.index("]")]
            alvo = trecho[trecho.index("](") + 2:-1]
            partes.append(_run(rotulo, sublinhado=True))
            partes.append(_run(f" ({alvo})", cor=COR_CINZA, tamanho=17))
        else:
            partes.append(_run(trecho[1:-1], italico=True))
        pos = m.end()
    if pos < len(texto):
        partes.append(_run(texto[pos:]))
    return "".join(partes) or _run("")


def _run(texto: str, *, negrito: bool = False, italico: bool = False,
         codigo: bool = False, sublinhado: bool = False,
         cor: str | None = None, tamanho: int | None = None) -> str:
    props: list[str] = []
    if codigo:
        props.append('<w:rStyle w:val="CodigoInline"/>')
    if negrito:
        props.append("<w:b/>")
    if italico:
        props.append("<w:i/>")
    if sublinhado:
        props.append('<w:u w:val="single"/><w:color w:val="1D4ED8"/>')
    if cor:
        props.append(f'<w:color w:val="{cor}"/>')
    if tamanho:
        props.append(f'<w:sz w:val="{tamanho}"/>')
    rpr = f"<w:rPr>{''.join(props)}</w:rPr>" if props else ""
    # xml:space preserva os espaços nas bordas, que o Word descartaria.
    return f'<w:r>{rpr}<w:t xml:space="preserve">{escape(texto)}</w:t></w:r>'


def _paragrafo(texto: str, estilo: str | None = None,
               marcador: str | None = None) -> str:
    props: list[str] = []
    if estilo:
        props.append(f'<w:pStyle w:val="{estilo}"/>')
    if marcador:
        props.append('<w:ind w:left="420" w:hanging="220"/>')
    ppr = f"<w:pPr>{''.join(props)}</w:pPr>" if props else ""
    prefixo = _run(f"{marcador}\t") if marcador else ""
    return f"<w:p>{ppr}{prefixo}{_runs(texto)}</w:p>"


def _linha_horizontal() -> str:
    return ('<w:p><w:pPr><w:pBdr><w:bottom w:val="single" w:sz="6" '
            f'w:space="6" w:color="{COR_CINZA}"/></w:pBdr></w:pPr></w:p>')


def _tabela(linhas: Sequence[Sequence[str]]) -> str:
    if not linhas:
        return ""
    n_colunas = max(len(l) for l in linhas)
    largura = int(9360 / max(n_colunas, 1))
    partes = [
        '<w:tbl><w:tblPr><w:tblStyle w:val="TabelaAgro"/>'
        '<w:tblW w:w="5000" w:type="pct"/>'
        '<w:tblBorders>'
        '<w:top w:val="single" w:sz="4" w:color="C7D2CB"/>'
        '<w:left w:val="single" w:sz="4" w:color="C7D2CB"/>'
        '<w:bottom w:val="single" w:sz="4" w:color="C7D2CB"/>'
        '<w:right w:val="single" w:sz="4" w:color="C7D2CB"/>'
        '<w:insideH w:val="single" w:sz="4" w:color="C7D2CB"/>'
        '<w:insideV w:val="single" w:sz="4" w:color="C7D2CB"/>'
        '</w:tblBorders></w:tblPr><w:tblGrid>'
        + f'<w:gridCol w:w="{largura}"/>' * n_colunas
        + "</w:tblGrid>"
    ]
    for i, linha in enumerate(linhas):
        cabecalho = i == 0
        celulas = []
        for j in range(n_colunas):
            conteudo = linha[j] if j < len(linha) else ""
            sombra = (f'<w:shd w:val="clear" w:fill="{COR_CABECALHO_TABELA}"/>'
                      if cabecalho else "")
            corpo = (f"<w:p><w:pPr><w:spacing w:after='40'/></w:pPr>"
                     f"{_run(_sem_marcacao(conteudo), negrito=cabecalho, tamanho=19)}</w:p>")
            celulas.append(
                f'<w:tc><w:tcPr><w:tcW w:w="{largura}" w:type="dxa"/>{sombra}'
                f"</w:tcPr>{corpo}</w:tc>"
            )
        cabecalho_repetido = "<w:trPr><w:tblHeader/></w:trPr>" if cabecalho else ""
        partes.append(f"<w:tr>{cabecalho_repetido}{''.join(celulas)}</w:tr>")
    partes.append("</w:tbl>")
    # Um parágrafo vazio após a tabela evita que o Word cole a tabela seguinte.
    partes.append("<w:p/>")
    return "".join(partes)


def _sem_marcacao(texto: str) -> str:
    texto = re.sub(r"\*\*([^*]+)\*\*", r"\1", texto)
    texto = re.sub(r"\*([^*]+)\*", r"\1", texto)
    texto = re.sub(r"`([^`]+)`", r"\1", texto)
    texto = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", texto)
    return texto.strip()


# ==========================================================================
# Conversão de Markdown
# ==========================================================================

def _celulas(linha: str) -> list[str]:
    bruto = linha.strip()
    if bruto.startswith("|"):
        bruto = bruto[1:]
    if bruto.endswith("|"):
        bruto = bruto[:-1]
    return [c.strip() for c in bruto.split("|")]


def _e_separador_tabela(linha: str) -> bool:
    return bool(re.fullmatch(r"\|?[\s:\-|]+\|?", linha.strip())) and "-" in linha


def markdown_para_corpo(markdown: str) -> str:
    """Converte o Markdown no corpo XML do documento."""
    corpo: list[str] = []
    linhas = markdown.replace("\r\n", "\n").split("\n")
    i = 0
    dentro_de_codigo = False
    bloco_codigo: list[str] = []

    while i < len(linhas):
        linha = linhas[i]
        cru = linha.rstrip()

        # ----------------------------------------------------- bloco de código
        if cru.strip().startswith("```"):
            if dentro_de_codigo:
                for l in bloco_codigo:
                    corpo.append(
                        '<w:p><w:pPr><w:ind w:left="280"/>'
                        '<w:spacing w:after="0"/></w:pPr>'
                        + _run(l, codigo=True) + "</w:p>"
                    )
                corpo.append("<w:p/>")
                bloco_codigo = []
            dentro_de_codigo = not dentro_de_codigo
            i += 1
            continue
        if dentro_de_codigo:
            bloco_codigo.append(cru)
            i += 1
            continue

        if not cru.strip():
            i += 1
            continue

        # ------------------------------------------------------------ tabela
        if cru.strip().startswith("|") and i + 1 < len(linhas) \
                and _e_separador_tabela(linhas[i + 1]):
            tabela_linhas = [_celulas(cru)]
            i += 2
            while i < len(linhas) and linhas[i].strip().startswith("|"):
                tabela_linhas.append(_celulas(linhas[i]))
                i += 1
            corpo.append(_tabela(tabela_linhas))
            continue

        # ---------------------------------------------------- linha horizontal
        if re.fullmatch(r"-{3,}|_{3,}|\*{3,}", cru.strip()):
            corpo.append(_linha_horizontal())
            i += 1
            continue

        # ------------------------------------------------------------ títulos
        cabecalho = re.match(r"^(#{1,6})\s+(.*)$", cru)
        if cabecalho:
            nivel = len(cabecalho.group(1))
            texto = cabecalho.group(2).strip()
            estilo = {1: "Title", 2: "Heading1", 3: "Heading2",
                      4: "Heading3"}.get(nivel, "Heading4")
            corpo.append(_paragrafo(texto, estilo))
            i += 1
            continue

        # ------------------------------------------------------------ citação
        if cru.strip().startswith(">"):
            corpo.append(_paragrafo(cru.strip().lstrip("> ").strip(), "Quote"))
            i += 1
            continue

        # ------------------------------------------------------------- listas
        marcador = re.match(r"^(\s*)([-*+])\s+(.*)$", cru)
        if marcador:
            corpo.append(_paragrafo(marcador.group(3).strip(), marcador="•"))
            i += 1
            continue
        numerada = re.match(r"^(\s*)(\d+)[.)]\s+(.*)$", cru)
        if numerada:
            corpo.append(_paragrafo(numerada.group(3).strip(),
                                    marcador=f"{numerada.group(2)}."))
            i += 1
            continue

        # --------------------------------------------------------- parágrafo
        corpo.append(_paragrafo(cru.strip()))
        i += 1

    return "".join(corpo)


def _documento_xml(corpo: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{corpo}"
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" '
        'w:header="567" w:footer="567" w:gutter="0"/></w:sectPr>'
        "</w:body></w:document>"
    )


# ==========================================================================
# API pública
# ==========================================================================

@dataclass
class ResultadoDocx:
    caminho: Path
    motor: str          # "python-docx" | "ooxml-stdlib"
    bytes_: int

    def __str__(self) -> str:
        return f"{self.caminho.name} ({self.bytes_ / 1024:.0f} KB, via {self.motor})"


def markdown_para_docx(
    markdown: str,
    destino: Path | str,
    *,
    titulo: str = "AgroSentinela",
    autor: str = "AgroSentinela",
    assunto: str = "Desafio 5 — Comunicação Inteligente",
    preferir_python_docx: bool = True,
) -> ResultadoDocx:
    """
    Escreve um ``.docx`` editável a partir de Markdown.

    Usa ``python-docx`` quando disponível e cai para a escrita direta do
    pacote OOXML quando não. Os dois caminhos produzem um arquivo que abre no
    Word, no LibreOffice e no Google Docs.
    """
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)

    if preferir_python_docx:
        try:
            caminho = _via_python_docx(markdown, destino, titulo, autor)
            return ResultadoDocx(caminho, "python-docx", caminho.stat().st_size)
        except ImportError:
            pass
        except Exception:  # noqa: BLE001 — qualquer falha cai para o stdlib
            pass

    corpo = markdown_para_corpo(markdown)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", RELS_RAIZ)
        z.writestr("docProps/core.xml", _core_xml(titulo, autor, assunto))
        z.writestr("docProps/app.xml", APP_XML)
        z.writestr("word/_rels/document.xml.rels", RELS_DOCUMENTO)
        z.writestr("word/styles.xml", ESTILOS)
        z.writestr("word/document.xml", _documento_xml(corpo))
    return ResultadoDocx(destino, "ooxml-stdlib", destino.stat().st_size)


def _via_python_docx(markdown: str, destino: Path, titulo: str,
                     autor: str) -> Path:
    """Caminho preferencial, quando a biblioteca está instalada."""
    from docx import Document                      # type: ignore
    from docx.shared import Pt, RGBColor           # type: ignore

    doc = Document()
    doc.core_properties.title = titulo
    doc.core_properties.author = autor

    linhas = markdown.replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(linhas):
        cru = linhas[i].rstrip()
        if not cru.strip():
            i += 1
            continue

        if cru.strip().startswith("|") and i + 1 < len(linhas) \
                and _e_separador_tabela(linhas[i + 1]):
            dados = [_celulas(cru)]
            i += 2
            while i < len(linhas) and linhas[i].strip().startswith("|"):
                dados.append(_celulas(linhas[i]))
                i += 1
            n_col = max(len(l) for l in dados)
            tabela = doc.add_table(rows=0, cols=n_col)
            tabela.style = "Table Grid"
            for k, linha in enumerate(dados):
                celulas = tabela.add_row().cells
                for j in range(n_col):
                    texto = _sem_marcacao(linha[j] if j < len(linha) else "")
                    celulas[j].text = texto
                    if k == 0:
                        for p in celulas[j].paragraphs:
                            for r in p.runs:
                                r.bold = True
            doc.add_paragraph()
            continue

        cabecalho = re.match(r"^(#{1,6})\s+(.*)$", cru)
        if cabecalho:
            nivel = min(len(cabecalho.group(1)), 4)
            doc.add_heading(_sem_marcacao(cabecalho.group(2)), level=nivel - 1
                            if nivel > 1 else 0)
            i += 1
            continue

        if re.fullmatch(r"-{3,}|_{3,}|\*{3,}", cru.strip()):
            doc.add_paragraph("—" * 30)
            i += 1
            continue

        marcador = re.match(r"^(\s*)([-*+])\s+(.*)$", cru)
        if marcador:
            doc.add_paragraph(_sem_marcacao(marcador.group(3)),
                              style="List Bullet")
            i += 1
            continue
        numerada = re.match(r"^(\s*)(\d+)[.)]\s+(.*)$", cru)
        if numerada:
            doc.add_paragraph(_sem_marcacao(numerada.group(3)),
                              style="List Number")
            i += 1
            continue
        if cru.strip().startswith(">"):
            p = doc.add_paragraph(_sem_marcacao(cru.strip().lstrip("> ")))
            for r in p.runs:
                r.italic = True
            i += 1
            continue

        doc.add_paragraph(_sem_marcacao(cru.strip()))
        i += 1

    doc.save(str(destino))
    return destino


def html_para_markdown_simples(html: str) -> str:
    """
    Redução grosseira de HTML para Markdown.

    Existe para um caso específico: o relatório técnico é montado em HTML
    (para virar PDF pelo wkhtmltopdf) e precisa também sair em DOCX. Converter
    o HTML já pronto evita manter duas fontes de verdade do mesmo texto — que
    é a forma mais confiável de os dois documentos divergirem com o tempo.
    """
    texto = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html,
                   flags=re.S | re.I)
    substituicoes = [
        (r"<h1[^>]*>(.*?)</h1>", r"\n# \1\n"),
        (r"<h2[^>]*>(.*?)</h2>", r"\n## \1\n"),
        (r"<h3[^>]*>(.*?)</h3>", r"\n### \1\n"),
        (r"<h4[^>]*>(.*?)</h4>", r"\n#### \1\n"),
        (r"<li[^>]*>(.*?)</li>", r"\n- \1"),
        (r"<(strong|b)>(.*?)</\1>", r"**\2**"),
        (r"<(em|i)>(.*?)</\1>", r"*\2*"),
        (r"<code>(.*?)</code>", r"`\1`"),
        (r"<br\s*/?>", "\n"),
        (r"</p>", "\n\n"),
        (r"<hr\s*/?>", "\n---\n"),
    ]
    for padrao, troca in substituicoes:
        texto = re.sub(padrao, troca, texto, flags=re.S | re.I)

    # Tabelas: uma linha Markdown por <tr>.
    def _tr(m: re.Match) -> str:
        celulas = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", m.group(1),
                             flags=re.S | re.I)
        limpas = [re.sub(r"<[^>]+>", "", c).strip() for c in celulas]
        return "\n| " + " | ".join(limpas) + " |"

    texto = re.sub(r"<tr[^>]*>(.*?)</tr>", _tr, texto, flags=re.S | re.I)
    texto = re.sub(r"<[^>]+>", "", texto)

    import html as _html
    texto = _html.unescape(texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def inserir_separadores_de_tabela(markdown: str) -> str:
    """
    Acrescenta a linha ``|---|`` após o cabeçalho de cada tabela.

    A conversão de HTML produz linhas ``| a | b |`` sem o separador que o
    Markdown exige; sem ele, a tabela vira parágrafo solto no DOCX.
    """
    linhas = markdown.split("\n")
    saida: list[str] = []
    i = 0
    while i < len(linhas):
        linha = linhas[i]
        saida.append(linha)
        e_tabela = linha.strip().startswith("|") and linha.strip().endswith("|")
        proxima_e_tabela = (
            i + 1 < len(linhas)
            and linhas[i + 1].strip().startswith("|")
        )
        ja_tem_separador = (
            i + 1 < len(linhas) and _e_separador_tabela(linhas[i + 1])
        )
        anterior_e_tabela = bool(saida[-2].strip().startswith("|")) if len(saida) > 1 else False
        if e_tabela and proxima_e_tabela and not ja_tem_separador \
                and not anterior_e_tabela:
            n = len(_celulas(linha))
            saida.append("|" + "|".join(["---"] * n) + "|")
        i += 1
    return "\n".join(saida)
