"""
MAPA — Atlas do Seguro Rural / SISSER: apólices do Programa de Subvenção ao
Prêmio do Seguro Rural (PSR).

Esta é a fonte que fecha a lacuna mais importante para o público de seguros.
O Sicor mostra a cobertura **do Proagro**; o PSR mostra a cobertura do
**seguro privado subvencionado**. Só com as duas é possível responder à
pergunta que interessa a seguradora, corretora, banco e política pública:

    "Neste município, a lavoura está descoberta — ou está coberta por outro
    instrumento que o Sicor não enxerga?"

A resposta muda tudo. Um município com 70% da área financiada sem Proagro
pode ser um deserto de proteção (oportunidade comercial e risco sistêmico)
ou uma praça já atendida por seguro privado (mercado maduro, competição).
A regra R-COB-01 usa exatamente essa distinção antes de sugerir contratação.

Dados abertos do MAPA, publicados em CSV no dados.gov.br.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .base import ConectorExterno

URL_SISSER = (
    "https://dados.agricultura.gov.br/dataset/sisser/resource/"
    "psr-dados-abertos.csv"
)

# Participação média do seguro rural privado subvencionado na área de
# lavoura, por UF — ordem de grandeza pública, usada apenas offline e
# sempre exibida com o selo de "referência embutida".
PENETRACAO_UF: dict[str, float] = {
    "PR": 0.31, "RS": 0.24, "SC": 0.22, "SP": 0.15, "MG": 0.11,
    "MT": 0.09, "MS": 0.12, "GO": 0.10, "BA": 0.06, "MA": 0.04,
    "TO": 0.05, "PI": 0.04, "DF": 0.13, "ES": 0.07, "RJ": 0.03,
    "PE": 0.02, "CE": 0.02, "AL": 0.02, "SE": 0.02, "PB": 0.02,
    "RN": 0.02, "PA": 0.02, "RO": 0.03, "AC": 0.01, "AM": 0.01,
    "AP": 0.01, "RR": 0.02,
}

TAXA_MEDIA_CULTURA: dict[str, float] = {
    "soja": 0.052, "milho": 0.068, "milho_2safra": 0.079, "trigo": 0.089,
    "algodao": 0.045, "arroz": 0.041, "feijao": 0.081, "cafe": 0.064,
    "uva": 0.098, "maca": 0.091, "cana": 0.038,
}


class PsrMapa(ConectorExterno):
    chave = "psr_mapa"
    nome = "Atlas do Seguro Rural (PSR/MAPA)"
    ttl_min = 60 * 24 * 30

    def _buscar(self, *, uf: str | None = None, ano: int | None = None,
                **_: Any) -> pd.DataFrame:
        df = self._get_csv(URL_SISSER, sep=";", encoding="latin-1",
                           low_memory=False)
        return self._normalizar(df, uf=uf, ano=ano)

    @staticmethod
    def _normalizar(df: pd.DataFrame, *, uf: str | None,
                    ano: int | None) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        mapa = {}
        for c in df.columns:
            b = str(c).strip().lower()
            if "ibge" in b:
                mapa[c] = "cd_ibge"
            elif b in ("nm_municipio", "municipio"):
                mapa[c] = "municipio"
            elif b in ("sg_uf", "uf", "nm_uf"):
                mapa[c] = "uf"
            elif "cultura" in b:
                mapa[c] = "cultura_psr"
            elif "ano" in b and "apolice" in b:
                mapa[c] = "ano"
            elif "area" in b and "segurada" in b:
                mapa[c] = "area_segurada_ha"
            elif "premio" in b and "total" in b:
                mapa[c] = "premio_total"
            elif "subvenc" in b:
                mapa[c] = "subvencao"
            elif "import" in b and "segurad" in b:
                mapa[c] = "importancia_segurada"
            elif "indeniz" in b:
                mapa[c] = "indenizacao"
            elif "apolice" in b and "nr" not in b:
                mapa[c] = "n_apolices"
        out = df.rename(columns=mapa)
        colunas = [c for c in ("cd_ibge", "municipio", "uf", "cultura_psr",
                               "ano", "n_apolices", "area_segurada_ha",
                               "premio_total", "subvencao",
                               "importancia_segurada", "indenizacao")
                   if c in out.columns]
        if not colunas:
            return pd.DataFrame()
        out = out[colunas]
        if uf and "uf" in out.columns:
            out = out[out["uf"].astype(str).str.upper() == str(uf).upper()]
        if ano and "ano" in out.columns:
            out = out[pd.to_numeric(out["ano"], errors="coerce") == int(ano)]
        return out

    def _offline(self, *, uf: str = "", **_: Any) -> pd.DataFrame:
        alvo = [uf.upper()] if uf else sorted(PENETRACAO_UF)
        return pd.DataFrame([
            {"uf": u, "penetracao_seguro_privado": PENETRACAO_UF.get(u, 0.03),
             "referencia": True}
            for u in alvo
        ])

    def _params_sonda(self) -> dict[str, Any]:
        return {"uf": "MT"}


def classificar_protecao(tem_proagro_pct: float,
                         penetracao_privada: float) -> dict[str, Any]:
    """
    Combina cobertura pública (Proagro, do Sicor) e privada (PSR) em um
    diagnóstico único de proteção do município.

    É esta função que evita o erro mais comum na leitura isolada do Sicor:
    confundir "sem Proagro" com "desprotegido".
    """
    cobertura_total = min(1.0, max(0.0, tem_proagro_pct) + max(0.0, penetracao_privada))
    if cobertura_total >= 0.6:
        nivel, rotulo = "alta", "praça madura em proteção de risco"
    elif cobertura_total >= 0.3:
        nivel, rotulo = "média", "proteção parcial — há espaço de crescimento"
    else:
        nivel, rotulo = "baixa", "deserto de proteção — exposição relevante"
    return {
        "cobertura_total": round(cobertura_total, 3),
        "cobertura_publica": round(max(0.0, tem_proagro_pct), 3),
        "cobertura_privada": round(max(0.0, penetracao_privada), 3),
        "nivel": nivel,
        "diagnostico": rotulo,
    }
