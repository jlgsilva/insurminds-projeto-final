"""Motor de regras — catálogo, simulador e auditoria dos disparos."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from agrosentinela.rules.catalogo import (  # noqa: E402
    CULTURAS,
    CULTURAS_POR_CODIGO,
    EVENTOS,
    get_cultura,
)
from agrosentinela.rules.engine import RULES_PATH  # noqa: E402
from agrosentinela.ui import (  # noqa: E402
    barra_lateral,
    botao_download,
    cabecalho,
    colunas,
    configurar_pagina,
    exigir_execucao,
    largura_total,
    obter_motor,
    tabela,
)
from agrosentinela.utils.formato import num, reais_compacto  # noqa: E402
from agrosentinela.viz.theme import ROTULO_SEVERIDADE, faixa  # noqa: E402

configurar_pagina("Motor de Regras", "⚙️")
barra_lateral(mostrar_execucao=False)

motor = obter_motor()

cabecalho(
    "Motor de Regras de Negócio",
    f"{len(motor.regras)} regras declarativas · versão {motor.versao} "
    f"· atualizado em {motor.atualizado_em}",
    "⚙️",
)

st.markdown(
    """
As regras não estão escondidas no código: vivem em um arquivo de texto
versionado (`src/agrosentinela/rules/rules.yaml`) que pode ser lido e
revisado por quem entende de crédito rural, mesmo sem saber programar.
Cada regra declara **quando dispara**, **quanto agrava**, **quem avisa** e
**qual ação recomenda** — e todo alerta carrega o identificador da regra que
o originou.
    """
)

aba_catalogo, aba_sim, aba_disparos, aba_fenologia = st.tabs(
    ["📋 Catálogo de regras", "🧪 Simulador", "🔍 Disparos da execução", "🌱 Fenologia e eventos"]
)

# ==========================================================================
with aba_catalogo:
    resumo = pd.DataFrame(motor.resumo())
    busca = st.text_input("Filtrar regras", placeholder="ex.: seca, geada, cobertura, R-CHU")
    if busca:
        mascara = resumo.apply(
            lambda r: busca.lower() in " ".join(str(v).lower() for v in r.values), axis=1
        )
        resumo = resumo[mascara]

    for _, r in resumo.iterrows():
        with st.expander(f"**{r['id']}** — {r['nome']}  ·  evento: `{r['evento']}`"):
            st.markdown(r["descrição"])
            col1, col2 = colunas([2, 1])
            with col1:
                st.markdown("**Condição de disparo**")
                st.code(r["condição"], language="python")
                st.markdown(f"**Ação recomendada:** {r['ação']}")
                st.markdown(f"**Base técnica:** {r['base_técnica']}")
            with col2:
                st.markdown(f"**Severidade base:** {faixa(r['severidade_base'])}",
                            unsafe_allow_html=True)
                st.markdown(f"**Escalonamentos:** {r['escalonamentos']}")
                st.markdown(f"**Fases críticas:** {r['fases_críticas']}")
                st.markdown(f"**Janela de ação:** {r['janela_ação_h']} h")
                st.markdown(f"**Coberto pelo Proagro:** {r['coberto_proagro']}")
                st.markdown(f"**Personas:** {r['personas']}")

    st.divider()
    col1, col2 = colunas(2)
    with col1:
        botao_download(pd.DataFrame(motor.resumo()), "catalogo_regras")
    with col2:
        st.download_button(
            "⬇️ Baixar rules.yaml",
            data=RULES_PATH.read_text(encoding="utf-8"),
            file_name="rules.yaml",
            mime="text/yaml",
            **largura_total(),
        )

    st.markdown("#### Política anti-fadiga de alerta")
    sup = motor.supressao
    st.markdown(
        f"""
