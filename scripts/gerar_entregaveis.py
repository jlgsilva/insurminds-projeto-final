#!/usr/bin/env python3
"""
Monta **todos os entregáveis** do Desafio 5 em ``Desafio5_Artefatos/``:

1. diagramas (PNG e SVG);
2. relatório técnico em PDF (com exemplos reais gerados pelo pipeline);
3. catálogo de exemplos de mensagens, por cenário, em Markdown e CSV;
4. exportação dos alertas, envios e rastro de execução;
5. checklist de conformidade com o enunciado;
6. ZIP do código-fonte, pronto para anexar ao e-mail.

    python scripts/gerar_entregaveis.py
    python scripts/gerar_entregaveis.py --com-llm     # usa a Groq, se houver chave
    python scripts/gerar_entregaveis.py --so-zip
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import zipfile
from datetime import date, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "scripts"))

import pandas as pd  # noqa: E402

from agrosentinela import __version__  # noqa: E402
from agrosentinela.data.loader import carregar_base  # noqa: E402
from agrosentinela.orchestrator import Orquestrador  # noqa: E402
from agrosentinela.outbox.store import Outbox  # noqa: E402
from agrosentinela.etl_catalogo import resumo as resumo_catalogo  # noqa: E402
from agrosentinela.filtros import FILTROS  # noqa: E402
from agrosentinela.fontes_externas import resumo as resumo_fontes  # noqa: E402
from agrosentinela.data.modelo_integrado import resumo as resumo_modelo  # noqa: E402
from agrosentinela.personas import (  # noqa: E402
    PERSONAS,
    PERSONAS_POR_CODIGO,
    SETORES,
)
from agrosentinela.projeto_final.clausulas import CLAUSULAS as CLAUSULAS_DO  # noqa: E402
from agrosentinela.rules.engine import MotorRegras  # noqa: E402
from agrosentinela.utils.logging_setup import configurar_logging, get_logger  # noqa: E402

log = get_logger("entregaveis")

ARTEFATOS = RAIZ / "Desafio5_Artefatos"
EXEMPLOS = ARTEFATOS / "exemplos_mensagens"
EXECUCAO = ARTEFATOS / "execucao"

NOME_ZIP = "InsurMinds_Desafio5_AgroSentinela_codigo_fonte.zip"

CENARIOS = [
    ("seca", ["MT", "GO", "BA"], 1.4),
    ("chuva_excessiva", ["PR", "SC", "RS"], 1.3),
    ("chuva_intensa", ["SP", "MG", "PR"], 1.4),
    ("granizo", ["RS", "SP", "MG"], 1.5),
    ("geada", ["RS", "SC", "PR"], 1.4),
    ("onda_calor", ["MT", "MS", "GO"], 1.3),
    ("vendaval", ["RS", "PR", "SC"], 1.4),
]

# O que NÃO entra no ZIP entregue
# O ZIP entregue é **o código-fonte**, e nada além disso — é exatamente o
# mesmo conteúdo que vai para o GitHub. Os documentos de entrega (relatório,
# resumo executivo, exemplos, diagramas) seguem por e-mail em anexo próprio;
# duplicá-los aqui dobraria o tamanho do arquivo e criaria duas versões do
# mesmo documento, sem que nenhuma fosse a definitiva.
EXCLUIR_DIRETORIOS = {
    ".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".ipynb_checkpoints", "node_modules",
    "saida", "raw", "cache_clima", "cache_llm",
    "Desafio5_Artefatos",
}
EXCLUIR_ARQUIVOS = {".env", "secrets.toml", "outbox.sqlite", ".DS_Store",
                    "diagnostico.txt"}
EXCLUIR_SUFIXOS = {".pyc", ".pyo", ".part", ".sqlite-journal", ".sqlite-wal", ".sqlite-shm"}


# ==========================================================================
# 1. Exemplos de mensagens
# ==========================================================================

def gerar_exemplos(usar_llm: bool) -> dict:
    """Executa um cenário por evento e exporta as mensagens produzidas."""
    import tempfile

    EXEMPLOS.mkdir(parents=True, exist_ok=True)
    EXECUCAO.mkdir(parents=True, exist_ok=True)

    base = carregar_base()
    outbox = Outbox(Path(tempfile.mkdtemp()) / "entregaveis.sqlite")
    orq = Orquestrador(base=base, outbox=outbox)

    todas: list[dict] = []
    alertas_todos: list[pd.DataFrame] = []
    envios_todos: list[pd.DataFrame] = []
    indice: list[dict] = []

    for cenario, ufs, intensidade in CENARIOS:
        res = orq.executar(
            horizonte_dias=7, cenario=cenario, intensidade_cenario=intensidade,
            modo_clima="sintetico", filtros={"uf": ufs}, usar_llm=usar_llm,
            max_mensagens=10, respeitar_supressao=False, persistir=False,
        )
        log.info("Cenário %-18s → %4d alertas · %2d mensagens",
                 cenario, len(res.contexto.alertas), len(res.contexto.mensagens))

        # Markdown por cenário
        linhas = [
            f"# Mensagens geradas — cenário «{cenario}»",
            "",
            f"- **Execução:** {res.execucao_id}",
            f"- **UFs:** {', '.join(ufs)} · **intensidade:** {intensidade}",
            f"- **Operações monitoradas:** {len(res.contexto.carteira)}",
            f"- **Alertas gerados:** {len(res.contexto.alertas)}",
            f"- **Origem do texto:** {'IA Generativa (Groq)' if usar_llm else 'template determinístico'}",
            "",
            "> Mensagens produzidas automaticamente pelo pipeline. Nenhuma foi escrita à mão.",
            "",
        ]
        for m in res.contexto.mensagens:
            persona = PERSONAS_POR_CODIGO.get(m.persona)
            linhas += [
                f"## {m.id} · {persona.nome if persona else m.persona}",
                "",
                f"| | |",
                f"|---|---|",
                f"| **Canal** | {m.canal} |",
                f"| **Severidade** | {m.severidade} (score {m.score:.0f}) |",
                f"| **Local** | {m.municipio or '—'} {m.uf} |",
                f"| **Evento** | {m.evento} |",
                f"| **Tamanho** | {m.caracteres} / {m.limite_canal} caracteres |",
                f"| **Origem** | {m.gerado_por} {m.modelo} |",
                f"| **Alertas vinculados** | {len(m.alertas)} |",
                "",
            ]
            if m.assunto:
                linhas += [f"**Assunto:** {m.assunto}", ""]
            linhas += ["```text", m.texto, "```", ""]
            if m.explicacao:
                linhas += [f"*Rastro das regras:* {m.explicacao}", ""]
            linhas += ["---", ""]

            todas.append({
                "cenario": cenario, **m.to_row(), "texto": m.texto,
                "explicacao": m.explicacao,
            })

        arquivo = EXEMPLOS / f"mensagens_{cenario}.md"
        arquivo.write_text("\n".join(linhas), encoding="utf-8")
        indice.append({
            "cenário": cenario,
            "arquivo": arquivo.name,
            "alertas": len(res.contexto.alertas),
            "mensagens": len(res.contexto.mensagens),
            "personas": len({m.persona for m in res.contexto.mensagens}),
        })

        if not res.alertas_df.empty:
            alertas_todos.append(res.alertas_df.assign(cenario=cenario))
        if not res.envios_df.empty:
            envios_todos.append(res.envios_df.assign(cenario=cenario))
        if cenario == "seca":
            res.rastro_df.to_csv(EXECUCAO / "rastro_pipeline.csv", index=False)
            (EXECUCAO / "resumo_execucao.json").write_text(
                json.dumps(res.resumo, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )

    # Consolidados
    pd.DataFrame(todas).to_csv(EXEMPLOS / "todas_as_mensagens.csv", index=False)
    if alertas_todos:
        pd.concat(alertas_todos, ignore_index=True).to_csv(
            EXECUCAO / "alertas.csv", index=False)
    if envios_todos:
        pd.concat(envios_todos, ignore_index=True).to_csv(
            EXECUCAO / "envios_simulados.csv", index=False)

    # Índice legível
    idx = ["# Exemplos de mensagens por cenário climático", "",
           "Um cenário por evento monitorado. Cada arquivo traz as mensagens",
           "efetivamente geradas pelo pipeline, com persona, canal, severidade,",
           "score e rastro das regras.", "",
           "| Cenário | Arquivo | Alertas | Mensagens | Personas |",
           "|---|---|---|---|---|"]
    idx += [
        f"| {i['cenário']} | [{i['arquivo']}]({i['arquivo']}) | {i['alertas']} | "
        f"{i['mensagens']} | {i['personas']} |"
        for i in indice
    ]
    idx += ["", "Consolidado em `todas_as_mensagens.csv`."]
    (EXEMPLOS / "README.md").write_text("\n".join(idx), encoding="utf-8")

    # Catálogo das regras, para quem for avaliar
    motor = MotorRegras()
    pd.DataFrame(motor.resumo()).to_csv(
        ARTEFATOS / "catalogo_regras_negocio.csv", index=False)

    return {"cenarios": indice, "mensagens": len(todas)}


# ==========================================================================
# 2. Checklist de conformidade
# ==========================================================================

def contar_testes() -> int:
    """
    Conta as funções de teste do projeto, lendo os arquivos.

    Escrever esse número à mão num checklist é a forma mais fácil de ele ficar
    errado com o tempo — e um número errado põe em dúvida todos os outros do
    mesmo documento. Testes parametrizados produzem mais casos do que funções,
    então o rótulo no checklist diz "funções de teste", que é o que se conta.
    """
    import re

    total = 0
    for arquivo in sorted((RAIZ / "tests").glob("test_*.py")):
        texto = arquivo.read_text(encoding="utf-8")
        total += len(re.findall(r"^def test_\w+", texto, re.M))
    return total


def gerar_checklist(resumo_exemplos: dict) -> Path:
    motor = MotorRegras()
    n_testes = contar_testes()
    conteudo = f"""# Checklist de conformidade — Desafio 5

