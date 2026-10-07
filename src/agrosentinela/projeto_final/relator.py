"""
Agente relator — o relatório comparativo em linguagem natural.

Mesmo contrato do RedatorAgent do Desafio 5: **as regras decidem, o modelo
redige**. O relator recebe um *bloco de fatos fechado* (escores, lacunas,
diferenças, evidências literais, perfil de risco da tomadora) e escreve a
leitura para o público escolhido. Depois, um verificador confere que **todo
número citado no texto existe no bloco de fatos**; números órfãos são
listados como alerta no próprio relatório.

Sem chave da Groq, um relatório determinístico (modelo de texto) é gerado a
partir dos mesmos fatos — a demonstração nunca fica sem resultado.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .clausulas import CLAUSULAS_POR_CODIGO, ROTULO_NIVEL
from .comparador import ComparacaoApolices, diferencas_relevantes


@dataclass(frozen=True)
class PublicoRelatorio:
    codigo: str
    nome: str
    foco: str


PUBLICOS: tuple[PublicoRelatorio, ...] = (
    PublicoRelatorio("gestor_riscos", "Gestor(a) de riscos / seguros da tomadora",
                     "qual apólice protege melhor os administradores pelo preço, o que "
                     "negociar com o corretor antes de fechar"),
    PublicoRelatorio("conselho", "Conselho de administração",
                     "risco pessoal dos conselheiros e diretores, em linguagem executiva, "
                     "sem jargão, com no máximo 5 pontos de decisão"),
    PublicoRelatorio("corretor", "Corretor(a) de seguros",
                     "argumentos técnicos para negociar cláusula a cláusula com cada "
                     "seguradora, pedidos de endosso concretos"),
    PublicoRelatorio("juridico", "Departamento jurídico",
                     "redação das cláusulas críticas, base legal, pontos de litígio "
                     "provável na regulação do sinistro"),
    PublicoRelatorio("subscritor", "Subscritor(a) da seguradora",
                     "posição competitiva da proposta frente às concorrentes e onde "
                     "ajustar wording ou preço"),
)
PUBLICOS_POR_CODIGO = {p.codigo: p for p in PUBLICOS}

SISTEMA_RELATOR = """Você é um consultor sênior de seguros D&O no Brasil,
especializado em empresas do agronegócio. Escreva em português do Brasil um
RELATÓRIO COMPARATIVO de apólices, em Markdown, para o público indicado.

REGRAS INVIOLÁVEIS
1. Use EXCLUSIVAMENTE os fatos do bloco JSON. Não acrescente nenhum número,
   percentual, valor, data, prazo ou nome que não esteja nele.
2. Ao citar uma cláusula, use o nome dela e, quando houver, a evidência
   literal entre aspas.
3. Se a melhor no escore geral não for a melhor nas cláusulas críticas,
   isso deve ser o PRIMEIRO ponto do relatório.
4. Considere o perfil de risco da tomadora (ajustes de peso e indicadores do
   crédito rural na UF) para explicar POR QUE certas cláusulas pesam mais.
5. Não faça recomendação definitiva de contratação: apresente a leitura e os
   pontos a negociar. Termine com o aviso do bloco de fatos.

ESTRUTURA
## Leitura em uma frase
## Principais diferenças (3 a 6 itens)
## Lacunas críticas e o que negociar
## Custo × proteção
## Contexto da tomadora (crédito rural e Proagro)
## Aviso"""


@dataclass
class RelatorioComparativo:
    texto: str
    metodo: str                      # "llm" | "deterministico"
    publico: str
    modelo: str = ""
    numeros_nao_verificados: list[str] = field(default_factory=list)
    erro: str = ""


def bloco_de_fatos_completo(comp: ComparacaoApolices, perfil: dict[str, Any] | None,
                            evidencias: dict[str, dict[str, str]] | None = None) -> dict[str, Any]:
    fatos = comp.bloco_de_fatos()
    fatos["diferencas_relevantes"] = [
        {k: v for k, v in d.items() if k != "por que importa"}
        for d in diferencas_relevantes(comp)[:12]
    ]
    for a in fatos["apolices"]:
        ap = next(x for x in comp.apolices if x.identificador == a["apólice"])
        a["taxa_premio_sobre_lmg_pct"] = round(100 * ap.premio / ap.lmg, 3) if ap.lmg else None
        a["tomadora"] = ap.tomadora
    if evidencias:
        # Só as evidências das cláusulas que diferem — o modelo não precisa do resto
        cods = {d["código"] for d in fatos["diferencas_relevantes"]}
        fatos["evidencias_literais"] = {
            ap: {c: texto[:220] for c, texto in ev.items() if c in cods and texto}
            for ap, ev in evidencias.items()
        }
    if perfil:
        fatos["perfil_tomadora"] = perfil
    return fatos


# ---------------------------------------------------------------- verificação
_NUM = re.compile(r"\d[\d.,]*\d|\d")


def _interpretacoes(token: str) -> set[float]:
    """'20.000.000' / '81,5' / '20000000.0' → valores possíveis (pt-BR e en)."""
    t = token.strip(".,")
    vals: set[float] = set()
    for conv in (lambda x: x.replace(".", "").replace(",", "."),   # pt-BR
                 lambda x: x.replace(",", "")):                     # en
        try:
            vals.add(float(conv(t)))
        except ValueError:
            pass
    return vals


