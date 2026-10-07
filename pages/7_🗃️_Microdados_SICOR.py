"""Explorador dos microdados e das tabelas de domínio do Sicor."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from agrosentinela.config import CURATED_DIR, SEED_DIR  # noqa: E402
from agrosentinela.data.schemas import DATASETS, resumo_dataset  # noqa: E402
from agrosentinela.etl_catalogo import CATALOGO_BCB, por_secao  # noqa: E402
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
from agrosentinela.utils.formato import hectares, inteiro, pct, reais_compacto  # noqa: E402
from agrosentinela.viz import charts  # noqa: E402

configurar_pagina("Microdados Sicor", "🗃️")
barra_lateral(mostrar_execucao=False)

cabecalho(
    "Microdados do Crédito Rural e do Proagro",
    "Exploração das tabelas curadas a partir da base do Banco Central.",
    "🗃️",
)

base = base_atual()

aba_explorar, aba_series, aba_esquema, aba_fontes = st.tabs(
    ["🔎 Explorar", "📈 Séries históricas", "🧬 Esquema dos dados", "🏦 Catálogo do BCB"]
)

# ==========================================================================
with aba_explorar:
    conjuntos = base.como_dict()
    nome = st.selectbox(
        "Conjunto de dados", list(conjuntos.keys()),
        format_func=lambda n: {
            "carteira": "Carteira — operações de crédito rural",
            "municipios": "Municípios — referência geográfica e alíquotas",
            "proagro_sinistros": "Proagro — histórico de COP e RCP",
            "serie_credito": "Série histórica de contratações",
        }.get(n, n),
        key="explorar_ds",
    )
    df = conjuntos[nome]
    if df.empty:
        st.warning("Conjunto vazio.")
    else:
        info = resumo_dataset(df)
        linha_metricas([
            ("Linhas", inteiro(info["linhas"]), ""),
            ("Colunas", inteiro(info["colunas"]), ""),
            ("Memória", f"{info['memoria_mb']} MB", ""),
            ("Células vazias", pct(info["nulos_pct"]), ""),
        ])
        st.write("")

        # ------------------------------------------------------- filtros
        with st.expander("Filtros", expanded=True):
            colunas_filtraveis = [
                c for c in df.columns
                if df[c].dtype == object or str(df[c].dtype) == "string"
            ][:8]
            filtros: dict[str, list] = {}
            cols = colunas(min(4, max(1, len(colunas_filtraveis))))
            for i, coluna in enumerate(colunas_filtraveis[:4]):
                valores = sorted(df[coluna].dropna().astype(str).unique().tolist())
                if 1 < len(valores) <= 300:
                    with cols[i % len(cols)]:
                        sel = st.multiselect(coluna, valores, key=f"flt_{nome}_{coluna}")
                        if sel:
                            filtros[coluna] = sel
            texto = st.text_input("Busca livre (qualquer coluna de texto)",
                                  key=f"busca_{nome}")

        sel = df
        for coluna, valores in filtros.items():
            sel = sel[sel[coluna].astype(str).isin(valores)]
        if texto:
            alvo = texto.lower()
            mascara = pd.Series(False, index=sel.index)
            for coluna in sel.columns:
                if sel[coluna].dtype == object or str(sel[coluna].dtype) == "string":
                    mascara |= sel[coluna].astype(str).str.lower().str.contains(alvo, na=False)
            sel = sel[mascara]

        st.caption(f"{inteiro(len(sel))} de {inteiro(len(df))} linhas.")
        tabela(sel.head(3000), altura=480)
        botao_download(sel, f"sicor_{nome}")

        # ------------------------------------------ estatística descritiva
        with st.expander("Estatística descritiva das colunas numéricas"):
            numericas = sel.select_dtypes("number")
            if numericas.empty:
                st.info("Nenhuma coluna numérica.")
            else:
                st.dataframe(numericas.describe().T, **largura_total())

        if nome == "carteira" and not sel.empty:
            col1, col2 = colunas(2, gap="large")
            with col1:
                st.plotly_chart(charts.composicao_carteira(sel, "cultura"),
                                **largura_total())
            with col2:
                st.plotly_chart(charts.composicao_carteira(sel, "uf"),
                                **largura_total())

# ==========================================================================
with aba_series:
    serie = base.serie_credito
    if serie.empty:
        st.warning("Série histórica não disponível nesta base.")
    else:
        col1, col2 = colunas([1, 3])
        with col1:
            por = st.radio("Agrupar por", ["cultura", "uf"], key="serie_por")
            top = st.slider("Séries exibidas", 3, 12, 6, key="serie_top")
        with col2:
            st.plotly_chart(charts.serie_credito_anual(serie, por, top),
                            **largura_total())

        resumo_ano = (
            serie.groupby("ano", as_index=False)
            .agg(operacoes=("n_operacoes", "sum"),
                 valor=("valor_credito", "sum"),
                 area=("area_ha", "sum"))
        )
        resumo_ano["valor"] = resumo_ano["valor"].map(reais_compacto)
        resumo_ano["area"] = resumo_ano["area"].map(hectares)
        resumo_ano["operacoes"] = resumo_ano["operacoes"].map(inteiro)
        resumo_ano.columns = ["Ano", "Operações", "Valor contratado", "Área"]
        tabela(resumo_ano, altura=420)
        botao_download(serie, "serie_credito")

# ==========================================================================
with aba_esquema:
    st.markdown(
        """
