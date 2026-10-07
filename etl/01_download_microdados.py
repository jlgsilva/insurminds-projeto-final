#!/usr/bin/env python3
"""
ETL 01 — baixa os **microdados** do Sicor.

⚠️ Estes arquivos são grandes. ``SICOR_OPERACAO_BASICA_ESTADO_2025.gz``
sozinho costuma passar de 300 MB comprimido, e alguns gigabytes quando
descomprimido. Baixe apenas os anos de que você precisa.

Recomendação para o Desafio 5: **os dois últimos anos** bastam para montar
uma carteira vigente representativa, mais os arquivos de Proagro e o
complemento que traz o município.

Uso:
    python etl/01_download_microdados.py --anos 2025 2026
    python etl/01_download_microdados.py --anos 2026 --sem-proagro
    python etl/01_download_microdados.py --listar
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _comum import RAW_DIR, baixar, cabecalho, iniciar, log  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from agrosentinela.etl_catalogo import CATALOGO_POR_CHAVE, obter  # noqa: E402

DESTINO = RAW_DIR / "microdados"

# Arquivos indispensáveis para montar a carteira e o histórico do Proagro.
BASE_PROAGRO = ("cop_basico", "rcp_basico", "complemento_cop", "complemento_rcp")
BASE_GEO = ("complemento_operacao",)

# Cadeia completa do Proagro: COP -> RCP -> súmula -> parcelas, mais as
# glebas periciadas. Sem a súmula não se conhece a taxa de indeferimento;
# sem as parcelas não se conhece o valor efetivamente pago.
CADEIA_PROAGRO = ("sumula", "parcelas_proagro", "rcp_glebas_2021",
                  "rcp_glebas_2015_2020")

# Exposição financeira: saldo devedor, desembolso e renegociação.
FINANCEIRO = ("liberacao", "parcelas_desembolso", "lista_renegociacao",
              "operacao_renegociacao", "complemento_reneg", "desclassificacao")

# Perfil do imóvel e dos beneficiários coletivos.
PERFIL = ("propriedades", "lista_cooperados")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Baixa os microdados do Sicor.")
    parser.add_argument("--anos", nargs="*", type=int, default=[2025, 2026],
                        help="Anos de operações contratadas (padrão: 2025 2026).")
    parser.add_argument("--contratado", action="store_true",
                        help="Baixa também SICOR_OPERACAO_BASICA_CONTRAT (carteira viva).")
    parser.add_argument("--glebas", nargs="*", type=int, default=None,
                        help="Anos de glebas em WKT (arquivos muito grandes).")
    parser.add_argument("--sem-proagro", action="store_true",
                        help="Pula COP/RCP — só a carteira.")
    parser.add_argument("--cadeia-proagro", action="store_true",
                        help="Baixa a cadeia completa do Proagro (súmula de "
                             "julgamento, parcelas pagas e glebas periciadas).")
    parser.add_argument("--saldos", nargs="*", type=int, default=None,
                        help="Anos de saldos das operações (dataset 'exposicao').")
    parser.add_argument("--financeiro", action="store_true",
                        help="Liberação, cronograma de desembolso, renegociação "
                             "e desclassificação.")
    parser.add_argument("--perfil", action="store_true",
                        help="Propriedades (área, posse, CAR) e lista de cooperados.")
    parser.add_argument("--completo", action="store_true",
                        help="Liga --contratado, --cadeia-proagro, --financeiro "
                             "e --perfil de uma vez. Muitos gigabytes.")
    parser.add_argument("--sem-hash", action="store_true",
                        help="Não verifica a integridade (mais rápido).")
    parser.add_argument("--forcar", action="store_true")
    parser.add_argument("--listar", action="store_true",
                        help="Apenas lista o que seria baixado.")
    parser.add_argument("--log", default="INFO")
    args = parser.parse_args(argv)

    iniciar(args.log)

    chaves: list[str] = []
    for ano in args.anos:
        chave = f"operacao_{ano}"
        if chave in CATALOGO_POR_CHAVE:
            chaves.append(chave)
        else:
            log.warning("Ano %s não consta no catálogo — ignorado.", ano)
    chaves += list(BASE_GEO)
    if not args.sem_proagro:
        chaves += list(BASE_PROAGRO)

    completo = args.completo
    if args.contratado or completo:
        chaves += ["operacao_contratada", "complemento_contratada",
                   "glebas_contratada", "propriedades_contratada",
                   "parcelas_contratada"]
    if (args.cadeia_proagro or completo) and not args.sem_proagro:
        chaves += list(CADEIA_PROAGRO)
    if args.financeiro or completo:
        chaves += list(FINANCEIRO)
    if args.perfil or completo:
        chaves += list(PERFIL)

    for ano in (args.glebas or []):
        chave = f"glebas_{ano}"
        if chave in CATALOGO_POR_CHAVE:
            chaves.append(chave)
        else:
            log.warning("Glebas de %s não constam no catálogo — ignorado.", ano)
    for ano in (args.saldos or []):
        chave = f"saldo_{ano}"
        if chave in CATALOGO_POR_CHAVE:
            chaves.append(chave)
        else:
            log.warning("Saldos de %s não constam no catálogo — ignorado.", ano)

    arquivos = [obter(c) for c in dict.fromkeys(chaves)]
    cabecalho(f"ETL 01 — Microdados do Sicor ({len(arquivos)} arquivos)")

    if args.listar:
        for a in arquivos:
            log.info("  %-30s %s", a.chave, a.url)
        return 0

    log.info("Destino: %s", DESTINO)
    log.info("⚠️  Arquivos grandes: o download pode levar bastante tempo.")

    relatorio = []
    for arquivo in arquivos:
        resultado = baixar(
            arquivo, DESTINO, forcar=args.forcar, verificar_hash=not args.sem_hash
        )
        relatorio.append({
            "chave": arquivo.chave,
            "nome": arquivo.nome,
            "url": arquivo.url,
            "arquivo": resultado.caminho.name,
            "tamanho_mb": resultado.tamanho_mb,
            "hash_ok": resultado.hash_ok,
            "erro": resultado.erro,
        })

    manifesto = DESTINO / "_manifesto_microdados.json"
    manifesto.write_text(
        json.dumps(
            {"gerado_em": datetime.now().isoformat(timespec="seconds"),
             "anos": args.anos, "arquivos": relatorio},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )

    falhas = [r for r in relatorio if r["erro"]]
    divergentes = [r for r in relatorio if r["hash_ok"] is False]
    total_mb = sum(r["tamanho_mb"] for r in relatorio)
    log.info("")
    log.info("Concluído: %d arquivos, %.1f MB, %d falhas, %d hashes divergentes.",
             len(relatorio), total_mb, len(falhas), len(divergentes))
    for f in falhas:
        log.error("  ✖ %s — %s", f["nome"], f["erro"])
    for d in divergentes:
        log.error("  ⚠ %s — hash divergente, rebaixe o arquivo.", d["nome"])
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