Documento de apoio à avaliação. Cada requisito do enunciado, onde ele foi
atendido e como verificar.

Gerado em {datetime.now().strftime('%d/%m/%Y às %H:%M')} · AgroSentinela v{__version__}

---

## Requisitos mínimos

| # | Requisito do enunciado | Atendido em | Como verificar |
|---|---|---|---|
| 1 | Consumir dados de pelo menos uma API pública de informações meteorológicas | `ClimaAgent` + `weather/open_meteo.py` (Open-Meteo) | Página **Radar Climático**; rótulo da fonte em cada série |
| 2 | Identificar automaticamente eventos climáticos relevantes | `EventoAgent` — 8 tipos de evento, escadas de limiares | Página **Radar Climático** → «Eventos identificados» |
| 3 | Aplicar regras de decisão para determinar quem deve ser notificado | `RegrasAgent` + `rules/rules.yaml` ({len(motor.regras)} regras) | Página **Motor de Regras** → catálogo, simulador e disparos |
| 4 | Gerar mensagens personalizadas usando IA ou modelos de linguagem | `RedatorAgent` + `llm/prompts.py` (GroqCloud) | Página **Central de Comunicação** |
| 5 | Simular o envio das notificações | `DespachanteAgent` + `outbox/store.py` | Página **Central de Comunicação** → «Simulação de envio» |
| 6 | Demonstrar o fluxo completo, da obtenção dos dados à comunicação | `Orquestrador` + rastro cronometrado | Página **Início** → rastro da execução |

