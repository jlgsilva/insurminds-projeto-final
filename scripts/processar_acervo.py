"""
Processa todo o acervo de apólices simuladas pelo pipeline de ingestão.

    # linha de base, sem IA (rápido; usado para gerar a base inicial do app)
    python scripts/processar_acervo.py

    # com IA (Groq) — requer GROQ_API_KEY no .env; respeita a cota gratuita
    python scripts/processar_acervo.py --llm

Saídas:
* ``data/apolices_simuladas/base_inicial.sqlite`` — a base que o app carrega
  na primeira execução (o OCR das digitalizadas já fica feito);
* ``data/apolices_simuladas/avaliacao_<metodo>.csv`` — acerto por apólice
  contra o gabarito.

Com ``--llm``, as chamadas ficam em cache (``data/cache_llm``): reexecutar
não gasta cota de novo.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from agrosentinela.config import APOLICES_DIR  # noqa: E402
from agrosentinela.projeto_final.agentes import OrquestradorApolices  # noqa: E402
from agrosentinela.projeto_final.repositorio import BASE_INICIAL, Repositorio  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="usar Groq na extração")
    ap.add_argument("--saida", default=str(BASE_INICIAL))
    ap.add_argument("--limite", type=int, default=0, help="processar só N documentos")
    ap.add_argument("--pausa", type=float, default=0.0,
                    help="segundos entre documentos (cota gratuita: use ~20 com --llm)")
    args = ap.parse_args()

    saida = Path(args.saida)
    if saida.exists() and not args.llm:
        saida.unlink()
    repo = Repositorio(saida, semear=False)

    cliente = None
    if args.llm:
        from agrosentinela.llm.groq_client import GroqClient

        cliente = GroqClient()
        if not cliente.disponivel:
            sys.exit("GROQ_API_KEY não configurada (.env ou variável de ambiente).")
        ok, msg = cliente.testar_conexao()
        print(msg)
        if not ok:
            sys.exit(1)

    orq = OrquestradorApolices(repo=repo, cliente=cliente)
    pasta = APOLICES_DIR / "documentos"
    arquivos = sorted(pasta.iterdir())
    grupos: dict[str, list[tuple[str, bytes]]] = {}
    from agrosentinela.projeto_final.documentos import agrupar_arquivos

    grupos = agrupar_arquivos((f.name, f.read_bytes()) for f in arquivos)
    nomes = list(grupos)[: args.limite or None]
    linhas = []
    t0 = time.time()
    for i, nome in enumerate(nomes, 1):
        ctx = orq.ingerir(grupos[nome], usar_llm=args.llm, reprocessar=True)
        it = ctx.itens[0]
        av = it.avaliacao or {}
        print(f"[{i:02d}/{len(nomes)}] {nome:<32} {it.doc.metodo_resumo if it.doc else '-':<10} "
              f"cláusulas={it.extracao.metodo_clausulas:<14} conf={it.validacao.confianca if it.validacao else '-'} "
              f"acerto_cl={av.get('acuracia_clausulas')}% campos={av.get('acuracia_campos')}%"
              + (f"  ⚠ {'; '.join(ctx.avisos)[:120]}" if ctx.avisos else ""))
        if av:
            linhas.append({**{k: v for k, v in av.items() if not isinstance(v, list)},
                           "metodo_clausulas": it.extracao.metodo_clausulas,
                           "leitura": it.doc.metodo_resumo if it.doc else "",
                           "erros_clausulas": ";".join(av.get("erros_clausulas", []))})
        if args.pausa and i < len(nomes):
            time.sleep(args.pausa)

    df = pd.DataFrame(linhas)
    metodo = "llm" if args.llm else "deterministico"
    if not df.empty:
        df.to_csv(APOLICES_DIR / f"avaliacao_{metodo}.csv", index=False)
        print(f"\nAcurácia média — campos: {df['acuracia_campos'].mean():.1f}% · "
              f"níveis de cláusula: {df['acuracia_clausulas'].mean():.1f}% · "
              f"presença/ausência: {df['acuracia_presenca'].mean():.1f}%")
    print(f"{len(nomes)} documentos em {time.time() - t0:.0f}s → {saida}")


if __name__ == "__main__":
    main()
