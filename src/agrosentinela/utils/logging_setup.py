"""
Configuração de logging estruturado e leve (sem dependências externas).

Compatibilidade com Windows
---------------------------
Os registros deste projeto usam acentuação e símbolos (``✔``, ``✖``, ``⚠``,
``═``) porque a legibilidade do log importa — é por ele que se acompanha um
ETL de uma hora. No Windows isso esbarra em duas armadilhas clássicas, e as
duas são tratadas aqui:

1. **Codificação do fluxo de saída.** O console do Windows lida bem com
   Unicode, mas assim que a saída é redirecionada (``> log.txt``) ou passa por
   um *pipe*, o Python volta à codificação local — normalmente ``cp1252`` —
   e qualquer símbolo fora dela derruba o programa com ``UnicodeEncodeError``.
   Perder uma execução de uma hora por causa de um caractere de visto é
   inaceitável, então o fluxo é reconfigurado para UTF-8 com
   ``errors="replace"``: na pior das hipóteses aparece um ``?`` no lugar do
   símbolo, e o processo segue.

2. **Cores ANSI.** O ``cmd.exe`` antigo não interpreta as sequências de
   escape e mostra lixo do tipo ``←[38;5;39m`` no lugar da cor. Aqui a cor só
   é ligada depois de **confirmar** que o terminal aceita — tentando habilitar
   o modo de terminal virtual no Windows 10 ou superior e desistindo em
   silêncio se não der.

Nada disso muda o comportamento em Linux e macOS.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

_CONFIGURADO = False


def _preparar_saida_unicode() -> None:
    """
    Garante que ``stdout`` e ``stderr`` aceitem Unicode em qualquer sistema.

    ``reconfigure`` existe desde o Python 3.7; em fluxos que não o suportam
    (um objeto substituído por um teste, por exemplo) a falha é ignorada,
    porque preparar o log nunca pode ser motivo para o programa não rodar.
    """
    for fluxo in (sys.stdout, sys.stderr):
        try:
            if getattr(fluxo, "encoding", "").lower().replace("-", "") != "utf8":
                fluxo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 — fluxo exótico ou já fechado
            continue


def _terminal_aceita_cor(fluxo: Any) -> bool:
    """
    Diz se vale a pena emitir sequências de cor ANSI neste terminal.

    Em Windows 10 ou superior, tenta ligar o modo de terminal virtual. Se a
    chamada falhar, o terminal é antigo e mostraria as sequências como lixo —
    então é melhor não colorir nada.
    """
    if os.environ.get("NO_COLOR") is not None:
        return False
    try:
        if not fluxo.isatty():
            return False
    except Exception:  # noqa: BLE001
        return False

    if sys.platform != "win32":
        return True

    # Windows Terminal e o VS Code já anunciam suporte; os demais precisam do
    # modo de terminal virtual ligado explicitamente.
    if os.environ.get("WT_SESSION") or os.environ.get("TERM_PROGRAM"):
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        STD_ERROR_HANDLE = -12
        handle = kernel32.GetStdHandle(STD_ERROR_HANDLE)
        modo = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(modo)):
            return False
        return bool(kernel32.SetConsoleMode(
            handle, modo.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING
        ))
    except Exception:  # noqa: BLE001 — console antigo ou sem ctypes
        return False


_CORES = {
    "DEBUG": "\033[38;5;245m",
    "INFO": "\033[38;5;39m",
    "WARNING": "\033[38;5;214m",
    "ERROR": "\033[38;5;196m",
    "CRITICAL": "\033[48;5;196;38;5;231m",
}
_RESET = "\033[0m"


class _Formatador(logging.Formatter):
    def __init__(self, colorido: bool) -> None:
        super().__init__("%(asctime)s | %(levelname)-8s | %(name)-34s | %(message)s", "%H:%M:%S")
        self.colorido = colorido

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        texto = super().format(record)
        if self.colorido:
            cor = _CORES.get(record.levelname, "")
            return f"{cor}{texto}{_RESET}" if cor else texto
        return texto


def configurar_logging(nivel: str | int = "INFO") -> None:
    """Configura o logger raiz uma única vez."""
    global _CONFIGURADO
    if _CONFIGURADO:
        return
    _CONFIGURADO = True

    if isinstance(nivel, str):
        nivel = getattr(logging, nivel.upper(), logging.INFO)

    _preparar_saida_unicode()

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_Formatador(_terminal_aceita_cor(sys.stderr)))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(nivel)

    # Reduz ruído de bibliotecas de rede
    for ruidoso in ("urllib3", "requests", "httpx", "httpcore"):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)


def get_logger(nome: str) -> logging.Logger:
    """Logger nomeado, garantindo a configuração mínima."""
    if not _CONFIGURADO:
        configurar_logging(os.environ.get("LOG_LEVEL", "INFO"))
    return logging.getLogger(nome)


class ColetorEventos(logging.Handler):
    """
    Handler que guarda os registros em memória para exibição na interface.

    Usado pela página "Execução do pipeline" do Streamlit para mostrar o
    passo a passo real do processamento, sem recorrer a ``print``.
    """

    def __init__(self, capacidade: int = 500) -> None:
        super().__init__()
        self.capacidade = capacidade
        self.registros: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.registros.append(
            {
                "hora": self.format(record).split(" | ")[0] if self.formatter else "",
                "nivel": record.levelname,
                "origem": record.name,
                "mensagem": record.getMessage(),
            }
        )
        if len(self.registros) > self.capacidade:
            self.registros = self.registros[-self.capacidade :]

    def limpar(self) -> None:
        self.registros.clear()
