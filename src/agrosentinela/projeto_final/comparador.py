"""
Comparador de apólices de D&O.

Princípio herdado do Desafio 5, e aqui ainda mais necessário: **as regras
decidem, o modelo redige**. Toda a comparação abaixo é aritmética simples e
conferível — nenhum escore, nenhuma lacuna e nenhuma diferença sai de um
modelo de linguagem. O LLM entra depois, recebendo este resultado como bloco
de fatos fechado, apenas para escrever a leitura em linguagem natural para
cada persona.

A razão é prática: ninguém decide contratação de cobertura a partir de um
número que não consegue refazer. Se a comparação diz "a apólice B perde 18
pontos em custos de defesa", tem de ser possível apontar qual cláusula, qual
peso e qual nível produziram exatamente esses 18 pontos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable, Sequence

from .clausulas import (
    CLAUSULAS,
    CLAUSULAS_POR_CODIGO,
    GRUPOS_CLAUSULA,
    NIVEIS,
    ROTULO_NIVEL,
    Clausula,
    criticas,
    peso_total,
)


# ==========================================================================
# Apólice
# ==========================================================================

@dataclass
class Apolice:
    """
    Uma apólice reduzida à grade de cláusulas.

    ``avaliacoes`` mapeia ``código da cláusula -> nível`` (ver ``NIVEIS``).
    Cláusula não informada é tratada como ``"ausente"`` — e não como neutra.
    A diferença importa: silêncio contratual costuma ser resolvido contra o
    segurado no sinistro, então tratar o não informado como neutro produziria
    uma comparação otimista e enganosa.
    """

    identificador: str
    seguradora: str
    produto: str = "D&O"
    lmg: float = 0.0
    premio: float = 0.0
    franquia: float = 0.0
    vigencia_inicio: date | None = None
    vigencia_fim: date | None = None
    retroatividade: date | None = None
    avaliacoes: dict[str, str] = field(default_factory=dict)
    observacoes: dict[str, str] = field(default_factory=dict)
    fonte: str = ""
    tomadora: str = ""
    uf: str = ""
    segmento: str = ""
    confianca: float | None = None
    metodo: str = ""
    # Pesos ajustados ao perfil de risco da tomadora (ver perfil_risco.py).
    # None → pesos-base da taxonomia.
    pesos: dict[str, float] | None = None

    def nivel(self, codigo: str) -> str:
        return self.avaliacoes.get(codigo, "ausente")

    def peso(self, clausula: Clausula) -> float:
        if self.pesos and clausula.codigo in self.pesos:
            return float(self.pesos[clausula.codigo])
        return float(clausula.peso)

    def pontos(self, clausula: Clausula) -> float:
        return self.peso(clausula) * NIVEIS.get(self.nivel(clausula.codigo), 0.0)

    def escore(self, apenas_criticas: bool = False) -> float:
        """Escore de 0 a 100, ponderado pelo peso (efetivo) de cada cláusula."""
        fonte = criticas() if apenas_criticas else CLAUSULAS
        total = sum(self.peso(c) for c in fonte)
        if not total:
            return 0.0
        obtidos = sum(self.pontos(c) for c in fonte)
        return round(100.0 * obtidos / total, 1)

    def escore_por_grupo(self) -> dict[str, float]:
        saida: dict[str, float] = {}
        for grupo in GRUPOS_CLAUSULA:
            do_grupo = [c for c in CLAUSULAS if c.grupo == grupo]
            total = sum(self.peso(c) for c in do_grupo)
            if not total:
                continue
            saida[grupo] = round(
                100.0 * sum(self.pontos(c) for c in do_grupo) / total, 1
            )
        return saida

    def custo_por_ponto(self) -> float:
        """
        Prêmio dividido pelo escore.

        Não é uma métrica de "melhor compra" — é uma forma de tornar
        comparável o que a proposta comercial apresenta separado. Duas
        apólices com o mesmo prêmio e escores de 82 e 51 não custam o mesmo.
        """
        escore = self.escore()
        if escore <= 0:
            return 0.0
        return round(self.premio / escore, 2)

    def to_row(self) -> dict[str, Any]:
        return {
            "apólice": self.identificador,
            "seguradora": self.seguradora,
            "LMG": self.lmg,
            "prêmio": self.premio,
            "franquia": self.franquia,
            "escore geral": self.escore(),
            "escore nas críticas": self.escore(apenas_criticas=True),
            "prêmio por ponto": self.custo_por_ponto(),
            "retroatividade": (self.retroatividade.isoformat()
                               if self.retroatividade else "não informada/ilimitada"),
        }


# ==========================================================================
# Resultado
# ==========================================================================

@dataclass
class LacunaCobertura:
    """Uma cláusula ausente ou restrita em uma apólice, com o impacto."""

    apolice: str
    clausula: Clausula
    nivel: str
    pontos_perdidos: float
    melhor_alternativa: str = ""
    nivel_alternativa: str = ""

    @property
    def gravidade(self) -> str:
        if self.clausula.critica and self.nivel in ("ausente", "excluida"):
            return "critica"
        if self.clausula.critica or self.nivel in ("ausente", "excluida"):
            return "alta"
        return "media"

    def to_row(self) -> dict[str, Any]:
        return {
            "apólice": self.apolice,
            "cláusula": self.clausula.nome,
            "código": self.clausula.codigo,
            "grupo": self.clausula.grupo,
            "situação": ROTULO_NIVEL.get(self.nivel, self.nivel),
            "gravidade": self.gravidade,
            "pontos perdidos": round(self.pontos_perdidos, 2),
            "melhor alternativa": (
                f"{self.melhor_alternativa} ({ROTULO_NIVEL.get(self.nivel_alternativa, '')})"
                if self.melhor_alternativa else "nenhuma das comparadas cobre"
            ),
            "por que importa": self.clausula.porque_importa,
        }


@dataclass
class ComparacaoApolices:
    apolices: list[Apolice]
    lacunas: list[LacunaCobertura] = field(default_factory=list)
    gerado_em: str = ""

    @property
    def vencedora_geral(self) -> Apolice | None:
        return max(self.apolices, key=lambda a: a.escore()) if self.apolices else None

    @property
    def vencedora_criticas(self) -> Apolice | None:
        if not self.apolices:
            return None
        return max(self.apolices, key=lambda a: a.escore(apenas_criticas=True))

    @property
    def divergencia_de_leitura(self) -> bool:
        """
        Verdadeiro quando a melhor no escore geral **não** é a melhor nas
        cláusulas críticas.

        É o achado mais útil que esta comparação produz: significa que o
        escore geral está sendo puxado por cláusulas que não decidem sinistro,
        e que a leitura precisa ser feita cláusula a cláusula. O relatório
        destaca este caso em vez de escondê-lo atrás de um ranking.
        """
        a, b = self.vencedora_geral, self.vencedora_criticas
        return bool(a and b and a.identificador != b.identificador)

    def lacunas_criticas(self) -> list[LacunaCobertura]:
        return [l for l in self.lacunas if l.gravidade == "critica"]

    def resumo(self) -> dict[str, Any]:
        geral = self.vencedora_geral
        critica = self.vencedora_criticas
        return {
            "apolices_comparadas": len(self.apolices),
            "clausulas_avaliadas": len(CLAUSULAS),
            "melhor_escore_geral": geral.identificador if geral else "",
            "melhor_nas_clausulas_criticas": critica.identificador if critica else "",
            "leitura_divergente": self.divergencia_de_leitura,
            "lacunas": len(self.lacunas),
            "lacunas_criticas": len(self.lacunas_criticas()),
            "gerado_em": self.gerado_em,
        }

    def bloco_de_fatos(self) -> dict[str, Any]:
        """
        Fatos fechados entregues ao redator.

        Mesmo contrato do Desafio 5: o modelo escreve **a partir daqui** e não
        pode acrescentar número nenhum. Em comparação de apólices isso deixa
        de ser rigor técnico e vira requisito — um limite inventado numa
        recomendação de cobertura é um dano concreto.
        """
        return {
            "apolices": [a.to_row() for a in self.apolices],
            "melhor_geral": (self.vencedora_geral.identificador
                             if self.vencedora_geral else ""),
            "melhor_nas_criticas": (self.vencedora_criticas.identificador
                                    if self.vencedora_criticas else ""),
            "atencao_leitura_divergente": self.divergencia_de_leitura,
            "lacunas_criticas": [l.to_row() for l in self.lacunas_criticas()],
            "escores_por_grupo": {
                a.identificador: a.escore_por_grupo() for a in self.apolices
            },
            "aviso": (
                "Comparação de apoio à decisão. Não constitui parecer jurídico "
                "nem recomendação de contratação; a leitura final das condições "
                "gerais é indispensável."
            ),
        }


# ==========================================================================
# Comparação
# ==========================================================================

def comparar(apolices: Sequence[Apolice],
             pesos: dict[str, float] | None = None) -> ComparacaoApolices:
    """
    Compara apólices cláusula a cláusula e levanta as lacunas.

    Uma lacuna é registrada quando a apólice atende a cláusula **pior do que
    a melhor das comparadas**. Isso é deliberado: o objetivo não é julgar uma
    apólice contra um ideal abstrato, mas mostrar o que se ganha e o que se
    perde ao escolher uma em vez da outra — que é a decisão real.
    """
    from datetime import datetime

    apolices = list(apolices)
    if pesos is not None:
        for a in apolices:
            a.pesos = dict(pesos)
    if len(apolices) < 2:
        return ComparacaoApolices(
            apolices=apolices,
            gerado_em=datetime.now().isoformat(timespec="seconds"),
        )

    lacunas: list[LacunaCobertura] = []
    for clausula in CLAUSULAS:
        pontuacoes = {a.identificador: a.pontos(clausula) for a in apolices}
        melhor_valor = max(pontuacoes.values())
        melhor_id = max(pontuacoes, key=lambda k: pontuacoes[k])
        melhor_ap = next(a for a in apolices if a.identificador == melhor_id)

        for apolice in apolices:
            perdidos = melhor_valor - pontuacoes[apolice.identificador]
            nivel = apolice.nivel(clausula.codigo)
            # Registra também quando ninguém cobre: a lacuna existe para as
            # duas, e escondê-la daria a impressão de que o tema está resolvido.
            todos_descobertos = melhor_valor <= 0 and nivel in ("ausente", "excluida")
            if perdidos <= 0 and not todos_descobertos:
                continue
            lacunas.append(LacunaCobertura(
                apolice=apolice.identificador,
                clausula=clausula,
                nivel=nivel,
                pontos_perdidos=perdidos,
                melhor_alternativa="" if todos_descobertos else melhor_ap.identificador,
                nivel_alternativa="" if todos_descobertos
                else melhor_ap.nivel(clausula.codigo),
            ))

    lacunas.sort(key=lambda l: (
        {"critica": 0, "alta": 1, "media": 2}[l.gravidade], -l.pontos_perdidos
    ))
    return ComparacaoApolices(
        apolices=apolices, lacunas=lacunas,
        gerado_em=datetime.now().isoformat(timespec="seconds"),
    )


def matriz_comparativa(apolices: Sequence[Apolice]) -> list[dict[str, Any]]:
    """Uma linha por cláusula, uma coluna por apólice — a visão de conferência."""
    linhas: list[dict[str, Any]] = []
    for clausula in CLAUSULAS:
        linha: dict[str, Any] = {
            "código": clausula.codigo,
            "grupo": clausula.grupo,
            "cláusula": clausula.nome,
            "peso": clausula.peso,
            "crítica": "sim" if clausula.critica else "—",
        }
        for a in apolices:
            linha[a.identificador] = ROTULO_NIVEL.get(
                a.nivel(clausula.codigo), a.nivel(clausula.codigo)
            )
        linha["o que procurar"] = clausula.pergunta
        linhas.append(linha)
    return linhas


def diferencas_relevantes(comparacao: ComparacaoApolices,
                          minimo_pontos: float = 1.0) -> list[dict[str, Any]]:
    """
    Só as cláusulas em que as apólices **de fato divergem**.

    Numa comparação real, a maioria das cláusulas é idêntica entre
    concorrentes. Mostrar as trinta linhas iguais junto das seis diferentes
    é a maneira mais eficiente de esconder as seis.
    """
    saida: list[dict[str, Any]] = []
    for clausula in CLAUSULAS:
        niveis = {a.identificador: a.nivel(clausula.codigo)
                  for a in comparacao.apolices}
        if len(set(niveis.values())) <= 1:
            continue
        pontos = {a.identificador: a.pontos(clausula) for a in comparacao.apolices}
        amplitude = max(pontos.values()) - min(pontos.values())
        if amplitude < minimo_pontos:
            continue
        saida.append({
            "código": clausula.codigo,
            "cláusula": clausula.nome,
            "crítica": "sim" if clausula.critica else "—",
            "amplitude": round(amplitude, 2),
            **{k: ROTULO_NIVEL.get(v, v) for k, v in niveis.items()},
            "por que importa": clausula.porque_importa,
        })
    saida.sort(key=lambda d: -d["amplitude"])
    return saida


# ==========================================================================
# Apólices de exemplo
# ==========================================================================

def exemplos() -> list[Apolice]:
    """
    Três apólices fictícias, construídas para exercitar o comparador.

    Foram desenhadas com um propósito didático específico: a apólice "Alfa"
    vence no escore geral, mas perde nas cláusulas críticas para a "Beta" —
    exatamente o caso em que um ranking simples levaria à decisão errada, e
    que o comparador precisa expor em vez de suavizar.

    São exemplos declaradamente fictícios. Nenhum dado de seguradora real.
    """
    return [
        Apolice(
            identificador="Alfa", seguradora="Seguradora Fictícia Alfa",
            lmg=20_000_000, premio=185_000, franquia=100_000,
            retroatividade=date(2019, 1, 1), fonte="exemplo didático",
            avaliacoes={
                # Generosa no que é fácil de vender: escopo largo, limite alto,
                # muitas conveniências operacionais.
                "ESC-01": "ampla", "ESC-02": "padrao", "ESC-03": "ampla",
                "ESC-04": "ampla", "ESC-05": "restrita", "ESC-06": "ampla",
                "LIM-01": "ampla", "LIM-02": "padrao", "LIM-03": "ampla",
                "LIM-04": "ampla",
                # ...e apertada exatamente onde sai o dinheiro de um sinistro
                # de D&O: custos de defesa e adiantamento.
                "DEF-01": "restrita", "DEF-02": "restrita", "DEF-03": "ampla",
                "DEF-04": "padrao", "DEF-05": "restrita",
                "TMP-01": "ampla", "TMP-02": "padrao", "TMP-03": "ampla",
                "TMP-04": "ampla",
                "EXC-01": "restrita", "EXC-02": "ampla", "EXC-03": "ampla",
                "EXC-04": "ampla", "EXC-05": "padrao",
                "OPE-01": "ampla", "OPE-02": "ampla", "OPE-03": "ampla",
                "OPE-04": "padrao", "OPE-05": "ampla",
            },
            observacoes={
                "ESC-05": "Exclui expressamente jurisdição dos EUA e Canadá.",
                "DEF-01": "Custos de defesa contidos no LMG.",
            },
        ),
        Apolice(
            identificador="Beta", seguradora="Seguradora Fictícia Beta",
            lmg=15_000_000, premio=210_000, franquia=50_000,
            retroatividade=date(2012, 6, 1), fonte="exemplo didático",
            avaliacoes={
                # O espelho de Alfa: forte em tudo que decide um sinistro,
                # magra nas conveniências que aparecem bem na proposta.
                "ESC-01": "ampla", "ESC-02": "ampla", "ESC-03": "restrita",
                "ESC-04": "restrita", "ESC-05": "ampla", "ESC-06": "restrita",
                "LIM-01": "padrao", "LIM-02": "ampla", "LIM-03": "ausente",
                "LIM-04": "restrita",
                "DEF-01": "ampla", "DEF-02": "ampla", "DEF-03": "restrita",
                "DEF-04": "ampla", "DEF-05": "ampla",
                "TMP-01": "ampla", "TMP-02": "ampla", "TMP-03": "restrita",
                "TMP-04": "restrita",
                "EXC-01": "ampla", "EXC-02": "restrita", "EXC-03": "restrita",
                "EXC-04": "restrita", "EXC-05": "ampla",
                "OPE-01": "restrita", "OPE-02": "restrita", "OPE-03": "restrita",
                "OPE-04": "ampla", "OPE-05": "restrita",
            },
            observacoes={
                "DEF-01": "Custos de defesa adicionais ao LMG.",
                "EXC-01": "Exclusão de dolo só após decisão final irrecorrível.",
            },
        ),
        Apolice(
            identificador="Gama", seguradora="Seguradora Fictícia Gama",
            lmg=10_000_000, premio=96_000, franquia=250_000,
            retroatividade=date(2023, 1, 1), fonte="exemplo didático",
            avaliacoes={
                "ESC-01": "restrita", "ESC-02": "padrao", "ESC-03": "padrao",
                "ESC-04": "ausente", "ESC-05": "restrita", "ESC-06": "restrita",
                "LIM-01": "restrita", "LIM-02": "restrita", "LIM-03": "ausente",
                "LIM-04": "restrita",
                "DEF-01": "restrita", "DEF-02": "ausente", "DEF-03": "restrita",
                "DEF-04": "ausente", "DEF-05": "ausente",
                "TMP-01": "restrita", "TMP-02": "restrita", "TMP-03": "ausente",
                "TMP-04": "ausente",
                "EXC-01": "restrita", "EXC-02": "restrita", "EXC-03": "excluida",
                "EXC-04": "excluida", "EXC-05": "restrita",
                "OPE-01": "padrao", "OPE-02": "padrao", "OPE-03": "padrao",
                "OPE-04": "ausente", "OPE-05": "padrao",
            },
            observacoes={
                "LIM-01": "Prêmio bem menor, porém com LMG e sublimites "
                          "significativamente reduzidos.",
            },
        ),
    ]
