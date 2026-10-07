#!/usr/bin/env python3
"""
ETL 02 — constrói a **carteira** curada a partir dos microdados do Sicor.

Entrada
-------
* ``SICOR_OPERACAO_BASICA_ESTADO_AAAA.gz`` — uma linha por operação:
  datas do ciclo, valor, área, empreendimento, cobertura, irrigação.
* ``SICOR_COMPLEMENTO_OPERACAO_BASICA.gz`` — traz ``CD_IBGE_MUNICIPIO``,
  que é o que permite georreferenciar a operação.
* tabelas de domínio — decodificam empreendimento, programa, categoria de
  emitente, fonte de recursos, tipo de seguro e instituição financeira.
* ``data/curated/municipios`` — centroides (gerado pelo ETL 04).

Saída
-----
``data/curated/carteira.{parquet,csv.gz}`` no esquema canônico
(``agrosentinela.data.schemas.CARTEIRA_COLS``).

Processamento em blocos: os arquivos anuais têm milhões de linhas, então o
script lê em pedaços, filtra as operações vigentes e só então junta.

Uso:
    python etl/02_build_carteira.py --anos 2025 2026
    python etl/02_build_carteira.py --anos 2026 --amostra 200000
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
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
from agrosentinela.data.schemas import CARTEIRA_COLS, aplicar_esquema  # noqa: E402
from agrosentinela.personas import inferir_persona_do_mutuario  # noqa: E402
from agrosentinela.rules.catalogo import mapear_produto_para_cultura  # noqa: E402

DOMINIOS = RAW_DIR / "dominios"
MICRO = RAW_DIR / "microdados"

COLUNAS_OPERACAO = [
    "REF_BACEN", "NU_ORDEM", "CNPJ_IF", "DT_EMISSAO", "DT_VENCIMENTO",
    "CD_CATEG_EMITENTE", "CD_FONTE_RECURSO", "CD_ESTADO", "CD_TIPO_SEGURO",
    "CD_EMPREENDIMENTO", "CD_PROGRAMA", "CD_TIPO_IRRIGACAO", "VL_ALIQ_PROAGRO",
    "VL_PREV_PROD", "VL_RECEITA_BRUTA_ESPERADA", "VL_PARC_CREDITO",
    "VL_AREA_FINANC", "VL_AREA_INFORMADA", "DT_FIM_COLHEITA", "DT_FIM_PLANTIO",
    "DT_INIC_COLHEITA", "DT_INIC_PLANTIO", "CD_SUBPROGRAMA", "CD_CICLO_CULTIVAR",
]


# ==========================================================================
# Tabelas de domínio
# ==========================================================================

def _mapa(nome_arquivo: str, col_chave: list[str], col_valor: list[str]) -> dict[str, str]:
    caminho = DOMINIOS / nome_arquivo
    if not caminho.exists():
        log.warning("Domínio ausente: %s", nome_arquivo)
        return {}
    df = ler_csv(caminho)
    chave = next((c for c in col_chave if c in df.columns), None)
    valor = next((c for c in col_valor if c in df.columns), None)
    if not chave or not valor:
        log.warning("%s: colunas não localizadas (disponíveis: %s)",
                    nome_arquivo, list(df.columns)[:12])
        return {}
    df = df[[chave, valor]].dropna()
    df[chave] = df[chave].astype(str).str.strip().str.lstrip("0")
    return dict(zip(df[chave], normalizar_texto(df[valor])))


def carregar_dominios() -> dict[str, dict[str, str]]:
    log.info("Carregando tabelas de domínio…")
    return {
        "programa": _mapa("Programa.csv", ["CD_PROGRAMA"], ["DESCRICAO", "NOME"]),
        "categoria": _mapa("CategoriaEmitente.csv", ["CD_CATEG_EMITENTE"], ["DESCRICAO"]),
        "fonte": _mapa("FonteRecursos.csv", ["CD_FONTE_RECURSO"], ["DESCRICAO"]),
        "seguro": _mapa("TipoGarantiaEmpreendimento.csv", ["CD_TIPO_SEGURO"], ["DESCRICAO"]),
        "instituicao": _mapa("SICOR_LISTA_IFS.csv", ["CNPJ_IF"], ["NOME_IF", "NOME"]),
        "irrigacao": _mapa("TipoIrrigacao.csv",
                           ["CD_TIPO_IRRIGACAO", "CD_IRRIGACAO"], ["DESCRICAO"]),
    }


def carregar_empreendimentos() -> pd.DataFrame:
    """
    ``Empreendimento.csv`` decompõe ``CD_EMPREENDIMENTO`` em atividade,
    modalidade, finalidade, produto e variedade — é a chave para saber
    **qual cultura** cada operação financia.
    """
    caminho = DOMINIOS / "Empreendimento.csv"
    if not caminho.exists():
        log.warning("Empreendimento.csv ausente — a cultura ficará indefinida.")
        return pd.DataFrame()
    df = ler_csv(caminho)
    col_cod = next((c for c in df.columns if "EMPREENDIMENTO" in c), None)
    if not col_cod:
        return pd.DataFrame()

    saida = pd.DataFrame({"cd_empreendimento": df[col_cod].astype(str).str.strip()})
    for destino, candidatos in {
        "produto": ["PRODUTO", "DS_PRODUTO", "NO_PRODUTO"],
        "atividade": ["ATIVIDADE", "DS_ATIVIDADE"],
        "modalidade": ["MODALIDADE", "DS_MODALIDADE"],
        "finalidade": ["FINALIDADE", "DS_FINALIDADE"],
        "variedade": ["VARIEDADE", "DS_VARIEDADE"],
        "unidade_medida": ["UNIDADE_MEDIDA", "UNIDADE"],
    }.items():
        col = next((c for c in candidatos if c in df.columns), None)
        saida[destino] = normalizar_texto(df[col]) if col else ""

    # Os códigos vêm como descrição ou como código; quando forem códigos,
    # tentamos resolver pelas tabelas auxiliares.
    for destino, arquivo, chaves in (
        ("produto", "Produto.csv", ["CD_PRODUTO"]),
        ("atividade", "Atividade.csv", ["CD_ATIVIDADE"]),
        ("modalidade", "Modalidade.csv", ["CD_MODALIDADE"]),
        ("finalidade", "Finalidade.csv", ["CD_FINALIDADE"]),
    ):
        if saida[destino].str.fullmatch(r"\d+").fillna(False).mean() > 0.7:
            traducao = _mapa(arquivo, chaves, ["DESCRICAO", "NOME"])
            if traducao:
                saida[destino] = (
                    saida[destino].str.strip().str.lstrip("0").map(traducao)
                    .fillna(saida[destino])
                )

    saida = saida.drop_duplicates(subset=["cd_empreendimento"])
    log.info("Empreendimentos: %d combinações decodificadas", len(saida))
    return saida


# ==========================================================================
# Município
# ==========================================================================

def carregar_municipio_por_operacao() -> pd.DataFrame:
    caminho = MICRO / "SICOR_COMPLEMENTO_OPERACAO_BASICA.gz"
    if not caminho.exists():
        log.warning(
            "SICOR_COMPLEMENTO_OPERACAO_BASICA.gz ausente — sem ele as operações "
            "não têm município e o alerta climático fica inviável."
        )
        return pd.DataFrame(columns=["REF_BACEN", "NU_ORDEM", "cd_ibge"])

    partes = []
    for bloco in ler_csv_em_blocos(
        caminho, colunas=["REF_BACEN", "NU_ORDEM", "CD_IBGE_MUNICIPIO"]
    ):
        if "CD_IBGE_MUNICIPIO" not in bloco.columns:
            continue
        bloco = bloco.copy()
        bloco["cd_ibge"] = pd.to_numeric(
            bloco["CD_IBGE_MUNICIPIO"].astype(str).str.extract(r"(\d+)")[0], errors="coerce"
        )
        partes.append(bloco[["REF_BACEN", "NU_ORDEM", "cd_ibge"]].dropna(subset=["cd_ibge"]))
    if not partes:
        return pd.DataFrame(columns=["REF_BACEN", "NU_ORDEM", "cd_ibge"])
    df = pd.concat(partes, ignore_index=True)
    df["cd_ibge"] = df["cd_ibge"].astype("int64")
    log.info("Municípios por operação: %d vínculos", len(df))
    return df.drop_duplicates(subset=["REF_BACEN", "NU_ORDEM"])


# ==========================================================================
# Construção
# ==========================================================================

def processar_ano(
    ano: int, *, amostra: int | None, data_corte: date
) -> pd.DataFrame:
    caminho = MICRO / f"SICOR_OPERACAO_BASICA_ESTADO_{ano}.gz"
    if not caminho.exists():
        log.warning("Arquivo de %d não encontrado (%s)", ano, caminho.name)
        return pd.DataFrame()

    log.info("Processando %s…", caminho.name)
    partes: list[pd.DataFrame] = []
    total_lidas = 0
    for bloco in ler_csv_em_blocos(caminho, colunas=COLUNAS_OPERACAO):
        total_lidas += len(bloco)
        b = bloco.copy()
        b["dt_vencimento"] = para_data(b.get("DT_VENCIMENTO"))
        # Carteira vigente: mantém o que ainda não venceu (com folga de 90 dias)
        vigentes = b["dt_vencimento"].isna() | (
            b["dt_vencimento"] >= pd.Timestamp(data_corte - timedelta(days=90))
        )
        b = b[vigentes]
        if not b.empty:
            partes.append(b)
        if amostra and sum(len(p) for p in partes) >= amostra:
            log.info("   limite de amostra (%d) atingido", amostra)
            break

    if not partes:
        log.warning("%d: nenhuma operação vigente encontrada.", ano)
        return pd.DataFrame()

    df = pd.concat(partes, ignore_index=True)
    if amostra and len(df) > amostra:
        df = df.sample(n=amostra, random_state=42).reset_index(drop=True)
    log.info("   %d linhas lidas → %d operações vigentes", total_lidas, len(df))
    return df


def montar(
    bruto: pd.DataFrame,
    dominios: dict[str, dict[str, str]],
    empreendimentos: pd.DataFrame,
    municipios_op: pd.DataFrame,
    municipios_geo: pd.DataFrame,
) -> pd.DataFrame:
    df = bruto.copy()

    saida = pd.DataFrame()
    saida["ref_bacen"] = df["REF_BACEN"].astype(str).str.strip()
    saida["nu_ordem"] = pd.to_numeric(df.get("NU_ORDEM"), errors="coerce").fillna(1).astype("int64")
    saida["cnpj_if"] = df.get("CNPJ_IF", pd.Series(dtype=str)).astype(str).str.strip()

    # --- domínios ------------------------------------------------------
    def traduz(coluna: str, mapa: dict[str, str], padrao: str = "") -> pd.Series:
        if coluna not in df.columns:
            return pd.Series([padrao] * len(df))
        chave = df[coluna].astype(str).str.strip().str.lstrip("0")
        return chave.map(mapa).fillna(padrao if padrao else chave)

    saida["instituicao"] = traduz("CNPJ_IF", dominios["instituicao"], "Instituição não identificada")
    saida["cd_programa"] = df.get("CD_PROGRAMA", pd.Series(dtype=str)).astype(str).str.strip()
    saida["programa"] = traduz("CD_PROGRAMA", dominios["programa"], "Programa não identificado")
    saida["categoria_emitente"] = traduz("CD_CATEG_EMITENTE", dominios["categoria"])
    saida["fonte_recurso"] = traduz("CD_FONTE_RECURSO", dominios["fonte"])
    saida["cd_tipo_seguro"] = df.get("CD_TIPO_SEGURO", pd.Series(dtype=str)).astype(str).str.strip()
    saida["tipo_seguro"] = traduz("CD_TIPO_SEGURO", dominios["seguro"],
                                  "Sem cobertura de risco declarada")

    # --- empreendimento -------------------------------------------------
    saida["cd_empreendimento"] = df.get("CD_EMPREENDIMENTO", pd.Series(dtype=str)).astype(str).str.strip()
    if not empreendimentos.empty:
        saida = saida.merge(empreendimentos, on="cd_empreendimento", how="left")
    for col in ("produto", "atividade", "modalidade", "finalidade", "unidade_medida"):
        if col not in saida.columns:
            saida[col] = ""
        saida[col] = saida[col].fillna("")
    saida["cultura"] = saida["produto"].map(mapear_produto_para_cultura)

    # --- datas e valores -------------------------------------------------
    saida["dt_emissao"] = para_data(df.get("DT_EMISSAO"))
    saida["dt_vencimento"] = para_data(df.get("DT_VENCIMENTO"))
    saida["dt_inic_plantio"] = para_data(df.get("DT_INIC_PLANTIO"))
    saida["dt_fim_plantio"] = para_data(df.get("DT_FIM_PLANTIO"))
    saida["dt_inic_colheita"] = para_data(df.get("DT_INIC_COLHEITA"))
    saida["dt_fim_colheita"] = para_data(df.get("DT_FIM_COLHEITA"))

    saida["valor_credito"] = para_numero(df.get("VL_PARC_CREDITO")).fillna(0.0)
    area = para_numero(df.get("VL_AREA_FINANC"))
    area_info = para_numero(df.get("VL_AREA_INFORMADA"))
    saida["area_ha"] = area.fillna(area_info).fillna(0.0)
    saida["produtividade_prevista"] = para_numero(df.get("VL_PREV_PROD")).fillna(0.0)
    saida["receita_bruta_esperada"] = para_numero(df.get("VL_RECEITA_BRUTA_ESPERADA")).fillna(0.0)
    saida["aliquota_proagro"] = para_numero(df.get("VL_ALIQ_PROAGRO")).fillna(0.0)

    # --- cobertura e irrigação -------------------------------------------
    texto_seguro = saida["tipo_seguro"].astype(str).str.lower()
    saida["tem_cobertura"] = ~(
        texto_seguro.str.contains("sem ")
        | texto_seguro.str.contains("não")
        | texto_seguro.str.contains("nao")
        | (texto_seguro.str.strip() == "")
    )
    irrig = df.get("CD_TIPO_IRRIGACAO", pd.Series(dtype=str)).astype(str).str.strip()
    # Códigos vazios, "0" ou rótulo de sequeiro indicam ausência de irrigação
    saida["irrigada"] = ~irrig.isin(["", "0", "00", "nan", "None"]) & ~irrig.str.lower().str.contains(
        "sequeiro", na=False
    )

    # --- geografia --------------------------------------------------------
    if not municipios_op.empty:
        chave = df[["REF_BACEN", "NU_ORDEM"]].copy()
        chave["REF_BACEN"] = chave["REF_BACEN"].astype(str).str.strip()
        chave["NU_ORDEM"] = chave["NU_ORDEM"].astype(str).str.strip()
        mop = municipios_op.copy()
        mop["REF_BACEN"] = mop["REF_BACEN"].astype(str).str.strip()
        mop["NU_ORDEM"] = mop["NU_ORDEM"].astype(str).str.strip()
        chave = chave.merge(mop, on=["REF_BACEN", "NU_ORDEM"], how="left")
        saida["cd_ibge"] = pd.to_numeric(chave["cd_ibge"], errors="coerce")
    else:
        saida["cd_ibge"] = np.nan

    if not municipios_geo.empty:
        geo = municipios_geo[["cd_ibge", "municipio", "uf", "regiao", "lat", "lon"]]
        saida = saida.merge(geo, on="cd_ibge", how="left")
    else:
        for c in ("municipio", "uf", "regiao", "lat", "lon"):
            saida[c] = pd.NA

    saida["cd_ibge"] = pd.to_numeric(saida["cd_ibge"], errors="coerce").fillna(0).astype("int64")

    # --- persona e safra ---------------------------------------------------
    saida["persona"] = [
        inferir_persona_do_mutuario(
            programa_descricao=p, categoria_emitente=c,
            valor_credito=v, area_financiada=a,
        )
        for p, c, v, a in zip(saida["programa"], saida["categoria_emitente"],
                              saida["valor_credito"], saida["area_ha"])
    ]
    ano_safra = saida["dt_inic_plantio"].dt.year.fillna(saida["dt_emissao"].dt.year)
    saida["safra"] = ano_safra.apply(
        lambda a: f"{int(a)}/{str(int(a) + 1)[-2:]}" if pd.notna(a) else ""
    )
    saida["fonte"] = "bcb_sicor"
    return aplicar_esquema(saida, CARTEIRA_COLS)


# ==========================================================================
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Constrói a carteira curada do Sicor.")
    parser.add_argument("--anos", nargs="*", type=int, default=[2025, 2026])
    parser.add_argument("--amostra", type=int, default=None,
                        help="Limita o número de operações por ano (útil em máquina modesta).")
    parser.add_argument("--log", default="INFO")
    args = parser.parse_args(argv)

    iniciar(args.log)
    cabecalho(f"ETL 02 — Carteira de crédito rural ({', '.join(map(str, args.anos))})")

    municipios_geo = carregar_curado("municipios")
    if municipios_geo is None or municipios_geo.empty:
        log.error("Tabela de municípios ausente. Execute antes: python etl/04_build_municipios.py")
        return 1

    dominios = carregar_dominios()
    empreendimentos = carregar_empreendimentos()
    municipios_op = carregar_municipio_por_operacao()

    hoje = date.today()
    partes = []
    for ano in args.anos:
        bruto = processar_ano(ano, amostra=args.amostra, data_corte=hoje)
        if bruto.empty:
            continue
        partes.append(montar(bruto, dominios, empreendimentos, municipios_op, municipios_geo))

    if not partes:
        log.error("Nenhuma operação processada. Baixe os microdados: "
                  "python etl/01_download_microdados.py --anos %s",
                  " ".join(map(str, args.anos)))
        return 1

    carteira = pd.concat(partes, ignore_index=True)
    carteira = carteira.drop_duplicates(subset=["ref_bacen", "nu_ordem"])

    gravar(carteira, "carteira")

    # ------------------------------------------------------------ relatório
    com_geo = int(carteira["lat"].notna().sum())
    log.info("")
    log.info("Resumo da carteira curada")
    log.info("  operações ............ %d", len(carteira))
    log.info("  com coordenada ....... %d (%.1f%%)", com_geo,
             100 * com_geo / max(len(carteira), 1))
    log.info("  municípios ........... %d", carteira["cd_ibge"].nunique())
    log.info("  UFs .................. %d", carteira["uf"].nunique())
    log.info("  valor total .......... R$ %.2f bi", carteira["valor_credito"].sum() / 1e9)
    log.info("  área total ........... %.0f mil ha", carteira["area_ha"].sum() / 1e3)
    log.info("  com cobertura ........ %.1f%%", 100 * carteira["tem_cobertura"].mean())
    log.info("  com ciclo declarado .. %.1f%%",
             100 * carteira["dt_inic_plantio"].notna().mean())
    log.info("")
    log.info("Culturas mais frequentes:")
    for cultura, n in carteira["cultura"].value_counts().head(10).items():
        log.info("    %-16s %6d", cultura, n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
