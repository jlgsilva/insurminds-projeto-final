"""
Agente de consulta — perguntas em linguagem natural sobre a base de apólices.

Arquitetura de *tool calling* (a mesma do Copiloto do Desafio 5): o LLM não
recebe o banco inteiro; recebe **ferramentas** e decide quais chamar, com
quais filtros. Cada ferramenta é uma consulta SQL/pandas determinística sobre
a base estruturada. A resposta final do modelo só pode usar o que as
ferramentas devolveram — e as tabelas de apoio são mostradas ao usuário.

Exemplos de perguntas:
* "Quais apólices pagam custos de defesa fora do LMG e têm LMG ≥ R$ 20 mi?"
* "Qual seguradora tem a melhor cobertura para crédito rural (AGR-01)?"
* "Mostre o texto da cláusula de retroatividade da AP12."
* "Entre as cotações da Coopergrãos, qual tem o menor prêmio por ponto?"
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from ..llm.groq_client import LLMIndisponivel
from ..utils.logging_setup import get_logger
from .clausulas import CLAUSULAS, CLAUSULAS_POR_CODIGO, NIVEIS, ROTULO_NIVEL
from .documentos import normalizar
from .repositorio import Repositorio

log = get_logger(__name__)
MAX_ITERACOES = 5
MAX_LINHAS = 30

FERRAMENTAS = [
    {"type": "function", "function": {
        "name": "listar_apolices",
        "description": "Lista apólices com filtros opcionais e escore de proteção (0-100).",
        "parameters": {"type": "object", "properties": {
            "seguradora": {"type": "string", "description": "parte do nome da seguradora"},
            "tomadora": {"type": "string", "description": "parte do nome da tomadora"},
            "uf": {"type": "string", "description": "sigla da UF da tomadora"},
            "regiao": {"type": "string", "enum": ["Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul"]},
            "amazonia_legal": {"type": "boolean", "description": "só tomadoras na Amazônia Legal"},
            "segmento": {"type": "string", "description": "parte do segmento, ex. 'cooperativa'"},
            "lmg_min": {"type": "number"}, "lmg_max": {"type": "number"},
            "premio_max": {"type": "number"},
            "ordenar_por": {"type": "string", "enum": [
                "escore", "premio", "lmg", "premio_por_ponto", "escore_criticas"]},
        }}}},
    {"type": "function", "function": {
        "name": "apolices_por_clausula",
        "description": "Filtra apólices pelo nível de uma cláusula da taxonomia "
                       "(ex.: DEF-01 custos de defesa, AGR-01 crédito rural).",
        "parameters": {"type": "object", "properties": {
            "codigo": {"type": "string", "description": "código da cláusula, ex. DEF-01"},
            "niveis": {"type": "array", "items": {"type": "string", "enum": list(NIVEIS)},
                       "description": "níveis aceitos"},
        }, "required": ["codigo"]}}},
    {"type": "function", "function": {
        "name": "detalhar_apolice",
        "description": "Dados cadastrais e todas as cláusulas (nível + evidência) de uma apólice.",
        "parameters": {"type": "object", "properties": {
            "apolice_id": {"type": "string", "description": "identificador, ex. AP12-ATL-T04"},
        }, "required": ["apolice_id"]}}},
    {"type": "function", "function": {
        "name": "buscar_texto",
        "description": "Busca um termo no texto integral das apólices (seções).",
        "parameters": {"type": "object", "properties": {
            "termo": {"type": "string"}, "apolice_id": {"type": "string"},
        }, "required": ["termo"]}}},
    {"type": "function", "function": {
        "name": "ranking_seguradoras",
        "description": "Média de escore por seguradora, opcionalmente só numa cláusula.",
        "parameters": {"type": "object", "properties": {
            "codigo": {"type": "string", "description": "código de cláusula (opcional)"},
        }}}},
    {"type": "function", "function": {
        "name": "taxonomia",
        "description": "Lista as cláusulas da taxonomia (código, nome, grupo, peso, crítica).",
        "parameters": {"type": "object", "properties": {}}}},
]

SISTEMA = f"""Você é o Agente de Consulta de uma plataforma de análise de
apólices de seguro D&O de empresas do agronegócio. Responda em português do
Brasil, de forma objetiva, usando SOMENTE os dados devolvidos pelas
ferramentas. Sempre que citar uma apólice, use o identificador (ex.: AP12-ATL-T04).
Se as ferramentas não trouxerem o dado, diga que não encontrou. Os documentos
são SIMULADOS (seguradoras e tomadoras fictícias) — mencione isso se o usuário
perguntar sobre empresas reais.
Níveis de cláusula: {', '.join(f'{k}={v}' for k, v in ROTULO_NIVEL.items())}.
Códigos: {', '.join(f'{c.codigo} ({c.nome})' for c in CLAUSULAS)}."""


@dataclass
class ChamadaFerramenta:
    nome: str
    argumentos: dict[str, Any]
    resultado: Any = None
    erro: str | None = None


@dataclass
class RespostaConsulta:
    texto: str
    ferramentas: list[ChamadaFerramenta] = field(default_factory=list)
    modo: str = "llm"
    modelo: str = ""
    erro: str | None = None

    @property
    def tabelas(self) -> list[tuple[str, pd.DataFrame]]:
        return [(f.nome, f.resultado) for f in self.ferramentas
                if isinstance(f.resultado, pd.DataFrame) and not f.resultado.empty]


class AgenteConsulta:
    nome = "ConsultaAgent"

    def __init__(self, repo: Repositorio, cliente: Any, escores: pd.DataFrame) -> None:
        self.repo = repo
        self.cliente = cliente
        self.escores = escores   # id, escore, escore_criticas, premio_por_ponto

    # ------------------------------------------------------------ ferramentas
    def _base(self) -> pd.DataFrame:
        ap = self.repo.apolices()
        if ap.empty:
            return ap
        cols = ["id", "seguradora", "tomadora", "segmento", "uf", "lmg", "premio",
                "franquia", "retroatividade", "metodo_clausulas", "confianca"]
        ap = ap[cols].copy()
        from .simulador import REGIAO, UF_AMAZONIA_LEGAL

        ap["regiao"] = ap["uf"].map(REGIAO)
        ap["amazonia_legal"] = ap["uf"].isin(UF_AMAZONIA_LEGAL)
        return ap.merge(self.escores, on="id", how="left")

    def listar_apolices(self, seguradora: str = "", tomadora: str = "", uf: str = "",
                        segmento: str = "", regiao: str = "", amazonia_legal: bool | None = None,
                        lmg_min: float | None = None,
                        lmg_max: float | None = None, premio_max: float | None = None,
                        ordenar_por: str = "escore") -> pd.DataFrame:
        df = self._base()
        for col, v in (("seguradora", seguradora), ("tomadora", tomadora),
                       ("segmento", segmento)):
            if v:
                df = df[df[col].fillna("").map(normalizar).str.contains(normalizar(v), regex=False)]
        if uf:
            df = df[df["uf"].fillna("").str.upper() == uf.upper()]
        if regiao:
            df = df[df["regiao"] == regiao]
        if amazonia_legal is not None:
            df = df[df["amazonia_legal"] == bool(amazonia_legal)]
        if lmg_min is not None:
            df = df[df["lmg"] >= float(lmg_min)]
        if lmg_max is not None:
            df = df[df["lmg"] <= float(lmg_max)]
        if premio_max is not None:
            df = df[df["premio"] <= float(premio_max)]
        if ordenar_por in df.columns:
            df = df.sort_values(ordenar_por, ascending=ordenar_por in ("premio", "premio_por_ponto"))
        return df.reset_index(drop=True)

    def apolices_por_clausula(self, codigo: str, niveis: list[str] | None = None) -> pd.DataFrame:
        codigo = codigo.upper().strip()
        if codigo not in CLAUSULAS_POR_CODIGO:
            raise ValueError(f"Código desconhecido: {codigo}")
        cl = self.repo.clausulas()
        cl = cl[cl["codigo"] == codigo]
        if niveis:
            cl = cl[cl["nivel"].isin(niveis)]
        base = self._base()[["id", "seguradora", "tomadora", "uf", "regiao", "lmg", "premio", "escore"]]
        out = cl[["apolice_id", "nivel", "evidencia"]].merge(
            base, left_on="apolice_id", right_on="id").drop(columns=["id"])
        out["nivel"] = out["nivel"].map(lambda n: ROTULO_NIVEL.get(n, n))
        out["evidencia"] = out["evidencia"].fillna("").str.slice(0, 160)
        return out.sort_values("escore", ascending=False).reset_index(drop=True)

    def detalhar_apolice(self, apolice_id: str) -> dict[str, Any]:
        ap = self._base()
        alvo = ap[ap["id"].str.upper().str.startswith(apolice_id.upper().strip())]
        if alvo.empty:
            raise ValueError(f"Apólice {apolice_id} não encontrada.")
        linha = alvo.iloc[0].to_dict()
        cl = self.repo.clausulas([linha["id"]])
        linha["clausulas"] = [
            {"codigo": r.codigo, "clausula": CLAUSULAS_POR_CODIGO[r.codigo].nome,
             "nivel": ROTULO_NIVEL.get(r.nivel, r.nivel), "evidencia": (r.evidencia or "")[:200]}
            for r in cl.itertuples()]
        return linha

    def buscar_texto(self, termo: str, apolice_id: str | None = None) -> pd.DataFrame:
        df = self.repo.buscar_texto(termo, apolice_id or None, limite=MAX_LINHAS)
        if not df.empty:
            df["texto"] = df["texto"].str.slice(0, 300)
        return df

    def ranking_seguradoras(self, codigo: str | None = None) -> pd.DataFrame:
        if codigo:
            cl = self.repo.clausulas()
            cl = cl[cl["codigo"] == codigo.upper()]
            cl["pontos"] = cl["nivel"].map(NIVEIS).fillna(0) * 100
            ap = self.repo.apolices()[["id", "seguradora"]]
            df = cl.merge(ap, left_on="apolice_id", right_on="id")
            return (df.groupby("seguradora")["pontos"].agg(["mean", "count"])
                    .rename(columns={"mean": f"atendimento_medio_{codigo}", "count": "apolices"})
                    .round(1).sort_values(f"atendimento_medio_{codigo}", ascending=False)
                    .reset_index())
        df = self._base()
        return (df.groupby("seguradora").agg(escore_medio=("escore", "mean"),
                                             escore_criticas=("escore_criticas", "mean"),
                                             apolices=("id", "count"),
                                             premio_medio=("premio", "mean"))
                .round(1).sort_values("escore_medio", ascending=False).reset_index())

    def taxonomia(self) -> pd.DataFrame:
        return pd.DataFrame([{"código": c.codigo, "cláusula": c.nome, "grupo": c.grupo,
                              "peso": c.peso, "crítica": c.critica} for c in CLAUSULAS])

    # ------------------------------------------------------------ execução
    def _executar(self, nome: str, args: dict[str, Any]) -> ChamadaFerramenta:
        fn = getattr(self, nome, None) if nome in {f["function"]["name"] for f in FERRAMENTAS} else None
        if fn is None:
            return ChamadaFerramenta(nome, args, erro="Ferramenta desconhecida.")
        try:
            return ChamadaFerramenta(nome, args, resultado=fn(**args))
        except Exception as exc:  # noqa: BLE001
            return ChamadaFerramenta(nome, args, erro=f"{type(exc).__name__}: {exc}")

    @staticmethod
    def _serializar(ch: ChamadaFerramenta) -> str:
        if ch.erro:
            return json.dumps({"erro": ch.erro}, ensure_ascii=False)
        r = ch.resultado
        if isinstance(r, pd.DataFrame):
            rec = r.head(MAX_LINHAS)
            return json.dumps({"linhas_totais": len(r), "dados": json.loads(
                rec.to_json(orient="records", force_ascii=False))}, ensure_ascii=False)
        return json.dumps(r, ensure_ascii=False, default=str)

    def perguntar(self, pergunta: str, historico: list[dict[str, str]] | None = None) -> RespostaConsulta:
        if not getattr(self.cliente, "disponivel", False):
            return self._deterministico(pergunta)
        try:
            return self._com_llm(pergunta, historico or [])
        except LLMIndisponivel as exc:
            r = self._deterministico(pergunta)
            r.erro = str(exc)
            return r

    def _com_llm(self, pergunta: str, historico: list[dict[str, str]]) -> RespostaConsulta:
        modelo = self.cliente.settings.modelo_copiloto
        msgs: list[dict[str, Any]] = [{"role": "system", "content": SISTEMA}]
        for h in historico[-6:]:
            if h.get("role") in ("user", "assistant") and h.get("content"):
                msgs.append({"role": h["role"], "content": h["content"]})
        msgs.append({"role": "user", "content": pergunta})
        chamadas: list[ChamadaFerramenta] = []
        for _ in range(MAX_ITERACOES):
            resp = self.cliente.chat(msgs, modelo=modelo, tools=FERRAMENTAS, max_tokens=3000,
                                     tarefa="pf_consulta")
            msg = ((resp.get("choices") or [{}])[0]).get("message") or {}
            tcs = msg.get("tool_calls") or []
            if not tcs:
                return RespostaConsulta((msg.get("content") or "").strip()
                                        or "Não consegui formular uma resposta.",
                                        chamadas, "llm", modelo)
            msgs.append({"role": "assistant", "content": msg.get("content") or "",
                         "tool_calls": tcs})
            for tc in tcs:
                fn = tc.get("function") or {}
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                ch = self._executar(fn.get("name", ""), args)
                chamadas.append(ch)
                msgs.append({"role": "tool", "tool_call_id": tc.get("id", ""),
                             "name": ch.nome, "content": self._serializar(ch)})
        return RespostaConsulta("Consultei a base, mas não fechei a resposta em "
                                f"{MAX_ITERACOES} passos. Veja as tabelas abaixo.",
                                chamadas, "llm", modelo)

    def _deterministico(self, pergunta: str) -> RespostaConsulta:
        """Roteamento simples por palavras-chave (contingência sem LLM)."""
        p = normalizar(pergunta)
        for c in CLAUSULAS:
            if c.codigo.lower() in p:
                ch = self._executar("apolices_por_clausula", {"codigo": c.codigo})
                return RespostaConsulta(
                    f"Modo sem IA: apólices pelo nível da cláusula **{c.nome}** ({c.codigo}).",
                    [ch], "deterministico")
        if "seguradora" in p and ("melhor" in p or "ranking" in p):
            ch = self._executar("ranking_seguradoras", {})
            return RespostaConsulta("Modo sem IA: ranking médio por seguradora.", [ch],
                                    "deterministico")
        ch = self._executar("listar_apolices", {"ordenar_por": "escore"})
        return RespostaConsulta(
            "Modo sem IA (configure a GROQ_API_KEY para perguntas livres): "
            "listei as apólices por escore de proteção.", [ch], "deterministico")
