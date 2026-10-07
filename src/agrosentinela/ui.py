"""
Componentes e estado compartilhado da interface Streamlit.

Centraliza aqui tudo o que as páginas reutilizam: carregamento em cache,
execução do pipeline, barra lateral de controles, cartões de métrica e
renderização de mensagens. As páginas ficam curtas e legíveis.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from functools import lru_cache
from typing import Any, Sequence

import pandas as pd
import streamlit as st

# Permite executar o app sem instalar o pacote (streamlit run app.py)
_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from agrosentinela import __app_name__, __tagline__, __version__  # noqa: E402
from agrosentinela.config import MODELOS_GROQ, get_settings, reset_settings_cache  # noqa: E402
from agrosentinela.data.loader import BaseDados, carregar_base  # noqa: E402
from agrosentinela.llm.groq_client import GroqClient  # noqa: E402
from agrosentinela.orchestrator import Orquestrador, ResultadoPipeline  # noqa: E402
from agrosentinela.outbox.store import Outbox  # noqa: E402
from agrosentinela.rules.catalogo import EVENTOS  # noqa: E402
from agrosentinela.rules.engine import MotorRegras  # noqa: E402
from agrosentinela.utils.formato import hectares, inteiro, pct, reais_compacto  # noqa: E402
from agrosentinela.utils.logging_setup import configurar_logging  # noqa: E402
from agrosentinela import filtros as flt  # noqa: E402
from agrosentinela.viz.theme import (  # noqa: E402
    ALTURA_MAPA_COMPACTA,
    ALTURA_MAPA_PADRAO,
    CSS,
    CORES_CANAL,
    ICONES_SEVERIDADE,
    faixa,
)

CENARIOS = {
    "(previsão real)": None,
    "🌵 Seca / veranico": "seca",
    "🌧️ Chuva excessiva": "chuva_excessiva",
    "⛈️ Chuva intensa": "chuva_intensa",
    "🧊 Granizo": "granizo",
    "❄️ Geada": "geada",
    "🔥 Onda de calor": "onda_calor",
    "🌪️ Vendaval": "vendaval",
}


# ==========================================================================
# Configuração de página
# ==========================================================================

def configurar_pagina(titulo: str, icone: str = "🌾", largura: str = "wide") -> None:
    st.set_page_config(
        page_title=f"{titulo} · {__app_name__}",
        page_icon=icone,
        layout=largura,
        initial_sidebar_state="expanded",
    )
    st.markdown(CSS, unsafe_allow_html=True)
    configurar_logging(get_settings().log_level)


def cabecalho(titulo: str, subtitulo: str = "", icone: str = "") -> None:
    st.markdown(f"## {icone} {titulo}".strip())
    if subtitulo:
        st.caption(subtitulo)


# ==========================================================================
# Carregamento e execução (com cache)
# ==========================================================================

@st.cache_resource(show_spinner="Carregando microdados do Sicor…")
def obter_base(fonte: str) -> BaseDados:
    return carregar_base(fonte)


@st.cache_resource
def obter_motor() -> MotorRegras:
    return MotorRegras()


@st.cache_resource
def obter_outbox() -> Outbox:
    return Outbox()


def base_atual() -> BaseDados:
    return obter_base(st.session_state.get("fonte_dados", get_settings().fonte_dados))


def resultado_atual() -> ResultadoPipeline | None:
    return st.session_state.get("resultado")


def executar_pipeline(**kwargs: Any) -> ResultadoPipeline:
    """Executa o pipeline e guarda o resultado na sessão."""
    orq = Orquestrador(
        base=base_atual(),
        motor=obter_motor(),
        cliente_llm=GroqClient(),
        outbox=obter_outbox(),
    )
    resultado = orq.executar(**kwargs)
    st.session_state["resultado"] = resultado
    st.session_state["executado_em"] = resultado.contexto.iniciado_em
    return resultado


def exigir_execucao() -> ResultadoPipeline | None:
    """Mostra aviso padrão quando ainda não houve execução."""
    res = resultado_atual()
    if res is None:
        st.info(
            "Nenhuma execução nesta sessão ainda. Abra a página **Início** e "
            "clique em **Executar pipeline** para gerar alertas e mensagens.",
            icon="▶️",
        )
    return res


# ==========================================================================
# Barra lateral
# ==========================================================================

def barra_lateral(*, mostrar_execucao: bool = True) -> dict[str, Any]:
    """
    Controles globais. Devolve os parâmetros escolhidos.

    A ordem aqui é uma decisão de usabilidade, não estética. A primeira versão
    colocava a ação principal — **Executar pipeline** — no fim da barra, depois
    de sete blocos de configuração. Numa tela de notebook ela ficava abaixo da
    dobra: quem abria o aplicativo pela primeira vez não via o botão, não via o
    seletor de cenário, e concluía que a interface era confusa. Estava certo.

    Agora a barra segue a ordem de quem chega: **o que fazer** primeiro, **como
    ajustar** depois. Os três controles que mudam o resultado ficam visíveis
    sem rolagem; todo o resto vai para seções recolhidas.
    """
    s = get_settings()
    base = base_atual()

    with st.sidebar:
        st.markdown(f"### 🌾 {__app_name__}")
        st.caption(f"{__tagline__} · v{__version__}")

        if not mostrar_execucao:
            # Nas páginas internas a ação principal é voltar ao Início e
            # executar; repetir os controles aqui só confundiria.
            if base.precisa_de_etl:
                st.error(
                    "**Sem dados.** Os dados oficiais do BCB não foram baixados "
                    "nesta máquina. Abra **🗂️ Fonte dos dados** e volte para "
                    "*Automática*.",
                    icon="❌",
                )
            elif resultado_atual() is None:
                st.warning(
                    "Ainda não há execução nesta sessão.\n\n"
                    "Abra **Início** no menu acima e clique em "
                    "**▶️ Executar pipeline**.",
                    icon="👆",
                )
            else:
                res = resultado_atual()
                st.success(
                    f"Execução carregada: {len(res.contexto.alertas)} alertas, "
                    f"{len(res.contexto.mensagens)} mensagens.",
                    icon="✅",
                )
            _bloco_fonte_dados(base, s)
            _rodape_lateral()
            return {}

        # ==================================================================
        # 1. A AÇÃO PRINCIPAL — sempre visível, sem rolagem
        # ==================================================================
        st.markdown("#### 1 · Escolha uma situação")
        rotulo_cenario = st.selectbox(
            "Cenário climático",
            list(CENARIOS.keys()),
            index=list(CENARIOS.keys()).index(
                st.session_state.get("rotulo_cenario", "🌵 Seca / veranico")
            ) if st.session_state.get("rotulo_cenario") in CENARIOS else 1,
            key="rotulo_cenario",
            help="Um cenário simula um evento climático sobre a carteira "
                 "inteira, para você ver o sistema reagir. «Previsão real» "
                 "consulta a previsão de verdade na Open-Meteo — nesse caso "
                 "pode não haver evento nenhum hoje, e é isso mesmo.",
        )
        cenario = CENARIOS[rotulo_cenario]

        st.markdown("#### 2 · Execute")
        executar = st.button("▶️  Executar pipeline", type="primary",
                             **largura_total())
        st.caption(
            "Leva poucos segundos. Funciona sem internet e sem chave de IA."
            if cenario else
            "Consulta a previsão real. Sem internet, o sistema avisa e usa o "
            "gerador interno."
        )

        if base.precisa_de_etl:
            st.error(
                "**Sem dados para mostrar.** Você escolheu os dados oficiais do "
                "BCB, mas eles ainda não foram baixados nesta máquina.\n\n"
                "Abra **🗂️ Fonte dos dados** abaixo e volte para "
                "*Automática* — ou rode `python etl/run_etl.py` no terminal.",
                icon="❌",
            )
        elif base.e_demonstracao:
            st.info("Usando a **base de demonstração** — dados sintéticos com o "
                    "mesmo formato dos oficiais.", icon="🧪")
        else:
            st.success("Usando os **microdados oficiais do Sicor/BCB**.", icon="🏦")

        st.divider()
        st.caption("Tudo abaixo é opcional — os padrões já funcionam.")

        # ==================================================================
        # 2. AJUSTES — recolhidos por padrão
        # ==================================================================
        with st.expander("🎚️ Intensidade e horizonte", expanded=False):
            intensidade = 1.0
            if cenario:
                intensidade = st.slider(
                    "Intensidade do evento", 0.6, 2.0,
                    float(st.session_state.get("f_intensidade", 1.2)), 0.1,
                    key="f_intensidade",
                    help="Quanto maior, mais severo o evento simulado.",
                )
            else:
                st.caption("A intensidade só se aplica a cenários simulados.")
            horizonte = st.slider(
                "Horizonte de previsão (dias)", 3, 14,
                int(st.session_state.get("horizonte", 7)),
                key="horizonte",
                help="Quantos dias à frente o sistema olha.",
            )
            modo_clima = st.selectbox(
                "De onde vem o clima",
                ["auto", "online", "sintetico"],
                index=["auto", "online", "sintetico"].index(
                    st.session_state.get("modo_clima", "auto")
                ),
                key="modo_clima",
                format_func=lambda x: {
                    "auto": "Open-Meteo, com plano B automático",
                    "online": "Open-Meteo obrigatoriamente (exige internet)",
                    "sintetico": "Gerador interno (funciona offline)",
                }[x],
            )

        with st.expander("🔎 Recortar a carteira", expanded=False):
            st.caption("Deixe vazio para monitorar tudo.")
            cart = base.carteira
            ufs = sorted(cart["uf"].dropna().unique().tolist()) if not cart.empty else []
            culturas = sorted(cart["cultura"].dropna().unique().tolist()) if not cart.empty else []
            personas_disp = sorted(cart["persona"].dropna().unique().tolist()) if not cart.empty else []

            sel_uf = st.multiselect("Estado (UF)", ufs,
                                    default=st.session_state.get("f_uf", []), key="f_uf")
            sel_cultura = st.multiselect("Cultura", culturas,
                                         default=st.session_state.get("f_cultura", []),
                                         key="f_cultura")
            sel_persona = st.multiselect("Perfil do produtor", personas_disp,
                                         default=st.session_state.get("f_persona", []),
                                         key="f_persona")
            valor_min = st.number_input("Valor mínimo da operação (R$)", 0, 10_000_000,
                                        int(st.session_state.get("f_valor", 0)), step=10_000,
                                        key="f_valor")

        with st.expander("💬 Como comunicar", expanded=False):
            canais = st.multiselect(
                "Canais ativos", list(CORES_CANAL.keys()),
                default=st.session_state.get(
                    "f_canais", ["whatsapp", "sms", "email", "push", "painel"]),
                key="f_canais",
            )
            max_msgs = st.slider(
                "Máximo de mensagens individuais", 3, 60,
                int(st.session_state.get("f_maxmsg", 12)), key="f_maxmsg",
                help="Limite de segurança: protege a cota gratuita da IA e "
                     "mantém a demonstração rápida.",
            )
            respeitar = st.checkbox(
                "Não repetir mensagem ao mesmo destinatário em 48 h",
                value=st.session_state.get("f_supressao", False),
                key="f_supressao",
                help="Política anti-fadiga. Deixe desligado para poder repetir "
                     "a demonstração quantas vezes quiser.",
            )

        with st.expander("🤖 Inteligência artificial (opcional)", expanded=False):
            cliente = GroqClient()
            if cliente.disponivel:
                st.success("Chave da Groq detectada — as mensagens serão "
                           "redigidas por IA.", icon="🔑")
            else:
                st.info(
                    "**Não é necessário.** Sem chave da Groq, as mensagens são "
                    "geradas por modelos de texto determinísticos, e a "
                    "interface marca cada mensagem com a sua origem.",
                    icon="ℹ️",
                )
            usar_llm = st.checkbox("Usar IA na redação",
                                   value=st.session_state.get("f_llm", True),
                                   key="f_llm")
            modelos = [m.id for m in MODELOS_GROQ]
            modelo = st.selectbox(
                "Modelo de redação", modelos,
                index=modelos.index(s.modelo_redacao) if s.modelo_redacao in modelos else 0,
                format_func=lambda mid: next(
                    (f"{m.rotulo} — {m.perfil}" for m in MODELOS_GROQ if m.id == mid), mid
                ),
                key="f_modelo",
            )
            if modelo != s.modelo_redacao:
                import os

                os.environ["GROQ_MODEL_REDACAO"] = modelo
                reset_settings_cache()
            if st.button("Testar conexão", **largura_total()):
                ok, msg = GroqClient().testar_conexao()
                (st.success if ok else st.error)(msg)

        _bloco_fonte_dados(base, s)

        with st.expander("📱 Modo de leitura", expanded=False):
            st.selectbox(
                "Densidade da tela", list(MODOS_TELA.keys()),
                index=list(MODOS_TELA.keys()).index(
                    st.session_state.get("modo_tela", "auto")
                ) if st.session_state.get("modo_tela") in MODOS_TELA else 0,
                key="modo_tela", format_func=lambda x: MODOS_TELA[x],
                help="O layout já se adapta sozinho ao tamanho da tela. Use "
                     "isto só para forçar a leitura compacta — por exemplo, no "
                     "celular com o navegador em modo desktop.",
            )

        _rodape_lateral()

    return {
        "executar": executar,
        "rotulo_cenario": rotulo_cenario,
        # `parametros` vai direto para `Orquestrador.executar(**parametros)`,
        # então as chaves precisam bater com a assinatura dele.
        "parametros": {
            "data_ref": date.today(),
            "horizonte_dias": horizonte,
            "cenario": cenario,
            "intensidade_cenario": intensidade,
            "modo_clima": modo_clima,
            "filtros": {
                "uf": sel_uf,
                "cultura": sel_cultura,
                "persona": sel_persona,
                "valor_min": valor_min,
            },
            "canais_ativos": tuple(canais),
            "max_mensagens": max_msgs,
            "respeitar_supressao": respeitar,
            "usar_llm": usar_llm,
            "persistir": True,
        },
    }


def _bloco_fonte_dados(base: BaseDados, s: Any) -> None:
    """Procedência dos dados — informação importante, mas não de primeira hora."""
    with st.expander("🗂️ Fonte dos dados", expanded=False):
        st.radio(
            "Origem",
            options=["auto", "curated", "seed"],
            index=["auto", "curated", "seed"].index(
                st.session_state.get("fonte_dados", s.fonte_dados)
            ),
            format_func=lambda x: {
                "auto": "Automática (oficiais, senão demonstração)",
                "curated": "Somente os dados oficiais do BCB",
                "seed": "Somente a amostra de demonstração",
            }[x],
            key="fonte_dados",
            help="Os dados oficiais são produzidos pelos scripts da pasta etl/.",
        )
        st.caption(base.aviso_procedencia)
        ativos = [k for k, v in base.enriquecimentos().items() if v]
        if ativos:
            st.caption("Enriquecimentos ativos: " + ", ".join(ativos))
        if base.problemas:
            st.caption("⚠️ " + " · ".join(base.problemas[:3]))


def _rodape_lateral() -> None:
    st.sidebar.divider()
    st.sidebar.caption(
        "Dados: [Sicor/Proagro — Banco Central do Brasil]"
        "(https://www.bcb.gov.br/estabilidadefinanceira/tabelas-credito-rural-proagro) · "
        "Clima: [Open-Meteo](https://open-meteo.com/) · "
        "IA: [GroqCloud](https://console.groq.com/docs/models)"
    )
    # As licenças das fontes externas exigem atribuição (a CC BY-SA do
    # MapBiomas, por exemplo). Cumprir isso é condição de uso, não cortesia.
    try:
        from agrosentinela.fontes_externas import creditos, resumo as _resumo_fontes

        info = _resumo_fontes()
        with st.sidebar.expander(
            f"Fontes externas ({info['ativas']} ativas, todas livres)", expanded=False
        ):
            for linha in creditos():
                st.caption(f"• {linha}")
    except Exception:  # noqa: BLE001 — o rodapé nunca derruba a página
        pass
    st.sidebar.caption("Licença MIT · Desafio 5 — InsurMinds/I2A2")


# ==========================================================================
# Responsividade
#
# O Streamlit não informa a largura da janela ao servidor, então a adaptação
# acontece em duas camadas que se complementam:
#
# * **CSS** (``viz/theme.py``) — empilha colunas, aumenta alvos de toque e
#   ajusta tipografia abaixo de 640 px, sem depender do servidor;
# * **Python** (aqui) — limita o número de colunas por linha e a altura dos
#   mapas, para que o layout já nasça adequado a telas estreitas.
#
# O usuário também pode declarar o modo na barra lateral. Isso importa: um
# técnico em campo às vezes abre o painel no navegador do celular em modo
# desktop, e queremos que ele possa forçar a leitura compacta.
# ==========================================================================

# ==========================================================================
# Compatibilidade entre versões do Streamlit
#
# O parâmetro `use_container_width=True` foi substituído por `width="stretch"`
# e será removido. Como o projeto declara `streamlit>=1.36,<2.0` e a versão
# instalada depende de quando a pessoa roda o `pip install`, o código precisa
# funcionar nas duas — e sem despejar vinte avisos de depreciação no terminal
# a cada clique, que era o que acontecia.
#
# A decisão é tomada uma única vez, inspecionando a assinatura da função em
# vez de comparar números de versão: assinatura é o que de fato importa, e
# comparar versão dá errado em builds intermediárias.
# ==========================================================================

@lru_cache(maxsize=1)
def _usa_width_moderno() -> bool:
    try:
        from inspect import signature

        return "width" in signature(st.dataframe).parameters
    except Exception:  # noqa: BLE001 — na dúvida, fica no comportamento antigo
        return False


def largura_total() -> dict[str, Any]:
    """
    Argumentos que fazem um componente ocupar toda a largura disponível.

    Use como ``st.plotly_chart(fig, **largura_total())``.
    """
    return {"width": "stretch"} if _usa_width_moderno() else {"use_container_width": True}


MODOS_TELA = {
    "auto": "Automático (recomendado)",
    "celular": "📱 Celular",
    "tablet": "📲 Tablet",
    "desktop": "🖥️ Desktop",
}

# Máximo de colunas lado a lado em cada modo. Mais do que isso vira
# decoração: um cartão de 90 px de largura não comunica número nenhum.
MAX_COLUNAS = {"celular": 1, "tablet": 2, "desktop": 4, "auto": 4}


def modo_tela() -> str:
    return str(st.session_state.get("modo_tela", "auto") or "auto")


def compacto() -> bool:
    """Verdadeiro quando o usuário pediu explicitamente a leitura de celular."""
    return modo_tela() == "celular"


def colunas(spec: int | Sequence[float], **kwargs: Any):
    """
    ``st.columns`` ciente do modo de tela.

    Aceita o número de colunas ou a lista de pesos, como o original. Em modo
    celular devolve contêineres empilhados, de modo que o código das páginas
    não precise de nenhum ``if``: continua escrevendo
    ``c1, c2 = colunas(2)`` e o layout se resolve sozinho.
    """
    n = spec if isinstance(spec, int) else len(spec)
    teto = MAX_COLUNAS.get(modo_tela(), 4)
    if n <= teto:
        return st.columns(spec, **kwargs)
    # Contrato importante: **sempre devolve exatamente n elementos**. As
    # páginas fazem `c1, c2, c3 = colunas(3)`, e devolver menos quebraria o
    # desempacotamento justamente na tela pequena, que é onde não se pode
    # falhar. Quando não cabem lado a lado, viram contêineres empilhados.
    return [st.container() for _ in range(n)]


def altura_mapa(padrao: int | None = None) -> int:
    """Mapa alto no desktop, mapa que cabe na mão no celular."""
    if compacto():
        return ALTURA_MAPA_COMPACTA
    if modo_tela() == "tablet":
        return int((padrao or ALTURA_MAPA_PADRAO) * 0.8)
    return padrao or ALTURA_MAPA_PADRAO


def altura_tabela(padrao: int = 420) -> int:
    return 280 if compacto() else padrao


# ==========================================================================
# Barra de filtros global
# ==========================================================================

CHAVE_FILTROS = "selecao_filtros"


def selecao_atual() -> dict[str, Any]:
    return dict(st.session_state.get(CHAVE_FILTROS, {}) or {})


def barra_filtros(
    df: pd.DataFrame,
    *,
    chave: str = "barra",
    apenas_essenciais: bool = False,
    titulo: str = "Filtros",
) -> dict[str, Any]:
    """
    Desenha a barra de filtros e devolve a seleção.

    Decisões de usabilidade embutidas:

    * a seleção é **compartilhada entre as páginas** (fica em ``session_state``),
      para que ninguém precise refazer o mesmo recorte a cada aba;
    * a barra abre **recolhida**, mas os filtros ativos aparecem como
      etiquetas visíveis acima dela — um painel filtrado sem aviso é a forma
      mais rápida de alguém concluir que "não há alertas" quando há;
    * só entram os filtros cuja coluna existe **e tem mais de um valor** no
      conjunto atual: filtro de uma opção só ocupa espaço e não filtra nada;
    * há um botão de limpar sempre visível.
    """
    if df is None or df.empty:
        return {}

    disponiveis = flt.aplicaveis(df)
    if apenas_essenciais or compacto():
        disponiveis = [f for f in disponiveis if f.essencial]
    if not disponiveis:
        return selecao_atual()

    selecao = selecao_atual()
    ativos = flt.resumo(selecao)

    if ativos:
        etiquetas = "".join(f'<span class="etiqueta">{t}</span>' for t in ativos)
        st.markdown(
            f'<div class="resumo-filtros"><strong>Filtros ativos:</strong> {etiquetas}</div>',
            unsafe_allow_html=True,
        )

    rotulo = f"🔎 {titulo}" + (f" ({len(ativos)} ativos)" if ativos else "")
    with st.expander(rotulo, expanded=bool(ativos) and not compacto()):
        nova: dict[str, Any] = {}
        grupos_presentes = [g for g in flt.GRUPOS
                            if any(f.grupo == g for f in disponiveis)]

        for grupo in grupos_presentes:
            do_grupo = [f for f in disponiveis if f.grupo == grupo]
            if not do_grupo:
                continue
            st.markdown(f"**{grupo}**")
            colunas_grupo = colunas(min(len(do_grupo), 3))
            for i, filtro in enumerate(do_grupo):
                with colunas_grupo[i % len(colunas_grupo)]:
                    valor = _widget_filtro(df, filtro, selecao, chave)
                    if valor is not None:
                        nova[filtro.chave] = valor

        esq, dir_ = st.columns([1, 1])
        with esq:
            if st.button("Limpar filtros", key=f"limpar_{chave}",
                         **largura_total()):
                st.session_state[CHAVE_FILTROS] = {}
                st.rerun()
        with dir_:
            st.caption(
                f"{len(disponiveis)} filtros disponíveis neste conjunto · "
                f"catálogo completo com {len(flt.FILTROS)} filtros na "
                "página de Documentação."
            )

        st.session_state[CHAVE_FILTROS] = nova
        return nova


def _widget_filtro(df: pd.DataFrame, filtro: flt.Filtro,
                   selecao: dict[str, Any], prefixo: str) -> Any:
    """Desenha o controle certo para o tipo do filtro."""
    chave_widget = f"flt_{prefixo}_{filtro.chave}"
    ajuda = filtro.porque

    if filtro.tipo in (flt.TIPO_MULTI, flt.TIPO_ESCOLHA):
        opcoes = flt.opcoes(df, filtro)
        if not opcoes:
            return None
        padrao = [v for v in (selecao.get(filtro.chave) or []) if v in opcoes]
        return st.multiselect(
            filtro.rotulo, opcoes, default=padrao, key=chave_widget, help=ajuda,
            format_func=lambda v: filtro.rotulos.get(v, str(v)),
        )

    if filtro.tipo == flt.TIPO_BOOL:
        rotulos = {None: "Indiferente", True: "Sim", False: "Não"}
        atual = selecao.get(filtro.chave)
        escolha = st.selectbox(
            filtro.rotulo, [None, True, False],
            index=[None, True, False].index(atual) if atual in (None, True, False) else 0,
            key=chave_widget, help=ajuda, format_func=lambda v: rotulos[v],
        )
        return escolha

    if filtro.tipo == flt.TIPO_FAIXA:
        minimo, maximo = flt.limites(df, filtro)
        if maximo <= minimo:
            return None
        atual = selecao.get(filtro.chave) or (minimo, maximo)
        atual = (max(minimo, float(atual[0])), min(maximo, float(atual[1])))
        return st.slider(
            f"{filtro.rotulo}{filtro.sufixo}", minimo, maximo, atual,
            key=chave_widget, help=ajuda,
        )
    return None


def aplicar_filtros(df: pd.DataFrame, selecao: dict[str, Any] | None = None) -> pd.DataFrame:
    """Aplica a seleção corrente e avisa quando o resultado fica vazio."""
    selecao = selecao if selecao is not None else selecao_atual()
    filtrado = flt.aplicar(df, selecao)
    if df is not None and not df.empty and (filtrado is None or filtrado.empty):
        st.warning(
            "Nenhum registro atende aos filtros escolhidos. "
            "Use **Limpar filtros** para voltar ao conjunto completo.",
            icon="🔎",
        )
    return filtrado


# ==========================================================================
# Componentes
# ==========================================================================

def cartao_metrica(rotulo: str, valor: str, nota: str = "") -> None:
    st.markdown(
        f'<div class="bloco-metrica"><div class="rotulo">{rotulo}</div>'
        f'<div class="valor">{valor}</div>'
        f'<div class="nota">{nota}</div></div>',
        unsafe_allow_html=True,
    )


def linha_metricas(itens: list[tuple[str, str, str]]) -> None:
    """
    Linha de cartões que se reorganiza conforme a tela.

    No celular os cartões empilham (um por linha) e no tablet vão de dois em
    dois; no desktop ficam lado a lado. Quatro números espremidos em 90 px
    cada não são um painel — são um enfeite.
    """
    if not itens:
        return
    teto = MAX_COLUNAS.get(modo_tela(), 4)
    for inicio in range(0, len(itens), teto):
        bloco = itens[inicio:inicio + teto]
        faixas = st.columns(len(bloco))
        for coluna, (rotulo, valor, nota) in zip(faixas, bloco):
            with coluna:
                cartao_metrica(rotulo, valor, nota)


def kpis_execucao(res: ResultadoPipeline) -> None:
    alertas = res.alertas_df
    envios = res.envios_df
    exposicao = float(alertas["valor_credito"].sum()) if not alertas.empty else 0.0
    area = float(alertas["area_ha"].sum()) if not alertas.empty else 0.0
    criticos = int((alertas["severidade"] == "critico").sum()) if not alertas.empty else 0
    entregues = int((envios["status"] == "simulado_entregue").sum()) if not envios.empty else 0
    linha_metricas([
        ("Operações monitoradas", inteiro(len(res.contexto.carteira)),
         f"{res.contexto.carteira['cd_ibge'].nunique() if not res.contexto.carteira.empty else 0} municípios"),
        ("Alertas gerados", inteiro(len(alertas)), f"{criticos} críticos"),
        ("Exposição sinalizada", reais_compacto(exposicao), hectares(area)),
        ("Mensagens", inteiro(len(res.contexto.mensagens)),
         f"{entregues} entregas simuladas"),
    ])


def avisos(res: ResultadoPipeline) -> None:
    for aviso in res.contexto.avisos:
        st.warning(aviso, icon="⚠️")


def render_mensagem(msg: Any, *, expandido: bool = False) -> None:
    """Cartão de uma mensagem gerada."""
    from agrosentinela.viz.theme import cor_severidade

    cor = cor_severidade(msg.severidade)
    canal_cor = CORES_CANAL.get(msg.canal, "#64748b")
    origem = "🤖 IA Generativa" if msg.gerado_por == "llm" else "🧩 Template determinístico"
    limite_ok = "✅" if msg.dentro_do_limite else "⚠️ excede o limite"

    cabecalho_html = (
        f'<div class="cartao-msg" style="border-left-color:{cor}">'
        f'<div class="cabecalho">'
        f'{faixa(msg.severidade)}'
        f'<span class="etiqueta" style="border-color:{canal_cor};color:{canal_cor}">'
        f"{msg.canal}</span>"
        f'<span class="etiqueta">{msg.persona_nome}</span>'
        f'<span class="etiqueta">score {msg.score:.0f}</span>'
        f'<span class="etiqueta">{msg.caracteres}/{msg.limite_canal} car. {limite_ok}</span>'
        f'<span class="etiqueta">{origem}{(" · " + msg.modelo) if msg.modelo else ""}</span>'
        f"</div>"
    )
    if msg.assunto:
        cabecalho_html += f"<b>{msg.assunto}</b><br><br>"
    cabecalho_html += f"<pre>{_escapar(msg.texto)}</pre></div>"
    st.markdown(cabecalho_html, unsafe_allow_html=True)

    with st.expander("Por que esta mensagem foi gerada?", expanded=expandido):
        st.markdown(f"**Destinatário:** {msg.destinatario_nome}")
        if msg.municipio:
            st.markdown(f"**Local:** {msg.municipio} — {msg.uf} · **Evento:** {msg.evento}")
        if msg.resumo_interno:
            st.markdown(f"**Resumo interno:** {msg.resumo_interno}")
        if msg.explicacao:
            st.markdown(f"**Rastro das regras:** {msg.explicacao}")
        if msg.acoes:
            st.markdown("**Ações recomendadas:**")
            for a in msg.acoes:
                st.markdown(f"- {a}")
        if msg.revisao:
            st.markdown("**Revisão automática de conformidade:**")
            st.json(msg.revisao, expanded=False)
        st.caption(f"ID {msg.id} · alertas vinculados: {len(msg.alertas)} · criado em {msg.criado_em}")


def _escapar(texto: str) -> str:
    return (
        str(texto)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def tabela(df: pd.DataFrame, altura: int = 420, **kwargs: Any) -> None:
    """
    Tabela padronizada.

    A altura se ajusta ao modo de tela e a rolagem horizontal fica **dentro**
    do quadro (regra em ``theme.py``), para que uma tabela larga nunca empurre
    a página inteira para o lado no celular.
    """
    if df is None or df.empty:
        st.info("Sem registros para exibir.")
        return
    st.dataframe(df, height=altura_tabela(altura), hide_index=True,
                 **largura_total(), **kwargs)


def botao_download(df: pd.DataFrame, nome: str, rotulo: str | None = None) -> None:
    if df is None or df.empty:
        return
    st.download_button(
        rotulo or f"⬇️ Baixar {nome}.csv",
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"{nome}.csv",
        mime="text/csv",
        **largura_total(),
    )


def seletor_evento(chave: str = "sel_evento") -> str | None:
    opcoes = ["(todos)"] + [f"{e.icone} {e.nome}" for e in EVENTOS]
    escolha = st.selectbox("Evento climático", opcoes, key=chave)
    if escolha == "(todos)":
        return None
    return next((e.codigo for e in EVENTOS if f"{e.icone} {e.nome}" == escolha), None)


def rodape_fonte(texto: str) -> None:
    st.markdown(f'<div class="rodape-fonte">{texto}</div>', unsafe_allow_html=True)
