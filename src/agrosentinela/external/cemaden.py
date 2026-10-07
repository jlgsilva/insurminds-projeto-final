"""
CEMADEN — pluviômetros automáticos e alertas oficiais de desastre.

A decisão de projeto aqui é deliberada e vale ser lida: **quando já existe
alerta oficial do CEMADEN para o município, o AgroSentinela não emite um
aviso concorrente — ele cita o alerta oficial**. Duplicar autoridade gera
ruído, contradição e perda de confiança. O papel da solução é traduzir o
alerta para a lavoura específica ("o alerta de chuva intensa alcança suas
120 ha de soja em enchimento de grãos"), não competir com o órgão.

Dados abertos, sem chave.
https://www.cemaden.gov.br
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .base import ConectorExterno

URL_PLUVIOMETROS = "http://sjc.salvar.cemaden.gov.br/resources/dados/{uf}.json"

NIVEIS = ("observação", "atenção", "alerta", "alerta máximo")


class Cemaden(ConectorExterno):
    chave = "cemaden"
    nome = "CEMADEN — chuva observada e alertas"
    ttl_min = 60                     # atualização horária

    def _buscar(self, *, uf: str, **_: Any) -> pd.DataFrame:
        dados = self._get_json(URL_PLUVIOMETROS.format(uf=str(uf).lower()))
        registros = dados if isinstance(dados, list) else dados.get("dados", [])
        if not registros:
            return pd.DataFrame()
        linhas = []
        for r in registros:
            linhas.append({
                "estacao": r.get("nomeEstacao") or r.get("nome"),
                "cd_ibge": r.get("codibge") or r.get("cod_ibge"),
                "municipio": r.get("municipio"),
                "uf": str(uf).upper(),
                "lat": r.get("latitude"),
                "lon": r.get("longitude"),
                "chuva_1h": r.get("chuva1h") or r.get("valorMedida"),
                "chuva_24h": r.get("chuva24h"),
                "chuva_72h": r.get("chuva72h"),
                "data": r.get("datahora") or r.get("horaLeitura"),
            })
        df = pd.DataFrame(linhas)
        for col in ("chuva_1h", "chuva_24h", "chuva_72h"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna(subset=["municipio"], how="all")

    def _offline(self, **_: Any) -> pd.DataFrame:
        # Como no conector de fogo: não se inventa observação de solo.
        return pd.DataFrame(columns=["estacao", "cd_ibge", "municipio", "uf",
                                     "lat", "lon", "chuva_1h", "chuva_24h",
                                     "chuva_72h", "data"])

    def _params_sonda(self) -> dict[str, Any]:
        return {"uf": "mt"}


def nivel_por_acumulado(chuva_24h: float) -> str:
    """
    Classificação simplificada por acumulado em 24h, alinhada às faixas
    usualmente praticadas na defesa civil. Serve de complemento quando não
    há alerta oficial publicado para o município.
    """
    if chuva_24h is None or pd.isna(chuva_24h):
        return "sem medição"
    v = float(chuva_24h)
    if v >= 100:
        return "alerta máximo"
    if v >= 60:
        return "alerta"
    if v >= 30:
        return "atenção"
    if v >= 10:
        return "observação"
    return "normal"
