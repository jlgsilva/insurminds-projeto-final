"""
Registro dos conectores externos e montagem do contexto municipal.

Duas funções de interesse geral:

* ``obter_conector(chave)`` — instancia um conector pelo identificador do
  catálogo ``fontes_externas``;
* ``contexto_municipal(...)`` — monta o conjunto ``contexto_externo``, que
  enriquece cada município com normal climática, denominador produtivo,
  proteção por seguro, uso do solo, fogo e seca oficial.

O contexto é opcional por construção: quando nenhuma fonte responde, ele
volta com as colunas presentes e vazias, e o pipeline segue funcionando com
o Sicor puro. Nenhuma página quebra por falta de rede — essa foi a condição
de projeto desde o início, porque a solução precisa ser avaliável offline.
"""

from __future__ import annotations

from typing import Any, Iterable

import pandas as pd

from ..fontes_externas import FONTES_POR_CHAVE, FonteExterna
from ..utils.logging_setup import get_logger
from .agritempo import Agritempo
from .ana import Ana, MonitorSecas, severidade_oficial
from .base import ORIGEM_OFFLINE, ConectorExterno, ResultadoExterno
from .cemaden import Cemaden
from .conab import Conab, valor_da_perda
from .ibge_malhas import IbgeMalhas
from .ibge_sidra import IbgeSidra, RENDIMENTO_REFERENCIA
from .inmet import Inmet
from .mapbiomas import MapBiomas, perfil_expansao
from .nasa_power import NasaPower, anomalia_chuva, classificar_anomalia
from .psr_mapa import PENETRACAO_UF, PsrMapa, classificar_protecao
from .queimadas import Queimadas, resumo_por_municipio
from .susep import Susep
from .zarc import Zarc, avaliar_plantio, janela_texto

log = get_logger(__name__)

CONECTORES: dict[str, type[ConectorExterno]] = {
    "nasa_power": NasaPower,
    "inmet": Inmet,
    "cemaden": Cemaden,
    "queimadas_inpe": Queimadas,
    "psr_mapa": PsrMapa,
    "susep": Susep,
    "ibge_pam": IbgeSidra,
    "ibge_ppm": IbgeSidra,
    "ibge_malhas": IbgeMalhas,
    "mapbiomas": MapBiomas,
    "zarc": Zarc,
    "conab": Conab,
    "ana_hidroweb": Ana,
    "monitor_secas": MonitorSecas,
    "agritempo": Agritempo,
}


# Apelidos de conveniência. Todo nome em ``CONECTORES`` corresponde a uma
# fonte catalogada em ``fontes_externas`` — os apelidos existem apenas para
# quem prefere chamar o conector pelo nome do sistema de origem.
APELIDOS: dict[str, str] = {
    "ibge_sidra": "ibge_pam",
    "pam": "ibge_pam",
    "ppm": "ibge_ppm",
    "queimadas": "queimadas_inpe",
    "psr": "psr_mapa",
    "ana": "ana_hidroweb",
}


def obter_conector(chave: str, *, offline: bool = False,
                   timeout: int = 20) -> ConectorExterno:
    chave = APELIDOS.get(chave, chave)
    if chave not in CONECTORES:
        raise KeyError(
            f"Conector externo desconhecido: {chave}. "
            f"Disponíveis: {', '.join(sorted(CONECTORES))}."
        )
    return CONECTORES[chave](offline=offline, timeout=timeout)


def fonte_do_conector(chave: str) -> FonteExterna | None:
    return FONTES_POR_CHAVE.get(chave)


def diagnostico(*, offline: bool = False) -> pd.DataFrame:
    """
    Estado de cada fonte externa, exibido na página de diagnóstico.

    Não dispara sondas de rede por padrão: a página oferece um botão, para
    que abrir o aplicativo não custe uma dezena de requisições.
    """
    linhas = []
    for chave, classe in CONECTORES.items():
        fonte = FONTES_POR_CHAVE.get(chave)
        if fonte is None:
            continue
        linhas.append({
            "chave": chave,
            "fonte": fonte.nome,
            "órgão": fonte.orgao,
            "categoria": fonte.categoria,
            "licença": fonte.licenca,
            "exige cadastro": "não" if not fonte.exige_chave else "sim",
            "ativa no fluxo": "sim" if fonte.usado_agora else "mapeada",
            "sem rede": fonte.fallback,
        })
    df = pd.DataFrame(linhas).drop_duplicates(subset=["fonte"])
    return df.reset_index(drop=True)


