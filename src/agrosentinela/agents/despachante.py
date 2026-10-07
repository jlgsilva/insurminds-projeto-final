"""
DespachanteAgent — simulação do envio das notificações.

Etapa 5 do fluxo exigido pelo Desafio 5: *"simulação do envio das
notificações"*. O enunciado dispensa o envio real de SMS, e-mail ou push;
este agente modela o que uma central real faria, **sem disparar nada**:

* aplica a política anti-fadiga (janela de repetição e teto diário);
* respeita a janela de contato de cada persona (não acorda produtor às 3h);
* escolhe a prioridade de despacho pela severidade e pela janela de ação;
* simula latência, tentativas e taxa de falha por canal;
* estima o custo que o envio real teria — informação útil para dimensionar
  a operação;
* grava tudo na caixa de saída SQLite, com ``simulado = verdadeiro``.
"""

from __future__ import annotations

import random
from datetime import datetime, time, timedelta
from typing import Any

from ..models import Envio, Mensagem
from ..personas import PESO_SEVERIDADE, get_persona
from ..rules.engine import MotorRegras
from ..utils.formato import reais
from ..outbox.store import Outbox
from .base import Agente, Contexto

# Perfil operacional simulado de cada canal:
# (custo unitário em R$, latência média em ms, taxa de falha)
PERFIL_CANAL: dict[str, tuple[float, int, float]] = {
    "sms": (0.0850, 1800, 0.030),
    "whatsapp": (0.0450, 900, 0.018),
    "push": (0.0008, 350, 0.045),
    "email": (0.0012, 1200, 0.012),
    "painel": (0.0000, 120, 0.002),
    "voz": (0.3200, 6500, 0.070),
}


