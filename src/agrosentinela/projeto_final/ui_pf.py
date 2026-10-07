"""Componentes de interface compartilhados pelas páginas do Projeto Final."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from ..config import APOLICES_DIR, get_settings
from ..llm.groq_client import GroqClient, Telemetria
from .agentes import OrquestradorApolices, tabela_escores
from .clausulas import ROTULO_NIVEL
from .repositorio import Repositorio

CORES_NIVEL = {
    "ampla": "#1b7f3b", "padrao": "#5b8def", "restrita": "#d98c00",
    "ausente": "#9e9e9e", "excluida": "#c62828",
}


@st.cache_resource
def obter_repo() -> Repositorio:
    return Repositorio()


def cliente_sessao() -> GroqClient:
    """Cliente Groq da sessão: chave dos secrets ou digitada pelo usuário."""
    chave = st.session_state.get("pf_groq_key") or None
    if "pf_telemetria" not in st.session_state:
        st.session_state["pf_telemetria"] = Telemetria()
    return GroqClient(api_key=chave, telemetria=st.session_state["pf_telemetria"])


def orquestrador() -> OrquestradorApolices:
    from ..ui import base_atual

    try:
        base = base_atual()
    except Exception:  # noqa: BLE001
        base = None
    return OrquestradorApolices(repo=obter_repo(), cliente=cliente_sessao(), base_sicor=base)


def painel_ia_lateral() -> bool:
    """Bloco da barra lateral: status da IA, chave opcional e uso de tokens."""
    with st.sidebar:
        st.markdown("### 🤖 IA do Projeto Final")
        cli = cliente_sessao()
        s = get_settings()
        if cli.disponivel:
            st.success("Groq configurada", icon="🔑")
        else:
            st.warning("Sem chave da Groq: a extração e o relatório usam o modo "
                       "determinístico (linha de base).", icon="⚠️")
            def _guardar() -> None:
                st.session_state["pf_groq_key"] = st.session_state.get("pf_groq_key_in", "").strip()

            st.text_input("Cole uma GROQ_API_KEY (só nesta sessão)", type="password",
                          key="pf_groq_key_in", on_change=_guardar,
                          help="Crie grátis em console.groq.com/keys. Não é gravada.")
        usar = st.toggle("Usar IA (Groq)", value=cli.disponivel, key="pf_usar_llm",
                         disabled=not cli.disponivel)
        st.caption(f"Extração de cláusulas: `{s.modelo_extracao}` · cadastro: "
                   f"`{s.modelo_rapido}` · relatório/consulta: `{s.modelo_redacao}` · "
                   f"raciocínio: `{s.llm_reasoning_effort}`")
        tel: Telemetria = st.session_state.get("pf_telemetria")
        if tel and tel.chamadas:
            r = tel.resumo()
            st.caption(f"Nesta sessão: {r['chamadas_api']} chamadas, {r['respostas_do_cache']} "
                       f"do cache, {r['tokens_total']:,} tokens, {r['erros']} erro(s).")
        if cli.disponivel and st.button("Testar conexão com a Groq", key="pf_testar"):
            ok, msg = cli.testar_conexao()
            (st.success if ok else st.error)(msg)
    return bool(usar and cli.disponivel)


def resumo_acervo() -> dict:
    from .avaliacao import gabarito

    g = list(gabarito().values())
    return {"apolices": len(g), "seguradoras": len({x["seguradora_codigo"] for x in g}),
            "tomadoras": len({x["tomadora_codigo"] for x in g}),
            "ufs": len({x["uf"] for x in g})}


def aviso_simulacao() -> None:
    r = resumo_acervo()
    st.info(
        f"**Acervo simulado.** As {r['apolices']} apólices de demonstração são **fictícias**: "
        f"{r['seguradoras']} seguradoras inventadas, **cada uma com seu próprio modelo de "
        f"documento** (quadro no início, no fim ou em prosa; cláusulas numeradas, em romanos, "
        f"em perguntas e respostas ou bilíngues), e {r['tomadoras']} tomadoras do agronegócio "
        f"em {r['ufs']} UFs — de associações de agricultura familiar a latifúndios. Todas com "
        "marca d'água *SIMULADA*. Você também pode enviar PDF ou imagem de apólice real: a "
        "plataforma foi validada também em 5 documentos reais (3 condições gerais de D&O e 2 "
        "apólices de outro ramo, que ela reconhece e recusa).",
        icon="🧪")


@st.cache_data(ttl=60, show_spinner=False)
def _escores_cache(_versao: int) -> pd.DataFrame:
    return tabela_escores(obter_repo())


def escores() -> pd.DataFrame:
    return _escores_cache(st.session_state.get("pf_versao_base", 0))


def base_alterada() -> None:
    st.session_state["pf_versao_base"] = st.session_state.get("pf_versao_base", 0) + 1


def rotulo_nivel(n: str) -> str:
    return ROTULO_NIVEL.get(n, n)


def estilo_niveis(df: pd.DataFrame, colunas: list[str]):
    """Colore células de nível (para st.dataframe)."""
    inv = {v: k for k, v in ROTULO_NIVEL.items()}

    def cor(v: Any) -> str:
        k = inv.get(v, v)
        c = CORES_NIVEL.get(k)
        return f"color: {c}; font-weight: 600" if c else ""

    try:
        return df.style.map(cor, subset=colunas)
    except AttributeError:  # pandas < 2.1
        return df.style.applymap(cor, subset=colunas)


def arquivos_do_acervo() -> list[str]:
    pasta = APOLICES_DIR / "documentos"
    return sorted(p.name for p in pasta.iterdir()) if pasta.exists() else []


def arquivos_reais_locais() -> dict:
    """PDFs reais colocados pelo usuário em data/apolices_reais/ (fora do Git)."""
    pasta = APOLICES_DIR.parent / "apolices_reais"
    return {p.name: p for p in sorted(pasta.glob("*.pdf"))} if pasta.exists() else {}


def ler_do_acervo(nomes: list[str]) -> list[tuple[str, bytes]]:
    pasta = APOLICES_DIR / "documentos"
    return [(n, (pasta / n).read_bytes()) for n in nomes]
