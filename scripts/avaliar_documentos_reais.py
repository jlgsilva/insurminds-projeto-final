"""
Valida a plataforma em documentos REAIS (fora do acervo simulado).

    python scripts/avaliar_documentos_reais.py --pasta <pasta_com_os_pdfs>
    python scripts/avaliar_documentos_reais.py --pasta <pasta> --llm     # com Groq

Os PDFs não ficam no repositório (ver data/apolices_reais/LEIA-ME.md): são
reconhecidos pelo SHA-256 registrado em data/apolices_reais/gabarito_reais.json.
Cada documento passa pelo pipeline completo de ingestão (os mesmos agentes do
app), numa base temporária, e o resultado é comparado com o gabarito:

* documentos de D&O (condições gerais): presença e nível das 32 cláusulas;
* documentos de outro ramo (Seguro Garantia): devem ser reconhecidos e
  recusados — não podem virar uma "apólice D&O" na base.

Saídas (agregadas, sem dados dos documentos de terceiros):
``data/apolices_reais/avaliacao_reais_<metodo>.csv`` e
``Projeto_Final_Artefatos/avaliacao_reais.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from agrosentinela.projeto_final.agentes import OrquestradorApolices  # noqa: E402
from agrosentinela.projeto_final.repositorio import Repositorio  # noqa: E402

PASTA_DADOS = ROOT / "data" / "apolices_reais"
GABARITO = PASTA_DADOS / "gabarito_reais.json"
RESUMO = ROOT / "Projeto_Final_Artefatos" / "avaliacao_reais.json"
AUSENTES = ("ausente", "excluida")


def _orquestrador(repo: Repositorio, usar_llm: bool) -> OrquestradorApolices:
    cliente = None
    if usar_llm:
        from agrosentinela.llm.groq_client import GroqClient

        cliente = GroqClient()
        if not cliente.disponivel:
            sys.exit("GROQ_API_KEY não configurada (.env).")
    return OrquestradorApolices(repo=repo, cliente=cliente)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pasta", default=str(PASTA_DADOS), help="pasta com os PDFs reais")
    ap.add_argument("--llm", action="store_true", help="usar Groq na extração")
    args = ap.parse_args()

    gab = json.loads(GABARITO.read_text(encoding="utf-8"))
    por_hash = {d["sha256"]: d for d in gab["documentos"]}
    arquivos = {}
    for p in sorted(Path(args.pasta).glob("*.pdf")):
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        if h in por_hash:
            arquivos[por_hash[h]["identificador"]] = p
    faltam = [d["identificador"] for d in gab["documentos"] if d["identificador"] not in arquivos]
    if not arquivos:
        sys.exit(f"Nenhum PDF do gabarito encontrado em {args.pasta}.")
    if faltam:
        print("Aviso: não encontrados (SHA-256 diferente ou ausentes):", ", ".join(faltam))

    metodo = "llm" if args.llm else "deterministico"
    linhas = []
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repositorio(Path(tmp) / "reais.sqlite", semear=False)
        orq = _orquestrador(repo, args.llm)
        for d in gab["documentos"]:
            ident = d["identificador"]
            if ident not in arquivos:
                continue
            t0 = time.time()
            ctx = orq.ingerir([(f"{ident}.pdf", arquivos[ident].read_bytes())],
                              usar_llm=args.llm, permitir_ocr=True, reprocessar=True)
            dur = time.time() - t0
            it = ctx.itens[0]
            linha = {"documento": ident, "paginas": d.get("paginas"),
                     "ramo_esperado": d["ramo"], "ramo_detectado": it.tipo.ramo if it.tipo else None,
                     "tipo_esperado": d["tipo"], "tipo_detectado": it.tipo.tipo if it.tipo else None,
                     "gravado_na_base": not it.ignorado and not it.erro,
                     "secoes": len(it.secoes), "segundos": round(dur, 1), "metodo": metodo}
            if d["ramo"] == "do" and linha["gravado_na_base"]:
                prev = {k: v.nivel for k, v in it.extracao.clausulas.items()}
                esp = {c["codigo"]: c["nivel"] for c in d["clausulas"]}
                pres = [(prev.get(k, "ausente") in AUSENTES) == (v in AUSENTES) for k, v in esp.items()]
                niv = [prev.get(k) == v for k, v in esp.items()]
                presentes = [k for k, v in esp.items() if v not in AUSENTES]
                linha.update({
                    "seguradora_lida": it.extracao.cadastro.get("seguradora"),
                    "seguradora_ok": bool(it.extracao.cadastro.get("seguradora")) and
                    d["seguradora"].split()[0].lower() in str(it.extracao.cadastro.get("seguradora")).lower(),
                    "acuracia_presenca": round(100 * sum(pres) / len(pres), 1),
                    "acuracia_nivel": round(100 * sum(niv) / len(niv), 1),
                    "cobertura_presentes": round(100 * sum(prev.get(k, "ausente") not in AUSENTES
                                                       for k in presentes) / max(1, len(presentes)), 1),
                })
            linhas.append(linha)
            print({k: linha.get(k) for k in ("documento", "ramo_detectado", "tipo_detectado",
                                              "gravado_na_base", "acuracia_presenca",
                                              "acuracia_nivel", "segundos")})
    df = pd.DataFrame(linhas)
    df.to_csv(PASTA_DADOS / f"avaliacao_reais_{metodo}.csv", index=False)
    do = df[df["ramo_esperado"] == "do"]
    resumo = json.loads(RESUMO.read_text(encoding="utf-8")) if RESUMO.exists() else {}
    resumo[metodo] = {
        "documentos": int(len(df)),
        "ramo_correto": int((df["ramo_esperado"] == df["ramo_detectado"]).sum()),
        "tipo_correto": int((df["tipo_esperado"] == df["tipo_detectado"]).sum()),
        "fora_do_escopo_recusados": int(((df["ramo_esperado"] != "do") & ~df["gravado_na_base"]).sum()),
        "fora_do_escopo_total": int((df["ramo_esperado"] != "do").sum()),
        "do_documentos": int(len(do)),
        "do_paginas": int(do["paginas"].sum()) if len(do) else 0,
        "acuracia_presenca": round(float(do["acuracia_presenca"].mean()), 1) if len(do) else None,
        "acuracia_nivel": round(float(do["acuracia_nivel"].mean()), 1) if len(do) else None,
        "cobertura_presentes": round(float(do["cobertura_presentes"].mean()), 1) if len(do) else None,
        "seguradora_ok": int(do["seguradora_ok"].sum()) if len(do) else 0,
        "por_documento": {r.documento: {"presenca": r.acuracia_presenca, "nivel": r.acuracia_nivel}
                          for r in do.itertuples()},
    }
    RESUMO.write_text(json.dumps(resumo, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(resumo[metodo], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
