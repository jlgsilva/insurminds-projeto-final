#!/usr/bin/env python3
"""
ETL 05 — valida os conjuntos curados e grava o manifesto.

Roda depois dos scripts 02, 03 e 04. Verifica:

* presença e esquema de cada conjunto;
* cobertura geográfica (proporção de operações com coordenada);
* coerência das datas do ciclo (plantio antes de colheita);
* valores negativos ou nulos onde não deveriam existir;
* coordenadas fora do limite aproximado da UF;
* integridade referencial entre carteira, municípios e sinistros.

Encerra com código 1 se houver problema bloqueante, o que permite usar o
script em CI (GitHub Actions).

Uso:
    python etl/05_validate.py
    python etl/05_validate.py --estrito
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _comum import CURATED_DIR, cabecalho, carregar_curado, iniciar, log  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from agrosentinela.data.municipios_seed import validar_coordenadas  # noqa: E402
from agrosentinela.data.schemas import DATASETS, resumo_dataset, validar  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Valida os conjuntos curados.")
    parser.add_argument("--estrito", action="store_true",
                        help="Trata avisos como erro (uso em CI).")
    parser.add_argument("--log", default="INFO")
    args = parser.parse_args(argv)

    iniciar(args.log)
    cabecalho("ETL 05 — Validação dos conjuntos curados")

    erros: list[str] = []
    avisos: list[str] = []
    manifesto: dict = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "origem": "Sicor/Proagro — Banco Central do Brasil",
        "pagina_fonte": (
            "https://www.bcb.gov.br/estabilidadefinanceira/tabelas-credito-rural-proagro"
        ),
        "conjuntos": {},
    }

    conjuntos: dict[str, pd.DataFrame] = {}
    for ds in DATASETS:
        df = carregar_curado(ds.nome)
        if df is None:
            erros.append(f"{ds.nome}: conjunto não encontrado em {CURATED_DIR}")
            continue
        conjuntos[ds.nome] = df
        problemas = validar(df, ds.nome)
        for p in problemas:
            avisos.append(p)
        info = resumo_dataset(df)
        manifesto["conjuntos"][ds.nome] = {
            **info, "descricao": ds.descricao, "origem_bcb": ds.origem_bcb,
        }
        log.info("✔ %-20s %7d linhas × %2d colunas (%.1f MB, %.1f%% vazio)",
                 ds.nome, info["linhas"], info["colunas"],
                 info["memoria_mb"], info["nulos_pct"])

    # ------------------------------------------------------------------
    carteira = conjuntos.get("carteira")
    municipios = conjuntos.get("municipios")
    sinistros = conjuntos.get("proagro_sinistros")

    if carteira is not None and not carteira.empty:
        log.info("")
        log.info("Verificações da carteira:")

        com_geo = carteira["lat"].notna().mean()
        log.info("  coordenada presente ......... %.1f%%", 100 * com_geo)
        if com_geo < 0.5:
            erros.append(
                f"Apenas {com_geo:.0%} das operações têm coordenada. Sem isso o "
                "alerta climático não funciona — confira se "
                "SICOR_COMPLEMENTO_OPERACAO_BASICA.gz foi baixado."
            )
        elif com_geo < 0.9:
            avisos.append(f"{1 - com_geo:.0%} das operações sem coordenada.")

        com_ciclo = carteira["dt_inic_plantio"].notna().mean()
        log.info("  ciclo de lavoura declarado .. %.1f%%", 100 * com_ciclo)
        if com_ciclo < 0.2:
            avisos.append(
                f"Só {com_ciclo:.0%} das operações declaram data de plantio; as "
                "demais não terão fase fenológica (regras agronômicas não se aplicam)."
            )

        invertidas = (
            (carteira["dt_inic_colheita"] < carteira["dt_inic_plantio"]).fillna(False).sum()
        )
        if invertidas:
            avisos.append(f"{invertidas} operações com colheita anterior ao plantio.")
        log.info("  datas invertidas ............ %d", int(invertidas))

        negativos = int((carteira["valor_credito"] < 0).sum())
        zerados = int((carteira["valor_credito"] <= 0).sum())
        log.info("  valor de crédito ≤ 0 ........ %d (%d negativos)", zerados, negativos)
        if negativos:
            erros.append(f"{negativos} operações com valor de crédito negativo.")

        duplicadas = int(carteira.duplicated(subset=["ref_bacen", "nu_ordem"]).sum())
        log.info("  chaves duplicadas ........... %d", duplicadas)
        if duplicadas:
            erros.append(f"{duplicadas} operações duplicadas (ref_bacen + nu_ordem).")

        sem_cultura = float((carteira["cultura"] == "OUTRAS").mean())
        log.info("  cultura não identificada .... %.1f%%", 100 * sem_cultura)
        if sem_cultura > 0.4:
            avisos.append(
                f"{sem_cultura:.0%} das operações ficaram como cultura 'OUTRAS'. "
                "Confira se Empreendimento.csv e Produto.csv foram baixados."
            )

    if municipios is not None and not municipios.empty:
        log.info("")
        log.info("Verificações de municípios:")
        com_geo = municipios.dropna(subset=["lat", "lon"])
        log.info("  com coordenada .............. %d de %d", len(com_geo), len(municipios))
        fora = validar_coordenadas(com_geo)
        log.info("  coordenada fora da UF ....... %d", len(fora))
        if len(fora) > len(com_geo) * 0.02:
            avisos.append(f"{len(fora)} municípios com coordenada fora do limite da UF.")

    if carteira is not None and municipios is not None:
        orfaos = set(carteira["cd_ibge"].unique()) - set(municipios["cd_ibge"].unique())
        orfaos.discard(0)
        if orfaos:
            avisos.append(
                f"{len(orfaos)} códigos IBGE presentes na carteira e ausentes na "
                "tabela de municípios."
            )

    if sinistros is not None and not sinistros.empty:
        log.info("")
        log.info("Verificações do Proagro:")
        sem_evento = float((sinistros["evento"] == "outro").mean())
        log.info("  evento sem mapeamento ....... %.1f%%", 100 * sem_evento)
        if sem_evento > 0.5:
            avisos.append(
                f"{sem_evento:.0%} dos registros de Proagro não foram mapeados para "
                "o catálogo interno de eventos — revise EventoProagro.csv."
            )
        rcp_maior = int((sinistros["n_rcp"] > sinistros["n_cop"]).sum())
        if rcp_maior:
            avisos.append(
                f"{rcp_maior} grupos com mais comprovações do que pedidos de cobertura."
            )

    # ------------------------------------------------------------------
    manifesto["erros"] = erros
    manifesto["avisos"] = avisos
    manifesto["valido"] = not erros
    caminho = CURATED_DIR / "manifesto.json"
    caminho.write_text(json.dumps(manifesto, ensure_ascii=False, indent=2, default=str),
                       encoding="utf-8")

    log.info("")
    log.info("─" * 74)
    if avisos:
        log.warning("Avisos (%d):", len(avisos))
        for a in avisos:
            log.warning("  ⚠ %s", a)
    if erros:
        log.error("Erros (%d):", len(erros))
        for e in erros:
            log.error("  ✖ %s", e)
        log.error("Validação REPROVADA.")
    else:
        log.info("✅ Validação aprovada. Manifesto gravado em %s", caminho)

    if erros:
        return 1
    if args.estrito and avisos:
        log.error("Modo estrito: avisos tratados como erro.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
