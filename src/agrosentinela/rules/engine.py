"""
Motor de regras declarativo do AgroSentinela.

As regras vivem em ``rules.yaml`` (texto, versionado, revisável por quem
entende do negócio e não necessariamente de Python). Este módulo:

* carrega e valida as regras;
* avalia as expressões da chave ``quando`` de forma **segura** — não usa
  ``eval`` aberto: um mini-interpretador sobre a AST aceita apenas
  comparações, operadores booleanos, aritmética simples e literais;
* calcula o **score de risco** (0–100) de cada acionamento;
* aplica a política de supressão (anti-fadiga de alerta).

Rastreabilidade: todo acionamento carrega o ``regra_id``, a expressão que
disparou e os valores dos indicadores usados — é isso que permite explicar
ao usuário final *por que* ele recebeu a mensagem.
"""

from __future__ import annotations

import ast
import operator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from ..personas import PESO_SEVERIDADE, SEVERIDADES

RULES_PATH = Path(__file__).resolve().parent / "rules.yaml"


# ==========================================================================
# Avaliador seguro de expressões
# ==========================================================================

class ExpressaoInvalida(ValueError):
    """Expressão da regra usa construção não permitida."""


_OPS_BIN = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_OPS_CMP = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}

_OPS_UN = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
    ast.Not: operator.not_,
}

_FUNCOES_PERMITIDAS = {
    "min": min,
    "max": max,
    "abs": abs,
    "round": round,
    "len": len,
    "int": int,
    "float": float,
    "bool": bool,
}


class AvaliadorSeguro(ast.NodeVisitor):
    """Interpreta um subconjunto seguro de expressões Python."""

    def __init__(self, contexto: Mapping[str, Any]) -> None:
        self.contexto = contexto
        self.nomes_usados: set[str] = set()

    # -- entrada -----------------------------------------------------------
    def avaliar(self, expressao: str) -> Any:
        try:
            arvore = ast.parse(expressao, mode="eval")
        except SyntaxError as exc:  # pragma: no cover - erro de autoria
            raise ExpressaoInvalida(f"Sintaxe inválida em {expressao!r}: {exc}") from exc
        return self.visit(arvore.body)

    # -- nós permitidos ----------------------------------------------------
    def visit_Constant(self, node: ast.Constant) -> Any:  # noqa: N802
        return node.value

    def visit_Name(self, node: ast.Name) -> Any:  # noqa: N802
        nome = node.id
        if nome in _FUNCOES_PERMITIDAS:
            return _FUNCOES_PERMITIDAS[nome]
        if nome not in self.contexto:
            # Indicador ausente -> trata como neutro (None) em vez de quebrar
            self.nomes_usados.add(nome)
            return None
        self.nomes_usados.add(nome)
        return self.contexto[nome]

    def visit_BoolOp(self, node: ast.BoolOp) -> Any:  # noqa: N802
        valores = [self.visit(v) for v in node.values]
        if isinstance(node.op, ast.And):
            return all(bool(v) for v in valores)
        return any(bool(v) for v in valores)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:  # noqa: N802
        fn = _OPS_UN.get(type(node.op))
        if fn is None:
            raise ExpressaoInvalida(f"Operador unário não permitido: {node.op!r}")
        return fn(self.visit(node.operand))

    def visit_BinOp(self, node: ast.BinOp) -> Any:  # noqa: N802
        fn = _OPS_BIN.get(type(node.op))
        if fn is None:
            raise ExpressaoInvalida(f"Operador não permitido: {node.op!r}")
        esq, dir_ = self.visit(node.left), self.visit(node.right)
        if esq is None or dir_ is None:
            return None
        return fn(esq, dir_)

    def visit_Compare(self, node: ast.Compare) -> Any:  # noqa: N802
        esquerda = self.visit(node.left)
        for op, comparador in zip(node.ops, node.comparators):
            direita = self.visit(comparador)
            fn = _OPS_CMP.get(type(op))
            if fn is None:
                raise ExpressaoInvalida(f"Comparador não permitido: {op!r}")
            if isinstance(op, (ast.In, ast.NotIn)):
                if direita is None:
                    return False
            elif esquerda is None or direita is None:
                # Indicador indisponível: a condição simplesmente não dispara.
                return False
            if not fn(esquerda, direita):
                return False
            esquerda = direita
        return True

    def visit_IfExp(self, node: ast.IfExp) -> Any:  # noqa: N802
        return self.visit(node.body) if self.visit(node.test) else self.visit(node.orelse)

    def visit_List(self, node: ast.List) -> Any:  # noqa: N802
        return [self.visit(e) for e in node.elts]

    def visit_Tuple(self, node: ast.Tuple) -> Any:  # noqa: N802
        return tuple(self.visit(e) for e in node.elts)

    def visit_Set(self, node: ast.Set) -> Any:  # noqa: N802
        return {self.visit(e) for e in node.elts}

    def visit_Call(self, node: ast.Call) -> Any:  # noqa: N802
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCOES_PERMITIDAS:
            raise ExpressaoInvalida("Somente funções matemáticas simples são permitidas")
        fn = _FUNCOES_PERMITIDAS[node.func.id]
        args = [self.visit(a) for a in node.args]
        if any(a is None for a in args):
            return None
        return fn(*args)

    # -- bloqueio explícito -------------------------------------------------
    def generic_visit(self, node: ast.AST) -> Any:
        raise ExpressaoInvalida(
            f"Construção não permitida na regra: {type(node).__name__}"
        )


