"""
MapBiomas — uso e cobertura do solo por município.

Responde a uma pergunta que nem o Sicor nem o IBGE respondem sozinhos: o
crédito rural está indo para área **já consolidada** ou para **fronteira**?
A distinção interessa a três personas de uma vez — política pública
(direcionamento do subsídio), subscrição de seguradora (critério
socioambiental) e trading (exigência de compradores internacionais).

Também alimenta o denominador de pastagem, que o PAM não cobre.

Licença CC BY-SA 4.0 — uso livre com atribuição obrigatória, registrada no
rodapé da aplicação.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .base import ConectorExterno

URL_ESTATISTICAS = "https://brasil.mapbiomas.org/wp-content/uploads/sites/4/2024/estatisticas_municipios.csv"

# Participação média das classes de uso por bioma, em fração da área do
# município — referência offline, sempre rotulada como tal.
USO_POR_BIOMA: dict[str, dict[str, float]] = {
    "Amazônia":   {"lavoura": 0.03, "pastagem": 0.14, "nativa": 0.79, "outros": 0.04},
    "Cerrado":    {"lavoura": 0.21, "pastagem": 0.30, "nativa": 0.44, "outros": 0.05},
    "Mata Atlântica": {"lavoura": 0.22, "pastagem": 0.36, "nativa": 0.28, "outros": 0.14},
    "Caatinga":   {"lavoura": 0.07, "pastagem": 0.17, "nativa": 0.70, "outros": 0.06},
    "Pampa":      {"lavoura": 0.29, "pastagem": 0.44, "nativa": 0.21, "outros": 0.06},
    "Pantanal":   {"lavoura": 0.01, "pastagem": 0.15, "nativa": 0.82, "outros": 0.02},
}

BIOMA_POR_UF: dict[str, str] = {
    "AC": "Amazônia", "AM": "Amazônia", "AP": "Amazônia", "PA": "Amazônia",
    "RO": "Amazônia", "RR": "Amazônia", "TO": "Cerrado",
    "MT": "Cerrado", "MS": "Cerrado", "GO": "Cerrado", "DF": "Cerrado",
    "MG": "Cerrado", "BA": "Caatinga", "PI": "Caatinga", "CE": "Caatinga",
    "RN": "Caatinga", "PB": "Caatinga", "PE": "Caatinga", "AL": "Caatinga",
    "SE": "Caatinga", "MA": "Cerrado",
    "SP": "Mata Atlântica", "RJ": "Mata Atlântica", "ES": "Mata Atlântica",
    "PR": "Mata Atlântica", "SC": "Mata Atlântica", "RS": "Pampa",
}


class MapBiomas(ConectorExterno):
    chave = "mapbiomas"
    nome = "MapBiomas — uso e cobertura do solo"
    ttl_min = 60 * 24 * 90

    def _buscar(self, *, cd_ibge: int | str | None = None, **_: Any) -> pd.DataFrame:
        df = self._get_csv(URL_ESTATISTICAS, sep=",", low_memory=False)
        if df is None or df.empty:
            return pd.DataFrame()
        df.columns = [str(c).strip().lower() for c in df.columns]
        col_ibge = next((c for c in df.columns if "ibge" in c or "geocod" in c), None)
        if cd_ibge and col_ibge:
            df = df[pd.to_numeric(df[col_ibge], errors="coerce") == int(cd_ibge)]
        return df

    def _offline(self, *, uf: str = "MT", **_: Any) -> pd.DataFrame:
        bioma = BIOMA_POR_UF.get(str(uf).upper(), "Cerrado")
        uso = USO_POR_BIOMA[bioma]
        return pd.DataFrame([{
            "uf": str(uf).upper(), "bioma_predominante": bioma,
            **{f"frac_{k}": v for k, v in uso.items()},
            "referencia": True,
        }])

    def _params_sonda(self) -> dict[str, Any]:
        return {"cd_ibge": 5107925}


def perfil_expansao(frac_lavoura: float, frac_nativa: float) -> str:
    """Leitura curta do perfil do município, usada nas páginas analíticas."""
    if frac_lavoura >= 0.30 and frac_nativa <= 0.35:
        return "agrícola consolidado"
    if frac_nativa >= 0.65:
        return "predominantemente nativo"
    if 0.05 <= frac_lavoura < 0.30 and frac_nativa >= 0.40:
        return "fronteira de expansão"
    return "uso misto"
