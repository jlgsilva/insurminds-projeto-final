#!/usr/bin/env python3
"""
Orquestrador do ETL — executa todas as etapas na ordem correta.

    00  baixa as tabelas de domínio
    04  constrói a tabela de municípios (geografia + alíquotas)
    01  baixa os microdados dos anos escolhidos
    02  constrói a carteira
    03  constrói o histórico de sinistralidade do Proagro
    06  constrói as glebas georreferenciadas          (opcional, --glebas)
    07  constrói a exposição financeira               (opcional, --exposicao)
    08  enriquece com fontes externas livres          (opcional, --externo)
    05  valida e grava o manifesto

As etapas 06 a 08 são **opcionais por decisão de projeto**: cada uma
adiciona uma capacidade (alerta em nível de talhão, risco em reais, contexto
externo) e nenhuma é necessária para a solução funcionar. Isso permite rodar
o ETL em uma máquina modesta e mesmo assim ter o aplicativo completo —
apenas com menos enriquecimento, o que a interface informa.

Uso:
    python etl/run_etl.py                       # 2025 e 2026, núcleo
    python etl/run_etl.py --anos 2026
    python etl/run_etl.py --amostra 150000      # máquina modesta
    python etl/run_etl.py --pular-download      # só reconstrói o que já baixou
    python etl/run_etl.py --tudo                # núcleo + glebas + exposição + externo
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

from _comum import cabecalho, iniciar, log  # noqa: E402


def _carregar(nome_arquivo: str):
    """Importa um script numerado (nome não é identificador Python válido)."""
    caminho = AQUI / nome_arquivo
    spec = importlib.util.spec_from_file_location(caminho.stem, caminho)
    if spec is None or spec.loader is None:
        raise ImportError(f"Não foi possível carregar {nome_arquivo}")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Executa o ETL completo do AgroSentinela.")
    parser.add_argument("--anos", nargs="*", type=int, default=[2025, 2026],
                        help="Anos de operações contratadas.")
    parser.add_argument("--amostra", type=int, default=None,
                        help="Limita operações por ano (economiza memória).")
    parser.add_argument("--pular-download", action="store_true",
                        help="Não baixa nada; usa o que já está em data/raw.")
    parser.add_argument("--todas-dominios", action="store_true",
                        help="Baixa todas as tabelas de domínio, não só as essenciais.")
    parser.add_argument("--centroides", default=None,
                        help="CSV local com os centroides municipais.")
    parser.add_argument("--glebas", action="store_true",
                        help="Constrói as glebas em WKT (alerta em nível de talhão).")
    parser.add_argument("--exposicao", action="store_true",
                        help="Constrói a exposição financeira (saldos e renegociação).")
    parser.add_argument("--externo", action="store_true",
                        help="Enriquece com as fontes externas gratuitas e públicas.")
    parser.add_argument("--externo-offline", action="store_true",
                        help="Roda a etapa externa sem rede, só com as tabelas "
                             "de referência embutidas.")
    parser.add_argument("--tudo", action="store_true",
                        help="Liga --glebas, --exposicao e --externo.")
    parser.add_argument("--estrito", action="store_true",
                        help="Validação em modo estrito (avisos viram erro).")
    parser.add_argument("--log", default="INFO")
    args = parser.parse_args(argv)

    iniciar(args.log)
    inicio = time.perf_counter()
    anos = [str(a) for a in args.anos]

    cabecalho("AgroSentinela — ETL completo dos microdados do Sicor/Proagro")
    extras = [n for n, ligado in (
        ("glebas", args.glebas or args.tudo),
        ("exposição", args.exposicao or args.tudo),
        ("contexto externo", args.externo or args.externo_offline or args.tudo),
    ) if ligado]
    log.info("Anos: %s | amostra por ano: %s | download: %s | extras: %s",
             ", ".join(anos), args.amostra or "completa",
             "não" if args.pular_download else "sim",
             ", ".join(extras) or "nenhum")

    etapas: list[tuple[str, str, list[str]]] = []
    if not args.pular_download:
        etapas.append((
            "00_download_dominios.py", "Tabelas de domínio",
            (["--todas"] if args.todas_dominios else []) + ["--log", args.log],
        ))
    etapas.append((
        "04_build_municipios.py", "Municípios",
        (["--centroides", args.centroides] if args.centroides else []) + ["--log", args.log],
    ))
    if not args.pular_download:
        argumentos_download = ["--anos", *anos]
        if args.glebas or args.tudo:
            argumentos_download += ["--glebas", *anos, "--contratado"]
        if args.exposicao or args.tudo:
            argumentos_download += ["--saldos", *anos, "--financeiro"]
        if args.tudo:
            argumentos_download += ["--cadeia-proagro", "--perfil"]
        etapas.append((
            "01_download_microdados.py", "Microdados",
            argumentos_download + ["--log", args.log],
        ))
    etapas.append((
        "02_build_carteira.py", "Carteira",
        ["--anos", *anos] + (["--amostra", str(args.amostra)] if args.amostra else [])
        + ["--log", args.log],
    ))
    etapas.append(("03_build_proagro.py", "Proagro", ["--log", args.log]))

    tudo = args.tudo
    if args.glebas or tudo:
        etapas.append((
            "06_build_glebas.py", "Glebas georreferenciadas",
            ["--anos", *anos, "--contratado", "--log", args.log],
        ))
    if args.exposicao or tudo:
        etapas.append((
            "07_build_exposicao.py", "Exposição financeira",
            ["--anos", *anos, "--log", args.log],
        ))
    if args.externo or args.externo_offline or tudo:
        etapas.append((
            "08_build_contexto_externo.py", "Contexto externo",
            (["--offline"] if args.externo_offline else []) + ["--log", args.log],
        ))

    etapas.append((
        "05_validate.py", "Validação",
        (["--estrito"] if args.estrito else []) + ["--log", args.log],
    ))

    resultados: list[tuple[str, int, float]] = []
    for arquivo, titulo, argumentos in etapas:
        t0 = time.perf_counter()
        log.info("")
        log.info("▶ %s (%s)", titulo, arquivo)
        try:
            modulo = _carregar(arquivo)
            codigo = int(modulo.main(argumentos) or 0)
        except SystemExit as exc:  # scripts podem chamar SystemExit
            codigo = int(exc.code or 0)
        except Exception as exc:  # noqa: BLE001
            log.exception("Etapa %s falhou: %s", titulo, exc)
            codigo = 1
        duracao = time.perf_counter() - t0
        resultados.append((titulo, codigo, duracao))
        if codigo != 0:
            log.error("✖ %s terminou com código %d — interrompendo.", titulo, codigo)
            break

    total = time.perf_counter() - inicio
    log.info("")
    log.info("═" * 74)
    log.info("  Resumo do ETL")
    log.info("═" * 74)
    for titulo, codigo, duracao in resultados:
        marca = "✔" if codigo == 0 else "✖"
        log.info("  %s %-24s %7.1fs  (código %d)", marca, titulo, duracao, codigo)
    log.info("  Tempo total: %.1fs", total)
    log.info("")
    if all(c == 0 for _, c, _ in resultados) and len(resultados) == len(etapas):
        log.info("✅ ETL concluído. Abra o aplicativo e selecione "
                 "«Somente dados curados do BCB» na barra lateral.")
        return 0
    log.error("ETL incompleto — verifique as mensagens acima.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
