"""Radar climático — série prevista e indicadores por município."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from agrosentinela.rules.catalogo import EVENTOS_POR_CODIGO  # noqa: E402
from agrosentinela.ui import (  # noqa: E402
    altura_mapa,
    barra_lateral,
    botao_download,
    cabecalho,
    colunas,
    configurar_pagina,
    exigir_execucao,
    largura_total,
    linha_metricas,
    tabela,
)
from agrosentinela.utils.formato import data_curta, hectares, inteiro, num, reais_compacto  # noqa: E402
from agrosentinela.viz import charts  # noqa: E402
from agrosentinela.viz.theme import ROTULO_SEVERIDADE, cor_severidade  # noqa: E402
from agrosentinela.weather.indicadores import descricao_indicadores  # noqa: E402

configurar_pagina("Radar Climático", "🌦️")
barra_lateral(mostrar_execucao=False)

cabecalho(
    "Radar Climático",
    "Previsão diária e indicadores derivados, por município da carteira.",
    "🌦️",
)

res = exigir_execucao()
if res is None:
    st.stop()

clima = res.contexto.clima_diario
indicadores = res.contexto.indicadores
carteira = res.contexto.carteira
eventos = res.contexto.eventos_municipio

if clima.empty:
    st.warning("Nenhuma série meteorológica foi obtida nesta execução.")
    st.stop()

fonte = ", ".join(sorted(clima["fonte"].dropna().unique())) if "fonte" in clima else "—"
st.caption(
    f"Fonte das séries: **{fonte}** · {clima['cell_id'].nunique()} células de grade · "
    f"{clima['data'].nunique()} dias (histórico recente + previsão)."
)
if "sintetico" in fonte:
    st.warning(
        "Séries geradas pelo simulador determinístico — úteis para demonstrar o "
        "motor de regras, mas não representam a previsão real. Selecione a fonte "
        "«Open-Meteo (obrigatório)» na barra lateral para usar dados reais.",
        icon="🧪",
    )

# ==========================================================================
# Seleção de município
# ==========================================================================
municipios = (
    carteira.dropna(subset=["cell_id"])
    .groupby(["municipio", "uf", "cell_id"], as_index=False)
    .agg(operacoes=("ref_bacen", "count"), exposicao=("valor_credito", "sum"),
         area=("area_ha", "sum"))
    .sort_values("exposicao", ascending=False)
)
if municipios.empty:
    st.warning("Nenhum município georreferenciado na carteira filtrada.")
    st.stop()

municipios["rotulo"] = (
    municipios["municipio"] + " - " + municipios["uf"]
    + "  (" + municipios["operacoes"].astype(str) + " operações)"
)

col_a, col_b = colunas([2, 1])
with col_a:
    escolha = st.selectbox("Município", municipios["rotulo"].tolist(), key="radar_muni")
with col_b:
    st.metric("Municípios monitorados", len(municipios))

linha = municipios[municipios["rotulo"] == escolha].iloc[0]
cell = linha["cell_id"]

serie = clima[clima["cell_id"] == cell].copy()
ind = indicadores[indicadores["cell_id"] == cell]
valores = ind.iloc[0].to_dict() if not ind.empty else {}

# ==========================================================================
# Cabeçalho do município
# ==========================================================================
linha_metricas([
    ("Operações no município", inteiro(linha["operacoes"]),
     f"{linha['municipio']} - {linha['uf']}"),
    ("Exposição", reais_compacto(linha["exposicao"]), hectares(linha["area"])),
    ("Chuva prevista (7 d)", f"{num(valores.get('prec_7d', 0), 0)} mm",
     f"maior em 24 h: {num(valores.get('prec_max_24h', 0), 0)} mm"),
    ("Dias secos consecutivos", inteiro(valores.get("dias_secos_consecutivos", 0)),
     f"balanço hídrico 14 d: {num(valores.get('balanco_hidrico_14d', 0), 0)} mm"),
])
st.write("")

# ==========================================================================
# Eventos identificados neste município
# ==========================================================================
evt_local = eventos[eventos["cell_id"] == cell] if not eventos.empty else pd.DataFrame()
if evt_local.empty:
    st.success("Nenhum evento climático relevante identificado neste município.", icon="✅")
else:
    st.markdown("#### Eventos identificados")
    faixas = colunas(min(len(evt_local), 4))
    for coluna, (_, e) in zip(faixas, evt_local.iterrows()):
        with coluna:
            cor = cor_severidade(e["severidade"])
            gatilhos = ", ".join(
                f"{k} = {num(v, 1)}" for k, v in (e.get("gatilhos") or {}).items()
            )
            st.markdown(
                f'<div class="bloco-metrica" style="border-left:5px solid {cor}">'
                f'<div class="rotulo">{e["icone"]} {e["evento_nome"]}</div>'
                f'<div class="valor" style="color:{cor};font-size:1.05rem">'
                f'{ROTULO_SEVERIDADE.get(e["severidade"], e["severidade"])}</div>'
                f'<div class="nota">Pico: {data_curta(e.get("dia_pico")) or "—"}<br>{gatilhos}</div>'
                f"</div>",
                unsafe_allow_html=True,
            )
    st.write("")

# ==========================================================================
# Série e indicadores
# ==========================================================================
st.plotly_chart(
    charts.serie_climatica(serie, f"Série diária — {linha['municipio']}-{linha['uf']}"),
    **largura_total(),
)
st.caption(
    "A área à esquerda de hoje é observação recente; à direita, previsão. "
    "ET0 é a evapotranspiração de referência (FAO-56) — a diferença entre "
    "chuva e ET0 é o balanço hídrico usado nas regras de seca."
)

col1, col2 = colunas(2, gap="large")
with col1:
    st.plotly_chart(
        charts.barras_indicadores(
            valores,
            ["prec_1d", "prec_3d", "prec_7d", "prec_14d", "prec_max_24h", "prec_passada_14d"],
            "Precipitação (mm)",
        ),
        **largura_total(),
    )
    st.plotly_chart(
        charts.barras_indicadores(
            valores,
            ["tmin_min", "tmax_max", "dias_tmin_le_3", "dias_tmax_ge_35", "amplitude_max"],
            "Temperatura (°C e dias)",
        ),
        **largura_total(),
    )
with col2:
    st.plotly_chart(
        charts.barras_indicadores(
            valores,
            ["dias_secos_consecutivos", "dias_secos_passados", "dias_com_chuva_7d",
             "balanco_hidrico_7d", "balanco_hidrico_14d", "et0_7d"],
            "Regime hídrico",
        ),
        **largura_total(),
    )
    st.plotly_chart(
        charts.barras_indicadores(
            valores,
            ["rajada_max", "vento_medio_max", "cape_max", "prob_granizo",
             "umidade_media", "umidade_min"],
            "Vento, convecção e umidade",
        ),
        **largura_total(),
    )

# ==========================================================================
# Operações do município e alertas
# ==========================================================================
st.markdown("#### Operações expostas neste município")
alertas = res.alertas_df
locais = alertas[alertas["municipio"] == linha["municipio"]] if not alertas.empty else pd.DataFrame()
if locais.empty:
    st.info("Nenhuma operação deste município atingiu o limiar de notificação.")
else:
    exibir = locais[["ref_bacen", "produto", "fase_nome", "evento_nome", "severidade",
                     "score", "area_ha", "valor_credito", "tipo_seguro", "persona"]].copy()
    exibir["valor_credito"] = exibir["valor_credito"].map(reais_compacto)
    exibir["area_ha"] = exibir["area_ha"].map(hectares)
    exibir["score"] = exibir["score"].round(0).astype(int)
    exibir["severidade"] = exibir["severidade"].map(ROTULO_SEVERIDADE)
    exibir.columns = ["Operação", "Cultura", "Fase", "Evento", "Severidade", "Score",
                      "Área", "Valor", "Cobertura", "Perfil"]
    tabela(exibir, altura=380)
    botao_download(locais, f"alertas_{linha['municipio']}")

with st.expander("Série diária completa (tabela)"):
    tabela(serie.sort_values("data"), altura=420)
    botao_download(serie, f"clima_{linha['municipio']}")

with st.expander("Dicionário dos indicadores"):
    tabela(pd.DataFrame(descricao_indicadores()), altura=480)
