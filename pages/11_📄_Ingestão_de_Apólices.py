"""
Projeto Final — Ingestão e extração de apólices D&O.

Recebimento dos documentos (PDF, digitalizado ou foto), extração automática
(texto/OCR → LLM), validação anti-alucinação, armazenamento estruturado e
avaliação contra o gabarito do acervo simulado.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import json  # noqa: E402

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from agrosentinela.projeto_final import avaliacao as av  # noqa: E402
from agrosentinela.projeto_final.clausulas import CLAUSULAS_POR_CODIGO  # noqa: E402
from agrosentinela.projeto_final.documentos import normalizar, ocr_disponivel  # noqa: E402
from agrosentinela.projeto_final.ui_pf import (  # noqa: E402
    arquivos_do_acervo, arquivos_reais_locais, aviso_simulacao, base_alterada, estilo_niveis,
    ler_do_acervo,
    obter_repo, orquestrador, painel_ia_lateral, rotulo_nivel,
)
from agrosentinela.ui import (  # noqa: E402
    cabecalho, configurar_pagina, largura_total, linha_metricas, tabela,
)
from agrosentinela.utils.formato import reais_compacto  # noqa: E402

configurar_pagina("Apólices D&O — Ingestão", "📄")

usar_llm = painel_ia_lateral()

cabecalho(
    "Projeto Final · Ingestão e extração de apólices D&O",
    "Documento → texto/OCR → agentes de IA → validação → base estruturada. "
    "Foco: D&O de empresas do agronegócio e do crédito rural.",
    "📄",
)
aviso_simulacao()

repo = obter_repo()
cont = repo.contagem()
ap_df = repo.apolices()
linha_metricas([
    ("Apólices na base", str(cont["apolices"]),
     f"{ap_df['seguradora'].dropna().map(normalizar).nunique() if not ap_df.empty else 0} seguradoras identificadas"),
    ("Extraídas com IA", str(int((ap_df["metodo_clausulas"] == "llm").sum()) if not ap_df.empty else 0),
     "demais: linha de base determinística"),
    ("Lidas por OCR", str(int(ap_df["metodo_leitura"].fillna("").str.contains("ocr").sum())
                          if not ap_df.empty else 0), "digitalizadas e fotos"),
    ("Confiança média", f"{ap_df['confianca'].mean():.0f}" if not ap_df.empty else "—",
     "índice do ValidacaoAgent (0–100)"),
])
st.write("")

aba_proc, aba_base, aba_aval, aba_agentes, aba_aud = st.tabs([
    "▶️ Processar documentos", "🗄️ Base estruturada", "🎯 Qualidade da extração",
    "🧩 Agentes", "📜 Auditoria",
])

# ==========================================================================
with aba_proc:
    st.markdown("##### 1. Escolha os documentos")
    reais_locais = arquivos_reais_locais()
    origem = st.radio("Origem", ["Acervo simulado", "Enviar arquivos"]
                      + (["Documentos reais (pasta local)"] if reais_locais else []),
                      horizontal=True, key="pf_origem",
                      help="Documentos reais ficam só na sua máquina, em data/apolices_reais/ "
                           "(não vão para o GitHub).")
    arquivos: list[tuple[str, bytes]] = []
    if origem.startswith("Acervo"):
        opcoes = arquivos_do_acervo()
        # sugestão: duas seguradoras de arquiteturas diferentes, uma delas digitalizada
        sugestao = ([n for n in opcoes if "-IPE-" in n and n.endswith(".pdf")
                     and "digital" not in n][:1]
                    + [n for n in opcoes if "-MUT-" in n and "_digitalizada" in n][:1])
        escolhidos = st.multiselect(
            "Arquivos do acervo (dica: inclua uma *_digitalizada* ou *_foto* para ver o OCR)",
            opcoes, default=sugestao, key="pf_sel_acervo")
        arquivos = ler_do_acervo(escolhidos) if escolhidos else []
    elif origem.startswith("Documentos reais"):
        escolhidos = st.multiselect("Documentos reais (não simulados)", sorted(reais_locais),
                                    default=sorted(reais_locais)[:1], key="pf_sel_reais")
        arquivos = [(n, reais_locais[n].read_bytes()) for n in escolhidos]
        st.caption("Condições gerais longas (50–100 páginas) levam alguns segundos a mais; "
                   "documentos de outro ramo (ex.: Seguro Garantia) são reconhecidos e recusados.")
    else:
        enviados = st.file_uploader(
            "PDF, imagens (JPG/PNG/TIFF) ou TXT — várias fotos com sufixo _p1, _p2… "
            "formam uma única apólice", type=["pdf", "png", "jpg", "jpeg", "tif", "tiff", "txt"],
            accept_multiple_files=True, key="pf_upload")
        arquivos = [(f.name, f.getvalue()) for f in (enviados or [])]

    c1, c2, c3 = st.columns(3)
    with c1:
        reprocessar = st.checkbox("Reprocessar se já estiver na base", value=True, key="pf_rep")
    with c2:
        permitir_ocr = st.checkbox("Permitir OCR", value=True, key="pf_ocr",
                                   disabled=not ocr_disponivel(),
                                   help="Tesseract instalado" if ocr_disponivel()
                                   else "Tesseract não encontrado neste servidor")
    with c3:
        st.caption(("🤖 Extração **com IA (Groq)**" if usar_llm else
                    "⚙️ Extração **determinística** (sem chave Groq)") +
                   " · OCR leva ~8 s por página digitalizada.")

    if st.button("▶️ Executar pipeline de ingestão", type="primary",
                 disabled=not arquivos, key="pf_exec"):
        orq = orquestrador()
        with st.status("Executando agentes…", expanded=True) as status:
            def _prog(agente):
                st.write(f"⏳ **{agente.nome}** — {agente.papel}")
            ctx = orq.ingerir(arquivos, usar_llm=usar_llm, permitir_ocr=permitir_ocr,
                              reprocessar=reprocessar, progresso=_prog)
            for e in ctx.rastro:
                st.write(f"{'✅' if e.sucesso else '❌'} **{e.agente}** ({e.duracao_s:.1f}s) — {e.resumo}")
            status.update(label=f"Ingestão concluída em {ctx.duracao_total_s:.1f}s",
                          state="complete" if all(e.sucesso for e in ctx.rastro) else "error",
                          expanded=False)
        st.session_state["pf_ultimo_ctx"] = ctx
        base_alterada()

    ctx = st.session_state.get("pf_ultimo_ctx")
    if ctx is not None:
        for a in ctx.avisos:
            st.warning(a, icon="⚠️")
        # recusados e ignorados primeiro, para o aviso não ficar escondido
        for it in sorted(ctx.itens, key=lambda i: not i.ignorado):
            if it.ignorado:
                if it.ignorado.startswith("fora do escopo"):
                    st.warning(f"🚫 **{it.ident}** — {it.ignorado}")
                    if it.tipo is not None and it.tipo.sinais:
                        st.caption("Sinais encontrados no texto: " + "; ".join(it.tipo.sinais[:4]))
                else:
                    st.info(f"**{it.ident}** — {it.ignorado}")
                continue
            if it.erro:
                st.error(f"**{it.ident}** — {it.erro}")
                continue
            cad = it.extracao.cadastro
            with st.expander(f"📑 {it.ident} — {cad.get('seguradora') or '?'} · "
                             f"confiança {it.validacao.confianca if it.validacao else '—'}",
                             expanded=True):
                k1, k2, k3, k4 = st.columns(4)
                def _v(x):
                    return reais_compacto(x) if x else "—"
                k1.metric("LMG", _v(cad.get("lmg")))
                k2.metric("Prêmio", _v(cad.get("premio")))
                k3.metric("Franquia", _v(cad.get("franquia")))
                k4.metric("Leitura", it.doc.metodo_resumo,
                          f"OCR {it.doc.confianca_ocr_media}" if it.doc.confianca_ocr_media else None)
                if it.tipo is not None:
                    st.caption(f"Documento: **{it.tipo.resumo()}**")
                st.caption(f"Cadastro: **{it.extracao.metodo_cadastro}** · cláusulas: "
                           f"**{it.extracao.metodo_clausulas}** "
                           f"{('· modelo ' + it.extracao.modelo) if it.extracao.modelo else ''} · "
                           f"{len(it.secoes)} seções identificadas")
                st.json({k: (str(v) if v is not None else None) for k, v in cad.items()},
                        expanded=False)
                linhas = [{
                    "código": c.codigo, "cláusula": CLAUSULAS_POR_CODIGO[c.codigo].nome,
                    "nível": rotulo_nivel(c.nivel), "seção": c.secao,
                    "evidência verificada": {True: "✔", False: "✖", None: "—"}[c.evidencia_verificada],
                    "evidência": c.evidencia[:180], "justificativa": c.justificativa[:160],
                } for c in it.extracao.clausulas.values()]
                st.dataframe(estilo_niveis(pd.DataFrame(linhas), ["nível"]),
                             hide_index=True, **largura_total())
                if it.validacao and it.validacao.alertas:
                    st.markdown("**Alertas da validação**")
                    for a in it.validacao.alertas[:15]:
                        st.caption(f"• {a}")
                if it.avaliacao:
                    st.success(
                        f"**Conferência com o gabarito** (só no acervo simulado): campos "
                        f"{it.avaliacao['acuracia_campos']}% · níveis de cláusula "
                        f"{it.avaliacao['acuracia_clausulas']}% · presença/ausência "
                        f"{it.avaliacao['acuracia_presenca']}%"
                        + (f" · divergências: {', '.join(it.avaliacao['erros_clausulas'])}"
                           if it.avaliacao["erros_clausulas"] else ""), icon="🎯")
                with st.expander("Texto extraído e seções"):
                    st.text(it.doc.texto[:6000])

# ==========================================================================
with aba_base:
    st.markdown("##### Apólices armazenadas")
    if ap_df.empty:
        st.info("Base vazia. Processe documentos na primeira aba.")
    else:
        vista = ap_df[["id", "seguradora", "tomadora", "segmento", "uf", "lmg", "premio",
                       "franquia", "retroatividade", "metodo_leitura", "metodo_clausulas",
                       "confianca"] + (["tipo_documento"] if "tipo_documento" in ap_df else [])].copy()
        tabela(vista, altura=420)
        escolha = st.selectbox("Detalhar apólice", ap_df["id"].tolist(), key="pf_det")
        if escolha:
            cl = repo.clausulas([escolha])
            cl["cláusula"] = cl["codigo"].map(lambda c: CLAUSULAS_POR_CODIGO[c].nome)
            cl["nível"] = cl["nivel"].map(rotulo_nivel)
            st.dataframe(estilo_niveis(cl[["codigo", "cláusula", "nível", "secao", "evidencia",
                                           "metodo"]], ["nível"]),
                         hide_index=True, **largura_total())
            linha = ap_df[ap_df["id"] == escolha].iloc[0]
            alertas = json.loads(linha["alertas_validacao"] or "[]")
            if alertas:
                st.caption("Alertas: " + " | ".join(alertas[:8]))
            with st.expander("Seções do texto"):
                tabela(repo.secoes(escolha)[["indice", "titulo", "texto"]], altura=360)

# ==========================================================================
with aba_aval:
    st.markdown("##### Quanto a extração automática acerta?")
    st.caption(
        "Cada apólice do acervo nasceu de uma especificação conhecida (o *gabarito*). "
        "Isso permite medir a extração campo a campo e cláusula a cláusula — e comparar "
        "o agente LLM com a linha de base determinística (dicionário + gatilhos).")
    linhas, conf = [], []
    for r in ap_df.itertuples() if not ap_df.empty else []:
        ident = av.identificador_de(r.id)
        if not ident:
            continue
        cl = repo.clausulas([r.id])
        niveis = dict(zip(cl["codigo"], cl["nivel"]))
        cad = {"lmg": r.lmg, "premio": r.premio, "franquia": r.franquia,
               "vigencia_inicio": r.vigencia_inicio, "vigencia_fim": r.vigencia_fim,
               "retroatividade": r.retroatividade,
               "retroatividade_ilimitada": bool(r.retroatividade_ilimitada), "uf": r.uf}
        res = av.avaliar(ident, cad, niveis)
        res["metodo"] = r.metodo_clausulas
        res["leitura"] = r.metodo_leitura
        linhas.append(res)
        g = av.gabarito()[ident]["avaliacoes"]
        conf += [(g[k], niveis.get(k, "ausente")) for k in g]
    if not linhas:
        st.info("Nenhuma apólice do acervo simulado na base.")
    else:
        dfa = pd.DataFrame(linhas)
        resumo = (dfa.groupby("metodo")[["acuracia_campos", "acuracia_clausulas",
                                         "acuracia_presenca"]].mean().round(1)
                  .assign(apolices=dfa.groupby("metodo").size()).reset_index())
        st.dataframe(resumo, hide_index=True, **largura_total())
        st.bar_chart(dfa.set_index("identificador")["acuracia_clausulas"])
        st.markdown("**Matriz de confusão dos níveis (linhas = gabarito, colunas = extraído)**")
        st.dataframe(av.matriz_confusao(conf), **largura_total())
        st.caption("Para gerar a avaliação com IA de todo o acervo: "
                   "`python scripts/processar_acervo.py --llm --pausa 20` (ver README).")
        tabela(dfa.drop(columns=["erros_campos"]), altura=360)

# ==========================================================================
with aba_agentes:
    st.markdown("##### Arquitetura multiagente do Projeto Final")
    st.code(
        "INGESTÃO   RecepcaoAgent → LeituraOCRAgent → CadastroAgent (LLM) → ClausulasAgent (LLM)\n"
        "           → ValidacaoAgent → ArmazenamentoAgent (SQLite)\n"
        "COMPARAÇÃO PerfilRiscoAgent (Sicor/Proagro) → ComparadorAgent (regras) → RelatorAgent (LLM)\n"
        "CONSULTA   ConsultaAgent (LLM + 6 ferramentas sobre a base)", language="text")
    tabela(pd.DataFrame(orquestrador().fichas()), altura=420)

with aba_aud:
    st.markdown("##### Rastro de auditoria (últimos eventos)")
    tabela(repo.auditoria(300), altura=480)
