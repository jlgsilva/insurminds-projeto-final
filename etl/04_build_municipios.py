#!/usr/bin/env python3
"""
ETL 04 — constrói a tabela de **municípios**.

Combina três fontes:

1. ``MunicipiosSicor.csv`` (BCB) — código IBGE, nome e UF de todos os
   municípios utilizados no Sicor;
2. ``AliquotaBaseProagro.csv`` (BCB) — alíquota básica do Proagro por
   município;
3. **centroides geográficos** — necessários para consultar a previsão do
   tempo. Tentados nesta ordem:
   a) arquivo local ``data/raw/municipios_centroides.csv`` (se você já tiver),
   b) base pública de municípios brasileiros com latitude e longitude,
   c) amostra embarcada no projeto (cobertura parcial).

Uso:
    python etl/04_build_municipios.py
    python etl/04_build_municipios.py --centroides caminho/para/municipios.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _comum import (  # noqa: E402
    RAW_DIR,
    cabecalho,
    gravar,
    iniciar,
    ler_csv,
    log,
    normalizar_coluna,
    normalizar_texto,
    para_numero,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from agrosentinela.data.municipios_seed import (  # noqa: E402
    UF_BBOX,
    UF_REGIAO,
    municipios_seed,
    validar_coordenadas,
)
from agrosentinela.data.schemas import MUNICIPIOS_COLS, aplicar_esquema  # noqa: E402

DOMINIOS = RAW_DIR / "dominios"

# Base pública consolidada de municípios brasileiros com coordenadas.
URL_CENTROIDES = (
    "https://raw.githubusercontent.com/kelvins/municipios-brasileiros/"
    "main/csv/municipios.csv"
)

UF_POR_CODIGO = {
    11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO",
    21: "MA", 22: "PI", 23: "CE", 24: "RN", 25: "PB", 26: "PE", 27: "AL",
    28: "SE", 29: "BA", 31: "MG", 32: "ES", 33: "RJ", 35: "SP", 41: "PR",
    42: "SC", 43: "RS", 50: "MS", 51: "MT", 52: "GO", 53: "DF",
}


# ==========================================================================
def carregar_municipios_sicor() -> pd.DataFrame | None:
    caminho = DOMINIOS / "MunicipiosSicor.csv"
    if not caminho.exists():
        log.warning("MunicipiosSicor.csv não encontrado em %s", DOMINIOS)
        return None
    df = ler_csv(caminho)
    log.info("MunicipiosSicor.csv: %d linhas, colunas %s", len(df), list(df.columns))

    # O BCB já variou os nomes; aceitamos os apelidos mais comuns.
    apelidos = {
        "cd_ibge": ["CD_IBGE", "CD_MUNICIPIO_IBGE", "CODIGO_IBGE", "CD_IBGE_MUNICIPIO",
                    "COD_IBGE", "CD_MUNICIPIO"],
        "municipio": ["NOME", "NO_MUNICIPIO", "MUNICIPIO", "DESCRICAO", "NOME_MUNICIPIO"],
        "uf": ["UF", "SG_UF", "SIGLA_UF", "ESTADO"],
    }
    saida = pd.DataFrame()
    for destino, candidatos in apelidos.items():
        for c in candidatos:
            if c in df.columns:
                saida[destino] = df[c]
                break
    if "cd_ibge" not in saida.columns:
        log.error("Não foi possível localizar o código IBGE em MunicipiosSicor.csv.")
        return None

    saida["cd_ibge"] = pd.to_numeric(
        saida["cd_ibge"].astype(str).str.extract(r"(\d+)")[0], errors="coerce"
    )
    saida = saida.dropna(subset=["cd_ibge"])
    saida["cd_ibge"] = saida["cd_ibge"].astype("int64")
    if "municipio" in saida.columns:
        saida["municipio"] = normalizar_texto(saida["municipio"]).str.title()
    if "uf" not in saida.columns:
        saida["uf"] = (saida["cd_ibge"] // 100000).map(UF_POR_CODIGO)
    saida["uf"] = saida["uf"].astype(str).str.upper().str.strip()
    return saida.drop_duplicates(subset=["cd_ibge"])


def carregar_aliquotas() -> pd.DataFrame | None:
    caminho = DOMINIOS / "AliquotaBaseProagro.csv"
    if not caminho.exists():
        log.warning("AliquotaBaseProagro.csv não encontrado — alíquotas ficarão vazias.")
        return None
    df = ler_csv(caminho)
    log.info("AliquotaBaseProagro.csv: %d linhas, colunas %s", len(df), list(df.columns))

    col_ibge = next((c for c in df.columns if "IBGE" in c or "MUNICIP" in c), None)
    col_aliq = next((c for c in df.columns if "ALIQ" in c or "TAXA" in c or "PERC" in c), None)
    if not col_ibge or not col_aliq:
        log.warning("Colunas de município/alíquota não identificadas em AliquotaBaseProagro.csv.")
        return None

    saida = pd.DataFrame({
        "cd_ibge": pd.to_numeric(
            df[col_ibge].astype(str).str.extract(r"(\d+)")[0], errors="coerce"
        ),
        "aliquota_proagro": para_numero(df[col_aliq]),
    }).dropna(subset=["cd_ibge"])
    saida["cd_ibge"] = saida["cd_ibge"].astype("int64")
    return saida.groupby("cd_ibge", as_index=False)["aliquota_proagro"].mean()


def carregar_centroides(caminho_local: Path | None) -> pd.DataFrame | None:
    """Centroides por código IBGE, de arquivo local ou da base pública."""
    candidatos: list[Path | str] = []
    if caminho_local:
        candidatos.append(caminho_local)
    candidatos.append(RAW_DIR / "municipios_centroides.csv")
    candidatos.append(URL_CENTROIDES)

    for origem in candidatos:
        try:
            if isinstance(origem, Path):
                if not origem.exists():
                    continue
                df = pd.read_csv(origem, dtype=str)
                rotulo = str(origem)
            else:
                log.info("Baixando centroides de %s", origem)
                df = pd.read_csv(origem, dtype=str)
                rotulo = origem
                # Guarda uma cópia local para próximas execuções
                try:
                    df.to_csv(RAW_DIR / "municipios_centroides.csv", index=False)
                except OSError:
                    pass
            df.columns = [normalizar_coluna(c) for c in df.columns]
            col_ibge = next((c for c in df.columns
                             if c in ("CODIGO_IBGE", "CD_IBGE", "IBGE", "COD_IBGE", "ID")), None)
            col_lat = next((c for c in df.columns if c.startswith("LAT")), None)
            col_lon = next((c for c in df.columns
                            if c.startswith("LON") or c.startswith("LNG")), None)
            if not (col_ibge and col_lat and col_lon):
                log.warning("Centroides em %s sem colunas reconhecíveis (%s)",
                            rotulo, list(df.columns)[:10])
                continue
            saida = pd.DataFrame({
                "cd_ibge": pd.to_numeric(df[col_ibge], errors="coerce"),
                "lat": pd.to_numeric(df[col_lat].astype(str).str.replace(",", "."),
                                     errors="coerce"),
                "lon": pd.to_numeric(df[col_lon].astype(str).str.replace(",", "."),
                                     errors="coerce"),
            }).dropna()
            saida["cd_ibge"] = saida["cd_ibge"].astype("int64")
            log.info("Centroides carregados de %s: %d municípios", rotulo, len(saida))
            return saida
        except Exception as exc:  # noqa: BLE001
            log.warning("Centroides de %s indisponíveis: %s", origem, exc)
    return None


# ==========================================================================
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Constrói a tabela curada de municípios.")
    parser.add_argument("--centroides", type=Path, default=None,
                        help="CSV local com codigo_ibge, latitude e longitude.")
    parser.add_argument("--log", default="INFO")
    args = parser.parse_args(argv)

    iniciar(args.log)
    cabecalho("ETL 04 — Municípios (geografia + alíquota do Proagro)")

    sicor = carregar_municipios_sicor()
    if sicor is None or sicor.empty:
        log.warning("Sem MunicipiosSicor.csv: usando a amostra embarcada como base.")
        base = municipios_seed()[["cd_ibge", "municipio", "uf"]].copy()
    else:
        base = sicor

    base["regiao"] = base["uf"].map(UF_REGIAO)

    centroides = carregar_centroides(args.centroides)
    if centroides is not None:
        base = base.merge(centroides, on="cd_ibge", how="left")
    else:
        base["lat"], base["lon"] = pd.NA, pd.NA

    # Preenche o que faltar com a amostra embarcada
    seed = municipios_seed()[["cd_ibge", "lat", "lon", "polo_agricola"]]
    base = base.merge(seed, on="cd_ibge", how="left", suffixes=("", "_seed"))
    for col in ("lat", "lon"):
        if f"{col}_seed" in base.columns:
            base[col] = pd.to_numeric(base[col], errors="coerce").fillna(
                pd.to_numeric(base[f"{col}_seed"], errors="coerce")
            )
            base = base.drop(columns=[f"{col}_seed"])

    aliquotas = carregar_aliquotas()
    if aliquotas is not None:
        base = base.merge(aliquotas, on="cd_ibge", how="left")
    else:
        base["aliquota_proagro"] = pd.NA

    base["fonte"] = "bcb_sicor"
    base["polo_agricola"] = base.get("polo_agricola", pd.Series(dtype=str)).fillna("")

    sem_geo = int(base["lat"].isna().sum())
    if sem_geo:
        log.warning("%d municípios (%.1f%%) ficaram sem coordenada — não receberão "
                    "consulta meteorológica.", sem_geo, 100 * sem_geo / max(len(base), 1))

    com_geo = base.dropna(subset=["lat", "lon"])
    problemas = validar_coordenadas(com_geo)
    if not problemas.empty:
        log.warning("%d coordenadas fora do limite aproximado da UF:", len(problemas))
        log.warning("\n%s", problemas.head(10).to_string(index=False))

    final = aplicar_esquema(base, MUNICIPIOS_COLS)
    gravar(final, "municipios")

    log.info("")
    log.info("Municípios: %d (%d com coordenada, %d com alíquota do Proagro)",
             len(final), len(com_geo), int(final["aliquota_proagro"].notna().sum()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
