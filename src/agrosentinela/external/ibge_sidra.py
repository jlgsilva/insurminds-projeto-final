"""
IBGE / SIDRA — Produção Agrícola Municipal (PAM) e Pesquisa da Pecuária
Municipal (PPM).

Esta é a fonte do **denominador**. O Sicor diz quantos hectares foram
financiados; a PAM diz quantos hectares existem. A razão entre os dois é o
que permite afirmações como "o crédito cobre 38% da área de soja deste
município" — e, quando há sinistro, estimar a perda em toneladas usando o
rendimento médio municipal em vez de um chute.

API pública, sem chave: https://apisidra.ibge.gov.br
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .base import ConectorExterno

URL_SIDRA = "https://apisidra.ibge.gov.br/values"

TABELA_PAM = "5457"      # Área plantada, quantidade produzida e rendimento
TABELA_PPM = "3939"      # Efetivo dos rebanhos

VARS_PAM = "8331,214,112"    # área plantada (ha), quantidade (t), rendimento (kg/ha)
CLASSIF_PRODUTO = "c782"

# Rendimentos médios de referência (kg/ha) por cultura, usados apenas
# offline. Ordem de grandeza pública e amplamente divulgada; a interface
# deixa claro que são valores de referência.
RENDIMENTO_REFERENCIA: dict[str, float] = {
    "soja": 3400.0,
    "milho": 5600.0,
    "milho_safrinha": 5200.0,
    "algodao": 4300.0,
    "arroz": 6200.0,
    "feijao": 1200.0,
    "trigo": 2700.0,
    "cafe": 1700.0,
    "cana": 76000.0,
    "laranja": 28000.0,
    "uva": 20000.0,
    "maca": 36000.0,
    "mandioca": 15000.0,
    "sorgo": 3000.0,
    "girassol": 1600.0,
    "amendoim": 3700.0,
}

REBANHO_REFERENCIA = {"bovino": 0.0}


class IbgeSidra(ConectorExterno):
    chave = "ibge_sidra"
    nome = "IBGE SIDRA — PAM / PPM"
    ttl_min = 60 * 24 * 90          # pesquisa anual

    def _buscar(self, *, cd_ibge: int | str, periodo: str = "last",
                tabela: str = TABELA_PAM, **_: Any) -> pd.DataFrame:
        caminho = (
            f"/t/{tabela}/n6/{cd_ibge}/v/{VARS_PAM}/p/{periodo}"
            f"/{CLASSIF_PRODUTO}/all/f/n"
        )
        bruto = self._get_json(URL_SIDRA + caminho)
        if not isinstance(bruto, list) or len(bruto) < 2:
            return pd.DataFrame()
        # A primeira linha do SIDRA é o cabeçalho descritivo.
        registros = bruto[1:]
        linhas = []
        for r in registros:
            valor = r.get("V")
            if valor in (None, "...", "-", "X"):
                continue
            try:
                valor = float(valor)
            except (TypeError, ValueError):
                continue
            linhas.append({
                "cd_ibge": int(r.get("D1C") or cd_ibge),
                "municipio": r.get("D1N", ""),
                "ano": int(r.get("D3C") or 0),
                "produto_ibge": r.get("D4N", ""),
                "variavel": r.get("D2N", ""),
                "valor": valor,
                "unidade": r.get("MN", ""),
            })
        if not linhas:
            return pd.DataFrame()
        longo = pd.DataFrame(linhas)
        return self._pivotar(longo)

    @staticmethod
    def _pivotar(longo: pd.DataFrame) -> pd.DataFrame:
        mapa = {
            "Área plantada": "area_plantada_ha",
            "Área plantada ou destinada à colheita": "area_plantada_ha",
            "Quantidade produzida": "producao_t",
            "Rendimento médio da produção": "rendimento_kg_ha",
        }
        longo = longo.copy()
        longo["coluna"] = longo["variavel"].map(
            lambda v: next((c for k, c in mapa.items() if str(v).startswith(k)), None)
        )
        longo = longo.dropna(subset=["coluna"])
        if longo.empty:
            return pd.DataFrame()
        largo = longo.pivot_table(
            index=["cd_ibge", "municipio", "ano", "produto_ibge"],
            columns="coluna", values="valor", aggfunc="sum",
        ).reset_index()
        largo.columns.name = None
        return largo

    def _offline(self, *, cd_ibge: int | str = 0, culturas: tuple[str, ...] = (),
                 **_: Any) -> pd.DataFrame:
        alvo = culturas or tuple(RENDIMENTO_REFERENCIA)
        return pd.DataFrame([
            {
                "cd_ibge": int(cd_ibge or 0),
                "municipio": "",
                "ano": 0,
                "produto_ibge": cultura,
                "rendimento_kg_ha": RENDIMENTO_REFERENCIA.get(cultura, 0.0),
                "area_plantada_ha": float("nan"),
                "producao_t": float("nan"),
                "referencia": True,
            }
            for cultura in alvo if cultura in RENDIMENTO_REFERENCIA
        ])

    def _params_sonda(self) -> dict[str, Any]:
        return {"cd_ibge": 5107925}     # Sorriso/MT


# Mapeia o nome do produto como o IBGE publica para a cultura interna.
PRODUTO_IBGE_PARA_CULTURA: dict[str, str] = {
    "soja (em grão)": "soja",
    "milho (em grão)": "milho",
    "algodão herbáceo (em caroço)": "algodao",
    "arroz (em casca)": "arroz",
    "feijão (em grão)": "feijao",
    "trigo (em grão)": "trigo",
    "café (em grão) total": "cafe",
    "café (em grão) arábica": "cafe",
    "cana-de-açúcar": "cana",
    "laranja": "laranja",
    "uva": "uva",
    "maçã": "maca",
    "mandioca": "mandioca",
    "sorgo (em grão)": "sorgo",
    "girassol (em grão)": "girassol",
    "amendoim (em casca)": "amendoim",
}


def cultura_do_produto_ibge(produto: str) -> str | None:
    if not produto:
        return None
    return PRODUTO_IBGE_PARA_CULTURA.get(str(produto).strip().lower())


def estimar_perda_toneladas(area_ha: float, rendimento_kg_ha: float,
                            perda_pct: float) -> float:
    """Perda física estimada, em toneladas, para a área e o rendimento dados."""
    if area_ha <= 0 or rendimento_kg_ha <= 0:
        return 0.0
    return round(area_ha * rendimento_kg_ha * max(0.0, min(perda_pct, 1.0)) / 1000.0, 1)
