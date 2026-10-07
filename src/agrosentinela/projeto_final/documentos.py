"""
Recepção de documentos e extração de texto (camada de texto do PDF ou OCR).

Estratégia em cascata, página a página:

1. **PDF com camada de texto** → ``pdfplumber`` (rápido, exato).
2. **PDF digitalizado** (página sem texto útil) → rasteriza com
   ``pypdfium2`` e aplica **OCR** (Tesseract, idioma português).
3. **Imagem** (JPG/PNG/TIFF; várias imagens = várias páginas da mesma
   apólice) → OCR direto.

A decisão é por página, não por documento: apólices reais misturam páginas
nativas e anexos escaneados (endossos assinados, por exemplo).

O OCR é a única dependência de sistema do projeto (binário ``tesseract``).
No Streamlit Cloud ele é instalado pelo ``packages.txt``. Sem o binário, o
sistema não quebra: a página é marcada como "OCR indisponível" e o restante
do pipeline segue com o que foi possível ler.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import shutil
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from ..utils.logging_setup import get_logger

log = get_logger(__name__)

TAMANHO_MAXIMO_MB = 20
EXTENSOES_PDF = {".pdf"}
EXTENSOES_IMAGEM = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
EXTENSOES_TEXTO = {".txt", ".md"}
MIN_CARACTERES_PAGINA = 60   # abaixo disso a página é tratada como imagem


class DocumentoInvalido(ValueError):
    """Arquivo recusado na recepção (tipo, tamanho ou conteúdo)."""


@dataclass
class Pagina:
    numero: int
    texto: str
    metodo: str            # "texto_pdf" | "ocr" | "texto" | "ocr_indisponivel"
    confianca_ocr: float | None = None


@dataclass
class DocumentoRecebido:
    """Um documento lógico (uma apólice), possivelmente de vários arquivos."""

    nome: str
    arquivos: list[str]
    hash: str
    tipo: str              # pdf | imagem | texto
    tamanho_bytes: int
    paginas: list[Pagina] = field(default_factory=list)
    # linhas removidas por se repetirem em várias páginas (cabeçalho/rodapé).
    # Guardadas porque o nome da seguradora costuma morar justamente aí.
    linhas_repetidas: list[str] = field(default_factory=list)

    @property
    def texto(self) -> str:
        return "\n".join(p.texto for p in self.paginas)

    @property
    def usou_ocr(self) -> bool:
        return any(p.metodo == "ocr" for p in self.paginas)

    @property
    def metodo_resumo(self) -> str:
        metodos = sorted({p.metodo for p in self.paginas})
        return "+".join(metodos) if metodos else "vazio"

    @property
    def confianca_ocr_media(self) -> float | None:
        vals = [p.confianca_ocr for p in self.paginas if p.confianca_ocr is not None]
        return round(sum(vals) / len(vals), 1) if vals else None


# --------------------------------------------------------------------------
# OCR
# --------------------------------------------------------------------------

def _tessdata_local() -> None:
    """Usa ``data/tessdata`` se existir (modelo 'por' empacotado no repo)."""
    from ..config import DATA_DIR

    local = DATA_DIR / "tessdata"
    if (local / "por.traineddata").exists() and not os.environ.get("TESSDATA_PREFIX"):
        os.environ["TESSDATA_PREFIX"] = str(local)


def ocr_disponivel() -> bool:
    if shutil.which("tesseract") is None:
        return False
    try:
        import pytesseract  # noqa: F401
    except ModuleNotFoundError:
        return False
    return True


def _idioma_ocr() -> str:
    _tessdata_local()
    try:
        import pytesseract

        langs = set(pytesseract.get_languages(config=""))
        return "por" if "por" in langs else "eng"
    except Exception:  # noqa: BLE001
        return "eng"


def ocr_imagem(imagem) -> tuple[str, float | None]:
    """OCR de uma imagem PIL. Devolve (texto, confiança média 0–100)."""
    import pytesseract

    lang = _idioma_ocr()
    img = imagem.convert("L")
    # Uma única passada (image_to_data) fornece texto e confiança. A
    # binarização foi testada e descartada: cortava trechos de linha em
    # digitalizações inclinadas. ``--psm 6`` (bloco uniforme) foi o modo
    # mais estável para condições contratuais em coluna única.
    dados = pytesseract.image_to_data(img, lang=lang, config="--psm 6",
                                      output_type=pytesseract.Output.DICT)
    linhas: dict[tuple[int, int, int], list[str]] = {}
    confs: list[float] = []
    for i, palavra in enumerate(dados["text"]):
        palavra = str(palavra).strip()
        if not palavra:
            continue
        chave = (dados["block_num"][i], dados["par_num"][i], dados["line_num"][i])
        linhas.setdefault(chave, []).append(palavra)
        try:
            c = float(dados["conf"][i])
            if c >= 0:
                confs.append(c)
        except (TypeError, ValueError):
            pass
    texto = "\n".join(" ".join(v) for _, v in sorted(linhas.items()))
    return texto, (round(sum(confs) / len(confs), 1) if confs else None)


# --------------------------------------------------------------------------
# Recepção
# --------------------------------------------------------------------------

def _extensao(nome: str) -> str:
    return Path(nome).suffix.lower()


def validar_arquivo(nome: str, conteudo: bytes) -> str:
    """Valida tipo e tamanho. Devolve o tipo lógico ('pdf'|'imagem'|'texto')."""
    if not conteudo:
        raise DocumentoInvalido(f"{nome}: arquivo vazio.")
    if len(conteudo) > TAMANHO_MAXIMO_MB * 1024 * 1024:
        raise DocumentoInvalido(f"{nome}: maior que {TAMANHO_MAXIMO_MB} MB.")
    ext = _extensao(nome)
    if ext in EXTENSOES_PDF:
        if not conteudo.startswith(b"%PDF"):
            raise DocumentoInvalido(f"{nome}: extensão .pdf, mas o conteúdo não é PDF.")
        return "pdf"
    if ext in EXTENSOES_IMAGEM:
        return "imagem"
    if ext in EXTENSOES_TEXTO:
        return "texto"
    raise DocumentoInvalido(
        f"{nome}: tipo não suportado. Envie PDF, imagem (JPG/PNG/TIFF) ou TXT.")


def agrupar_arquivos(arquivos: Iterable[tuple[str, bytes]]) -> dict[str, list[tuple[str, bytes]]]:
    """
    Agrupa arquivos que formam uma mesma apólice.

    Fotos de páginas costumam chegar como ``X_p1.jpg``, ``X_p2.jpg``…: o
    sufixo de página é removido para formar o nome lógico do documento.
    """
    grupos: dict[str, list[tuple[str, bytes]]] = {}
    for nome, conteudo in arquivos:
        base = Path(nome).stem
        base = re.sub(r"(_foto)?[_\-\s]?(p|pag|pagina|page)[_\-\s]?\d+$", "", base,
                      flags=re.IGNORECASE)
        base = re.sub(r"[_\-\s](digitalizad[ao]|scan|escaneada|foto)$", "", base,
                      flags=re.IGNORECASE)
        grupos.setdefault(base, []).append((nome, conteudo))
    for k in grupos:
        grupos[k].sort(key=lambda x: _ordem_pagina(x[0]))
    return grupos


def _ordem_pagina(nome: str) -> int:
    m = re.search(r"(\d+)\D*$", Path(nome).stem)
    return int(m.group(1)) if m else 0


def ler_documento(nome_logico: str, arquivos: list[tuple[str, bytes]],
                  *, permitir_ocr: bool = True) -> DocumentoRecebido:
    """Recebe 1..n arquivos de uma apólice e devolve o texto por página."""
    tipos = {validar_arquivo(n, c) for n, c in arquivos}
    if len(tipos) > 1:
        raise DocumentoInvalido(f"{nome_logico}: mistura de PDF e imagens no mesmo documento.")
    tipo = tipos.pop()
    h = hashlib.sha256(b"".join(c for _, c in arquivos)).hexdigest()
    doc = DocumentoRecebido(
        nome=nome_logico, arquivos=[n for n, _ in arquivos], hash=h, tipo=tipo,
        tamanho_bytes=sum(len(c) for _, c in arquivos),
    )
    numero = 0
    for nome, conteudo in arquivos:
        if tipo == "texto":
            numero += 1
            doc.paginas.append(Pagina(numero, conteudo.decode("utf-8", "replace"), "texto"))
        elif tipo == "imagem":
            from PIL import ImageFile

            numero += 1
            # Decodifica a partir dos bytes (sem arquivo em disco)
            parser = ImageFile.Parser()
            parser.feed(conteudo)
            img = parser.close()
            doc.paginas.append(_ocr_ou_marca(img, numero, permitir_ocr))
        else:
            for pagina in _ler_pdf(conteudo, permitir_ocr, inicio=numero):
                doc.paginas.append(pagina)
            numero = len(doc.paginas)
    doc.linhas_repetidas = remover_cabecalhos_e_rodapes(doc.paginas)
    remover_sumario(doc.paginas)
    return doc


def _assinatura_linha(linha: str) -> str:
    return re.sub(r"\d+", "#", normalizar(linha))


def remover_cabecalhos_e_rodapes(paginas: list[Pagina]) -> list[str]:
    """
    Remove linhas que se repetem em várias páginas (cabeçalho, rodapé,
    numeração). Sem isso, o rodapé "pág. 2" ou o nome da seguradora no topo
    da página caem no meio de uma cláusula e contaminam a extração. Os
    números são ignorados na comparação, para pegar "pág. 1", "pág. 2"...
    """
    if len(paginas) < 2:
        return []
    contagem: dict[str, int] = {}
    for pg in paginas:
        for assin in {_assinatura_linha(l) for l in pg.texto.splitlines() if l.strip()}:
            contagem[assin] = contagem.get(assin, 0) + 1
    repetidas = {a for a, n in contagem.items()
                 if n >= max(2, (len(paginas) + 1) // 2) and 0 < len(a) <= 160}
    removidas: dict[str, str] = {}
    for pg in paginas:
        manter = []
        for l in pg.texto.splitlines():
            a = _assinatura_linha(l)
            if a in repetidas:
                removidas.setdefault(a, l.strip())
            elif not re.fullmatch(r"\s*p[aá]g(ina)?\.?\s*\d+(\s*de\s*\d+)?\s*", l, re.I):
                manter.append(l)
        pg.texto = "\n".join(manter)
    return list(removidas.values())


# Linha de sumário: "3. OBJETIVO DO SEGURO ........ 18" / "Cláusula 4. Coberturas ..... 9"
_LINHA_SUMARIO = re.compile(r"(?:\.\s?){4,}\s*\d{1,3}\s*$|…{2,}\s*\d{1,3}\s*$")


def remover_sumario(paginas: list[Pagina]) -> int:
    """
    Remove o sumário (índice) de documentos longos. Nas condições gerais
    reais, o sumário repete todos os títulos com a página ao lado; sem esta
    limpeza, cada título vira uma "seção" vazia e o leitor por regras acha a
    cláusula no índice em vez de no texto. Remove também a linha "SUMÁRIO" e
    continuações de títulos quebradas entre duas linhas do índice.
    """
    removidas = 0
    for pg in paginas:
        linhas = pg.texto.splitlines()
        if sum(bool(_LINHA_SUMARIO.search(l)) for l in linhas) < 3:
            continue
        manter = []
        for i, l in enumerate(linhas):
            prox = linhas[i + 1] if i + 1 < len(linhas) else ""
            if (_LINHA_SUMARIO.search(l) or re.fullmatch(r"\s*(SUM[ÁA]RIO|[ÍI]NDICE)\s*", l, re.I)
                    or (l.strip() and len(l.strip()) < 90 and _LINHA_SUMARIO.search(prox)
                        and not l.strip().endswith("."))):
                removidas += 1
                continue
            manter.append(l)
        pg.texto = "\n".join(manter)
    return removidas


def _ocr_ou_marca(img, numero: int, permitir_ocr: bool) -> Pagina:
    if permitir_ocr and ocr_disponivel():
        try:
            texto, conf = ocr_imagem(img)
            return Pagina(numero, texto, "ocr", conf)
        except Exception as exc:  # noqa: BLE001
            log.warning("OCR falhou na página %d: %s", numero, exc)
    return Pagina(numero, "", "ocr_indisponivel")


def _ler_pdf(conteudo: bytes, permitir_ocr: bool, inicio: int = 0) -> list[Pagina]:
    import pdfplumber

    paginas: list[Pagina] = []
    with pdfplumber.PDF(io.BytesIO(conteudo)) as pdf:
        for i, pg in enumerate(pdf.pages, start=1):
            texto = pg.extract_text() or ""
            if len(texto.strip()) >= MIN_CARACTERES_PAGINA:
                paginas.append(Pagina(inicio + i, texto, "texto_pdf"))
                continue
            # página sem camada de texto: rasteriza e aplica OCR
            img = None
            try:
                import pypdfium2 as pdfium

                img = pdfium.PdfDocument(conteudo)[i - 1].render(scale=200 / 72).to_pil()
            except Exception as exc:  # noqa: BLE001
                log.warning("Falha ao rasterizar página %d: %s", i, exc)
            if img is None:
                paginas.append(Pagina(inicio + i, texto, "ocr_indisponivel"))
            else:
                paginas.append(_ocr_ou_marca(img, inicio + i, permitir_ocr))
    return paginas


# --------------------------------------------------------------------------
# Normalização e segmentação
# --------------------------------------------------------------------------

def sem_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto)
                   if not unicodedata.combining(c))


def normalizar(texto: str) -> str:
    """Minúsculas, sem acento, espaços colapsados — para comparar trechos."""
    t = sem_acentos(texto).lower()
    t = re.sub(r"[^a-z0-9%$,./ -]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


@dataclass
class Secao:
    indice: int
    titulo: str
    texto: str
    # parte do documento em que a seção está: "glossario" (definições),
    # "exclusoes" ou "geral". Definições e exclusões mudam o sentido de uma
    # menção: "multas" no glossário não é cobertura; dentro das exclusões, é
    # para excluir.
    parte: str = "geral"

    @property
    def rotulo(self) -> str:
        return f"S{self.indice}"


_MAIUSC = "A-ZÁÉÍÓÚÂÊÔÃÕÇ"
_PADROES_TITULO = [
    # CLÁUSULA 4 – / Cláusula 4ª – / Cláusula Particular Rural nº 1 –
    re.compile(r"^\s*CL[AÁ]USULA\s+(?:PARTICULAR\b.*?|\d+\s*[ªº°]?)\s*[–\-—:.]\s*(.+)$", re.IGNORECASE),
    re.compile(r"^\s*Art\.?\s*\d+\s*[ºo°]?\s*[–\-—:.]\s*(.+)$", re.IGNORECASE),
    # 6. EXCLUSÕES  /  3) TÍTULO
    re.compile(rf"^\s*\d{{1,2}}(?:\.\d{{1,2}})?\s*[.)\-–]\s+([{_MAIUSC}][{_MAIUSC}0-9 ,/()\-–—&]{{3,}})$"),
    # Endorsement No. 1 / Endosso nº 1 — …
    re.compile(r"^\s*(?:Endorsement|Endosso)\s+(?:No\.|n[ºo°])\s*\d+.*$", re.IGNORECASE),
    # SECTION 2 — …
    re.compile(r"^\s*SECTION\s+\d+\b.*$"),
]
# 3.1 Definição de Segurado / 5.1.2 Atos Intencionais (subseção curta, sem ponto final)
_SUBSECAO_DECIMAL = re.compile(rf"^\s*\d{{1,2}}(?:\.\d{{1,2}}){{1,3}}\.?\s+[{_MAIUSC}][^.;:]{{2,70}}$")
# Itens com título em linha: "A) Título: corpo", "IV – Título: corpo", "(b) Title / Título: corpo",
# "12.1.3 Título: corpo"
_ITEM_EM_LINHA = re.compile(
    r"^\s*((?:[A-H]\)|[IVX]{1,5}\s*[–\-—]|\([a-z]\)|\d{1,2}(?:\.\d{1,2}){1,3})\s*[^:]{3,120}?):\s+(.*)$")
_TITULOS_LIVRES = ("QUADRO-RESUMO", "QUADRO RESUMO", "OBJETO DO SEGURO", "PREÂMBULO",
                   "CONDIÇÕES PARTICULARES", "CONDICOES PARTICULARES")


def _caixa_alta_curta(limpa: str) -> bool:
    """Linha curta toda em maiúsculas, sem ponto final → título de seção."""
    letras = [c for c in limpa if c.isalpha()]
    # ≤ 65: nas condições gerais reais, parágrafos inteiros em caixa alta
    # (exclusões em destaque) quebram em linhas de ~75–90 caracteres.
    return (len(limpa) <= 65 and len(limpa.split()) >= 2 and not limpa.endswith((".", ",", ";"))
            and letras and sum(c.isupper() for c in letras) / len(letras) > 0.85)


def _titulo(linha: str, anterior: str = ".") -> tuple[str, str] | None:
    """Devolve (título, resto do corpo na mesma linha) quando a linha abre seção.

    ``anterior`` é a última linha de corpo: uma linha em caixa alta só abre
    seção se a frase anterior terminou — senão é continuação de um parágrafo
    em caixa alta (exclusões em destaque, por exemplo)."""
    limpa = linha.strip()
    if not limpa or len(limpa) > 140:
        return None
    m = _ITEM_EM_LINHA.match(limpa)
    if m and len(m.group(1)) <= 120:
        return m.group(1).strip(), m.group(2).strip()
    for p in _PADROES_TITULO:
        if p.match(limpa):
            return limpa, ""
    if limpa.upper() in _TITULOS_LIVRES or _SUBSECAO_DECIMAL.match(limpa):
        return limpa, ""
    # pergunta curta (linguagem simples): "Quem fica protegido por este seguro?"
    if limpa.endswith("?") and len(limpa) <= 95 and limpa[0].isupper():
        return limpa, ""
    fim_de_frase = anterior.rstrip().endswith((".", ":", "?", ")"))
    if (_caixa_alta_curta(limpa) or _titulo_capitalizado(limpa)) and fim_de_frase:
        return limpa, ""
    return None


def _titulo_capitalizado(limpa: str) -> bool:
    """Subtítulo sem numeração: 'Limite Máximo de Garantia', 'Prazo Adicional'."""
    if len(limpa) > 70 or limpa.endswith((".", ",", ";", ":")) or not limpa[0].isupper():
        return False
    palavras = [w for w in limpa.split() if len(w) > 3]
    if len(limpa.split()) < 2 or not palavras:
        return False
    return sum(w[0].isupper() for w in palavras) / len(palavras) >= 0.6


def segmentar(texto: str) -> list[Secao]:
    """
    Quebra o texto em seções pelos títulos, em qualquer das convenções de
    mercado: "CLÁUSULA 4 –", "Cláusula 4ª –", "6. EXCLUSÕES", "3.1 Título",
    itens "A) …:", "IV – …:", "(b) …:", "Endorsement No. 1", "SECTION 2",
    perguntas curtas (linguagem simples) e linhas curtas em caixa alta.

    Não depende da taxonomia: a identificação de *qual* cláusula cada seção
    trata é feita depois, pelo agente de cláusulas (LLM) ou pelo dicionário
    determinístico. Texto antes do primeiro título vira a seção 0.
    """
    secoes: list[Secao] = []
    titulo_atual, corpo = "CABEÇALHO E QUADRO-RESUMO", []
    for linha in texto.splitlines():
        t = _titulo(linha, corpo[-1] if corpo else ".")
        if t:
            if corpo or secoes:
                secoes.append(Secao(len(secoes), titulo_atual, " ".join(corpo).strip()))
            titulo_atual, corpo = t[0], ([t[1]] if t[1] else [])
        else:
            if linha.strip():
                corpo.append(linha.strip())
    secoes.append(Secao(len(secoes), titulo_atual, " ".join(corpo).strip()))
    marcar_partes(secoes)
    # remove seções vazias mantendo a numeração estável
    secoes = [s for s in secoes if s.texto or s.indice == 0]
    for i, s in enumerate(secoes):
        s.indice = i
    return secoes


_SUBNIVEL = re.compile(r"^\s*(?:\d{1,2}\.\d|[A-Ha-h]\)|\([a-z]\)|[IVX]{1,5}\s*[–\-—.)])")


_CAPITULO = re.compile(
    r"^\s*(?:CL[AÁ]USULA\s+(?:\d+|PARTICULAR)|\d{1,2}\s*[.)\-–]?\s+\D|SE[ÇC][ÃA]O\b|SECTION\s+\d|"
    r"CAP[IÍ]TULO\b|ENDORSEMENT\b|ENDOSSO\b|"
    r"CONDI[ÇC][ÕO]ES\s+(?:ESPECIAIS|PARTICULARES)|COBERTURAS?\s+(?:B[ÁA]SICA|ADICIONA))",
    re.IGNORECASE)


def _titulo_de_topo(titulo: str) -> bool:
    """Título de capítulo ("CLÁUSULA 7.", "4. EXCLUSÕES", "SEÇÃO II"), não
    subseção, alínea nem linha solta em caixa alta."""
    if titulo.strip().endswith("?") and not _SUBNIVEL.match(titulo):
        return True  # documento em perguntas e respostas: cada pergunta é um capítulo
    return bool(_CAPITULO.match(titulo)) and not _SUBNIVEL.match(titulo)


def marcar_partes(secoes: list[Secao]) -> None:
    """Marca cada seção como glossário, exclusões ou geral, herdando do
    capítulo de topo mais recente ("2. GLOSSÁRIO", "Cláusula 7. Exclusões")."""
    parte = "geral"
    for s in secoes:
        t = sem_acentos(s.titulo).upper()
        topo = _titulo_de_topo(s.titulo)
        if ("DEFINIC" in t or "GLOSSARIO" in t) and (topo or not _SUBNIVEL.match(s.titulo)):
            parte = "glossario"
        elif (("EXCLUS" in t or "RISCOS EXCLUIDOS" in t or "NAO ESTA COBERTO" in t)
              and (topo or not _SUBNIVEL.match(s.titulo))):
            parte = "exclusoes"
        elif topo:
            parte = "geral"
        s.parte = parte
