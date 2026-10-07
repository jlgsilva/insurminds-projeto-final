"""
AgroSentinela — ponto de entrada da aplicação Streamlit.

Execute com:

    streamlit run app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Torna o pacote importável sem instalação (modo "streamlit run app.py")
_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import streamlit as st  # noqa: E402

from agrosentinela import __app_name__, __version__  # noqa: E402
from agrosentinela.ui import (  # noqa: E402
    avisos,
    barra_lateral,
    cabecalho,
    colunas,
    configurar_pagina,
    executar_pipeline,
    kpis_execucao,
    largura_total,
    linha_metricas,
    obter_motor,
    resultado_atual,
    tabela,
)
from agrosentinela.utils.formato import inteiro, reais_compacto  # noqa: E402
from agrosentinela.etl_catalogo import resumo as resumo_catalogo  # noqa: E402
from agrosentinela.personas import PERSONAS  # noqa: E402
from agrosentinela.rules.catalogo import EVENTOS  # noqa: E402
from agrosentinela.viz import charts  # noqa: E402

configurar_pagina("Início", "🌾")

controles = barra_lateral()

# ==========================================================================
# Cabeçalho
# ==========================================================================
st.markdown(
    f"# 🌾 {__app_name__}\n"
    "### Inteligência climática e comunicação proativa para crédito rural e Proagro"
)
st.caption(
    f"v{__version__} · InsurMinds / I2A2 · **Desafio 5** (comunicação proativa) + "
    "**Projeto Final** (análise e comparação de apólices D&O) · "
    "Construído sobre as Tabelas e Microdados do Crédito Rural e do Proagro "
    "(Sicor, Banco Central do Brasil)"
)

with st.container(border=True):
    st.markdown(
        "#### 🆕 Projeto Final — Plataforma de análise e comparação de apólices D&O\n"
        "Apólices de D&O de **cooperativas de crédito rural, usinas, tradings, frigoríficos "
        "e agroindústrias**: o sistema recebe o documento (PDF, digitalizado ou foto), "
        "extrai o texto (OCR quando preciso), e uma cadeia de **agentes de IA (Groq)** "
        "estrutura o quadro-resumo, classifica **32 cláusulas** com evidência literal, "
        "valida contra alucinação, grava em banco, ajusta os pesos ao **perfil de crédito "
        "rural da tomadora (Sicor/Proagro)**, compara e redige o relatório. "
        "Acervo de demonstração: **120 apólices simuladas** de **6 seguradoras fictícias, cada "
        "uma com seu próprio modelo de documento**, para 45 tomadoras — da associação "
        "extrativista do Acre ao latifúndio do Pantanal — nas cinco regiões do país."
    )
    _l1, _l2, _l3 = st.columns(3)
    with _l1:
        st.page_link("pages/11_📄_Ingestão_de_Apólices.py",
                     label="1 · Ingestão e extração por IA", icon="📄")
    with _l2:
        st.page_link("pages/12_⚖️_Comparador_de_Apólices.py",
                     label="2 · Comparar apólices", icon="⚖️")
    with _l3:
        st.page_link("pages/13_💬_Consulta_às_Apólices.py",
                     label="3 · Perguntar à base", icon="💬")

# ==========================================================================
# Comece aqui
#
# A primeira versão desta página abria com dois blocos densos de texto e a
# ação principal escondida no fim da barra lateral. Quem chegava pela
# primeira vez não sabia o que clicar. Agora a primeira coisa na tela é o que
# fazer, em três passos, e o texto explicativo vem depois — para quem quiser.
# ==========================================================================
if resultado_atual() is None:
    st.success(
        "### 👋 Primeira vez aqui? São 3 passos, e leva menos de um minuto.\n\n"
        "**1.** Na barra à esquerda, escolha uma **situação** "
        "(sugestão: `🌵 Seca / veranico`).\n\n"
        "**2.** Clique no botão azul **▶️ Executar pipeline**.\n\n"
        "**3.** Os resultados aparecem aqui embaixo. Depois, percorra as "
        "páginas do menu à esquerda — mapas, mensagens geradas, regras.\n\n"
        "Não precisa de internet, nem de cadastro, nem de chave de IA. "
        "Se faltar alguma coisa, o próprio sistema avisa na tela.",
        icon="🚀",
    )
else:
    st.caption(
        "Dica: mude a **situação** na barra à esquerda e execute de novo para "
        "ver o sistema reagir a outro evento climático."
    )

col_a, col_b = colunas([3, 2], gap="large")

with col_a:
    st.markdown(
        """
