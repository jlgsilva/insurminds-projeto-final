"""
Conectores de dados externos — **gratuitos, públicos e livres**.

Todo conector desta pasta obedece ao mesmo contrato (``base.ConectorExterno``)
e degrada graciosamente: rede → cache → referência embutida, sempre com a
procedência declarada até a tela. Nenhum exige chave de API; nenhum é
obrigatório para o funcionamento do pipeline.

O catálogo descritivo das fontes (licença, órgão, granularidade, papel) fica
em ``agrosentinela.fontes_externas``; aqui ficam as implementações.
"""

from .base import ConectorExterno, ResultadoExterno
from .registry import (
    CONECTORES,
    contexto_municipal,
    diagnostico,
    enriquecer_alerta,
    obter_conector,
    sondar,
)

__all__ = [
    "ConectorExterno",
    "ResultadoExterno",
    "CONECTORES",
    "obter_conector",
    "contexto_municipal",
    "diagnostico",
    "sondar",
    "enriquecer_alerta",
]
