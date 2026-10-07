"""
Agritempo — sistema de monitoramento agrometeorológico (Embrapa/Unicamp).

Boletins por município já em linguagem agronômica (balanço hídrico,
adequação de plantio, risco de doença). Registrado e pronto para ativação:
hoje o balanço hídrico é calculado internamente a partir de ET0 e
precipitação da Open-Meteo, o que mantém o pipeline com uma dependência de
rede a menos. Manter o conector aqui documenta a alternativa e permite
trocar a implementação sem tocar no restante do sistema.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .base import ConectorExterno

URL_BOLETIM = "https://www.agritempo.gov.br/agritempo/jsp/Boletim/index.jsp"


class Agritempo(ConectorExterno):
    chave = "agritempo"
    nome = "Agritempo — boletim agrometeorológico"
    ttl_min = 60 * 24

    def _buscar(self, *, uf: str | None = None, **_: Any) -> pd.DataFrame:
        raise RuntimeError(
            "Conector mapeado e não ativado: o balanço hídrico é calculado "
            "internamente (weather/indicadores.py) a partir de ET0 e chuva."
        )

    def _offline(self, **_: Any) -> pd.DataFrame:
        return pd.DataFrame(columns=["cd_ibge", "municipio", "uf",
                                     "balanco_hidrico", "decendio"])

    def disponivel(self) -> bool:
        return False
