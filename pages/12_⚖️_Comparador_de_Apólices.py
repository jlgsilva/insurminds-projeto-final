"""
Projeto Final — Comparação de apólices D&O.

Perfil de risco da tomadora (Sicor/Proagro) → comparação determinística
cláusula a cláusula → relatório redigido por IA para o público escolhido.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from agrosentinela.projeto_final import comparador as cp  # noqa: E402
from agrosentinela.projeto_final.clausulas import CLAUSULAS_POR_CODIGO, criticas  # noqa: E402
from agrosentinela.projeto_final.relator import PUBLICOS  # noqa: E402
from agrosentinela.projeto_final.ui_pf import (  # noqa: E402
    aviso_simulacao, estilo_niveis, escores, obter_repo, orquestrador, painel_ia_lateral,
)
from agrosentinela.ui import (  # noqa: E402
    cabecalho, configurar_pagina, largura_total, linha_metricas, tabela,
)
from agrosentinela.utils.formato import reais_compacto  # noqa: E402

configurar_pagina("Comparador de Apólices", "⚖️")

usar_llm = painel_ia_lateral()

cabecalho(
    "Projeto Final · Comparador de apólices D&O",
    "As regras comparam; a IA explica. Pesos ajustados ao perfil de crédito rural "
    "da tomadora (microdados do Sicor e do Proagro).",
    "⚖️",
)
aviso_simulacao()

repo = obter_repo()
ap = repo.apolices()
if ap.empty or len(ap) < 2:
    st.warning("São necessárias ao menos duas apólices na base. Use a página "
               "**Ingestão de Apólices**.")
    st.stop()

ap = ap.merge(escores(), on="id", how="left")

# ---------------------------------------------------------------- seleção
st.markdown("##### 1. Quais apólices comparar?")
modo = st.radio("Seleção", ["Cotações de uma mesma tomadora", "Escolha livre"],
                horizontal=True, key="pf_modo_sel")
if modo.startswith("Cotações"):
    # A mesma tomadora pode ter sido lida com grafias diferentes em cada
    # apólice (cada seguradora escreve de um jeito; OCR erra). Agrupa pelo
    # CNPJ quando existe e, senão, pelo nome normalizado.
    from agrosentinela.projeto_final.documentos import normalizar

    # união: apólices com o mesmo CNPJ OU o mesmo nome são da mesma tomadora
    pai: dict[str, str] = {}

    def _raiz(x: str) -> str:
        while pai.setdefault(x, x) != x:
            x = pai[x]
        return x

    chaves = []
    for r in ap.itertuples():
        nome = r.tomadora if isinstance(r.tomadora, str) and r.tomadora.strip() else None
        cnpj = "".join(ch for ch in str(r.tomadora_cnpj or "") if ch.isdigit())
        ks = ([f"n:{normalizar(nome)}"] if nome else []) + ([f"c:{cnpj}"] if len(cnpj) == 14 else [])
        for k in ks[1:]:
            pai[_raiz(k)] = _raiz(ks[0])
        chaves.append(ks[0] if ks else None)
    ap["chave_tom"] = [(_raiz(k) if k else None) for k in chaves]
    nome_tom = (ap.dropna(subset=["tomadora"]).groupby("chave_tom")["tomadora"]
                .agg(lambda x: x.value_counts().index[0]).to_dict())
    contagem = ap["chave_tom"].dropna().value_counts()
    tomadoras = [k for k in contagem.index if contagem[k] >= 2]
    padrao_tom = next((i for i, k in enumerate(tomadoras) if "Grão Norte" in nome_tom.get(k, "")), 0)
    tom = st.selectbox("Tomadora", tomadoras, index=padrao_tom, key="pf_tom",
                       format_func=lambda k: f"{nome_tom.get(k, k)} ({contagem[k]} cotações)")
    padrao = ap[ap["chave_tom"] == tom]["id"].tolist()
    ids = st.multiselect("Apólices (cotações recebidas)", ap["id"].tolist(), default=padrao,
                         key=f"pf_ids_{tom}")
else:
    ids = st.multiselect("Apólices", ap["id"].tolist(), default=ap["id"].tolist()[:2],
                         key="pf_ids_livre")

c1, c2 = st.columns([2, 1])
with c1:
    publico = st.selectbox("Relatório para", [p.codigo for p in PUBLICOS],
                           format_func=lambda c: next(p.nome for p in PUBLICOS if p.codigo == c),
                           key="pf_publico")
with c2:
    ajustar = st.checkbox("Ajustar pesos ao perfil da tomadora (Sicor)", value=True,
                          key="pf_ajustar")

if st.button("⚖️ Comparar", type="primary", disabled=len(ids) < 2, key="pf_comparar"):
    with st.status("Executando agentes de comparação…", expanded=True) as status:
        ctx = orquestrador().comparar(ids, publico=publico, usar_llm=usar_llm,
                                      ajustar_por_perfil=ajustar)
        for e in ctx.rastro:
            st.write(f"{'✅' if e.sucesso else '❌'} **{e.agente}** ({e.duracao_s:.1f}s) — {e.resumo}")
        status.update(label=f"Comparação concluída em {ctx.duracao_total_s:.1f}s",
                      state="complete", expanded=False)
    st.session_state["pf_comp_ctx"] = ctx

ctx = st.session_state.get("pf_comp_ctx")
if ctx is None or ctx.comparacao is None:
    st.info("Escolha as apólices e clique em **Comparar**.")
    st.stop()

comp = ctx.comparacao
for a in ctx.avisos:
    st.warning(a, icon="⚠️")
r = comp.resumo()
linha_metricas([
    ("Apólices", str(r["apolices_comparadas"]), ", ".join(ctx.ids_comparacao)[:60]),
    ("Melhor escore geral", r["melhor_escore_geral"],
     f"{comp.vencedora_geral.escore()} pontos"),
    ("Melhor nas críticas", r["melhor_nas_clausulas_criticas"],
     f"{comp.vencedora_criticas.escore(True)} pontos em {len(criticas())} cláusulas"),
    ("Lacunas críticas", str(r["lacunas_criticas"]), f"{r['lacunas']} lacunas no total"),
])
if comp.divergencia_de_leitura:
    st.warning(
        f"**A melhor no escore geral ({r['melhor_escore_geral']}) não é a melhor nas cláusulas "
        f"críticas ({r['melhor_nas_clausulas_criticas']}).** O ranking simples levaria à decisão "
        "errada — veja as abas *Cláusulas críticas* e *Lacunas*.", icon="⚠️")

abas = st.tabs(["📝 Relatório (IA)", "🏁 Placar", "⭐ Cláusulas críticas", "🔀 Diferenças",
                "🕳️ Lacunas", "🌾 Perfil da tomadora", "🧾 Rastro"])

with abas[0]:
    rel = ctx.relatorio
    if rel:
        st.caption(f"Gerado por: **{'IA — ' + rel.modelo if rel.metodo == 'llm' else 'modelo de texto (sem IA)'}**"
                   + (f" · {len(rel.numeros_nao_verificados)} número(s) sinalizados pelo verificador"
                      if rel.numeros_nao_verificados else " · todos os números conferidos com os fatos"))
        st.markdown(rel.texto)
        st.download_button("⬇️ Baixar relatório (.md)", rel.texto.encode("utf-8"),
                           file_name=f"relatorio_comparativo_{'_'.join(ctx.ids_comparacao)[:60]}.md",
                           mime="text/markdown", key="pf_dl_rel")

with abas[1]:
    placar = pd.DataFrame([{**a.to_row(), "tomadora": a.tomadora, "método": a.metodo,
                            "confiança extração": a.confianca} for a in comp.apolices])
    for c in ("LMG", "prêmio", "franquia", "prêmio por ponto"):
        placar[c] = placar[c].map(reais_compacto)
    tabela(placar, altura=260)
    st.markdown("**Escore por grupo de cláusulas**")
    st.bar_chart(pd.DataFrame({a.identificador: a.escore_por_grupo() for a in comp.apolices}))
    st.caption("Escore 0–100 ponderado pela criticidade da cláusula (e pelo perfil da "
               "tomadora, se ativado). «Prêmio por ponto» torna comparável o que a "
               "proposta comercial apresenta separado.")

with abas[2]:
    linhas = []
    for c in criticas():
        linha = {"código": c.codigo, "cláusula": c.nome,
                 "peso efetivo": comp.apolices[0].peso(c)}
        for a in comp.apolices:
            linha[a.identificador] = cp.ROTULO_NIVEL.get(a.nivel(c.codigo))
        linhas.append(linha)
    df = pd.DataFrame(linhas)
    st.dataframe(estilo_niveis(df, [a.identificador for a in comp.apolices]),
                 hide_index=True, **largura_total())

with abas[3]:
    dif = cp.diferencas_relevantes(comp)
    if dif:
        dfd = pd.DataFrame(dif)
        st.dataframe(estilo_niveis(dfd, [a.identificador for a in comp.apolices]),
                     hide_index=True, **largura_total())
    else:
        st.info("Sem divergências relevantes.")
    st.markdown("**Evidências literais (o que cada apólice diz)**")
    cod = st.selectbox("Cláusula", [d["código"] for d in dif] or list(CLAUSULAS_POR_CODIGO),
                       format_func=lambda c: f"{c} — {CLAUSULAS_POR_CODIGO[c].nome}",
                       key="pf_ev_cod")
    for a in comp.apolices:
        st.markdown(f"**{a.identificador}** · {cp.ROTULO_NIVEL.get(a.nivel(cod))}")
        st.caption(a.observacoes.get(cod) or "— cláusula não encontrada no documento —")

with abas[4]:
    if comp.lacunas:
        lac = pd.DataFrame([l.to_row() for l in comp.lacunas])
        grav = st.multiselect("Gravidade", ["critica", "alta", "media"],
                              default=["critica", "alta"], key="pf_grav")
        tabela(lac[lac["gravidade"].isin(grav)] if grav else lac, altura=460)
    else:
        st.success("Nenhuma lacuna.")

with abas[5]:
    p = ctx.perfil
    if p:
        st.markdown(f"**{p.tomadora}** · {p.segmento} · UF **{p.uf}**")
        ind = {k: v for k, v in p.indicadores.items() if k not in ("uf",)}
        st.json(ind, expanded=True)
        if p.ajustes:
            tabela(pd.DataFrame([{"código": a.codigo,
                                  "cláusula": CLAUSULAS_POR_CODIGO[a.codigo].nome,
                                  "fator": a.fator, "motivo": a.motivo} for a in p.ajustes]),
                   altura=300)
        st.caption("Indicadores calculados sobre a base do AgroSentinela (Desafio 5): operações "
                   "de crédito rural do Sicor, acionamento do Proagro e saldos em atraso na UF.")

with abas[6]:
    tabela(ctx.rastro_df(), altura=260)