| Parâmetro | Valor | Por quê |
|---|---|---|
| Janela de repetição | {sup.janela_repeticao_h} h | Evita reenviar a mesma mensagem enquanto a situação não muda |
| Máximo por destinatário/dia | {sup.max_msgs_destinatario_dia} | Alerta em excesso deixa de ser lido |
| Severidade mínima | {sup.severidade_minima_global} | Ruído informativo não vira mensagem |
| Consolidação por destinatário | {"sim" if sup.consolidar_por_destinatario else "não"} | Vários eventos viram uma mensagem só |
        """
    )
    st.markdown("#### Composição do score de risco (0–100)")
    p = motor.pesos
    st.markdown(
        f"""
| Componente | Peso | O que mede |
|---|---|---|
| Severidade meteorológica | {p.peso_severidade:.0f} | Intensidade do evento previsto |
| Sensibilidade da fase | {p.peso_fase:.0f} | Quanto a fase fenológica sofre com aquele evento |
| Histórico do Proagro | {p.peso_historico:.0f} | Recorrência do evento naquele município |
| Exposição financeira | {p.peso_exposicao:.0f} | Valor financiado, em escala logarítmica |
| Ausência de cobertura | {p.peso_cobertura:.0f} | Risco não transferido |
| **Limiar de notificação** | **{p.limiar_notificacao:.0f}** | Abaixo disso, não vira mensagem |