## Etapas mínimas de desenvolvimento

| Etapa | Implementação |
|---|---|
| 1. Coleta em fonte externa de dados meteorológicos | `ClimaAgent` — Open-Meteo em lote, com deduplicação por célula de grade |
| 2. Identificação de eventos relevantes | `EventoAgent` — ~30 indicadores derivados e escadas de limiares |
| 3. Aplicação de regras de negócio | `RegrasAgent` — motor declarativo com avaliação segura de expressões |
| 4. Geração automática das mensagens | `RedatorAgent` — IA generativa com saída estruturada e revisão |
| 5. Simulação do envio das notificações | `DespachanteAgent` — fila, anti-fadiga, latência, falha e custo |

## Boas práticas recomendadas

| Prática | Como foi atendida |
|---|---|
| Separar claramente coleta, processamento, decisão e comunicação | Seis agentes com responsabilidade única e contrato explícito |
| Utilizar agentes especializados para diferentes responsabilidades | `agents/` — seis do pipeline mais o copiloto |
| Documentar o fluxo da solução | README, `docs/` (5 documentos), página **Documentação** e relatório em PDF |
| Explicar como as regras de negócio foram definidas | `docs/regras_negocio.md` + campo `base_tecnica` em cada regra |
| Demonstrar diferentes tipos de mensagem para diferentes cenários | {len(CENARIOS)} cenários × {len(PERSONAS)} personas × 6 canais — ver `exemplos_mensagens/` |
| Organizar o código em módulos | `src/agrosentinela/` com 9 subpacotes |
| Ocultar chaves de API e credenciais | `.env` no `.gitignore`; leitura por `st.secrets`/ambiente; `.env.example` versionado |