**O problema.** A relação entre seguradora, banco e produtor rural quase
sempre começa **depois** do sinistro: a chuva já caiu, a geada já queimou o
cafezal, a seca já comprometeu o enchimento de grãos. Nesse ponto, resta
administrar a perda.

**A virada.** O Banco Central publica, em dados abertos, **todas as operações
de crédito rural contratadas no país** — município, cultura, área, valor,
janela de plantio e de colheita, cobertura do Proagro — e o histórico
completo de acionamento do Proagro desde 1983. Cruzando isso com previsão
meteorológica pública, é possível saber **quem** está exposto a **qual**
evento, em **qual** fase da lavoura, **antes** que o evento aconteça.

**O AgroSentinela** faz esse cruzamento a cada execução e transforma o
resultado em comunicação personalizada para dezesseis perfis diferentes da cadeia
do agronegócio — do produtor familiar no WhatsApp ao analista de subscrição
no painel.
        """
    )

with col_b:
    st.markdown("#### Fluxo da solução")
    st.markdown(
        """
```
①  CarteiraAgent     universo monitorado (Sicor)
        ↓
②  ClimaAgent        coleta externa (Open-Meteo)
        ↓
③  EventoAgent       identificação dos eventos
        ↓
④  RegrasAgent       regras de negócio + score
        ↓
⑤  RedatorAgent      IA Generativa (Groq)
        ↓
⑥  DespachanteAgent  simulação do envio
```
        """
    )
    st.caption(
        "As cinco etapas exigidas pelo enunciado estão mapeadas uma a uma em "
        "agentes especializados, cada um com responsabilidade única e rastro "
        "próprio de execução."
    )

st.divider()

# ==========================================================================
# Execução
# ==========================================================================
if controles.get("executar"):
    with st.status("Executando o pipeline multiagente…", expanded=True) as status:
        st.write("Preparando a carteira do Sicor…")
        resultado = executar_pipeline(**controles["parametros"])
        for etapa in resultado.contexto.rastro:
            marca = "✅" if etapa.sucesso else "❌"
            st.write(f"{marca} **{etapa.agente}** ({etapa.duracao_s:.2f}s) — {etapa.resumo}")
        status.update(
            label=f"Execução {resultado.execucao_id} concluída em "
                  f"{resultado.contexto.duracao_total_s:.2f}s",
            state="complete" if resultado.sucesso else "error",
            expanded=False,
        )

res = resultado_atual()

if res is None:
    motor = obter_motor()
    st.markdown("#### O que este sistema faz de diferente")
    linha_metricas([
        ("Perfis atendidos", str(len(PERSONAS)),
         "do produtor familiar ao atuário de seguradora"),
        ("Eventos climáticos", str(len(EVENTOS)),
         "seca, granizo, geada, vendaval, chuva…"),
        ("Regras de negócio", str(len(motor.regras)),
         f"declarativas e auditáveis, versão {motor.versao}"),
        ("Arquivos do BCB usados", f"{resumo_catalogo()['usados']} de {resumo_catalogo()['total']}",
         f"{resumo_catalogo()['cobertura_pct']}% do que o Banco Central publica"),
    ])

    st.markdown("#### O que você encontra em cada página")
    st.markdown(
        """
