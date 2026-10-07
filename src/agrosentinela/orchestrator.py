"""
Orquestrador do pipeline multiagente.

    ┌──────────────┐   ┌────────────┐   ┌─────────────┐   ┌─────────────┐
    │ CarteiraAgent│──▶│ ClimaAgent │──▶│ EventoAgent │──▶│ RegrasAgent │
    └──────────────┘   └────────────┘   └─────────────┘   └─────────────┘
        universo           coleta          identificação       decisão
      monitorado          externa          dos eventos       de negócio
                                                                   │
                                    ┌──────────────────┐   ┌───────▼──────┐
                                    │ DespachanteAgent │◀──│ RedatorAgent │
                                    └──────────────────┘   └──────────────┘
                                      simulação de envio      IA Generativa

O encadeamento é explícito e cada etapa é cronometrada e registrada, de
modo que a interface consiga exibir o fluxo completo — requisito do
Desafio 5 ("permitir demonstrar o fluxo completo da solução, desde a
obtenção dos dados até a geração da comunicação").
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Sequence

import pandas as pd

from .agents.base import Agente, Contexto
from .agents.carteira import CarteiraAgent
from .agents.clima import ClimaAgent
from .agents.despachante import DespachanteAgent
from .agents.evento import EventoAgent
from .agents.redator import RedatorAgent
from .agents.regras import RegrasAgent
from .config import get_settings
from .data.loader import BaseDados, carregar_base
from .llm.groq_client import GroqClient
from .outbox.store import Outbox
from .rules.engine import MotorRegras
from .utils.logging_setup import get_logger

log = get_logger(__name__)


@dataclass
class ResultadoPipeline:
    """Saída completa de uma execução, pronta para a interface."""

    execucao_id: str
    contexto: Contexto
    base: BaseDados
    persistido: bool = False
    erro: str | None = None
    _dfs: dict[str, pd.DataFrame] = field(default_factory=dict)

    # -------------------------------------------------------------- views
    @property
    def alertas_df(self) -> pd.DataFrame:
        if "alertas" not in self._dfs:
            self._dfs["alertas"] = pd.DataFrame(
                [a.to_row() for a in self.contexto.alertas]
            )
        return self._dfs["alertas"]

    @property
    def mensagens_df(self) -> pd.DataFrame:
        if "mensagens" not in self._dfs:
            self._dfs["mensagens"] = pd.DataFrame(
                [m.to_row() for m in self.contexto.mensagens]
            )
        return self._dfs["mensagens"]

    @property
    def envios_df(self) -> pd.DataFrame:
        if "envios" not in self._dfs:
            self._dfs["envios"] = pd.DataFrame([e.to_row() for e in self.contexto.envios])
        return self._dfs["envios"]

    @property
    def rastro_df(self) -> pd.DataFrame:
        return self.contexto.rastro_df()

    @property
    def resumo(self) -> dict[str, Any]:
        r = self.contexto.resumo()
        r["execucao_id"] = self.execucao_id
        r["origem_dados"] = self.base.origem if self.base else "—"
        if self.contexto.telemetria_llm is not None:
            r["llm"] = self.contexto.telemetria_llm.resumo()
        return r

    @property
    def sucesso(self) -> bool:
        return self.erro is None and all(e.sucesso for e in self.contexto.rastro)

    def mensagem_por_id(self, msg_id: str):
        return next((m for m in self.contexto.mensagens if m.id == msg_id), None)

    def alerta_por_id(self, alerta_id: str):
        return next((a for a in self.contexto.alertas if a.id == alerta_id), None)


class Orquestrador:
    """Monta e executa a cadeia de agentes."""

    def __init__(
        self,
        *,
        base: BaseDados | None = None,
        motor: MotorRegras | None = None,
        cliente_llm: GroqClient | None = None,
        outbox: Outbox | None = None,
        agentes: Sequence[Agente] | None = None,
    ) -> None:
        self.settings = get_settings()
        self.base = base
        self.motor = motor or MotorRegras()
        self.cliente_llm = cliente_llm or GroqClient()
        self.outbox = outbox or Outbox()
        self.agentes: list[Agente] = list(agentes) if agentes else [
            CarteiraAgent(),
            ClimaAgent(),
            EventoAgent(),
            RegrasAgent(self.motor),
            RedatorAgent(self.cliente_llm, self.motor),
            DespachanteAgent(self.outbox, self.motor),
        ]

    # ------------------------------------------------------------------
    def descrever_pipeline(self) -> list[dict[str, str]]:
        """Ficha de cada agente — alimenta a página de arquitetura."""
        return [
            {"ordem": str(i), **a.ficha()}
            for i, a in enumerate(self.agentes, start=1)
        ]

    # ------------------------------------------------------------------
    def executar(
        self,
        *,
        data_ref: date | None = None,
        horizonte_dias: int = 7,
        filtros: dict[str, Any] | None = None,
        cenario: str | None = None,
        intensidade_cenario: float = 1.0,
        modo_clima: str = "auto",
        usar_llm: bool = True,
        max_mensagens: int = 40,
        canais_ativos: Sequence[str] = ("whatsapp", "sms", "email", "push", "painel"),
        respeitar_supressao: bool = True,
        persistir: bool = True,
    ) -> ResultadoPipeline:
        """Executa o pipeline completo e devolve o resultado consolidado."""
        execucao_id = f"EXE-{uuid.uuid4().hex[:10].upper()}"
        log.info("═══ Execução %s iniciada ═══", execucao_id)

        if self.base is None:
            self.base = carregar_base()

        self.cliente_llm.reiniciar_orcamento()
        self.cliente_llm.telemetria.limpar()

        ctx = Contexto(
            data_ref=data_ref or date.today(),
            horizonte_dias=int(horizonte_dias),
            filtros=dict(filtros or {}),
            cenario=cenario,
            intensidade_cenario=float(intensidade_cenario),
            modo_clima=modo_clima,
            usar_llm=bool(usar_llm),
            max_mensagens=int(max_mensagens),
            canais_ativos=tuple(canais_ativos),
            respeitar_supressao=bool(respeitar_supressao),
            base=self.base,
        )
        if self.base.e_demonstracao:
            ctx.avisar(self.base.aviso_procedencia)
        if cenario:
            ctx.avisar(
                f"Modo cenário ativo ('{cenario}'): as séries meteorológicas foram "
                "geradas para demonstrar a regra correspondente e não representam "
                "a previsão real."
            )

        erro: str | None = None
        for agente in self.agentes:
            ctx = agente.executar(ctx)

        resultado = ResultadoPipeline(
            execucao_id=execucao_id, contexto=ctx, base=self.base, erro=erro
        )

        if persistir:
            try:
                self.outbox.gravar_alertas(execucao_id, ctx.alertas)
                self.outbox.gravar_mensagens(execucao_id, ctx.mensagens)
                self.outbox.gravar_envios(execucao_id, ctx.envios)
                self.outbox.registrar_execucao(
                    execucao_id,
                    data_ref=ctx.data_ref.isoformat(),
                    origem_dados=self.base.origem,
                    cenario=cenario,
                    resumo=ctx.resumo(),
                )
                resultado.persistido = True
            except Exception as exc:  # noqa: BLE001
                log.warning("Falha ao persistir na caixa de saída: %s", exc)
                ctx.avisar(f"Caixa de saída não pôde ser gravada: {exc}")

        log.info(
            "═══ Execução %s concluída em %.2fs — %d alertas, %d mensagens ═══",
            execucao_id, ctx.duracao_total_s, len(ctx.alertas), len(ctx.mensagens),
        )
        return resultado


# ==========================================================================
# Execução por linha de comando
# ==========================================================================

def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover
    """Ponto de entrada CLI: ``python -m agrosentinela.orchestrator``."""
    import argparse
    import json

    from .utils.formato import reais_compacto
    from .utils.logging_setup import configurar_logging

    parser = argparse.ArgumentParser(
        prog="agrosentinela",
        description="Executa o pipeline de comunicação proativa do AgroSentinela.",
    )
    parser.add_argument("--horizonte", type=int, default=7, help="Dias de previsão analisados.")
    parser.add_argument("--cenario", default=None,
                        choices=["seca", "chuva_excessiva", "chuva_intensa", "granizo",
                                 "geada", "onda_calor", "vendaval"],
                        help="Força um cenário climático para demonstração.")
    parser.add_argument("--intensidade", type=float, default=1.0)
    parser.add_argument("--clima", default="auto", choices=["auto", "online", "sintetico"])
    parser.add_argument("--uf", nargs="*", default=None, help="Filtra por UF.")
    parser.add_argument("--cultura", nargs="*", default=None, help="Filtra por cultura.")
    parser.add_argument("--max-mensagens", type=int, default=25)
    parser.add_argument("--sem-llm", action="store_true", help="Desliga a IA Generativa.")
    parser.add_argument("--sem-persistencia", action="store_true")
    parser.add_argument("--ignorar-supressao", action="store_true",
                        help="Ignora a política anti-fadiga (útil para demonstrações repetidas).")
    parser.add_argument("--exportar", default=None, help="Diretório para exportar os resultados.")
    parser.add_argument("--log", default="INFO")
    args = parser.parse_args(argv)

    configurar_logging(args.log)

    filtros: dict[str, Any] = {}
    if args.uf:
        filtros["uf"] = [u.upper() for u in args.uf]
    if args.cultura:
        filtros["cultura"] = [c.upper() for c in args.cultura]

    orq = Orquestrador()
    res = orq.executar(
        horizonte_dias=args.horizonte,
        filtros=filtros,
        cenario=args.cenario,
        intensidade_cenario=args.intensidade,
        modo_clima=args.clima,
        usar_llm=not args.sem_llm,
        max_mensagens=args.max_mensagens,
        respeitar_supressao=not args.ignorar_supressao,
        persistir=not args.sem_persistencia,
    )

    print("\n" + "═" * 78)
    print(f"  AgroSentinela — execução {res.execucao_id}")
    print("═" * 78)
    for etapa in res.contexto.rastro:
        marca = "✔" if etapa.sucesso else "✖"
        print(f"  {marca} {etapa.agente:<18} {etapa.duracao_s:6.2f}s  {etapa.resumo}")
    print("─" * 78)
    r = res.resumo
    print(f"  Operações monitoradas : {r['operações_monitoradas']:,}".replace(",", "."))
    print(f"  Eventos detectados    : {r['eventos_detectados']}")
    print(f"  Alertas gerados       : {r['alertas_gerados']}")
    print(f"  Mensagens geradas     : {r['mensagens_geradas']}")
    print(f"  Envios simulados      : {r['envios_simulados']}")
    if not res.alertas_df.empty:
        print(f"  Exposição sinalizada  : {reais_compacto(res.alertas_df['valor_credito'].sum())}")
    if "llm" in r:
        print(f"  IA Generativa         : {r['llm']['chamadas_api']} chamadas, "
              f"{r['llm']['tokens_total']} tokens, {r['llm']['respostas_do_cache']} do cache")
    for aviso in r.get("avisos", []):
        print(f"  ⚠ {aviso}")
    print("═" * 78 + "\n")

    if args.exportar:
        from pathlib import Path

        destino = Path(args.exportar)
        destino.mkdir(parents=True, exist_ok=True)
        res.alertas_df.to_csv(destino / "alertas.csv", index=False)
        res.mensagens_df.to_csv(destino / "mensagens.csv", index=False)
        res.envios_df.to_csv(destino / "envios.csv", index=False)
        res.rastro_df.to_csv(destino / "rastro_pipeline.csv", index=False)
        (destino / "resumo.json").write_text(
            json.dumps(res.resumo, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        # Mensagens em texto legível
        with (destino / "mensagens.md").open("w", encoding="utf-8") as fh:
            fh.write(f"# Mensagens geradas — execução {res.execucao_id}\n\n")
            for m in res.contexto.mensagens:
                fh.write(f"## {m.id} · {m.persona_nome} · canal {m.canal}\n\n")
                fh.write(f"- **Severidade:** {m.severidade} · **Score:** {m.score:.0f}\n")
                fh.write(f"- **Local:** {m.municipio} {m.uf} · **Evento:** {m.evento}\n")
                fh.write(f"- **Origem do texto:** {m.gerado_por} {m.modelo}\n")
                if m.assunto:
                    fh.write(f"- **Assunto:** {m.assunto}\n")
                fh.write(f"\n```\n{m.texto}\n```\n\n")
        print(f"Resultados exportados para {destino.resolve()}")

    return 0 if res.sucesso else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
