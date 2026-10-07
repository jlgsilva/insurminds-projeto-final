"""
Projeto Final — Consulta em linguagem natural sobre a base de apólices.

O ConsultaAgent (LLM com *tool calling*) decide quais consultas executar na
base estruturada e responde só com o que elas devolveram.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import streamlit as st  # noqa: E402

from agrosentinela.projeto_final.consulta import AgenteConsulta  # noqa: E402
from agrosentinela.projeto_final.ui_pf import (  # noqa: E402
    aviso_simulacao, cliente_sessao, escores, obter_repo, painel_ia_lateral,
)
from agrosentinela.ui import cabecalho, configurar_pagina, tabela  # noqa: E402

configurar_pagina("Consulta às Apólices", "💬")

usar_llm = painel_ia_lateral()

cabecalho(
    "Projeto Final · Consulta às apólices em linguagem natural",
    "Pergunte sobre coberturas, limites, seguradoras e cláusulas. O agente consulta "
    "a base estruturada por meio de ferramentas e mostra as tabelas que usou.",
    "💬",
)
aviso_simulacao()

SUGESTOES = [
    "Quais apólices pagam custos de defesa fora do LMG (DEF-01 ampla) com LMG de pelo menos R$ 20 milhões?",
    "Qual seguradora oferece, em média, a melhor cobertura para atos de gestão em crédito rural (AGR-01)?",
    "Entre as cotações da Agropecuária Matopiba, qual tem o menor prêmio por ponto de escore?",
    "Quais apólices excluem multas e penalidades?",
    "Mostre o que a apólice AP001 diz sobre retroatividade.",
    "Quais cooperativas de crédito rural têm cobertura de Side A com limite adicional?",
    "Quais apólices de tomadoras da Amazônia Legal excluem danos ambientais (EXC-03)?",
]

agente = AgenteConsulta(obter_repo(), cliente_sessao(), escores())
if not usar_llm:
    agente.cliente = None  # força o modo determinístico quando a IA está desligada
    st.caption("IA desligada: respostas por roteamento simples de palavras-chave.")

hist = st.session_state.setdefault("pf_chat", [])
with st.expander("💡 Exemplos de perguntas", expanded=not hist):
    for i, s in enumerate(SUGESTOES):
        if st.button(s, key=f"pf_sug_{i}"):
            st.session_state["pf_pergunta_pendente"] = s

for m in hist:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        for nome, df in m.get("tabelas", []):
            st.caption(f"🔧 ferramenta: `{nome}`")
            tabela(df, altura=240)

pergunta = st.chat_input("Pergunte sobre as apólices…") or st.session_state.pop(
    "pf_pergunta_pendente", None)
if pergunta:
    with st.chat_message("user"):
        st.markdown(pergunta)
    with st.chat_message("assistant"):
        with st.spinner("Consultando a base…"):
            resp = agente.perguntar(pergunta, [{"role": m["role"], "content": m["content"]}
                                              for m in hist])
        st.markdown(resp.texto)
        if resp.erro:
            st.caption(f"⚠️ IA indisponível ({resp.erro[:160]}) — resposta em modo determinístico.")
        for ch in resp.ferramentas:
            st.caption(f"🔧 `{ch.nome}({ch.argumentos})`" + (f" — erro: {ch.erro}" if ch.erro else ""))
        for nome, df in resp.tabelas:
            tabela(df, altura=240)
    hist += [{"role": "user", "content": pergunta},
             {"role": "assistant", "content": resp.texto, "tabelas": resp.tabelas[:2]}]

if hist and st.button("🧹 Limpar conversa", key="pf_limpar"):
    st.session_state["pf_chat"] = []
    st.rerun()
