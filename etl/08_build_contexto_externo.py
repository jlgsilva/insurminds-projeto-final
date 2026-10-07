#!/usr/bin/env python3
"""
ETL 08 — constrói o conjunto **contexto_externo** com fontes livres.

Regra inegociável do projeto: **só entra dado gratuito, público e livre**.
Nenhuma fonte consumida aqui exige contrato, cartão de crédito ou cota paga,
e nenhuma exige sequer cadastro. O catálogo completo — com órgão, licença,
granularidade e o papel de cada uma — está em
``src/agrosentinela/fontes_externas.py``.

Fontes consumidas
-----------------
* **NASA POWER** — normais climatológicas no centroide (domínio público).
* **IBGE SIDRA / PAM e PPM** — área, produção e rendimento municipal.
* **PSR / MAPA (Atlas do Seguro Rural)** — cobertura por seguro privado.
* **MapBiomas** — uso e cobertura do solo (CC BY-SA 4.0).
* **INPE / Programa Queimadas** — focos de calor.
* **Monitor de Secas (ANA e parceiros)** — classificação oficial de seca.

Honestidade de procedência
--------------------------
Cada execução grava, na coluna ``origem_contexto``, se cada fonte respondeu
ao vivo, veio de cache ou caiu na tabela de referência embutida. O aplicativo
exibe esse selo junto do número. Um valor de referência **nunca** é
apresentado como se fosse consulta ao vivo — é o que separa um painel
utilizável em decisão de um painel decorativo.

Uso:
    python etl/08_build_contexto_externo.py
    python etl/08_build_contexto_externo.py --offline        # só referências
    python etl/08_build_contexto_externo.py --normais 300    # mais municípios
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _comum import (  # noqa: E402
    CURATED_DIR,
    cabecalho,
    carregar_curado,
    gravar,
    iniciar,
    log,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from agrosentinela.data.schemas import CONTEXTO_COLS, aplicar_esquema  # noqa: E402
from agrosentinela.external import contexto_municipal, sondar  # noqa: E402
from agrosentinela.external.ibge_sidra import (  # noqa: E402
    RENDIMENTO_REFERENCIA,
    IbgeSidra,
    cultura_do_produto_ibge,
)
from agrosentinela.fontes_externas import creditos, resumo as resumo_fontes  # noqa: E402


def rendimento_por_municipio(municipios: pd.DataFrame, carteira: pd.DataFrame,
                             *, offline: bool, limite: int) -> pd.DataFrame:
    """
    Busca na PAM o rendimento médio da **cultura dominante** de cada município.

    Consultar todas as culturas de todos os municípios seriam dezenas de
    milhares de requisições. A cultura dominante é a que concentra o crédito
    ali, então é a que importa para estimar perda — e a coluna
    ``cultura_referencia`` deixa explícito a qual cultura o rendimento se
    refere, em vez de sugerir um número universal.
    """
    if carteira is None or carteira.empty or "cultura" not in carteira.columns:
        return pd.DataFrame(columns=["cd_ibge", "rendimento_ref_kg_ha",
                                     "cultura_referencia"])

    dominante = (carteira.groupby(["cd_ibge", "cultura"], as_index=False)
                         .agg(valor=("valor_credito", "sum"))
                         .sort_values("valor", ascending=False)
                         .drop_duplicates(subset=["cd_ibge"]))

    conector = IbgeSidra(offline=offline)
    linhas: list[dict] = []
    consultados = 0
    for _, r in dominante.iterrows():
        cultura = str(r["cultura"]).lower()
        rendimento = RENDIMENTO_REFERENCIA.get(cultura, 0.0)
        if not offline and consultados < limite:
            res = conector.obter(cd_ibge=int(r["cd_ibge"]))
            consultados += 1
            if not res.vazio and "rendimento_kg_ha" in res.dados.columns:
                casadas = res.dados[
                    res.dados["produto_ibge"].map(
                        lambda p: cultura_do_produto_ibge(p) == cultura)
                ]
                if not casadas.empty:
                    valor = pd.to_numeric(casadas["rendimento_kg_ha"],
                                          errors="coerce").max()
                    if pd.notna(valor) and valor > 0:
                        rendimento = float(valor)
        linhas.append({
            "cd_ibge": int(r["cd_ibge"]),
            "rendimento_ref_kg_ha": rendimento,
            "cultura_referencia": cultura,
        })
    log.info("PAM: %d municípios consultados ao vivo, %d resolvidos por "
             "rendimento de referência.", consultados, len(linhas) - consultados)
    return pd.DataFrame(linhas)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Enriquece os municípios com fontes externas livres.")
    parser.add_argument("--offline", action="store_true",
                        help="Não acessa a rede; usa só as tabelas embutidas.")
    parser.add_argument("--normais", type=int, default=120,
                        help="Quantos municípios consultam a NASA POWER "
                             "ponto a ponto (padrão: 120).")
    parser.add_argument("--sondar", action="store_true",
                        help="Testa antes quais fontes estão respondendo.")
    parser.add_argument("--log", default="INFO")
    args = parser.parse_args(argv)

    iniciar(args.log)
    cabecalho("ETL 08 — Contexto externo (fontes gratuitas, públicas e livres)")

    resumo = resumo_fontes()
    log.info("Catálogo de fontes: %d no total, %d ativas, %d sem cadastro, "
             "todas gratuitas: %s.",
             resumo["total"], resumo["ativas"], resumo["sem_cadastro"],
             "sim" if resumo["todas_gratuitas"] else "NÃO")

    if args.sondar and not args.offline:
        log.info("")
        for _, linha in sondar().iterrows():
            log.info("  %-45s %s", linha["fonte"], linha["estado"])
        log.info("")

    municipios = carregar_curado("municipios")
    if municipios is None or municipios.empty:
        log.error("Municípios curados ausentes. Rode etl/04_build_municipios.py.")
        return 1
    carteira = carregar_curado("carteira")

    log.info("Enriquecendo %d municípios...", len(municipios))
    contexto, procedencia = contexto_municipal(
        municipios, offline=args.offline,
        incluir_normais=True, limite_normais=args.normais,
    )

    rendimentos = rendimento_por_municipio(
        municipios, carteira, offline=args.offline, limite=args.normais)
    if not rendimentos.empty:
        contexto = contexto.drop(
            columns=[c for c in ("rendimento_ref_kg_ha", "cultura_referencia")
                     if c in contexto.columns]
        ).merge(rendimentos, on="cd_ibge", how="left")

    contexto = aplicar_esquema(contexto, CONTEXTO_COLS)
    gravar(contexto, "contexto_externo")

    manifesto = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "modo": "offline" if args.offline else "rede",
        "municipios": int(len(contexto)),
        "procedencia_por_fonte": procedencia,
        "creditos": creditos(),
        "aviso": (
            "Valores marcados como 'referência embutida' são aproximações "
            "públicas para manter a aplicação funcional sem rede. Não devem "
            "ser usados em decisão operacional."
        ),
    }
    (CURATED_DIR / "manifesto_contexto_externo.json").write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")

    log.info("")
    log.info("Procedência desta execução:")
    for fonte, origem in sorted(procedencia.items()):
        log.info("  %-20s %s", fonte, origem)
    log.info("")
    log.info("Créditos de atribuição gravados no manifesto (%d fontes).",
             len(manifesto["creditos"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