class DespachanteAgent(Agente):
    nome = "DespachanteAgent"
    papel = "Simulação do envio das notificações"
    descricao = (
        "Aplica a política anti-fadiga e a janela de contato de cada persona, "
        "ordena a fila por urgência, simula o despacho por canal (latência, "
        "falha e custo) e registra tudo na caixa de saída — sem enviar "
        "nenhuma mensagem real."
    )

    def __init__(
        self,
        outbox: Outbox | None = None,
        motor: MotorRegras | None = None,
        *,
        semente: int = 42,
    ) -> None:
        super().__init__()
        self.outbox = outbox or Outbox()
        self.motor = motor or MotorRegras()
        self.rng = random.Random(semente)

    # ------------------------------------------------------------------
    def _executar(self, ctx: Contexto) -> str:
        if not ctx.mensagens:
            return "Nenhuma mensagem para despachar."

        if ctx.respeitar_supressao:
            historico = self.outbox.historico_envios(self.motor.supressao.janela_repeticao_h)
            enviados_hoje = self.outbox.contagem_hoje()
        else:
            # Modo demonstração: ignora o histórico para que a mesma execução
            # possa ser repetida sem que tudo apareça como suprimido.
            historico, enviados_hoje = {}, {}
        agora = datetime.now()

        fila = sorted(
            ctx.mensagens,
            key=lambda m: (
                -PESO_SEVERIDADE.get(m.severidade, 0),
                -m.score,
            ),
        )

        envios: list[Envio] = []
        for msg in fila:
            chave = f"{msg.destinatario_id}|{msg.canal}"
            suprimir, motivo = self.motor.deve_suprimir(
                chave=chave,
                severidade=msg.severidade,
                historico=historico,
                agora=agora,
                enviados_hoje=enviados_hoje.get(msg.destinatario_id, 0),
            )
            if suprimir:
                envios.append(
                    Envio(
                        id=f"ENV-{msg.id[4:]}",
                        mensagem_id=msg.id,
                        canal=msg.canal,
                        destinatario=msg.destinatario_id,
                        status="suprimido",
                        motivo=motivo,
                        tentativas=0,
                        latencia_ms=0,
                        custo_estimado=0.0,
                    )
                )
                continue

            agendado = self._agendar(msg, agora)
            envios.append(self._simular(msg, agendado))
            enviados_hoje[msg.destinatario_id] = enviados_hoje.get(msg.destinatario_id, 0) + 1
            historico[chave] = agora

        ctx.envios = envios

        entregues = [e for e in envios if e.status == "simulado_entregue"]
        falhas = [e for e in envios if e.status == "simulado_falha"]
        suprimidos = [e for e in envios if e.status == "suprimido"]
        custo = sum(e.custo_estimado for e in envios)

        return (
            f"{len(entregues)} entregas simuladas, {len(falhas)} falhas simuladas, "
            f"{len(suprimidos)} suprimidas pela política anti-fadiga. "
            f"Custo equivalente de um envio real: {reais(custo, 2)}."
        )

    # ------------------------------------------------------------------
    def _agendar(self, msg: Mensagem, agora: datetime) -> datetime:
        """
        Respeita a janela de contato da persona.

        Um alerta crítico com janela de ação curta é despachado de imediato,
        porque o custo de esperar supera o incômodo — e isso fica registrado
        no motivo do envio.
        """
        persona = get_persona(msg.persona)
        if msg.severidade == "critico":
            return agora
        try:
            ini_txt, fim_txt = persona.janela_contato.replace("h", "").split("-")
            ini, fim = int(ini_txt), int(fim_txt)
        except (ValueError, AttributeError):
            ini, fim = 7, 20

        hora = agora.hour
        if ini <= hora < fim:
            return agora
        alvo = agora.replace(hour=ini, minute=0, second=0, microsecond=0)
        if hora >= fim:
            alvo += timedelta(days=1)
        return alvo

    # ------------------------------------------------------------------
    def _simular(self, msg: Mensagem, agendado: datetime) -> Envio:
        custo_base, latencia_base, taxa_falha = PERFIL_CANAL.get(msg.canal, (0.001, 500, 0.02))
        tentativas = 1
        falhou = self.rng.random() < taxa_falha
        if falhou:
            # Reenvio automático: canais transacionais tentam de novo
            tentativas = 2
            falhou = self.rng.random() < taxa_falha

        latencia = max(80, int(self.rng.gauss(latencia_base, latencia_base * 0.28))) * tentativas
        atrasado = agendado > datetime.now()
        motivo = ""
        if atrasado:
            motivo = (
                f"Agendado para {agendado.strftime('%d/%m %H:%M')} — fora da janela "
                f"de contato da persona."
            )
        elif tentativas > 1:
            motivo = "Entregue na segunda tentativa (falha transitória simulada)."

        return Envio(
            id=f"ENV-{msg.id[4:]}",
            mensagem_id=msg.id,
            canal=msg.canal,
            destinatario=msg.destinatario_id,
            status="simulado_falha" if falhou else "simulado_entregue",
            motivo=motivo or ("Falha definitiva simulada no canal." if falhou else "Entrega simulada com sucesso."),
            tentativas=tentativas,
            latencia_ms=latencia,
            custo_estimado=round(custo_base * tentativas, 4),
            agendado_para=agendado.isoformat(timespec="minutes"),
            simulado=True,
        )

    # ------------------------------------------------------------------
    def metricas(self, ctx: Contexto) -> dict[str, Any]:
        if not ctx.envios:
            return {"envios": 0}
        return {
            "envios": len(ctx.envios),
            "entregues": sum(1 for e in ctx.envios if e.status == "simulado_entregue"),
            "falhas": sum(1 for e in ctx.envios if e.status == "simulado_falha"),
            "suprimidos": sum(1 for e in ctx.envios if e.status == "suprimido"),
            "custo_estimado": round(sum(e.custo_estimado for e in ctx.envios), 4),
            "latencia_media_ms": int(
                sum(e.latencia_ms for e in ctx.envios) / max(len(ctx.envios), 1)
            ),
        }