## Entregáveis

| Entregável exigido | Arquivo |
|---|---|
| Relatório técnico em PDF | `InsurMinds_Desafio5_Relatorio_Tecnico.pdf` |
| → **versão editável** do relatório | `InsurMinds_Desafio5_Relatorio_Tecnico.docx` |
| → arquitetura da solução | Seção 4 + Figura 1 |
| → descrição dos agentes desenvolvidos | Seção 5 |
| → tecnologias utilizadas | Seção 6 |
| → fluxo de processamento | Seção 7 (com rastro real de execução) |
| → exemplos das mensagens geradas | Seção 11 |
| Arquivo ZIP com todo o código-fonte | `{NOME_ZIP}` |
| Link para o repositório público no GitHub | Informado no e-mail e no README |

## Documentos complementares (além do exigido)

| Documento | Para quê | Formatos |
|---|---|---|
| Resumo executivo | Explica **o quê, como, por quê, para quais objetivos e quais problemas resolve** — em quatro páginas, para quem não vai ler o relatório técnico | `.md`, `.pdf`, `.docx` |
| Modelo integrado de dados | Como os {resumo_catalogo()['total']} arquivos do BCB se ligam entre si, com chave e cardinalidade de cada junção | `docs/modelo_integrado.md` (gerado a partir do código) |
| Checklist de conformidade | Este documento | `.md` |

> Todo PDF entregue tem a sua versão editável (`.docx`) ao lado, gerada a
> partir da **mesma fonte** — manter dois textos paralelos é a forma mais
> confiável de os dois documentos divergirem com o tempo.

## Considera-se uma entrega completa quando

- [x] A solução consulta uma fonte externa de dados meteorológicos — Open-Meteo, API pública sem chave.
- [x] As regras de negócio são aplicadas corretamente — {len(motor.regras)} regras declarativas, com testes automatizados.
- [x] As mensagens são geradas automaticamente — {resumo_exemplos.get('mensagens', 0)} exemplos produzidos nesta geração, em {len(CENARIOS)} cenários.
- [x] O fluxo completo da solução pode ser demonstrado — rastro cronometrado de cada agente na página inicial.
- [x] O relatório descreve claramente a arquitetura implementada — seções 4 e 5, com diagramas.
- [x] O código-fonte foi entregue — ZIP e repositório público.

## Observações importantes do enunciado

