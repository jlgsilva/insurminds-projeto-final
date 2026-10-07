"""
INPE — Programa Queimadas: focos de calor.

Fogo é evento coberto pelo Proagro e, em pastagem e cana, é o risco mais
subnotificado da carteira: o produtor raramente comunica a tempo. Também
importa o fogo **vizinho** — a queima de resteva no imóvel ao lado é causa
frequente de perda em lavoura segurada.

O conector responde duas perguntas: quantos focos houve neste município nos
últimos N dias, e há foco dentro (ou a menos de X km) da gleba financiada.

Dados abertos, CSV público, sem chave.
https://terrabrasilis.dpi.inpe.br/queimadas/portal/
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

import pandas as pd

from .base import ConectorExterno

URL_CSV_24H = (
    "https://firms.modaps.eosdis.nasa.gov/data/active_fire/"
    "modis-c6.1/csv/MODIS_C6_1_South_America_24h.csv"
)
URL_INPE_DIARIO = (
    "https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/diario/Brasil"
)

RAIO_TERRA_KM = 6371.0


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distância de grande círculo entre dois pontos, em quilômetros."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * RAIO_TERRA_KM * math.asin(math.sqrt(a))


class Queimadas(ConectorExterno):
    chave = "queimadas_inpe"
    nome = "INPE / Programa Queimadas — focos de calor"
    ttl_min = 60 * 3                # o INPE publica a cada 3 horas

    def _buscar(self, *, dia: str | None = None, **_: Any) -> pd.DataFrame:
        alvo = dia or (date.today() - timedelta(days=1)).strftime("%Y%m%d")
        url = f"{URL_INPE_DIARIO}/focos_diario_br_{alvo}.csv"
        df = self._get_csv(url)
        return self._normalizar(df)

    @staticmethod
    def _normalizar(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        renomear = {}
        for c in df.columns:
            baixo = str(c).strip().lower()
            if baixo in ("lat", "latitude"):
                renomear[c] = "lat"
            elif baixo in ("lon", "long", "longitude"):
                renomear[c] = "lon"
            elif "municipio" in baixo and "id" not in baixo:
                renomear[c] = "municipio"
            elif baixo in ("estado", "uf"):
                renomear[c] = "uf"
            elif "data" in baixo or baixo in ("acq_date", "datahora"):
                renomear[c] = "data"
            elif "satelite" in baixo or baixo == "satellite":
                renomear[c] = "satelite"
            elif "bioma" in baixo:
                renomear[c] = "bioma"
            elif "frp" in baixo:
                renomear[c] = "frp"
        out = df.rename(columns=renomear)
        manter = [c for c in ("lat", "lon", "municipio", "uf", "data",
                              "satelite", "bioma", "frp") if c in out.columns]
        if "lat" not in manter or "lon" not in manter:
            return pd.DataFrame()
        return out[manter]

    def _offline(self, **_: Any) -> pd.DataFrame:
        # Sem rede não há como inventar foco de calor: inventar seria pior do
        # que não informar. Devolvemos a estrutura vazia e a interface exibe
        # "monitoramento de fogo indisponível" em vez de "zero focos".
        return pd.DataFrame(columns=["lat", "lon", "municipio", "uf", "data",
                                     "satelite", "bioma", "frp"])

    def _params_sonda(self) -> dict[str, Any]:
        return {}


def focos_proximos(focos: pd.DataFrame, lat: float, lon: float,
                   raio_km: float = 10.0) -> pd.DataFrame:
    """Focos a até ``raio_km`` do ponto informado, ordenados por distância."""
    if focos is None or focos.empty:
        return pd.DataFrame()
    df = focos.copy()
    df["distancia_km"] = [
        round(distancia_km(lat, lon, float(a), float(o)), 1)
        for a, o in zip(df["lat"], df["lon"])
    ]
    return df[df["distancia_km"] <= raio_km].sort_values("distancia_km")


def resumo_por_municipio(focos: pd.DataFrame) -> pd.DataFrame:
    if focos is None or focos.empty or "municipio" not in focos.columns:
        return pd.DataFrame(columns=["municipio", "uf", "n_focos"])
    grp = (focos.groupby([c for c in ("municipio", "uf") if c in focos.columns])
                .size().reset_index(name="n_focos"))
    return grp.sort_values("n_focos", ascending=False)