Os conjuntos curados seguem um esquema canônico. O ETL do Banco Central e o
gerador de demonstração produzem **exatamente as mesmas colunas** — é isso
que permite trocar a fonte sem alterar uma linha da aplicação.
        """
    )
    for ds in DATASETS:
        with st.expander(f"**{ds.nome}** — {ds.descricao}"):
            st.caption(f"Origem no BCB: {ds.origem_bcb}")
            st.dataframe(
                pd.DataFrame(
                    [{"coluna": c, "tipo": t} for c, t in ds.colunas.items()]
                ),
                **largura_total(), hide_index=True, height=min(420, 40 + 35 * len(ds.colunas)),
            )

    st.markdown("#### Procedência da base carregada")
    st.json(
        {
            "origem": base.origem,
            "arquivos": base.detalhes_origem,
            "diretorio_curado": str(CURATED_DIR),
            "diretorio_demonstracao": str(SEED_DIR),
            "manifesto": base.manifesto,
            "problemas_de_validacao": base.problemas,
            "carregado_em": base.carregado_em,
        },
        expanded=False,
    )

# ==========================================================================
with aba_fontes:
    st.markdown(
        """
Catálogo dos arquivos publicados pelo Banco Central em
[Tabelas e Microdados do Crédito Rural e do Proagro](https://www.bcb.gov.br/estabilidadefinanceira/tabelas-credito-rural-proagro).

O ETL (`etl/`) baixa, valida (hash quando disponível) e transforma esses
arquivos nos conjuntos curados. Os marcados como **usado** são os que
alimentam diretamente o AgroSentinela.
        """
    )
    catalogo = pd.DataFrame([c.to_row() for c in CATALOGO_BCB])
    secoes = ["(todas)"] + sorted(catalogo["seção"].unique().tolist())
    sec = st.selectbox("Seção", secoes, key="cat_secao")
    somente_usados = st.checkbox("Somente arquivos usados pela solução", value=False)

    sel = catalogo if sec == "(todas)" else catalogo[catalogo["seção"] == sec]
    if somente_usados:
        sel = sel[sel["usado"] == "sim"]
    st.caption(f"{len(sel)} arquivos.")
    st.dataframe(
        sel, **largura_total(), hide_index=True, height=560,
        column_config={"url": st.column_config.LinkColumn("url", display_text="abrir")},
    )
    botao_download(catalogo, "catalogo_bcb_sicor")
