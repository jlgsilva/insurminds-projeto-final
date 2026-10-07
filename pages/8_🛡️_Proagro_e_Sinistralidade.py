"""Proagro e sinistralidade — histórico de acionamento e leitura atuarial."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from agrosentinela.data.loader import indices_sinistralidade  # noqa: E402
from agrosentinela.rules.catalogo import EVENTOS_POR_CODIGO  # noqa: E402
from agrosentinela.ui import (  # noqa: E402
    barra_lateral,
    base_atual,
    botao_download,
    cabecalho,
    colunas,
    configurar_pagina,
    largura_total,
    linha_metricas,
    tabela,
)
from agrosentinela.utils.formato import inteiro, num, pct, reais_compacto  # noqa: E402
from agrosentinela.viz import charts  # noqa: E402

configurar_pagina("Proagro e Sinistralidade", "🛡️")
barra_lateral(mostrar_execucao=False)

cabecalho(
    "Proagro e Sinistralidade",
    "O que a série histórica de acionamento do Proagro diz sobre o risco de "
    "cada município, cultura e evento.",
    "🛡️",
)

base = base_atual()
sin = base.proagro_sinistros

if sin.empty:
    st.warning("Histórico de Proagro não disponível na base carregada.")
    st.stop()

st.markdown(
    """
O Proagro é o mecanismo público que exonera o produtor de obrigações
financeiras em caso de perda por evento climático coberto. Toda a cadeia
está no Sicor: o **pedido de cobertura** (COP), o **relatório de comprovação
de perdas** (RCP) e a súmula de julgamento.

