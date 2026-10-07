"""
Cliente da GroqCloud (API compatível com OpenAI).

Decisões de projeto
-------------------

* **Sem SDK proprietário.** Falamos o protocolo HTTP diretamente com
  ``/openai/v1/chat/completions``. Isso elimina conflitos de versão no
  Streamlit Cloud e deixa explícito, para fins didáticos, o que é enviado
  ao modelo.
* **Camada gratuita respeitada.** Há um orçamento de chamadas por execução,
  respeito ao cabeçalho ``Retry-After`` em 429 e *backoff* exponencial.
* **Cache em disco.** Requisições idênticas não são repetidas — essencial
  para não queimar cota ao reexecutar o pipeline durante a avaliação.
* **Telemetria.** Cada chamada registra modelo, latência, tokens e se veio
  do cache. A interface mostra esse painel.
* **Degradação graciosa.** Sem chave de API, ou com a API indisponível, o
  sistema **não quebra**: o :mod:`redator` cai para um gerador determinístico
  baseado em modelos de texto. O fluxo do desafio continua demonstrável.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..config import DATA_DIR, get_settings
from ..utils.logging_setup import get_logger

log = get_logger(__name__)

CACHE_DIR = DATA_DIR / "cache_llm"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


class LLMIndisponivel(RuntimeError):
    """A API do modelo não pôde ser usada (sem chave, cota ou rede)."""


@dataclass
class ChamadaLLM:
    """Registro de telemetria de uma chamada ao modelo."""

    modelo: str
    tarefa: str
    tokens_entrada: int = 0
    tokens_saida: int = 0
    latencia_s: float = 0.0
    do_cache: bool = False
    erro: str | None = None

    @property
    def tokens_total(self) -> int:
        return self.tokens_entrada + self.tokens_saida


@dataclass
class Telemetria:
    """Acumulador de uso do modelo durante uma execução do pipeline."""

    chamadas: list[ChamadaLLM] = field(default_factory=list)

    def registrar(self, c: ChamadaLLM) -> None:
        self.chamadas.append(c)

    @property
    def n_chamadas(self) -> int:
        return len([c for c in self.chamadas if not c.do_cache and not c.erro])

    @property
    def n_cache(self) -> int:
        return len([c for c in self.chamadas if c.do_cache])

    @property
    def n_erros(self) -> int:
        return len([c for c in self.chamadas if c.erro])

    @property
    def tokens_total(self) -> int:
        return sum(c.tokens_total for c in self.chamadas)

    @property
    def latencia_total(self) -> float:
        return round(sum(c.latencia_s for c in self.chamadas), 2)

    def resumo(self) -> dict[str, Any]:
        return {
            "chamadas_api": self.n_chamadas,
            "respostas_do_cache": self.n_cache,
            "erros": self.n_erros,
            "tokens_entrada": sum(c.tokens_entrada for c in self.chamadas),
            "tokens_saida": sum(c.tokens_saida for c in self.chamadas),
            "tokens_total": self.tokens_total,
            "latencia_total_s": self.latencia_total,
            "modelos": sorted({c.modelo for c in self.chamadas}),
        }

    def por_tarefa(self) -> list[dict[str, Any]]:
        agrupado: dict[str, dict[str, Any]] = {}
        for c in self.chamadas:
            item = agrupado.setdefault(
                c.tarefa,
                {"tarefa": c.tarefa, "chamadas": 0, "cache": 0, "tokens": 0, "latencia_s": 0.0},
            )
            item["chamadas"] += 0 if c.do_cache else 1
            item["cache"] += 1 if c.do_cache else 0
            item["tokens"] += c.tokens_total
            item["latencia_s"] = round(item["latencia_s"] + c.latencia_s, 2)
        return list(agrupado.values())

    def limpar(self) -> None:
        self.chamadas.clear()


class GroqClient:
    """Cliente mínimo, resiliente e instrumentado da GroqCloud."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        telemetria: Telemetria | None = None,
        usar_cache: bool | None = None,
    ) -> None:
        self.settings = get_settings()
        self.api_key = api_key or self.settings.groq_api_key
        self.base_url = self.settings.groq_base_url.rstrip("/")
        self.telemetria = telemetria or Telemetria()
        self.usar_cache = self.settings.llm_cache_ativo if usar_cache is None else usar_cache
        self._orcamento = self.settings.llm_max_chamadas_por_run
        self._gastas = 0

    # ------------------------------------------------------------- estado
    @property
    def disponivel(self) -> bool:
        return bool(self.api_key)

    @property
    def orcamento_restante(self) -> int:
        return max(0, self._orcamento - self._gastas)

    def reiniciar_orcamento(self, novo: int | None = None) -> None:
        self._orcamento = novo if novo is not None else self.settings.llm_max_chamadas_por_run
        self._gastas = 0

    # -------------------------------------------------------------- cache
    @staticmethod
    def _chave(payload: dict[str, Any]) -> Path:
        bruto = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return CACHE_DIR / f"{hashlib.sha256(bruto).hexdigest()[:24]}.json"

    # ---------------------------------------------------------------- api
    def chat(
        self,
        mensagens: Sequence[dict[str, Any]],
        *,
        modelo: str | None = None,
        temperatura: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
        tools: Iterable[dict[str, Any]] | None = None,
        tarefa: str = "generico",
        reasoning_effort: str | None = None,
    ) -> dict[str, Any]:
        """
        Executa uma chamada de *chat completion*.

        Devolve o dicionário bruto da resposta (formato OpenAI). Levanta
        :class:`LLMIndisponivel` quando não é possível chamar a API — cabe
        ao chamador decidir pelo caminho determinístico de contingência.
        """
        if not self.disponivel:
            raise LLMIndisponivel(
                "GROQ_API_KEY não configurada. Defina em .env ou nos secrets do Streamlit."
            )

        modelo = modelo or self.settings.modelo_redacao
        payload: dict[str, Any] = {
            "model": modelo,
            "messages": list(mensagens),
            "temperature": self.settings.llm_temperatura if temperatura is None else temperatura,
            "max_tokens": max_tokens or self.settings.llm_max_tokens,
        }
        if eh_modelo_raciocinio(modelo):
            # GPT-OSS: controla quanto o modelo "pensa" e não devolve o
            # raciocínio no corpo (só a resposta), o que economiza banda e
            # evita que o raciocínio vaze para a interface.
            payload["reasoning_effort"] = (reasoning_effort
                                           or self.settings.llm_reasoning_effort)
            payload["include_reasoning"] = False
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if tools:
            payload["tools"] = list(tools)
            payload["tool_choice"] = "auto"

        # --- cache --------------------------------------------------------
        caminho_cache = self._chave(payload)
        if self.usar_cache and caminho_cache.exists():
            try:
                dados = json.loads(caminho_cache.read_text(encoding="utf-8"))
                uso = dados.get("usage") or {}
                self.telemetria.registrar(
                    ChamadaLLM(
                        modelo=modelo,
                        tarefa=tarefa,
                        tokens_entrada=int(uso.get("prompt_tokens", 0)),
                        tokens_saida=int(uso.get("completion_tokens", 0)),
                        do_cache=True,
                    )
                )
                log.debug("LLM cache-hit (%s / %s)", tarefa, modelo)
                return dados
            except json.JSONDecodeError:
                pass

        # --- orçamento ----------------------------------------------------
        if self.orcamento_restante <= 0:
            raise LLMIndisponivel(
                f"Orçamento de {self._orcamento} chamadas ao modelo esgotado nesta execução "
                "(guarda-corpo da camada gratuita). Aumente LLM_MAX_CHAMADAS_POR_RUN se necessário."
            )

        resposta = self._post(payload, tarefa=tarefa, modelo=modelo)
        if self.usar_cache:
            try:
                caminho_cache.write_text(json.dumps(resposta, ensure_ascii=False), encoding="utf-8")
            except OSError:  # pragma: no cover
                pass
        return resposta

    def _post(self, payload: dict[str, Any], *, tarefa: str, modelo: str) -> dict[str, Any]:
        import requests

        url = f"{self.base_url}/chat/completions"
        cabecalhos = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        ultimo_erro = ""
        for tentativa in range(1, self.settings.llm_max_retries + 1):
            inicio = time.perf_counter()
            try:
                r = requests.post(
                    url, headers=cabecalhos, json=payload, timeout=self.settings.llm_timeout_s
                )
                latencia = time.perf_counter() - inicio

                if r.status_code == 429:
                    espera = float(r.headers.get("retry-after", min(2 ** tentativa, 20)))
                    ultimo_erro = f"429 (cota) — aguardando {espera:.0f}s"
                    log.warning("Groq: limite de taxa atingido. Aguardando %.0fs.", espera)
                    time.sleep(min(espera, 25))
                    continue
                if r.status_code >= 500:
                    ultimo_erro = f"{r.status_code} servidor"
                    time.sleep(min(2 ** tentativa, 8))
                    continue
                if r.status_code >= 400:
                    detalhe = r.text[:300]
                    self.telemetria.registrar(
                        ChamadaLLM(modelo=modelo, tarefa=tarefa, latencia_s=latencia,
                                   erro=f"{r.status_code}: {detalhe}")
                    )
                    raise LLMIndisponivel(f"Groq respondeu {r.status_code}: {detalhe}")

                dados = r.json()
                uso = dados.get("usage") or {}
                self._gastas += 1
                self.telemetria.registrar(
                    ChamadaLLM(
                        modelo=modelo,
                        tarefa=tarefa,
                        tokens_entrada=int(uso.get("prompt_tokens", 0)),
                        tokens_saida=int(uso.get("completion_tokens", 0)),
                        latencia_s=round(latencia, 3),
                    )
                )
                return dados
            except LLMIndisponivel:
                raise
            except Exception as exc:  # noqa: BLE001
                ultimo_erro = str(exc)
                log.warning("Groq tentativa %d falhou: %s", tentativa, exc)
                time.sleep(min(2 ** tentativa, 8))

        self.telemetria.registrar(ChamadaLLM(modelo=modelo, tarefa=tarefa, erro=ultimo_erro))
        raise LLMIndisponivel(f"Groq indisponível após {self.settings.llm_max_retries} tentativas: {ultimo_erro}")

    # ------------------------------------------------------------ helpers
    def texto(
        self,
        *,
        sistema: str,
        usuario: str,
        modelo: str | None = None,
        temperatura: float | None = None,
        max_tokens: int | None = None,
        tarefa: str = "texto",
        reasoning_effort: str | None = None,
    ) -> str:
        """Chamada simples que devolve apenas o conteúdo textual."""
        resposta = self.chat(
            [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
            modelo=modelo,
            temperatura=temperatura,
            max_tokens=max_tokens,
            tarefa=tarefa,
            reasoning_effort=reasoning_effort,
        )
        return self._extrair_texto(resposta)

    def json(
        self,
        *,
        sistema: str,
        usuario: str,
        modelo: str | None = None,
        temperatura: float | None = None,
        max_tokens: int | None = None,
        tarefa: str = "json",
        reasoning_effort: str | None = None,
    ) -> dict[str, Any]:
        """Chamada com ``response_format=json_object`` e *parsing* tolerante."""
        resposta = self.chat(
            [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
            modelo=modelo,
            temperatura=temperatura,
            max_tokens=max_tokens,
            json_mode=True,
            tarefa=tarefa,
            reasoning_effort=reasoning_effort,
        )
        return extrair_json(self._extrair_texto(resposta))

    @staticmethod
    def _extrair_texto(resposta: dict[str, Any]) -> str:
        try:
            return (resposta["choices"][0]["message"].get("content") or "").strip()
        except (KeyError, IndexError, TypeError):
            return ""

    def testar_conexao(self) -> tuple[bool, str]:
        """Ping barato usado pela interface para validar a chave."""
        if not self.disponivel:
            return False, "GROQ_API_KEY não configurada."
        try:
            texto = self.texto(
                sistema="Responda apenas: OK",
                usuario="ping",
                modelo=self.settings.modelo_rapido,
                max_tokens=256,
                temperatura=0.0,
                tarefa="healthcheck",
            )
            return True, f"Conexão com a Groq estabelecida (resposta: {texto[:20] or 'vazia'})."
        except LLMIndisponivel as exc:
            return False, str(exc)


def eh_modelo_raciocinio(modelo: str | None) -> bool:
    """Modelos GPT-OSS aceitam ``reasoning_effort``; os demais rejeitam."""
    return bool(modelo) and str(modelo).startswith("openai/gpt-oss")


def extrair_json(texto: str) -> dict[str, Any]:
    """
    Extrai um objeto JSON de uma resposta do modelo, tolerando cercas de
    código e texto ao redor. Devolve ``{}`` quando não há JSON válido.
    """
    if not texto:
        return {}
    limpo = texto.strip()
    if limpo.startswith("```"):
        limpo = limpo.strip("`")
        if limpo.lower().startswith("json"):
            limpo = limpo[4:]
    try:
        return json.loads(limpo)
    except json.JSONDecodeError:
        pass
    inicio, fim = limpo.find("{"), limpo.rfind("}")
    if inicio >= 0 and fim > inicio:
        try:
            return json.loads(limpo[inicio : fim + 1])
        except json.JSONDecodeError:
            return {}
    return {}
