"""Central de comunicação — mensagens geradas, envios simulados e personas."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from agrosentinela.personas import (  # noqa: E402
    LIMITE_CANAL,
    PERSONAS,
    PERSONAS_POR_CODIGO,
)
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
    obter_outbox,
    render_mensagem,
    rodape_fonte,
    tabela,
)
from agrosentinela.utils.formato import inteiro, num, pct, reais  # noqa: E402
from agrosentinela.viz import charts, maps  # noqa: E402
from agrosentinela.viz.theme import ROTULO_SEVERIDADE  # noqa: E402

configurar_pagina("Central de Comunicação", "💬")
barra_lateral(mostrar_execucao=False)

cabecalho(
    "Central de Comunicação",
    "As mensagens geradas automaticamente, por persona e por canal, e a "
    "simulação do despacho.",
    "💬",
)

aba_msgs, aba_envios, aba_personas, aba_hist = st.tabs(
    ["✉️ Mensagens geradas", "📤 Simulação de envio", "👥 Personas", "🗄️ Caixa de saída"]
)

# ==========================================================================
with aba_msgs:
    res = exigir_execucao()
    if res is not None:
        mensagens = res.contexto.mensagens
        if not mensagens:
            st.info("Nenhuma mensagem gerada nesta execução.")
        else:
            df = res.mensagens_df
            por_llm = int((df["gerado_por"] == "llm").sum())
            fora = int((~df["dentro_do_limite"]).sum())
            linha_metricas([
                ("Mensagens", inteiro(len(df)),
                 f"{df['persona'].nunique()} personas · {df['canal'].nunique()} canais"),
                ("Por IA Generativa", inteiro(por_llm),
                 f"{len(df) - por_llm} por template determinístico"),
                ("Tamanho médio", f"{df['caracteres'].mean():.0f} car.",
                 f"{fora} fora do limite do canal"),
                ("Críticas", inteiro(int((df["severidade"] == "critico").sum())),
                 f"score médio {df['score'].mean():.0f}"),
            ])
            st.write("")

            col1, col2, col3 = colunas(3)
            with col1:
                f_persona = st.multiselect(
                    "Persona", sorted(df["persona"].unique()),
                    format_func=lambda c: PERSONAS_POR_CODIGO[c].nome
                    if c in PERSONAS_POR_CODIGO else c,
                    key="msg_persona",
                )
            with col2:
                f_canal = st.multiselect("Canal", sorted(df["canal"].unique()), key="msg_canal")
            with col3:
                f_sev = st.multiselect(
                    "Severidade", ["critico", "alerta", "atencao", "informativo"],
                    format_func=lambda s: ROTULO_SEVERIDADE.get(s, s), key="msg_sev",
                )

            selecionadas = [
                m for m in mensagens
                if (not f_persona or m.persona in f_persona)
                and (not f_canal or m.canal in f_canal)
                and (not f_sev or m.severidade in f_sev)
            ]
            st.caption(f"{len(selecionadas)} de {len(mensagens)} mensagens.")

            # ------------------------------------------------------------------
            # A comunicação chegou onde o risco está?
            #
            # Pergunta de auditoria que nenhuma tabela responde bem. Comparado
            # lado a lado com o Mapa de Risco, este mapa expõe na hora uma
            # cobertura desigual — municípios com alerta e sem mensagem.
            # ------------------------------------------------------------------
            # Atenção ao nome da coluna: `mensagens_df` publica «município»
            # **com acento**, porque é um quadro voltado à leitura humana e à
            # exportação em CSV. Assumir a forma sem acento aqui derrubava a
            # página inteira com KeyError — defeito encontrado pelo teste que
            # executa as páginas de ponta a ponta.
            col_mun = "município" if "município" in df.columns else "municipio"
            geo_msgs = (
                df[df[col_mun].astype(str).str.strip() != ""].copy()
                if col_mun in df.columns else df.iloc[0:0].copy()
            )
            if not geo_msgs.empty and not res.alertas_df.empty:
                coord = (res.alertas_df.groupby(["municipio", "uf"], as_index=False)
                                       .agg(lat=("lat", "mean"), lon=("lon", "mean")))
                geo_msgs = geo_msgs.rename(columns={col_mun: "municipio"})
                geo_msgs = geo_msgs.merge(coord, on=["municipio", "uf"], how="left")
                if "lat" in geo_msgs.columns and geo_msgs["lat"].notna().any():
                    with st.expander("🗺️ Onde as mensagens foram entregues", expanded=False):
                        st.plotly_chart(
                            maps.mapa_mensagens(geo_msgs, altura=altura_mapa(440)),
                            **largura_total(),
                        )
                        rodape_fonte(
                            "Um ponto por mensagem individual, colorido pelo canal. "
                            "Os boletins institucionais não aparecem aqui porque "
                            "consolidam vários municípios — eles estão na aba Personas."
                        )

            for m in selecionadas:
                render_mensagem(m)

            st.divider()
            col1, col2 = colunas(2)
            with col1:
                botao_download(df, f"mensagens_{res.execucao_id}")
            with col2:
                md = [f"# Mensagens geradas — execução {res.execucao_id}\n"]
                for m in mensagens:
                    md.append(f"## {m.id} · {m.persona_nome} · canal {m.canal}\n")
                    md.append(f"- Severidade: {m.severidade} · score {m.score:.0f}")
                    md.append(f"- Local: {m.municipio} {m.uf} · evento: {m.evento}")
                    md.append(f"- Origem: {m.gerado_por} {m.modelo}")
                    if m.assunto:
                        md.append(f"- Assunto: {m.assunto}")
                    md.append(f"\n```\n{m.texto}\n```\n")
                st.download_button(
                    "⬇️ Baixar mensagens em Markdown",
                    data="\n".join(md).encode("utf-8"),
                    file_name=f"mensagens_{res.execucao_id}.md",
                    mime="text/markdown",
                    **largura_total(),
                )

            st.plotly_chart(charts.mensagens_por_persona(df), **largura_total())

            if res.contexto.telemetria_llm is not None:
                t = res.contexto.telemetria_llm
                resumo = t.resumo()
                if resumo["chamadas_api"] or resumo["respostas_do_cache"]:
                    st.markdown("#### Uso de IA Generativa nesta execução")
                    linha_metricas([
                        ("Chamadas à API", inteiro(resumo["chamadas_api"]),
                         f"{resumo['respostas_do_cache']} servidas pelo cache"),
                        ("Tokens", inteiro(resumo["tokens_total"]),
                         f"{inteiro(resumo['tokens_entrada'])} entrada / "
                         f"{inteiro(resumo['tokens_saida'])} saída"),
                        ("Latência acumulada", f"{resumo['latencia_total_s']:.1f} s",
                         f"{resumo['erros']} erros"),
                        ("Modelos", ", ".join(resumo["modelos"]) or "—", ""),
                    ])
                    st.write("")
                    st.plotly_chart(charts.uso_llm(t.por_tarefa()), **largura_total())

# ==========================================================================
with aba_envios:
    res = st.session_state.get("resultado")
    if res is None:
        st.info("Execute o pipeline para ver a simulação de envio.", icon="▶️")
    else:
        envios = res.envios_df
        if envios.empty:
            st.info("Nenhum envio simulado nesta execução.")
        else:
            entregues = int((envios["status"] == "simulado_entregue").sum())
            falhas = int((envios["status"] == "simulado_falha").sum())
            suprimidos = int((envios["status"] == "suprimido").sum())
            custo = float(envios["custo_estimado_R$"].sum())
            linha_metricas([
                ("Entregas simuladas", inteiro(entregues),
                 f"{pct(100 * entregues / max(len(envios), 1))} da fila"),
                ("Falhas simuladas", inteiro(falhas), "com reenvio automático"),
                ("Suprimidos", inteiro(suprimidos), "política anti-fadiga"),
                ("Custo equivalente", reais(custo, 4),
                 "se o envio fosse real"),
            ])
            st.write("")
            st.info(
                "**Nenhuma mensagem é enviada de verdade.** O enunciado do Desafio 5 "
                "dispensa o envio real; este agente reproduz o comportamento de uma "
                "central (fila, janela de contato, tentativa, latência, custo) e "
                "grava tudo na caixa de saída com a marca `simulado`.",
                icon="🧪",
            )
            st.plotly_chart(charts.custo_por_canal(envios), **largura_total())
            tabela(envios, altura=420)
            botao_download(envios, f"envios_{res.execucao_id}")

            st.markdown("##### Perfil operacional simulado por canal")
            from agrosentinela.agents.despachante import PERFIL_CANAL

            perfil = pd.DataFrame(
                [
                    {"Canal": c, "Custo unitário (R$)": v[0],
                     "Latência média (ms)": v[1], "Taxa de falha": pct(v[2] * 100, 1),
                     "Limite de caracteres": LIMITE_CANAL.get(c, "—")}
                    for c, v in PERFIL_CANAL.items()
                ]
            )
            tabela(perfil, altura=260)

# ==========================================================================
with aba_personas:
    st.markdown(
        """
