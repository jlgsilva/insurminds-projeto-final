"""
Zarc — Zoneamento Agrícola de Risco Climático (MAPA / Embrapa).

O Zarc é o único instrumento brasileiro que diz, com respaldo legal, **em
que decêndio se pode plantar cada cultura em cada município, em cada tipo de
solo, com risco de perda de 20%, 30% ou 40%**. É a condição para acesso ao
Proagro e ao seguro subvencionado.

O AgroSentinela usa o Zarc de duas formas, e a segunda é a mais valiosa:

1. **Atenuante do escore** — quem plantou dentro da janela recomendada tem
   o risco calculado reduzido, porque o risco climático já foi mitigado na
   decisão de plantio.
2. **Explicação causal na mensagem** — quando a data de plantio registrada
   no Sicor cai fora da janela, a mensagem deixa de ser "há risco de seca" e
   passa a ser "há risco de seca e seu plantio ficou 2 decêndios além da
   janela Zarc para esta cultura e solo neste município". Essa é uma
   informação que nem o Sicor nem a previsão do tempo dão isoladamente —
   ela só existe no cruzamento.

A tabela embutida abaixo cobre as principais combinações região × cultura,
para que o mecanismo funcione mesmo sem acesso ao portal do MAPA. É uma
aproximação declarada: as janelas oficiais são municipais e publicadas por
portaria de safra.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from .base import ConectorExterno

URL_PLANTIO_CERTO = "https://api.plantiocerto.agricultura.gov.br/v1/zarc"

# Janela de plantio recomendada: (mês/dia de início, mês/dia de fim).
# Janelas que atravessam a virada do ano são representadas com fim < início.
JANELAS: dict[tuple[str, str], tuple[tuple[int, int], tuple[int, int]]] = {
    # (região, cultura): (início, fim)
    ("Centro-Oeste", "SOJA"):        ((10, 1),  (12, 20)),
    ("Sul", "SOJA"):                 ((10, 11), (12, 31)),
    ("Sudeste", "SOJA"):             ((10, 11), (12, 20)),
    ("Nordeste", "SOJA"):            ((11, 1),  (1, 10)),
    ("Norte", "SOJA"):               ((10, 21), (1, 10)),

    ("Centro-Oeste", "MILHO"):       ((10, 1),  (12, 10)),
    ("Sul", "MILHO"):                ((8, 1),   (11, 30)),
    ("Sudeste", "MILHO"):            ((10, 1),  (12, 10)),
    ("Nordeste", "MILHO"):           ((11, 1),  (2, 10)),
    ("Norte", "MILHO"):              ((10, 21), (1, 20)),

    ("Centro-Oeste", "MILHO_2SAFRA"):((1, 11),  (3, 10)),
    ("Sul", "MILHO_2SAFRA"):         ((12, 21), (2, 20)),
    ("Sudeste", "MILHO_2SAFRA"):     ((1, 11),  (3, 10)),
    ("Nordeste", "MILHO_2SAFRA"):    ((1, 21),  (3, 20)),
    ("Norte", "MILHO_2SAFRA"):       ((1, 11),  (3, 20)),

    ("Centro-Oeste", "ALGODAO"):     ((11, 21), (1, 20)),
    ("Nordeste", "ALGODAO"):         ((11, 21), (2, 10)),
    ("Sudeste", "ALGODAO"):          ((11, 1),  (12, 31)),

    ("Sul", "ARROZ"):                ((9, 11),  (12, 10)),
    ("Norte", "ARROZ"):              ((11, 1),  (2, 10)),
    ("Centro-Oeste", "ARROZ"):       ((10, 11), (12, 20)),

    ("Sul", "FEIJAO"):               ((8, 21),  (11, 30)),
    ("Sudeste", "FEIJAO"):           ((9, 21),  (12, 20)),
    ("Centro-Oeste", "FEIJAO"):      ((10, 11), (12, 31)),
    ("Nordeste", "FEIJAO"):          ((11, 1),  (2, 20)),

    ("Sul", "TRIGO"):                ((5, 1),   (7, 20)),
    ("Sudeste", "TRIGO"):            ((3, 1),   (5, 20)),
    ("Centro-Oeste", "TRIGO"):       ((2, 21),  (4, 30)),
}

# Culturas perenes e pecuária não têm janela de plantio anual no Zarc.
SEM_JANELA = {"CAFE", "CANA", "LARANJA", "UVA", "MACA", "PASTAGEM",
              "BOVINOS", "MANDIOCA", "HORTALICAS", "OUTRAS"}

NIVEIS_RISCO = (20, 30, 40)


def _dentro(dia: date, inicio: tuple[int, int], fim: tuple[int, int]) -> bool:
    mi, di = inicio
    mf, df = fim
    atual = (dia.month, dia.day)
    if (mi, di) <= (mf, df):
        return (mi, di) <= atual <= (mf, df)
    # janela que atravessa o ano
    return atual >= (mi, di) or atual <= (mf, df)


def _decendios_de_distancia(dia: date, inicio: tuple[int, int],
                            fim: tuple[int, int]) -> int:
    """
    Quantos decêndios (10 dias) o plantio ficou fora da janela.

    A janela é anual e se repete a cada safra, então a distância é medida
    contra a **safra mais próxima** — o ano anterior, o corrente e o
    seguinte. Sem isso, um plantio em 20/01 contra uma janela out–dez seria
    lido como "25 decêndios adiantado para a próxima safra" em vez de
    "3 decêndios atrasado em relação à safra corrente", que é a leitura
    agronomicamente correta.
    """
    if _dentro(dia, inicio, fim):
        return 0
    melhor = None
    for deslocamento in (-1, 0, 1):
        ano = dia.year + deslocamento
        try:
            d_ini = date(ano, inicio[0], inicio[1])
            d_fim = date(ano, fim[0], fim[1])
        except ValueError:                  # 29/02 em ano não bissexto
            continue
        if d_fim < d_ini:                   # janela que atravessa o ano
            d_fim = date(ano + 1, fim[0], fim[1])
        dist = 0 if d_ini <= dia <= d_fim else min(
            abs((d_ini - dia).days), abs((dia - d_fim).days)
        )
        if melhor is None or dist < melhor:
            melhor = dist
    return max(1, (melhor or 0) // 10)


class Zarc(ConectorExterno):
    chave = "zarc"
    nome = "Zarc — Zoneamento Agrícola de Risco Climático"
    ttl_min = 60 * 24 * 30

    def _buscar(self, *, cd_ibge: int | str, cultura: str, **_: Any) -> pd.DataFrame:
        dados = self._get_json(URL_PLANTIO_CERTO, {
            "municipio": cd_ibge, "cultura": cultura,
        })
        registros = dados.get("dados") if isinstance(dados, dict) else dados
        if not registros:
            return pd.DataFrame()
        return pd.DataFrame(registros)

    def _offline(self, *, cultura: str = "SOJA", regiao: str = "Centro-Oeste",
                 **_: Any) -> pd.DataFrame:
        cultura = (cultura or "").upper()
        janela = JANELAS.get((regiao, cultura))
        if janela is None:
            return pd.DataFrame([{
                "cultura": cultura, "regiao": regiao,
                "tem_janela": False,
                "observacao": "cultura perene ou pecuária — sem janela anual de "
                              "plantio no Zarc",
            }])
        (mi, di), (mf, df) = janela
        return pd.DataFrame([{
            "cultura": cultura,
            "regiao": regiao,
            "tem_janela": True,
            "inicio_mes": mi, "inicio_dia": di,
            "fim_mes": mf, "fim_dia": df,
            "nivel_risco_pct": 30,
            "referencia": True,
        }])

    def _params_sonda(self) -> dict[str, Any]:
        return {"cd_ibge": 5107925, "cultura": "SOJA"}


# ==========================================================================
# Avaliação usada pelo motor de regras
# ==========================================================================

def avaliar_plantio(cultura: str, regiao: str,
                    dt_plantio: date | None) -> dict[str, Any]:
    """
    Diz se o plantio registrado no Sicor caiu dentro da janela Zarc.

    Devolve sempre as mesmas chaves, para que o motor de regras possa usá-las
    sem verificar disponibilidade:

    * ``avaliavel``          — há janela conhecida para esta combinação
    * ``dentro_janela``      — ``True`` / ``False``
    * ``decendios_fora``     — 0 quando dentro
    * ``fator``              — multiplicador aplicado ao escore (0,85 a 1,25)
    * ``explicacao``         — frase pronta para entrar na mensagem
    """
    cultura = (cultura or "").upper()
    vazio = {
        "avaliavel": False, "dentro_janela": None, "decendios_fora": 0,
        "fator": 1.0, "explicacao": "",
    }
    if dt_plantio is None or cultura in SEM_JANELA:
        return vazio
    janela = JANELAS.get((regiao, cultura))
    if janela is None:
        return vazio

    inicio, fim = janela
    dentro = _dentro(dt_plantio, inicio, fim)
    fora = 0 if dentro else _decendios_de_distancia(dt_plantio, inicio, fim)

    if dentro:
        return {
            "avaliavel": True, "dentro_janela": True, "decendios_fora": 0,
            "fator": 0.85,
            "explicacao": "o plantio está dentro da janela recomendada pelo "
                          "Zoneamento Agrícola de Risco Climático (Zarc) para "
                          "esta cultura na sua região",
        }

    fator = min(1.25, 1.0 + 0.05 * fora)
    plural = "decêndio" if fora == 1 else "decêndios"
    return {
        "avaliavel": True, "dentro_janela": False, "decendios_fora": fora,
        "fator": round(fator, 2),
        "explicacao": (
            f"o plantio registrado ficou {fora} {plural} fora da janela "
            "recomendada pelo Zarc para esta cultura na sua região, o que "
            "eleva a exposição climática e pode afetar o enquadramento no "
            "Proagro"
        ),
    }


def janela_texto(cultura: str, regiao: str) -> str:
    """Janela em formato legível, para exibir na interface."""
    janela = JANELAS.get((regiao, (cultura or "").upper()))
    if janela is None:
        return "sem janela anual definida"
    (mi, di), (mf, df) = janela
    return f"{di:02d}/{mi:02d} a {df:02d}/{mf:02d}"


def cobertura() -> pd.DataFrame:
    """Todas as janelas embutidas, exibidas na página de documentação."""
    return pd.DataFrame([
        {"regiao": r, "cultura": c, "janela": janela_texto(c, r)}
        for (r, c) in sorted(JANELAS)
    ])
