"""
ClimaAgent — coleta de dados meteorológicos externos.

Etapa 1 do fluxo exigido pelo Desafio 5: *"coleta de informações em uma
fonte externa de dados meteorológicos"*.

Estratégia de eficiência: a carteira pode ter milhares de operações, mas
elas se concentram em poucas centenas de municípios e, depois da
deduplicação por célula de grade (~11 km), em ainda menos pontos. O agente:

1. reduz a carteira ao conjunto de municípios distintos;
2. prioriza por exposição financeira quando há limite de cota;
3. deduplica municípios que caem na mesma célula;
4. consulta a Open-Meteo em lote;
5. calcula os indicadores derivados por célula.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from ..config import get_settings
from ..utils.formato import inteiro
from ..weather.indicadores import calcular_por_celula
from ..weather.open_meteo import celulas_de_municipios, obter_provedor, para_celula
from .base import Agente, Contexto


class ClimaAgent(Agente):
    nome = "ClimaAgent"
    papel = "Coleta de dados meteorológicos externos"
    descricao = (
        "Consulta a API pública Open-Meteo (previsão de até 16 dias e "
        "histórico recente) para cada célula de grade onde existe operação "
        "de crédito rural, e calcula os indicadores que alimentam as regras."
    )

    def _executar(self, ctx: Contexto) -> str:
        settings = get_settings()
        if ctx.carteira.empty:
            return "Sem carteira — coleta meteorológica dispensada."

        municipios = (
            ctx.carteira.dropna(subset=["lat", "lon"])
            .groupby(["cd_ibge", "municipio", "uf", "lat", "lon"], as_index=False)
            .agg(exposicao=("valor_credito", "sum"), operacoes=("ref_bacen", "count"))
            .sort_values("exposicao", ascending=False)
        )
        if municipios.empty:
            ctx.avisar(
                "Nenhuma operação com coordenada geográfica — sem isso não há "
                "como consultar a previsão do tempo."
            )
            return "Nenhum município georreferenciado."

        limite = settings.clima_max_municipios
        total_municipios = len(municipios)
        if total_municipios > limite:
            municipios = municipios.head(limite)
            ctx.avisar(
                f"Consulta meteorológica limitada aos {limite} municípios de maior "
                f"exposição (de {total_municipios}), para respeitar a cota da API "
                "pública. Ajuste em CLIMA_MAX_MUNICIPIOS."
            )

        registros_muni = municipios.to_dict("records")
        celulas, _ = celulas_de_municipios(registros_muni)

        provedor = obter_provedor(
            ctx.modo_clima, cenario=ctx.cenario, intensidade=ctx.intensidade_cenario
        )
        self.log.info(
            "Consultando %s para %d células (%d municípios).",
            provedor.nome, len(celulas), len(municipios),
        )
        registros = provedor.series_diarias(
            celulas,
            dias_passados=21,
            dias_previsao=max(ctx.horizonte_dias + 3, settings.dias_previsao),
        )
        clima = pd.DataFrame(registros)
        if clima.empty:
            ctx.avisar("A fonte meteorológica não devolveu dados.")
            return "Nenhum dado meteorológico obtido."

        ctx.clima_diario = clima
        ctx.indicadores = calcular_por_celula(
            clima, data_ref=ctx.data_ref, horizonte_dias=ctx.horizonte_dias
        )

        # Vincula cada operação da carteira à sua célula de grade.
        ctx.carteira = ctx.carteira.copy()
        ctx.carteira["cell_id"] = [
            para_celula(float(la), float(lo)).id if pd.notna(la) and pd.notna(lo) else None
            for la, lo in zip(ctx.carteira["lat"], ctx.carteira["lon"])
        ]

        fontes = sorted(clima["fonte"].dropna().unique().tolist()) if "fonte" in clima else []
        if "sintetico" in fontes and ctx.cenario is None and ctx.modo_clima != "sintetico":
            ctx.avisar(
                "Parte das séries veio do gerador sintético porque a API pública "
                "não respondeu. Os alertas continuam demonstráveis, mas não "
                "refletem a previsão real."
            )

        return (
            f"{inteiro(len(clima))} registros diários de {len(celulas)} células "
            f"({', '.join(fontes) or 'fonte não identificada'}); indicadores "
            f"calculados para {len(ctx.indicadores)} células."
        )

    def metricas(self, ctx: Contexto) -> dict[str, Any]:
        if ctx.clima_diario.empty:
            return {}
        return {
            "celulas": int(ctx.clima_diario["cell_id"].nunique()),
            "dias": int(ctx.clima_diario["data"].nunique()),
            "registros": int(len(ctx.clima_diario)),
            "fonte": ", ".join(sorted(ctx.clima_diario.get("fonte", pd.Series(dtype=str)).dropna().unique())),
        }