O total é normalizado pelo máximo teórico da própria regra, o que torna o
score comparável entre regras diferentes.
        """
    )

# ==========================================================================
with aba_sim:
    st.markdown("##### Simule uma situação e veja quais regras disparam")
    st.caption(
        "Este simulador executa o **mesmo** motor usado no pipeline, com o "
        "mesmo arquivo de regras. Serve para calibrar limiares e para explicar "
        "a decisão a quem não conhece o sistema."
    )

    col1, col2, col3 = colunas(3)
    with col1:
        st.markdown("**Lavoura**")
        cultura = st.selectbox("Cultura", [c.codigo for c in CULTURAS],
                               format_func=lambda c: CULTURAS_POR_CODIGO[c].nome, key="sim_cult")
        info = get_cultura(cultura)
        fase = st.selectbox("Fase", [f.codigo for f in info.fases],
                            format_func=lambda f: next(x.nome for x in info.fases if x.codigo == f),
                            index=min(2, len(info.fases) - 1), key="sim_fase")
        irrigada = st.checkbox("Lavoura irrigada", value=False, key="sim_irrig")
        area = st.number_input("Área (ha)", 1.0, 20000.0, 120.0, step=10.0, key="sim_area")
    with col2:
        st.markdown("**Operação**")
        valor = st.number_input("Valor financiado (R$)", 1000.0, 20_000_000.0,
                                450_000.0, step=10_000.0, key="sim_valor")
        cobertura = st.checkbox("Possui cobertura declarada", value=False, key="sim_cob")
        dias_venc = st.slider("Dias até o vencimento", 0, 720, 120, key="sim_venc")
        dias_colh = st.slider("Dias até a colheita", -30, 240, 45, key="sim_colh")
        exposicao_mun = st.number_input("Exposição do município (R$)", 0.0, 500_000_000.0,
                                        8_000_000.0, step=1_000_000.0, key="sim_expo")
    with col3:
        st.markdown("**Clima previsto**")
        dias_secos = st.slider("Dias secos consecutivos", 0, 45, 16, key="sim_secos")
        bh14 = st.slider("Balanço hídrico 14 d (mm)", -150, 150, -55, key="sim_bh")
        prec7 = st.slider("Chuva prevista 7 d (mm)", 0, 350, 10, key="sim_prec7")
        prec24 = st.slider("Maior acumulado 24 h (mm)", 0, 200, 8, key="sim_prec24")
        tmin = st.slider("Mínima prevista (°C)", -6.0, 30.0, 14.0, 0.5, key="sim_tmin")
        tmax = st.slider("Máxima prevista (°C)", 10.0, 46.0, 31.0, 0.5, key="sim_tmax")
        rajada = st.slider("Rajada máxima (km/h)", 0, 140, 35, key="sim_raj")
        granizo = st.slider("Índice de granizo (0–100)", 0, 100, 10, key="sim_gran")
        freq_hist = st.slider("Frequência histórica do evento no município", 0.0, 1.0, 0.3, 0.05,
                              key="sim_hist")

    fase_obj = next((f for f in info.fases if f.codigo == fase), info.fases[0])

    contexto = {
        "cultura": cultura,
        "cultura_grupo": info.grupo,
        "fase": fase,
        "sensibilidade_fase": 1.0,
        "irrigada": irrigada,
        "area_ha": area,
        "valor_credito": valor,
        "tem_cobertura": cobertura,
        "dias_para_vencimento": dias_venc,
        "dias_para_colheita": dias_colh,
        "exposicao_municipio": exposicao_mun,
        "freq_evento_municipio": freq_hist,
        "dias_secos_consecutivos": dias_secos,
        "balanco_hidrico_14d": bh14,
        "balanco_hidrico_7d": prec7 - 30,
        "prec_7d": prec7,
        "prec_max_24h": prec24,
        "prec_14d": prec7 * 1.6,
        "dias_com_chuva_7d": min(7, int(prec7 / 12)),
        "umidade_media": 60 + min(35, prec7 / 4),
        "tmin_min": tmin,
        "tmax_max": tmax,
        "dias_tmin_le_3": 2 if tmin <= 3 else 0,
        "dias_tmin_le_0": 1 if tmin <= 0 else 0,
        "dias_tmax_ge_35": 4 if tmax >= 35 else 0,
        "dias_tmax_ge_32": 5 if tmax >= 32 else 0,
        "rajada_max": rajada,
        "vento_medio_max": rajada * 0.6,
        "prob_granizo": granizo,
        "cape_max": granizo * 32,
    }

    # A sensibilidade depende do evento de cada regra: avaliamos por evento.
    acionamentos_total = []
    for evento in EVENTOS:
        ctx_evt = dict(contexto)
        ctx_evt["sensibilidade_fase"] = fase_obj.sensibilidade.get(evento.codigo, 1.0)
        regras_evt = [r for r in motor.regras
                      if r.evento == evento.codigo or r.aplica_a_qualquer_evento]
        for ac in motor.avaliar(ctx_evt, regras=regras_evt):
            ac_dict = ac.to_dict()
            ac_dict["evento_avaliado"] = evento.nome
            acionamentos_total.append(ac_dict)

    # Remove duplicatas de regras genéricas (aparecem uma vez por evento)
    vistos = set()
    unicos = []
    for ac in sorted(acionamentos_total, key=lambda a: (-a["severidade_peso"], -a["score"])):
        chave = (ac["regra_id"], ac["evento_avaliado"] if ac["evento"] != "multiplo" else "*")
        if chave in vistos:
            continue
        vistos.add(chave)
        unicos.append(ac)

    st.divider()
    if not unicos:
        st.success(
            "Nenhuma regra dispara com esses parâmetros. A operação não entraria "
            "na fila de comunicação.",
            icon="✅",
        )
    else:
        acima = [a for a in unicos if a["score"] >= motor.pesos.limiar_notificacao]
        st.markdown(
            f"**{len(unicos)} regras dispararam** — {len(acima)} acima do limiar de "
            f"notificação ({motor.pesos.limiar_notificacao:.0f} pontos)."
        )
        for ac in unicos[:12]:
            marca = "🔔" if ac["score"] >= motor.pesos.limiar_notificacao else "🔕"
            with st.container(border=True):
                st.markdown(
                    f"{marca} **{ac['regra_id']} — {ac['regra_nome']}** "
                    f"· evento avaliado: {ac['evento_avaliado']} "
                    f"· {faixa(ac['severidade'])} · score **{ac['score']:.0f}**",
                    unsafe_allow_html=True,
                )
                st.caption(ac["explicacao"])
                st.markdown(f"**Ação:** {ac['acao']}")
                st.caption(
                    f"Notificaria: {', '.join(ac['personas'])} · janela de "
                    f"{ac['janela_acao_h']} h"
                )

# ==========================================================================
with aba_disparos:
    res = exigir_execucao()
    if res is not None:
        alertas = res.alertas_df
        if alertas.empty:
            st.info("Nenhum alerta gerado nesta execução.")
        else:
            linhas = []
            for a in res.contexto.alertas:
                for ac in a.acionamentos:
                    linhas.append({
                        "regra_id": ac["regra_id"],
                        "regra": ac["regra_nome"],
                        "evento": a.evento_nome,
                        "severidade": ac["severidade"],
                        "score": ac["score"],
                        "municipio": a.municipio,
                        "uf": a.uf,
                        "cultura": a.produto,
                        "fase": a.fase_nome,
                        "valor_credito": a.valor_credito,
                        "fase_critica": ac["fase_critica"],
                    })
            df = pd.DataFrame(linhas)
            agg = (
                df.groupby(["regra_id", "regra"], as_index=False)
                .agg(disparos=("regra_id", "count"),
                     municipios=("municipio", "nunique"),
                     exposicao=("valor_credito", "sum"),
                     score_medio=("score", "mean"),
                     criticos=("severidade", lambda s: int((s == "critico").sum())))
                .sort_values("disparos", ascending=False)
            )
            agg["exposição"] = agg["exposicao"].map(reais_compacto)
            agg["score médio"] = agg["score_medio"].round(1)
            tabela(
                agg[["regra_id", "regra", "disparos", "criticos", "municipios",
                     "exposição", "score médio"]],
                altura=420,
            )
            st.caption(
                "Regras que nunca disparam podem estar com limiar alto demais; "
                "regras que disparam sempre, com limiar baixo demais. Esta tabela "
                "é o instrumento de calibração do motor."
            )
            nao_dispararam = [r.id for r in motor.regras if r.id not in set(agg["regra_id"])]
            if nao_dispararam:
                st.info(
                    "Regras sem disparo nesta execução: " + ", ".join(nao_dispararam),
                    icon="🔕",
                )
            botao_download(df, "disparos_detalhados")

# ==========================================================================
with aba_fenologia:
    st.markdown("##### Eventos climáticos monitorados")
    ev = pd.DataFrame([
        {
            "Código": e.codigo,
            "Evento": f"{e.icone} {e.nome}",
            "Coberto pelo Proagro": "sim" if e.cobertura_proagro else "não",
            "Indicadores": ", ".join(e.indicadores),
            "Equivalente no EventoProagro.csv": ", ".join(e.sinonimos_proagro),
            "Descrição": e.descricao,
        }
        for e in EVENTOS
    ])
    tabela(ev, altura=340)

    st.markdown("##### Sensibilidade por cultura e fase")
    st.caption(
        "Multiplicador aplicado ao score conforme a fase em que a lavoura se "
        "encontra. Valores acima de 1 agravam; abaixo de 1 atenuam. É o que "
        "diferencia «chove muito» de «chove muito em plena colheita»."
    )
    cultura_sel = st.selectbox(
        "Cultura", [c.codigo for c in CULTURAS],
        format_func=lambda c: f"{CULTURAS_POR_CODIGO[c].icone} {CULTURAS_POR_CODIGO[c].nome}",
        key="fen_cult",
    )
    cult = get_cultura(cultura_sel)
    st.caption(f"Ciclo típico: {cult.ciclo_dias} dias · unidade: {cult.unidade_produtiva}")
    linhas = []
    for f in cult.fases:
        linha = {"Fase": f.nome, "Início do ciclo": f"{f.inicio:.0%}", "Fim": f"{f.fim:.0%}"}
        for e in EVENTOS:
            linha[e.icone] = f.sensibilidade.get(e.codigo, 1.0)
        linha["Recomendação da fase"] = f.recomendacao
        linhas.append(linha)
    tabela(pd.DataFrame(linhas), altura=300)
    st.caption("Legenda dos ícones: " + " · ".join(f"{e.icone} {e.nome}" for e in EVENTOS))