def avaliar_expressao(expressao: str, contexto: Mapping[str, Any]) -> bool:
    """Avalia com segurança uma expressão de regra. Erros => ``False``."""
    if not expressao or not str(expressao).strip():
        return False
    try:
        return bool(AvaliadorSeguro(contexto).avaliar(str(expressao)))
    except ExpressaoInvalida:
        raise
    except Exception:
        return False


# ==========================================================================
# Modelo de regra
# ==========================================================================

@dataclass(frozen=True)
class Escalonamento:
    quando: str
    severidade: str


@dataclass(frozen=True)
class Regra:
    id: str
    nome: str
    evento: str
    descricao: str
    quando: str
    severidade_base: str
    escalonamento: tuple[Escalonamento, ...] = ()
    fases_criticas: tuple[str, ...] = ()
    bonus_fase: float = 0.0
    personas: tuple[str, ...] = ()
    janela_acao_h: int = 72
    acao: str = ""
    base_tecnica: str = ""
    cobertura_proagro: bool = False

    @property
    def aplica_a_qualquer_evento(self) -> bool:
        return self.evento in {"*", "", "qualquer"}


@dataclass
class Acionamento:
    """Resultado da avaliação de uma regra sobre uma operação."""

    regra_id: str
    regra_nome: str
    evento: str
    severidade: str
    score: float
    acao: str
    base_tecnica: str
    janela_acao_h: int
    personas: tuple[str, ...]
    cobertura_proagro: bool
    fase_critica: bool
    explicacao: str
    indicadores_usados: dict[str, Any] = field(default_factory=dict)

    @property
    def severidade_peso(self) -> int:
        return PESO_SEVERIDADE.get(self.severidade, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "regra_id": self.regra_id,
            "regra_nome": self.regra_nome,
            "evento": self.evento,
            "severidade": self.severidade,
            "severidade_peso": self.severidade_peso,
            "score": round(self.score, 1),
            "acao": self.acao,
            "base_tecnica": self.base_tecnica,
            "janela_acao_h": self.janela_acao_h,
            "personas": list(self.personas),
            "cobertura_proagro": self.cobertura_proagro,
            "fase_critica": self.fase_critica,
            "explicacao": self.explicacao,
            "indicadores_usados": self.indicadores_usados,
        }


@dataclass(frozen=True)
class PoliticaSupressao:
    janela_repeticao_h: int = 48
    max_msgs_destinatario_dia: int = 3
    severidade_minima_global: str = "atencao"
    consolidar_por_destinatario: bool = True


@dataclass(frozen=True)
class PesosScore:
    peso_severidade: float = 40
    peso_fase: float = 25
    peso_historico: float = 15
    peso_exposicao: float = 12
    peso_cobertura: float = 8
    limiar_notificacao: float = 35


