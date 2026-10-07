"""
EventoAgent — identificação de eventos climáticos relevantes.

Etapa 2 do fluxo exigido pelo Desafio 5: *"identificação de eventos
relevantes"*.

Distinção importante em relação ao :mod:`regras`:

* **este agente** olha apenas para o clima e responde "que fenômeno está
  previsto para este território, com que intensidade e em que dia";
* o :class:`RegrasAgent` cruza esse fenômeno com a lavoura financiada, a
  fase fenológica, o histórico do Proagro e a exposição financeira para
  decidir **quem** deve ser comunicado.

Separar as duas coisas mantém o sistema explicável: é possível mostrar o
mapa de eventos do país independentemente da carteira de qualquer cliente.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from ..personas import PESO_SEVERIDADE
from ..rules.catalogo import EVENTOS_POR_CODIGO
from .base import Agente, Contexto

# Escada de limiares por evento: (indicador, [(limiar, severidade), ...]).
# Os mesmos limiares sustentam as regras em rules.yaml — aqui eles servem
# para classificar o *território*, e lá para decidir sobre a *operação*.
ESCADAS: dict[str, list[tuple[str, list[tuple[float, str]]]]] = {
    "seca": [
        ("dias_secos_consecutivos", [(10, "atencao"), (15, "alerta"), (21, "critico")]),
        ("balanco_hidrico_14d", [(-30, "atencao"), (-50, "alerta"), (-80, "critico")]),
    ],
    "chuva_excessiva": [
        ("prec_7d", [(120, "atencao"), (180, "alerta"), (260, "critico")]),
    ],
    "chuva_intensa": [
        ("prec_max_24h", [(50, "atencao"), (80, "alerta"), (120, "critico")]),
    ],
    "granizo": [
        ("prob_granizo", [(30, "atencao"), (45, "alerta"), (65, "critico")]),
    ],
    "geada": [
        ("tmin_min", [(4, "atencao"), (2, "alerta"), (0, "critico")]),
    ],
    "onda_calor": [
        ("dias_tmax_ge_35", [(3, "atencao"), (5, "alerta"), (7, "critico")]),
    ],
    "vendaval": [
        ("rajada_max", [(60, "atencao"), (80, "alerta"), (100, "critico")]),
    ],
    "umidade_colheita": [
        ("dias_com_chuva_7d", [(4, "atencao"), (6, "alerta")]),
    ],
}

# Indicadores em que "menor é pior" (limiar invertido).
INVERTIDOS = {"tmin_min", "balanco_hidrico_14d", "balanco_hidrico_7d"}

# Dia de pico associado a cada evento, para datar a mensagem.
PICO_POR_EVENTO = {
    "seca": "calor",
    "chuva_excessiva": "chuva",
    "chuva_intensa": "chuva",
    "granizo": "convectivo",
    "geada": "frio",
    "onda_calor": "calor",
    "vendaval": "vento",
    "umidade_colheita": "chuva",
}


def _severidade_por_escada(
    valor: float | None, degraus: list[tuple[float, str]], invertido: bool
) -> str | None:
    """Classifica um valor na escada de limiares. ``None`` = sem evento."""
    if valor is None:
        return None
    severidade: str | None = None
    for limiar, sev in degraus:
        atingiu = valor <= limiar if invertido else valor >= limiar
        if atingiu and PESO_SEVERIDADE.get(sev, 0) > PESO_SEVERIDADE.get(severidade or "", 0):
            severidade = sev
    return severidade


class EventoAgent(Agente):
    nome = "EventoAgent"
    papel = "Identificação de eventos climáticos relevantes"
    descricao = (
        "Classifica, para cada célula de grade, quais fenômenos climáticos "
        "estão previstos no horizonte e com que severidade, usando escadas "
        "de limiares objetivas e auditáveis."
    )

    def _executar(self, ctx: Contexto) -> str:
        if ctx.indicadores is None or ctx.indicadores.empty:
            return "Sem indicadores meteorológicos — nenhum evento a identificar."

        # Municípios associados a cada célula (para relatar por território)
        if not ctx.carteira.empty and "cell_id" in ctx.carteira.columns:
            munis = (
                ctx.carteira.dropna(subset=["cell_id"])
                .groupby("cell_id")
                .agg(
                    municipios=("municipio", lambda s: sorted(set(s.dropna()))[:6]),
                    ufs=("uf", lambda s: sorted(set(s.dropna()))),
                    operacoes=("ref_bacen", "count"),
                    exposicao=("valor_credito", "sum"),
                )
                .reset_index()
            )
        else:
            munis = pd.DataFrame(columns=["cell_id", "municipios", "ufs", "operacoes", "exposicao"])

        linhas: list[dict[str, Any]] = []
        for _, ind in ctx.indicadores.iterrows():
            for codigo, criterios in ESCADAS.items():
                sev_final: str | None = None
                gatilhos: dict[str, Any] = {}
                for indicador, degraus in criterios:
                    valor = ind.get(indicador)
                    valor = None if pd.isna(valor) else float(valor)
                    sev = _severidade_por_escada(valor, degraus, indicador in INVERTIDOS)
                    if sev:
                        gatilhos[indicador] = valor
                        if PESO_SEVERIDADE.get(sev, 0) > PESO_SEVERIDADE.get(sev_final or "", 0):
                            sev_final = sev
                if not sev_final:
                    continue

                evento = EVENTOS_POR_CODIGO[codigo]
                chave_pico = PICO_POR_EVENTO.get(codigo, "chuva")
                linhas.append(
                    {
                        "cell_id": ind["cell_id"],
                        "evento": codigo,
                        "evento_nome": evento.nome,
                        "icone": evento.icone,
                        "severidade": sev_final,
                        "severidade_peso": PESO_SEVERIDADE[sev_final],
                        "cobertura_proagro": evento.cobertura_proagro,
                        "gatilhos": gatilhos,
                        "dia_pico": ind.get(f"dia_pico_{chave_pico}", ""),
                        "cor": evento.cor,
                    }
                )

        eventos = pd.DataFrame(linhas)
        if eventos.empty:
            ctx.eventos_municipio = eventos
            return "Nenhum evento climático relevante no horizonte analisado."

        if not munis.empty:
            eventos = eventos.merge(munis, on="cell_id", how="left")
        ctx.eventos_municipio = eventos.sort_values(
            ["severidade_peso", "exposicao"], ascending=False
        ).reset_index(drop=True)

        contagem = (
            ctx.eventos_municipio.groupby("evento_nome")["cell_id"].nunique().sort_values(ascending=False)
        )
        detalhe = "; ".join(f"{nome}: {n} células" for nome, n in contagem.head(4).items())
        criticos = int((ctx.eventos_municipio["severidade"] == "critico").sum())
        return (
            f"{len(ctx.eventos_municipio)} ocorrências em "
            f"{ctx.eventos_municipio['cell_id'].nunique()} células "
            f"({criticos} críticas). {detalhe}."
        )

    def metricas(self, ctx: Contexto) -> dict[str, Any]:
        if ctx.eventos_municipio is None or ctx.eventos_municipio.empty:
            return {"eventos": 0}
        e = ctx.eventos_municipio
        return {
            "eventos": int(len(e)),
            "celulas_afetadas": int(e["cell_id"].nunique()),
            "criticos": int((e["severidade"] == "critico").sum()),
            "alertas": int((e["severidade"] == "alerta").sum()),
            "tipos": int(e["evento"].nunique()),
        }
