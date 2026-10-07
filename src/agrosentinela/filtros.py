"""
Catálogo de filtros — definidos **depois** de olhar para os dados.

Filtro bom não é filtro para toda coluna. É filtro para as perguntas que as
pessoas de fato fazem. Depois de analisar a carteira do Sicor, o histórico do
Proagro e os alertas produzidos pelo motor de regras, os cortes que mudam uma
decisão são estes — e cada um está registrado abaixo com o **porquê**, para
que a escolha possa ser discutida em vez de aceita.

Os quatro que separam um painel útil de um painel bonito:

* **Cobertura de risco** — "sem Proagro e sem seguro" é a única combinação em
  que o produtor perde tudo. É o primeiro corte que qualquer pessoa faz.
* **Fase fenológica** — a mesma seca é irrelevante na maturação e
  potencialmente fatal na floração. Filtrar por evento sem filtrar por fase
  produz uma lista longa e inútil.
* **Janela de ação** — quem opera no campo não pergunta "o que é grave?",
  pergunta "o que preciso resolver até amanhã?".
* **Aderência ao Zarc** — separa o risco que veio do céu do risco que veio da
  decisão de plantio. Muda completamente a conversa: no primeiro caso se
  oferece apoio, no segundo, orientação.

Cada filtro declara ``dataset`` (a que conjunto se aplica), ``coluna``,
``tipo`` de widget, ``porque`` (a justificativa) e uma função de aplicação.
A interface desenha a barra a partir desta lista; o relatório técnico publica
a mesma tabela. Acrescentar um filtro é acrescentar uma entrada aqui.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

import pandas as pd

# ==========================================================================
# Declaração
# ==========================================================================

TIPO_MULTI = "multi"        # multiseleção de categorias
TIPO_FAIXA = "faixa"        # intervalo numérico
TIPO_BOOL = "bool"          # sim / não / indiferente
TIPO_ESCOLHA = "escolha"    # uma opção entre poucas


@dataclass(frozen=True)
class Filtro:
    chave: str
    rotulo: str
    coluna: str
    tipo: str
    porque: str
    dataset: str = "alertas"
    grupo: str = "Território e lavoura"
    ordem: int = 50
    essencial: bool = False
    rotulos: dict[Any, str] = field(default_factory=dict)
    passo: float = 1.0
    sufixo: str = ""
    ajuda: str = ""

    def to_row(self) -> dict[str, Any]:
        return {
            "filtro": self.rotulo,
            "grupo": self.grupo,
            "conjunto": self.dataset,
            "coluna": self.coluna,
            "tipo": self.tipo,
            "essencial": "sim" if self.essencial else "—",
            "por que existe": self.porque,
        }


FILTROS: tuple[Filtro, ...] = (
    # ------------------------------------------------- risco e urgência
    Filtro(
        "severidade", "Severidade", "severidade", TIPO_MULTI,
        porque="Corte mais direto entre 'preciso agir' e 'quero acompanhar'. "
               "Em carteira grande, só o crítico cabe num dia de trabalho.",
        grupo="Risco e urgência", ordem=1, essencial=True,
        rotulos={"critico": "🔴 Crítico", "alerta": "🔶 Alerta",
                 "atencao": "⚠️ Atenção", "informativo": "ℹ️ Informativo"},
    ),
    Filtro(
        "evento", "Evento climático", "evento", TIPO_MULTI,
        porque="Cada evento tem manejo, prazo e cobertura diferentes. Misturar "
               "geada e granizo na mesma lista produz uma ação média que não "
               "serve para nenhum dos dois.",
        grupo="Risco e urgência", ordem=2, essencial=True,
    ),
    Filtro(
        "janela_acao_h", "Janela de ação (horas)", "janela_acao_h", TIPO_FAIXA,
        porque="A pergunta de quem está em campo não é 'o que é grave?', é "
               "'o que preciso resolver até amanhã?'. Sem este filtro, o "
               "urgente se perde no meio do importante.",
        grupo="Risco e urgência", ordem=3, essencial=True, sufixo=" h",
    ),
    Filtro(
        "score", "Escore de risco", "score", TIPO_FAIXA,
        porque="Permite calibrar o volume de trabalho: quem tem equipe para "
               "50 visitas corta em um escore; quem tem para 5, em outro.",
        grupo="Risco e urgência", ordem=4, sufixo=" pts",
    ),

    # --------------------------------------------------------- cobertura
    Filtro(
        "tem_cobertura", "Possui cobertura de risco", "tem_cobertura", TIPO_BOOL,
        porque="'Sem Proagro e sem seguro' é a única combinação em que o "
               "produtor perde tudo — e é onde a comunicação preventiva tem o "
               "maior retorno. Primeiro corte que praticamente todo usuário faz.",
        grupo="Cobertura e proteção", ordem=10, essencial=True,
    ),
    Filtro(
        "coberto_proagro_evento", "Evento coberto pelo Proagro",
        "coberto_proagro_evento", TIPO_BOOL,
        porque="Ter Proagro não basta: o Proagro não cobre todo evento. "
               "Este filtro isola o caso perigoso de quem **acredita** estar "
               "coberto e não está.",
        grupo="Cobertura e proteção", ordem=11, essencial=True,
    ),
    Filtro(
        "protecao_municipio", "Proteção do município", "protecao_municipio",
        TIPO_MULTI,
        porque="Cruza a cobertura do Sicor com a penetração do seguro privado "
               "(PSR/MAPA). Distingue município **descoberto** de município "
               "**coberto por outro instrumento** — distinção que o Sicor "
               "sozinho não permite e que muda a recomendação comercial.",
        grupo="Cobertura e proteção", ordem=12,
    ),
    Filtro(
        "tipo_seguro", "Tipo de cobertura declarada", "tipo_seguro", TIPO_MULTI,
        porque="Proagro, Proagro Mais e seguro privado têm regras e prazos "
               "distintos de comunicação de sinistro.",
        grupo="Cobertura e proteção", ordem=13,
    ),

    # ------------------------------------------------ território e lavoura
    Filtro(
        "uf", "UF", "uf", TIPO_MULTI,
        porque="Recorte natural de quem opera por regional, superintendência "
               "ou unidade da federação.",
        grupo="Território e lavoura", ordem=20, essencial=True,
    ),
    Filtro(
        "regiao", "Região", "regiao", TIPO_MULTI,
        porque="Agrega para leitura macro em política pública e resseguro.",
        grupo="Território e lavoura", ordem=21,
    ),
    Filtro(
        "municipio", "Município", "municipio", TIPO_MULTI,
        porque="Unidade de decisão do extensionista, do assessor e do "
               "gerente de agência.",
        grupo="Território e lavoura", ordem=22,
    ),
    Filtro(
        "cultura", "Cultura", "cultura", TIPO_MULTI,
        porque="Define calendário, sensibilidade e interlocutor técnico.",
        grupo="Território e lavoura", ordem=23, essencial=True,
    ),
    Filtro(
        "fase", "Fase da lavoura", "fase", TIPO_MULTI,
        porque="A mesma seca é irrelevante na maturação e potencialmente "
               "fatal na floração. Filtrar evento sem filtrar fase devolve "
               "uma lista longa e inútil.",
        grupo="Território e lavoura", ordem=24, essencial=True,
    ),
    Filtro(
        "irrigada", "Lavoura irrigada", "irrigada", TIPO_BOOL,
        porque="Sequeiro e irrigado respondem de forma oposta à seca: o "
               "primeiro perde lavoura, o segundo perde outorga e custo de "
               "energia.",
        grupo="Território e lavoura", ordem=25,
    ),
    Filtro(
        "dentro_janela_zarc", "Plantio dentro da janela Zarc",
        "dentro_janela_zarc", TIPO_BOOL,
        porque="Separa o risco que veio do céu do risco que veio da decisão "
               "de plantio. No primeiro caso se oferece apoio; no segundo, "
               "orientação — e o enquadramento no Proagro pode estar em jogo.",
        grupo="Território e lavoura", ordem=26, essencial=True,
    ),

    # ---------------------------------------------- crédito e exposição
    Filtro(
        "valor_credito", "Valor financiado (R$)", "valor_credito", TIPO_FAIXA,
        porque="Prioriza por exposição quando a equipe é pequena. É o corte "
               "que a área de crédito faz primeiro.",
        grupo="Crédito e exposição", ordem=30, passo=10_000.0,
    ),
    Filtro(
        "area_ha", "Área financiada (ha)", "area_ha", TIPO_FAIXA,
        porque="Proxy de porte quando o valor não está disponível, e a "
               "unidade em que o técnico agronômico pensa.",
        grupo="Crédito e exposição", ordem=31, sufixo=" ha",
    ),
    Filtro(
        "programa", "Programa de crédito", "programa", TIPO_MULTI,
        porque="Pronaf, Pronamp e demais linhas definem porte, taxa e — "
               "principalmente — o tom e o canal da comunicação.",
        grupo="Crédito e exposição", ordem=32,
    ),
    Filtro(
        "instituicao", "Instituição financeira", "instituicao", TIPO_MULTI,
        porque="Cada banco só pode agir sobre a própria carteira. Sem este "
               "filtro o painel não é utilizável por uma instituição.",
        grupo="Crédito e exposição", ordem=33,
    ),
    Filtro(
        "dias_para_vencimento", "Dias até o vencimento", "dias_para_vencimento",
        TIPO_FAIXA,
        porque="Evento climático perto do vencimento é o cenário que vira "
               "inadimplência. Cruzar os dois antecipa a renegociação.",
        grupo="Crédito e exposição", ordem=34,
    ),
    Filtro(
        "dias_para_colheita", "Dias até a colheita", "dias_para_colheita",
        TIPO_FAIXA,
        porque="Define se ainda há tempo de manejo ou se resta apenas "
               "documentar a perda.",
        grupo="Crédito e exposição", ordem=35,
    ),
    Filtro(
        "perda_estimada_reais", "Perda estimada (R$)", "perda_estimada_reais",
        TIPO_FAIXA,
        porque="Traduz risco em dinheiro usando rendimento do IBGE e preço "
               "da CONAB. É a unidade em que crédito, atuária e política "
               "pública conversam entre si.",
        grupo="Crédito e exposição", ordem=36, passo=10_000.0,
    ),

    # -------------------------------------------------------- público-alvo
    Filtro(
        "persona", "Perfil do destinatário", "persona", TIPO_MULTI,
        porque="Cada persona recebe conteúdo, canal e tom distintos. O "
               "filtro permite conferir o que **aquele público** receberia.",
        grupo="Público-alvo", ordem=40, essencial=True,
    ),
    Filtro(
        "setor", "Setor de atuação", "setor", TIPO_MULTI,
        porque="Agrupa as 16 personas em cinco setores (produção, seguros, "
               "crédito e política, assistência técnica, cadeia produtiva) "
               "para quem quer a visão de um mercado inteiro.",
        grupo="Público-alvo", ordem=41,
    ),
    Filtro(
        "anomalia_chuva", "Chuva x média histórica", "anomalia_chuva", TIPO_MULTI,
        porque="Contextualiza o número absoluto: 80 mm é rotina no litoral "
               "norte e excepcional no oeste baiano. Sem a anomalia, o alerta "
               "vira alarme falso e perde credibilidade.",
        grupo="Público-alvo", ordem=42,
    ),
)

FILTROS_POR_CHAVE: dict[str, Filtro] = {f.chave: f for f in FILTROS}

GRUPOS: tuple[str, ...] = (
    "Risco e urgência",
    "Cobertura e proteção",
    "Território e lavoura",
    "Crédito e exposição",
    "Público-alvo",
)


def por_grupo(grupo: str) -> list[Filtro]:
    return sorted([f for f in FILTROS if f.grupo == grupo], key=lambda f: f.ordem)


def essenciais() -> list[Filtro]:
    """Os que aparecem na barra compacta, inclusive no celular."""
    return sorted([f for f in FILTROS if f.essencial], key=lambda f: f.ordem)


def aplicaveis(df: pd.DataFrame) -> list[Filtro]:
    """Filtros cuja coluna existe e tem mais de um valor no conjunto atual."""
    if df is None or df.empty:
        return []
    saida = []
    for f in FILTROS:
        if f.coluna not in df.columns:
            continue
        serie = df[f.coluna].dropna()
        if serie.empty or serie.nunique() <= 1:
            continue
        saida.append(f)
    return sorted(saida, key=lambda f: f.ordem)


def tabela() -> list[dict[str, Any]]:
    return [f.to_row() for f in sorted(FILTROS, key=lambda f: (f.grupo, f.ordem))]


# ==========================================================================
# Aplicação
# ==========================================================================

def opcoes(df: pd.DataFrame, filtro: Filtro) -> list[Any]:
    """Valores distintos disponíveis para um filtro categórico."""
    if df is None or df.empty or filtro.coluna not in df.columns:
        return []
    serie = df[filtro.coluna].dropna()
    if serie.empty:
        return []
    if filtro.chave == "severidade":
        ordem = ["critico", "alerta", "atencao", "informativo"]
        presentes = set(serie.astype(str))
        return [s for s in ordem if s in presentes]
    return sorted(serie.astype(str).unique().tolist())


def limites(df: pd.DataFrame, filtro: Filtro) -> tuple[float, float]:
    """Mínimo e máximo de um filtro numérico, já arredondados."""
    if df is None or df.empty or filtro.coluna not in df.columns:
        return 0.0, 0.0
    serie = pd.to_numeric(df[filtro.coluna], errors="coerce").dropna()
    if serie.empty:
        return 0.0, 0.0
    return float(serie.min()), float(serie.max())


def aplicar(df: pd.DataFrame, selecao: dict[str, Any]) -> pd.DataFrame:
    """
    Aplica a seleção ao conjunto.

    Convenções, pensadas para que "não escolhi nada" nunca esconda dados:

    * lista vazia ou ausente = **sem filtro** (mostra tudo);
    * ``None`` em filtro booleano = indiferente;
    * faixa numérica ``(min, max)`` é inclusiva nas duas pontas;
    * valores nulos da coluna são **mantidos** em filtros de faixa, porque
      "não sei o valor" não é o mesmo que "está fora do intervalo" — omitir
      silenciosamente o desconhecido é como se perde um alerta.
    """
    if df is None or df.empty or not selecao:
        return df

    out = df
    for chave, valor in selecao.items():
        filtro = FILTROS_POR_CHAVE.get(chave)
        if filtro is None or filtro.coluna not in out.columns:
            continue
        coluna = out[filtro.coluna]

        if filtro.tipo in (TIPO_MULTI, TIPO_ESCOLHA):
            if not valor:
                continue
            escolhidos = {str(v) for v in (valor if isinstance(valor, (list, tuple, set)) else [valor])}
            out = out[coluna.astype(str).isin(escolhidos)]

        elif filtro.tipo == TIPO_BOOL:
            if valor is None:
                continue
            alvo = bool(valor)
            normalizada = coluna.map(_para_bool)
            out = out[normalizada == alvo]

        elif filtro.tipo == TIPO_FAIXA:
            if not valor or not isinstance(valor, (list, tuple)) or len(valor) != 2:
                continue
            minimo, maximo = float(valor[0]), float(valor[1])
            numerica = pd.to_numeric(coluna, errors="coerce")
            dentro = numerica.between(minimo, maximo) | numerica.isna()
            out = out[dentro]

    return out


def _para_bool(valor: Any) -> bool | None:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    if isinstance(valor, bool):
        return valor
    texto = str(valor).strip().lower()
    if texto in {"true", "sim", "1", "1.0", "verdadeiro"}:
        return True
    if texto in {"false", "nao", "não", "0", "0.0", "falso"}:
        return False
    if texto in {"", "nan", "none", "<na>"}:
        return None
    return None


# ==========================================================================
# Resumo legível
# ==========================================================================

def resumo(selecao: dict[str, Any]) -> list[str]:
    """
    Frases curtas descrevendo os filtros ativos.

    Existe para uma razão específica de usabilidade: no celular a barra de
    filtros fica recolhida, e um painel filtrado sem aviso visível é a forma
    mais rápida de alguém concluir que "não há alertas" quando na verdade há.
    """
    partes: list[str] = []
    for chave, valor in (selecao or {}).items():
        filtro = FILTROS_POR_CHAVE.get(chave)
        if filtro is None:
            continue
        if filtro.tipo in (TIPO_MULTI, TIPO_ESCOLHA):
            if not valor:
                continue
            itens = list(valor) if isinstance(valor, (list, tuple, set)) else [valor]
            rotulados = [str(filtro.rotulos.get(i, i)) for i in itens]
            texto = ", ".join(rotulados[:3])
            if len(rotulados) > 3:
                texto += f" +{len(rotulados) - 3}"
            partes.append(f"{filtro.rotulo}: {texto}")
        elif filtro.tipo == TIPO_BOOL:
            if valor is None:
                continue
            partes.append(f"{filtro.rotulo}: {'sim' if valor else 'não'}")
        elif filtro.tipo == TIPO_FAIXA:
            if not valor or len(valor) != 2:
                continue
            partes.append(
                f"{filtro.rotulo}: {_numero(valor[0])}–{_numero(valor[1])}{filtro.sufixo}"
            )
    return partes


def _numero(v: Any) -> str:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return str(v)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} mi".replace(".", ",")
    if n >= 1_000:
        return f"{n / 1_000:.0f} mil"
    return f"{n:.0f}"


def ativos(selecao: dict[str, Any]) -> int:
    return len(resumo(selecao))


def limpar() -> dict[str, Any]:
    return {}