##### Oito perfis, oito formas de comunicar

O enunciado pede "mensagens personalizadas para diferentes perfis de
segurados". A solução vai além do segurado e modela toda a cadeia que decide
sobre risco agrícola. Cada persona tem canal, tom, limite de tamanho,
severidade mínima e — o mais importante — **uma decisão concreta que a
mensagem precisa habilitar**.
        """
    )
    for p in PERSONAS:
        with st.expander(f"**{p.nome}** · {p.papel_na_cadeia}"):
            col1, col2 = colunas([2, 1])
            with col1:
                st.markdown(p.descricao)
                st.markdown(f"**Decisão que a mensagem habilita:** {p.decisao_alvo}")
                st.markdown(f"**Tom:** {p.tom}")
                if p.exemplos_necessidade:
                    st.markdown("**Perguntas que essa pessoa faz:**")
                    for e in p.exemplos_necessidade:
                        st.markdown(f"- *{e}*")
            with col2:
                st.markdown(f"**Código:** `{p.codigo}`")
                st.markdown(f"**Canal padrão:** {p.canal_padrao}")
                st.markdown(f"**Canais:** {', '.join(p.canais)}")
                st.markdown(f"**Limite:** {p.limite_caracteres} caracteres")
                st.markdown(f"**Severidade mínima:** {p.severidade_minima}")
                st.markdown(f"**Janela de contato:** {p.janela_contato}")
                st.markdown(f"**Letramento técnico:** {p.letramento_tecnico}")
                st.markdown(f"**Agregação:** por {p.agrega_por}")

    st.markdown("##### Como a persona é derivada dos microdados")
    st.markdown(
        """
