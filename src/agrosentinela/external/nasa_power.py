"""
NASA POWER — normais climatológicas no ponto.

Por que esta fonte existe no projeto: previsão sozinha não informa. "Vai
chover 80 mm" só é acionável quando acompanhado de "contra uma média
histórica de 26 mm para esta semana aqui". A anomalia — e não o valor
absoluto — é o que separa alerta útil de alarme falso, e é ela que aparece
na mensagem redigida pelo LLM.

API pública, domínio público, sem chave e sem cota declarada.
https://power.larc.nasa.gov/docs/services/api/
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .base import ConectorExterno

URL_CLIMATOLOGIA = "https://power.larc.nasa.gov/api/temporal/climatology/point"

PARAMETROS = "PRECTOTCORR,T2M,T2M_MAX,T2M_MIN,ALLSKY_SFC_SW_DWN,RH2M,WS2M"

MESES = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
         "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")

# Normais mensais de referência por macrorregião (mm/mês de chuva e °C de
# temperatura média), derivadas de médias climatológicas públicas. Servem
# apenas para manter a interface funcional sem rede — a procedência é
# sempre exibida como "referência embutida".
NORMAIS_REGIAO: dict[str, dict[str, list[float]]] = {
    "Norte":        {"chuva": [300, 310, 330, 300, 240, 140, 100, 90, 120, 180, 230, 270],
                     "temp":  [26.2, 26.0, 26.1, 26.3, 26.5, 26.6, 26.7, 27.3, 27.6, 27.4, 27.0, 26.6]},
    "Nordeste":     {"chuva": [120, 150, 190, 160, 90, 45, 30, 20, 15, 30, 60, 95],
                     "temp":  [27.0, 26.8, 26.7, 26.5, 26.0, 25.2, 24.7, 25.0, 26.1, 27.0, 27.4, 27.3]},
    "Centro-Oeste": {"chuva": [260, 220, 210, 110, 45, 12, 8, 15, 60, 150, 230, 280],
                     "temp":  [25.4, 25.5, 25.6, 25.3, 23.8, 22.4, 22.3, 24.2, 26.1, 26.3, 25.8, 25.3]},
    "Sudeste":      {"chuva": [240, 190, 160, 75, 40, 20, 15, 22, 60, 120, 180, 250],
                     "temp":  [24.4, 24.6, 24.2, 22.8, 20.7, 19.4, 19.2, 20.8, 22.3, 23.3, 23.7, 24.0]},
    "Sul":          {"chuva": [160, 150, 130, 120, 115, 130, 140, 130, 155, 175, 140, 145],
                     "temp":  [24.3, 24.1, 22.8, 19.9, 16.7, 14.4, 14.2, 15.6, 17.4, 19.8, 21.9, 23.5]},
}

REGIAO_PADRAO = "Centro-Oeste"


def _regiao_por_coordenada(lat: float, lon: float) -> str:
    """Classificação grosseira usada apenas no modo offline."""
    if lat > -5.5 and lon < -46:
        return "Norte"
    if lat > -18 and lon > -46:
        return "Nordeste"
    if lat < -24:
        return "Sul"
    if lat < -18:
        return "Sudeste"
    return REGIAO_PADRAO


class NasaPower(ConectorExterno):
    chave = "nasa_power"
    nome = "NASA POWER — normais climatológicas"
    ttl_min = 60 * 24 * 30          # normais mudam uma vez por ano, no máximo

    def _buscar(self, *, lat: float, lon: float, **_: Any) -> pd.DataFrame:
        dados = self._get_json(URL_CLIMATOLOGIA, {
            "parameters": PARAMETROS,
            "community": "AG",
            "latitude": round(float(lat), 3),
            "longitude": round(float(lon), 3),
            "format": "JSON",
        })
        bloco = dados.get("properties", {}).get("parameter", {})
        if not bloco:
            return pd.DataFrame()
        linhas = []
        for i, mes in enumerate(MESES, start=1):
            linha = {"mes": i, "lat": float(lat), "lon": float(lon)}
            for nome_api, coluna in (
                ("PRECTOTCORR", "chuva_normal_mm"),
                ("T2M", "temp_normal_c"),
                ("T2M_MAX", "tmax_normal_c"),
                ("T2M_MIN", "tmin_normal_c"),
                ("ALLSKY_SFC_SW_DWN", "radiacao_normal"),
                ("RH2M", "umidade_normal_pct"),
                ("WS2M", "vento_normal_ms"),
            ):
                valor = bloco.get(nome_api, {}).get(mes)
                if valor is not None and valor > -900:
                    # PRECTOTCORR vem em mm/dia na climatologia mensal
                    if coluna == "chuva_normal_mm":
                        valor = float(valor) * 30.0
                    linha[coluna] = round(float(valor), 2)
            linhas.append(linha)
        return pd.DataFrame(linhas)

    def _offline(self, *, lat: float = -15.0, lon: float = -55.0, **_: Any) -> pd.DataFrame:
        regiao = _regiao_por_coordenada(float(lat), float(lon))
        base = NORMAIS_REGIAO[regiao]
        return pd.DataFrame([
            {
                "mes": i + 1,
                "lat": float(lat),
                "lon": float(lon),
                "regiao_referencia": regiao,
                "chuva_normal_mm": base["chuva"][i],
                "temp_normal_c": base["temp"][i],
            }
            for i in range(12)
        ])

    def _params_sonda(self) -> dict[str, Any]:
        return {"lat": -15.6, "lon": -56.1}


def anomalia_chuva(observado_mm: float | None,
                   normal_mm: float | None) -> float | None:
    """
    Razão entre o observado e a normal do período (1,0 = exatamente normal).

    Devolve ``None`` quando **falta informação** — seja a normal, seja a
    observação. A distinção importa: uma razão de ``0.0`` significa "não vai
    chover nada", que é o caso mais grave de seca; confundi-la com "não sei"
    apagaria justamente o alerta mais importante. Este foi um erro real
    encontrado em teste e o motivo de a função devolver ``None`` em vez de
    zero.
    """
    if normal_mm is None or float(normal_mm) <= 0:
        return None
    if observado_mm is None:
        return None
    return round(float(observado_mm) / float(normal_mm), 2)


def classificar_anomalia(razao: float | None) -> str:
    if razao is None:
        return "sem referência"
    if razao >= 3.0:
        return "muito acima da média"
    if razao >= 1.6:
        return "acima da média"
    if razao <= 0.25:
        return "muito abaixo da média"
    if razao <= 0.6:
        return "abaixo da média"
    return "dentro da média"