def sondar(*, timeout: int = 8) -> pd.DataFrame:
    """Testa a disponibilidade real de cada fonte (acionado por botão)."""
    linhas = []
    for chave in dict.fromkeys(CONECTORES):
        fonte = FONTES_POR_CHAVE.get(chave)
        if fonte is None:
            continue
        conector = obter_conector(chave, timeout=timeout)
        ok = conector.disponivel()
        linhas.append({
            "fonte": fonte.nome,
            "estado": "🟢 respondendo" if ok else "⚪ indisponível agora",
            "sem rede, a solução usa": fonte.fallback,
        })
    return pd.DataFrame(linhas).drop_duplicates(subset=["fonte"])


# ==========================================================================
# Contexto municipal
# ==========================================================================

COLUNAS_CONTEXTO = [
    "cd_ibge", "municipio", "uf", "regiao",
    "chuva_normal_mm_mes", "temp_normal_c",
    "rendimento_ref_kg_ha", "cultura_referencia",
    "penetracao_seguro_privado", "bioma", "frac_lavoura", "frac_pastagem",
    "frac_nativa", "perfil_uso", "focos_calor_24h", "classe_seca",
    "severidade_seca", "origem_contexto",
]


def contexto_municipal(
    municipios: pd.DataFrame,
    *,
    offline: bool = False,
    incluir_normais: bool = True,
    limite_normais: int = 60,
) -> tuple[pd.DataFrame, dict[str, str]]:
    """
    Enriquece a tabela de municípios com as fontes externas livres.

    ``limite_normais`` existe porque a NASA POWER é consultada ponto a ponto:
    em uma carteira nacional isso seriam milhares de requisições. O ETL
    consulta os municípios de maior exposição e reaproveita a normal regional
    para os demais — decisão registrada na coluna ``origem_contexto``, para
    que ninguém leia um valor regional como se fosse pontual.
    """
    if municipios is None or municipios.empty:
        return pd.DataFrame(columns=COLUNAS_CONTEXTO), {}

    base = municipios.copy()
    for col in COLUNAS_CONTEXTO:
        if col not in base.columns:
            base[col] = pd.NA

    procedencia: dict[str, str] = {}

    # ------------------------------------------------- proteção por seguro
    psr = obter_conector("psr_mapa", offline=offline)
    res_psr = psr.obter()
    procedencia["psr_mapa"] = res_psr.origem
    if "uf" in base.columns:
        base["penetracao_seguro_privado"] = base["uf"].map(
            lambda u: PENETRACAO_UF.get(str(u).upper(), 0.03)
        )

    # ------------------------------------------------------- uso do solo
    mb = obter_conector("mapbiomas", offline=offline)
    from .mapbiomas import BIOMA_POR_UF, USO_POR_BIOMA

    if "uf" in base.columns:
        base["bioma"] = base["uf"].map(
            lambda u: BIOMA_POR_UF.get(str(u).upper(), "Cerrado")
        )
        for classe, coluna in (("lavoura", "frac_lavoura"),
                               ("pastagem", "frac_pastagem"),
                               ("nativa", "frac_nativa")):
            base[coluna] = base["bioma"].map(
                lambda b, c=classe: USO_POR_BIOMA.get(b, {}).get(c, float("nan"))
            )
        base["perfil_uso"] = [
            perfil_expansao(float(l or 0), float(n or 0))
            for l, n in zip(base["frac_lavoura"], base["frac_nativa"])
        ]
    procedencia["mapbiomas"] = mb.obter(uf="MT").origem

    # ------------------------------------------------------- normais NASA
    if incluir_normais and {"lat", "lon"}.issubset(base.columns):
        np_con = obter_conector("nasa_power", offline=offline)
        alvo = base.head(max(0, int(limite_normais)))
        normais: dict[int, tuple[float, float]] = {}
        origem_normal = ORIGEM_OFFLINE
        for _, linha in alvo.iterrows():
            try:
                lat, lon = float(linha["lat"]), float(linha["lon"])
            except (TypeError, ValueError):
                continue
            res = np_con.obter(lat=lat, lon=lon)
            origem_normal = res.origem
            if res.vazio:
                continue
            df = res.dados
            chuva = pd.to_numeric(df.get("chuva_normal_mm"), errors="coerce").mean()
            temp = pd.to_numeric(df.get("temp_normal_c"), errors="coerce").mean()
            try:
                normais[int(linha["cd_ibge"])] = (float(chuva), float(temp))
            except (TypeError, ValueError):
                continue
        if normais:
            base["chuva_normal_mm_mes"] = base["cd_ibge"].map(
                lambda c: normais.get(int(c), (float("nan"),))[0]
                if pd.notna(c) else float("nan")
            )
            base["temp_normal_c"] = base["cd_ibge"].map(
                lambda c: normais.get(int(c), (float("nan"), float("nan")))[1]
                if pd.notna(c) else float("nan")
            )
        procedencia["nasa_power"] = origem_normal

    # ------------------------------------------------------------- fogo
    fogo = obter_conector("queimadas_inpe", offline=offline)
    res_fogo = fogo.obter()
    procedencia["queimadas_inpe"] = res_fogo.origem
    if not res_fogo.vazio:
        por_mun = resumo_por_municipio(res_fogo.dados)
        if not por_mun.empty and "municipio" in base.columns:
            mapa_fogo = {
                str(m).upper(): int(n)
                for m, n in zip(por_mun["municipio"], por_mun["n_focos"])
            }
            base["focos_calor_24h"] = base["municipio"].map(
                lambda m: mapa_fogo.get(str(m).upper(), 0)
            )

    # ---------------------------------------------------------- seca oficial
    seca = obter_conector("monitor_secas", offline=offline)
    res_seca = seca.obter()
    procedencia["monitor_secas"] = res_seca.origem
    if not res_seca.vazio and "cd_ibge" in res_seca.dados.columns:
        mapa_seca = {
            int(c): str(k) for c, k in
            zip(res_seca.dados["cd_ibge"], res_seca.dados["classe"])
            if pd.notna(c)
        }
        base["classe_seca"] = base["cd_ibge"].map(
            lambda c: mapa_seca.get(int(c)) if pd.notna(c) else None
        )
        base["severidade_seca"] = base["classe_seca"].map(
            lambda k: severidade_oficial(k)["severidade"]
        )

    base["origem_contexto"] = "; ".join(
        f"{k}={v}" for k, v in sorted(procedencia.items())
    )
    extras = [c for c in base.columns if c not in COLUNAS_CONTEXTO]
    return base[COLUNAS_CONTEXTO + extras], procedencia