- [x] **Repositório com acesso público** no GitHub.
- [x] **README.md** com instruções de instalação e execução.
- [x] **Licença MIT** declarada no README e no arquivo `LICENSE`.
- [x] **Nenhum envio real** de SMS, e-mail ou push — todo despacho é simulado e marcado como tal.
- [x] **Arquitetura multiagente** (sugerida como dica no enunciado) — implementada com seis agentes especializados.

## Além do mínimo exigido

| Item | Descrição |
|---|---|
| Base de dados real e não trivial | Microdados do Sicor/Proagro do Banco Central — {resumo_catalogo()['total']} arquivos catalogados, **{resumo_catalogo()['usados']} consumidos ({resumo_catalogo()['cobertura_pct']}%)**, ETL completo com validação |
| Modelo de integração explícito | {resumo_modelo()['entidades']} entidades e {resumo_modelo()['ligacoes']} ligações declaradas com chave e cardinalidade, verificadas por teste |
| {len(PERSONAS)} personas em {len(SETORES)} setores | Toda a cadeia do crédito rural **e do seguro**, incluindo profissionais MEI (extensionistas e assessores) |
| {resumo_fontes()['total']} fontes externas gratuitas e públicas | Clima, produção, uso do solo, seguro privado, fogo e seca oficial — **nenhuma exige cadastro**, verificado por teste |
| Alerta em nível de talhão | Geometria WKT das glebas do Sicor substitui o centroide do município na consulta climática |
| Risco expresso em reais | Saldo devedor e vencido por operação, com perda estimada por rendimento do IBGE e preço da CONAB |
| Aderência ao Zarc no escore | Plantio dentro da janela oficial atenua o risco; fora dela, agrava — e a mensagem **explica por quê** |
| Interface responsiva | Celular, tablet e desktop, com alvos de toque adequados e {len(FILTROS)} filtros definidos após analisar os dados |
| Prévia do Projeto Final | Comparador de apólices de D&O com {len(CLAUSULAS_DO)} cláusulas, reaproveitando o mesmo núcleo |
| Fase fenológica | Calculada a partir das datas de plantio e colheita da própria operação |
| Histórico de sinistralidade | Série de COP/RCP do Proagro entra no score de risco |
| Simulador de regras | Calibração interativa dos limiares na própria interface |
| Copiloto com *function calling* | Consulta em linguagem natural sem alucinação de número |
| Política anti-fadiga | Janela de repetição, teto diário, janela de contato por persona |
| Revisão automática das mensagens | Segunda passagem de conformidade por modelo rápido |
| Degradação graciosa | Funciona sem chave de API e sem internet, sinalizando o modo |
| {len(CENARIOS)} cenários climáticos simuláveis | Demonstração de cada regra sem depender do tempo real |
| {n_testes} funções de teste automatizado | Executadas em CI para Python 3.11 e 3.12; com parametrização, mais de {n_testes} casos |
| ETL mensal automatizado | GitHub Actions abre PR com os dados atualizados |
| Privacidade por projeto | Nenhum dado pessoal é usado ou enviado ao modelo |
"""
    caminho = ARTEFATOS / "CHECKLIST_CONFORMIDADE.md"
    caminho.write_text(conteudo, encoding="utf-8")
    return caminho


# ==========================================================================
# 3. ZIP
# ==========================================================================

def _incluir(caminho: Path) -> bool:
    partes = set(caminho.parts)
    if partes & EXCLUIR_DIRETORIOS:
        return False
    if caminho.name in EXCLUIR_ARQUIVOS or caminho.suffix in EXCLUIR_SUFIXOS:
        return False
    # data/raw e caches ficam de fora; data/seed e data/curated entram
    if "data" in caminho.parts:
        i = caminho.parts.index("data")
        if len(caminho.parts) > i + 1 and caminho.parts[i + 1] in {
            "raw", "cache_clima", "cache_llm"
        }:
            return False
    return True


def gerar_zip() -> Path:
    destino = ARTEFATOS / NOME_ZIP
    if destino.exists():
        destino.unlink()

    incluidos = 0
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for caminho in sorted(RAIZ.rglob("*")):
            if not caminho.is_file():
                continue
            relativo = caminho.relative_to(RAIZ)
            if relativo.name == NOME_ZIP:
                continue
            if not _incluir(relativo):
                continue
            arquivo_no_zip = Path("ai_to_so_desafio5_agrosentinela") / relativo
            # Normaliza a permissão gravada no ZIP para 0644 (ou 0755 em
            # scripts executáveis). Sem isto, o ZIP carrega a permissão que o
            # arquivo tinha na máquina que o gerou — e um arquivo restrito
            # extraído no Windows pode acabar ilegível, produzindo um
            # PermissionError na hora de importar o módulo. O defeito é raro,
            # é intermitente e a mensagem não aponta para a causa, o que o
            # torna especialmente caro de diagnosticar.
            info = zipfile.ZipInfo.from_file(caminho, str(arquivo_no_zip))
            executavel = caminho.suffix in {".sh", ".ps1"}
            info.external_attr = (0o755 if executavel else 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, caminho.read_bytes())
            incluidos += 1

    tamanho = destino.stat().st_size / 1e6
    log.info("📦 ZIP gerado: %s (%d arquivos, %.1f MB)", destino.name, incluidos, tamanho)
    return destino


# ==========================================================================
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gera todos os entregáveis do Desafio 5.")
    parser.add_argument("--com-llm", action="store_true",
                        help="Usa a IA generativa nos exemplos (exige GROQ_API_KEY).")
    parser.add_argument("--so-zip", action="store_true",
                        help="Apenas reempacota o código-fonte.")
    parser.add_argument("--sem-relatorio", action="store_true")
    parser.add_argument("--log", default="INFO")
    args = parser.parse_args(argv)

    configurar_logging(args.log)
    ARTEFATOS.mkdir(parents=True, exist_ok=True)

    if args.so_zip:
        gerar_zip()
        return 0

    log.info("═" * 74)
    log.info("  Gerando os entregáveis do Desafio 5 — AgroSentinela v%s", __version__)
    log.info("═" * 74)

    log.info("")
    log.info("[1/7] Diagramas…")
    import gerar_diagramas  # noqa: PLC0415

    gerar_diagramas.main()

    log.info("")
    log.info("[2/7] Exemplos de mensagens (%d cenários)…", len(CENARIOS))
    resumo = gerar_exemplos(args.com_llm)

    log.info("")
    log.info("[3/7] Relatório técnico em PDF e DOCX…")
    if args.sem_relatorio:
        log.info("      (pulado)")
    else:
        import gerar_relatorio  # noqa: PLC0415

        gerar_relatorio.main(["--com-llm"] if args.com_llm else [])

    log.info("")
    log.info("[4/7] Resumo executivo (Markdown, PDF e DOCX)…")
    if args.sem_relatorio:
        log.info("      (pulado)")
    else:
        import gerar_resumo_executivo  # noqa: PLC0415

        gerar_resumo_executivo.main([])

    log.info("")
    log.info("[5/7] Documentação do modelo integrado de dados…")
    import gerar_doc_modelo  # noqa: PLC0415

    gerar_doc_modelo.main()

    log.info("")
    log.info("[6/7] Checklist de conformidade…")
    checklist = gerar_checklist(resumo)
    log.info("      %s", checklist.name)

    log.info("")
    log.info("[7/7] ZIP do código-fonte…")
    gerar_zip()

    log.info("")
    log.info("═" * 74)
    log.info("  Entregáveis em %s", ARTEFATOS)
    log.info("═" * 74)
    for caminho in sorted(ARTEFATOS.rglob("*")):
        if caminho.is_file():
            rel = caminho.relative_to(ARTEFATOS)
            log.info("  %-58s %8.1f KB", str(rel), caminho.stat().st_size / 1024)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
