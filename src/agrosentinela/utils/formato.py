"""Formatação de números, datas e textos no padrão brasileiro."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

_MESES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)
_DIAS = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
         "sexta-feira", "sábado", "domingo")


def num(valor: Any, casas: int = 2) -> str:
    """1234567.89 -> '1.234.567,89'"""
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return "—"
    texto = f"{v:,.{casas}f}"
    return texto.replace(",", "§").replace(".", ",").replace("§", ".")


def inteiro(valor: Any) -> str:
    return num(valor, 0)


def reais(valor: Any, casas: int = 2) -> str:
    return f"R$ {num(valor, casas)}"


def reais_compacto(valor: Any) -> str:
    """Abrevia grandes valores: R$ 3,12 bi / R$ 450,0 mi / R$ 12,4 mil."""
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return "—"
    sinal = "-" if v < 0 else ""
    v = abs(v)
    if v >= 1e9:
        return f"{sinal}R$ {num(v / 1e9, 2)} bi"
    if v >= 1e6:
        return f"{sinal}R$ {num(v / 1e6, 1)} mi"
    if v >= 1e3:
        return f"{sinal}R$ {num(v / 1e3, 1)} mil"
    return f"{sinal}R$ {num(v, 2)}"


def hectares(valor: Any) -> str:
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return "—"
    if v >= 1e6:
        return f"{num(v / 1e6, 2)} mi ha"
    if v >= 1e3:
        return f"{num(v / 1e3, 1)} mil ha"
    return f"{num(v, 1)} ha"


def pct(valor: Any, casas: int = 1) -> str:
    try:
        return f"{num(float(valor), casas)}%"
    except (TypeError, ValueError):
        return "—"


def data_br(valor: Any) -> str:
    """Converte para 'dd/mm/aaaa'."""
    d = _para_data(valor)
    return d.strftime("%d/%m/%Y") if d else "—"


def data_extensa(valor: Any) -> str:
    """'quinta-feira, 17 de setembro'."""
    d = _para_data(valor)
    if not d:
        return "—"
    return f"{_DIAS[d.weekday()]}, {d.day} de {_MESES[d.month - 1]}"


def data_curta(valor: Any) -> str:
    """'17/09 (qui)'."""
    d = _para_data(valor)
    if not d:
        return "—"
    abrev = _DIAS[d.weekday()][:3]
    return f"{d.day:02d}/{d.month:02d} ({abrev})"


def _para_data(valor: Any) -> date | None:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor).strip()
    if not texto or texto.lower() in {"nat", "nan", "none"}:
        return None
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(texto[: len(formato) + 2], formato).date()
        except ValueError:
            continue
    try:
        import pandas as pd

        ts = pd.to_datetime(texto, errors="coerce")
        return None if ts is None or ts is not ts else ts.date()  # NaT != NaT
    except Exception:  # noqa: BLE001
        return None


def truncar(texto: str, limite: int, sufixo: str = "…") -> str:
    """Corta preservando a última palavra inteira."""
    if texto is None:
        return ""
    t = str(texto).strip()
    if len(t) <= limite:
        return t
    corte = t[: max(0, limite - len(sufixo))]
    if " " in corte:
        corte = corte[: corte.rfind(" ")]
    return corte.rstrip(" ,;:.") + sufixo


def plural(n: int, singular: str, plural_: str | None = None) -> str:
    return singular if abs(n) == 1 else (plural_ or singular + "s")
