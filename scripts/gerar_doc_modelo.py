#!/usr/bin/env python3
"""
Gera ``docs/modelo_integrado.md`` a partir do código.

A documentação do modelo de dados envelhece mal quando é escrita à mão: o
código muda, o texto fica. Aqui o texto é **derivado** de
``modelo_integrado.py``, ``etl_catalogo.py`` e ``fontes_externas.py``, de
modo que a única forma de a documentação ficar desatualizada é alguém
esquecer de rodar este script — e o gerador de entregáveis o roda sempre.

Uso:
    python scripts/gerar_doc_modelo.py
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from agrosentinela import etl_catalogo as cat  # noqa: E402
from agrosentinela import fontes_externas as fe  # noqa: E402
from agrosentinela.data import modelo_integrado as mi  # noqa: E402

DESTINO = RAIZ / "docs" / "modelo_integrado.md"


def gerar() -> str:
    buf = io.StringIO()
    w = buf.write
    r, rc, rf = mi.resumo(), cat.resumo(), fe.resumo()

    w(f"""# Modelo integrado — como os {rc['total']} arquivos do BCB se conversam

> Documento gerado a partir de `src/agrosentinela/data/modelo_integrado.py`.
> O código é a fonte da verdade; este texto é a leitura dele.
> Regenerar com `python scripts/gerar_doc_modelo.py`.

A página *Tabelas e Microdados do Crédito Rural e do Proagro* publica
{rc['total']} arquivos. A pergunta que separa uma solução real de uma
demonstração é: **como eles se ligam?**

O AgroSentinela consome **{rc['usados']} dos {rc['total']}** ({rc['cobertura_pct']}%).
Os {rc['excluidos_por_privacidade']} restantes são os arquivos de mutuários,
deliberadamente excluídos por decisão de privacidade — a solução trabalha em
nível de operação, gleba e município, e nunca lê dado pessoal identificável.
A exclusão está registrada no catálogo (`etl_catalogo.nao_usados()`) para que
se veja que foi escolha, não esquecimento.

## Três descobertas que organizam tudo

**1. A chave universal é `(REF_BACEN, NU_ORDEM)`.**
`REF_BACEN` identifica o contrato junto ao Banco Central; `NU_ORDEM` distingue
cada empreendimento dentro dele. Quase todo microdado do Sicor carrega esse
par — é por ele que carteira, Proagro, glebas, saldos e renegociação se
encontram.

**2. A operação básica não tem município.**
`SICOR_OPERACAO_BASICA_ESTADO_AAAA.gz` só traz `CD_ESTADO`. O
`CD_IBGE_MUNICIPIO` mora em `SICOR_COMPLEMENTO_OPERACAO_BASICA.gz`. Sem essa
junção não existe georreferenciamento — e sem georreferenciamento não existe
alerta climático dirigido. É a ligação mais crítica do modelo inteiro.

**3. O Proagro é uma cadeia de quatro etapas, não uma tabela.**
COP (pedido) → RCP (perícia) → Súmula (julgamento) → Parcelas (pagamento).
Medir sinistralidade só pelo COP superestima; só pelo RCP ignora o que foi
negado. O AgroSentinela percorre a cadeia inteira e expõe as taxas separadas:
acionamento, comprovação e deferimento.

## Números do grafo

| Métrica | Valor |
|---|---|
| Entidades (tabelas lógicas) | {r['entidades']} |
| — de fato | {r['entidades_fato']} |
| — de domínio | {r['entidades_dominio']} |
| Ligações declaradas | {r['ligacoes']} |
| Ligações críticas | {r['ligacoes_criticas']} |
| Grafo conexo | {'sim' if r['grafo_conexo'] else 'NÃO'} |
| Fontes externas livres | {rf['total']} ({rf['ativas']} ativas) |

## Ligações críticas

Sem qualquer uma delas, alguma capacidade da solução deixa de existir.

| De | Para | Chave | Para quê |
|---|---|---|---|
""")
    for l in mi.ligacoes_criticas():
        row = l.to_row()
        w(f"| {row['de']} | {row['para']} | `{row['chave']}` | {row['para quê']} |\n")

    w("\n## Receita de montagem\n\nA ordem em que o ETL executa as junções.\n\n")
    w("| # | Passo | Produz | O que faz |\n|---|---|---|---|\n")
    for p in mi.receita_tabela():
        w(f"| {p['ordem']} | {p['passo']} | `{p['produz']}` | {p['o que faz']} |\n")

    w("\n## Todas as entidades\n\n")
    w("| Entidade | Grão | Chave primária | Volume | Usado | Papel |\n"
      "|---|---|---|---|---|---|\n")
    for e in mi.tabela_entidades():
        w(f"| {e['entidade']} | {e['grão']} | `{e['chave primária']}` | "
          f"{e['volume']} | {e['usado']} | {e['papel']} |\n")

    w("\n## Todas as ligações\n\n")
    w("| De | Para | Chave | Cardinalidade | Crítica | Para quê |\n"
      "|---|---|---|---|---|---|\n")
    for l in mi.tabela_ligacoes():
        w(f"| {l['de']} | {l['para']} | `{l['chave']}` | {l['cardinalidade']} | "
          f"{l['crítica']} | {l['para quê']} |\n")

    w("\n## Diagrama\n\n```mermaid\n")
    w(mi.mermaid(somente_criticas=True))
    w("\n```\n\n")
    w("> Acima, apenas as ligações críticas, para legibilidade. O grafo "
      "completo sai de `modelo_integrado.mermaid()` e é desenhado na página "
      "*Documentação* do aplicativo.\n")

    w("\n## Fontes externas\n\n"
      "Todas gratuitas, públicas e livres; nenhuma exige cadastro.\n\n")
    w("| Fonte | Órgão | Categoria | Licença | Liga por | Papel |\n"
      "|---|---|---|---|---|---|\n")
    for f in fe.tabela():
        w(f"| {f['fonte']} | {f['órgão']} | {f['categoria']} | {f['licença']} | "
          f"{f['liga ao Sicor por']} | {f['papel na solução']} |\n")

    return buf.getvalue()


def main() -> int:
    # Sem isto, `python scripts/gerar_doc_modelo.py > log.txt` no Windows
    # morre com UnicodeEncodeError por causa do ✔ da última linha.
    from agrosentinela.utils.logging_setup import _preparar_saida_unicode

    _preparar_saida_unicode()

    texto = gerar()
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(texto, encoding="utf-8")
    print(f"✔ {DESTINO.relative_to(RAIZ)} ({len(texto):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
