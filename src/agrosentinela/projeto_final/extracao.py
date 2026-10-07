"""
Extração estruturada: dados cadastrais (quadro-resumo) e cláusulas.

Dois extratores convivem, de propósito:

* **LLM (Groq)** — o caminho principal. Lê o texto como um especialista
  leria: identifica a cláusula pelo *significado* (não pelo título),
  classifica o nível de atendimento e devolve a **evidência** (seção e
  trecho) que justifica cada classificação.
* **Determinístico** — dicionário de títulos + expressões-gatilho de nível
  + expressões regulares no quadro-resumo. Serve como *linha de base*
  (para medir quanto a IA agrega), como *contingência* (sem chave, sem cota)
  e como *verificação cruzada* dos números extraídos pela IA.

O contrato com o modelo é estrito: saída JSON, níveis num vocabulário
fechado, evidência obrigatória apontando para uma seção existente. O agente
de validação confere tudo isso antes de qualquer dado chegar ao banco.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .clausulas import CLAUSULAS, CLAUSULAS_POR_CODIGO, NIVEIS
from .documentos import Secao, normalizar, sem_acentos

NIVEIS_VALIDOS = tuple(NIVEIS)  # ampla, padrao, restrita, ausente, excluida

CAMPOS_CADASTRAIS = (
    "seguradora", "numero_apolice", "tomadora", "tomadora_cnpj", "segmento",
    "municipio", "uf", "vigencia_inicio", "vigencia_fim", "retroatividade",
    "retroatividade_ilimitada", "lmg", "premio", "franquia",
)


@dataclass
class ClausulaExtraida:
    codigo: str
    nivel: str
    secao: str = ""             # rótulo "S7"
    evidencia: str = ""
    justificativa: str = ""
    metodo: str = "deterministico"
    evidencia_verificada: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class ExtracaoApolice:
    cadastro: dict[str, Any] = field(default_factory=dict)
    clausulas: dict[str, ClausulaExtraida] = field(default_factory=dict)
    metodo_cadastro: str = "deterministico"
    metodo_clausulas: str = "deterministico"
    modelo: str = ""
    avisos: list[str] = field(default_factory=list)
    tipo_documento: str = "apolice"   # "apolice" | "condicoes_gerais"


# ==========================================================================
# Números e datas em português
# ==========================================================================

_NUM_MONETARIO = re.compile(
    r"(?:R\$|BRL|US\$)?\s*(\d[\d.,]*)\s*(bilh(?:ão|ões|ao|oes)|milh(?:ão|ões|ao|oes)|mi\b|mil\b)?",
    re.IGNORECASE)
_MONEY = re.compile(
    r"(?:R\$|BRL)\s*(\d[\d.,]*)\s*(bilh(?:ão|ões|ao|oes)|milh(?:ão|ões|ao|oes)|mil\b)?", re.IGNORECASE)


def _numero(token: str) -> float | None:
    """Interpreta '5.000.000,00' (pt-BR), '5,000,000.00' (en), '1,5', '25'."""
    t = token.strip(".,")
    if not t:
        return None
    if "." in t and "," in t:
        dec = "," if t.rfind(",") > t.rfind(".") else "."
        mil = "." if dec == "," else ","
        t = t.replace(mil, "").replace(dec, ".")
    elif "," in t:
        t = t.replace(",", "") if re.fullmatch(r"\d{1,3}(,\d{3})+", t) else t.replace(",", ".")
    elif "." in t:
        if re.fullmatch(r"\d{1,3}(\.\d{3})+", t):
            t = t.replace(".", "")
    try:
        return float(t)
    except ValueError:
        return None


def _multiplicador(m: str | None) -> float:
    m = (m or "").lower()
    if m.startswith("bilh"):
        return 1e9
    if m.startswith("milh") or m == "mi":
        return 1e6
    if m == "mil":
        return 1e3
    return 1.0


def valor_reais(texto) -> float | None:
    """Primeiro valor monetário do texto, em qualquer grafia de mercado:
    'R$ 5.000.000,00', 'R$ 5 milhões', 'R$ 1,5 milhão', 'R$ 25 mil',
    'BRL 30,000,000.00', 'R$ 5.000.000,00 (cinco milhões de reais)'."""
    if texto is None:
        return None
    if isinstance(texto, (int, float)):
        return float(texto)
    t = str(texto)
    m = _MONEY.search(t) or _NUM_MONETARIO.search(t)
    if not m:
        return None
    v = _numero(m.group(1))
    return None if v is None else v * _multiplicador(m.group(2))


def valores_monetarios(texto: str) -> list[float]:
    """Todos os valores precedidos de R$/BRL no texto (para verificação cruzada)."""
    out = []
    for m in _MONEY.finditer(texto or ""):
        v = _numero(m.group(1))
        if v is not None:
            out.append(v * _multiplicador(m.group(2)))
    return out


_MESES = {"janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4, "maio": 5,
          "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11,
          "dezembro": 12}
_DATA = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})"                                   # ISO
    r"|(\d{1,2})[/.](\d{1,2})[/.](\d{4})"                        # 01/07/2026 ou 01.07.2026
    r"|(\d{1,2})\s*[ºo°]?\s+de\s+([a-zçã]+)\s+de\s+(\d{4})",     # 1º de julho de 2026
    re.IGNORECASE)


def _de_match(m) -> date | None:
    try:
        if m.group(1):
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if m.group(4):
            return date(int(m.group(6)), int(m.group(5)), int(m.group(4)))
        mes = _MESES.get(m.group(8).lower())
        return date(int(m.group(9)), mes, int(m.group(7))) if mes else None
    except (ValueError, TypeError):
        return None


def datas(texto: str) -> list[date]:
    return [d for d in (_de_match(m) for m in _DATA.finditer(texto or "")) if d]


def data_br(texto) -> date | None:
    if not texto:
        return None
    if isinstance(texto, date):
        return texto
    ds = datas(str(texto))
    return ds[0] if ds else None


# ==========================================================================
# Extrator determinístico — quadro-resumo
# ==========================================================================
#
# Cada seguradora rotula o quadro do seu jeito ("Limite Máximo de Garantia",
# "LMI", "Limit of Liability", "Até quanto o seguro paga"), coloca-o no início,
# no fim ou em prosa. A leitura determinística procura uma lista de rótulos
# conhecidos do mercado; o que não encontrar fica para o LLM. Não é um
# leitor universal — é a linha de base e a conferência cruzada dos números.

# Rótulos do mais específico para o mais genérico. Quadros em tabela quebram o
# rótulo em duas linhas ("Item 5 — Limit of Liability /" + "Limite (LMG)"), por
# isso os padrões usam só o começo distintivo do rótulo.
_ROTULOS: dict[str, list[str]] = {
    "seguradora": [r"Item 1 — Insurer\s*/\s*Seguradora", r"(?m)^\s*(?:\d+\.\s*)?Seguradora\s*:?\s+(?=[A-ZÁÉÍÓÚ])",
                   r"(?m)^\s*A (?=[A-ZÁÉÍÓÚ][^,\n]{3,80}, inscrita no CNPJ)"],
    "numero_apolice": [r"N[uú]mero da ap[oó]lice", r"Policy No\. / Ap[oó]lice n[ºo°]",
                       r"Ap[oó]lice n[ºo°]", r"(?m)^\s*Ap[oó]lice\s+(?=[A-Z0-9])"],
    "tomadora": [r"Item 2 — Named Insured / Companhia", r"Sociedade \(Tomador\)",
                 r"(?:\d+\.\s*)?Empresa Tomadora:?", r"Quem contratou:?", r"em favor da Tomadora",
                 r"(?m)^\s*Tomadora?\s*:?\s+(?=[A-ZÁÉÍÓÚ])"],
    "sede": [r"Item 3 — Principal Address\s*/\s*Sede", r"Endere[cç]o da Sociedade", r"Munic[ií]pio/UF",
             r"(?m)^\s*(?:\d+\.\s*)?Sede:?", r"com sede em"],
    "vigencia": [r"Item 4 — Policy Period", r"Per[ií]odo de Vig[eê]ncia", r"Quando vale",
                 r"vigente de", r"(?m)^\s*(?:\d+\.\s*)?Vig[eê]ncia\s*:?"],
    "retro": [r"Item 7 — Continuity", r"Data (?:limite )?de retroatividade:?",
              r"Fatos anteriores cobertos a partir", r"com data de retroatividade fixada em",
              r"(?m)^\s*Retroatividade"],
    "lmg": [r"Item 5 — Limit of Liability", r"Limite M[aá]ximo de Garantia(?: da Ap[oó]lice)?(?: \(LMG\))?:?",
            r"Limite M[aá]ximo de Indeniza[cç][aã]o(?: \(LMI\))?", r"At[eé] quanto o seguro paga:?",
            r"at[eé] o Limite M[aá]ximo de Garantia de"],
    "franquia": [r"Item 6 — Retention", r"Participa[cç][aã]o Obrigat[oó]ria do Segurado \(POS\):?",
                 r"Parte que a cooperativa paga", r"\(franquia\) de",
                 r"(?m)^\s*Franquia(?: \([^)]*\))?:?"],
    "premio": [r"Item 8 — Premium", r"Quanto custa:?", r"pr[eê]mio total de",
               r"(?m)^\s*(?:\d+\.\s*)?Pr[eê]mio(?: L[ií]quido \+ IOF| total| Total| l[ií]quido total)?:?"],
}


def _procurar(texto: str, chave: str, extrator, alcance: int = 160):
    """Tenta cada rótulo, e cada ocorrência dele, até o extrator achar um valor."""
    for rot in _ROTULOS[chave]:
        for m in re.finditer(rot, texto, re.IGNORECASE):
            v = extrator(texto[m.end(): m.end() + alcance])
            if v not in (None, "", []):
                return v
    return None


def _nome(trecho: str) -> str | None:
    linha = trecho.replace("\n", " ").strip(" :.")
    nome = re.split(r"\s*[—,(]\s*(?:inscrita no |inscrita sob )?CNPJ|\s+\(CNPJ|, inscrita|\s+—\s+CNPJ"
                    r"|\s+CNPJ\b|\s+Munic[ií]pio/UF|\s+Item \d", linha)[0].strip(" :.,")
    return nome if 3 <= len(nome) <= 140 and nome[0].isupper() else None


_SEGURADORA = re.compile(
    r"\b([A-Z][A-Za-zÀ-ú&]+(?:\s+[A-Z][A-Za-zÀ-ú&.]+){0,3}\s+"
    r"(?:Seguros|SEGUROS|Seguradora|SEGURADORA|Cia\.?\s+de\s+Seguros(?:\s+Gerais)?|"
    r"Companhia\s+de\s+Seguros(?:\s+Gerais)?)(?:\s+(?:S\.?\s?A\.?|Gerais))?)")
_NAO_NOME = {"CONDICOES", "CONDICAO", "SEGURO", "APOLICE", "RESPONSABILIDADE", "CLAUSULA",
             "SUPERINTENDENCIA", "SOCIEDADE", "PRIVADOS", "OUTROS", "DEMAIS", "AS", "OS",
             "DA", "DE", "DO", "PELA", "PELO", "NA", "NO", "ESTA", "ESTE", "QUAISQUER"}


def seguradora_provavel(texto: str, linhas_repetidas: list[str] | None = None) -> str | None:
    """Nome da seguradora em documentos sem quadro-resumo (condições gerais):
    o nome mais frequente com a forma "<Nome> Seguros S.A." no cabeçalho,
    no rodapé, no início ou no fim do documento."""
    fontes = list(linhas_repetidas or []) + [texto[:5000], texto[-5000:], texto]
    contagem: dict[str, int] = {}
    for peso, fonte in zip([5] * len(linhas_repetidas or []) + [3, 2, 1], fontes):
        for m in _SEGURADORA.finditer(fonte):
            nome = " ".join(m.group(1).split())
            if sem_acentos(nome.split()[0]).upper() in _NAO_NOME:
                continue
            contagem[nome] = contagem.get(nome, 0) + peso
    if not contagem:
        return None
    return max(contagem, key=lambda k: (contagem[k], len(k)))


def extrair_cadastro_regex(texto: str) -> dict[str, Any]:
    """Lê o quadro de dados por rótulos conhecidos do mercado (início OU fim do documento)."""
    out: dict[str, Any] = {k: None for k in CAMPOS_CADASTRAIS}
    # o aviso de simulação não faz parte da apólice
    limpo = re.sub(r"DOCUMENTO SIMULADO PARA FINS ACAD[ÊE]MICOS.*?seguradora\s+real\.", " ", texto,
                   flags=re.IGNORECASE | re.DOTALL)
    cab = limpo[:5000] + "\n" + limpo[-2500:]

    out["seguradora"] = _procurar(cab, "seguradora", _nome, 140)
    num = _procurar(cab, "numero_apolice",
                    lambda t: (re.match(r"\s*([A-Z0-9][A-Z0-9./-]{4,})", t) or [None, None])[1], 40)
    out["numero_apolice"] = num
    out["tomadora"] = _procurar(cab, "tomadora", _nome, 220)
    m = re.search(r"CNPJ(?:\s+(?:sob o n[ºo°]|do Tomador|da Tomadora))?\s*:?\s*([\d./-]{14,20})",
                  _procurar(cab, "tomadora", lambda t: t, 260) or "")
    out["tomadora_cnpj"] = m.group(1).strip(".") if m else None

    def _local(t: str):
        m = (re.search(r"munic[ií]pio de ([^,]+), Estado ([A-Z]{2})", t)
             or re.search(r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ú' ()-]{1,40}?)\s*(?:/|,|—)\s*([A-Z]{2})\b", t))
        return (m.group(1).strip(), m.group(2)) if m else None
    local = _procurar(cab, "sede", _local, 120) or _procurar(cab, "tomadora", _local, 260)
    if local:
        out["municipio"], out["uf"] = local

    def _duas_datas(t: str):
        ds = datas(t)
        return ds[:2] if len(ds) >= 2 else None
    ds = _procurar(cab, "vigencia", _duas_datas, 200)
    if not ds:  # especificação com início e término em linhas separadas
        ini = re.search(r"In[ií]cio de Vig[eê]ncia\s*:?\s*(.{0,40})", cab, re.IGNORECASE)
        fim = re.search(r"T[eé]rmino de Vig[eê]ncia\s*:?\s*(.{0,40})", cab, re.IGNORECASE)
        ds = [d for d in (data_br(ini.group(1)) if ini else None,
                          data_br(fim.group(1)) if fim else None) if d]
    if ds and len(ds) >= 2:
        out["vigencia_inicio"], out["vigencia_fim"] = ds[0], ds[1]

    def _retro(t: str):
        if re.match(r"\s*:?\s*(?:Date\s+)?(?:Unlimited|Ilimitada|qualquer data|sem limite)", t, re.IGNORECASE):
            return "ilimitada"
        return data_br(t[:60])
    retro = _procurar(cab, "retro", _retro, 80)
    if retro == "ilimitada" or (retro is None and re.search(
            r"sem limita[cç][aã]o de data retroativa|retroatividade ilimitada", cab, re.IGNORECASE)):
        out["retroatividade_ilimitada"] = True
    else:
        out["retroatividade"] = retro
        out["retroatividade_ilimitada"] = False if retro else None
    for campo in ("lmg", "franquia", "premio"):
        out[campo] = _procurar(cab, campo, lambda t: valor_reais(t[:90]) if _MONEY.search(t[:90]) else None, 120)
    return out


# ==========================================================================
# Extrator determinístico — cláusulas
# ==========================================================================

# Palavras de título (sem acento, maiúsculas). A ordem importa: a primeira
# regra que casar vence — por isso as mais específicas vêm antes. O
# vocabulário foi ampliado com o das condições gerais reais de D&O testadas
# (AXA, Allianz, Porto): "Cobertura A — pagamento ao segurado", "participação
# obrigatória do segurado", "limite agregado", "gastos com defesa",
# "prioridade de pagamento", "divisibilidade", "litígio anterior e pendente"…
_DICIONARIO_TITULOS: list[tuple[str, tuple[str, ...]]] = [
    ("AGR-01", ("CREDITO RURAL", "PROAGRO", "SICOR")),
    ("AGR-02", ("AMBIENTAIS RURAIS", "AMBIENTAL NA CADEIA", "RESPONSABILIDADE AMBIENTAL",
                "AMBIENTAL RURAL", "AMBIENTAL DO ADMINISTRADOR", "DANOS AMBIENTAIS")),
    ("AGR-03", ("RECUPERACAO JUDICIAL", "INSOLVENCIA", "FALENCIA", "ADMINISTRADOR JUDICIAL")),
    ("EXC-05", ("FATOS CONHECIDOS", "PRETERITOS", "LITIGIOS ANTERIORES", "FATOS ANTERIORES",
                "LITIGIO ANTERIOR", "CIRCUNSTANCIAS ANTERIORES", "RECLAMACOES ANTERIORES",
                "RECLAMACOES/CIRCUNSTANCIAS ANTERIORES", "ANTERIOR E PENDENTE")),
    ("EXC-02", ("ENTRE SEGURADOS", "SEGURADO CONTRA SEGURADO", "CONTRA SEGURADO",
                "SOCIO CONTRA", "SOCIOCONTRA")),
    ("EXC-01", ("DOLOS", "INTENCIONA", "FRAUD", "EXCLUSAO DE CONDUTA", "ATOS ILICITOS")),
    ("LIM-02", ("SUBLIMITE",)),
    ("LIM-03", ("REINTEGRA", "RESTABELEC")),
    ("LIM-01", ("LIMITE MAXIMO", "LIMITE AGREGADO")),
    ("LIM-04", ("FRANQUIA", "PARTICIPACAO OBRIGATORIA")),
    ("DEF-02", ("ADIANTAMENTO", "ANTECIPAD", "ANTECIPACAO")),
    ("DEF-01", ("CUSTOS DE DEFESA", "DESPESAS DE DEFESA", "GASTOS COM DEFESA")),
    ("DEF-03", ("ADVOGADO", "PATRONO")),
    ("DEF-04", ("SEPARABILIDADE", "INDIVISIBILIDADE", "DIVISIBILIDADE")),
    ("DEF-05", ("MULTA",)),
    ("ESC-02", ("SIDE A", "COBERTURA A", "NAO INDENIZ", "PAGAMENTO AO SEGURADO")),
    ("ESC-03", ("SIDE B", "COBERTURA B", "REEMBOLSO")),
    ("ESC-04", ("SIDE C", "COBERTURA C", "VALORES MOBILIARIOS", "MERCADO DE CAPITAIS")),
    ("ESC-01", ("DEFINICAO DE SEGURADO", "PESSOAS SEGURADAS")),
    ("ESC-05", ("GEOGRAF", "TERRITORIAL", "JURISDICAO")),
    ("ESC-06", ("SUBSIDIARIA", "CONTROLADAS")),
    ("TMP-01", ("RETROATIV",)),
    ("TMP-02", ("PRAZO ADICIONAL", "PRAZO COMPLEMENTAR", "PRAZO SUPLEMENTAR")),
    ("TMP-03", ("CIRCUNSTANCIA",)),
    ("TMP-04", ("MUDANCA DE CONTROLE", "ALTERACAO DE CONTROLE", "TRANSFERENCIA DE CONTROLE",
                "VENDA DE CONTROLE", "CONTROLE", "RUN-OFF", "RUN OFF")),
    ("EXC-03", ("POLUICAO", "POLUENTE", "AMBIENTA")),
    ("EXC-04", ("CIBERN", "DADOS E SISTEMAS", "SEGURANCA DA INFORMACAO")),
    ("OPE-01", ("CANCELAMENTO", "RESCISAO")),
    ("OPE-02", ("ARBITRAG", "CONTROVERSIA", "FORO", "RESOLUCAO DE DISPUTAS")),
    ("OPE-03", ("SUB-ROGA", "SUBROGA", "REGRESSO")),
    ("OPE-04", ("ORDEM DE PAGAMENTO", "ORDEM DOS PAGAMENTOS", "ORDEM DE PAGAMENTOS", "PRIORIDADE")),
    ("OPE-05", ("MOEDA", "ATUALIZACAO DE VALORES", "ATUALIZACAO MONETARIA")),
]
# Títulos que, sozinhos, são a cláusula (o glossário real define "Segurado").
_TITULOS_EXATOS = {"SEGURADO": "ESC-01", "SEGURADOS": "ESC-01", "FRANQUIA": "LIM-04",
                   "OPERACAO": "TMP-04"}

# Expressões de corpo (normalizadas) para achar a cláusula quando nenhum
# título a nomeia — típico de exclusões em alíneas e de documentos longos.
TERMOS_CORPO: dict[str, tuple[str, ...]] = {
    "ESC-01": ("administrador de fato", "conjuge", "espolio"),
    "ESC-02": ("nao indenizad", "cobertura a"),
    "ESC-03": ("reembolso a tomadora", "reembolso da empresa", "reembolsar a sociedade",
               "cobertura b"),
    "ESC-04": ("valores mobiliarios", "cobertura c"),
    "ESC-05": ("qualquer parte do mundo", "ambito geografico", "territorio brasileiro"),
    "ESC-06": ("subsidiaria", "controlada"),
    "LIM-01": ("limite maximo de garantia", "limite agregado"),
    "LIM-02": ("sublimite",),
    "LIM-03": ("reintegra",),
    "LIM-04": ("franquia", "participacao obrigatoria"),
    "DEF-01": ("custos de defesa", "despesas de defesa", "gastos com defesa"),
    "DEF-02": ("adiantamento", "antecipacao dos custos", "adiantara", "pagamento antecipado"),
    "DEF-03": ("advogado", "patrono"),
    "DEF-04": ("separabilidade", "nao sera imputad", "nao serao imputad", "divisibilidade"),
    "DEF-05": ("multas", "penalidades"),
    "TMP-01": ("retroatividade",),
    "TMP-02": ("prazo adicional", "prazo complementar", "prazo suplementar"),
    "TMP-03": ("notificacao de circunstancia", "circunstancias que possam"),
    "TMP-04": ("mudanca de controle", "alteracao de controle", "transferencia de controle",
               "run-off", "run off"),
    "EXC-01": ("dolo", "ato doloso", "fraude", "fraudulent"),
    "EXC-02": ("segurado contra segurado", "movida por um segurado", "proposta por qualquer segurado",
               "por outro segurado"),
    "EXC-03": ("poluente", "poluicao", "dano ambiental", "danos ambientais"),
    "EXC-04": ("cibernet", "violacao de dados", "ataque hacker", "vazamento de dados"),
    "EXC-05": ("fatos conhecidos", "litigio anterior", "litigios anteriores", "anteriores a data",
               "pendente"),
    "OPE-01": ("cancelamento", "rescisao"),
    "OPE-02": ("arbitragem", "juizo arbitral", "foro"),
    "OPE-03": ("sub-rogacao", "sub-rogara", "subrogacao", "direito de regresso"),
    "OPE-04": ("ordem de pagamento", "prioridade de pagamento", "pagara primeiramente"),
    "OPE-05": ("moeda", "taxa de cambio", "variacao cambial"),
    "AGR-01": ("credito rural", "proagro", "manual de credito rural"),
    "AGR-02": ("responsabilidade ambiental", "dano ambiental", "danos ambientais"),
    "AGR-03": ("recuperacao judicial", "falencia", "administrador judicial", "insolvencia"),
}

# Gatilhos genéricos de nível — vocabulário de qualquer wording de D&O, não
# frases copiadas do simulador. É uma heurística honesta de linha de base.
_GATILHOS_EXCLUSAO_TOTAL = ("excluem-se quaisquer", "de qualquer natureza",
                            "inclusive custos de defesa", "inclusive por falha")
_GATILHOS_RESTRITIVOS = ("exclusivamente", "somente", "apenas as", "nao ha adiantamento",
                         "sem excecoes", "integram e reduzem", "a qualquer tempo",
                         "painel credenciado", "vinculam todos", "cancelada",
                         "dolares", "ordem cronologica", "inclusive contra outros",
                         "dependera de analise", "minimo previsto", "ainda que",
                         "nao sao considerados", "participacao obrigatoria",
                         "excluidas multas", "alegue")
_GATILHOS_AMPLOS = ("qualquer parte do mundo, inclusive", "ilimitada", "sem cobranca",
                    "automaticamente", "livremente", "nao serao imputados",
                    "independentemente", "irrecorrivel", "renuncia expressamente",
                    "com prioridade", "nao podera ser cancelada", "limite adicional",
                    "nao reduz", "100% do lmg", "ipca", "nao se aplica a", "ate o lmg",
                    "nao afeta", "administrador de fato", "cvm")


def _titulo_sem_numeracao(titulo: str) -> str:
    t = sem_acentos(titulo).upper()
    t = re.sub(r"^\s*(?:CLAUSULA\s+\d+\s*[ºª°]?|\d{1,2}(?:\.\d{1,2})*|[IVX]{1,5}|[A-Ha-h])\s*[.)\-–—:]*\s*",
               "", t)
    return re.sub(r"[^A-Z0-9 /-]+", " ", t).strip()


def _titulo_normalizado(titulo: str) -> str:
    t = sem_acentos(titulo).upper()
    return re.sub(r"[\u2010-\u2015\u2212]", "-", t)   # hífens tipográficos do Word


def codigos_do_titulo(titulo: str) -> set[str]:
    """Todos os códigos que o título nomeia ("Danos ambientais" serve à
    cobertura ambiental do administrador e à exclusão de poluição)."""
    t = _titulo_normalizado(titulo)
    exato = _TITULOS_EXATOS.get(re.sub(r"\s+", " ", _titulo_sem_numeracao(titulo)))
    out = {exato} if exato else set()
    out |= {cod for cod, chaves in _DICIONARIO_TITULOS if any(k in t for k in chaves)}
    return out


def classificar_titulo(titulo: str) -> str | None:
    t = _titulo_normalizado(titulo)
    exato = _TITULOS_EXATOS.get(re.sub(r"\s+", " ", _titulo_sem_numeracao(titulo)))
    if exato:
        return exato
    for codigo, chaves in _DICIONARIO_TITULOS:
        if any(k in t for k in chaves):
            # "Cobertura para danos ambientais" fora das exclusões é a
            # cobertura do administrador (AGR-02); dentro delas, EXC-03.
            return codigo
    return None


def nivel_por_gatilhos(texto: str) -> str:
    t = normalizar(texto)
    if any(g in t for g in _GATILHOS_EXCLUSAO_TOTAL):
        return "excluida"
    amplos = sum(g in t for g in _GATILHOS_AMPLOS)
    restritos = sum(g in t for g in _GATILHOS_RESTRITIVOS)
    if amplos > restritos:
        return "ampla"
    if restritos > amplos:
        return "restrita"
    return "padrao"


_EXPRESSOES_EXCLUSAO = ("exclu", "nao cobre", "nao estao cobert", "nao esta cobert",
                        "nao sera indeniz", "nao serao indeniz", "nao responde",
                        "not cover", "exclusion", "shall not be liable")


def _linguagem_de_exclusao(texto: str) -> bool:
    t = normalizar(texto)
    return any(x in t for x in _EXPRESSOES_EXCLUSAO)


def _e_exclusao(codigo: str) -> bool:
    return codigo.startswith("EXC-")


def _trecho(texto: str, termos: tuple[str, ...], tamanho: int) -> str:
    """Janela de ``tamanho`` caracteres em torno da primeira ocorrência."""
    if len(texto) <= tamanho:
        return texto
    t = normalizar(texto)
    pos = min((t.find(x) for x in termos if x in t), default=-1)
    if pos < 0:
        return texto[:tamanho]
    # normalizar() encolhe pouco o texto; a posição serve de aproximação
    ini = max(0, min(len(texto) - tamanho, int(pos * len(texto) / max(len(t), 1)) - tamanho // 4))
    return ("…" if ini else "") + texto[ini:ini + tamanho] + "…"


def candidatos(secoes: list[Secao], codigo: str) -> list[tuple[float, Secao, str]]:
    """Seções que provavelmente tratam da cláusula ``codigo``, com pontuação.

    Título que nomeia a cláusula pesa mais que menção no corpo; definição de
    glossário pesa pouco (define o termo, não concede nem exclui); para os
    códigos de exclusão, só vale menção dentro da parte de exclusões."""
    termos = TERMOS_CORPO.get(codigo, ())
    out = []
    for s in secoes:
        if s.indice == 0 and len(secoes) > 1:
            continue
        pontos, origem = 0.0, ""
        cods = codigos_do_titulo(s.titulo)
        if codigo in cods:
            # título que nomeia uma só cláusula vale mais que um título genérico
            pontos, origem = (3.0 if len(cods) == 1 else 2.4), "titulo"
        corpo = normalizar(s.texto)
        hits = sum(corpo.count(x) for x in termos)
        if hits and (not _e_exclusao(codigo) or s.parte == "exclusoes"):
            pontos += min(hits, 3) * 0.6
            origem = origem or "corpo"
        if not pontos:
            continue
        if s.parte == "glossario":
            pontos *= 0.3
        elif _e_exclusao(codigo) and s.parte == "exclusoes":
            pontos *= 1.3
        out.append((pontos, s, origem))
    out.sort(key=lambda x: (-x[0], x[1].indice))
    return out


def extrair_clausulas_deterministico(secoes: list[Secao]) -> dict[str, ClausulaExtraida]:
    """Linha de base por regras: para cada código, a seção mais provável
    (título > corpo; fora do glossário > glossário) e o nível por gatilhos.
    Uma cobertura que só aparece dentro das exclusões fica "excluida"."""
    out: dict[str, ClausulaExtraida] = {}
    for c in CLAUSULAS:
        cands = candidatos(secoes, c.codigo)
        # menção solta no corpo, sem título, só conta se for forte (≥ 2 ocorrências)
        cands = [x for x in cands if x[2] == "titulo" or x[0] >= 1.2 * (0.3 if x[1].parte == "glossario" else 1)]
        if not cands:
            out[c.codigo] = ClausulaExtraida(codigo=c.codigo, nivel="ausente",
                                             justificativa="Nenhuma seção correspondente.",
                                             metodo="deterministico")
            continue
        _, s, origem = cands[0]
        termos = TERMOS_CORPO.get(c.codigo, ())
        trecho = s.texto if origem == "titulo" else _trecho(s.texto, termos, 600)
        if not _e_exclusao(c.codigo) and all(x[1].parte == "exclusoes" for x in cands) \
                and (origem == "titulo" or _linguagem_de_exclusao(s.titulo + " " + trecho)):
            nivel = "excluida"
        elif s.parte == "glossario" and len(cands) == 1:
            nivel = "padrao"
        else:
            nivel = nivel_por_gatilhos(trecho)
        out[c.codigo] = ClausulaExtraida(
            codigo=c.codigo, nivel=nivel, secao=s.rotulo,
            evidencia=trecho.lstrip("…")[:220],
            justificativa=("Título reconhecido por dicionário" if origem == "titulo"
                           else "Expressão encontrada no texto") + f" ({s.parte}); nível por expressões-gatilho.",
            metodo="deterministico", evidencia_verificada=True,
        )
    return out


def documento_longo(secoes: list[Secao], limite_chars: int = 14000) -> bool:
    return sum(len(s.texto) + len(s.titulo) + 8 for s in secoes if s.indice != 0) > limite_chars


# Em documentos longos, a classificação vai em lotes de códigos: cada lote
# recebe os trechos dos SEUS códigos (o dobro de texto por cláusula).
LOTES_CODIGOS: tuple[tuple[str, ...], ...] = (
    tuple(c.codigo for c in CLAUSULAS if c.codigo[:3] in ("ESC", "LIM", "DEF", "TMP")),
    tuple(c.codigo for c in CLAUSULAS if c.codigo[:3] in ("EXC", "OPE", "AGR")),
)


def selecionar_trechos(secoes: list[Secao], limite_chars: int = 14000,
                       por_codigo: int = 2, tamanho: int = 900,
                       codigos: tuple[str, ...] | None = None) -> str:
    """
    Monta o texto que vai ao LLM. Documento curto: vai inteiro. Documento
    longo (condições gerais reais têm 150–250 mil caracteres; o plano
    gratuito da Groq aceita ~8 mil tokens por minuto): para cada uma das 32
    cláusulas, pega as seções mais prováveis e um trecho de até ``tamanho``
    caracteres de cada, em ordem de documento, até ``limite_chars``. É uma
    recuperação de trechos (RAG simples) sem banco vetorial: título +
    vocabulário de mercado + parte do documento (glossário/exclusões).
    """
    corpo = [s for s in secoes if s.indice != 0 or len(secoes) == 1]
    inteiro = "\n\n".join(f"[{s.rotulo}] {s.titulo}\n{s.texto}" for s in corpo)
    if len(inteiro) <= limite_chars:
        return inteiro
    escolhidas: dict[int, set[str]] = {}
    alvo = codigos or tuple(c.codigo for c in CLAUSULAS)
    rodada = [(cod, candidatos(secoes, cod)[:por_codigo]) for cod in alvo]
    # 1ª passada: a melhor seção de cada código; 2ª: a segunda melhor
    blocos: dict[int, str] = {}
    total = 0
    for k in range(por_codigo):
        for codigo, cands in rodada:
            if len(cands) <= k:
                continue
            _, s, _ = cands[k]
            escolhidas.setdefault(s.indice, set()).add(codigo)
            if s.indice in blocos:
                continue
            termos = tuple(t for c in escolhidas[s.indice] for t in TERMOS_CORPO.get(c, ()))
            parte = {"glossario": " · glossário", "exclusoes": " · exclusões"}.get(s.parte, "")
            bloco = f"[{s.rotulo}{parte}] {s.titulo}\n{_trecho(s.texto, termos, tamanho)}"
            if total + len(bloco) > limite_chars:
                continue
            blocos[s.indice] = bloco
            total += len(bloco)
    cab = (f"[Documento longo: {len(corpo)} seções, {len(inteiro):,} caracteres. Abaixo, os "
           f"trechos mais prováveis de cada cláusula da taxonomia, selecionados "
           f"automaticamente e em ordem de documento.]").replace(",", ".")
    return cab + "\n\n" + "\n\n".join(blocos[i] for i in sorted(blocos))


# ==========================================================================
# Extrator LLM — prompts
# ==========================================================================

SISTEMA_CADASTRO = """Você é um analista de subscrição de seguros D&O no Brasil.
Extraia os dados cadastrais de uma apólice e responda SOMENTE com um objeto
JSON com exatamente estas chaves:
seguradora (string), numero_apolice (string), tomadora (string, razão social
sem o CNPJ), tomadora_cnpj (string), segmento (atividade da tomadora),
municipio (string), uf (sigla), vigencia_inicio (AAAA-MM-DD),
vigencia_fim (AAAA-MM-DD), retroatividade (AAAA-MM-DD ou null),
retroatividade_ilimitada (true/false), lmg (número em reais), premio (número
em reais), franquia (número em reais).
Atenção: cada seguradora organiza a apólice de um jeito. Os dados podem estar
numa tabela no início, numa "Especificação" no FIM do documento, num
parágrafo corrido (preâmbulo), num "Policy Schedule" bilíngue (Item 1…9) ou
num resumo em linguagem simples ("Até quanto o seguro paga", "Quanto custa").
O limite pode se chamar LMG, LMI, Limit of Liability ou "valor máximo do
seguro"; a franquia, POS, participação obrigatória ou Retention.
Valores podem vir como "R$ 5.000.000,00", "R$ 5 milhões", "R$ 1,5 milhão",
"R$ 25 mil" ou "BRL 5,000,000.00" — converta sempre para número em reais
(ex.: 5000000.0). Datas podem vir como 01/07/2026, 01.07.2026, 2026-07-01
ou "1º de julho de 2026".
Se um dado não estiver no texto, use null — NUNCA invente. O texto pode vir
de OCR e conter pequenos erros: corrija só o que for inequívoco."""


def _tabela_taxonomia() -> str:
    linhas = []
    for c in CLAUSULAS:
        linhas.append(f"- {c.codigo} | {c.nome} | o que verificar: {c.pergunta}")
    return "\n".join(linhas)


SISTEMA_CLAUSULAS = f"""Você é um especialista em seguros D&O (Directors & Officers)
no mercado brasileiro, com foco em empresas do agronegócio. Sua tarefa é
mapear as condições particulares de uma apólice para uma TAXONOMIA FIXA de
cláusulas e classificar o nível de proteção ao segurado em cada uma.

