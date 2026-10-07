"""
ANA — situação hídrica (HidroWeb / Sala de Situação) e Monitor de Secas.

Em lavoura irrigada, a restrição de outorga chega **antes** da seca
agronômica: quando o nível do rio cai, a captação é limitada por ato
administrativo, e a lavoura sofre com o solo ainda úmido. Esse é o alerta
mais antecipado disponível para as operações irrigadas da carteira — e é
exatamente o público da regra R-SEC-02.

O Monitor de Secas é tratado como **autoridade**: quando ele classifica o
município, a classificação oficial prevalece sobre o cálculo interno, pela
mesma razão do CEMADEN.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .base import ConectorExterno

URL_SALA_SITUACAO = "https://www.ana.gov.br/sar0/MedicaoSin"
URL_MONITOR_SECAS = "https://monitordesecas.ana.gov.br/api/monitor"

# Escala oficial do Monitor de Secas.
ESCALA_SECA = {
    "S0": ("seca fraca", 0.15),
    "S1": ("seca moderada", 0.35),
    "S2": ("seca grave", 0.60),
    "S3": ("seca extrema", 0.80),
    "S4": ("seca excepcional", 1.00),
}


class Ana(ConectorExterno):
    chave = "ana_hidroweb"
    nome = "ANA — situação hídrica"
    ttl_min = 60 * 12

    def _buscar(self, *, uf: str | None = None, **_: Any) -> pd.DataFrame:
        dados = self._get_json(URL_SALA_SITUACAO, {"uf": uf} if uf else None)
        registros = dados if isinstance(dados, list) else dados.get("dados", [])
        return pd.DataFrame(registros) if registros else pd.DataFrame()

    def _offline(self, **_: Any) -> pd.DataFrame:
        return pd.DataFrame(columns=["estacao", "rio", "uf", "nivel_cm",
                                     "vazao_m3s", "data"])

    def _params_sonda(self) -> dict[str, Any]:
        return {"uf": "MT"}


class MonitorSecas(ConectorExterno):
    chave = "monitor_secas"
    nome = "Monitor de Secas do Brasil"
    ttl_min = 60 * 24 * 15          # publicação mensal

    def _buscar(self, *, uf: str | None = None, **_: Any) -> pd.DataFrame:
        dados = self._get_json(URL_MONITOR_SECAS, {"uf": uf} if uf else None)
        registros = dados if isinstance(dados, list) else dados.get("features", [])
        if not registros:
            return pd.DataFrame()
        linhas = []
        for r in registros:
            prop = r.get("properties", r)
            linhas.append({
                "cd_ibge": prop.get("cd_ibge") or prop.get("geocodigo"),
                "municipio": prop.get("municipio") or prop.get("nome"),
                "uf": prop.get("uf") or prop.get("sigla_uf"),
                "classe": prop.get("classe") or prop.get("intensidade"),
                "mes": prop.get("mes") or prop.get("data"),
            })
        return pd.DataFrame(linhas)

    def _offline(self, **_: Any) -> pd.DataFrame:
        return pd.DataFrame(columns=["cd_ibge", "municipio", "uf", "classe", "mes"])

    def _params_sonda(self) -> dict[str, Any]:
        return {"uf": "BA"}


def severidade_oficial(classe: str | None) -> dict[str, Any]:
    """
    Converte a classe oficial do Monitor de Secas em severidade 0–1 usada
    pelo motor de regras. Quando há classe oficial, ela **substitui** o
    cálculo interno de déficit hídrico e a mensagem passa a citar a fonte.
    """
    if not classe:
        return {"tem_classificacao": False, "severidade": 0.0,
                "rotulo": "", "fonte": ""}
    chave = str(classe).strip().upper()
    if chave not in ESCALA_SECA:
        return {"tem_classificacao": False, "severidade": 0.0,
                "rotulo": "", "fonte": ""}
    rotulo, sev = ESCALA_SECA[chave]
    return {
        "tem_classificacao": True,
        "severidade": sev,
        "rotulo": rotulo,
        "classe": chave,
        "fonte": "Monitor de Secas do Brasil (ANA e parceiros)",
    }
