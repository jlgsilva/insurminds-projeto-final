"""
Catálogo de domínio: eventos climáticos, culturas e fenologia.

O catálogo conecta três universos:

1. **Meteorologia** (Open-Meteo / INMET) — variáveis observadas e previstas.
2. **Risco agronômico** — fase fenológica da cultura financiada.
3. **Proagro/Sicor** — os eventos cobertos, conforme a tabela de domínio
   ``EventoProagro.csv`` do Banco Central.

A ligação com o Proagro é feita por **normalização textual** do nome do
evento (e não por código fixo), porque os códigos da tabela de domínio
podem ser revistos pelo BCB. O ETL resolve o ``CD_EVENTO`` real a partir
do arquivo oficial e grava o mapeamento em
``data/curated/mapa_eventos_proagro.parquet``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


def normalizar(texto: str | None) -> str:
    """Minúsculas, sem acento, sem pontuação — para casar rótulos do BCB."""
    if not texto:
        return ""
    s = unicodedata.normalize("NFKD", str(texto))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# --------------------------------------------------------------------------
# Eventos climáticos monitorados
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class EventoClimatico:
    """Tipo de evento climático monitorado pelo AgroSentinela."""

    codigo: str
    nome: str
    icone: str
    descricao: str
    # Termos que identificam o evento equivalente na tabela EventoProagro.csv
    sinonimos_proagro: tuple[str, ...]
    # Indicadores meteorológicos que sustentam a detecção
    indicadores: tuple[str, ...]
    # Culturas mais sensíveis (apenas para priorização visual)
    culturas_criticas: tuple[str, ...] = field(default_factory=tuple)
    cobertura_proagro: bool = True
    cor: str = "#64748b"


EVENTOS: tuple[EventoClimatico, ...] = (
    EventoClimatico(
        codigo="seca",
        nome="Seca / veranico",
        icone="🌵",
        descricao=(
            "Déficit hídrico prolongado: sequência de dias sem chuva "
            "significativa combinada a balanço hídrico negativo."
        ),
        sinonimos_proagro=("seca", "estiagem", "deficiencia hidrica", "veranico"),
        indicadores=("dias_secos_consecutivos", "balanco_hidrico_14d", "prec_14d"),
        culturas_criticas=("SOJA", "MILHO", "FEIJAO", "ARROZ", "PASTAGEM"),
        cor="#d97706",
    ),
    EventoClimatico(
        codigo="chuva_excessiva",
        nome="Chuva excessiva",
        icone="🌧️",
        descricao=(
            "Precipitação acumulada muito acima do normal, com risco de "
            "encharcamento, perda de qualidade e impedimento de colheita."
        ),
        sinonimos_proagro=("chuva excessiva", "excesso de chuva", "excesso hidrico"),
        indicadores=("prec_7d", "prec_max_24h", "dias_com_chuva_7d"),
        culturas_criticas=("SOJA", "TRIGO", "FEIJAO", "CAFE", "ALGODAO"),
        cor="#2563eb",
    ),
    EventoClimatico(
        codigo="chuva_intensa",
        nome="Chuva intensa / tromba d'água",
        icone="⛈️",
        descricao=(
            "Evento convectivo de curta duração e alta intensidade, com risco "
            "de erosão, alagamento e perda localizada."
        ),
        sinonimos_proagro=("tromba d agua", "chuva intensa", "enchente", "inundacao"),
        indicadores=("prec_max_24h", "cape_max", "rajada_max"),
        culturas_criticas=("HORTALICAS", "FEIJAO", "MILHO", "SOJA"),
        cor="#1d4ed8",
    ),
    EventoClimatico(
        codigo="granizo",
        nome="Granizo",
        icone="🧊",
        descricao=(
            "Probabilidade elevada de queda de granizo, estimada por proxy "
            "convectivo (CAPE alto + rajada forte + precipitação convectiva)."
        ),
        sinonimos_proagro=("granizo", "chuva de pedra"),
        indicadores=("cape_max", "rajada_max", "prec_max_24h", "prob_granizo"),
        culturas_criticas=("UVA", "MACA", "CAFE", "LARANJA", "SOJA", "MILHO"),
        cor="#0ea5e9",
    ),
    EventoClimatico(
        codigo="geada",
        nome="Geada",
        icone="❄️",
        descricao=(
            "Temperatura mínima em nível de abrigo próxima ou abaixo do limiar "
            "de formação de geada (relva chega a ser ~3 °C mais fria)."
        ),
        sinonimos_proagro=("geada",),
        indicadores=("tmin_min", "dias_tmin_le_3", "umidade_min"),
        culturas_criticas=("CAFE", "TRIGO", "MILHO", "CANA", "UVA"),
        cor="#7dd3fc",
    ),
    EventoClimatico(
        codigo="onda_calor",
        nome="Onda de calor / estresse térmico",
        icone="🔥",
        descricao=(
            "Sequência de dias com temperatura máxima elevada, comprometendo "
            "floração, enchimento de grãos e bem-estar animal."
        ),
        sinonimos_proagro=(
            "variacao excessiva de temperatura",
            "temperatura excessiva",
            "calor excessivo",
            "ventos quentes",
        ),
        indicadores=("dias_tmax_ge_35", "tmax_max", "et0_7d"),
        culturas_criticas=("MILHO", "SOJA", "FEIJAO", "CAFE", "BOVINOS"),
        cor="#dc2626",
    ),
    EventoClimatico(
        codigo="vendaval",
        nome="Vendaval",
        icone="🌪️",
        descricao=(
            "Rajadas de vento capazes de causar acamamento, quebra de plantas "
            "e danos a estruturas."
        ),
        sinonimos_proagro=("vendaval", "ventos fortes", "ciclone", "ventania"),
        indicadores=("rajada_max", "vento_medio_max"),
        culturas_criticas=("MILHO", "BANANA", "CANA", "CAFE", "LARANJA"),
        cor="#4b5563",
    ),
    EventoClimatico(
        codigo="umidade_colheita",
        nome="Janela de colheita comprometida",
        icone="🚜",
        descricao=(
            "Combinação de chuva recorrente e umidade alta durante a janela de "
            "colheita declarada na operação — risco de perda de qualidade."
        ),
        sinonimos_proagro=("chuva excessiva", "excesso hidrico"),
        indicadores=("dias_com_chuva_7d", "umidade_media", "prec_7d"),
        culturas_criticas=("SOJA", "TRIGO", "MILHO", "CAFE", "FEIJAO"),
        cobertura_proagro=False,
        cor="#a16207",
    ),
)

EVENTOS_POR_CODIGO: dict[str, EventoClimatico] = {e.codigo: e for e in EVENTOS}


def mapear_evento_proagro(nome_evento_bcb: str) -> str | None:
    """
    Dado o rótulo de um evento na tabela ``EventoProagro.csv`` do BCB,
    devolve o código interno do AgroSentinela correspondente (ou ``None``).
    """
    alvo = normalizar(nome_evento_bcb)
    if not alvo:
        return None
    melhor: tuple[int, str] | None = None
    for evento in EVENTOS:
        for sin in evento.sinonimos_proagro:
            s = normalizar(sin)
            if s and s in alvo:
                score = len(s)
                if melhor is None or score > melhor[0]:
                    melhor = (score, evento.codigo)
    return melhor[1] if melhor else None


# --------------------------------------------------------------------------
# Culturas e fenologia
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class FaseFenologica:
    """Fase do ciclo da cultura com sua sensibilidade a cada evento."""

    codigo: str
    nome: str
    # Fração do ciclo (0.0 = plantio, 1.0 = colheita)
    inicio: float
    fim: float
    # Multiplicador de severidade por evento (1.0 = neutro; >1 agrava)
    sensibilidade: dict[str, float] = field(default_factory=dict)
    recomendacao: str = ""


@dataclass(frozen=True)
class Cultura:
    """Cultura agrícola com ciclo típico e fases fenológicas."""

    codigo: str
    nome: str
    grupo: str
    ciclo_dias: int
    unidade_produtiva: str
    fases: tuple[FaseFenologica, ...]
    icone: str = "🌱"

    def fase_em(self, progresso: float) -> FaseFenologica:
        """Fase correspondente a um progresso do ciclo entre 0 e 1."""
        p = min(max(progresso, 0.0), 1.0)
        for fase in self.fases:
            if fase.inicio <= p <= fase.fim:
                return fase
        return self.fases[-1]


def _fases_graos(cultura: str) -> tuple[FaseFenologica, ...]:
    """Fases genéricas de culturas anuais de grãos, com ajustes por cultura."""
    geada_flor = 2.2 if cultura in {"TRIGO", "MILHO"} else 1.6
    return (
        FaseFenologica(
            codigo="semeadura",
            nome="Semeadura / emergência",
            inicio=0.0,
            fim=0.18,
            sensibilidade={
                "seca": 1.6,
                "chuva_excessiva": 1.5,
                "chuva_intensa": 1.7,
                "granizo": 0.7,
                "geada": 1.2,
                "onda_calor": 1.2,
                "vendaval": 0.6,
            },
            recomendacao=(
                "Avaliar replantio, ajuste de densidade e drenagem de sulcos; "
                "registrar data efetiva de semeadura para fins de Proagro."
            ),
        ),
        FaseFenologica(
            codigo="vegetativo",
            nome="Desenvolvimento vegetativo",
            inicio=0.18,
            fim=0.45,
            sensibilidade={
                "seca": 1.3,
                "chuva_excessiva": 1.2,
                "chuva_intensa": 1.2,
                "granizo": 1.3,
                "geada": 1.4,
                "onda_calor": 1.1,
                "vendaval": 1.0,
            },
            recomendacao=(
                "Monitorar estande e nutrição; antecipar tratos culturais na "
                "janela seca disponível."
            ),
        ),
        FaseFenologica(
            codigo="floracao",
            nome="Floração / polinização",
            inicio=0.45,
            fim=0.65,
            sensibilidade={
                "seca": 2.0,
                "chuva_excessiva": 1.5,
                "chuva_intensa": 1.5,
                "granizo": 1.8,
                "geada": geada_flor,
                "onda_calor": 2.0,
                "vendaval": 1.3,
            },
            recomendacao=(
                "Fase de maior sensibilidade do ciclo: priorizar as medidas de "
                "mitigação disponíveis e documentar o evento com fotos e data, "
                "caso venha a ser necessário abrir pedido de cobertura."
            ),
        ),
        FaseFenologica(
            codigo="enchimento",
            nome="Enchimento de grãos",
            inicio=0.65,
            fim=0.85,
            sensibilidade={
                "seca": 1.8,
                "chuva_excessiva": 1.3,
                "chuva_intensa": 1.4,
                "granizo": 1.9,
                "geada": 1.9,
                "onda_calor": 1.7,
                "vendaval": 1.4,
            },
            recomendacao=(
                "Perdas nesta fase são praticamente irrecuperáveis: registrar "
                "ocorrência e avaliar comunicação preventiva ao agente do Proagro."
            ),
        ),
        FaseFenologica(
            codigo="maturacao",
            nome="Maturação / pré-colheita",
            inicio=0.85,
            fim=0.96,
            sensibilidade={
                "seca": 0.8,
                "chuva_excessiva": 1.9,
                "chuva_intensa": 1.8,
                "granizo": 2.0,
                "geada": 1.2,
                "onda_calor": 1.0,
                "vendaval": 1.8,
                "umidade_colheita": 2.0,
            },
            recomendacao=(
                "Planejar a colheita para a melhor janela disponível e preparar "
                "secagem e armazenagem, evitando perda de qualidade."
            ),
        ),
        FaseFenologica(
            codigo="colheita",
            nome="Colheita",
            inicio=0.96,
            fim=1.0,
            sensibilidade={
                "seca": 0.5,
                "chuva_excessiva": 2.0,
                "chuva_intensa": 1.9,
                "granizo": 1.6,
                "geada": 0.8,
                "onda_calor": 0.9,
                "vendaval": 1.5,
                "umidade_colheita": 2.2,
            },
            recomendacao=(
                "Priorizar talhões mais maduros, monitorar umidade de grão e "
                "evitar tráfego em solo encharcado."
            ),
        ),
    )


def _fases_perene(cultura: str) -> tuple[FaseFenologica, ...]:
    return (
        FaseFenologica(
            codigo="repouso",
            nome="Repouso / pós-colheita",
            inicio=0.0,
            fim=0.25,
            sensibilidade={"seca": 1.1, "geada": 1.3, "granizo": 0.8, "vendaval": 1.0},
            recomendacao="Janela de tratos culturais e adubação de reposição.",
        ),
        FaseFenologica(
            codigo="brotacao",
            nome="Brotação / floração",
            inicio=0.25,
            fim=0.5,
            sensibilidade={
                "seca": 1.7,
                "geada": 2.3 if cultura in {"CAFE", "UVA", "MACA"} else 1.6,
                "granizo": 2.0,
                "chuva_excessiva": 1.5,
                "onda_calor": 1.6,
                "vendaval": 1.4,
            },
            recomendacao=(
                "Fase que define a safra seguinte: acionar as medidas de proteção "
                "disponíveis para o evento em curso e registrar a ocorrência com "
                "data, hora e fotos por talhão."
            ),
        ),
        FaseFenologica(
            codigo="frutificacao",
            nome="Frutificação / granação",
            inicio=0.5,
            fim=0.8,
            sensibilidade={
                "seca": 1.8,
                "granizo": 2.2,
                "chuva_excessiva": 1.4,
                "onda_calor": 1.6,
                "vendaval": 1.7,
                "geada": 1.5,
            },
            recomendacao="Monitorar carga pendente e sustentação de ramos.",
        ),
        FaseFenologica(
            codigo="colheita",
            nome="Colheita",
            inicio=0.8,
            fim=1.0,
            sensibilidade={
                "chuva_excessiva": 1.9,
                "granizo": 1.8,
                "vendaval": 1.6,
                "umidade_colheita": 2.1,
                "seca": 0.7,
            },
            recomendacao="Organizar logística de colheita e secagem.",
        ),
    )


def _fases_pecuaria() -> tuple[FaseFenologica, ...]:
    """
    Pecuária e pastagem não têm fenologia de lavoura: o que importa é o
    ciclo forrageiro e o conforto térmico do rebanho. Modelamos quatro
    estágios de manejo ao longo do ano-pecuário.
    """
    return (
        FaseFenologica(
            codigo="rebrota",
            nome="Rebrota da pastagem",
            inicio=0.0,
            fim=0.3,
            sensibilidade={"seca": 1.8, "geada": 1.6, "chuva_excessiva": 1.1,
                           "onda_calor": 1.3, "vendaval": 0.7, "granizo": 0.6},
            recomendacao=(
                "Ajustar taxa de lotação e diferir piquetes; conferir "
                "disponibilidade de água e reservas de volumoso."
            ),
        ),
        FaseFenologica(
            codigo="pleno_pastejo",
            nome="Pleno pastejo",
            inicio=0.3,
            fim=0.65,
            sensibilidade={"seca": 1.5, "geada": 1.3, "chuva_excessiva": 1.2,
                           "onda_calor": 1.6, "vendaval": 0.8, "granizo": 0.6},
            recomendacao=(
                "Monitorar ganho de peso e sombreamento; evitar manejo de "
                "animais nas horas mais quentes."
            ),
        ),
        FaseFenologica(
            codigo="entressafra_forrageira",
            nome="Entressafra forrageira",
            inicio=0.65,
            fim=0.9,
            sensibilidade={"seca": 2.0, "geada": 1.8, "onda_calor": 1.5,
                           "chuva_excessiva": 1.0, "vendaval": 0.8, "granizo": 0.6},
            recomendacao=(
                "Planejar suplementação volumosa e concentrada; antecipar "
                "compra de insumos antes da elevação de preço."
            ),
        ),
        FaseFenologica(
            codigo="manejo_sanitario",
            nome="Manejo sanitário e reprodutivo",
            inicio=0.9,
            fim=1.0,
            sensibilidade={"seca": 1.4, "geada": 1.2, "onda_calor": 1.7,
                           "chuva_excessiva": 1.3, "vendaval": 0.9, "granizo": 0.6},
            recomendacao=(
                "Reprogramar manejos que exijam contenção dos animais para "
                "janelas de conforto térmico."
            ),
        ),
    )


CULTURAS: tuple[Cultura, ...] = (
    Cultura("SOJA", "Soja", "Grãos", 125, "sacas/ha", _fases_graos("SOJA"), "🫘"),
    Cultura("MILHO", "Milho", "Grãos", 140, "sacas/ha", _fases_graos("MILHO"), "🌽"),
    Cultura("MILHO_2SAFRA", "Milho 2ª safra", "Grãos", 120, "sacas/ha", _fases_graos("MILHO"), "🌽"),
    Cultura("ALGODAO", "Algodão", "Fibras", 180, "@/ha", _fases_graos("ALGODAO"), "🧵"),
    Cultura("ARROZ", "Arroz", "Grãos", 130, "sacas/ha", _fases_graos("ARROZ"), "🍚"),
    Cultura("FEIJAO", "Feijão", "Grãos", 90, "sacas/ha", _fases_graos("FEIJAO"), "🫘"),
    Cultura("TRIGO", "Trigo", "Grãos", 120, "sacas/ha", _fases_graos("TRIGO"), "🌾"),
    Cultura("CAFE", "Café", "Perenes", 365, "sacas/ha", _fases_perene("CAFE"), "☕"),
    Cultura("CANA", "Cana-de-açúcar", "Perenes", 365, "t/ha", _fases_perene("CANA"), "🎋"),
    Cultura("LARANJA", "Laranja / citros", "Perenes", 365, "caixas/ha", _fases_perene("LARANJA"), "🍊"),
    Cultura("UVA", "Uva", "Perenes", 240, "t/ha", _fases_perene("UVA"), "🍇"),
    Cultura("MACA", "Maçã", "Perenes", 240, "t/ha", _fases_perene("MACA"), "🍎"),
    Cultura("MANDIOCA", "Mandioca", "Raízes", 300, "t/ha", _fases_graos("MANDIOCA"), "🥔"),
    Cultura("PASTAGEM", "Pastagem / pecuária", "Pecuária", 365, "UA/ha", _fases_pecuaria(), "🐄"),
    Cultura("BOVINOS", "Bovinocultura", "Pecuária", 365, "cabeças", _fases_pecuaria(), "🐄"),
    Cultura("HORTALICAS", "Hortaliças", "Olerícolas", 80, "t/ha", _fases_graos("HORTALICAS"), "🥬"),
    Cultura("OUTRAS", "Outras culturas", "Diversos", 150, "un/ha", _fases_graos("OUTRAS"), "🌱"),
)

CULTURAS_POR_CODIGO: dict[str, Cultura] = {c.codigo: c for c in CULTURAS}


# Termos do campo PRODUTO (tabela Produto.csv do Sicor) -> cultura interna.
# A ordem importa: o primeiro casamento vence.
_MAPA_PRODUTO: tuple[tuple[str, str], ...] = (
    ("soja", "SOJA"),
    ("milho 2", "MILHO_2SAFRA"),
    ("milho safrinha", "MILHO_2SAFRA"),
    ("milho", "MILHO"),
    ("algodao", "ALGODAO"),
    ("arroz", "ARROZ"),
    ("feijao", "FEIJAO"),
    ("trigo", "TRIGO"),
    ("cafe", "CAFE"),
    ("cana", "CANA"),
    ("laranja", "LARANJA"),
    ("citr", "LARANJA"),
    ("tangerina", "LARANJA"),
    ("limao", "LARANJA"),
    ("uva", "UVA"),
    ("maca", "MACA"),
    ("mandioca", "MANDIOCA"),
    ("pastagem", "PASTAGEM"),
    ("forrageira", "PASTAGEM"),
    ("bovino", "BOVINOS"),
    ("gado", "BOVINOS"),
    ("leite", "BOVINOS"),
    ("hortalic", "HORTALICAS"),
    ("olericultura", "HORTALICAS"),
    ("tomate", "HORTALICAS"),
    ("batata", "HORTALICAS"),
    ("cebola", "HORTALICAS"),
)


def mapear_produto_para_cultura(nome_produto: str | None) -> str:
    """Converte o rótulo de PRODUTO do Sicor na cultura interna."""
    alvo = normalizar(nome_produto)
    if not alvo:
        return "OUTRAS"
    for termo, cultura in _MAPA_PRODUTO:
        if termo in alvo:
            return cultura
    return "OUTRAS"


def get_cultura(codigo: str | None) -> Cultura:
    return CULTURAS_POR_CODIGO.get((codigo or "").upper(), CULTURAS_POR_CODIGO["OUTRAS"])
