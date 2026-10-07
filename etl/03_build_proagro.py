#!/usr/bin/env python3
"""
ETL 03 — constrói o **histórico de sinistralidade do Proagro**.

Entrada
-------
* ``SICOR_COP_BASICO.gz``       — pedidos de cobertura, com ``CD_EVENTO``
* ``SICOR_RCP_BASICO.gz``       — comprovações de perdas, com ``CD_EVENTO``
* ``SICOR_COMPLEMENTO_COP.gz``  — evento complementar do pedido
* ``SICOR_COMPLEMENTO_RCP.gz``  — evento complementar da comprovação
* ``EventoProagro.csv``         — vocabulário oficial dos eventos
* ``data/curated/carteira``     — município, UF e cultura de cada operação

Saída
-----
``data/curated/proagro_sinistros.{parquet,csv.gz}``: agregado por
município × cultura × evento, com participação do evento, taxa de
acionamento e valor indenizado. É essa tabela que alimenta o componente
histórico do score e a regra R-HIS-01.

Uso:
    python etl/03_build_proagro.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _comum import (  # noqa: E402
    RAW_DIR,
    cabecalho,
    carregar_curado,
    gravar,
    iniciar,
    ler_csv,
    ler_csv_em_blocos,
    log,
    normalizar_texto,
    para_data,
    para_numero,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from agrosentinela.data.schemas import SINISTROS_COLS, aplicar_esquema  # noqa: E402
from agrosentinela.rules.catalogo import mapear_evento_proagro  # noqa: E402

DOMINIOS = RAW_DIR / "dominios"
MICRO = RAW_DIR / "microdados"


# ==========================================================================
def carregar_eventos() -> tuple[dict[str, str], dict[str, str]]:
    """
    Devolve dois mapas:

    * ``codigo -> rótulo oficial do BCB``
    * ``codigo -> código interno do AgroSentinela``
    """
    caminho = DOMINIOS / "EventoProagro.csv"
    if not caminho.exists():
        log.warning("EventoProagro.csv ausente — os eventos ficarão sem rótulo.")
        return {}, {}
    df = ler_csv(caminho)
    col_cod = next((c for c in df.columns if "EVENTO" in c and c.startswith("CD")), None)
    col_nome = next((c for c in df.columns
                     if "NOME" in c or "DESCRICAO" in c or c == "EVENTO"), None)
    if not col_cod or not col_nome:
        log.warning("EventoProagro.csv: colunas não localizadas (%s)", list(df.columns))
        return {}, {}

    codigos = df[col_cod].astype(str).str.strip().str.lstrip("0")
    nomes = normalizar_texto(df[col_nome])
    rotulos = dict(zip(codigos, nomes))
    internos = {c: (mapear_evento_proagro(n) or "outro") for c, n in rotulos.items()}

    nao_mapeados = sorted({rotulos[c] for c, i in internos.items() if i == "outro"})
    log.info("Eventos do Proagro: %d códigos; %d mapeados para o catálogo interno.",
             len(rotulos), sum(1 for v in internos.values() if v != "outro"))
    if nao_mapeados:
        log.info("   sem correspondência interna: %s", ", ".join(nao_mapeados[:12]))
    return rotulos, internos


def carregar_eventos_complementares(nome_arquivo: str) -> pd.DataFrame:
    """Evento declarado nos arquivos de complemento (COP/RCP)."""
    caminho = MICRO / nome_arquivo
    if not caminho.exists():
        return pd.DataFrame(columns=["REF_BACEN", "NU_ORDEM", "CD_EVENTO"])
    partes = []
    for bloco in ler_csv_em_blocos(caminho, colunas=["REF_BACEN", "NU_ORDEM", "CD_EVENTO"]):
        if "CD_EVENTO" in bloco.columns:
            partes.append(bloco)
    if not partes:
        return pd.DataFrame(columns=["REF_BACEN", "NU_ORDEM", "CD_EVENTO"])
    return pd.concat(partes, ignore_index=True)


def carregar_tabela_proagro(nome_arquivo: str, colunas: list[str]) -> pd.DataFrame:
    caminho = MICRO / nome_arquivo
    if not caminho.exists():
        log.warning("%s ausente.", nome_arquivo)
        return pd.DataFrame()
    log.info("Processando %s…", nome_arquivo)
    partes = [bloco for bloco in ler_csv_em_blocos(caminho, colunas=colunas)]
    if not partes:
        return pd.DataFrame()
    df = pd.concat(partes, ignore_index=True)
    log.info("   %d registros", len(df))
    return df


# ==========================================================================
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Constrói o histórico de sinistralidade do Proagro."
    )
    parser.add_argument("--ano-inicio", type=int, default=2013)
    parser.add_argument("--log", default="INFO")
    args = parser.parse_args(argv)

    iniciar(args.log)
    cabecalho("ETL 03 — Histórico de acionamento do Proagro (COP e RCP)")

    carteira = carregar_curado("carteira")
    if carteira is None or carteira.empty:
        log.error("Carteira curada ausente. Execute antes: python etl/02_build_carteira.py")
        return 1

    rotulos, internos = carregar_eventos()

    cop = carregar_tabela_proagro(
        "SICOR_COP_BASICO.gz",
        ["REF_BACEN", "NU_ORDEM", "DT_COMUNICACAO", "CD_STATUS", "CD_EVENTO"],
    )
    rcp = carregar_tabela_proagro(
        "SICOR_RCP_BASICO.gz",
        ["REF_BACEN", "NU_ORDEM", "DT_ENTREGA", "CD_STATUS", "CD_EVENTO",
         "VL_AREA", "VL_PREV_PROD", "VL_REC_PREV"],
    )
    if cop.empty and rcp.empty:
        log.error("Nenhum dado de Proagro encontrado. Baixe com: "
                  "python etl/01_download_microdados.py")
        return 1

    # Completa o evento a partir dos arquivos de complemento, quando faltar.
    for base, complemento in ((cop, "SICOR_COMPLEMENTO_COP.gz"),
                              (rcp, "SICOR_COMPLEMENTO_RCP.gz")):
        if base.empty:
            continue
        faltando = "CD_EVENTO" not in base.columns or base["CD_EVENTO"].isna().mean() > 0.3
        if not faltando:
            continue
        extra = carregar_eventos_complementares(complemento)
        if extra.empty:
            continue
        base_chaves = base[["REF_BACEN", "NU_ORDEM"]].astype(str)
        extra[["REF_BACEN", "NU_ORDEM"]] = extra[["REF_BACEN", "NU_ORDEM"]].astype(str)
        juncao = base_chaves.merge(extra, on=["REF_BACEN", "NU_ORDEM"], how="left")
        base["CD_EVENTO"] = base.get("CD_EVENTO", pd.Series(index=base.index, dtype=str)).fillna(
            juncao["CD_EVENTO"]
        )
        log.info("   evento completado a partir de %s", complemento)

    # ------------------------------------------------------------------
    # Chave de junção com a carteira: município, UF e cultura
    # ------------------------------------------------------------------
    chave_carteira = carteira[["ref_bacen", "nu_ordem", "cd_ibge", "uf", "cultura"]].copy()
    chave_carteira["ref_bacen"] = chave_carteira["ref_bacen"].astype(str).str.strip()
    chave_carteira["nu_ordem"] = chave_carteira["nu_ordem"].astype(str).str.strip()

    def enriquecer(df: pd.DataFrame, rotulo: str) -> pd.DataFrame:
        if df.empty:
            return df
        out = df.copy()
        out["REF_BACEN"] = out["REF_BACEN"].astype(str).str.strip()
        out["NU_ORDEM"] = out["NU_ORDEM"].astype(str).str.strip()
        out = out.merge(
            chave_carteira,
            left_on=["REF_BACEN", "NU_ORDEM"],
            right_on=["ref_bacen", "nu_ordem"],
            how="inner",
        )
        cod = out.get("CD_EVENTO", pd.Series(index=out.index, dtype=str))
        cod = cod.astype(str).str.strip().str.lstrip("0")
        out["evento_proagro"] = cod.map(rotulos).fillna("NAO INFORMADO")
        out["evento"] = cod.map(internos).fillna("outro")
        log.info("   %s cruzado com a carteira: %d registros (%.1f%% com evento mapeado)",
                 rotulo, len(out), 100 * (out["evento"] != "outro").mean() if len(out) else 0)
        return out

    cop_e = enriquecer(cop, "COP")
    rcp_e = enriquecer(rcp, "RCP")

    if cop_e.empty and rcp_e.empty:
        log.warning(
            "Nenhum registro de Proagro cruzou com a carteira. Isso acontece "
            "quando a carteira cobre apenas anos recentes e os pedidos são "
            "antigos. Amplie os anos em etl/02_build_carteira.py."
        )

    # ------------------------------------------------------------------
    # Agregação
    # ------------------------------------------------------------------
    grupos = ["cd_ibge", "uf", "cultura", "evento", "evento_proagro"]

    agg_cop = (
        cop_e.groupby(grupos, as_index=False).agg(n_cop=("REF_BACEN", "count"))
        if not cop_e.empty else pd.DataFrame(columns=grupos + ["n_cop"])
    )
    if not rcp_e.empty:
        rcp_e["valor_indenizado"] = para_numero(rcp_e.get("VL_REC_PREV")).fillna(0.0)
        agg_rcp = rcp_e.groupby(grupos, as_index=False).agg(
            n_rcp=("REF_BACEN", "count"),
            valor_indenizado=("valor_indenizado", "sum"),
        )
    else:
        agg_rcp = pd.DataFrame(columns=grupos + ["n_rcp", "valor_indenizado"])

    sinistros = agg_cop.merge(agg_rcp, on=grupos, how="outer")
    sinistros[["n_cop", "n_rcp", "valor_indenizado"]] = (
        sinistros[["n_cop", "n_rcp", "valor_indenizado"]].fillna(0)
    )

    # Universo de operações por município/cultura, para calcular a taxa
    universo = (
        carteira.groupby(["cd_ibge", "cultura"], as_index=False)
        .agg(n_operacoes=("ref_bacen", "count"))
    )
    sinistros = sinistros.merge(universo, on=["cd_ibge", "cultura"], how="left")
    sinistros["n_operacoes"] = sinistros["n_operacoes"].fillna(0).astype("int64")

    total_muni = sinistros.groupby(["cd_ibge", "cultura"])["n_cop"].transform("sum")
    sinistros["freq_evento"] = (
        sinistros["n_cop"] / total_muni.replace(0, np.nan)
    ).fillna(0.0).round(4)
    sinistros["taxa_acionamento"] = (
        sinistros["n_cop"] / sinistros["n_operacoes"].replace(0, np.nan)
    ).fillna(0.0).round(4)
    sinistros["ano_inicio"] = args.ano_inicio
    sinistros["ano_fim"] = pd.Timestamp.today().year
    sinistros["fonte"] = "bcb_sicor"

    final = aplicar_esquema(sinistros, SINISTROS_COLS)
    gravar(final, "proagro_sinistros")

    # ------------------------------------------------------------ relatório
    log.info("")
    log.info("Resumo do histórico do Proagro")
    log.info("  combinações município×cultura×evento .. %d", len(final))
    log.info("  pedidos de cobertura (COP) ............ %d", int(final["n_cop"].sum()))
    log.info("  comprovações de perdas (RCP) .......... %d", int(final["n_rcp"].sum()))
    log.info("  municípios com registro ............... %d", final["cd_ibge"].nunique())
    if final["n_cop"].sum():
        log.info("")
        log.info("Participação por evento:")
        por_evento = final.groupby("evento")["n_cop"].sum().sort_values(ascending=False)
        for evento, n in por_evento.items():
            log.info("    %-20s %8d  (%.1f%%)", evento, int(n),
                     100 * n / final["n_cop"].sum())

    # ------------------------------------------------------ série de crédito
    serie = (
        carteira.assign(ano=carteira["dt_emissao"].dt.year)
        .dropna(subset=["ano"])
        .groupby(["ano", "uf", "cultura"], as_index=False)
        .agg(n_operacoes=("ref_bacen", "count"),
             valor_credito=("valor_credito", "sum"),
             area_ha=("area_ha", "sum"))
    )
    if not serie.empty:
        serie["ano"] = serie["ano"].astype("int64")
        from agrosentinela.data.schemas import SERIE_COLS

        gravar(aplicar_esquema(serie, SERIE_COLS), "serie_credito")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
