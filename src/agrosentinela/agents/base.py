"""
Infraestrutura comum dos agentes.

Cada agente do AgroSentinela é uma unidade com **uma responsabilidade
única**, contrato de entrada e saída explícito e rastro de execução
próprio. O orquestrador encadeia os agentes e agrega os rastros, o que
permite mostrar na interface exatamente o que cada etapa fez, quanto tempo
levou e o que produziu.

A classe base é deliberadamente simples (não depende de nenhum framework
de agentes): o objetivo didático do Desafio 5 é evidenciar a *arquitetura*,
e um encadeamento explícito é mais auditável do que um grafo implícito.
O contrato, porém, é compatível com LangGraph/CrewAI — cada ``executar``
recebe e devolve o mesmo ``Contexto``, que funciona como estado do grafo.
"""

from __future__ import annotations

import time
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import pandas as pd

from ..utils.logging_setup import get_logger


@dataclass
class RastroEtapa:
    """Registro de execução de um agente."""

    agente: str
    papel: str
    inicio: str
    duracao_s: float
    sucesso: bool
    resumo: str
    metricas: dict[str, Any] = field(default_factory=dict)
    erro: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "agente": self.agente,
            "papel": self.papel,
            "início": self.inicio,
            "duração_s": round(self.duracao_s, 3),
            "status": "ok" if self.sucesso else "erro",
            "resumo": self.resumo,
            **{f"m_{k}": v for k, v in self.metricas.items()},
            "erro": self.erro or "",
        }


@dataclass
class Contexto:
    """
    Estado compartilhado que atravessa todo o pipeline.

    Funciona como o "quadro-negro" da arquitetura multiagente: cada agente
    lê o que precisa e escreve o seu produto, sem conhecer os demais.
    """

    # --- entrada -----------------------------------------------------------
    data_ref: date = field(default_factory=date.today)
    horizonte_dias: int = 7
    filtros: dict[str, Any] = field(default_factory=dict)
    cenario: str | None = None
    intensidade_cenario: float = 1.0
    modo_clima: str = "auto"
    usar_llm: bool = True
    max_mensagens: int = 40
    canais_ativos: tuple[str, ...] = ("whatsapp", "sms", "email", "push", "painel")
    respeitar_supressao: bool = True

    # --- dados -------------------------------------------------------------
    base: Any = None                       # BaseDados
    carteira: pd.DataFrame = field(default_factory=pd.DataFrame)
    clima_diario: pd.DataFrame = field(default_factory=pd.DataFrame)
    indicadores: pd.DataFrame = field(default_factory=pd.DataFrame)
    eventos_municipio: pd.DataFrame = field(default_factory=pd.DataFrame)
    alertas: list[Any] = field(default_factory=list)
    mensagens: list[Any] = field(default_factory=list)
    envios: list[Any] = field(default_factory=list)

    # --- observabilidade ---------------------------------------------------
    rastro: list[RastroEtapa] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    telemetria_llm: Any = None
    iniciado_em: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    # ----------------------------------------------------------------------
    def registrar(self, etapa: RastroEtapa) -> None:
        self.rastro.append(etapa)

    def avisar(self, mensagem: str) -> None:
        if mensagem not in self.avisos:
            self.avisos.append(mensagem)

    @property
    def duracao_total_s(self) -> float:
        return round(sum(e.duracao_s for e in self.rastro), 3)

    def rastro_df(self) -> pd.DataFrame:
        return pd.DataFrame([e.to_dict() for e in self.rastro])

    def resumo(self) -> dict[str, Any]:
        return {
            "data_referência": self.data_ref.isoformat(),
            "horizonte_dias": self.horizonte_dias,
            "operações_monitoradas": int(len(self.carteira)),
            "municípios_consultados": int(self.indicadores["cell_id"].nunique())
            if not self.indicadores.empty and "cell_id" in self.indicadores
            else 0,
            "eventos_detectados": int(len(self.eventos_municipio)),
            "alertas_gerados": len(self.alertas),
            "mensagens_geradas": len(self.mensagens),
            "envios_simulados": len(self.envios),
            "duração_total_s": self.duracao_total_s,
            "avisos": self.avisos,
        }


class Agente(ABC):
    """Classe base de todos os agentes."""

    nome: str = "Agente"
    papel: str = ""
    descricao: str = ""

    def __init__(self) -> None:
        self.log = get_logger(f"agente.{self.nome}")

    @abstractmethod
    def _executar(self, ctx: Contexto) -> str:
        """Lógica do agente. Deve devolver um resumo textual curto."""

    def metricas(self, ctx: Contexto) -> dict[str, Any]:  # noqa: ARG002
        """Métricas específicas do agente (sobrescrever quando útil)."""
        return {}

    def executar(self, ctx: Contexto) -> Contexto:
        """Executa o agente, cronometrando e capturando falhas."""
        inicio_ts = time.perf_counter()
        inicio_iso = datetime.now().isoformat(timespec="seconds")
        self.log.info("▶ %s — %s", self.nome, self.papel)
        try:
            resumo = self._executar(ctx)
            duracao = time.perf_counter() - inicio_ts
            etapa = RastroEtapa(
                agente=self.nome,
                papel=self.papel,
                inicio=inicio_iso,
                duracao_s=duracao,
                sucesso=True,
                resumo=resumo,
                metricas=self.metricas(ctx),
            )
            self.log.info("✔ %s (%.2fs) — %s", self.nome, duracao, resumo)
        except Exception as exc:  # noqa: BLE001 - o pipeline não pode cair inteiro
            duracao = time.perf_counter() - inicio_ts
            etapa = RastroEtapa(
                agente=self.nome,
                papel=self.papel,
                inicio=inicio_iso,
                duracao_s=duracao,
                sucesso=False,
                resumo="Falha na execução do agente.",
                erro=f"{type(exc).__name__}: {exc}",
            )
            ctx.avisar(f"{self.nome}: {type(exc).__name__}: {exc}")
            self.log.error("✖ %s falhou: %s\n%s", self.nome, exc, traceback.format_exc(limit=3))
        ctx.registrar(etapa)
        return ctx

    # ------------------------------------------------------------------
    def ficha(self) -> dict[str, str]:
        """Descrição do agente, exibida na documentação da interface."""
        return {"agente": self.nome, "papel": self.papel, "descrição": self.descricao}
