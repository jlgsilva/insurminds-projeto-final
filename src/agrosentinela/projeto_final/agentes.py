"""
Agentes do Projeto Final e o orquestrador.

Dois fluxos, cada um uma cadeia de agentes com responsabilidade única —
reaproveitando a classe-base ``Agente`` do Desafio 5 (rastro cronometrado,
captura de falha por agente, métricas):

**Ingestão** (documento → base estruturada)

    RecepcaoAgent → LeituraOCRAgent → CadastroAgent (LLM) → ClausulasAgent (LLM)
        → ValidacaoAgent → ArmazenamentoAgent

**Comparação** (apólices escolhidas → relatório)

    PerfilRiscoAgent (Sicor) → ComparadorAgent (regras) → RelatorAgent (LLM)

e, à parte, o ``AgenteConsulta`` (LLM com ferramentas) sobre a base.

Princípio de projeto mantido do Desafio 5: **o modelo lê e redige; as regras
decidem**. O LLM extrai e explica — mas escores, lacunas e números finais
vêm de código determinístico e auditável.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import pandas as pd

from ..agents.base import Agente, RastroEtapa
from ..llm.groq_client import LLMIndisponivel
from . import avaliacao as av
from . import extracao as ex
from .clausulas import CLAUSULAS
from .comparador import Apolice, ComparacaoApolices, comparar
from .documentos import DocumentoRecebido, Secao, agrupar_arquivos, ler_documento, segmentar
from .perfil_risco import PerfilRisco, montar_perfil
from .relator import (PUBLICOS_POR_CODIGO, RelatorioComparativo, bloco_de_fatos_completo,
                      gerar_deterministico, gerar_llm)
from .repositorio import Repositorio
from .tipo_documento import classificar as classificar_documento
from .validacao import ResultadoValidacao, validar


# ==========================================================================
# Contexto (o "quadro-negro" compartilhado pelos agentes)
# ==========================================================================

@dataclass
class ItemDocumento:
    ident: str
    arquivos: list[tuple[str, bytes]]
    doc: DocumentoRecebido | None = None
    secoes: list[Secao] = field(default_factory=list)
    cadastro_regex: dict[str, Any] = field(default_factory=dict)
    extracao: ex.ExtracaoApolice = field(default_factory=ex.ExtracaoApolice)
    validacao: ResultadoValidacao | None = None
    avaliacao: dict[str, Any] = field(default_factory=dict)
    ignorado: str = ""
    erro: str = ""
    tipo: Any = None          # tipo_documento.TipoDocumento


@dataclass
class ContextoApolices:
    usar_llm: bool = True
    permitir_ocr: bool = True
    reprocessar: bool = False
    itens: list[ItemDocumento] = field(default_factory=list)
    # comparação
    ids_comparacao: list[str] = field(default_factory=list)
    publico: str = "gestor_riscos"
    ajustar_por_perfil: bool = True
    perfil: PerfilRisco | None = None
    comparacao: ComparacaoApolices | None = None
    relatorio: RelatorioComparativo | None = None
    # observabilidade
    rastro: list[RastroEtapa] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    def registrar(self, etapa: RastroEtapa) -> None:
        self.rastro.append(etapa)

    def avisar(self, msg: str) -> None:
        if msg not in self.avisos:
            self.avisos.append(msg)

    @property
    def ativos(self) -> list[ItemDocumento]:
        return [i for i in self.itens if not i.ignorado and not i.erro]

    def rastro_df(self) -> pd.DataFrame:
        return pd.DataFrame([e.to_dict() for e in self.rastro])

    @property
    def duracao_total_s(self) -> float:
        return round(sum(e.duracao_s for e in self.rastro), 2)


class _AgentePF(Agente):
    """Agente do Projeto Final: acesso ao repositório e ao cliente LLM."""

    def __init__(self, repo: Repositorio, cliente: Any = None, base_sicor: Any = None) -> None:
        super().__init__()
        self.repo = repo
        self.cliente = cliente
        self.base_sicor = base_sicor

    @property
    def llm_ok(self) -> bool:
        return bool(self.cliente is not None and getattr(self.cliente, "disponivel", False))

    def auditar(self, ref: str, evento: str, detalhe: Any = "") -> None:
        try:
            self.repo.auditar(self.nome, ref, evento, detalhe)
        except Exception:  # noqa: BLE001 - auditoria nunca derruba o fluxo
            pass


# ==========================================================================
# Ingestão
# ==========================================================================

class RecepcaoAgent(_AgentePF):
    nome = "RecepcaoAgent"
    papel = "Recebe arquivos, agrupa páginas, valida tipo/tamanho e evita duplicidade"
    descricao = ("Aceita PDF, imagens (JPG/PNG/TIFF — várias fotos = uma apólice) e TXT; "
                 "calcula hash SHA-256 e ignora documento já processado.")

    def _executar(self, ctx: ContextoApolices) -> str:
        import hashlib

        ign = 0
        for it in ctx.itens:
            h = hashlib.sha256(b"".join(c for _, c in it.arquivos)).hexdigest()
            existente = self.repo.existe_hash(h)
            if existente and not ctx.reprocessar:
                it.ignorado = f"já processado como {existente}"
                ign += 1
                self.auditar(it.ident, "ignorado_duplicado", existente)
            else:
                self.auditar(it.ident, "recebido", [n for n, _ in it.arquivos])
        return f"{len(ctx.itens)} documento(s) recebidos; {ign} já existiam na base."

    def metricas(self, ctx: ContextoApolices) -> dict[str, Any]:
        return {"documentos": len(ctx.itens),
                "arquivos": sum(len(i.arquivos) for i in ctx.itens)}


class LeituraOCRAgent(_AgentePF):
    nome = "LeituraOCRAgent"
    papel = "Extrai o texto: camada de texto do PDF ou OCR (Tesseract) por página"
    descricao = "Detecta página digitalizada e aplica OCR em português; segmenta em seções."

    def _executar(self, ctx: ContextoApolices) -> str:
        ocr = fora = 0
        for it in ctx.ativos:
            try:
                it.doc = ler_documento(it.ident, it.arquivos, permitir_ocr=ctx.permitir_ocr)
                it.secoes = segmentar(it.doc.texto)
                it.cadastro_regex = ex.extrair_cadastro_regex(it.doc.texto)
                it.tipo = classificar_documento(it.doc.texto, it.cadastro_regex)
                if it.doc.usou_ocr:
                    ocr += 1
                if it.doc.texto.strip() and not it.tipo.e_do:
                    it.ignorado = (f"fora do escopo: documento identificado como "
                                   f"{it.tipo.ramo_nome} ({it.tipo.tipo_nome.split(' (')[0].lower()}). "
                                   "A grade de comparação é de apólices D&O; o documento não foi "
                                   "gravado na base.")
                    self.auditar(it.ident, "fora_do_escopo", it.tipo.to_dict())
                    fora += 1
                if not it.doc.texto.strip():
                    it.erro = "Nenhum texto extraído (OCR indisponível ou documento vazio)."
                    ctx.avisar(f"{it.ident}: {it.erro}")
                self.auditar(it.ident, "texto_extraido", {
                    "paginas": len(it.doc.paginas), "metodo": it.doc.metodo_resumo,
                    "conf_ocr": it.doc.confianca_ocr_media, "secoes": len(it.secoes),
                    "ramo": it.tipo.ramo, "tipo": it.tipo.tipo})
            except Exception as exc:  # noqa: BLE001
                it.erro = f"{type(exc).__name__}: {exc}"
                ctx.avisar(f"{it.ident}: {it.erro}")
        return (f"{len(ctx.ativos) + fora} documento(s) lidos; {ocr} com OCR"
                + (f"; {fora} fora do escopo D&O (não gravados)." if fora else "."))

    def metricas(self, ctx: ContextoApolices) -> dict[str, Any]:
        return {"paginas": sum(len(i.doc.paginas) for i in ctx.ativos if i.doc),
                "secoes": sum(len(i.secoes) for i in ctx.ativos)}


class CadastroAgent(_AgentePF):
    nome = "CadastroAgent"
    papel = "Estrutura os dados do quadro-resumo (LLM GPT-OSS 20B, com regex de apoio)"
    descricao = ("Lê seguradora, tomadora, vigência, retroatividade, LMG, prêmio e franquia; "
                 "a leitura por expressão regular serve de contingência e de verificação.")

    def _executar(self, ctx: ContextoApolices) -> str:
        n_llm = 0
        for it in ctx.ativos:
            if not it.cadastro_regex:
                it.cadastro_regex = ex.extrair_cadastro_regex(it.doc.texto)
            nome = it.cadastro_regex.get("seguradora")
            if (not nome or len(nome) > 80 or (it.tipo and it.tipo.tipo == "condicoes_gerais")):
                # condições gerais não têm quadro-resumo: o nome mora no
                # cabeçalho/rodapé ("Allianz Seguros S.A. — Página 2 de 75")
                it.cadastro_regex["seguradora"] = ex.seguradora_provavel(
                    it.doc.texto, it.doc.linhas_repetidas) or (nome if nome and len(nome) <= 80 else None)
            it.extracao.tipo_documento = it.tipo.tipo if it.tipo else "apolice"
            if ctx.usar_llm and self.llm_ok:
                try:
                    modelo = self.cliente.settings.modelo_rapido
                    it.extracao.cadastro = ex.extrair_cadastro_llm(self.cliente, it.doc.texto, modelo)
                    it.extracao.metodo_cadastro = "llm"
                    it.extracao.modelo = modelo
                    n_llm += 1
                    continue
                except (LLMIndisponivel, ValueError) as exc:
                    ctx.avisar(f"{it.ident}: cadastro sem LLM ({str(exc)[:120]})")
            it.extracao.cadastro = dict(it.cadastro_regex)
            it.extracao.metodo_cadastro = "deterministico"
        return f"Cadastro estruturado de {len(ctx.ativos)} apólice(s); {n_llm} via LLM."


class ClausulasAgent(_AgentePF):
    nome = "ClausulasAgent"
    papel = "Identifica e classifica as 32 cláusulas da taxonomia (LLM GPT-OSS 120B)"
    descricao = ("Mapeia cada seção para a taxonomia pelo significado, classifica o nível "
                 "e cita a evidência literal. Contingência: dicionário + gatilhos.")

    def _executar(self, ctx: ContextoApolices) -> str:
        n_llm = 0
        for it in ctx.ativos:
            if ctx.usar_llm and self.llm_ok:
                try:
                    modelo = self.cliente.settings.modelo_extracao
                    it.extracao.clausulas = ex.extrair_clausulas_llm(self.cliente, it.secoes, modelo)
                    it.extracao.metodo_clausulas = "llm"
                    it.extracao.modelo = ", ".join(
                        sorted({m for m in (it.extracao.modelo, modelo) if m}))
                    n_llm += 1
                    continue
                except (LLMIndisponivel, ValueError) as exc:
                    ctx.avisar(f"{it.ident}: cláusulas sem LLM ({str(exc)[:120]})")
            it.extracao.clausulas = ex.extrair_clausulas_deterministico(it.secoes)
            it.extracao.metodo_clausulas = "deterministico"
        return f"{len(CLAUSULAS)} cláusulas classificadas em {len(ctx.ativos)} apólice(s); {n_llm} via LLM."


class ValidacaoAgent(_AgentePF):
    nome = "ValidacaoAgent"
    papel = "Confere esquema, evidências, números e coerência; calcula a confiança"
    descricao = ("Anti-alucinação: evidência citada precisa existir no texto; números do "
                 "LLM são conferidos com o quadro-resumo; mede acerto contra o gabarito.")

    def _executar(self, ctx: ContextoApolices) -> str:
        alertas = 0
        for it in ctx.ativos:
            r = validar(it.extracao, it.secoes, it.cadastro_regex, it.extracao.tipo_documento)
            conf_ocr = it.doc.confianca_ocr_media if it.doc else None
            if conf_ocr is not None and conf_ocr < 85:
                r.confianca = max(0.0, r.confianca - (85 - conf_ocr))
                r.alertas.append(f"Confiança média do OCR baixa ({conf_ocr}).")
            it.validacao = r
            alertas += len(r.alertas)
            ident_gab = av.identificador_de(it.ident)
            if ident_gab:
                it.avaliacao = av.avaliar(ident_gab, it.extracao.cadastro,
                                          {k: v.nivel for k, v in it.extracao.clausulas.items()})
            self.auditar(it.ident, "validado", {"confianca": r.confianca,
                                                "alertas": r.alertas[:10],
                                                "avaliacao": {k: it.avaliacao.get(k) for k in (
                                                    "acuracia_campos", "acuracia_clausulas")}})
        return f"{len(ctx.ativos)} apólice(s) validadas; {alertas} alerta(s)."

    def metricas(self, ctx: ContextoApolices) -> dict[str, Any]:
        confs = [i.validacao.confianca for i in ctx.ativos if i.validacao]
        return {"confianca_media": round(sum(confs) / len(confs), 1) if confs else None}


class ArmazenamentoAgent(_AgentePF):
    nome = "ArmazenamentoAgent"
    papel = "Persiste documento, cadastro, cláusulas, seções e auditoria (SQLite)"
    descricao = "Base estruturada consultável pelas telas de comparação e pelo agente de consulta."

    def _executar(self, ctx: ContextoApolices) -> str:
        n = 0
        for it in ctx.ativos:
            self.repo.salvar_documento(it.ident, it.doc)
            self.repo.salvar_extracao(it.ident, it.extracao, it.secoes,
                                      it.validacao.confianca if it.validacao else 0.0,
                                      it.validacao.alertas if it.validacao else [])
            self.auditar(it.ident, "armazenado", {"metodo": it.extracao.metodo_clausulas})
            n += 1
        return f"{n} apólice(s) gravadas. Base: {self.repo.contagem()['apolices']} apólices."


# ==========================================================================
# Comparação
# ==========================================================================

def apolice_do_banco(repo: Repositorio, ident: str) -> Apolice:
    ap = repo.df("SELECT * FROM apolices WHERE id = ?", (ident,))
    if ap.empty:
        raise KeyError(ident)
    r = ap.iloc[0]
    cl = repo.clausulas([ident])

    def _d(v):
        try:
            return date.fromisoformat(str(v)[:10]) if v else None
        except ValueError:
            return None

    return Apolice(
        identificador=ident, seguradora=r["seguradora"] or "?",
        lmg=float(r["lmg"] or 0), premio=float(r["premio"] or 0),
        franquia=float(r["franquia"] or 0), vigencia_inicio=_d(r["vigencia_inicio"]),
        vigencia_fim=_d(r["vigencia_fim"]), retroatividade=_d(r["retroatividade"]),
        avaliacoes=dict(zip(cl["codigo"], cl["nivel"])),
        observacoes=dict(zip(cl["codigo"], cl["evidencia"].fillna(""))),
        fonte=r.get("metodo_clausulas") or "", tomadora=r["tomadora"] or "",
        uf=r["uf"] or "", segmento=r["segmento"] or "",
        confianca=float(r["confianca"]) if r["confianca"] is not None else None,
        metodo=r["metodo_clausulas"] or "",
    )


def tabela_escores(repo: Repositorio) -> pd.DataFrame:
    """Escore de todas as apólices da base (pesos-base), para consultas e rankings."""
    ids = repo.df("SELECT id FROM apolices")["id"].tolist()
    linhas = []
    for i in ids:
        a = apolice_do_banco(repo, i)
        linhas.append({"id": i, "escore": a.escore(), "escore_criticas": a.escore(True),
                       "premio_por_ponto": a.custo_por_ponto()})
    return pd.DataFrame(linhas, columns=["id", "escore", "escore_criticas", "premio_por_ponto"])


class PerfilRiscoAgent(_AgentePF):
    nome = "PerfilRiscoAgent"
    papel = "Contextualiza a tomadora com os microdados do Sicor/Proagro e ajusta pesos"
    descricao = ("Usa crédito rural, acionamento do Proagro e atrasos na UF da tomadora "
                 "(base do Desafio 5) para dizer quais cláusulas pesam mais para ela.")

    def _executar(self, ctx: ContextoApolices) -> str:
        primeira = apolice_do_banco(self.repo, ctx.ids_comparacao[0])
        ctx.perfil = montar_perfil(primeira.tomadora, primeira.uf, primeira.segmento,
                                   self.base_sicor)
        return (f"Tomadora em {primeira.uf or '?'} ({primeira.segmento or 'segmento ?'}): "
                f"{len(ctx.perfil.ajustes)} ajuste(s) de peso.")


class ComparadorAgent(_AgentePF):
    nome = "ComparadorAgent"
    papel = "Compara cláusula a cláusula, calcula escores e levanta lacunas (determinístico)"
    descricao = ("Escore ponderado por criticidade (e pelo perfil da tomadora), escore só "
                 "nas cláusulas críticas, prêmio por ponto e lacunas com melhor alternativa.")

    def _executar(self, ctx: ContextoApolices) -> str:
        apolices = [apolice_do_banco(self.repo, i) for i in ctx.ids_comparacao]
        pesos = ctx.perfil.pesos() if (ctx.perfil and ctx.ajustar_por_perfil) else None
        ctx.comparacao = comparar(apolices, pesos=pesos)
        r = ctx.comparacao.resumo()
        self.auditar(",".join(ctx.ids_comparacao), "comparado", r)
        return (f"Melhor geral: {r['melhor_escore_geral']} · melhor nas críticas: "
                f"{r['melhor_nas_clausulas_criticas']} · {r['lacunas']} lacunas "
                f"({r['lacunas_criticas']} críticas).")


class RelatorAgent(_AgentePF):
    nome = "RelatorAgent"
    papel = "Redige o relatório comparativo para o público escolhido (LLM GPT-OSS 120B)"
    descricao = ("Escreve a partir de um bloco de fatos fechado; verificador confere que "
                 "todo número citado existe nos fatos. Contingência: modelo de texto.")

    def _executar(self, ctx: ContextoApolices) -> str:
        comp = ctx.comparacao
        publico = PUBLICOS_POR_CODIGO.get(ctx.publico) or next(iter(PUBLICOS_POR_CODIGO.values()))
        evidencias = {a.identificador: a.observacoes for a in comp.apolices}
        fatos = bloco_de_fatos_completo(comp, ctx.perfil.to_dict() if ctx.perfil else None,
                                        evidencias)
        rel = None
        if ctx.usar_llm and self.llm_ok:
            try:
                rel = gerar_llm(self.cliente, fatos, publico,
                                self.cliente.settings.modelo_redacao)
            except (LLMIndisponivel, ValueError) as exc:
                ctx.avisar(f"Relatório sem LLM ({str(exc)[:150]})")
        if rel is None:
            rel = gerar_deterministico(comp, fatos, publico)
        ctx.relatorio = rel
        self.repo.salvar_comparacao(ctx.ids_comparacao, comp.resumo(), rel.texto,
                                    publico.codigo, rel.metodo)
        orfaos = f"; {len(rel.numeros_nao_verificados)} número(s) a conferir" \
            if rel.numeros_nao_verificados else ""
        return f"Relatório ({rel.metodo}) para {publico.nome}{orfaos}."


# ==========================================================================
# Orquestrador
# ==========================================================================

class OrquestradorApolices:
    def __init__(self, repo: Repositorio | None = None, cliente: Any = None,
                 base_sicor: Any = None) -> None:
        self.repo = repo or Repositorio()
        self.cliente = cliente
        self.base_sicor = base_sicor
        kw = {"repo": self.repo, "cliente": cliente, "base_sicor": base_sicor}
        self.ingestao = [RecepcaoAgent(**kw), LeituraOCRAgent(**kw), CadastroAgent(**kw),
                         ClausulasAgent(**kw), ValidacaoAgent(**kw), ArmazenamentoAgent(**kw)]
        self.comparacao = [PerfilRiscoAgent(**kw), ComparadorAgent(**kw), RelatorAgent(**kw)]

    def fichas(self) -> list[dict[str, str]]:
        return [a.ficha() for a in self.ingestao + self.comparacao] + [{
            "agente": "ConsultaAgent",
            "papel": "Responde perguntas em linguagem natural sobre a base (LLM + ferramentas)",
            "descrição": "Tool calling: lista, filtra por cláusula, detalha, busca texto, ranking."}]

    def ingerir(self, arquivos: list[tuple[str, bytes]], *, usar_llm: bool = True,
                permitir_ocr: bool = True, reprocessar: bool = False,
                progresso=None) -> ContextoApolices:
        if self.cliente is not None and hasattr(self.cliente, "reiniciar_orcamento"):
            self.cliente.reiniciar_orcamento(max(40, 3 * len(arquivos) + 10))
        ctx = ContextoApolices(usar_llm=usar_llm, permitir_ocr=permitir_ocr,
                               reprocessar=reprocessar)
        for nome, grupo in agrupar_arquivos(arquivos).items():
            ctx.itens.append(ItemDocumento(ident=nome, arquivos=grupo))
        for agente in self.ingestao:
            if progresso:
                progresso(agente)
            agente.executar(ctx)
            if not ctx.ativos:
                break
        return ctx

    def comparar(self, ids: list[str], *, publico: str = "gestor_riscos",
                 usar_llm: bool = True, ajustar_por_perfil: bool = True,
                 progresso=None) -> ContextoApolices:
        if len(ids) < 2:
            raise ValueError("Selecione pelo menos duas apólices para comparar.")
        if self.cliente is not None and hasattr(self.cliente, "reiniciar_orcamento"):
            self.cliente.reiniciar_orcamento()
        ctx = ContextoApolices(usar_llm=usar_llm, ids_comparacao=list(ids), publico=publico,
                               ajustar_por_perfil=ajustar_por_perfil)
        for agente in self.comparacao:
            if progresso:
                progresso(agente)
            agente.executar(ctx)
            if agente.nome == "ComparadorAgent" and ctx.comparacao is None:
                break
        return ctx


def carimbo() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M")
