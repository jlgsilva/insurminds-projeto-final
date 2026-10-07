#!/usr/bin/env python3
"""
ETL 07 — constrói o conjunto **exposicao**: a posição financeira da carteira.

O que muda com esta etapa
-------------------------
Sem ela, o AgroSentinela fala em hectares. Com ela, fala em reais — e reais
é a única unidade em que gerente de crédito, atuário, gestor de política
pública e o próprio produtor conversam entre si. A mesma geada que "atinge
2.300 ha de trigo" passa a "alcançar R$ 41 milhões de saldo devedor, dos
quais R$ 6,2 milhões em operações já vencidas".

Entrada
-------
* ``SICOR_SALDOS_AAAA.gz`` — saldo devedor e vencido por posição.
* ``SICOR_LIBERACAO_RECURSOS.gz`` — quanto já foi desembolsado.
* ``SICOR_PARCELAS_DESEMBOLSO.gz`` — cronograma futuro de liberação.
* ``SICOR_LISTA_RENEGOCIACAO.gz`` — operações já renegociadas.
* ``data/curated/carteira`` — para herdar município e UF.

Saída
-----
``data/curated/exposicao.{parquet,csv.gz}`` no esquema ``EXPOSICAO_COLS``.

Nota sobre a posição
--------------------
O arquivo de saldos traz **várias posições por operação** (uma por mês).
Esta etapa mantém, por padrão, apenas a **posição mais recente** de cada
operação: é ela que representa o risco de hoje. A série completa fica
disponível com ``--todas-posicoes`` para análise de tendência.

Uso:
    python etl/07_build_exposicao.py --anos 2026
    python etl/07_build_exposicao.py --anos 2025 2026 --todas-posicoes
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
    ler_csv,
    ler_csv_em_blocos,
    log,
    para_data,
    para_numero,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from agrosentinela.data.schemas import EXPOSICAO_COLS, aplicar_esquema  # noqa: E402

MICRO = RAW_DIR / "microdados"

FAIXAS: tuple[tuple[int, str], ...] = (
    (0, "em dia"), (15, "1 a 15 dias"), (30, "16 a 30 dias"),
    (90, "31 a 90 dias"), (180, "91 a 180 dias"),
)


def faixa_atraso(dias: float) -> str:
    try:
        d = int(dias)
    except (TypeError, ValueError):
        return "em dia"
    for limite, rotulo in FAIXAS:
        if d <= limite:
            return rotulo
    return "acima de 180 dias"


def _primeiro(df: pd.DataFrame, *nomes: str) -> pd.Series | None:
    for nome in nomes:
        if nome in df.columns:
            return df[nome]
    return None


def ler_saldos(anos: list[int], *, todas_posicoes: bool,
               amostra: int | None) -> pd.DataFrame:
    partes: list[pd.DataFrame] = []
    for ano in anos:
        caminho = MICRO / f"SICOR_SALDOS_{ano}.gz"
        if not caminho.exists():
            log.warning("Saldos de %s não encontrados (%s).", ano, caminho.name)
            continue
        log.info("▶ %s", caminho.name)
        lidas = 0
        for bloco in ler_csv_em_blocos(caminho):
            dados = pd.DataFrame({
                "ref_bacen": bloco.get("REF_BACEN", pd.Series(dtype=str)).astype(str).str.strip(),
                "nu_ordem": pd.to_numeric(bloco.get("NU_ORDEM"), errors="coerce"),
                "dt_posicao": para_data(_primeiro(bloco, "DT_POSICAO", "DT_BASE",
                                                  "DT_REFERENCIA")),
                "saldo_devedor": para_numero(_primeiro(
                    bloco, "VL_SALDO_DEVEDOR", "VL_SALDO", "VL_SLD_DEVEDOR")),
                "saldo_vencido": para_numero(_primeiro(
                    bloco, "VL_SALDO_VENCIDO", "VL_VENCIDO", "VL_SLD_VENCIDO")),
                "dias_em_atraso": pd.to_numeric(_primeiro(
                    bloco, "QT_DIAS_ATRASO", "NU_DIAS_ATRASO"), errors="coerce"),
            })
            partes.append(dados.dropna(subset=["ref_bacen"]))
            lidas += len(bloco)
            if amostra and lidas >= amostra:
                break
    if not partes:
        return pd.DataFrame()

    saldos = pd.concat(partes, ignore_index=True)
    if not todas_posicoes and "dt_posicao" in saldos.columns:
        antes = len(saldos)
        saldos = (saldos.sort_values("dt_posicao")
                        .drop_duplicates(subset=["ref_bacen", "nu_ordem"], keep="last"))
        log.info("Posições: %d linhas -> %d operações (mantida a mais recente).",
                 antes, len(saldos))
    return saldos


def ler_liberacao(amostra: int | None) -> pd.DataFrame:
    caminho = MICRO / "SICOR_LIBERACAO_RECURSOS.gz"
    if not caminho.exists():
        log.info("Liberação de recursos ausente — 'valor_liberado' ficará vazio.")
        return pd.DataFrame()
    log.info("▶ %s", caminho.name)
    partes, lidas = [], 0
    for bloco in ler_csv_em_blocos(caminho):
        partes.append(pd.DataFrame({
            "ref_bacen": bloco.get("REF_BACEN", pd.Series(dtype=str)).astype(str).str.strip(),
            "nu_ordem": pd.to_numeric(bloco.get("NU_ORDEM"), errors="coerce"),
            "valor_liberado": para_numero(_primeiro(
                bloco, "VL_LIBERACAO", "VL_PARC_LIBERADA", "VL_VALOR")),
        }))
        lidas += len(bloco)
        if amostra and lidas >= amostra:
            break
    if not partes:
        return pd.DataFrame()
    return (pd.concat(partes, ignore_index=True)
              .groupby(["ref_bacen", "nu_ordem"], as_index=False)["valor_liberado"].sum())


def ler_parcelas(amostra: int | None) -> pd.DataFrame:
    caminho = MICRO / "SICOR_PARCELAS_DESEMBOLSO.gz"
    if not caminho.exists():
        log.info("Cronograma de desembolso ausente — 'proxima_parcela' ficará vazia.")
        return pd.DataFrame()
    log.info("▶ %s", caminho.name)
    hoje = pd.Timestamp.today().normalize()
    partes, lidas = [], 0
    for bloco in ler_csv_em_blocos(caminho):
        dados = pd.DataFrame({
            "ref_bacen": bloco.get("REF_BACEN", pd.Series(dtype=str)).astype(str).str.strip(),
            "nu_ordem": pd.to_numeric(bloco.get("NU_ORDEM"), errors="coerce"),
            "data_parcela": para_data(_primeiro(
                bloco, "DT_PARCELA", "DT_VENCIMENTO", "DT_PREVISAO")),
            "valor_parcela": para_numero(_primeiro(
                bloco, "VL_PARCELA", "VL_PREVISTO", "VL_VALOR")),
        })
        partes.append(dados[dados["data_parcela"] >= hoje])
        lidas += len(bloco)
        if amostra and lidas >= amostra:
            break
    if not partes:
        return pd.DataFrame()
    futuras = pd.concat(partes, ignore_index=True)
    if futuras.empty:
        return pd.DataFrame()
    agregado = futuras.groupby(["ref_bacen", "nu_ordem"], as_index=False).agg(
        proxima_parcela=("data_parcela", "min"),
        valor_a_liberar=("valor_parcela", "sum"),
    )
    return agregado


def ler_renegociadas() -> set[tuple[str, float]]:
    caminho = MICRO / "SICOR_LISTA_RENEGOCIACAO.gz"
    if not caminho.exists():
        log.info("Lista de renegociação ausente — 'renegociada' ficará em falso.")
        return set()
    log.info("▶ %s", caminho.name)
    try:
        df = ler_csv(caminho, colunas=["REF_BACEN", "NU_ORDEM"])
    except Exception as exc:  # noqa: BLE001
        log.warning("Falha ao ler a lista de renegociação: %s", exc)
        return set()
    if df.empty:
        return set()
    return {
        (str(r).strip(), float(o) if pd.notna(o) else 0.0)
        for r, o in zip(df.get("REF_BACEN", []),
                        pd.to_numeric(df.get("NU_ORDEM"), errors="coerce"))
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Constrói a exposição financeira da carteira.")
    parser.add_argument("--anos", nargs="*", type=int, default=[2026])
    parser.add_argument("--todas-posicoes", action="store_true",
                        help="Mantém todas as posições mensais, não só a última.")
    parser.add_argument("--amostra", type=int, default=None)
    parser.add_argument("--log", default="INFO")
    args = parser.parse_args(argv)

    iniciar(args.log)
    cabecalho("ETL 07 — Exposição financeira (saldos, liberação, renegociação)")

    saldos = ler_saldos(args.anos, todas_posicoes=args.todas_posicoes,
                        amostra=args.amostra)
    if saldos.empty:
        log.error("Nenhum arquivo de saldos disponível. Baixe com:")
        log.error("  python etl/01_download_microdados.py --saldos %s",
                  " ".join(str(a) for a in args.anos))
        return 1

    liberacao = ler_liberacao(args.amostra)
    parcelas = ler_parcelas(args.amostra)
    renegociadas = ler_renegociadas()

    exposicao = saldos
    for extra in (liberacao, parcelas):
        if extra is not None and not extra.empty:
            exposicao = exposicao.merge(extra, on=["ref_bacen", "nu_ordem"],
                                        how="left")

    exposicao["renegociada"] = [
        (r, o if pd.notna(o) else 0.0) in renegociadas
        for r, o in zip(exposicao["ref_bacen"], exposicao["nu_ordem"])
    ]

    # Município e UF vêm da carteira — a tabela de saldos não os traz.
    carteira = carregar_curado("carteira")
    if carteira is not None and not carteira.empty:
        ref = (carteira[["ref_bacen", "nu_ordem", "cd_ibge", "uf"]]
               .drop_duplicates(subset=["ref_bacen", "nu_ordem"]))
        ref["ref_bacen"] = ref["ref_bacen"].astype(str)
        exposicao = exposicao.merge(ref, on=["ref_bacen", "nu_ordem"], how="left")
        cobertura = exposicao["cd_ibge"].notna().mean()
        log.info("Ligação com a carteira: %.1f%% das posições encontraram operação.",
                 100 * cobertura)
        if cobertura < 0.5:
            log.warning("Menos da metade dos saldos casou com a carteira. "
                        "Confirme que os anos de saldo e de operação coincidem.")
    else:
        log.warning("Carteira curada ausente — a exposição fica sem município/UF.")

    exposicao["dias_em_atraso"] = exposicao["dias_em_atraso"].fillna(0)
    exposicao["faixa_atraso"] = exposicao["dias_em_atraso"].map(faixa_atraso)

    exposicao = aplicar_esquema(exposicao, EXPOSICAO_COLS)
    gravar(exposicao, "exposicao")

    total = float(exposicao["saldo_devedor"].sum())
    vencido = float(exposicao["saldo_vencido"].sum())
    log.info("")
    log.info("Posição consolidada:")
    log.info("  operações ................. %d", len(exposicao))
    log.info("  saldo devedor ............. R$ %.1f milhões", total / 1e6)
    log.info("  saldo vencido ............. R$ %.1f milhões (%.2f%%)",
             vencido / 1e6, 100 * vencido / total if total else 0.0)
    log.info("  renegociadas .............. %d (%.2f%%)",
             int(exposicao["renegociada"].sum()),
             100 * exposicao["renegociada"].mean() if len(exposicao) else 0.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
