"""
Avaliação da extração contra o gabarito do acervo simulado.

É o que transforma "a IA extraiu" em "a IA extraiu com X% de acerto": cada
apólice simulada nasceu de uma especificação conhecida, então dá para medir
campo a campo e cláusula a cláusula — e comparar o extrator LLM com a linha
de base determinística.
"""

from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from typing import Any

import pandas as pd

from ..config import APOLICES_DIR
from .clausulas import CLAUSULAS


@lru_cache(maxsize=1)
def gabarito() -> dict[str, dict[str, Any]]:
    caminho = APOLICES_DIR / "gabarito.json"
    if not caminho.exists():
        return {}
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    return {d["identificador"]: d for d in dados}


def identificador_de(nome_documento: str) -> str | None:
    """'AP03-BAO-T01_digitalizada' → 'AP03-BAO-T01' quando estiver no gabarito."""
    for ident in gabarito():
        if nome_documento.startswith(ident):
            return ident
    return None


def _num_ok(a: Any, b: Any, tol: float = 0.005) -> bool:
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return False
    return abs(a - b) <= tol * max(1.0, abs(b))


def _data_ok(a: Any, b: str | None) -> bool:
    if b is None:
        return a in (None, "", "null")
    if isinstance(a, date):
        a = a.isoformat()
    return str(a)[:10] == b[:10]


def avaliar(ident: str, cadastro: dict[str, Any], niveis: dict[str, str]) -> dict[str, Any]:
    g = gabarito().get(ident)
    if not g:
        return {}
    campos = {
        "lmg": _num_ok(cadastro.get("lmg"), g["lmg"]),
        "premio": _num_ok(cadastro.get("premio"), g["premio"]),
        "franquia": _num_ok(cadastro.get("franquia"), g["franquia"]),
        "vigencia_inicio": _data_ok(cadastro.get("vigencia_inicio"), g["vigencia_inicio"]),
        "vigencia_fim": _data_ok(cadastro.get("vigencia_fim"), g["vigencia_fim"]),
        "retroatividade": (bool(cadastro.get("retroatividade_ilimitada"))
                           if g["retroatividade_ilimitada"]
                           else _data_ok(cadastro.get("retroatividade"), g["retroatividade"])),
        "uf": str(cadastro.get("uf") or "").upper() == g["uf"],
    }
    acertos_cl = {c.codigo: niveis.get(c.codigo, "ausente") == g["avaliacoes"][c.codigo]
                  for c in CLAUSULAS}
    # Acerto "tolerante": confundir ampla↔padrão é menos grave que errar
    # presença/ausência — medimos as duas coisas.
    presenca = {c.codigo: (niveis.get(c.codigo, "ausente") in ("ausente", "excluida"))
                == (g["avaliacoes"][c.codigo] in ("ausente", "excluida")) for c in CLAUSULAS}
    return {
        "identificador": ident,
        "campos_ok": sum(campos.values()), "campos_total": len(campos),
        "clausulas_ok": sum(acertos_cl.values()), "clausulas_total": len(acertos_cl),
        "presenca_ok": sum(presenca.values()),
        "acuracia_campos": round(100 * sum(campos.values()) / len(campos), 1),
        "acuracia_clausulas": round(100 * sum(acertos_cl.values()) / len(acertos_cl), 1),
        "acuracia_presenca": round(100 * sum(presenca.values()) / len(presenca), 1),
        "erros_campos": [k for k, v in campos.items() if not v],
        "erros_clausulas": [k for k, v in acertos_cl.items() if not v],
    }


def matriz_confusao(linhas: list[tuple[str, str]]) -> pd.DataFrame:
    """(gabarito, extraído) → tabela cruzada de níveis."""
    if not linhas:
        return pd.DataFrame()
    df = pd.DataFrame(linhas, columns=["gabarito", "extraído"])
    return pd.crosstab(df["gabarito"], df["extraído"])
