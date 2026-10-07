"""Mapas de exposição, risco climático e histórico do Proagro."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from agrosentinela.ui import (  # noqa: E402
    altura_mapa,
    aplicar_filtros,
    barra_filtros,
    barra_lateral,
    base_atual,
    botao_download,
    cabecalho,
    colunas,
    configurar_pagina,
    exigir_execucao,
    largura_total,
    linha_metricas,
    rodape_fonte,
    tabela,
)
from agrosentinela.utils.formato import hectares, inteiro, reais_compacto  # noqa: E402
from agrosentinela.viz import maps  # noqa: E402

configurar_pagina("Mapa de Risco", "🗺️")
barra_lateral(mostrar_execucao=False)

cabecalho(
    "Mapa de Exposição e Risco",
    "Onde está o crédito rural, onde está o evento climático e onde os dois se encontram.",
    "🗺️",
)

base = base_atual()

aba_alertas, aba_carteira, aba_glebas, aba_clima, aba_proagro, aba_expo = st.tabs(
    ["🚨 Alertas da execução", "🌾 Carteira monitorada", "📐 Glebas (talhões)",
     "🌦️ Indicadores climáticos", "🛡️ Histórico do Proagro", "💰 Exposição"]
)

# ==========================================================================
with aba_alertas:
    res = exigir_execucao()
    if res is not None:
        alertas = res.alertas_df
        if alertas.empty:
            st.success("Nenhum alerta nesta execução.", icon="✅")
        else:
            # Barra de filtros compartilhada com as demais páginas: o recorte
            # feito aqui continua valendo na Central de Comunicação e no
            # Painel Executivo.
            barra_filtros(alertas, chave="mapa")
            sel = aplicar_filtros(alertas)
            if sel is None or sel.empty:
                sel = alertas.iloc[0:0]
            if sel.empty:
                st.info("Nenhum alerta com os filtros selecionados.")
            else:
                linha_metricas([
                    ("Municípios com alerta", inteiro(sel["cd_ibge"].nunique()), ""),
                    ("Alertas exibidos", inteiro(len(sel)),
                     f"{int((sel['severidade'] == 'critico').sum())} críticos"),
                    ("Exposição no mapa", reais_compacto(sel["valor_credito"].sum()),
                     hectares(sel["area_ha"].sum())),
                    ("Sem cobertura", inteiro(int((~sel["tem_cobertura"].astype(bool)).sum())),
                     reais_compacto(sel.loc[~sel["tem_cobertura"].astype(bool), "valor_credito"].sum())),
                ])
                st.write("")
                st.plotly_chart(maps.mapa_alertas(sel, altura=altura_mapa()),
                                **largura_total())
                st.caption(
                    "Tamanho da bolha = exposição financeira no município. "
                    "Cor = maior severidade encontrada. Passe o mouse para ver o detalhe."
                )
                botao_download(sel, "alertas_mapa")

# ==========================================================================
with aba_carteira:
    st.markdown("##### Distribuição da carteira de crédito rural")
    cart = base.carteira
    if cart.empty:
        st.warning("Carteira não carregada.")
    else:
        col1, col2 = colunas(2)
        with col1:
            ufs = sorted(cart["uf"].dropna().unique().tolist())
            sel_uf = st.multiselect("UF", ufs, default=[], key="mapa_cart_uf")
        with col2:
            culturas = sorted(cart["cultura"].dropna().unique().tolist())
            sel_cult = st.multiselect("Cultura", culturas, default=[], key="mapa_cart_cult")

        sel = cart
        if sel_uf:
            sel = sel[sel["uf"].isin(sel_uf)]
        if sel_cult:
            sel = sel[sel["cultura"].isin(sel_cult)]

        linha_metricas([
            ("Operações", inteiro(len(sel)), f"{sel['cd_ibge'].nunique()} municípios"),
            ("Valor", reais_compacto(sel["valor_credito"].sum()), ""),
            ("Área", hectares(sel["area_ha"].sum()), ""),
            ("Cobertura declarada",
             f"{sel['tem_cobertura'].mean() * 100:.1f}%" if len(sel) else "—", ""),
        ])
        st.write("")
        st.plotly_chart(maps.mapa_carteira(sel, altura=altura_mapa()),
                        **largura_total())
        st.caption(
            "Cada bolha é um município; o tamanho representa o valor financiado e "
            "a cor, a cultura predominante nas operações daquele município."
        )

# ==========================================================================
with aba_clima:
    res = st.session_state.get("resultado")
    if res is None:
        st.info("Execute o pipeline para calcular os indicadores climáticos.", icon="▶️")
    elif res.contexto.indicadores.empty:
        st.warning("Nenhum indicador climático calculado nesta execução.")
    else:
        indicadores = res.contexto.indicadores
        cart = res.contexto.carteira
        # Liga indicadores (por célula) aos municípios (para o mapa)
        geo = (
            cart.dropna(subset=["cell_id", "lat", "lon"])
            .groupby(["cell_id", "municipio", "uf"], as_index=False)
            .agg(lat=("lat", "first"), lon=("lon", "first"),
                 operacoes=("ref_bacen", "count"))
        )
        dados = geo.merge(indicadores, on="cell_id", how="inner")

        opcoes = {
            "Chuva prevista em 7 dias (mm)": ("prec_7d", "Blues"),
            "Maior acumulado em 24 h (mm)": ("prec_max_24h", "Blues"),
            "Dias secos consecutivos": ("dias_secos_consecutivos", "YlOrBr"),
            "Balanço hídrico 14 dias (mm)": ("balanco_hidrico_14d", "RdYlGn"),
            "Temperatura mínima prevista (°C)": ("tmin_min", "RdYlBu"),
            "Temperatura máxima prevista (°C)": ("tmax_max", "RdYlBu_r"),
            "Dias com máxima ≥ 35 °C": ("dias_tmax_ge_35", "Reds"),
            "Rajada máxima (km/h)": ("rajada_max", "Purples"),
            "Índice de granizo (0–100)": ("prob_granizo", "Teal"),
            "Umidade relativa média (%)": ("umidade_media", "Blues"),
        }
        rotulo = st.selectbox("Indicador", list(opcoes.keys()), key="mapa_ind")
        coluna, escala = opcoes[rotulo]

        st.plotly_chart(
            maps.mapa_indicador(dados, coluna, rotulo, escala=escala,
                                altura=altura_mapa()),
            **largura_total(),
        )
        st.caption(
            "Valores calculados a partir da série diária da célula de grade "
            "(~11 km) em que cada município se enquadra. Janela prevista: "
            f"{res.contexto.horizonte_dias} dias; janela observada: 14 dias."
        )
        with st.expander("Tabela de indicadores por município"):
            cols = ["municipio", "uf", "operacoes", coluna]
            tabela(dados[cols].sort_values(coluna, ascending=False), altura=420)
            botao_download(dados, "indicadores_climaticos")

# ==========================================================================
with aba_proagro:
    st.markdown("##### Onde o Proagro historicamente é acionado")
    sin = base.proagro_sinistros
    if sin.empty:
        st.warning("Histórico de Proagro não carregado.")
    else:
        eventos = sorted(sin["evento"].dropna().unique().tolist())
        evt = st.selectbox("Evento", ["(todos)"] + eventos, key="mapa_proagro_evt")
        sel = sin if evt == "(todos)" else sin[sin["evento"] == evt]

        geo = base.municipios[["cd_ibge", "municipio", "uf", "lat", "lon"]]
        dados = (
            sel.groupby("cd_ibge", as_index=False)
            .agg(n_cop=("n_cop", "sum"), n_rcp=("n_rcp", "sum"),
                 valor_indenizado=("valor_indenizado", "sum"))
            .merge(geo, on="cd_ibge", how="inner")
        )
        linha_metricas([
            ("Pedidos de cobertura", inteiro(dados["n_cop"].sum()), "no período da base"),
            ("Comprovações de perda", inteiro(dados["n_rcp"].sum()), ""),
            ("Valor indenizado", reais_compacto(dados["valor_indenizado"].sum()), ""),
            ("Municípios", inteiro(len(dados)), ""),
        ])
        st.write("")
        st.plotly_chart(maps.mapa_densidade_sinistros(dados, altura=altura_mapa()),
                        **largura_total())
        st.caption(
            "Mapa de calor dos pedidos de cobertura (COP) registrados no Sicor. "
            "Essa série alimenta a regra R-HIS-01, que eleva a prioridade em "
            "municípios historicamente recorrentes para o mesmo evento."
        )
        botao_download(dados, "proagro_por_municipio")

# ==========================================================================
with aba_glebas:
    st.markdown("##### O talhão, não o centroide do município")
    st.caption(
        "Os arquivos `sicor_glebas_wkt_AAAA.gz` publicam o **polígono de cada "
        "gleba financiada**. Com eles, a consulta climática deixa de ser feita "
        "no centroide do município e passa a ser feita na própria lavoura. "
        "Em municípios extensos — Ribas do Rio Pardo, Altamira — a distância "
        "entre os dois passa de 80 km, o bastante para consultar uma frente de "
        "chuva que não está sobre o talhão."
    )
    glebas = base.glebas
    if glebas is None or glebas.empty:
        st.info(
            "Geometria de glebas não carregada nesta base. Para habilitar: "
            "`python etl/01_download_microdados.py --glebas 2026` e depois "
            "`python etl/06_build_glebas.py --anos 2026`.",
            icon="📐",
        )
    else:
        cobertura = glebas["ref_bacen"].nunique() / max(len(base.carteira), 1)
        divergentes = float((glebas["divergencia_area_pct"] > 25).mean())
        linha_metricas([
            ("Glebas georreferenciadas", inteiro(len(glebas)),
             f"{glebas['cd_ibge'].nunique()} municípios"),
            ("Cobertura da carteira", f"{cobertura * 100:.0f}%",
             "operações com geometria publicada"),
            ("Área total desenhada", hectares(float(glebas["area_gleba_ha"].sum())), ""),
            ("Divergência de área > 25%", f"{divergentes * 100:.1f}%",
             "declarado x polígono"),
        ])
        st.write("")
        colorir = st.selectbox(
            "Colorir por", [c for c in ("cultura", "uf") if c in glebas.columns],
            key="glebas_cor",
        )
        st.plotly_chart(
            maps.mapa_glebas(glebas, altura=altura_mapa(), colorir_por=colorir),
            **largura_total(),
        )
        rodape_fonte(
            "Cada ponto é o centroide de um polígono de gleba; o tamanho "
            "representa a área. A divergência entre a área declarada no Sicor e "
            "a área calculada do polígono não invalida a gleba — é um indicador "
            "de qualidade útil para perícia e subscrição."
        )
        with st.expander("Tabela de glebas"):
            tabela(glebas.head(2000), altura=420)
            botao_download(glebas, "glebas")

# ==========================================================================
with aba_expo:
    st.markdown("##### Dinheiro em risco, não apenas hectares")
    st.caption(
        "Saldo devedor, saldo vencido e renegociação por operação, vindos de "
        "`SICOR_SALDOS`, `SICOR_LIBERACAO_RECURSOS` e "
        "`SICOR_LISTA_RENEGOCIACAO`. É a unidade em que gerente de crédito, "
        "atuário e gestor público conversam entre si."
    )
    expo = base.exposicao
    if expo is None or expo.empty:
        st.info(
            "Exposição financeira não carregada. Para habilitar: "
            "`python etl/01_download_microdados.py --saldos 2026 --financeiro` "
            "e depois `python etl/07_build_exposicao.py --anos 2026`.",
            icon="💰",
        )
    else:
        saldo = float(expo["saldo_devedor"].sum())
        vencido = float(expo["saldo_vencido"].sum())
        linha_metricas([
            ("Saldo devedor", reais_compacto(saldo), f"{inteiro(len(expo))} operações"),
            ("Saldo vencido", reais_compacto(vencido),
             f"{vencido / saldo * 100:.2f}% da carteira" if saldo else "—"),
            ("Operações em atraso", inteiro(int((expo["dias_em_atraso"] > 0).sum())), ""),
            ("Renegociadas", inteiro(int(expo["renegociada"].astype(bool).sum())),
             f"{expo['renegociada'].astype(bool).mean() * 100:.1f}% da carteira"),
        ])
        st.write("")
        geo_mun = base.municipios[["cd_ibge", "municipio", "uf", "lat", "lon"]]
        por_mun = (
            expo.groupby("cd_ibge", as_index=False)
            .agg(saldo_devedor=("saldo_devedor", "sum"),
                 saldo_vencido=("saldo_vencido", "sum"))
            .merge(geo_mun, on="cd_ibge", how="inner")
        )
        st.plotly_chart(maps.mapa_exposicao(por_mun, altura=altura_mapa()),
                        **largura_total())
        rodape_fonte(
            "Tamanho: saldo devedor. Cor: participação do saldo vencido — "
            "verde até 5%, vermelho acima de 35%."
        )
        with st.expander("Faixas de atraso"):
            faixas = (expo.groupby("faixa_atraso", as_index=False)
                          .agg(operacoes=("ref_bacen", "count"),
                               saldo=("saldo_devedor", "sum")))
            faixas["saldo"] = faixas["saldo"].map(reais_compacto)
            tabela(faixas, altura=260)
            botao_download(expo, "exposicao")

st.divider()
st.caption(f"Renderização de mapas: {maps.disponivel()['api_de_mapas']} · sem token de mapa.")
