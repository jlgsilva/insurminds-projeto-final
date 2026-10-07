"""
SUSEP — estatísticas do mercado segurador (ramo rural).

Traz a sinistralidade de mercado com que a persona atuarial compara a
carteira própria e com que a área comercial dimensiona a praça. É o
complemento natural do PSR: o PSR mostra **quanto** foi segurado com
subvenção; a SUSEP mostra **como o risco se comportou** no mercado.

Dados abertos, sem chave.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .base import ConectorExterno

URL_SES = "https://www2.susep.gov.br/redarq.asp?arq=BaseCompleta.zip"

# Sinistralidade de referência do ramo rural (sinistros retidos / prêmios
# ganhos), por ano — ordem de grandeza pública para uso offline.
SINISTRALIDADE_RURAL: dict[int, float] = {
    2019: 0.61, 2020: 0.72, 2021: 1.18, 2022: 0.94,
    2023: 0.83, 2024: 0.69, 2025: 0.75,
}


class Susep(ConectorExterno):
    chave = "susep"
    nome = "SUSEP — estatísticas do mercado segurador"
    ttl_min = 60 * 24 * 30

    def _buscar(self, **_: Any) -> pd.DataFrame:
        # A base completa da SUSEP é distribuída em ZIP de dezenas de MB.
        # Baixá-la a cada execução seria desproporcional para uma prova de
        # conceito publicada em plano gratuito, então o conector depende de
        # um recorte previamente extraído pelo ETL (etl/09_build_externos.py).
        raise RuntimeError(
            "A base SES da SUSEP é consumida pelo ETL, não em tempo de "
            "execução. Rode `python etl/09_build_externos.py --susep`."
        )

    def _offline(self, **_: Any) -> pd.DataFrame:
        return pd.DataFrame([
            {"ano": ano, "sinistralidade_rural": valor, "referencia": True}
            for ano, valor in sorted(SINISTRALIDADE_RURAL.items())
        ])

    def disponivel(self) -> bool:
        return False


def comparar_sinistralidade(taxa_carteira: float, ano: int) -> dict[str, Any]:
    """Posiciona a taxa observada na carteira contra a do mercado."""
    mercado = SINISTRALIDADE_RURAL.get(ano)
    if mercado is None:
        anos = sorted(SINISTRALIDADE_RURAL)
        mercado = SINISTRALIDADE_RURAL[anos[-1]] if anos else 0.0
    if mercado <= 0:
        return {"mercado": 0.0, "diferenca": 0.0, "leitura": "sem referência"}
    dif = taxa_carteira - mercado
    if dif > 0.15:
        leitura = "acima do mercado — revisar subscrição ou precificação"
    elif dif < -0.15:
        leitura = "abaixo do mercado — carteira com desempenho favorável"
    else:
        leitura = "em linha com o mercado"
    return {"mercado": round(mercado, 3), "diferenca": round(dif, 3),
            "leitura": leitura}
