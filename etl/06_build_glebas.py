#!/usr/bin/env python3
"""
ETL 06 — constrói o conjunto **glebas** a partir da geometria WKT do Sicor.

Por que esta etapa é a de maior ganho de precisão do projeto
-------------------------------------------------------------
Até aqui, cada operação era localizada no **centroide do município**. Em
municípios grandes isso é um erro enorme: em Ribas do Rio Pardo (MS) ou
Altamira (PA), a distância entre o centroide e uma lavoura na divisa passa
de 80 km — o suficiente para consultar uma frente de chuva que não é a que
está sobre a lavoura. Alerta errado destrói confiança mais rápido do que
alerta ausente.

``sicor_glebas_wkt_AAAA.gz`` publica o **polígono de cada gleba financiada**.
Com ele, a consulta climática passa a ser feita no centroide do talhão.

Entrada
-------
* ``sicor_glebas_wkt_AAAA.gz`` ou ``SICOR_GLEBAS_CONTRAT.gz`` — REF_BACEN,
  NU_ORDEM, NU_GLEBA, geometria em WKT e área declarada.
* ``SICOR_PROPRIEDADES.gz`` (opcional) — área total do imóvel e município.
* ``data/curated/carteira`` — para herdar cultura, UF e município.

Saída
-----
``data/curated/glebas.{parquet,csv.gz}`` no esquema ``GLEBAS_COLS``.

Conferência embutida
--------------------
A área calculada a partir do polígono é comparada com a área declarada no
Sicor. Divergência acima do limiar (padrão: 25%) é registrada e **contada no
relatório**: é um indicador de qualidade do dado, não um erro a esconder.

Uso:
    python etl/06_build_glebas.py --anos 2026
    python etl/06_build_glebas.py --contratado
    python etl/06_build_glebas.py --anos 2026 --amostra 500000
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
    carregar_curado,
    gravar,
    iniciar,
    ler_csv_em_blocos,
    log,
    para_numero,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from agrosentinela.data.schemas import GLEBAS_COLS, aplicar_esquema  # noqa: E402
from agrosentinela.external.ibge_malhas import (  # noqa: E402
    area_aproximada_ha,
    centroide_de_wkt,
)

MICRO = RAW_DIR / "microdados"

COLUNAS_WKT = ("REF_BACEN", "NU_ORDEM", "NU_GLEBA", "VL_AREA_GLEBA",
               "GEOMETRIA_WKT", "WKT", "GEOMETRIA", "CD_IBGE_MUNICIPIO")


def _coluna_geometria(df: pd.DataFrame) -> str | None:
    for nome in ("GEOMETRIA_WKT", "WKT", "GEOMETRIA", "GEOM"):
        if nome in df.columns:
            return nome
    # Último recurso: a coluna que mais parece conter WKT.
    for col in df.columns:
        amostra = df[col].dropna().astype(str).head(20)
        if any(s.upper().startswith(("POLYGON", "MULTIPOLYGON")) for s in amostra):
            return col
    return None


def _arquivos(anos: list[int], contratado: bool) -> list[Path]:
    caminhos: list[Path] = []
    for ano in anos:
        p = MICRO / f"sicor_glebas_wkt_{ano}.gz"
        if p.exists():
            caminhos.append(p)
        else:
            log.warning("Arquivo de glebas de %s não encontrado em %s", ano, MICRO)
    if contratado:
        p = MICRO / "SICOR_GLEBAS_CONTRAT.gz"
        if p.exists():
            caminhos.append(p)
        else:
            log.warning("SICOR_GLEBAS_CONTRAT.gz não encontrado.")
    return caminhos


def processar(caminho: Path, *, amostra: int | None,
              limiar_divergencia: float) -> tuple[pd.DataFrame, dict[str, int]]:
    """Lê um arquivo de glebas em blocos e devolve centroides e áreas."""
    linhas: list[dict] = []
    estat = {"lidas": 0, "sem_geometria": 0, "fora_do_brasil": 0, "divergentes": 0}
    lidas = 0

    for bloco in ler_csv_em_blocos(caminho):
        col_geo = _coluna_geometria(bloco)
        if col_geo is None:
            log.error("%s: nenhuma coluna de geometria reconhecida (%s)",
                      caminho.name, list(bloco.columns)[:12])
            break

        area_decl = (para_numero(bloco["VL_AREA_GLEBA"])
                     if "VL_AREA_GLEBA" in bloco.columns
                     else pd.Series([float("nan")] * len(bloco)))

        for i, (_, r) in enumerate(bloco.iterrows()):
            estat["lidas"] += 1
            wkt = r.get(col_geo)
            centro = centroide_de_wkt(wkt) if isinstance(wkt, str) else None
            if centro is None:
                if isinstance(wkt, str) and wkt.strip():
                    estat["fora_do_brasil"] += 1
                else:
                    estat["sem_geometria"] += 1
                continue
            lat, lon = centro
            a_decl = float(area_decl.iloc[i]) if i < len(area_decl) else float("nan")
            a_wkt = area_aproximada_ha(wkt)
            divergencia = 0.0
            if a_decl and a_decl > 0 and a_wkt > 0:
                divergencia = round(abs(a_wkt - a_decl) / a_decl * 100, 2)
                if divergencia > limiar_divergencia:
                    estat["divergentes"] += 1
            linhas.append({
                "ref_bacen": str(r.get("REF_BACEN") or "").strip(),
                "nu_ordem": pd.to_numeric(r.get("NU_ORDEM"), errors="coerce"),
                "nu_gleba": pd.to_numeric(r.get("NU_GLEBA"), errors="coerce"),
                "cd_ibge": pd.to_numeric(r.get("CD_IBGE_MUNICIPIO"), errors="coerce"),
                "lat": lat,
                "lon": lon,
                "area_gleba_ha": a_decl,
                "area_wkt_ha": a_wkt,
                "divergencia_area_pct": divergencia,
                "tem_geometria": True,
            })
        lidas += len(bloco)
        if amostra and lidas >= amostra:
            log.info("   amostra de %d linhas atingida em %s", amostra, caminho.name)
            break

    return pd.DataFrame(linhas), estat


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Constrói o conjunto de glebas georreferenciadas.")
    parser.add_argument("--anos", nargs="*", type=int, default=[2026])
    parser.add_argument("--contratado", action="store_true",
                        help="Inclui SICOR_GLEBAS_CONTRAT.gz (carteira viva).")
    parser.add_argument("--amostra", type=int, default=None,
                        help="Limita linhas lidas por arquivo.")
    parser.add_argument("--limiar-divergencia", type=float, default=25.0,
                        help="Divergência de área (%%) a partir da qual a gleba "
                             "é contada como suspeita no relatório.")
    parser.add_argument("--log", default="INFO")
    args = parser.parse_args(argv)

    iniciar(args.log)
    cabecalho("ETL 06 — Glebas georreferenciadas (WKT do Sicor)")

    caminhos = _arquivos(args.anos, args.contratado)
    if not caminhos:
        log.error("Nenhum arquivo de glebas disponível. Baixe com:")
        log.error("  python etl/01_download_microdados.py --glebas %s",
                  " ".join(str(a) for a in args.anos))
        return 1

    partes: list[pd.DataFrame] = []
    total_estat = {"lidas": 0, "sem_geometria": 0, "fora_do_brasil": 0,
                   "divergentes": 0}
    for caminho in caminhos:
        log.info("▶ %s", caminho.name)
        df, estat = processar(caminho, amostra=args.amostra,
                              limiar_divergencia=args.limiar_divergencia)
        for k, v in estat.items():
            total_estat[k] += v
        if not df.empty:
            partes.append(df)

    if not partes:
        log.error("Nenhuma gleba com geometria válida foi extraída.")
        return 1

    glebas = pd.concat(partes, ignore_index=True)
    glebas = glebas.drop_duplicates(subset=["ref_bacen", "nu_ordem", "nu_gleba"])

    # Herda cultura, município e UF da carteira curada.
    carteira = carregar_curado("carteira")
    if carteira is not None and not carteira.empty:
        chaves = ["ref_bacen", "nu_ordem"]
        cols = [c for c in ("cultura", "uf", "cd_ibge") if c in carteira.columns]
        ref = carteira[chaves + cols].drop_duplicates(subset=chaves)
        ref["ref_bacen"] = ref["ref_bacen"].astype(str)
        glebas["ref_bacen"] = glebas["ref_bacen"].astype(str)
        glebas = glebas.merge(ref, on=chaves, how="left", suffixes=("", "_cart"))
        # O município da carteira prevalece quando a gleba não o traz.
        if "cd_ibge_cart" in glebas.columns:
            glebas["cd_ibge"] = glebas["cd_ibge"].fillna(glebas["cd_ibge_cart"])
            glebas = glebas.drop(columns=["cd_ibge_cart"])
        ligadas = glebas["cultura"].notna().mean() if "cultura" in glebas else 0.0
        log.info("Ligação com a carteira: %.1f%% das glebas encontraram operação.",
                 100 * ligadas)
    else:
        log.warning("Carteira curada ausente — as glebas ficam sem cultura/UF. "
                    "Rode etl/02_build_carteira.py antes desta etapa.")

    glebas = aplicar_esquema(glebas, GLEBAS_COLS)
    gravar(glebas, "glebas")

    log.info("")
    log.info("Qualidade da geometria:")
    log.info("  linhas lidas .............. %d", total_estat["lidas"])
    log.info("  sem geometria ............. %d", total_estat["sem_geometria"])
    log.info("  coordenada fora do Brasil . %d", total_estat["fora_do_brasil"])
    log.info("  área divergente (> %.0f%%) ... %d",
             args.limiar_divergencia, total_estat["divergentes"])
    log.info("  glebas válidas gravadas ... %d", len(glebas))
    if total_estat["divergentes"]:
        log.info("  ↳ divergência de área não invalida a gleba: ela indica "
                 "que a área financiada e a área desenhada não coincidem, "
                 "informação útil para perícia e para subscrição.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
