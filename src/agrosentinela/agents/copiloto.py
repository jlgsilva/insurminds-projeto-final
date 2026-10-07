"""
CopilotoAgent — pergunta e resposta em linguagem natural sobre a operação.

Este agente não faz parte do pipeline de alerta: ele é a camada de consulta
que transforma a base do Sicor e o resultado da execução em conversa.

Uso correto de IA generativa aqui significa **não deixar o modelo inventar
número**. O copiloto usa *function calling*: o modelo escolhe a ferramenta e
os parâmetros, mas quem calcula é o pandas. O modelo só vê o resultado já
apurado e o transforma em resposta. Toda resposta exibe as ferramentas
chamadas e os parâmetros usados, de modo que o usuário possa conferir.

Sem chave de API, o copiloto ainda funciona em **modo determinístico**:
interpreta um conjunto de perguntas frequentes por palavras-chave e executa
a ferramenta correspondente, devolvendo a tabela apurada.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

import pandas as pd

from ..llm.groq_client import GroqClient, LLMIndisponivel
from ..llm.prompts import FERRAMENTAS_COPILOTO, SISTEMA_COPILOTO
from ..rules.catalogo import normalizar
from ..rules.engine import MotorRegras
from ..utils.formato import hectares, inteiro, num, pct, reais_compacto
from ..utils.logging_setup import get_logger

log = get_logger(__name__)

MAX_ITERACOES = 4
MAX_LINHAS_RESPOSTA = 25


@dataclass
class ChamadaFerramenta:
    nome: str
    argumentos: dict[str, Any]
    linhas: int = 0
    erro: str | None = None
    resultado: pd.DataFrame | dict[str, Any] | None = None


@dataclass
class RespostaCopiloto:
    texto: str
    ferramentas: list[ChamadaFerramenta] = field(default_factory=list)
    modelo: str = ""
    modo: str = "llm"          # "llm" | "deterministico"
    erro: str | None = None

    @property
    def tabelas(self) -> list[pd.DataFrame]:
        return [
            f.resultado for f in self.ferramentas
            if isinstance(f.resultado, pd.DataFrame) and not f.resultado.empty
        ]


class CopilotoAgent:
    """Copiloto analítico com ferramentas sobre a base e sobre os alertas."""

    nome = "CopilotoAgent"
    papel = "Consulta em linguagem natural sobre carteira, alertas e Proagro"
    descricao = (
        "Responde perguntas em português usando *function calling*: o modelo "
        "escolhe a consulta, o pandas calcula o número e o modelo apenas "
        "redige. Funciona também sem chave de API, em modo determinístico."
    )

    def __init__(
        self,
        *,
        carteira: pd.DataFrame,
        alertas: pd.DataFrame | None = None,
        sinistros: pd.DataFrame | None = None,
        indicadores: pd.DataFrame | None = None,
        municipios: pd.DataFrame | None = None,
        cliente: GroqClient | None = None,
        motor: MotorRegras | None = None,
        origem_dados: str = "seed",
    ) -> None:
        self.carteira = carteira if carteira is not None else pd.DataFrame()
        self.alertas = alertas if alertas is not None else pd.DataFrame()
        self.sinistros = sinistros if sinistros is not None else pd.DataFrame()
        self.indicadores = indicadores if indicadores is not None else pd.DataFrame()
        self.municipios = municipios if municipios is not None else pd.DataFrame()
        self.cliente = cliente or GroqClient()
        self.motor = motor or MotorRegras()
        self.origem_dados = origem_dados

        self.ferramentas: dict[str, Callable[..., pd.DataFrame | dict[str, Any]]] = {
            "consultar_carteira": self.consultar_carteira,
            "consultar_alertas": self.consultar_alertas,
            "consultar_proagro": self.consultar_proagro,
            "consultar_clima": self.consultar_clima,
            "explicar_regra": self.explicar_regra,
        }

    # ==================================================================
    # Ferramentas
    # ==================================================================
    def consultar_carteira(
        self,
        agrupar_por: Sequence[str] | None = None,
        filtros: dict[str, Any] | None = None,
        metricas: Sequence[str] | None = None,
        ordenar_por: str | None = None,
        limite: int = 15,
    ) -> pd.DataFrame:
        df = self._filtrar(self.carteira, filtros)
        if df.empty:
            return pd.DataFrame()
        grupos = [g for g in (agrupar_por or ["uf"]) if g in df.columns] or ["uf"]
        metricas = list(metricas or ["n_operacoes", "valor_credito", "area_ha"])

        agg = df.groupby(grupos, as_index=False).agg(
            n_operacoes=("ref_bacen", "count"),
            valor_credito=("valor_credito", "sum"),
            area_ha=("area_ha", "sum"),
            valor_medio=("valor_credito", "mean"),
            pct_cobertura=("tem_cobertura", "mean"),
        )
        agg["pct_cobertura"] = (agg["pct_cobertura"] * 100).round(1)
        agg["valor_medio"] = agg["valor_medio"].round(2)
        agg["valor_credito"] = agg["valor_credito"].round(2)
        agg["area_ha"] = agg["area_ha"].round(1)

        colunas = grupos + [m for m in metricas if m in agg.columns]
        ordem = ordenar_por if ordenar_por in agg.columns else (
            "valor_credito" if "valor_credito" in colunas else colunas[-1]
        )
        return agg[colunas].sort_values(ordem, ascending=False).head(int(limite or 15))

    def consultar_alertas(
        self,
        agrupar_por: Sequence[str] | None = None,
        filtros: dict[str, Any] | None = None,
        limite: int = 15,
    ) -> pd.DataFrame:
        df = self._filtrar(self.alertas, filtros)
        if df.empty:
            return pd.DataFrame()
        mapa = {"evento": "evento_nome", "municipio": "municipio"}
        grupos = [mapa.get(g, g) for g in (agrupar_por or ["evento"])]
        grupos = [g for g in grupos if g in df.columns] or ["severidade"]
        agg = df.groupby(grupos, as_index=False).agg(
            alertas=("id", "count"),
            operacoes=("ref_bacen", "nunique"),
            exposicao=("valor_credito", "sum"),
            area_ha=("area_ha", "sum"),
            score_max=("score", "max"),
            score_medio=("score", "mean"),
            criticos=("severidade", lambda s: int((s == "critico").sum())),
            sem_cobertura=("tem_cobertura", lambda s: int((~s.astype(bool)).sum())),
        )
        agg["exposicao"] = agg["exposicao"].round(2)
        agg["area_ha"] = agg["area_ha"].round(1)
        agg["score_medio"] = agg["score_medio"].round(1)
        return agg.sort_values(["criticos", "exposicao"], ascending=False).head(int(limite or 15))

    def consultar_proagro(
        self,
        agrupar_por: Sequence[str] | None = None,
        filtros: dict[str, Any] | None = None,
        limite: int = 15,
    ) -> pd.DataFrame:
        df = self._filtrar(self.sinistros, filtros)
        if df.empty:
            return pd.DataFrame()
        if "municipio" in (agrupar_por or []) and "municipio" not in df.columns:
            df = self._anexar_nome_municipio(df)
        grupos = [g for g in (agrupar_por or ["evento"]) if g in df.columns] or ["evento"]
        agg = df.groupby(grupos, as_index=False).agg(
            pedidos_cobertura=("n_cop", "sum"),
            comprovacoes_perda=("n_rcp", "sum"),
            operacoes=("n_operacoes", "sum"),
            valor_indenizado=("valor_indenizado", "sum"),
        )
        agg["taxa_acionamento_pct"] = (
            100 * agg["pedidos_cobertura"] / agg["operacoes"].replace(0, pd.NA)
        ).astype(float).round(2)
        agg["valor_indenizado"] = agg["valor_indenizado"].round(2)
        return agg.sort_values("pedidos_cobertura", ascending=False).head(int(limite or 15))

    def consultar_clima(self, municipio: str, uf: str | None = None) -> pd.DataFrame:
        if self.indicadores.empty or self.carteira.empty:
            return pd.DataFrame()
        alvo = normalizar(municipio)
        cart = self.carteira
        mask = cart["municipio"].astype(str).map(normalizar).str.contains(alvo, na=False)
        if uf:
            mask &= cart["uf"].astype(str).str.upper() == str(uf).upper()
        sel = cart[mask]
        if sel.empty or "cell_id" not in sel.columns:
            return pd.DataFrame()
        cells = sel["cell_id"].dropna().unique().tolist()
        ind = self.indicadores[self.indicadores["cell_id"].isin(cells)]
        if ind.empty:
            return pd.DataFrame()
        linha = ind.iloc[0].to_dict()
        nome = sel["municipio"].iloc[0]
        uf_nome = sel["uf"].iloc[0]
        registros = [
            {"municipio": f"{nome}-{uf_nome}", "indicador": k, "valor": v}
            for k, v in linha.items()
            if k != "cell_id" and not str(k).startswith("dia_pico_") and pd.notna(v)
        ]
        return pd.DataFrame(registros)

    def explicar_regra(self, regra_id: str) -> dict[str, Any]:
        alvo = str(regra_id).strip().upper()
        for r in self.motor.regras:
            if r.id.upper() == alvo:
                return {
                    "id": r.id, "nome": r.nome, "evento": r.evento,
                    "descricao": r.descricao, "condicao": r.quando,
                    "severidade_base": r.severidade_base,
                    "escalonamento": [{"quando": e.quando, "severidade": e.severidade}
                                      for e in r.escalonamento],
                    "fases_criticas": list(r.fases_criticas),
                    "personas": list(r.personas),
                    "acao": r.acao, "base_tecnica": r.base_tecnica,
                    "janela_acao_h": r.janela_acao_h,
                    "coberto_pelo_proagro": r.cobertura_proagro,
                }
        return {"erro": f"Regra {alvo} não encontrada.",
                "regras_disponiveis": [r.id for r in self.motor.regras]}

    # ------------------------------------------------------------------
    @staticmethod
    def _filtrar(df: pd.DataFrame, filtros: dict[str, Any] | None) -> pd.DataFrame:
        if df is None or df.empty or not filtros:
            return df if df is not None else pd.DataFrame()
        out = df
        for coluna, valor in filtros.items():
            if coluna not in out.columns:
                continue
            serie = out[coluna]
            if isinstance(valor, (list, tuple, set)):
                alvos = {str(v).strip().upper() for v in valor}
                out = out[serie.astype(str).str.upper().isin(alvos)]
            elif isinstance(valor, dict):
                if "min" in valor:
                    out = out[pd.to_numeric(serie, errors="coerce") >= float(valor["min"])]
                if "max" in valor:
                    out = out[pd.to_numeric(serie, errors="coerce") <= float(valor["max"])]
            elif isinstance(valor, bool):
                out = out[serie.astype(bool) == valor]
            else:
                texto = str(valor).strip()
                if serie.dtype == object or str(serie.dtype) == "string":
                    alvo = normalizar(texto)
                    out = out[serie.astype(str).map(normalizar).str.contains(alvo, na=False)]
                else:
                    out = out[serie.astype(str) == texto]
        return out

    def _anexar_nome_municipio(self, df: pd.DataFrame) -> pd.DataFrame:
        if self.municipios.empty or "cd_ibge" not in df.columns:
            return df
        ref = self.municipios.set_index("cd_ibge")["municipio"]
        out = df.copy()
        out["municipio"] = out["cd_ibge"].map(ref)
        return out

    # ==================================================================
    # Conversa
    # ==================================================================
    def perguntar(
        self, pergunta: str, historico: Sequence[dict[str, str]] | None = None
    ) -> RespostaCopiloto:
        """Responde uma pergunta, usando LLM com ferramentas quando possível."""
        if not self.cliente.disponivel:
            return self._responder_deterministico(pergunta)
        try:
            return self._responder_com_llm(pergunta, historico or [])
        except LLMIndisponivel as exc:
            log.warning("Copiloto sem LLM (%s) — usando modo determinístico.", exc)
            resposta = self._responder_deterministico(pergunta)
            resposta.erro = str(exc)
            return resposta

    # ------------------------------------------------------------------
    def _responder_com_llm(
        self, pergunta: str, historico: Sequence[dict[str, str]]
    ) -> RespostaCopiloto:
        modelo = self.cliente.settings.modelo_copiloto
        contexto = self._contexto_do_sistema()
        mensagens: list[dict[str, Any]] = [
            {"role": "system", "content": SISTEMA_COPILOTO + "\n\n" + contexto}
        ]
        for h in list(historico)[-6:]:
            if h.get("role") in {"user", "assistant"} and h.get("content"):
                mensagens.append({"role": h["role"], "content": h["content"]})
        mensagens.append({"role": "user", "content": pergunta})

        chamadas: list[ChamadaFerramenta] = []
        for _ in range(MAX_ITERACOES):
            resposta = self.cliente.chat(
                mensagens,
                modelo=modelo,
                tools=FERRAMENTAS_COPILOTO,
                max_tokens=2500,
                tarefa="copiloto",
            )
            escolha = (resposta.get("choices") or [{}])[0]
            msg = escolha.get("message") or {}
            tool_calls = msg.get("tool_calls") or []

            if not tool_calls:
                return RespostaCopiloto(
                    texto=(msg.get("content") or "").strip()
                    or "Não consegui formular uma resposta para essa pergunta.",
                    ferramentas=chamadas,
                    modelo=modelo,
                    modo="llm",
                )

            mensagens.append(
                {"role": "assistant", "content": msg.get("content") or "", "tool_calls": tool_calls}
            )
            for tc in tool_calls:
                nome = (tc.get("function") or {}).get("name", "")
                try:
                    args = json.loads((tc.get("function") or {}).get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                chamada = self._executar_ferramenta(nome, args)
                chamadas.append(chamada)
                mensagens.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "name": nome,
                        "content": self._serializar(chamada),
                    }
                )

        return RespostaCopiloto(
            texto=(
                "Consultei os dados, mas não consegui fechar a resposta em "
                f"{MAX_ITERACOES} passos. Os resultados das consultas estão abaixo."
            ),
            ferramentas=chamadas,
            modelo=modelo,
            modo="llm",
        )

    def _executar_ferramenta(self, nome: str, args: dict[str, Any]) -> ChamadaFerramenta:
        fn = self.ferramentas.get(nome)
        if fn is None:
            return ChamadaFerramenta(nome=nome, argumentos=args, erro="Ferramenta desconhecida.")
        try:
            resultado = fn(**args)
        except TypeError as exc:
            return ChamadaFerramenta(nome=nome, argumentos=args, erro=f"Parâmetros inválidos: {exc}")
        except Exception as exc:  # noqa: BLE001
            return ChamadaFerramenta(nome=nome, argumentos=args, erro=f"{type(exc).__name__}: {exc}")
        linhas = len(resultado) if isinstance(resultado, pd.DataFrame) else 1
        return ChamadaFerramenta(nome=nome, argumentos=args, linhas=linhas, resultado=resultado)

    @staticmethod
    def _serializar(chamada: ChamadaFerramenta) -> str:
        if chamada.erro:
            return json.dumps({"erro": chamada.erro}, ensure_ascii=False)
        r = chamada.resultado
        if isinstance(r, pd.DataFrame):
            if r.empty:
                return json.dumps(
                    {"linhas": 0, "aviso": "Nenhum registro para esses filtros."},
                    ensure_ascii=False,
                )
            recorte = r.head(MAX_LINHAS_RESPOSTA)
            return json.dumps(
                {
                    "linhas_totais": int(len(r)),
                    "linhas_retornadas": int(len(recorte)),
                    "dados": json.loads(recorte.to_json(orient="records", force_ascii=False)),
                },
                ensure_ascii=False,
            )
        return json.dumps(r, ensure_ascii=False, default=str)

    def _contexto_do_sistema(self) -> str:
        origem = (
            "microdados oficiais do Sicor/Proagro (Banco Central)"
            if self.origem_dados == "curated"
            else "AMOSTRA DE DEMONSTRAÇÃO sintética (mesma estrutura dos microdados "
                 "do Sicor, mas não são dados reais) — informe isso ao usuário"
        )
        linhas = [
            f"BASE CARREGADA: {origem}.",
            f"Carteira: {inteiro(len(self.carteira))} operações.",
        ]
        if not self.carteira.empty:
            linhas += [
                f"Valor total: {reais_compacto(self.carteira['valor_credito'].sum())}.",
                f"Área total: {hectares(self.carteira['area_ha'].sum())}.",
                f"UFs presentes: {', '.join(sorted(self.carteira['uf'].dropna().unique())[:30])}.",
                f"Culturas: {', '.join(sorted(self.carteira['cultura'].dropna().unique())[:25])}.",
            ]
        if not self.alertas.empty:
            linhas.append(
                f"Execução atual: {len(self.alertas)} alertas, "
                f"{int((self.alertas['severidade'] == 'critico').sum())} críticos, "
                f"exposição {reais_compacto(self.alertas['valor_credito'].sum())}."
            )
        else:
            linhas.append("Execução atual: nenhum alerta carregado no momento.")
        linhas.append(
            "Regras disponíveis: " + ", ".join(r.id for r in self.motor.regras) + "."
        )
        return "\n".join(linhas)

    # ==================================================================
    # Modo determinístico (sem chave de API)
    # ==================================================================
    def _responder_deterministico(self, pergunta: str) -> RespostaCopiloto:
        p = normalizar(pergunta)
        chamadas: list[ChamadaFerramenta] = []

        regra = re.search(r"\b(r-[a-z]{3}-\d{2})\b", pergunta, re.IGNORECASE)
        if regra:
            ch = self._executar_ferramenta("explicar_regra", {"regra_id": regra.group(1)})
            chamadas.append(ch)
            return RespostaCopiloto(
                texto=self._texto_regra(ch), ferramentas=chamadas, modo="deterministico"
            )

        if any(t in p for t in ("alerta", "risco climatico", "evento climatico", "severidade")):
            dim = "uf" if " uf" in p or "estado" in p else (
                "municipio" if "municip" in p else (
                    "cultura" if "cultura" in p else "evento"))
            ch = self._executar_ferramenta("consultar_alertas", {"agrupar_por": [dim]})
            chamadas.append(ch)
            return RespostaCopiloto(
                texto=self._texto_tabela(
                    ch, f"Alertas da execução atual, agrupados por {dim}"
                ),
                ferramentas=chamadas, modo="deterministico",
            )

        if any(t in p for t in ("proagro", "sinistr", "indenizac", "cobertura de perda", "cop", "rcp")):
            dim = "uf" if ("uf" in p or "estado" in p) else ("municipio" if "municip" in p else "evento")
            ch = self._executar_ferramenta("consultar_proagro", {"agrupar_por": [dim]})
            chamadas.append(ch)
            return RespostaCopiloto(
                texto=self._texto_tabela(ch, f"Histórico do Proagro por {dim}"),
                ferramentas=chamadas, modo="deterministico",
            )

        if "clima" in p or "previsao" in p or "chuva" in p or "tempo em" in p:
            m = re.search(r"(?:em|de|para)\s+([A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ÿ\s]{2,40})", pergunta)
            if m:
                ch = self._executar_ferramenta("consultar_clima", {"municipio": m.group(1).strip()})
                chamadas.append(ch)
                return RespostaCopiloto(
                    texto=self._texto_tabela(ch, f"Indicadores climáticos de {m.group(1).strip()}"),
                    ferramentas=chamadas, modo="deterministico",
                )

        dim = ("cultura" if "cultura" in p else
               "municipio" if "municip" in p else
               "programa" if "programa" in p or "pronaf" in p else
               "instituicao" if "banco" in p or "institui" in p else
               "persona" if "persona" in p or "perfil" in p else "uf")
        ch = self._executar_ferramenta("consultar_carteira", {"agrupar_por": [dim]})
        chamadas.append(ch)
        return RespostaCopiloto(
            texto=self._texto_tabela(ch, f"Carteira de crédito rural por {dim}"),
            ferramentas=chamadas,
            modo="deterministico",
        )

    @staticmethod
    def _texto_regra(ch: ChamadaFerramenta) -> str:
        r = ch.resultado or {}
        if not isinstance(r, dict) or r.get("erro"):
            return str((r or {}).get("erro", "Regra não encontrada."))
        return (
            f"**{r['id']} — {r['nome']}**\n\n"
            f"{r['descricao']}\n\n"
            f"- **Evento:** {r['evento']}\n"
            f"- **Condição:** `{r['condicao']}`\n"
            f"- **Severidade base:** {r['severidade_base']}\n"
            f"- **Fases críticas:** {', '.join(r['fases_criticas']) or '—'}\n"
            f"- **Personas notificadas:** {', '.join(r['personas'])}\n"
            f"- **Janela de ação:** {r['janela_acao_h']} h\n"
            f"- **Ação recomendada:** {r['acao']}\n"
            f"- **Base técnica:** {r['base_tecnica']}"
        )

    def _texto_tabela(self, ch: ChamadaFerramenta, titulo: str) -> str:
        if ch.erro:
            return f"Não consegui consultar: {ch.erro}"
        df = ch.resultado
        if not isinstance(df, pd.DataFrame) or df.empty:
            return (
                f"{titulo}: não há registros para esse recorte na base carregada "
                f"({'demonstração' if self.origem_dados != 'curated' else 'Sicor'})."
            )
        linhas = [f"**{titulo}** — {len(df)} linhas (modo sem IA generativa).", ""]
        for _, r in df.head(10).iterrows():
            partes = []
            for col, val in r.items():
                if isinstance(val, float):
                    if "valor" in col or "exposicao" in col or "indeniz" in col:
                        partes.append(f"{col}: {reais_compacto(val)}")
                    elif "pct" in col or "taxa" in col:
                        partes.append(f"{col}: {pct(val)}")
                    else:
                        partes.append(f"{col}: {num(val, 1)}")
                elif isinstance(val, (int,)):
                    partes.append(f"{col}: {inteiro(val)}")
                else:
                    partes.append(f"{col}: {val}")
            linhas.append("- " + " · ".join(partes))
        if len(df) > 10:
            linhas.append(f"- … e mais {len(df) - 10} linhas na tabela abaixo.")
        linhas += [
            "",
            "_Configure a `GROQ_API_KEY` para que o copiloto interprete a pergunta "
            "com IA generativa e escreva a análise._",
        ]
        return "\n".join(linhas)

    # ------------------------------------------------------------------
    @staticmethod
    def sugestoes() -> list[str]:
        """Perguntas de exemplo exibidas na interface."""
        return [
            "Qual o valor total da carteira por UF?",
            "Quais municípios concentram os alertas críticos desta execução?",
            "Quanto da carteira está sem cobertura de risco declarada?",
            "Qual evento climático mais aciona o Proagro no histórico?",
            "Explique a regra R-SEC-01.",
            "Quais culturas têm maior exposição em alerta?",
            "Como está o clima em Sorriso?",
            "Compare a cobertura de Proagro entre Pronaf e demais programas.",
        ]
