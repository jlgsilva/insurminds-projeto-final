"""
Projeto Final — Comparação de Apólices de D&O (entrega em 06/10/2026).

Este pacote é a **ponte** entre o Desafio 5 e o Projeto Final. Ele não é um
sistema novo: é o mesmo núcleo do AgroSentinela apontado para outro domínio.

O que se reaproveita, sem reescrever:

* **Motor de regras declarativo** (``rules/engine.py``) — lá as regras avaliam
  clima e fase fenológica; aqui avaliam cláusulas e limites. O avaliador de
  expressões baseado em AST, que nunca usa ``eval``, é exatamente o mesmo.
* **Contrato "o modelo redige, as regras decidem"** — a comparação entre
  apólices é calculada em Python, de forma determinística e conferível; o LLM
  apenas redige a leitura em linguagem natural, a partir de um bloco de fatos
  fechado. Numa comparação de apólices isso deixa de ser elegância técnica e
  vira requisito: ninguém pode tomar decisão de cobertura a partir de um
  número que o modelo inventou.
* **Personas** — muda o elenco (gestor de riscos, conselheiro, corretor,
  subscritor, jurídico), mas o mecanismo de tom, canal e profundidade técnica
  é o mesmo.
* **Rastro e auditoria** (``outbox/``) — toda comparação fica registrada.
* **Interface** (``ui.py``, ``viz/``) — filtros, responsividade e componentes.

O que é novo e específico deste domínio está aqui: a **taxonomia de cláusulas**
(``clausulas.py``) e o **comparador** (``comparador.py``).

Estado: estrutura funcional com um conjunto de apólices de exemplo. A carga de
apólices reais e a extração assistida por LLM entram na etapa final.
"""

from .clausulas import (
    CLAUSULAS,
    CLAUSULAS_POR_CODIGO,
    GRUPOS_CLAUSULA,
    Clausula,
    clausulas_do_grupo,
    criticas,
    peso_total,
)
from .comparador import (
    Apolice,
    ComparacaoApolices,
    LacunaCobertura,
    comparar,
    matriz_comparativa,
)

__all__ = [
    "Clausula",
    "CLAUSULAS",
    "CLAUSULAS_POR_CODIGO",
    "GRUPOS_CLAUSULA",
    "clausulas_do_grupo",
    "criticas",
    "peso_total",
    "Apolice",
    "ComparacaoApolices",
    "LacunaCobertura",
    "comparar",
    "matriz_comparativa",
]
