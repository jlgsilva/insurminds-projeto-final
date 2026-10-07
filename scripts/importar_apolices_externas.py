"""
Importa um lote de apólices simuladas gerado por outra IA (ver
docs/PROMPT_GERAR_APOLICES.md) para o acervo do aplicativo.

    python scripts/importar_apolices_externas.py --pasta caminho/do/lote
    python scripts/processar_acervo.py          # reconstrói a base inicial

O lote precisa ter os PDFs/imagens e um ``gabarito_externo.json``. O
importador VALIDA tudo antes de copiar (lote é aceito inteiro ou recusado):

* chaves obrigatórias, os 32 códigos de cláusula e o vocabulário de níveis;
* arquivos citados existem e são PDF/imagem de verdade;
* nomes com "(fictícia)" e nenhuma seguradora/empresa real conhecida;
* identificador único (não colide com o acervo atual);
* coerência mínima (vigência, valores positivos, perfil/região válidos);
* o aviso de simulação está no texto do PDF (quando há camada de texto).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from agrosentinela.config import APOLICES_DIR  # noqa: E402
from agrosentinela.projeto_final.clausulas import CLAUSULAS, NIVEIS  # noqa: E402

OBRIGATORIAS = ["identificador", "seguradora_codigo", "seguradora", "tomadora_codigo", "tomadora",
                "perfil", "uf", "regiao", "lmg", "premio", "franquia", "vigencia_inicio",
                "vigencia_fim", "retroatividade", "retroatividade_ilimitada", "avaliacoes",
                "arquivos"]
PERFIS = {"familiar", "pequeno", "medio", "grande", "latifundio", "cooperativa_credito",
          "cooperativa_agroindustrial", "agroindustria", "cadeia"}
REGIOES = {"Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul"}
NOMES_REAIS = ["aig", "allianz", "tokio", "sompo", "chubb", "zurich", "mapfre", "porto seguro",
               "bradesco", "itaú", "itau", "sulamérica", "sulamerica", "liberty", "yelum",
               "fairfax", "axa", "swiss re", "berkley", "junto seguros", "brasilseg",
               "caixa seguradora", "hdi", "austral", "pottencial", "ezze", "excelsior", "newe",
               "sancor", "essor", "coamo", "cooxupé", "cooxupe", "sicredi", "sicoob", "cresol",
               "castrolanda", "frísia", "frisia", "c.vale", "jbs", "marfrig", "raízen", "raizen"]
AVISO = "DOCUMENTO SIMULADO PARA FINS ACADÊMICOS"


def validar(lote: Path, itens: list[dict], existentes: set[str]) -> list[str]:
    erros: list[str] = []
    codigos = {c.codigo for c in CLAUSULAS}
    vistos: set[str] = set()
    for i, g in enumerate(itens):
        ref = g.get("identificador", f"item {i}")
        falta = [k for k in OBRIGATORIAS if k not in g]
        if falta:
            erros.append(f"{ref}: faltam chaves {falta}")
            continue
        if ref in existentes or ref in vistos:
            erros.append(f"{ref}: identificador já existe")
        vistos.add(ref)
        for campo in ("seguradora", "tomadora"):
            nome = str(g[campo])
            if "(fictícia)" not in nome:
                erros.append(f"{ref}: {campo} sem '(fictícia)': {nome}")
            import re

            if any(re.search(rf"\b{re.escape(r)}\b", nome.lower()) for r in NOMES_REAIS):
                erros.append(f"{ref}: {campo} lembra empresa real: {nome}")
        av = g["avaliacoes"]
        if set(av) != codigos:
            erros.append(f"{ref}: avaliacoes deve ter exatamente os 32 códigos "
                         f"(faltam {sorted(codigos - set(av))}, sobram {sorted(set(av) - codigos)})")
        ruins = {k: v for k, v in av.items() if v not in NIVEIS}
        if ruins:
            erros.append(f"{ref}: níveis inválidos {ruins}")
        if g["perfil"] not in PERFIS:
            erros.append(f"{ref}: perfil inválido {g['perfil']}")
        if g["regiao"] not in REGIOES:
            erros.append(f"{ref}: região inválida {g['regiao']}")
        try:
            ini, fim = date.fromisoformat(g["vigencia_inicio"]), date.fromisoformat(g["vigencia_fim"])
            if fim <= ini:
                erros.append(f"{ref}: vigência invertida")
            if g["retroatividade"] and date.fromisoformat(g["retroatividade"]) > ini:
                erros.append(f"{ref}: retroatividade posterior ao início")
        except (TypeError, ValueError) as exc:
            erros.append(f"{ref}: data inválida ({exc})")
        if not all(float(g[k]) >= 0 for k in ("lmg", "premio", "franquia")) or float(g["lmg"]) <= 0:
            erros.append(f"{ref}: valores inválidos")
        for nome in g["arquivos"]:
            f = lote / nome
            if not f.exists():
                erros.append(f"{ref}: arquivo ausente {nome}")
                continue
            cabeca = f.read_bytes()[:8]
            if f.suffix.lower() == ".pdf" and not cabeca.startswith(b"%PDF"):
                erros.append(f"{ref}: {nome} não é PDF")
            if f.suffix.lower() == ".pdf" and g.get("formato") != "pdf_digitalizado":
                try:
                    import pdfplumber
                    import io

                    with pdfplumber.PDF(io.BytesIO(f.read_bytes())) as pdf:
                        texto = (pdf.pages[0].extract_text() or "")
                    if AVISO not in texto.replace("\n", " "):
                        erros.append(f"{ref}: aviso de simulação ausente na 1ª página")
                except Exception as exc:  # noqa: BLE001
                    erros.append(f"{ref}: PDF ilegível ({exc})")
    return erros


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pasta", required=True)
    ap.add_argument("--gabarito", default="gabarito_externo.json")
    ap.add_argument("--simular", action="store_true", help="só valida, não copia")
    args = ap.parse_args()

    lote = Path(args.pasta)
    itens = json.loads((lote / args.gabarito).read_text(encoding="utf-8"))
    caminho_gab = APOLICES_DIR / "gabarito.json"
    atual = json.loads(caminho_gab.read_text(encoding="utf-8")) if caminho_gab.exists() else []
    erros = validar(lote, itens, {g["identificador"] for g in atual})
    if erros:
        print(f"Lote RECUSADO — {len(erros)} problema(s):")
        for e in erros[:60]:
            print("  -", e)
        sys.exit(1)
    print(f"Lote válido: {len(itens)} apólices.")
    if args.simular:
        return
    destino = APOLICES_DIR / "documentos"
    for g in itens:
        for nome in g["arquivos"]:
            shutil.copyfile(lote / nome, destino / nome)
        g.setdefault("fonte", f"externa:{lote.name}")
        g.setdefault("estilo_titulo", 0)
        g.setdefault("semente", 0)
    caminho_gab.write_text(json.dumps(atual + itens, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Importadas {len(itens)} apólices. Acervo: {len(atual) + len(itens)}.")
    print("Agora rode: python scripts/processar_acervo.py")


if __name__ == "__main__":
    main()
