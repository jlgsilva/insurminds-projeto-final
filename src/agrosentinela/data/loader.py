"""
Carregamento dos conjuntos de dados.

Estratégia de resolução (``fonte_dados`` em ``config``):

* ``curated`` — usa **apenas** os dados curados pelo ETL a partir dos
  microdados oficiais do Banco Central (``data/curated``);
* ``seed``    — usa **apenas** a amostra de demonstração (``data/seed``);
* ``auto``    — prefere os dados curados; se não existirem, cai para a
  amostra de demonstração e **avisa explicitamente na interface**.

Formatos aceitos, nesta ordem: ``.parquet`` (quando ``pyarrow`` estiver
disponível) e ``.csv.gz``. Isso permite que o ETL grave Parquet (mais
rápido e compacto) sem tornar o ``pyarrow`` uma dependência dura.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from ..config import CURATED_DIR, SEED_DIR, get_settings
from ..utils.logging_setup import get_logger
from .schemas import (
    DATASETS_OPCIONAIS,
    DATASETS_POR_NOME,
    aplicar_esquema,
    validar,
)
from . import seed_builder

log = get_logger(__name__)

NOMES_DATASETS = ("municipios", "carteira", "proagro_sinistros", "serie_credito")

# Conjuntos que enriquecem a análise sem serem obrigatórios. O aplicativo
# detecta quais existem e adapta o que oferece, em vez de exigir o ETL
# completo de dezenas de gigabytes antes da primeira tela.
NOMES_OPCIONAIS = DATASETS_OPCIONAIS

COLUNAS_DATA = {
    "carteira": [
        "dt_emissao", "dt_vencimento", "dt_inic_plantio",
        "dt_fim_plantio", "dt_inic_colheita", "dt_fim_colheita",
    ]
}


@dataclass
class BaseDados:
    """Conjunto completo de dados carregado, com procedência declarada."""

    municipios: pd.DataFrame
    carteira: pd.DataFrame
    proagro_sinistros: pd.DataFrame
    serie_credito: pd.DataFrame
    glebas: pd.DataFrame = field(default_factory=pd.DataFrame)
    exposicao: pd.DataFrame = field(default_factory=pd.DataFrame)
    contexto_externo: pd.DataFrame = field(default_factory=pd.DataFrame)
    origem: str = "desconhecida"          # "curated" | "seed"
    detalhes_origem: dict[str, str] = field(default_factory=dict)
    manifesto: dict[str, Any] = field(default_factory=dict)
    problemas: list[str] = field(default_factory=list)
    carregado_em: str = ""

    @property
    def vazia(self) -> bool:
        """
        Não há carteira nenhuma para monitorar.

        O caso que importa: alguém escolhe «Somente dados curados do BCB» sem
        ter rodado o ETL. Antes, o aplicativo respondia com um selo verde de
        "dados oficiais" e todas as telas em branco — o pior resultado
        possível, porque parecia que o sistema estava funcionando e não tinha
        nada a mostrar. Esta propriedade existe para que a interface diga o
        que de fato aconteceu.
        """
        return self.carteira is None or self.carteira.empty

    @property
    def e_demonstracao(self) -> bool:
        return self.origem != "curated"

    @property
    def precisa_de_etl(self) -> bool:
        """Pediram os dados oficiais, mas eles não existem nesta máquina."""
        return self.origem == "curated" and self.vazia

    @property
    def aviso_procedencia(self) -> str:
        if self.precisa_de_etl:
            return (
                "❌ **Os dados oficiais do BCB ainda não foram baixados nesta "
                "máquina**, por isso não há nada para mostrar.\n\n"
                "São dezenas de gigabytes e por isso não vêm no repositório. "
                "Para carregá-los, rode no terminal:\n\n"
                "`python etl/run_etl.py --anos 2025 2026`\n\n"
                "Enquanto isso, volte para **Automática** ou **Somente a "
                "amostra de demonstração** na barra lateral — a demonstração "
                "usa exatamente o mesmo formato dos dados oficiais."
            )
        if self.origem == "curated":
            return (
                "Dados curados a partir dos microdados oficiais do Sicor/Proagro "
                "(Banco Central do Brasil)."
            )
        return (
            "⚠️ Amostra de **demonstração** (dados sintéticos com o mesmo esquema "
            "dos microdados do Sicor). Execute `python etl/run_etl.py` para "
            "carregar os dados oficiais do Banco Central."
        )

    def resumo(self) -> dict[str, Any]:
        return {
            "origem": self.origem,
            "operações": len(self.carteira),
            "municípios": len(self.municipios),
            "valor_carteira": float(self.carteira["valor_credito"].sum()) if len(self.carteira) else 0.0,
            "área_ha": float(self.carteira["area_ha"].sum()) if len(self.carteira) else 0.0,
            "registros_sinistro": len(self.proagro_sinistros),
            "carregado_em": self.carregado_em,
            "problemas": self.problemas,
        }

    def como_dict(self) -> dict[str, pd.DataFrame]:
        return {
            "municipios": self.municipios,
            "carteira": self.carteira,
            "proagro_sinistros": self.proagro_sinistros,
            "serie_credito": self.serie_credito,
            "glebas": self.glebas,
            "exposicao": self.exposicao,
            "contexto_externo": self.contexto_externo,
        }

    @property
    def tem_glebas(self) -> bool:
        """Há geometria de talhão — a consulta climática ganha precisão."""
        return self.glebas is not None and not self.glebas.empty

    @property
    def tem_exposicao(self) -> bool:
        """Há saldo devedor — o risco pode ser expresso em reais."""
        return self.exposicao is not None and not self.exposicao.empty

    @property
    def tem_contexto(self) -> bool:
        """Há enriquecimento por fontes externas livres."""
        return self.contexto_externo is not None and not self.contexto_externo.empty

    def enriquecimentos(self) -> dict[str, bool]:
        """O que está disponível nesta execução — exibido na interface."""
        return {
            "Geometria de glebas": self.tem_glebas,
            "Exposição financeira": self.tem_exposicao,
            "Contexto externo": self.tem_contexto,
        }


# --------------------------------------------------------------------------
# Leitura de arquivo
# --------------------------------------------------------------------------

def _ler(diretorio: Path, nome: str) -> tuple[pd.DataFrame | None, str]:
    """Lê ``nome`` de ``diretorio`` tentando Parquet e depois CSV comprimido."""
    parquet = diretorio / f"{nome}.parquet"
    csvgz = diretorio / f"{nome}.csv.gz"
    csv = diretorio / f"{nome}.csv"

    if parquet.exists():
        try:
            return pd.read_parquet(parquet), str(parquet)
        except Exception as exc:  # noqa: BLE001 - pyarrow ausente ou arquivo corrompido
            log.warning("Falha ao ler %s (%s). Tentando CSV.", parquet.name, exc)
    for caminho in (csvgz, csv):
        if caminho.exists():
            try:
                datas = COLUNAS_DATA.get(nome, [])
                df = pd.read_csv(caminho, parse_dates=datas or None, low_memory=False)
                return df, str(caminho)
            except Exception as exc:  # noqa: BLE001
                log.warning("Falha ao ler %s (%s).", caminho.name, exc)
    return None, ""


def _diretorio_tem_dados(diretorio: Path) -> bool:
    if not diretorio.exists():
        return False
    return any(
        (diretorio / f"{n}{ext}").exists()
        for n in ("carteira", "municipios")
        for ext in (".parquet", ".csv.gz", ".csv")
    )


# --------------------------------------------------------------------------
# API pública
# --------------------------------------------------------------------------

def carregar_base(
    fonte: str | None = None,
    *,
    gerar_seed_se_faltar: bool = True,
) -> BaseDados:
    """Carrega os quatro conjuntos e devolve um :class:`BaseDados`."""
    settings = get_settings()
    fonte = (fonte or settings.fonte_dados or "auto").lower()

    diretorio: Path
    origem: str
    if fonte == "curated":
        diretorio, origem = CURATED_DIR, "curated"
    elif fonte == "seed":
        diretorio, origem = SEED_DIR, "seed"
    else:  # auto
        if _diretorio_tem_dados(CURATED_DIR):
            diretorio, origem = CURATED_DIR, "curated"
        else:
            diretorio, origem = SEED_DIR, "seed"

    if origem == "seed" and gerar_seed_se_faltar and not _diretorio_tem_dados(SEED_DIR):
        log.info("Amostra de demonstração ausente — gerando agora.")
        seed_builder.construir_seed(SEED_DIR)

    conjuntos: dict[str, pd.DataFrame] = {}
    detalhes: dict[str, str] = {}
    problemas: list[str] = []

    for nome in NOMES_DATASETS:
        df, caminho = _ler(diretorio, nome)
        if df is None:
            problemas.append(f"{nome}: arquivo não encontrado em {diretorio}")
            df = pd.DataFrame()
        else:
            detalhes[nome] = caminho
        esquema = DATASETS_POR_NOME.get(nome)
        if esquema and not df.empty:
            df = aplicar_esquema(df, esquema.colunas)
        conjuntos[nome] = df

    # Conjuntos opcionais: a ausência é normal e não vira problema de
    # validação — apenas desliga o enriquecimento correspondente.
    opcionais: dict[str, pd.DataFrame] = {}
    for nome in NOMES_OPCIONAIS:
        df, caminho = _ler(diretorio, nome)
        if df is None or df.empty:
            opcionais[nome] = pd.DataFrame()
            continue
        detalhes[nome] = caminho
        esquema = DATASETS_POR_NOME.get(nome)
        if esquema:
            df = aplicar_esquema(df, esquema.colunas)
        opcionais[nome] = df

    for nome, df in conjuntos.items():
        problemas.extend(validar(df, nome))

    manifesto: dict[str, Any] = {}
    manifesto_path = diretorio / "manifesto.json"
    if manifesto_path.exists():
        try:
            manifesto = json.loads(manifesto_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    base = BaseDados(
        municipios=conjuntos["municipios"],
        carteira=conjuntos["carteira"],
        proagro_sinistros=conjuntos["proagro_sinistros"],
        serie_credito=conjuntos["serie_credito"],
        glebas=opcionais.get("glebas", pd.DataFrame()),
        exposicao=opcionais.get("exposicao", pd.DataFrame()),
        contexto_externo=opcionais.get("contexto_externo", pd.DataFrame()),
        origem=origem,
        detalhes_origem=detalhes,
        manifesto=manifesto,
        problemas=problemas,
        carregado_em=datetime.now().isoformat(timespec="seconds"),
    )

    # Garante coordenadas na carteira mesmo que o ETL não as tenha trazido.
    base.carteira = _completar_geo(base.carteira, base.municipios)
    ativos = [k for k, v in base.enriquecimentos().items() if v]
    log.info(
        "Base carregada (%s): %d operações, %d municípios, %d registros de "
        "sinistro. Enriquecimentos ativos: %s.",
        origem, len(base.carteira), len(base.municipios),
        len(base.proagro_sinistros), ", ".join(ativos) or "nenhum",
    )
    if problemas:
        for p in problemas:
            log.warning("Validação: %s", p)
    return base


def completar_colunas(
    df: pd.DataFrame,
    referencia: pd.DataFrame,
    *,
    chave: str = "cd_ibge",
    colunas: Sequence[str] = ("municipio", "uf", "lat", "lon"),
) -> pd.DataFrame:
    """
    Traz de ``referencia`` apenas as colunas que **faltam** em ``df``.

    Existe para evitar um defeito específico e traiçoeiro do pandas: juntar
    dois quadros que já têm a mesma coluna produz ``lat_x`` e ``lat_y``, e a
    coluna ``lat`` **deixa de existir**. O código seguinte quebra com
    ``KeyError: ['lat', 'lon']``, e a mensagem não diz nada sobre a junção
    que causou o problema — foi exatamente assim que a página de dados
    externos caiu.

    Aqui a junção só acontece para o que falta de fato; se o quadro já tem
    tudo, ele volta intacto e nenhuma coluna é renomeada.
    """
    if df is None or df.empty:
        return df
    if referencia is None or referencia.empty or chave not in referencia.columns:
        return df
    if chave not in df.columns:
        return df

    faltando = [c for c in colunas
                if c not in df.columns or df[c].isna().all()]
    if not faltando:
        return df

    # Remove as colunas totalmente vazias antes de juntar, para que a versão
    # da referência ocupe o lugar sem gerar sufixo.
    saida = df.drop(columns=[c for c in faltando if c in df.columns])
    disponiveis = [c for c in faltando if c in referencia.columns]
    if not disponiveis:
        return df
    ref = referencia[[chave, *disponiveis]].drop_duplicates(subset=[chave])
    return saida.merge(ref, on=chave, how="left")


def _completar_geo(carteira: pd.DataFrame, municipios: pd.DataFrame) -> pd.DataFrame:
    """Preenche lat/lon/município/UF ausentes na carteira via código IBGE."""
    if carteira.empty or municipios.empty:
        return carteira
    faltando = carteira["lat"].isna() | carteira["lon"].isna() if "lat" in carteira.columns else None
    if faltando is None or not bool(faltando.any()):
        return carteira

    ref = municipios.set_index("cd_ibge")[["municipio", "uf", "regiao", "lat", "lon"]]
    out = carteira.copy()
    idx = out.index[faltando]
    for col in ("municipio", "uf", "regiao", "lat", "lon"):
        valores = out.loc[idx, "cd_ibge"].map(ref[col])
        out.loc[idx, col] = out.loc[idx, col].where(out.loc[idx, col].notna(), valores)
    return out


def estatisticas_carteira(carteira: pd.DataFrame) -> dict[str, Any]:
    """Indicadores agregados usados no painel executivo."""
    if carteira.empty:
        return {}
    return {
        "n_operacoes": int(len(carteira)),
        "valor_total": float(carteira["valor_credito"].sum()),
        "valor_medio": float(carteira["valor_credito"].mean()),
        "area_total": float(carteira["area_ha"].sum()),
        "n_municipios": int(carteira["cd_ibge"].nunique()),
        "n_ufs": int(carteira["uf"].nunique()),
        "n_culturas": int(carteira["cultura"].nunique()),
        "pct_coberto": float(carteira["tem_cobertura"].mean() * 100),
        "valor_descoberto": float(carteira.loc[~carteira["tem_cobertura"], "valor_credito"].sum()),
        "n_instituicoes": int(carteira["instituicao"].nunique()),
    }


def indices_sinistralidade(sinistros: pd.DataFrame) -> pd.DataFrame:
    """
    Consolida o histórico de Proagro por município × evento, produzindo:

    * ``freq_evento``       — participação do evento nos acionamentos;
    * ``taxa_acionamento``  — acionamentos por operação;
    * ``severidade_media``  — indenização média por comprovação.
    """
    if sinistros.empty:
        return pd.DataFrame(
            columns=["cd_ibge", "evento", "freq_evento", "taxa_acionamento", "severidade_media"]
        )
    agg = (
        sinistros.groupby(["cd_ibge", "evento"], as_index=False)
        .agg(
            n_cop=("n_cop", "sum"),
            n_rcp=("n_rcp", "sum"),
            n_operacoes=("n_operacoes", "sum"),
            valor_indenizado=("valor_indenizado", "sum"),
        )
    )
    total_muni = agg.groupby("cd_ibge")["n_cop"].transform("sum")
    agg["freq_evento"] = (agg["n_cop"] / total_muni.replace(0, pd.NA)).fillna(0.0).astype(float).round(4)
    agg["taxa_acionamento"] = (
        (agg["n_cop"] / agg["n_operacoes"].replace(0, pd.NA)).fillna(0.0).astype(float).round(4)
    )
    agg["severidade_media"] = (
        (agg["valor_indenizado"] / agg["n_rcp"].replace(0, pd.NA)).fillna(0.0).astype(float).round(2)
    )
    return agg