A persona não é escolhida à mão: é inferida dos campos reais da operação no
Sicor, na seguinte ordem de precedência:

1. `CategoriaEmitente` indicando cooperativa, condomínio ou associação → **Cooperativa**
2. `Programa` contendo Pronaf → **Produtor familiar**
3. `Programa` contendo Pronamp → **Produtor empresarial / médio**
4. Sem programa identificável → desempate por porte (`VL_PARC_CREDITO` e `VL_AREA_FINANC`)

As personas institucionais não vêm da operação: são destinatários de
**boletins consolidados**, e cada regra declara quais delas devem receber o
alerta que ela originou.
        """
    )

# ==========================================================================
with aba_hist:
    outbox = obter_outbox()
    stats = outbox.estatisticas()
    linha_metricas([
        ("Execuções registradas", inteiro(stats["execucoes"]), ""),
        ("Alertas acumulados", inteiro(stats["alertas"]), ""),
        ("Mensagens acumuladas", inteiro(stats["mensagens"]), ""),
        ("Envios registrados", inteiro(stats["envios"]),
         f"{len(stats['por_canal'])} canais"),
    ])
    st.caption(f"Banco: `{stats['arquivo']}`")
    st.write("")

    qual = st.selectbox("Tabela", ["execucoes", "mensagens", "alertas", "envios"],
                        key="outbox_tabela")
    df = outbox.tabela(qual, limite=1500)
    tabela(df, altura=460)
    botao_download(df, f"outbox_{qual}")

    st.divider()
    col1, col2 = colunas(2)
    with col1:
        if st.button("🧹 Limpar caixa de saída", **largura_total()):
            outbox.limpar()
            st.success("Caixa de saída zerada.")
            st.rerun()
    with col2:
        st.caption(
            "A caixa de saída é o que sustenta a política anti-fadiga entre "
            "execuções e serve de trilha de auditoria da comunicação."
        )
