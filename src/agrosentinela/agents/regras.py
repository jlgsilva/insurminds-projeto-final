"""
RegrasAgent — aplicação das regras de negócio.

Etapa 3 do fluxo exigido pelo Desafio 5: *"aplicação de regras de negócio"*.

O agente cruza, para cada operação da carteira, três camadas de informação:

1. **o que vem do céu** — indicadores meteorológicos da célula de grade;
2. **o que está no campo** — cultura, fase fenológica, irrigação, área;
3. **o que está no contrato** — valor, vencimento, cobertura, programa.

...e, desde a segunda versão, uma quarta camada:

4. **o que vem de fora** — aderência ao Zarc (janela de plantio oficial),
   normal climática da NASA POWER, rendimento municipal do IBGE, preço de
   referência da CONAB e cobertura por seguro privado do PSR/MAPA.

O resultado é uma lista de :class:`~agrosentinela.models.Alerta`, cada um
carregando as regras que dispararam, os valores que as dispararam e um
score de risco de 0 a 100. Nenhuma decisão aqui depende de LLM.

O Zarc entra no cálculo por um caminho explícito e auditável: o escore é
multiplicado por um fator entre 0,85 (plantio dentro da janela recomendada)
e 1,25 (vários decêndios fora dela). O fator, o número de decêndios e a
explicação em texto ficam registrados no alerta, de modo que qualquer pessoa
consiga refazer a conta.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from ..external.registry import enriquecer_alerta
from ..external.zarc import avaliar_plantio
from ..models import Alerta
from ..rules.catalogo import EVENTOS_POR_CODIGO
from ..rules.engine import MotorRegras
from ..utils.formato import inteiro, reais_compacto
from .base import Agente, Contexto
from .evento import PICO_POR_EVENTO


class RegrasAgent(Agente):
    nome = "RegrasAgent"
    papel = "Aplicação das regras de negócio e cálculo de risco"
    descricao = (
        "Avalia cada operação contra o catálogo declarativo de regras "
        "(rules.yaml), combinando clima, fase fenológica, histórico do "
        "Proagro e exposição financeira, e produz alertas com score e "
        "justificativa rastreável."
    )

    def __init__(self, motor: MotorRegras | None = None) -> None:
        super().__init__()
        self.motor = motor or MotorRegras()

    # ------------------------------------------------------------------
    def _executar(self, ctx: Contexto) -> str:
        if ctx.carteira.empty:
            return "Carteira vazia."
        if ctx.indicadores is None or ctx.indicadores.empty:
            return "Sem indicadores meteorológicos — nenhuma regra avaliada."

        indicadores_por_celula: dict[str, dict[str, Any]] = {
            str(r["cell_id"]): {k: v for k, v in r.items() if k != "cell_id"}
            for _, r in ctx.indicadores.iterrows()
        }

        # Eventos identificados por célula (severidade territorial)
        eventos_por_celula: dict[str, list[dict[str, Any]]] = {}
        if ctx.eventos_municipio is not None and not ctx.eventos_municipio.empty:
            for cell, grupo in ctx.eventos_municipio.groupby("cell_id"):
                eventos_por_celula[str(cell)] = grupo.to_dict("records")

        alertas: list[Alerta] = []
        avaliadas = 0

        for _, op in ctx.carteira.iterrows():
            cell = op.get("cell_id")
            if not cell or str(cell) not in indicadores_por_celula:
                continue
            avaliadas += 1
            ind = indicadores_por_celula[str(cell)]
            eventos_celula = eventos_por_celula.get(str(cell), [])
            if not eventos_celula:
                continue

            contexto_base = self._montar_contexto(op, ind)

            # Uma avaliação por evento presente no território: assim cada
            # alerta fala de um fenômeno só, o que torna a mensagem clara.
            for ev in eventos_celula:
                codigo_evento = str(ev["evento"])
                ctx_evt = dict(contexto_base)
                ctx_evt["evento_territorial"] = codigo_evento
                ctx_evt["severidade_territorial"] = ev["severidade"]
                ctx_evt["sensibilidade_fase"] = float(
                    (op.get("_sensibilidade") or {}).get(codigo_evento, 1.0)
                )
                ctx_evt["freq_evento_municipio"] = float(
                    (op.get("hist_eventos") or {}).get(codigo_evento, 0.0)
                )

                regras_do_evento = [
                    r for r in self.motor.regras
                    if r.evento == codigo_evento or r.aplica_a_qualquer_evento
                ]
                acionamentos = self.motor.avaliar(ctx_evt, regras=regras_do_evento)
                if not acionamentos:
                    continue

                melhor = acionamentos[0]
                score = max(a.score for a in acionamentos)

                # --- Zarc: atenua quem plantou na janela, agrava quem não ---
                zarc = avaliar_plantio(
                    str(op.get("cultura") or ""),
                    str(op.get("regiao") or ""),
                    _data_ou_none(op.get("dt_inic_plantio")),
                )
                if zarc["avaliavel"]:
                    score = min(100.0, score * float(zarc["fator"]))

                if score < self.motor.pesos.limiar_notificacao:
                    continue

                # --- fatos externos, determinísticos e conferíveis ----------
                perda_hist = float(
                    (op.get("hist_perda_evento") or {}).get(codigo_evento, 0.0)
                )
                externo = enriquecer_alerta(
                    cultura=str(op.get("cultura") or ""),
                    regiao=str(op.get("regiao") or ""),
                    uf=str(op.get("uf") or ""),
                    area_ha=float(op.get("area_ha") or 0.0),
                    perda_estimada_pct=perda_hist,
                    dt_plantio=_data_ou_none(op.get("dt_inic_plantio")),
                    chuva_prevista_mm=_num_ou_none(ind.get("prec_7d")),
                    # A normal da NASA POWER é mensal; a previsão é de 7 dias.
                    # Comparar os dois sem ajustar daria uma anomalia falsa de
                    # ~4x para todo município. Aqui a normal é reescalada para
                    # a mesma janela antes da comparação.
                    chuva_normal_mm=_normal_na_janela(
                        op.get("chuva_normal_mm_mes"), dias=7),
                    tem_proagro_pct=float(op.get("cobertura_municipio") or 0.0),
                )
                externo["base_perda"] = (
                    "perda média histórica comprovada no Proagro para este "
                    "evento e cultura neste município"
                    if perda_hist > 0 else "sem histórico comprovado suficiente"
                )
                externo["deferimento_historico"] = float(
                    (op.get("hist_deferimento_evento") or {}).get(codigo_evento, 0.0)
                )
                externo["prazo_pagamento_dias"] = float(
                    op.get("prazo_pagamento_municipio") or 0.0
                )
                externo["motivo_negativa_frequente"] = str(
                    op.get("motivo_negativa_municipio") or ""
                )

                evento_info = EVENTOS_POR_CODIGO.get(codigo_evento)
                chave_pico = PICO_POR_EVENTO.get(codigo_evento, "chuva")
                alertas.append(
                    Alerta(
                        id=Alerta.novo_id(op.get("ref_bacen"), op.get("nu_ordem"),
                                          codigo_evento, ctx.data_ref),
                        ref_bacen=str(op.get("ref_bacen", "")),
                        nu_ordem=int(op.get("nu_ordem", 1) or 1),
                        cd_ibge=int(op.get("cd_ibge", 0) or 0),
                        municipio=str(op.get("municipio", "")),
                        uf=str(op.get("uf", "")),
                        regiao=str(op.get("regiao", "")),
                        lat=float(op.get("lat") or 0.0),
                        lon=float(op.get("lon") or 0.0),
                        cell_id=str(cell),
                        cultura=str(op.get("cultura", "")),
                        produto=str(op.get("produto", "")),
                        fase=str(op.get("fase", "")),
                        fase_nome=str(op.get("fase_nome", "")),
                        recomendacao_fase=str(op.get("recomendacao_fase", "") or ""),
                        area_ha=float(op.get("area_ha") or 0.0),
                        valor_credito=float(op.get("valor_credito") or 0.0),
                        programa=str(op.get("programa", "")),
                        instituicao=str(op.get("instituicao", "")),
                        tipo_seguro=str(op.get("tipo_seguro", "")),
                        tem_cobertura=bool(op.get("tem_cobertura", False)),
                        irrigada=bool(op.get("irrigada", False)),
                        dias_para_colheita=_num_ou_none(op.get("dias_para_colheita")),
                        dias_para_vencimento=_num_ou_none(op.get("dias_para_vencimento")),
                        persona=str(op.get("persona", "produtor_familiar")),
                        evento=codigo_evento,
                        evento_nome=evento_info.nome if evento_info else codigo_evento,
                        severidade=melhor.severidade,
                        score=score,
                        dia_pico=str(ind.get(f"dia_pico_{chave_pico}", "") or ""),
                        janela_acao_h=min(a.janela_acao_h for a in acionamentos),
                        cobertura_proagro_evento=bool(evento_info.cobertura_proagro)
                        if evento_info else False,
                        acionamentos=[a.to_dict() for a in acionamentos],
                        indicadores={
                            k: v for k, v in ind.items()
                            if not str(k).startswith("dia_pico_") and pd.notna(v)
                        },
                        historico_municipio={
                            "freq_evento": ctx_evt["freq_evento_municipio"],
                            "taxa_acionamento": float(op.get("taxa_acionamento_municipio") or 0.0),
                            "perda_media_pct": perda_hist,
                            "taxa_deferimento": externo["deferimento_historico"],
                            "prazo_pagamento_dias": externo["prazo_pagamento_dias"],
                        },
                        contexto_externo=externo,
                    )
                )

        alertas.sort(key=lambda a: (-a.severidade_peso, -a.score))
        ctx.alertas = alertas

        if not alertas:
            return (
                f"{inteiro(avaliadas)} operações avaliadas; nenhuma atingiu o "
                f"limiar de notificação (score ≥ {self.motor.pesos.limiar_notificacao:.0f})."
            )

        exposicao = sum(a.valor_credito for a in alertas)
        criticos = sum(1 for a in alertas if a.severidade == "critico")
        return (
            f"{inteiro(len(alertas))} alertas de {inteiro(avaliadas)} operações avaliadas "
            f"({criticos} críticos); {reais_compacto(exposicao)} de exposição sinalizada; "
            f"{len(self.motor.regras)} regras (v{self.motor.versao})."
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _montar_contexto(op: pd.Series, indicadores: dict[str, Any]) -> dict[str, Any]:
        """Junta indicadores meteorológicos e atributos da operação."""
        ctx: dict[str, Any] = {
            k: (None if pd.isna(v) else v)
            for k, v in indicadores.items()
            if not str(k).startswith("dia_pico_")
        }
        ctx.update(
            {
                "fase": op.get("fase"),
                "cultura": op.get("cultura"),
                "cultura_grupo": op.get("cultura_grupo"),
                "progresso_ciclo": _num_ou_none(op.get("progresso_ciclo")),
                "dias_para_colheita": _num_ou_none(op.get("dias_para_colheita")),
                "dias_para_vencimento": _num_ou_none(op.get("dias_para_vencimento")),
                "dias_desde_plantio": _num_ou_none(op.get("dias_desde_plantio")),
                "tem_cobertura": bool(op.get("tem_cobertura", False)),
                "irrigada": bool(op.get("irrigada", False)),
                "area_ha": float(op.get("area_ha") or 0.0),
                "valor_credito": float(op.get("valor_credito") or 0.0),
                "exposicao_municipio": float(op.get("exposicao_municipio") or 0.0),
                "operacoes_municipio": int(op.get("operacoes_municipio") or 0),
                "sinistralidade_municipio": float(op.get("taxa_acionamento_municipio") or 0.0),
                "programa": op.get("programa"),
                "modalidade": op.get("modalidade"),
                "persona": op.get("persona"),
                "uf": op.get("uf"),
                "regiao": op.get("regiao"),
            }
        )
        return ctx

    # ------------------------------------------------------------------
    def metricas(self, ctx: Contexto) -> dict[str, Any]:
        if not ctx.alertas:
            return {"alertas": 0, "regras_carregadas": len(self.motor.regras)}
        df = pd.DataFrame([a.to_row() for a in ctx.alertas])
        return {
            "alertas": int(len(df)),
            "criticos": int((df["severidade"] == "critico").sum()),
            "operacoes_distintas": int(df["ref_bacen"].nunique()),
            "municipios": int(df["cd_ibge"].nunique()),
            "exposicao": float(df["valor_credito"].sum()),
            "score_medio": round(float(df["score"].mean()), 1),
            "regras_carregadas": len(self.motor.regras),
        }


def _normal_na_janela(normal_mensal: Any, *, dias: int) -> float | None:
    """Reescala uma normal mensal para uma janela de ``dias`` dias."""
    valor = _num_ou_none(normal_mensal)
    if valor is None or valor <= 0:
        return None
    return round(valor * dias / 30.0, 1)


def _data_ou_none(valor: Any):
    """Converte a data do Sicor em ``datetime.date``, ou ``None``."""
    try:
        if valor is None or pd.isna(valor):
            return None
        return pd.Timestamp(valor).date()
    except (TypeError, ValueError):
        return None


def _num_ou_none(valor: Any) -> float | None:
    try:
        if valor is None or pd.isna(valor):
            return None
        return float(valor)
    except (TypeError, ValueError):
        return None