TAXONOMIA (código | cláusula | o que verificar):
{_tabela_taxonomia()}

NÍVEIS (vocabulário fechado):
- "ampla": protege integralmente, sem condicionantes relevantes (para
  exclusões: a exclusão é estreita e favorável ao segurado).
- "padrao": cobre nos termos usuais de mercado.
- "restrita": cobre com sublimite, condição, carência, painel, franquia
  incidente ou redação desfavorável relevante.
- "excluida": a apólice trata do tema PARA EXCLUIR a proteção.
- "ausente": o tema não aparece em nenhuma seção.

REGRAS
1. Classifique pelo SIGNIFICADO, não pelo título nem pela posição. Cada
   seguradora organiza o documento de um jeito: cláusulas numeradas,
   alíneas dentro de uma lista de exclusões, perguntas e respostas em
   linguagem simples, wording bilíngue (Side A = Cobertura A, Defence Costs =
   custos de defesa, Retention = franquia), prazo complementar/suplementar
   (= prazo adicional), LMI (= LMG). Títulos podem vir com erros de OCR.
   Uma cobertura (ex.: crédito rural, multas, recuperação judicial) que
   aparece DENTRO da lista de exclusões tem nível "excluida".
   O documento pode ser uma apólice emitida ou CONDIÇÕES GERAIS (texto-padrão
   registrado na SUSEP, sem valores). Nas condições gerais, coberturas
   oferecidas como "Condições Especiais", "Coberturas Adicionais" ou
   "Extensões" (contratação opcional) contam como presentes: classifique a
   redação e diga "opcional" na justificativa. Uma DEFINIÇÃO de glossário
   (marcada "· glossário") não concede nem exclui cobertura por si só.
   Documentos longos chegam como TRECHOS selecionados; use "ausente" só se o
   tema não aparecer em nenhum trecho.
