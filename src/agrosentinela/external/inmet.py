"""
INMET — estações meteorológicas automáticas.

Papel duplo:

* **Validação da previsão** — comparar o previsto com o observado na estação
  mais próxima produz uma medida de acerto (*skill*) que a interface exibe.
  Alerta cuja fonte nunca é conferida perde credibilidade com o tempo.
* **Evidência** — em pedido de cobertura do Proagro, o dado de estação
  oficial é aceito como prova documental do evento. A mensagem do
  AgroSentinela indica ao produtor **qual estação** consultar.

API pública do INMET, sem chave: https://apitempo.inmet.gov.br
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd

from .base import ConectorExterno

URL_ESTACOES = "https://apitempo.inmet.gov.br/estacoes/T"
URL_DADOS = "https://apitempo.inmet.gov.br/estacao/{ini}/{fim}/{codigo}"


class Inmet(ConectorExterno):
    chave = "inmet"
    nome = "INMET — estações automáticas"
    ttl_min = 60 * 6

    def _buscar(self, *, codigo: str | None = None, dias: int = 7,
                **_: Any) -> pd.DataFrame:
        if codigo is None:
            estacoes = self._get_json(URL_ESTACOES)
            return self._normalizar_estacoes(estacoes)
        fim = date.today()
        ini = fim - timedelta(days=max(1, int(dias)))
        dados = self._get_json(URL_DADOS.format(
            ini=ini.isoformat(), fim=fim.isoformat(), codigo=codigo))
        if not dados:
            return pd.DataFrame()
        df = pd.DataFrame(dados)
        renomear = {
            "DC_NOME": "estacao", "CD_ESTACAO": "codigo", "UF": "uf",
            "DT_MEDICAO": "data", "HR_MEDICAO": "hora",
            "CHUVA": "chuva_mm", "TEM_INS": "temp_c", "TEM_MAX": "tmax_c",
            "TEM_MIN": "tmin_c", "UMD_INS": "umidade_pct",
            "VEN_VEL": "vento_ms", "VEN_RAJ": "rajada_ms",
        }
        df = df.rename(columns={k: v for k, v in renomear.items() if k in df.columns})
        manter = [c for c in renomear.values() if c in df.columns]
        return df[manter] if manter else pd.DataFrame()

    @staticmethod
    def _normalizar_estacoes(dados: Any) -> pd.DataFrame:
        if not dados:
            return pd.DataFrame()
        linhas = []
        for e in dados:
            try:
                linhas.append({
                    "codigo": e.get("CD_ESTACAO"),
                    "estacao": e.get("DC_NOME"),
                    "uf": e.get("SG_ESTADO"),
                    "lat": float(e.get("VL_LATITUDE")),
                    "lon": float(e.get("VL_LONGITUDE")),
                    "altitude": e.get("VL_ALTITUDE"),
                    "situacao": e.get("CD_SITUACAO"),
                })
            except (TypeError, ValueError):
                continue
        return pd.DataFrame(linhas)

    def _offline(self, **_: Any) -> pd.DataFrame:
        # Estações de referência das principais praças agrícolas, para que a
        # mensagem consiga citar uma fonte oficial mesmo offline.
        return pd.DataFrame([
            {"codigo": "A901", "estacao": "SORRISO", "uf": "MT", "lat": -12.55, "lon": -55.72},
            {"codigo": "A923", "estacao": "SAPEZAL", "uf": "MT", "lat": -12.99, "lon": -58.76},
            {"codigo": "A702", "estacao": "CAMPO GRANDE", "uf": "MS", "lat": -20.45, "lon": -54.72},
            {"codigo": "A002", "estacao": "BRASILIA", "uf": "DF", "lat": -15.79, "lon": -47.93},
            {"codigo": "A756", "estacao": "RIO VERDE", "uf": "GO", "lat": -17.79, "lon": -50.96},
            {"codigo": "A807", "estacao": "PORTO ALEGRE", "uf": "RS", "lat": -30.05, "lon": -51.17},
            {"codigo": "A840", "estacao": "PASSO FUNDO", "uf": "RS", "lat": -28.23, "lon": -52.40},
            {"codigo": "A807", "estacao": "LONDRINA", "uf": "PR", "lat": -23.31, "lon": -51.14},
            {"codigo": "A701", "estacao": "SAO PAULO", "uf": "SP", "lat": -23.50, "lon": -46.62},
            {"codigo": "A521", "estacao": "UBERLANDIA", "uf": "MG", "lat": -18.92, "lon": -48.26},
            {"codigo": "A402", "estacao": "BARREIRAS", "uf": "BA", "lat": -12.12, "lon": -45.03},
            {"codigo": "A203", "estacao": "BALSAS", "uf": "MA", "lat": -7.46, "lon": -46.03},
            {"codigo": "A230", "estacao": "PALMAS", "uf": "TO", "lat": -10.19, "lon": -48.30},
        ])

    def _params_sonda(self) -> dict[str, Any]:
        return {}


def estacao_mais_proxima(estacoes: pd.DataFrame, lat: float, lon: float,
                         raio_km: float = 150.0) -> dict[str, Any] | None:
    """Estação oficial mais próxima do ponto, dentro do raio informado."""
    from .queimadas import distancia_km

    if estacoes is None or estacoes.empty:
        return None
    if "lat" not in estacoes.columns or "lon" not in estacoes.columns:
        return None
    melhor, menor = None, float("inf")
    for _, linha in estacoes.iterrows():
        try:
            d = distancia_km(lat, lon, float(linha["lat"]), float(linha["lon"]))
        except (TypeError, ValueError):
            continue
        if d < menor:
            melhor, menor = linha, d
    if melhor is None or menor > raio_km:
        return None
    saida = melhor.to_dict()
    saida["distancia_km"] = round(menor, 1)
    return saida
