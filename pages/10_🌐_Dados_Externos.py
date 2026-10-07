"""
Fontes externas — gratuitas, públicas e livres.

Esta página existe por dois motivos, e o segundo é o mais importante.

O primeiro é mostrar o que a solução consome além do Sicor: clima, produção,
uso do solo, seguro privado, fogo e seca oficial.

O segundo é **prestar contas sobre a procedência de cada número**. Toda
fonte aqui pode estar indisponível no momento em que alguém abre o painel —
e nesse caso a solução continua funcionando com uma tabela de referência
embutida. Isso é honesto apenas se estiver dito na tela. Por isso cada valor
carrega um selo: 🟢 ao vivo, 🟡 cache, ⚪ referência embutida. Um painel que
apresenta valor aproximado como se fosse consulta ao vivo é pior do que um
painel vazio.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from agrosentinela import fontes_externas as fe  # noqa: E402
from agrosentinela.data.loader import completar_colunas  # noqa: E402
from agrosentinela.external import diagnostico, obter_conector, sondar  # noqa: E402
from agrosentinela.external.zarc import cobertura as zarc_cobertura  # noqa: E402
from agrosentinela.ui import (  # noqa: E402
    altura_mapa,
    barra_lateral,
    base_atual,
    botao_download,
    cabecalho,
    colunas,
    configurar_pagina,
    largura_total,
    linha_metricas,
    rodape_fonte,
    tabela,
)
from agrosentinela.utils.formato import inteiro  # noqa: E402
from agrosentinela.viz import maps  # noqa: E402

configurar_pagina("Dados Externos", "🌐")
barra_lateral(mostrar_execucao=False)

cabecalho(
    "Dados externos",
    "Tudo gratuito, público e livre. Nenhuma fonte exige cadastro, contrato "
    "ou cota paga.",
    "🌐",
)

base = base_atual()
resumo = fe.resumo()

linha_metricas([
    ("Fontes catalogadas", inteiro(resumo["total"]),
     f"{resumo['ativas']} ativas no fluxo"),
    ("Exigem cadastro", "nenhuma", f"{resumo['sem_cadastro']} de {resumo['total']} livres"),
    ("Custo", "R$ 0,00", "condição de projeto"),
    ("Categorias", inteiro(len(fe.CATEGORIAS)),
     ", ".join(list(fe.CATEGORIAS)[:3]) + "…"),
])
st.write("")

aba_catalogo, aba_estado, aba_zarc, aba_mapa = st.tabs(
    ["📚 Catálogo", "📡 Estado das fontes", "🌱 Janelas Zarc", "🗺️ Contexto no mapa"]
)

# ==========================================================================
with aba_catalogo:
    st.markdown("##### Por que dados externos, se o Sicor já é riquíssimo?")
    st.markdown(
        """
O Sicor conta o que foi **financiado** e o que foi **sinistrado**. Ele não
conta o que está acontecendo **agora** no campo, nem o que existe **fora** do
crédito rural. São três lacunas concretas:

* **Tempo presente e futuro** — o Sicor é retrospectivo. Alerta útil exige
  previsão (Open-Meteo), série climática longa (NASA POWER, INMET) e
  monitoramento quase em tempo real (CEMADEN, INPE).
* **Denominador** — "1.200 operações de soja em Sorriso" só vira risco quando
  comparado à área total de soja do município (IBGE/PAM) e ao uso do solo
  (MapBiomas).
* **O outro lado da cobertura** — o Proagro é metade do mercado. A outra
  metade é o seguro rural privado subvencionado (PSR/MAPA) e o mercado
  supervisionado pela SUSEP. Sem eles não se sabe se um município está
  *descoberto* ou apenas *protegido por outro instrumento* — e essa
  diferença muda completamente a recomendação.
        """
    )

    categoria = st.selectbox(
        "Categoria", ["(todas)"] + list(fe.CATEGORIAS), key="fe_cat"
    )
    fontes = fe.FONTES if categoria == "(todas)" else fe.por_categoria(categoria)
    tabela(pd.DataFrame([f.to_row() for f in fontes]), altura=460)

    st.markdown("##### Detalhe por fonte")
    nomes = {f.nome: f for f in fontes}
    escolhida = st.selectbox("Fonte", list(nomes.keys()), key="fe_detalhe")
    f = nomes[escolhida]
    esq, dir_ = colunas(2, gap="large")
    with esq:
        st.markdown(f"**Órgão:** {f.orgao}")
        st.markdown(f"**Licença:** {f.licenca}")
        st.markdown(f"**Granularidade:** {f.granularidade}")
        st.markdown(f"**Atualização:** {f.atualizacao}")
        st.markdown(f"**Liga ao Sicor por:** `{f.chave_juncao}`")
    with dir_:
        st.markdown(f"**Papel na solução:** {f.papel}")
        st.markdown(f"**Sem rede, a solução usa:** {f.fallback}")
        if f.nota:
            st.info(f.nota, icon="ℹ️")
        st.markdown(f"[Abrir portal oficial]({f.url_portal})")

# ==========================================================================
with aba_estado:
    st.markdown("##### O que está respondendo agora")
    st.caption(
        "A sondagem é acionada por botão, e não ao abrir a página: testar "
        "dezesseis fontes a cada carregamento seria desrespeitoso com "
        "servidores públicos e deixaria o painel lento sem benefício."
    )
    tabela(diagnostico(), altura=420)

    if st.button("📡 Sondar fontes agora", **largura_total()):
        with st.spinner("Consultando as fontes públicas…"):
            tabela(sondar(), altura=420)

    st.markdown("##### Como a solução degrada")
    st.markdown(
        """