2. Para cada código cite a seção (ex.: "S7") e uma evidência LITERAL curta
   (até 25 palavras) copiada do texto dessa seção. Sem evidência → "ausente".
3. Nunca invente valores, prazos ou seções.
4. Responda SOMENTE com JSON no formato:
{{"clausulas": [{{"codigo": "ESC-01", "nivel": "ampla", "secao": "S3",
"evidencia": "...", "justificativa": "uma frase"}}, ...]}}
com TODOS os códigos pedidos (por padrão, os {len(CLAUSULAS)} da taxonomia), uma
única vez cada."""


def _secoes_para_prompt(secoes: list[Secao], limite_chars: int = 14000) -> str:
    return selecionar_trechos(secoes, limite_chars)


def extrair_cadastro_llm(cliente, texto: str, modelo: str | None = None) -> dict[str, Any]:
    dados = cliente.json(
        sistema=SISTEMA_CADASTRO,
        usuario=("INÍCIO DA APÓLICE:\n\n" + texto[:3500]
                 + ("\n\n[…]\n\nFIM DA APÓLICE (a especificação pode estar aqui):\n\n"
                    + texto[-2000:] if len(texto) > 5500 else texto[3500:])),
        modelo=modelo, temperatura=0.0, max_tokens=1500, tarefa="pf_cadastro",
    )
    out = {k: dados.get(k) for k in CAMPOS_CADASTRAIS}
    for k in ("lmg", "premio", "franquia"):
        v = out.get(k)
        if isinstance(v, str):
            out[k] = valor_reais(v)
        elif isinstance(v, (int, float)):
            out[k] = float(v)
    for k in ("vigencia_inicio", "vigencia_fim", "retroatividade"):
        out[k] = data_br(out.get(k)) if out.get(k) else None
    if isinstance(out.get("retroatividade_ilimitada"), str):
        out["retroatividade_ilimitada"] = out["retroatividade_ilimitada"].lower() == "true"
    return out


def _ler_itens(dados: Any, permitidos: set[str], out: dict[str, ClausulaExtraida]) -> None:
    itens = dados.get("clausulas") if isinstance(dados, dict) else None
    if not isinstance(itens, list):
        raise ValueError("Resposta do modelo sem a lista 'clausulas'.")
    for item in itens:
        if not isinstance(item, dict):
            continue
        codigo = str(item.get("codigo", "")).strip().upper()
        if codigo not in permitidos or codigo in out:
            continue
        nivel = str(item.get("nivel", "")).strip().lower()
        nivel = {"padrão": "padrao", "excluída": "excluida", "exclusao": "excluida"}.get(nivel, nivel)
        if nivel not in NIVEIS_VALIDOS:
            nivel = "ausente"
        out[codigo] = ClausulaExtraida(
            codigo=codigo, nivel=nivel, secao=str(item.get("secao") or "").strip(),
            evidencia=str(item.get("evidencia") or "")[:400],
            justificativa=str(item.get("justificativa") or "")[:400], metodo="llm",
        )


def extrair_clausulas_llm(cliente, secoes: list[Secao],
                          modelo: str | None = None) -> dict[str, ClausulaExtraida]:
    """Classifica as 32 cláusulas com o LLM.

    Documento curto (apólice): uma chamada com o texto inteiro. Documento
    longo (condições gerais reais, 50–100 páginas): uma chamada por lote de
    códigos, cada uma com os trechos selecionados para os seus códigos —
    cabe na cota gratuita e cada cláusula recebe o dobro de texto."""
    out: dict[str, ClausulaExtraida] = {}
    if not documento_longo(secoes):
        dados = cliente.json(
            sistema=SISTEMA_CLAUSULAS,
            usuario="TEXTO DA APÓLICE (seções numeradas):\n\n" + selecionar_trechos(secoes),
            modelo=modelo, temperatura=0.0, max_tokens=6000, tarefa="pf_clausulas",
        )
        _ler_itens(dados, set(CLAUSULAS_POR_CODIGO), out)
    else:
        for lote in LOTES_CODIGOS:
            trechos = selecionar_trechos(secoes, codigos=lote, por_codigo=4, tamanho=600)
            dados = cliente.json(
                sistema=SISTEMA_CLAUSULAS,
                usuario=(f"Classifique SOMENTE estes {len(lote)} códigos: {', '.join(lote)}. "
                         "Responda no mesmo formato JSON, só com eles.\n\n"
                         "TRECHOS SELECIONADOS DO DOCUMENTO:\n\n" + trechos),
                modelo=modelo, temperatura=0.0, max_tokens=4500, tarefa="pf_clausulas",
            )
            _ler_itens(dados, set(lote), out)
    for c in CLAUSULAS:
        out.setdefault(c.codigo, ClausulaExtraida(
            codigo=c.codigo, nivel="ausente", justificativa="Não retornada pelo modelo.",
            metodo="llm"))
    return out


def serializar(extracao: ExtracaoApolice) -> str:
    def conv(v):
        return v.isoformat() if isinstance(v, date) else v
    return json.dumps({
        "cadastro": {k: conv(v) for k, v in extracao.cadastro.items()},
        "clausulas": {k: c.to_dict() for k, c in extracao.clausulas.items()},
        "metodo_cadastro": extracao.metodo_cadastro,
        "metodo_clausulas": extracao.metodo_clausulas,
        "modelo": extracao.modelo, "avisos": extracao.avisos,
    }, ensure_ascii=False)