def _valores_conhecidos(fatos: dict[str, Any]) -> set[float]:
    bruto = json.dumps(fatos, ensure_ascii=False, default=str)
    base: set[float] = set()
    for tok in _NUM.findall(bruto):
        base |= _interpretacoes(tok)
    out = set(base)
    for v in base:   # "R$ 20 milhões", "R$ 150 mil", percentuais arredondados
        out |= {v / 1e6, v / 1e3, round(v, 1), round(v, 0), round(v / 1e6, 1)}
    return out


def numeros_orfaos(texto: str, fatos: dict[str, Any]) -> list[str]:
    """Números do texto que não correspondem a nenhum valor do bloco de fatos."""
    conhecidos = _valores_conhecidos(fatos)
    orfaos: list[str] = []
    for tok in _NUM.findall(texto):
        if len(re.sub(r"\D", "", tok)) <= 1:   # "3 itens", "Side A 1"
            continue
        ok = any(abs(v - k) <= max(0.051, 0.005 * abs(k))
                 for v in _interpretacoes(tok) for k in conhecidos)
        if not ok and tok not in orfaos:
            orfaos.append(tok)
    return orfaos


# ---------------------------------------------------------------- geração
def gerar_llm(cliente, fatos: dict[str, Any], publico: PublicoRelatorio,
              modelo: str | None = None) -> RelatorioComparativo:
    usuario = (f"PÚBLICO: {publico.nome}\nFOCO: {publico.foco}\n\n"
               "BLOCO DE FATOS (JSON):\n" + json.dumps(fatos, ensure_ascii=False, default=str))
    texto = cliente.texto(sistema=SISTEMA_RELATOR, usuario=usuario, modelo=modelo,
                          temperatura=0.3, max_tokens=4000, tarefa="pf_relatorio")
    if not texto.strip():
        raise ValueError("Modelo devolveu relatório vazio.")
    orfaos = numeros_orfaos(texto, fatos)
    if orfaos:
        texto += ("\n\n> ⚠️ **Verificação automática:** os números a seguir não foram "
                  "encontrados no bloco de fatos e devem ser conferidos: "
                  + ", ".join(orfaos[:15]))
    return RelatorioComparativo(texto=texto, metodo="llm", publico=publico.codigo,
                                modelo=modelo or "", numeros_nao_verificados=orfaos)


def _brl(v: float) -> str:
    return "R$ " + f"{v:,.0f}".replace(",", ".")


def gerar_deterministico(comp: ComparacaoApolices, fatos: dict[str, Any],
                         publico: PublicoRelatorio) -> RelatorioComparativo:
    g, c = comp.vencedora_geral, comp.vencedora_criticas
    linhas = [f"*Relatório gerado por modelo de texto (sem IA) para: {publico.nome}.*", ""]
    linhas.append("## Leitura em uma frase")
    if comp.divergencia_de_leitura:
        linhas.append(f"**{g.identificador}** lidera no escore geral ({g.escore()}), mas "
                      f"**{c.identificador}** é a mais forte nas cláusulas críticas "
                      f"({c.escore(True)}) — o ranking simples levaria à escolha errada.")
    else:
        linhas.append(f"**{g.identificador}** lidera tanto no escore geral ({g.escore()}) "
                      f"quanto nas cláusulas críticas ({g.escore(True)}).")
    linhas += ["", "## Principais diferenças"]
    for d in fatos.get("diferencas_relevantes", [])[:6]:
        niveis = "; ".join(f"{a.identificador}: {d.get(a.identificador, '?')}"
                           for a in comp.apolices)
        linhas.append(f"- **{d['cláusula']}** ({d['código']}) — {niveis}")
    linhas += ["", "## Lacunas críticas e o que negociar"]
    criticas = comp.lacunas_criticas()
    if not criticas:
        linhas.append("- Nenhuma lacuna crítica (cláusula crítica ausente ou excluída).")
    for l in criticas[:8]:
        alt = (f"; {l.melhor_alternativa} oferece «{ROTULO_NIVEL.get(l.nivel_alternativa)}»"
               if l.melhor_alternativa else "; nenhuma das comparadas cobre")
        linhas.append(f"- **{l.apolice}** — {l.clausula.nome}: "
                      f"{ROTULO_NIVEL.get(l.nivel)}{alt}. Negociar endosso.")
    linhas += ["", "## Custo × proteção", "| Apólice | LMG | Prêmio | Escore | Prêmio por ponto |",
               "|---|---|---|---|---|"]
    for a in comp.apolices:
        linhas.append(f"| {a.identificador} | {_brl(a.lmg)} | {_brl(a.premio)} | "
                      f"{a.escore()} | {_brl(a.custo_por_ponto())} |")
    perfil = fatos.get("perfil_tomadora")
    if perfil:
        linhas += ["", "## Contexto da tomadora (crédito rural e Proagro)"]
        for aj in perfil.get("ajustes", []):
            nome = CLAUSULAS_POR_CODIGO[aj["codigo"]].nome
            linhas.append(f"- Peso de **{nome}** ×{aj['fator']}: {aj['motivo']}")
    linhas += ["", "## Aviso", fatos["aviso"]]
    return RelatorioComparativo(texto="\n".join(linhas), metodo="deterministico",
                                publico=publico.codigo)