Para o AgroSentinela, essa série responde a uma pergunta que a previsão do
tempo sozinha não responde: *dado que este evento vai acontecer aqui, qual a
probabilidade histórica de ele virar sinistro?* É o componente `freq_evento`
do score e a base da regra **R-HIS-01**.
    """
)

# ==========================================================================
# Métricas gerais
# ==========================================================================
periodo = f"{int(sin['ano_inicio'].min())}–{int(sin['ano_fim'].max())}"
linha_metricas([
    ("Pedidos de cobertura", inteiro(sin["n_cop"].sum()), f"período {periodo}"),
    ("Comprovações de perda", inteiro(sin["n_rcp"].sum()),
     f"{pct(100 * sin['n_rcp'].sum() / max(sin['n_cop'].sum(), 1))} dos pedidos"),
    ("Valor indenizado", reais_compacto(sin["valor_indenizado"].sum()), ""),
    ("Municípios com registro", inteiro(sin["cd_ibge"].nunique()),
     f"{sin['cultura'].nunique()} culturas"),
])
st.write("")

col1, col2 = colunas([3, 2], gap="large")
with col1:
    st.plotly_chart(charts.sinistralidade_evento(sin), **largura_total())
with col2:
    por_evento = (
        sin.groupby("evento", as_index=False)
        .agg(cop=("n_cop", "sum"), rcp=("n_rcp", "sum"),
             valor=("valor_indenizado", "sum"))
        .sort_values("cop", ascending=False)
    )
    por_evento["Evento"] = por_evento["evento"].map(
        lambda c: f"{EVENTOS_POR_CODIGO[c].icone} {EVENTOS_POR_CODIGO[c].nome}"
        if c in EVENTOS_POR_CODIGO else c
    )
    por_evento["Participação"] = pct(0)  # placeholder substituído abaixo
    total_cop = por_evento["cop"].sum()
    por_evento["Participação"] = (100 * por_evento["cop"] / max(total_cop, 1)).round(1).map(
        lambda v: f"{v}%".replace(".", ",")
    )
    por_evento["Severidade média"] = (
        por_evento["valor"] / por_evento["rcp"].replace(0, pd.NA)
    ).map(reais_compacto)
    tabela(
        por_evento[["Evento", "cop", "rcp", "Participação", "Severidade média"]].rename(
            columns={"cop": "Pedidos", "rcp": "Comprovações"}
        ),
        altura=340,
    )
    st.caption(
        "A severidade média (indenização por comprovação) é o que diferencia um "
        "evento frequente e barato de um raro e caro."
    )

st.divider()

# ==========================================================================
# Recorte por município e cultura
# ==========================================================================
st.markdown("#### Perfil de risco por município")

col1, col2, col3 = colunas(3)
with col1:
    ufs = ["(todas)"] + sorted(sin["uf"].dropna().unique().tolist())
    uf = st.selectbox("UF", ufs, key="proagro_uf")
with col2:
    culturas = ["(todas)"] + sorted(sin["cultura"].dropna().unique().tolist())
    cultura = st.selectbox("Cultura", culturas, key="proagro_cult")
with col3:
    eventos = ["(todos)"] + sorted(sin["evento"].dropna().unique().tolist())
    evento = st.selectbox("Evento", eventos, key="proagro_evt")

sel = sin
if uf != "(todas)":
    sel = sel[sel["uf"] == uf]
if cultura != "(todas)":
    sel = sel[sel["cultura"] == cultura]
if evento != "(todos)":
    sel = sel[sel["evento"] == evento]

nomes = base.municipios.set_index("cd_ibge")["municipio"]
agg = (
    sel.groupby(["cd_ibge", "uf"], as_index=False)
    .agg(cop=("n_cop", "sum"), rcp=("n_rcp", "sum"),
         operacoes=("n_operacoes", "sum"), valor=("valor_indenizado", "sum"))
)
agg["Município"] = agg["cd_ibge"].map(nomes)
agg["Taxa de acionamento"] = (100 * agg["cop"] / agg["operacoes"].replace(0, pd.NA)).round(2)
agg["Taxa de deferimento"] = (100 * agg["rcp"] / agg["cop"].replace(0, pd.NA)).round(1)
agg["Valor indenizado"] = agg["valor"].map(reais_compacto)
agg = agg.sort_values("cop", ascending=False)

exibir = agg[["Município", "uf", "cop", "rcp", "Taxa de acionamento",
              "Taxa de deferimento", "Valor indenizado"]].rename(
    columns={"uf": "UF", "cop": "Pedidos", "rcp": "Comprovações"}
)
tabela(exibir, altura=460)
botao_download(agg, "proagro_por_municipio")

# ==========================================================================
# Matriz município × evento
# ==========================================================================
st.markdown("#### Composição dos acionamentos por município")
st.caption(
    "Participação de cada evento no total de pedidos de cobertura do "
    "município. É exatamente o vetor usado pelo motor de regras: um município "
    "onde 60% dos sinistros históricos são de seca recebe prioridade maior "
    "quando uma seca é prevista."
)

top_municipios = agg.head(18)["cd_ibge"].tolist()
matriz = (
    sin[sin["cd_ibge"].isin(top_municipios)]
    .pivot_table(index="cd_ibge", columns="evento", values="n_cop",
                 aggfunc="sum", fill_value=0)
)
if not matriz.empty:
    matriz = matriz.div(matriz.sum(axis=1).replace(0, pd.NA), axis=0).fillna(0).round(3) * 100
    matriz.index = matriz.index.map(nomes)
    import plotly.express as px

    fig = px.imshow(
        matriz, text_auto=".0f", aspect="auto",
        color_continuous_scale=["#f8fafc", "#fcd34d", "#ea580c", "#7f1d1d"],
        labels=dict(color="% dos pedidos"),
    )
    fig.update_layout(height=520, margin=dict(l=8, r=8, t=40, b=8),
                      title="Participação do evento nos pedidos de cobertura (%)",
                      xaxis_title="", yaxis_title="", separators=",.")
    st.plotly_chart(fig, **largura_total())

# ==========================================================================
# Índices consolidados
# ==========================================================================
with st.expander("Índices de sinistralidade usados pelo motor de regras"):
    idx = indices_sinistralidade(sin)
    idx["municipio"] = idx["cd_ibge"].map(nomes)
    idx["freq_evento"] = (idx["freq_evento"] * 100).round(1)
    idx["taxa_acionamento"] = (idx["taxa_acionamento"] * 100).round(2)
    tabela(
        idx[["municipio", "evento", "n_cop", "n_rcp", "freq_evento",
             "taxa_acionamento", "severidade_media"]].rename(
            columns={
                "municipio": "Município", "evento": "Evento",
                "n_cop": "Pedidos", "n_rcp": "Comprovações",
                "freq_evento": "Participação (%)",
                "taxa_acionamento": "Acionamento (%)",
                "severidade_media": "Severidade média (R$)",
            }
        ),
        altura=460,
    )
    botao_download(idx, "indices_sinistralidade")

# ==========================================================================
# Alíquotas
# ==========================================================================
st.markdown("#### Alíquotas do Proagro por município")
st.caption(
    "Fonte oficial: `AliquotaBaseProagro.csv` (Banco Central). Na base de "
    "demonstração as alíquotas são simuladas."
)
muni = base.municipios[["municipio", "uf", "regiao", "aliquota_proagro", "polo_agricola"]].copy()
muni = muni.sort_values("aliquota_proagro", ascending=False)
muni["aliquota_proagro"] = muni["aliquota_proagro"].map(lambda v: pct(v, 2))
muni.columns = ["Município", "UF", "Região", "Alíquota básica", "Polo agrícola"]
tabela(muni, altura=420)
