"""
Integração com fontes públicas de dados meteorológicos.

Fonte primária: **Open-Meteo** (https://open-meteo.com) — API pública,
gratuita e **sem necessidade de chave** para uso não comercial, o que a
torna adequada a uma prova de conceito publicada no Streamlit Cloud.

Boas práticas implementadas:

* **Deduplicação por célula de grade** — municípios vizinhos caem na mesma
  célula (~11 km); consultamos a célula uma única vez.
* **Requisições em lote** — a Open-Meteo aceita listas de coordenadas em uma
  única chamada, reduzindo drasticamente o número de requisições.
* **Retry com backoff exponencial** e timeout explícito.
* **Cache em disco com TTL**, para não repetir chamadas durante a mesma
  sessão de trabalho.
* **Provedor sintético** determinístico, para demonstrar o fluxo completo
  sem rede (ambientes offline, avaliação e testes automatizados).
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Protocol, Sequence

from ..config import DATA_DIR, get_settings
from ..utils.logging_setup import get_logger

log = get_logger(__name__)

CACHE_DIR = DATA_DIR / "cache_clima"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Variáveis diárias solicitadas à Open-Meteo.
DAILY_VARS = [
    "temperature_2m_max",
    "temperature_2m_min",
    "temperature_2m_mean",
    "precipitation_sum",
    "rain_sum",
    "precipitation_hours",
    "precipitation_probability_max",
    "wind_speed_10m_max",
    "wind_gusts_10m_max",
    "shortwave_radiation_sum",
    "et0_fao_evapotranspiration",
    "relative_humidity_2m_mean",
    "relative_humidity_2m_min",
]

HOURLY_VARS = ["cape"]

# Cenários que o provedor sintético sabe injetar. Um nome fora desta lista
# não injeta nada e produziria, silenciosamente, uma "demonstração" idêntica
# à linha de base — erro difícil de perceber e fácil de propagar para o
# relatório. Por isso o provedor avisa em vez de ignorar.
CENARIOS_SINTETICOS: tuple[str, ...] = (
    "seca", "chuva_excessiva", "chuva_intensa", "granizo",
    "geada", "onda_calor", "vendaval",
)

COLUNAS_SAIDA = [
    "cell_id",
    "data",
    "tmax",
    "tmin",
    "tmed",
    "precipitacao",
    "chuva",
    "horas_chuva",
    "prob_precipitacao",
    "vento_medio",
    "rajada",
    "radiacao",
    "et0",
    "umidade_media",
    "umidade_min",
    "cape_max",
]


# ==========================================================================
# Célula de grade
# ==========================================================================

@dataclass(frozen=True)
class Celula:
    """Célula de grade meteorológica (agrupa municípios próximos)."""

    lat: float
    lon: float

    @property
    def id(self) -> str:
        return f"{self.lat:+06.2f}_{self.lon:+07.2f}"


def para_celula(lat: float, lon: float, resolucao: float = 0.1) -> Celula:
    """Arredonda coordenadas para o centro da célula de grade."""
    return Celula(
        lat=round(round(float(lat) / resolucao) * resolucao, 2),
        lon=round(round(float(lon) / resolucao) * resolucao, 2),
    )


# ==========================================================================
# Protocolo de provedor
# ==========================================================================

class ClimaProvider(Protocol):
    """Contrato de um provedor de séries meteorológicas diárias."""

    nome: str

    def series_diarias(
        self,
        celulas: Sequence[Celula],
        *,
        dias_passados: int,
        dias_previsao: int,
    ) -> "list[dict[str, Any]]":
        """Devolve uma lista de registros diários por célula."""
        ...


# ==========================================================================
# Cache simples em disco
# ==========================================================================

def _chave_cache(prefixo: str, payload: Any) -> Path:
    bruto = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    h = hashlib.sha256(bruto).hexdigest()[:20]
    return CACHE_DIR / f"{prefixo}_{h}.json"


def _ler_cache(caminho: Path, ttl_min: int) -> Any | None:
    if not caminho.exists():
        return None
    idade_min = (time.time() - caminho.stat().st_mtime) / 60.0
    if idade_min > ttl_min:
        return None
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _gravar_cache(caminho: Path, dados: Any) -> None:
    try:
        caminho.write_text(json.dumps(dados, default=str), encoding="utf-8")
    except OSError:  # pragma: no cover
        log.debug("Não foi possível gravar cache em %s", caminho)


# ==========================================================================
# Provedor Open-Meteo
# ==========================================================================

class OpenMeteoProvider:
    """Cliente da API pública Open-Meteo (previsão + histórico recente)."""

    nome = "Open-Meteo"
    fonte_url = "https://open-meteo.com/"
    licenca = "CC-BY 4.0 (uso não comercial sem chave de API)"
    TAMANHO_LOTE = 40

    def __init__(self, tamanho_lote: int | None = None) -> None:
        self.settings = get_settings()
        self.tamanho_lote = tamanho_lote or self.TAMANHO_LOTE

    # ------------------------------------------------------------------ api
    def series_diarias(
        self,
        celulas: Sequence[Celula],
        *,
        dias_passados: int = 21,
        dias_previsao: int = 10,
    ) -> list[dict[str, Any]]:
        if not celulas:
            return []
        registros: list[dict[str, Any]] = []
        lotes = [
            list(celulas[i : i + self.tamanho_lote])
            for i in range(0, len(celulas), self.tamanho_lote)
        ]
        for i, lote in enumerate(lotes, start=1):
            log.info("Open-Meteo: lote %d/%d (%d células)", i, len(lotes), len(lote))
            try:
                registros.extend(self._consultar_lote(lote, dias_passados, dias_previsao))
            except Exception as exc:  # noqa: BLE001
                log.warning("Falha no lote %d (%s). Usando fallback sintético.", i, exc)
                registros.extend(
                    SinteticoProvider().series_diarias(
                        lote, dias_passados=dias_passados, dias_previsao=dias_previsao
                    )
                )
        return registros

    # -------------------------------------------------------------- interno
    def _consultar_lote(
        self, lote: Sequence[Celula], dias_passados: int, dias_previsao: int
    ) -> list[dict[str, Any]]:
        params = {
            "latitude": ",".join(f"{c.lat:.2f}" for c in lote),
            "longitude": ",".join(f"{c.lon:.2f}" for c in lote),
            "daily": ",".join(DAILY_VARS),
            "hourly": ",".join(HOURLY_VARS),
            "timezone": self.settings.timezone,
            "past_days": int(max(0, min(dias_passados, 92))),
            "forecast_days": int(max(1, min(dias_previsao, 16))),
            "wind_speed_unit": "kmh",
            "precipitation_unit": "mm",
            "temperature_unit": "celsius",
        }
        cache_path = _chave_cache("om", params)
        bruto = _ler_cache(cache_path, self.settings.clima_cache_ttl_min)
        if bruto is None:
            bruto = self._get(self.settings.open_meteo_forecast_url, params)
            _gravar_cache(cache_path, bruto)
        else:
            log.debug("Cache de clima reaproveitado (%s)", cache_path.name)

        blocos = bruto if isinstance(bruto, list) else [bruto]
        registros: list[dict[str, Any]] = []
        for celula, bloco in zip(lote, blocos):
            registros.extend(self._normalizar(celula, bloco))
        return registros

    def _get(self, url: str, params: dict[str, Any]) -> Any:
        import requests  # import tardio: mantém o core utilizável sem rede

        ultima_exc: Exception | None = None
        for tentativa in range(1, 4):
            try:
                resp = requests.get(url, params=params, timeout=self.settings.clima_timeout_s)
                resp.raise_for_status()
                return resp.json()
            except Exception as exc:  # noqa: BLE001
                ultima_exc = exc
                espera = min(2 ** tentativa, 8)
                log.warning("Open-Meteo tentativa %d falhou (%s). Aguardando %ss.", tentativa, exc, espera)
                time.sleep(espera)
        raise RuntimeError(f"Open-Meteo indisponível: {ultima_exc}")

    @staticmethod
    def _normalizar(celula: Celula, bloco: dict[str, Any]) -> list[dict[str, Any]]:
        daily = (bloco or {}).get("daily") or {}
        datas = daily.get("time") or []
        if not datas:
            return []

        # CAPE horário -> máximo diário
        cape_por_dia: dict[str, float] = {}
        hourly = (bloco or {}).get("hourly") or {}
        horas = hourly.get("time") or []
        capes = hourly.get("cape") or []
        for t, v in zip(horas, capes):
            if v is None:
                continue
            dia = str(t)[:10]
            cape_por_dia[dia] = max(cape_por_dia.get(dia, 0.0), float(v))

        def col(nome: str) -> list[Any]:
            return daily.get(nome) or [None] * len(datas)

        saida = []
        for i, dia in enumerate(datas):
            saida.append(
                {
                    "cell_id": celula.id,
                    "lat": celula.lat,
                    "lon": celula.lon,
                    "data": str(dia)[:10],
                    "tmax": _f(col("temperature_2m_max")[i]),
                    "tmin": _f(col("temperature_2m_min")[i]),
                    "tmed": _f(col("temperature_2m_mean")[i]),
                    "precipitacao": _f(col("precipitation_sum")[i], 0.0),
                    "chuva": _f(col("rain_sum")[i], 0.0),
                    "horas_chuva": _f(col("precipitation_hours")[i], 0.0),
                    "prob_precipitacao": _f(col("precipitation_probability_max")[i], 0.0),
                    "vento_medio": _f(col("wind_speed_10m_max")[i], 0.0),
                    "rajada": _f(col("wind_gusts_10m_max")[i], 0.0),
                    "radiacao": _f(col("shortwave_radiation_sum")[i], 0.0),
                    "et0": _f(col("et0_fao_evapotranspiration")[i], 0.0),
                    "umidade_media": _f(col("relative_humidity_2m_mean")[i]),
                    "umidade_min": _f(col("relative_humidity_2m_min")[i]),
                    "cape_max": cape_por_dia.get(str(dia)[:10], 0.0),
                    "fonte": "open-meteo",
                }
            )
        return saida


def _f(valor: Any, default: float | None = None) -> float | None:
    try:
        if valor is None:
            return default
        v = float(valor)
        return v if not math.isnan(v) else default
    except (TypeError, ValueError):
        return default


# ==========================================================================
# Provedor sintético (offline / demonstração / testes)
# ==========================================================================

class SinteticoProvider:
    """
    Gera séries meteorológicas **determinísticas e fisicamente plausíveis**.

    Serve para três finalidades legítimas:

    1. permitir a demonstração completa do fluxo sem acesso à internet;
    2. tornar os testes automatizados reprodutíveis;
    3. alimentar o modo "cenário" da interface, no qual o usuário força um
       evento (seca, geada, granizo...) para ver a regra e a mensagem
       correspondentes.

    O gerador combina: sazonalidade anual, gradiente latitudinal, ruído
    pseudoaleatório reprodutível (semente derivada da célula) e, quando
    solicitado, a injeção de um cenário extremo.
    """

    nome = "Sintético (demonstração)"
    fonte_url = "interno"
    licenca = "—"

    def __init__(self, cenario: str | None = None, intensidade: float = 1.0) -> None:
        self.cenario = cenario
        self.intensidade = float(intensidade)
        if cenario and cenario not in CENARIOS_SINTETICOS:
            log.warning(
                "Cenário '%s' desconhecido — nenhum evento será injetado e a "
                "série ficará igual à linha de base. Cenários válidos: %s.",
                cenario, ", ".join(CENARIOS_SINTETICOS),
            )

    def series_diarias(
        self,
        celulas: Sequence[Celula],
        *,
        dias_passados: int = 21,
        dias_previsao: int = 10,
    ) -> list[dict[str, Any]]:
        hoje = date.today()
        inicio = hoje - timedelta(days=dias_passados)
        total = dias_passados + dias_previsao
        registros: list[dict[str, Any]] = []

        for celula in celulas:
            semente = int(hashlib.sha256(celula.id.encode()).hexdigest()[:8], 16)
            rng = random.Random(semente)
            # Regime climático aproximado por latitude
            lat = celula.lat
            base_temp = 27.0 + (lat + 15.0) * 0.28   # mais frio ao sul
            amplitude_sazonal = 3.0 + abs(lat) * 0.22
            chance_chuva_base = 0.42 if lat > -18 else 0.34

            for d in range(total):
                dia = inicio + timedelta(days=d)
                doy = dia.timetuple().tm_yday
                # Verão no hemisfério sul em torno do dia 15
                sazonal = math.cos(2 * math.pi * (doy - 15) / 365.25)
                tmed = base_temp + amplitude_sazonal * sazonal + rng.gauss(0, 2.0)
                amplitude_dia = rng.uniform(7.5, 13.0)
                tmax = tmed + amplitude_dia / 2
                tmin = tmed - amplitude_dia / 2

                chove = rng.random() < (chance_chuva_base + 0.16 * sazonal)
                prec = round(abs(rng.lognormvariate(1.7, 0.95)), 1) if chove else 0.0
                prec = min(prec, 95.0)

                rajada = max(8.0, rng.gauss(28, 11))
                cape = max(0.0, rng.gauss(620, 420)) if chove else max(0.0, rng.gauss(180, 150))
                umid = min(98.0, max(28.0, rng.gauss(72 if chove else 58, 9)))
                et0 = max(0.6, 1.4 + 0.14 * max(tmax, 0) + rng.gauss(0, 0.5) - (1.1 if chove else 0))

                reg = {
                    "cell_id": celula.id,
                    "lat": celula.lat,
                    "lon": celula.lon,
                    "data": dia.isoformat(),
                    "tmax": round(tmax, 1),
                    "tmin": round(tmin, 1),
                    "tmed": round(tmed, 1),
                    "precipitacao": prec,
                    "chuva": prec,
                    "horas_chuva": round(min(14.0, prec / 4.5), 1) if chove else 0.0,
                    "prob_precipitacao": round(min(97.0, 18 + prec * 3.2), 0),
                    "vento_medio": round(max(4.0, rajada * 0.55), 1),
                    "rajada": round(rajada, 1),
                    "radiacao": round(max(4.0, rng.gauss(20, 5)), 1),
                    "et0": round(et0, 2),
                    "umidade_media": round(umid, 1),
                    "umidade_min": round(max(15.0, umid - rng.uniform(12, 26)), 1),
                    "cape_max": round(cape, 0),
                    "fonte": "sintetico",
                }
                registros.append(reg)

            if self.cenario:
                self._injetar_cenario(registros, celula, hoje, dias_previsao)

        return registros

    # ------------------------------------------------------------- cenários
    def _injetar_cenario(
        self,
        registros: list[dict[str, Any]],
        celula: Celula,
        hoje: date,
        dias_previsao: int,
    ) -> None:
        """Força um evento extremo nos registros futuros da célula."""
        alvo = [r for r in registros if r["cell_id"] == celula.id]
        futuros = [r for r in alvo if r["data"] >= hoje.isoformat()]
        passados = [r for r in alvo if r["data"] < hoje.isoformat()]
        k = self.intensidade

        if self.cenario == "seca":
            for r in passados[-25:] + futuros:
                r["precipitacao"] = 0.0
                r["chuva"] = 0.0
                r["horas_chuva"] = 0.0
                r["prob_precipitacao"] = 5.0
                r["umidade_media"] = round(max(22.0, 40 - 6 * k), 1)
                r["umidade_min"] = round(max(12.0, 24 - 6 * k), 1)
                r["et0"] = round(min(9.5, r["et0"] + 1.8 * k), 2)
                r["tmax"] = round(r["tmax"] + 2.5 * k, 1)
        elif self.cenario == "chuva_excessiva":
            for r in futuros:
                r["precipitacao"] = round(min(160.0, 32 * k + abs(random.Random(r["data"]).gauss(14, 8))), 1)
                r["chuva"] = r["precipitacao"]
                r["horas_chuva"] = 11.0
                r["prob_precipitacao"] = 95.0
                r["umidade_media"] = 91.0
                r["et0"] = 1.4
        elif self.cenario == "chuva_intensa":
            for r in futuros[1:3]:
                r["precipitacao"] = round(70.0 * k, 1)
                r["chuva"] = r["precipitacao"]
                r["prob_precipitacao"] = 92.0
                r["cape_max"] = round(2200 * k, 0)
                r["rajada"] = round(72 * k, 1)
        elif self.cenario == "granizo":
            for r in futuros[1:3]:
                r["cape_max"] = round(2900 * k, 0)
                r["rajada"] = round(88 * k, 1)
                r["precipitacao"] = round(46 * k, 1)
                r["chuva"] = r["precipitacao"]
                r["prob_precipitacao"] = 90.0
        elif self.cenario == "geada":
            for r in futuros[1:4]:
                r["tmin"] = round(1.6 - 2.2 * (k - 1), 1)
                r["tmax"] = round(max(r["tmin"] + 8, 15.0), 1)
                r["tmed"] = round((r["tmin"] + r["tmax"]) / 2, 1)
                r["precipitacao"] = 0.0
                r["chuva"] = 0.0
                r["umidade_min"] = 32.0
        elif self.cenario == "onda_calor":
            for r in futuros[:6]:
                r["tmax"] = round(36.5 + 1.6 * k, 1)
                r["tmin"] = round(23.0 + k, 1)
                r["tmed"] = round((r["tmin"] + r["tmax"]) / 2, 1)
                r["precipitacao"] = 0.0
                r["chuva"] = 0.0
                r["et0"] = round(7.8 + 0.8 * k, 2)
                r["umidade_media"] = 38.0
        elif self.cenario == "vendaval":
            for r in futuros[1:3]:
                r["rajada"] = round(84 * k, 1)
                r["vento_medio"] = round(52 * k, 1)
                r["cape_max"] = round(1500 * k, 0)


# ==========================================================================
# Fábrica
# ==========================================================================

def obter_provedor(
    modo: str = "auto",
    *,
    cenario: str | None = None,
    intensidade: float = 1.0,
) -> ClimaProvider:
    """
    Devolve o provedor de clima conforme o modo:

    * ``"online"``    — sempre Open-Meteo;
    * ``"sintetico"`` — sempre o gerador determinístico;
    * ``"auto"``      — Open-Meteo com fallback automático para sintético.
    """
    if modo == "sintetico" or cenario:
        return SinteticoProvider(cenario=cenario, intensidade=intensidade)
    return OpenMeteoProvider()


def celulas_de_municipios(municipios: Iterable[dict[str, Any]], resolucao: float = 0.1) -> tuple[list[Celula], dict[str, str]]:
    """
    Converte uma lista de municípios (com ``lat``/``lon``) em células únicas.

    Devolve ``(celulas, mapa_municipio_para_celula)``.
    """
    celulas: dict[str, Celula] = {}
    mapa: dict[str, str] = {}
    for m in municipios:
        lat, lon = m.get("lat"), m.get("lon")
        if lat is None or lon is None:
            continue
        c = para_celula(float(lat), float(lon), resolucao)
        celulas[c.id] = c
        mapa[str(m.get("cd_ibge") or m.get("codigo") or m.get("id"))] = c.id
    return list(celulas.values()), mapa


def agora_local() -> datetime:
    """Data/hora corrente no fuso configurado."""
    from zoneinfo import ZoneInfo

    try:
        return datetime.now(ZoneInfo(get_settings().timezone))
    except Exception:  # pragma: no cover
        return datetime.now()
