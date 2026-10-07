"""
CONAB — preços e custos de produção.

Serve a um propósito específico e verificável: **converter perda física em
perda financeira usando preço oficial, não estimativa**. A diferença importa.
Quando o alerta diz "risco de perda de 18% em 340 ha de soja", o gerente de
crédito precisa de R$; o produtor precisa saber se cobre o custeio; o
atuário precisa da exposição. Usar preço CONAB torna esse número auditável.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .base import ConectorExterno

URL_PRECOS = "https://portaldeinformacoes.conab.gov.br/downloads/arquivos/PrecosMinimos.csv"

# Preços de referência por unidade usual da cultura (R$), mantidos como
# ordem de grandeza para o modo offline. A interface rotula como referência
# e o relatório registra a data da tabela em uso.
PRECO_REFERENCIA: dict[str, tuple[float, str]] = {
    "soja":         (128.00, "saca de 60 kg"),
    "milho":        (62.00,  "saca de 60 kg"),
    "milho_2safra": (62.00,  "saca de 60 kg"),
    "algodao":      (145.00, "arroba"),
    "arroz":        (95.00,  "saca de 50 kg"),
    "feijao":       (230.00, "saca de 60 kg"),
    "trigo":        (76.00,  "saca de 60 kg"),
    "cafe":         (1250.00, "saca de 60 kg"),
    "cana":         (110.00, "tonelada"),
    "laranja":      (38.00,  "caixa de 40,8 kg"),
    "uva":          (4.20,   "quilo"),
    "maca":         (3.10,   "quilo"),
    "mandioca":     (620.00, "tonelada"),
    "bovinos":      (305.00, "arroba"),
}

KG_POR_UNIDADE: dict[str, float] = {
    "saca de 60 kg": 60.0,
    "saca de 50 kg": 50.0,
    "arroba": 15.0,
    "tonelada": 1000.0,
    "quilo": 1.0,
    "caixa de 40,8 kg": 40.8,
}


class Conab(ConectorExterno):
    chave = "conab"
    nome = "CONAB — preços de referência"
    ttl_min = 60 * 24 * 7

    def _buscar(self, *, produto: str | None = None, **_: Any) -> pd.DataFrame:
        df = self._get_csv(URL_PRECOS, sep=";", encoding="latin-1")
        if df is None or df.empty:
            return pd.DataFrame()
        df.columns = [str(c).strip().lower() for c in df.columns]
        if produto:
            alvo = str(produto).lower()
            col = next((c for c in df.columns if "produto" in c), None)
            if col:
                df = df[df[col].astype(str).str.lower().str.contains(alvo, na=False)]
        return df

    def _offline(self, *, produto: str | None = None, **_: Any) -> pd.DataFrame:
        itens = ([produto] if produto and produto in PRECO_REFERENCIA
                 else list(PRECO_REFERENCIA))
        return pd.DataFrame([
            {"cultura": c, "preco_referencia": PRECO_REFERENCIA[c][0],
             "unidade": PRECO_REFERENCIA[c][1], "referencia": True}
            for c in itens
        ])

    def _params_sonda(self) -> dict[str, Any]:
        return {"produto": "soja"}


def valor_da_perda(cultura: str, area_ha: float, rendimento_kg_ha: float,
                   perda_pct: float, preco: float | None = None) -> dict[str, Any]:
    """
    Perda estimada em quilos, em unidades comerciais e em reais.

    Devolve também ``base_preco`` para que a interface possa dizer se usou
    preço consultado ou valor de referência — o tipo de transparência que
    torna o número utilizável em decisão de crédito.
    """
    cultura = (cultura or "").lower()
    ref = PRECO_REFERENCIA.get(cultura)
    unidade = ref[1] if ref else "saca de 60 kg"
    preco_usado = preco if preco else (ref[0] if ref else 0.0)
    base = "consultado" if preco else ("referência" if ref else "indisponível")

    kg = max(0.0, area_ha) * max(0.0, rendimento_kg_ha) * max(0.0, min(perda_pct, 1.0))
    por_unidade = KG_POR_UNIDADE.get(unidade, 60.0)
    unidades = kg / por_unidade if por_unidade else 0.0
    return {
        "perda_kg": round(kg, 1),
        "perda_unidades": round(unidades, 1),
        "unidade": unidade,
        "preco_unitario": round(preco_usado, 2),
        "perda_reais": round(unidades * preco_usado, 2),
        "base_preco": base,
    }
