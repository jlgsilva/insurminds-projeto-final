"""Copiloto IA — pergunta e resposta sobre a carteira, os alertas e o Proagro."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from agrosentinela.agents.copiloto import CopilotoAgent  # noqa: E402
from agrosentinela.llm.groq_client import GroqClient  # noqa: E402
from agrosentinela.ui import (  # noqa: E402
    barra_lateral,
    base_atual,
    cabecalho,
    colunas,
    configurar_pagina,
    largura_total,
    obter_motor,
    tabela,
)

configurar_pagina("Copiloto IA", "🤖")
barra_lateral(mostrar_execucao=False)

cabecalho(
    "Copiloto IA",
    "Pergunte em português sobre a carteira do Sicor, os alertas da execução "
    "atual e o histórico do Proagro.",
    "🤖",
)

base = base_atual()
res = st.session_state.get("resultado")
cliente = GroqClient()

st.info(
    """
**Como este copiloto evita inventar número.** O modelo de linguagem não vê a
base de dados: ele escolhe **qual consulta fazer** e com **quais parâmetros**
(*function calling*); quem calcula é o pandas. O modelo recebe de volta
apenas o resultado já apurado e o transforma em texto. Toda resposta mostra
as ferramentas chamadas e os argumentos usados, para conferência.
    """,
    icon="🔍",
)

if not cliente.disponivel:
    st.warning(
        "Sem `GROQ_API_KEY` configurada, o copiloto funciona em **modo "
        "determinístico**: interpreta a pergunta por palavras-chave, executa a "
        "consulta e devolve a tabela apurada, sem redação por IA.",
        icon="ℹ️",
    )

copiloto = CopilotoAgent(
    carteira=res.contexto.carteira if res is not None else base.carteira,
    alertas=res.alertas_df if res is not None else pd.DataFrame(),
    sinistros=base.proagro_sinistros,
    indicadores=res.contexto.indicadores if res is not None else pd.DataFrame(),
    municipios=base.municipios,
    cliente=cliente,
    motor=obter_motor(),
    origem_dados=base.origem,
)

if res is None:
    st.caption(
        "Nenhuma execução nesta sessão: o copiloto responderá sobre a carteira e "
        "o histórico do Proagro, mas não sobre alertas."
    )

# ==========================================================================
# Sugestões
# ==========================================================================
st.markdown("##### Sugestões de pergunta")
sugestoes = CopilotoAgent.sugestoes()
faixas = colunas(4)
pergunta_clicada = None
for i, s in enumerate(sugestoes):
    with faixas[i % len(faixas)]:
        if st.button(s, key=f"sug_{i}", **largura_total()):
            pergunta_clicada = s

# ==========================================================================
# Conversa
# ==========================================================================
if "chat_copiloto" not in st.session_state:
    st.session_state["chat_copiloto"] = []

for item in st.session_state["chat_copiloto"]:
    with st.chat_message(item["role"]):
        st.markdown(item["content"])
        for tabela_resultado in item.get("tabelas", []):
            st.dataframe(tabela_resultado, **largura_total(), hide_index=True)
        if item.get("ferramentas"):
            with st.expander("Ferramentas chamadas"):
                for f in item["ferramentas"]:
                    st.markdown(f"- `{f['nome']}` → {f['linhas']} linha(s)")
                    st.json(f["argumentos"], expanded=False)
                    if f.get("erro"):
                        st.error(f["erro"])

pergunta = st.chat_input("Pergunte sobre a carteira, os alertas ou o Proagro…")
pergunta = pergunta or pergunta_clicada

if pergunta:
    st.session_state["chat_copiloto"].append({"role": "user", "content": pergunta})
    with st.chat_message("user"):
        st.markdown(pergunta)

    with st.chat_message("assistant"):
        with st.spinner("Consultando os dados…"):
            historico = [
                {"role": m["role"], "content": m["content"]}
                for m in st.session_state["chat_copiloto"][:-1]
            ]
            resposta = copiloto.perguntar(pergunta, historico)
        st.markdown(resposta.texto)
        for t in resposta.tabelas:
            st.dataframe(t, **largura_total(), hide_index=True)
        if resposta.ferramentas:
            with st.expander("Ferramentas chamadas"):
                for f in resposta.ferramentas:
                    st.markdown(f"- `{f.nome}` → {f.linhas} linha(s)")
                    st.json(f.argumentos, expanded=False)
                    if f.erro:
                        st.error(f.erro)
        rodape = (
            f"modo: {resposta.modo}"
            + (f" · modelo: {resposta.modelo}" if resposta.modelo else "")
            + f" · base: {base.origem}"
        )
        st.caption(rodape)
        if resposta.erro:
            st.caption(f"⚠️ {resposta.erro}")

    st.session_state["chat_copiloto"].append(
        {
            "role": "assistant",
            "content": resposta.texto,
            "tabelas": resposta.tabelas,
            "ferramentas": [
                {"nome": f.nome, "argumentos": f.argumentos, "linhas": f.linhas, "erro": f.erro}
                for f in resposta.ferramentas
            ],
        }
    )

if st.session_state["chat_copiloto"]:
    if st.button("🧹 Limpar conversa"):
        st.session_state["chat_copiloto"] = []
        st.rerun()

# ==========================================================================
with st.expander("Ferramentas disponíveis ao copiloto"):
    st.markdown(
        """
| Ferramenta | O que faz |
|---|---|
| `consultar_carteira` | Agrega a carteira do Sicor por UF, município, cultura, programa, instituição, persona, safra… |
| `consultar_alertas` | Consulta os alertas da execução atual por evento, severidade, município, cultura ou regra |
| `consultar_proagro` | Histórico de pedidos de cobertura e comprovações de perdas por município, cultura e evento |
| `consultar_clima` | Indicadores meteorológicos calculados para um município |
| `explicar_regra` | Devolve a definição completa de uma regra pelo identificador (ex.: `R-SEC-01`) |

O modelo pode encadear até quatro chamadas antes de responder. O resultado de
cada chamada é truncado em 25 linhas antes de voltar ao modelo — o que
protege a janela de contexto e a cota da camada gratuita.
        """
    )