| Página | O que mostra | Precisa executar antes? |
|---|---|---|
| 📊 **Painel Executivo** | Os números da carteira e dos alertas, com mapas | sim |
| 🗺️ **Mapa de Risco** | Onde está o crédito, o evento e o dinheiro em risco | em parte |
| 🌦️ **Radar Climático** | A previsão que gerou cada alerta | sim |
| ⚙️ **Motor de Regras** | As regras, com um simulador para você testar | não |
| 💬 **Central de Comunicação** | As mensagens geradas, uma a uma | sim |
| 🤖 **Copiloto IA** | Perguntas em português sobre os dados | sim |
| 🗃️ **Microdados SICOR** | Os dados brutos e o catálogo do Banco Central | não |
| 🛡️ **Proagro e Sinistralidade** | O histórico de sinistros por município | não |
| 🌐 **Dados Externos** | As 16 fontes públicas que complementam o Sicor | não |
| 📚 **Documentação** | Arquitetura, decisões técnicas e governança | não |
| 📄 **Ingestão de Apólices** *(Projeto Final)* | Upload, OCR, extração por IA, validação e base | não |
| ⚖️ **Comparador de Apólices** *(Projeto Final)* | Comparação cláusula a cláusula + relatório por IA | não |
| 💬 **Consulta às Apólices** *(Projeto Final)* | Perguntas em linguagem natural sobre as apólices | não |
        """
    )

    with st.expander("Por que os microdados do Sicor mudam o jogo", expanded=False):
        st.markdown(
            """
Um alerta meteorológico genérico ("vai gear no Sul") não ajuda ninguém a
decidir. O que muda a decisão é saber que **aquela operação**, de café em
fase de brotação, com 42 hectares financiados em Patrocínio-MG, sem seguro
declarado e com vencimento em 70 dias, está na área da geada.

Essa informação existe, é pública e está nos microdados do Sicor:

| Campo do Sicor | Uso no AgroSentinela |
|---|---|
| `CD_IBGE_MUNICIPIO` | localiza a operação na grade meteorológica |
| `DT_INIC_PLANTIO` / `DT_INIC_COLHEITA` | calcula a **fase fenológica** de hoje |
| `CD_EMPREENDIMENTO` → Produto | define a **cultura** e sua sensibilidade |
| `CD_TIPO_SEGURO` | indica se há Proagro, seguro privado ou nada |
| `CD_TIPO_IRRIGACAO` | distingue sequeiro de irrigado nas regras de seca |
| `VL_PARC_CREDITO`, `VL_AREA_FINANC` | dimensionam a exposição |
| `DT_VENCIMENTO` | antecipa risco de prorrogação e inadimplência |
| `CD_PROGRAMA` (Pronaf/Pronamp) | deriva a **persona** e o tom da mensagem |
| `SICOR_COP_BASICO` / `SICOR_RCP_BASICO` | histórico de sinistro por evento e município |
            """
        )
    st.stop()

# ==========================================================================
# Resultado
# ==========================================================================
cabecalho(
    f"Execução {res.execucao_id}",
    f"Base: {res.base.origem} · referência {res.contexto.data_ref.strftime('%d/%m/%Y')} · "
    f"horizonte de {res.contexto.horizonte_dias} dias · "
    f"{res.contexto.duracao_total_s:.2f}s de processamento",
)

kpis_execucao(res)
st.write("")
avisos(res)

col1, col2 = colunas([1, 1], gap="large")
with col1:
    envios = res.envios_df
    entregues = int((envios["status"] == "simulado_entregue").sum()) if not envios.empty else 0
    st.plotly_chart(
        charts.funil_comunicacao(
            operacoes=len(res.contexto.carteira),
            alertas=len(res.contexto.alertas),
            mensagens=len(res.contexto.mensagens),
            entregues=entregues,
        ),
        **largura_total(),
    )
with col2:
    st.plotly_chart(charts.alertas_por_evento(res.alertas_df), **largura_total())

st.markdown("#### Rastro da execução")
st.caption(
    "Cada linha é um agente do pipeline, com o tempo gasto e as métricas que "
    "produziu — é a evidência do fluxo completo exigida pelo desafio."
)
rastro = res.rastro_df
colunas_visiveis = [c for c in rastro.columns if c in
                    ("agente", "papel", "duração_s", "status", "resumo")]
tabela(rastro[colunas_visiveis], altura=260)

with st.expander("Métricas detalhadas por agente"):
    st.dataframe(rastro, **largura_total(), hide_index=True)

with st.expander("Resumo técnico da execução (JSON)"):
    st.json(res.resumo, expanded=False)

st.divider()
st.markdown(
    "➡️ Continue pelas páginas na barra lateral: **Painel Executivo**, "
    "**Mapa de Risco**, **Radar Climático**, **Motor de Regras**, "
    "**Central de Comunicação**, **Copiloto IA**, **Microdados Sicor**, "
    "**Proagro & Sinistralidade** e **Documentação**."
)
