"""
AgroSentinela
=============

Plataforma de Inteligência Climática e Comunicação Proativa para
Crédito Rural e Proagro, construída sobre as *Tabelas e Microdados do
Crédito Rural e do Proagro* do Banco Central do Brasil (Sicor/Recor).

Entrega do **Desafio 5 — Comunicação Inteligente** do curso InsurMinds (I2A2).

Arquitetura multiagente:

    CarteiraAgent -> ClimaAgent -> EventoAgent -> RiscoAgent
                  -> RegrasAgent -> RedatorAgent -> DespachanteAgent

mais o CopilotoAgent (Q&A em linguagem natural sobre a carteira).

Licença: MIT
"""

__version__ = "1.0.0"
__app_name__ = "AgroSentinela"
__tagline__ = "Comunicação proativa para crédito rural e Proagro"

__all__ = ["__version__", "__app_name__", "__tagline__"]
