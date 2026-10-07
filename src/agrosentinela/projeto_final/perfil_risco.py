"""
Perfil de risco da tomadora — a ponte com os microdados do Sicor (Desafio 5).

Comparar apólices com pesos fixos ignora uma pergunta essencial: *para quem*
é a apólice? A cláusula de crédito rural (AGR-01) vale muito para uma
cooperativa de crédito e quase nada para um frigorífico; a cobertura de
defesa ambiental pesa mais no Matopiba e na Amazônia Legal; a cobertura em
recuperação judicial importa mais onde a sinistralidade agrícola é alta.

Este agente usa a mesma base do AgroSentinela (operações de crédito rural do
Sicor, histórico de acionamento do Proagro e saldos/atrasos) para montar o
contexto da UF da tomadora e **ajustar os pesos** da taxonomia. Os ajustes
são regras explícitas, cada uma com justificativa — a comparação continua
auditável, só que agora contextualizada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from .clausulas import CLAUSULAS_POR_CODIGO

# Amazônia Legal + Matopiba: fronteira agrícola com maior exposição a
# embargos ambientais, CAR e rastreabilidade de fornecedores.
UF_FRONTEIRA_AMBIENTAL = {"AC", "AM", "AP", "PA", "RO", "RR", "TO", "MT", "MA", "PI", "BA"}

SEGMENTOS_CREDITO = ("cooperativa de crédito", "fintech", "securitizadora", "trading",
                     "revenda", "cooperativa agroindustrial")


@dataclass
class AjustePeso:
    codigo: str
    fator: float
    motivo: str


@dataclass
class PerfilRisco:
    tomadora: str
    uf: str
    segmento: str
    indicadores: dict[str, Any] = field(default_factory=dict)
    ajustes: list[AjustePeso] = field(default_factory=list)

    def pesos(self) -> dict[str, float]:
        """Peso efetivo por cláusula (peso base × fatores)."""
        out = {c: float(cl.peso) for c, cl in CLAUSULAS_POR_CODIGO.items()}
        for a in self.ajustes:
            out[a.codigo] = round(out[a.codigo] * a.fator, 2)
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "tomadora": self.tomadora, "uf": self.uf, "segmento": self.segmento,
            "indicadores": self.indicadores,
            "ajustes": [a.__dict__ for a in self.ajustes],
        }


def indicadores_uf(base: Any, uf: str) -> dict[str, Any]:
    """Indicadores do Sicor/Proagro para a UF (da base do Desafio 5)."""
    ind: dict[str, Any] = {"uf": uf, "fonte": getattr(base, "origem", "?")}
    if base is None:
        return ind
    cart: pd.DataFrame = base.carteira
    c_uf = cart[cart["uf"] == uf] if "uf" in cart else cart.iloc[0:0]
    total_br = float(cart["valor_credito"].sum()) if not cart.empty else 0.0
    ind["operacoes_credito_rural"] = int(len(c_uf))
    ind["credito_rural_rs"] = float(c_uf["valor_credito"].sum()) if not c_uf.empty else 0.0
    ind["participacao_credito_pct"] = (round(100 * ind["credito_rural_rs"] / total_br, 1)
                                       if total_br else 0.0)
    if not c_uf.empty and "tem_cobertura" in c_uf:
        ind["sem_cobertura_pct"] = round(100 * (1 - c_uf["tem_cobertura"].astype(bool).mean()), 1)
    sin: pd.DataFrame = base.proagro_sinistros
    s_uf = sin[sin["uf"] == uf] if "uf" in sin else sin.iloc[0:0]
    if not s_uf.empty:
        pesos = s_uf["n_operacoes"].clip(lower=1)
        ind["taxa_acionamento_proagro_pct"] = round(
            100 * float((s_uf["taxa_acionamento"] * pesos).sum() / pesos.sum()), 2)
        media_br = sin["taxa_acionamento"].mean() if not sin.empty else 0
        ind["taxa_acionamento_proagro_brasil_pct"] = round(100 * float(media_br), 2)
        ind["evento_mais_frequente"] = (s_uf.groupby("evento")["n_cop"].sum()
                                        .sort_values(ascending=False).index[0])
    exp: pd.DataFrame = getattr(base, "exposicao", pd.DataFrame())
    if not exp.empty and "uf" in exp:
        e_uf = exp[exp["uf"] == uf]
        if not e_uf.empty:
            ind["operacoes_em_atraso_pct"] = round(100 * float((e_uf["dias_em_atraso"] > 0).mean()), 1)
            ind["renegociadas_pct"] = round(100 * float(e_uf["renegociada"].astype(bool).mean()), 1)
    return ind


def montar_perfil(tomadora: str, uf: str, segmento: str, base: Any = None,
                  *, capital_aberto: bool | None = None,
                  exterior: bool | None = None) -> PerfilRisco:
    uf = (uf or "").upper()
    seg = (segmento or "").lower()
    p = PerfilRisco(tomadora=tomadora, uf=uf, segmento=segmento,
                    indicadores=indicadores_uf(base, uf))
    ind = p.indicadores

    if any(s in seg for s in SEGMENTOS_CREDITO):
        p.ajustes.append(AjustePeso(
            "AGR-01", 1.6, f"Segmento '{segmento}' concede, repassa ou financia crédito rural: "
            "exposição direta a processo sancionador do BCB (MCR/Sicor/Proagro)."))
        p.ajustes.append(AjustePeso(
            "DEF-05", 1.25, "Multas administrativas do BCB são o desfecho típico de "
            "irregularidade em crédito rural."))
    if uf in UF_FRONTEIRA_AMBIENTAL:
        p.ajustes.append(AjustePeso(
            "AGR-02", 1.6, f"{uf} está na Amazônia Legal/Matopiba: embargos, CAR e "
            "rastreabilidade de fornecedores alcançam o administrador."))
        p.ajustes.append(AjustePeso(
            "EXC-03", 1.4, "Exclusão ambiental ampla pesa mais em fronteira agrícola."))
    tx, tx_br = ind.get("taxa_acionamento_proagro_pct"), ind.get(
        "taxa_acionamento_proagro_brasil_pct")
    if tx is not None and tx_br and tx > tx_br:
        p.ajustes.append(AjustePeso(
            "AGR-03", 1.4, f"Acionamento do Proagro na UF ({tx:.1f}%) acima da média "
            f"nacional ({tx_br:.1f}%): maior risco de quebra de safra e recuperação "
            "judicial na cadeia."))
    atraso = ind.get("operacoes_em_atraso_pct")
    if atraso is not None and atraso >= 10:
        p.ajustes.append(AjustePeso(
            "ESC-02", 1.2, f"{atraso:.0f}% das operações de crédito rural da UF em atraso: "
            "cenário de estresse em que a companhia pode não indenizar o administrador."))
    if capital_aberto or "s.a." in tomadora.lower() and "securitizadora" in seg:
        p.ajustes.append(AjustePeso(
            "ESC-04", 1.3, "Companhia com valores mobiliários emitidos: Side C relevante."))
    if exterior or any(s in seg for s in ("trading", "exportadora", "celulose", "frigor")):
        p.ajustes.append(AjustePeso(
            "ESC-05", 1.3, "Operação ou investidores no exterior: jurisdição estrangeira "
            "é risco concreto."))
    return p
