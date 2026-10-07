"""Painel executivo — visão consolidada da exposição e dos alertas."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from agrosentinela.data.loader import estatisticas_carteira  # noqa: E402
from agrosentinela.personas import PERSONAS_POR_CODIGO  # noqa: E402
from agrosentinela.ui import (  # noqa: E402
    altura_mapa,
    aplicar_filtros,
    barra_filtros,
    barra_lateral,
    base_atual,
    botao_download,
    cabecalho,
    colunas,
    compacto,
    configurar_pagina,
    exigir_execucao,
    kpis_execucao,
    largura_total,
    linha_metricas,
    rodape_fonte,
    tabela,
)
from agrosentinela.utils.formato import (  # noqa: E402
    hectares,
    inteiro,
    pct,
    reais_compacto,
)
from agrosentinela.viz import charts, maps  # noqa: E402
from agrosentinela.viz.theme import ROTULO_SEVERIDADE  # noqa: E402

configurar_pagina("Painel Executivo", "📊")
barra_lateral(mostrar_execucao=False)

cabecalho(
    "Painel Executivo",
    "Exposição da carteira de crédito rural e alertas climáticos da execução atual.",
    "📊",
)

base = base_atual()
stats = estatisticas_carteira(base.carteira)

# ==========================================================================
# Carteira (independe de execução)
# ==========================================================================
st.markdown("#### Carteira monitorada")
if stats:
    linha_metricas([
        ("Operações", inteiro(stats["n_operacoes"]),
         f"{stats['n_municipios']} municípios em {stats['n_ufs']} UFs"),
        ("Valor financiado", reais_compacto(stats["valor_total"]),
         f"ticket médio {reais_compacto(stats['valor_medio'])}"),
        ("Área financiada", hectares(stats["area_total"]),
         f"{stats['n_culturas']} culturas"),
        ("Com cobertura de risco", pct(stats["pct_coberto"]),
         f"{reais_compacto(stats['valor_descoberto'])} sem cobertura"),
    ])
else:
    st.warning("Nenhuma carteira carregada.")

col1, col2 = colunas(2, gap="large")
with col1:
    dimensao = st.selectbox(
        "Composição por", ["cultura", "uf", "programa", "instituicao", "persona", "regiao"],
        key="dim_composicao",
    )
    st.plotly_chart(charts.composicao_carteira(base.carteira, dimensao),
                    **largura_total())
with col2:
    st.plotly_chart(charts.cobertura_por_programa(base.carteira), **largura_total())
    st.caption(
        "A ausência de cobertura declarada é, ao mesmo tempo, o maior fator de "
        "risco do produtor e a maior oportunidade comercial do corretor — por "
        "isso a regra R-COB-01 notifica os dois lados."
    )

st.divider()

# ==========================================================================
# Execução
# ==========================================================================
res = exigir_execucao()
if res is None:
    st.stop()

cabecalho(
    "Alertas da execução atual",
    f"{res.execucao_id} · horizonte de {res.contexto.horizonte_dias} dias"
    + (f" · cenário simulado: {res.contexto.cenario}" if res.contexto.cenario else ""),
    "🚨",
)
kpis_execucao(res)
st.write("")

alertas_completos = res.alertas_df

# A barra de filtros é global: a seleção feita aqui vale nas demais páginas,
# para que ninguém precise refazer o mesmo recorte a cada aba.
barra_filtros(alertas_completos, chave="painel")
alertas = aplicar_filtros(alertas_completos)
if alertas is not None and not alertas.empty and len(alertas) < len(alertas_completos):
    st.caption(
        f"Exibindo {len(alertas):,} de {len(alertas_completos):,} alertas "
        "após os filtros.".replace(",", ".")
    )

if alertas is None or alertas.empty:
    st.success(
        "Nenhuma operação atingiu o limiar de notificação neste horizonte. "
        "Experimente um cenário climático na barra lateral para ver o motor em ação.",
        icon="✅",
    )
    st.stop()

c1, c2 = colunas(2, gap="large")
with c1:
    st.plotly_chart(charts.alertas_por_severidade(alertas), **largura_total())
    st.plotly_chart(charts.distribuicao_score(alertas), **largura_total())
with c2:
    st.plotly_chart(charts.exposicao_por_uf(alertas), **largura_total())

st.plotly_chart(charts.matriz_evento_cultura(alertas), **largura_total())
st.plotly_chart(charts.fases_afetadas(alertas), **largura_total())

# ==========================================================================
# Onde está o dinheiro em risco
#
# O mesmo conjunto de alertas, agregado por município e desenhado no mapa.
# A tabela abaixo serve para conferir; o mapa serve para decidir — e quem
# trabalha com território decide olhando o mapa.
# ==========================================================================
st.markdown("#### Onde está a exposição")
geo = (
    alertas.groupby(["municipio", "uf"], as_index=False)
    .agg(lat=("lat", "mean"), lon=("lon", "mean"),
         saldo_devedor=("valor_credito", "sum"),
         area_municipio=("area_ha", "sum"),
         criticos=("severidade", lambda s: int((s == "critico").sum())),
         cobertura_total=("tem_cobertura", lambda s: float(s.astype(bool).mean())))
)
aba_exposicao, aba_protecao = st.tabs(["💰 Exposição sinalizada", "🛡️ Proteção"])
with aba_exposicao:
    st.plotly_chart(
        maps.mapa_exposicao(geo.assign(saldo_vencido=0.0), altura=altura_mapa()),
        **largura_total(),
    )
    rodape_fonte(
        "Tamanho do círculo: exposição financeira sinalizada. Fonte: Sicor/BCB."
    )
with aba_protecao:
    st.plotly_chart(
        maps.mapa_cobertura(geo, altura=altura_mapa()), **largura_total()
    )
    rodape_fonte(
        "Verde: praça com proteção consolidada. Vermelho: deserto de proteção. "
        "Combina a cobertura declarada no Sicor com a penetração do seguro "
        "rural privado subvencionado (PSR/MAPA)."
    )

# ==========================================================================
# Top municípios
# ==========================================================================
st.markdown("#### Municípios prioritários")
st.caption(
    "Ordenados por número de alertas críticos e, em seguida, por exposição "
    "financeira — a mesma ordenação que alimenta o boletim do gerente de "
    "crédito rural."
)
top = (
    alertas.groupby(["municipio", "uf"], as_index=False)
    .agg(
        alertas=("id", "count"),
        criticos=("severidade", lambda s: int((s == "critico").sum())),
        operacoes=("ref_bacen", "nunique"),
        exposicao=("valor_credito", "sum"),
        area_ha=("area_ha", "sum"),
        score_max=("score", "max"),
        sem_cobertura=("tem_cobertura", lambda s: int((~s.astype(bool)).sum())),
        eventos=("evento_nome", lambda s: ", ".join(sorted(set(s))[:3])),
    )
    .sort_values(["criticos", "exposicao"], ascending=False)
)
exibir = top.head(25).copy()
exibir["exposicao"] = exibir["exposicao"].map(reais_compacto)
exibir["area_ha"] = exibir["area_ha"].map(hectares)
exibir["score_max"] = exibir["score_max"].round(0).astype(int)
exibir.columns = ["Município", "UF", "Alertas", "Críticos", "Operações", "Exposição",
                  "Área", "Score máx.", "Sem cobertura", "Eventos"]
tabela(exibir, altura=460)
botao_download(top, "municipios_prioritarios")

# ==========================================================================
# Por persona
# ==========================================================================
st.markdown("#### Quem precisa ser comunicado")
por_persona = (
    alertas.groupby("persona", as_index=False)
    .agg(alertas=("id", "count"), operacoes=("ref_bacen", "nunique"),
         exposicao=("valor_credito", "sum"),
         criticos=("severidade", lambda s: int((s == "critico").sum())))
    .sort_values("alertas", ascending=False)
)
por_persona["Perfil"] = por_persona["persona"].map(
    lambda c: PERSONAS_POR_CODIGO[c].nome if c in PERSONAS_POR_CODIGO else c
)
por_persona["Canal preferencial"] = por_persona["persona"].map(
    lambda c: PERSONAS_POR_CODIGO[c].canal_padrao if c in PERSONAS_POR_CODIGO else "—"
)
por_persona["Exposição"] = por_persona["exposicao"].map(reais_compacto)
tabela(
    por_persona[["Perfil", "Canal preferencial", "alertas", "criticos",
                 "operacoes", "Exposição"]].rename(
        columns={"alertas": "Alertas", "criticos": "Críticos", "operacoes": "Operações"}
    ),
    altura=280,
)

st.caption(
    "Observação: personas institucionais (banco, seguradora, ATER, corretor e "
    "gestor público) recebem **boletins consolidados**, não mensagens por "
    "operação. Veja a Central de Comunicação."
)

with st.expander("Tabela completa de alertas"):
    tabela(alertas, altura=520)
    botao_download(alertas, f"alertas_{res.execucao_id}")