# ==========================================================================
# Motor
# ==========================================================================

class MotorRegras:
    """Carrega ``rules.yaml`` e avalia operações contra as regras."""

    def __init__(self, caminho: Path | str | None = None) -> None:
        self.caminho = Path(caminho) if caminho else RULES_PATH
        bruto = yaml.safe_load(self.caminho.read_text(encoding="utf-8")) or {}
        self.versao: str = str(bruto.get("versao", "0"))
        self.atualizado_em: str = str(bruto.get("atualizado_em", ""))
        self.regras: tuple[Regra, ...] = tuple(
            self._parse_regra(r) for r in bruto.get("regras", [])
        )
        sup = bruto.get("supressao", {}) or {}
        self.supressao = PoliticaSupressao(
            janela_repeticao_h=int(sup.get("janela_repeticao_h", 48)),
            max_msgs_destinatario_dia=int(sup.get("max_msgs_destinatario_dia", 3)),
            severidade_minima_global=str(sup.get("severidade_minima_global", "atencao")),
            consolidar_por_destinatario=bool(sup.get("consolidar_por_destinatario", True)),
        )
        sc = bruto.get("score", {}) or {}
        self.pesos = PesosScore(
            peso_severidade=float(sc.get("peso_severidade", 40)),
            peso_fase=float(sc.get("peso_fase", 25)),
            peso_historico=float(sc.get("peso_historico", 15)),
            peso_exposicao=float(sc.get("peso_exposicao", 12)),
            peso_cobertura=float(sc.get("peso_cobertura", 8)),
            limiar_notificacao=float(sc.get("limiar_notificacao", 35)),
        )
        self._validar()

    # ---------------------------------------------------------------- setup
    @staticmethod
    def _parse_regra(d: Mapping[str, Any]) -> Regra:
        esc = tuple(
            Escalonamento(quando=str(e.get("quando", "")), severidade=str(e.get("severidade", "atencao")))
            for e in (d.get("escalonamento") or [])
        )
        return Regra(
            id=str(d["id"]),
            nome=str(d.get("nome", d["id"])),
            evento=str(d.get("evento", "*")),
            descricao=" ".join(str(d.get("descricao", "")).split()),
            quando=str(d.get("quando", "")),
            severidade_base=str(d.get("severidade_base", "atencao")),
            escalonamento=esc,
            fases_criticas=tuple(d.get("fases_criticas") or []),
            bonus_fase=float(d.get("bonus_fase", 0) or 0),
            personas=tuple(d.get("personas") or []),
            janela_acao_h=int(d.get("janela_acao_h", 72)),
            acao=" ".join(str(d.get("acao", "")).split()),
            base_tecnica=" ".join(str(d.get("base_tecnica", "")).split()),
            cobertura_proagro=bool(d.get("cobertura_proagro", False)),
        )

    def _validar(self) -> None:
        if not self.regras:
            raise ValueError("Nenhuma regra carregada de rules.yaml")
        vistos: set[str] = set()
        for r in self.regras:
            if r.id in vistos:
                raise ValueError(f"ID de regra duplicado: {r.id}")
            vistos.add(r.id)
            if r.severidade_base not in SEVERIDADES:
                raise ValueError(f"Severidade inválida em {r.id}: {r.severidade_base}")
            for e in r.escalonamento:
                if e.severidade not in SEVERIDADES:
                    raise ValueError(f"Severidade inválida em {r.id}: {e.severidade}")
            # Valida sintaxe das expressões já no carregamento (falha rápido)
            AvaliadorSeguro({}).avaliar(r.quando) if r.quando else None
            for e in r.escalonamento:
                AvaliadorSeguro({}).avaliar(e.quando) if e.quando else None

    # ------------------------------------------------------------ avaliação
    def avaliar(
        self,
        contexto: Mapping[str, Any],
        *,
        regras: Iterable[Regra] | None = None,
    ) -> list[Acionamento]:
        """
        Avalia todas as regras contra um contexto (operação x dia) e devolve
        os acionamentos ordenados por score decrescente.

        O contexto deve reunir indicadores meteorológicos + atributos da
        operação. Chaves ausentes não quebram a avaliação.
        """
        ctx = dict(contexto)
        acionamentos: list[Acionamento] = []

        # Primeira passada: regras vinculadas a um evento específico.
        especificas = [r for r in (regras or self.regras) if not r.aplica_a_qualquer_evento]
        genericas = [r for r in (regras or self.regras) if r.aplica_a_qualquer_evento]

        for regra in especificas:
            ac = self._avaliar_regra(regra, ctx)
            if ac:
                acionamentos.append(ac)

        # As regras genéricas ("*") dependem da severidade já apurada.
        if acionamentos:
            pico = max(a.severidade_peso for a in acionamentos)
            evento_pico = max(acionamentos, key=lambda a: (a.severidade_peso, a.score)).evento
        else:
            pico, evento_pico = 0, "nenhum"
        ctx["severidade_peso"] = pico
        ctx["evento_predominante"] = evento_pico

        for regra in genericas:
            ac = self._avaliar_regra(regra, ctx, evento_fallback=evento_pico)
            if ac:
                acionamentos.append(ac)

        acionamentos.sort(key=lambda a: (-a.severidade_peso, -a.score))
        return acionamentos

    def _avaliar_regra(
        self,
        regra: Regra,
        ctx: Mapping[str, Any],
        *,
        evento_fallback: str | None = None,
    ) -> Acionamento | None:
        if not avaliar_expressao(regra.quando, ctx):
            return None

        severidade = regra.severidade_base
        expressao_disparo = regra.quando
        for esc in regra.escalonamento:
            if avaliar_expressao(esc.quando, ctx):
                if PESO_SEVERIDADE.get(esc.severidade, 0) > PESO_SEVERIDADE.get(severidade, 0):
                    severidade = esc.severidade
                    expressao_disparo = esc.quando

        fase = str(ctx.get("fase", ""))
        fase_critica = fase in regra.fases_criticas

        avaliador = AvaliadorSeguro(ctx)
        try:
            avaliador.avaliar(expressao_disparo)
        except ExpressaoInvalida:
            pass
        usados = {
            n: ctx.get(n)
            for n in sorted(avaliador.nomes_usados)
            if n in ctx and not isinstance(ctx.get(n), (dict, list))
        }

        score = self._score(regra, ctx, severidade, fase_critica)
        evento = regra.evento if not regra.aplica_a_qualquer_evento else (evento_fallback or "multiplo")

        explicacao = self._explicar(regra, severidade, usados, fase, fase_critica)

        return Acionamento(
            regra_id=regra.id,
            regra_nome=regra.nome,
            evento=evento,
            severidade=severidade,
            score=score,
            acao=regra.acao,
            base_tecnica=regra.base_tecnica,
            janela_acao_h=regra.janela_acao_h,
            personas=regra.personas,
            cobertura_proagro=regra.cobertura_proagro,
            fase_critica=fase_critica,
            explicacao=explicacao,
            indicadores_usados=usados,
        )

    # ---------------------------------------------------------------- score
    def _score(
        self,
        regra: Regra,
        ctx: Mapping[str, Any],
        severidade: str,
        fase_critica: bool,
    ) -> float:
        """
        Score de risco 0–100.

        É uma **soma ponderada normalizada**: cada componente contribui com
        no máximo o seu peso, e o total é reescalado pelo máximo teórico da
        própria regra (que varia por causa do ``bonus_fase``). Assim o score
        é comparável entre regras diferentes e não satura em 100.
        """
        import math

        p = self.pesos

        # 1) severidade meteorológica (0..1)
        c_sev = PESO_SEVERIDADE.get(severidade, 1) / 4.0

        # 2) sensibilidade da fase fenológica (0..1); 0.5–2.3 é a faixa útil
        sens = float(ctx.get("sensibilidade_fase", 1.0) or 1.0)
        c_fase = min(max((sens - 0.5) / 1.8, 0.0), 1.0)

        # 3) histórico de acionamento do Proagro para o evento (0..1)
        hist = float(ctx.get("freq_evento_municipio", 0.0) or 0.0)
        c_hist = min(max(hist / 0.5, 0.0), 1.0)

        # 4) exposição financeira em escala log: 10 mil ~ 0 | 500 mil ~ 0,63 | 5 mi ~ 1
        valor = float(ctx.get("valor_credito", 0.0) or 0.0)
        c_exp = min(max((math.log10(valor) - 4.0) / 2.7, 0.0), 1.0) if valor > 0 else 0.0

        # 5) ausência de cobertura de risco (0 ou 1)
        c_cob = 0.0 if bool(ctx.get("tem_cobertura", True)) else 1.0

        bruto = (
            p.peso_severidade * c_sev
            + p.peso_fase * c_fase
            + p.peso_historico * c_hist
            + p.peso_exposicao * c_exp
            + p.peso_cobertura * c_cob
            + (regra.bonus_fase if fase_critica else 0.0)
        )
        maximo = (
            p.peso_severidade + p.peso_fase + p.peso_historico
            + p.peso_exposicao + p.peso_cobertura + regra.bonus_fase
        )
        return float(min(max(100.0 * bruto / max(maximo, 1e-9), 0.0), 100.0))

    # ----------------------------------------------------------- explicação
    @staticmethod
    def _explicar(
        regra: Regra,
        severidade: str,
        usados: Mapping[str, Any],
        fase: str,
        fase_critica: bool,
    ) -> str:
        partes = []
        for nome, valor in usados.items():
            if isinstance(valor, float):
                partes.append(f"{nome}={valor:.1f}")
            elif isinstance(valor, bool):
                partes.append(f"{nome}={'sim' if valor else 'não'}")
            else:
                partes.append(f"{nome}={valor}")
        base = f"Regra {regra.id} ({regra.nome}) — severidade {severidade}."
        if partes:
            base += " Indicadores: " + ", ".join(partes) + "."
        if fase:
            base += f" Fase fenológica: {fase}"
            base += " (crítica para esta regra)." if fase_critica else "."
        return base

    # ------------------------------------------------------------ supressão
    def deve_suprimir(
        self,
        *,
        chave: str,
        severidade: str,
        historico: Mapping[str, datetime],
        agora: datetime | None = None,
        enviados_hoje: int = 0,
    ) -> tuple[bool, str]:
        """
        Aplica a política anti-fadiga.

        ``chave`` identifica (destinatário, regra, severidade).
        ``historico`` mapeia chave -> datetime do último envio.
        """
        agora = agora or datetime.now()
        if PESO_SEVERIDADE.get(severidade, 0) < PESO_SEVERIDADE.get(
            self.supressao.severidade_minima_global, 0
        ):
            return True, "Severidade abaixo do mínimo global."
        ultimo = historico.get(chave)
        if ultimo and agora - ultimo < timedelta(hours=self.supressao.janela_repeticao_h):
            horas = self.supressao.janela_repeticao_h
            return True, f"Mensagem equivalente já enviada nas últimas {horas}h."
        if enviados_hoje >= self.supressao.max_msgs_destinatario_dia:
            return True, (
                f"Limite diário de {self.supressao.max_msgs_destinatario_dia} "
                "mensagens por destinatário atingido."
            )
        return False, ""

    # ------------------------------------------------------------- utilidades
    def resumo(self) -> list[dict[str, Any]]:
        """Tabela das regras, usada na página de documentação da UI."""
        return [
            {
                "id": r.id,
                "nome": r.nome,
                "evento": r.evento,
                "condição": r.quando,
                "severidade_base": r.severidade_base,
                "escalonamentos": len(r.escalonamento),
                "fases_críticas": ", ".join(r.fases_criticas) or "—",
                "personas": ", ".join(r.personas),
                "janela_ação_h": r.janela_acao_h,
                "coberto_proagro": "sim" if r.cobertura_proagro else "não",
                "descrição": r.descricao,
                "ação": r.acao,
                "base_técnica": r.base_tecnica,
            }
            for r in self.regras
        ]
