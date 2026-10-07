"""
Infraestrutura comum dos conectores de dados externos.

Todo conector aqui obedece ao mesmo contrato, porque o aplicativo precisa
funcionar em três situações e **nunca** pode quebrar em nenhuma delas:

1. **Com rede** — consulta a API pública e guarda em cache.
2. **Sem rede, com cache** — reaproveita a última resposta boa.
3. **Sem rede e sem cache** — devolve a tabela embutida de referência,
   **sempre rotulada como tal na interface**.

O terceiro caso é o que permite publicar a solução no Streamlit Cloud com
plano gratuito e avaliá-la offline sem que nenhuma página fique em branco.
A honestidade é preservada por construção: ``ResultadoExterno.origem``
acompanha o dado até a tela, e a interface mostra o selo de procedência.

Nenhum conector exige chave de API. Nenhum conector é obrigatório: falha de
um não interrompe o pipeline — apenas remove o enriquecimento que ele traria.
"""

from __future__ import annotations

import hashlib
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from ..config import DATA_DIR
from ..utils.logging_setup import get_logger

log = get_logger(__name__)

CACHE_DIR = DATA_DIR / "cache_externo"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

ORIGEM_REDE = "rede"
ORIGEM_CACHE = "cache"
ORIGEM_OFFLINE = "referência embutida"

TIMEOUT_PADRAO = 20
TTL_PADRAO_MIN = 60 * 24          # dados externos mudam devagar


@dataclass
class ResultadoExterno:
    """Resposta de um conector, com procedência declarada."""

    dados: pd.DataFrame
    fonte: str
    origem: str = ORIGEM_OFFLINE
    mensagem: str = ""
    consultado_em: str = ""
    parametros: dict[str, Any] = field(default_factory=dict)

    @property
    def vazio(self) -> bool:
        return self.dados is None or self.dados.empty

    @property
    def ao_vivo(self) -> bool:
        return self.origem == ORIGEM_REDE

    @property
    def selo(self) -> str:
        """Rótulo curto exibido junto do número na interface."""
        return {
            ORIGEM_REDE: "🟢 ao vivo",
            ORIGEM_CACHE: "🟡 cache",
            ORIGEM_OFFLINE: "⚪ referência",
        }.get(self.origem, "⚪ referência")

    def resumo(self) -> dict[str, Any]:
        return {
            "fonte": self.fonte,
            "origem": self.origem,
            "linhas": 0 if self.vazio else int(len(self.dados)),
            "mensagem": self.mensagem,
            "consultado_em": self.consultado_em,
        }


def _agora() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


class ConectorExterno(ABC):
    """
    Base dos conectores.

    Subclasses implementam ``_buscar`` (a chamada de rede) e ``_offline``
    (a tabela embutida). A classe base cuida de cache, timeout, tratamento
    de erro e rotulagem de procedência — nenhum conector repete essa lógica.
    """

    chave: str = ""
    nome: str = ""
    ttl_min: int = TTL_PADRAO_MIN

    def __init__(self, *, timeout: int = TIMEOUT_PADRAO, offline: bool = False) -> None:
        self.timeout = timeout
        self.offline = offline

    # ------------------------------------------------------------ público
    def obter(self, **params: Any) -> ResultadoExterno:
        """Fluxo completo: cache → rede → cache antigo → tabela embutida."""
        caminho = self._caminho_cache(params)
        em_cache = self._ler_cache(caminho)
        if em_cache is not None:
            return ResultadoExterno(
                dados=pd.DataFrame(em_cache["dados"]),
                fonte=self.nome, origem=ORIGEM_CACHE,
                mensagem="resposta em cache ainda válida",
                consultado_em=em_cache.get("consultado_em", ""),
                parametros=params,
            )

        if not self.offline:
            try:
                df = self._buscar(**params)
                if df is not None and not df.empty:
                    self._gravar_cache(caminho, df)
                    return ResultadoExterno(
                        dados=df, fonte=self.nome, origem=ORIGEM_REDE,
                        mensagem="consulta bem-sucedida",
                        consultado_em=_agora(), parametros=params,
                    )
                log.info("%s: resposta vazia; usando referência embutida.", self.chave)
            except Exception as exc:  # noqa: BLE001 — indisponibilidade é esperada
                log.info("%s indisponível (%s); usando referência embutida.",
                         self.chave, type(exc).__name__)

        antigo = self._ler_cache(caminho, ignorar_ttl=True)
        if antigo is not None:
            return ResultadoExterno(
                dados=pd.DataFrame(antigo["dados"]),
                fonte=self.nome, origem=ORIGEM_CACHE,
                mensagem="fonte indisponível — usando a última resposta guardada",
                consultado_em=antigo.get("consultado_em", ""),
                parametros=params,
            )

        return ResultadoExterno(
            dados=self._offline(**params), fonte=self.nome, origem=ORIGEM_OFFLINE,
            mensagem="fonte indisponível — valores de referência embutidos, "
                     "úteis para demonstração e não para decisão operacional",
            consultado_em=_agora(), parametros=params,
        )

    def disponivel(self) -> bool:
        """Sonda barata, usada pela página de diagnóstico."""
        if self.offline:
            return False
        try:
            df = self._buscar(**self._params_sonda())
            return df is not None and not df.empty
        except Exception:  # noqa: BLE001
            return False

    # ------------------------------------------------------- a implementar
    @abstractmethod
    def _buscar(self, **params: Any) -> pd.DataFrame:
        ...

    @abstractmethod
    def _offline(self, **params: Any) -> pd.DataFrame:
        ...

    def _params_sonda(self) -> dict[str, Any]:
        return {}

    # ------------------------------------------------------------- helpers
    def _caminho_cache(self, params: dict[str, Any]) -> Path:
        bruto = json.dumps({"c": self.chave, "p": params}, sort_keys=True, default=str)
        h = hashlib.sha256(bruto.encode("utf-8")).hexdigest()[:16]
        return CACHE_DIR / f"{self.chave}_{h}.json"

    def _ler_cache(self, caminho: Path, *, ignorar_ttl: bool = False) -> dict | None:
        if not caminho.exists():
            return None
        try:
            if not ignorar_ttl:
                idade_min = (time.time() - caminho.stat().st_mtime) / 60
                if idade_min > self.ttl_min:
                    return None
            return json.loads(caminho.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return None

    def _gravar_cache(self, caminho: Path, df: pd.DataFrame) -> None:
        try:
            caminho.write_text(
                json.dumps(
                    {"consultado_em": _agora(),
                     "dados": df.to_dict(orient="records")},
                    ensure_ascii=False, default=str,
                ),
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001
            log.debug("Falha ao gravar cache de %s: %s", self.chave, exc)

    def _get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        import requests  # import tardio: o núcleo funciona sem rede

        resp = requests.get(url, params=params, timeout=self.timeout,
                            headers={"User-Agent": "AgroSentinela/1.0 (POC academica)"})
        resp.raise_for_status()
        return resp.json()

    def _get_texto(self, url: str, params: dict[str, Any] | None = None) -> str:
        import requests

        resp = requests.get(url, params=params, timeout=self.timeout,
                            headers={"User-Agent": "AgroSentinela/1.0 (POC academica)"})
        resp.raise_for_status()
        resp.encoding = resp.encoding or "utf-8"
        return resp.text

    def _get_csv(self, url: str, params: dict[str, Any] | None = None,
                 **kwargs: Any) -> pd.DataFrame:
        import io

        texto = self._get_texto(url, params)
        return pd.read_csv(io.StringIO(texto), **kwargs)
