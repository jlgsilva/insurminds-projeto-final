#!/usr/bin/env python3
"""
ETL 00 — baixa as **tabelas de domínio** do Sicor.

São arquivos pequenos (dezenas de KB a poucos MB) que decodificam os
códigos usados nos microdados: produto, programa, município, evento do
Proagro, tipo de seguro, e assim por diante.

Uso:
    python etl/00_download_dominios.py              # apenas as essenciais
    python etl/00_download_dominios.py --todas      # todas as 58 tabelas
    python etl/00_download_dominios.py --forcar     # rebaixa o que já existe
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _comum import RAW_DIR, baixar, cabecalho, espiar, iniciar, log  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from agrosentinela.etl_catalogo import DOMINIOS, dominios_essenciais  # noqa: E402

DESTINO = RAW_DIR / "dominios"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Baixa as tabelas de domínio do Sicor.")
    parser.add_argument("--todas", action="store_true",
                        help="Baixa todas as tabelas, não só as usadas pela solução.")
    parser.add_argument("--forcar", action="store_true", help="Rebaixa arquivos existentes.")
    parser.add_argument("--espiar", action="store_true",
                        help="Mostra as primeiras linhas de cada arquivo baixado.")
    parser.add_argument("--log", default="INFO")
    args = parser.parse_args(argv)

    iniciar(args.log)
    alvo = list(DOMINIOS) if args.todas else dominios_essenciais()
    cabecalho(f"ETL 00 — Tabelas de domínio do Sicor ({len(alvo)} arquivos)")
    log.info("Destino: %s", DESTINO)

    relatorio = []
    for arquivo in alvo:
        resultado = baixar(arquivo, DESTINO, forcar=args.forcar)
        linha = {
            "chave": arquivo.chave,
            "nome": arquivo.nome,
            "url": arquivo.url,
            "arquivo": resultado.caminho.name,
            "baixado_agora": resultado.baixado,
            "tamanho_mb": resultado.tamanho_mb,
            "erro": resultado.erro,
        }
        if resultado.caminho.exists() and args.espiar:
            try:
                amostra = espiar(resultado.caminho, 3)
                linha["colunas"] = list(amostra.columns)
                log.info("   colunas: %s", ", ".join(amostra.columns[:12]))
            except Exception as exc:  # noqa: BLE001
                log.warning("   não foi possível espiar: %s", exc)
        relatorio.append(linha)

    manifesto = DESTINO / "_manifesto_dominios.json"
    manifesto.write_text(
        json.dumps(
            {"gerado_em": datetime.now().isoformat(timespec="seconds"),
             "arquivos": relatorio},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )

    falhas = [r for r in relatorio if r["erro"]]
    log.info("")
    log.info("Concluído: %d arquivos, %d falhas. Manifesto em %s",
             len(relatorio), len(falhas), manifesto)
    for f in falhas:
        log.error("  ✖ %s — %s", f["nome"], f["erro"])
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