Todo conector segue a mesma escada, e o resultado carrega a procedência até
a tela:

1. **🟢 ao vivo** — a API pública respondeu e a resposta foi guardada em cache.
2. **🟡 cache** — a fonte não respondeu, mas há uma resposta anterior válida.
3. **⚪ referência embutida** — nem rede nem cache: entra a tabela de
   referência do próprio código, **sempre rotulada como tal**.

Duas exceções deliberadas: **fogo (INPE)** e **chuva medida em solo
(CEMADEN)** nunca caem para referência. Sem rede, eles devolvem "não sei" em
vez de "zero". Um zero inventado esconderia justamente o evento que importa.
        """
    )

# ==========================================================================
with aba_zarc:
    st.markdown("##### Zoneamento Agrícola de Risco Climático")
    st.markdown(
        """
O Zarc é o único instrumento brasileiro que diz, com respaldo legal, **em que
decêndio se pode plantar cada cultura, em cada município e tipo de solo**, com
risco de perda de 20%, 30% ou 40%. É condição de acesso ao Proagro e ao seguro
subvencionado.

O AgroSentinela o usa de duas formas, e a segunda vale mais:

1. **Atenuante do escore** — quem plantou dentro da janela tem o risco
   calculado reduzido em 15%, porque parte do risco climático já foi mitigada
   na decisão de plantio. Fora da janela, o escore sobe até 25%,
   proporcionalmente aos decêndios de distância.
2. **Explicação causal na mensagem** — quando a data de plantio registrada no
   Sicor cai fora da janela, a mensagem deixa de ser "há risco de seca" e passa
   a ser *"há risco de seca **e** seu plantio ficou 2 decêndios além da janela
   Zarc para esta cultura e solo neste município"*. Essa informação não existe
   nem no Sicor nem na previsão do tempo isoladamente — ela só aparece no
   cruzamento.
        """
    )
    st.caption(
        "As janelas abaixo são a referência embutida por região, usada quando "
        "o portal do MAPA não está acessível. As janelas oficiais são "
        "municipais e publicadas por portaria de safra."
    )
    tabela(zarc_cobertura(), altura=420)

# ==========================================================================
with aba_mapa:
    st.markdown("##### Contexto externo por município")
    contexto = base.contexto_externo
    if contexto is None or contexto.empty:
        st.info(
            "Contexto externo não carregado. Para habilitar: "
            "`python etl/08_build_contexto_externo.py` "
            "(use `--offline` para rodar sem rede).",
            icon="🌐",
        )
    else:
        origem = (contexto["origem_contexto"].dropna().iloc[0]
                  if "origem_contexto" in contexto.columns
                  and not contexto["origem_contexto"].dropna().empty else "")
        if origem:
            st.caption(f"Procedência desta carga — {origem}")

        # `completar_colunas` só traz o que falta. Uma junção direta aqui
        # produziria `lat_x`/`lat_y` e faria a coluna `lat` desaparecer —
        # o mapa então quebrava a página inteira com KeyError.
        dados = completar_colunas(
            contexto, base.municipios, chave="cd_ibge",
            colunas=("municipio", "uf", "lat", "lon"),
        )

        indicadores = {
            "Chuva normal (mm/mês) — NASA POWER": ("chuva_normal_mm_mes", "Blues"),
            "Temperatura normal (°C) — NASA POWER": ("temp_normal_c", "RdYlBu_r"),
            "Penetração do seguro privado — PSR/MAPA":
                ("penetracao_seguro_privado", "Greens"),
            "Rendimento de referência (kg/ha) — IBGE/PAM":
                ("rendimento_ref_kg_ha", "YlGn"),
            "Fração de lavoura — MapBiomas": ("frac_lavoura", "YlOrBr"),
            "Fração de vegetação nativa — MapBiomas": ("frac_nativa", "Greens"),
            "Severidade de seca oficial — Monitor de Secas":
                ("severidade_seca", "OrRd"),
            "Focos de calor (24 h) — INPE": ("focos_calor_24h", "Reds"),
        }
        disponiveis = {
            k: v for k, v in indicadores.items()
            if v[0] in dados.columns
            and pd.to_numeric(dados[v[0]], errors="coerce").notna().any()
        }
        if not disponiveis:
            st.warning("Nenhum indicador externo com valores nesta carga.")
        else:
            rotulo = st.selectbox("Indicador", list(disponiveis.keys()), key="fe_ind")
            coluna, escala = disponiveis[rotulo]
            st.plotly_chart(
                maps.mapa_indicador(dados, coluna, rotulo.split(" — ")[0],
                                    escala=escala, altura=altura_mapa()),
                **largura_total(),
            )
            rodape_fonte(
                "Fonte externa gratuita e pública. Quando o selo indicar "
                "«referência embutida», o valor é uma aproximação regional "
                "para manter o painel funcional sem rede — útil para "
                "demonstração, não para decisão operacional."
            )
            with st.expander("Tabela do contexto externo"):
                tabela(contexto, altura=420)
                botao_download(contexto, "contexto_externo")

st.divider()
st.caption(
    "Créditos de atribuição exigidos pelas licenças: "
    + " · ".join(fe.creditos()[:4]) + " · e demais fontes listadas no catálogo."
)
