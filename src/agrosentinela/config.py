"""
Configuração central do AgroSentinela.

Todas as credenciais são lidas de variáveis de ambiente ou de
``st.secrets`` (Streamlit Cloud). **Nenhuma chave é versionada.**

Ordem de resolução de segredos:
    1. ``st.secrets`` (quando executando dentro do Streamlit)
    2. variáveis de ambiente do processo
    3. arquivo ``.env`` na raiz do projeto (carregado manualmente, sem
       dependência externa obrigatória)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------
# Caminhos do projeto
# --------------------------------------------------------------------------

PACKAGE_DIR = Path(__file__).resolve().parent
SRC_DIR = PACKAGE_DIR.parent
ROOT_DIR = SRC_DIR.parent

DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"          # microdados brutos do BCB (não versionado)
CURATED_DIR = DATA_DIR / "curated"  # parquet/csv.gz gerados pelo ETL
SEED_DIR = DATA_DIR / "seed"        # amostra de demonstração versionada
DOCS_DIR = ROOT_DIR / "docs"
RULES_DIR = PACKAGE_DIR / "rules"
ARTEFATOS_DIR = ROOT_DIR / "Desafio5_Artefatos"
ARTEFATOS_PF_DIR = ROOT_DIR / "Projeto_Final_Artefatos"
APOLICES_DIR = DATA_DIR / "apolices_simuladas"

for _d in (RAW_DIR, CURATED_DIR, SEED_DIR):
    _d.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------
# Leitura de segredos (.env sem dependência de python-dotenv)
# --------------------------------------------------------------------------

def _load_dotenv_once() -> None:
    """Carrega ``.env`` para ``os.environ`` sem sobrescrever o que já existe."""
    if getattr(_load_dotenv_once, "_done", False):
        return
    _load_dotenv_once._done = True  # type: ignore[attr-defined]
    env_file = ROOT_DIR / ".env"
    if not env_file.exists():
        return
    try:
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)
    except OSError:
        pass


def get_secret(name: str, default: Any = None) -> Any:
    """Busca um segredo em st.secrets -> os.environ -> .env -> default."""
    _load_dotenv_once()

    # 1) Streamlit secrets (import tardio: o core roda fora do Streamlit)
    try:  # pragma: no cover - depende do runtime
        import streamlit as st  # type: ignore

        try:
            if name in st.secrets:
                return st.secrets[name]
        except Exception:
            # st.secrets levanta se não houver secrets.toml configurado
            pass
    except ModuleNotFoundError:
        pass

    return os.environ.get(name, default)


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "sim", "on"}


def _as_int(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------
# Catálogo de modelos Groq (camada gratuita)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ModelSpec:
    """Metadados de um modelo da GroqCloud."""

    id: str
    rotulo: str
    contexto: int
    tool_calling: bool
    perfil: str  # "qualidade" | "equilibrio" | "velocidade"
    observacao: str = ""


# Fonte: https://console.groq.com/docs/models (consultada em 06/10/2026).
#
# Atenção à mudança de catálogo: os modelos Llama 3.x passaram a ser
# oferecidos na Groq apenas no plano *Enterprise* ("Contact Sales"). Os padrões
# do projeto foram migrados para a família **GPT-OSS**, que está em
# *produção* (não é "preview") — portanto sem risco de descontinuação súbita —
# e disponível no plano gratuito/desenvolvedor. Modelos em *preview* (ex.:
# qwen/qwen3.8-27b) foram deliberadamente evitados, porque a própria Groq
# avisa que podem ser descontinuados a qualquer momento.
MODELOS_GROQ: tuple[ModelSpec, ...] = (
    ModelSpec(
        id="openai/gpt-oss-120b",
        rotulo="GPT-OSS 120B",
        contexto=131_072,
        tool_calling=True,
        perfil="qualidade",
        observacao="Modelo de produção com raciocínio. Padrão para redação, "
                   "extração de cláusulas, relatórios e copiloto.",
    ),
    ModelSpec(
        id="openai/gpt-oss-20b",
        rotulo="GPT-OSS 20B",
        contexto=131_072,
        tool_calling=True,
        perfil="velocidade",
        observacao="Produção, ~1000 tok/s e metade do custo de cota. Padrão "
                   "para triagem, revisão e extração de dados cadastrais.",
    ),
    ModelSpec(
        id="llama-3.3-70b-versatile",
        rotulo="Llama 3.3 70B (Enterprise)",
        contexto=131_072,
        tool_calling=True,
        perfil="qualidade",
        observacao="Disponível apenas no plano Enterprise da Groq desde 2026.",
    ),
)

MODELOS_POR_ID = {m.id: m for m in MODELOS_GROQ}


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------

@dataclass
class Settings:
    """Configuração efetiva da aplicação."""

    # --- LLM -------------------------------------------------------------
    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    modelo_redacao: str = "openai/gpt-oss-120b"
    modelo_rapido: str = "openai/gpt-oss-20b"
    modelo_copiloto: str = "openai/gpt-oss-120b"
    modelo_extracao: str = "openai/gpt-oss-120b"
    # Esforço de raciocínio dos modelos GPT-OSS ("low" | "medium" | "high").
    # "low" é suficiente para redação e extração guiada por esquema, e poupa
    # a cota de tokens por minuto do plano gratuito.
    llm_reasoning_effort: str = "low"
    llm_temperatura: float = 0.35
    # Modelos com raciocínio gastam tokens "pensando" antes de responder; o
    # teto precisa comportar o raciocínio + a resposta.
    llm_max_tokens: int = 2048
    llm_timeout_s: int = 45
    llm_max_retries: int = 3
    llm_cache_ativo: bool = True
    # Guarda-corpo de cota gratuita: nº máximo de chamadas por execução do pipeline
    llm_max_chamadas_por_run: int = 40

    # --- Clima -----------------------------------------------------------
    open_meteo_forecast_url: str = "https://api.open-meteo.com/v1/forecast"
    open_meteo_archive_url: str = "https://archive-api.open-meteo.com/v1/archive"
    dias_previsao: int = 10
    timezone: str = "America/Sao_Paulo"
    clima_timeout_s: int = 30
    clima_max_municipios: int = 250  # guarda-corpo de cota da API pública
    clima_cache_ttl_min: int = 60

    # --- Dados -----------------------------------------------------------
    fonte_dados: str = "auto"  # auto | curated | seed
    bcb_base_sicor: str = "https://www.bcb.gov.br/htms/sicor"
    bcb_base_dados_brutos: str = "https://www.bcb.gov.br/htms/sicor/DadosBrutos"

    # --- Operacional ------------------------------------------------------
    outbox_db: Path = field(default_factory=lambda: DATA_DIR / "outbox.sqlite")
    log_level: str = "INFO"
    modo_simulacao: bool = True  # NUNCA envia mensagem real (requisito do desafio)

    # ---------------------------------------------------------------------
    @property
    def llm_disponivel(self) -> bool:
        return bool(self.groq_api_key)

    def resumo_publico(self) -> dict[str, Any]:
        """Resumo sem segredos, seguro para exibir na interface."""
        return {
            "modelo_redacao": self.modelo_redacao,
            "modelo_rapido": self.modelo_rapido,
            "modelo_copiloto": self.modelo_copiloto,
            "modelo_extracao": self.modelo_extracao,
            "llm_configurado": self.llm_disponivel,
            "fonte_dados": self.fonte_dados,
            "dias_previsao": self.dias_previsao,
            "timezone": self.timezone,
            "modo_simulacao": self.modo_simulacao,
            "limite_municipios_clima": self.clima_max_municipios,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Instância única de Settings resolvida a partir do ambiente."""
    return Settings(
        groq_api_key=get_secret("GROQ_API_KEY") or None,
        groq_base_url=get_secret("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
        modelo_redacao=get_secret("GROQ_MODEL_REDACAO", "openai/gpt-oss-120b"),
        modelo_rapido=get_secret("GROQ_MODEL_RAPIDO", "openai/gpt-oss-20b"),
        modelo_copiloto=get_secret("GROQ_MODEL_COPILOTO", "openai/gpt-oss-120b"),
        modelo_extracao=get_secret("GROQ_MODEL_EXTRACAO", "openai/gpt-oss-120b"),
        llm_reasoning_effort=str(get_secret("LLM_REASONING_EFFORT", "low")).lower(),
        llm_temperatura=_as_float(get_secret("LLM_TEMPERATURA"), 0.35),
        llm_max_tokens=_as_int(get_secret("LLM_MAX_TOKENS"), 2048),
        llm_timeout_s=_as_int(get_secret("LLM_TIMEOUT_S"), 45),
        llm_max_retries=_as_int(get_secret("LLM_MAX_RETRIES"), 3),
        llm_cache_ativo=_as_bool(get_secret("LLM_CACHE_ATIVO"), True),
        llm_max_chamadas_por_run=_as_int(get_secret("LLM_MAX_CHAMADAS_POR_RUN"), 40),
        dias_previsao=_as_int(get_secret("DIAS_PREVISAO"), 10),
        timezone=get_secret("TIMEZONE", "America/Sao_Paulo"),
        clima_max_municipios=_as_int(get_secret("CLIMA_MAX_MUNICIPIOS"), 250),
        fonte_dados=str(get_secret("FONTE_DADOS", "auto")).lower(),
        log_level=str(get_secret("LOG_LEVEL", "INFO")).upper(),
        modo_simulacao=_as_bool(get_secret("MODO_SIMULACAO"), True),
    )


def reset_settings_cache() -> None:
    """Permite recarregar a configuração após alteração em runtime (UI)."""
    get_settings.cache_clear()