def enriquecer_alerta(
    *,
    cultura: str,
    regiao: str,
    uf: str,
    area_ha: float,
    perda_estimada_pct: float,
    dt_plantio: Any = None,
    chuva_prevista_mm: float | None = None,
    chuva_normal_mm: float | None = None,
    tem_proagro_pct: float = 0.0,
) -> dict[str, Any]:
    """
    Bloco de fatos externos anexado a um acionamento, pronto para entrar no
    contexto factual fechado do redator.

    Tudo aqui é **determinístico e conferível**: o LLM redige a partir destes
    números, nunca os inventa. Cada campo tem origem declarada, e campos sem
    fonte disponível saem vazios em vez de aproximados — a diferença entre
    uma mensagem que o produtor pode levar ao banco e uma que ele não pode.
    """
    cultura_baixa = (cultura or "").lower()
    rendimento = RENDIMENTO_REFERENCIA.get(cultura_baixa, 0.0)
    perda = valor_da_perda(cultura_baixa, area_ha, rendimento, perda_estimada_pct)
    zarc_info = avaliar_plantio(cultura, regiao, dt_plantio)
    protecao = classificar_protecao(tem_proagro_pct,
                                    PENETRACAO_UF.get(str(uf).upper(), 0.03))

    razao = anomalia_chuva(chuva_prevista_mm, chuva_normal_mm)

    return {
        "perda_estimada": perda,
        "zarc": zarc_info,
        "protecao_municipio": protecao,
        "anomalia_chuva": {
            "razao": razao,
            "classificacao": classificar_anomalia(razao),
            "normal_mm": chuva_normal_mm,
            "previsto_mm": chuva_prevista_mm,
        },
        "janela_zarc": janela_texto(cultura, regiao),
        "fontes": [
            "IBGE/PAM (rendimento)", "CONAB (preço)", "Zarc/MAPA (janela)",
            "PSR/MAPA (cobertura privada)", "NASA POWER (normal climática)",
        ],
    }
