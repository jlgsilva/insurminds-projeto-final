#!/usr/bin/env python3
"""
Gera o **resumo executivo** do AgroSentinela em Markdown, PDF e DOCX.

Por que existe um documento separado do relatório técnico
---------------------------------------------------------
O relatório técnico responde *"como foi feito"*, em 20 e tantas páginas, para
quem vai avaliar a engenharia. O resumo executivo responde outra pergunta,
para outra pessoa, em quatro páginas:

    O que foi feito, como, por quê, para atender a quais objetivos e
    resolver quais problemas — e o que isso vale para quem usa.

É o documento que se manda antes de uma reunião, que se anexa a um e-mail e
que alguém lê no celular a caminho do escritório. Se não couber em quatro
páginas e não fizer sentido sem o autor ao lado, falhou.

Os números não são escritos à mão: o script **executa o pipeline de verdade**
e lê o catálogo de dados, as regras e as personas diretamente do código. Um
resumo executivo com número desatualizado é pior do que nenhum.

Saídas (todas em ``Desafio5_Artefatos/``):

* ``InsurMinds_Desafio5_Resumo_Executivo.md``   — fonte única do texto
* ``InsurMinds_Desafio5_Resumo_Executivo.pdf``  — para enviar
* ``InsurMinds_Desafio5_Resumo_Executivo.docx`` — para editar

Uso:
    python scripts/gerar_resumo_executivo.py
    python scripts/gerar_resumo_executivo.py --sem-pipeline   # mais rápido
"""

from __future__ import annotations

import argparse
import html as _html
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "scripts"))

from agrosentinela import __version__  # noqa: E402
from agrosentinela import filtros as flt  # noqa: E402
from agrosentinela import fontes_externas as fe  # noqa: E402
from agrosentinela.data import modelo_integrado as mi  # noqa: E402
from agrosentinela.etl_catalogo import PAGINA_FONTE, resumo as resumo_catalogo  # noqa: E402
from agrosentinela.personas import PERSONAS, SETORES  # noqa: E402
from agrosentinela.projeto_final import clausulas as clausulas_do  # noqa: E402
from agrosentinela.rules.catalogo import EVENTOS  # noqa: E402
from agrosentinela.rules.engine import MotorRegras  # noqa: E402
from agrosentinela.utils.formato import inteiro, reais_compacto  # noqa: E402
from agrosentinela.utils.logging_setup import configurar_logging, get_logger  # noqa: E402

from docx_writer import markdown_para_docx  # noqa: E402

log = get_logger("resumo")

ARTEFATOS = RAIZ / "Desafio5_Artefatos"
BASE_NOME = "InsurMinds_Desafio5_Resumo_Executivo"
SAIDA_MD = ARTEFATOS / f"{BASE_NOME}.md"
SAIDA_HTML = ARTEFATOS / f"{BASE_NOME}.html"
SAIDA_PDF = ARTEFATOS / f"{BASE_NOME}.pdf"
SAIDA_DOCX = ARTEFATOS / f"{BASE_NOME}.docx"

AUTOR = "Jefferson Luiz Gonçalves Silva"
REPO = "https://github.com/jlgsilva/ai_to_so_desafio5_agrosentinela"


# ==========================================================================
# Coleta de números reais
# ==========================================================================

def coletar(rodar_pipeline: bool = True) -> dict:
    """Lê o estado real do projeto — nada aqui é digitado à mão."""
    from agrosentinela.data.loader import carregar_base, estatisticas_carteira

    motor = MotorRegras()
    base = carregar_base()
    stats = estatisticas_carteira(base.carteira)

    dados = {
        "versao": __version__,
        "catalogo": resumo_catalogo(),
        "modelo": mi.resumo(),
        "fontes": fe.resumo(),
        "personas": len(PERSONAS),
        "setores": len(SETORES),
        "regras": len(motor.regras),
        "eventos": len(EVENTOS),
        "filtros": len(flt.FILTROS),
        "clausulas_do": len(clausulas_do.CLAUSULAS),
        "origem_base": base.origem,
        "operacoes": stats.get("n_operacoes", 0),
        "municipios": stats.get("n_municipios", 0),
        "valor_carteira": stats.get("valor_total", 0.0),
        "pct_coberto": stats.get("pct_coberto", 0.0),
        "enriquecimentos": base.enriquecimentos(),
        "alertas": 0,
        "criticos": 0,
        "mensagens": 0,
        "exposicao_sinalizada": 0.0,
        "tempo_s": 0.0,
    }

    if rodar_pipeline:
        from agrosentinela.orchestrator import Orquestrador

        log.info("Executando o pipeline para coletar números reais…")
        orq = Orquestrador(base=base)
        res = orq.executar(
            data_ref=date.today(), horizonte_dias=7, cenario="seca",
            intensidade_cenario=1.4, modo_clima="sintetico", usar_llm=False,
            max_mensagens=12, persistir=False, respeitar_supressao=False,
        )
        alertas = res.alertas_df
        dados.update({
            "alertas": len(alertas),
            "criticos": int((alertas["severidade"] == "critico").sum())
            if not alertas.empty else 0,
            "mensagens": len(res.contexto.mensagens),
            "exposicao_sinalizada": float(alertas["valor_credito"].sum())
            if not alertas.empty else 0.0,
            "tempo_s": float(res.resumo.get("duracao_s", 0.0))
            if isinstance(res.resumo, dict) else 0.0,
        })
    return dados


# ==========================================================================
# Texto
# ==========================================================================

def montar_markdown(d: dict) -> str:
    cat, mod, fon = d["catalogo"], d["modelo"], d["fontes"]
    hoje = date.today().strftime("%d/%m/%Y")
    enriquecidos = [k for k, v in d["enriquecimentos"].items() if v]

    return f"""# AgroSentinela — Resumo Executivo

**Desafio 5 — Comunicação Inteligente** · InsurMinds / I2A2
{AUTOR} · {hoje} · versão {d['versao']}
Repositório: {REPO}

---

## Em uma frase

O AgroSentinela transforma os microdados públicos do crédito rural e do
Proagro em **avisos climáticos úteis, dirigidos e auditáveis** — a mensagem
certa, para a pessoa certa, no canal certo, antes do prejuízo.

---

## O problema

O Banco Central publica {cat['total']} arquivos de microdados do Sicor e do
Proagro. Eles contam, operação por operação, o que foi financiado, onde, para
qual cultura, com qual cobertura de risco e o que já deu errado no passado. É
um dos conjuntos de dados agrícolas mais ricos do mundo, e é aberto.

Ainda assim, quando vem uma seca, o produtor descobre tarde. A cooperativa
descobre pelo telefone tocando. O banco descobre na inadimplência. A
seguradora descobre no aviso de sinistro.

Não falta dado. **Falta comunicação.** E há três razões concretas para isso:

1. **Os dados não vêm prontos para conversar entre si.** A tabela principal
   de operações do Sicor **não tem o município** — só o estado. O código IBGE
   mora em outro arquivo. Sem essa junção específica, não existe
   georreferenciamento e, portanto, nenhum aviso pode ser dirigido a ninguém.

2. **O Sicor é retrospectivo.** Ele conta o que já aconteceu. Alerta útil
   precisa de previsão, de normal climática para dar contexto e de
   monitoramento em tempo quase real — nada disso está lá.

3. **Aviso genérico não muda comportamento.** "Previsão de chuva forte no
   Centro-Oeste" não faz ninguém agir. "Sua soja em enchimento de grãos, 340
   ha em Sorriso, com 95 mm previstos contra 26 mm de média histórica, e sem
   cobertura declarada" faz.

---

## O que foi construído

Um **pipeline de seis agentes** encadeados, mais um copiloto conversacional,
que percorre o caminho completo do dado bruto até a mensagem entregue:

| # | Agente | O que faz |
|---|---|---|
| 1 | Carteira | Monta o universo monitorado e calcula a fase fenológica de cada lavoura a partir das datas reais de plantio e colheita do contrato |
| 2 | Clima | Consulta previsão e histórico em fontes públicas, deduplicando por célula de grade para caber na cota gratuita |
| 3 | Evento | Identifica {d['eventos']} tipos de evento climático e mede a severidade por território |
| 4 | Regras | Aplica {d['regras']} regras declarativas e produz um escore de risco de 0 a 100, rastreável até a linha de YAML que o gerou |
| 5 | Redator | Redige a mensagem por IA generativa, a partir de um bloco de fatos fechado |
| 6 | Despachante | Simula o envio, aplica a política anti-fadiga e registra tudo para auditoria |

E uma aplicação web com {len(list(ARTEFATOS.parent.glob('pages/*.py')))} páginas,
publicável no plano gratuito do Streamlit Cloud.

---

## Como foi feito — as cinco decisões que definem a solução

### 1. As regras decidem; o modelo redige

Nenhuma decisão de risco passa pelo modelo de linguagem. O escore, a
severidade, quem é notificado e por qual canal saem de {d['regras']} regras
declarativas em YAML, avaliadas por um interpretador próprio que **nunca usa
`eval`**. O LLM recebe um bloco de fatos fechado e só escreve o texto.

Isso não é preciosismo: numa comunicação que menciona cobertura de risco, um
número inventado é um dano concreto. O produtor pode levar essa mensagem ao
gerente ou ao perito.

### 2. Todos os dados, integrados por um grafo explícito

A solução consome **{cat['usados']} dos {cat['total']} arquivos publicados
({cat['cobertura_pct']}%)**. Os {cat['excluidos_por_privacidade']} de fora são
os de mutuários, deliberadamente excluídos por privacidade — e a exclusão está
registrada no catálogo, não apenas omitida.

O modelo de integração é código executável: {mod['entidades']} entidades,
{mod['ligacoes']} ligações declaradas com chave e cardinalidade, das quais
{mod['ligacoes_criticas']} são críticas. Três descobertas organizam tudo:

- a chave universal do Sicor é o par `(REF_BACEN, NU_ORDEM)`;
- **a operação básica não tem município** — ele vem do arquivo de complemento;
- **o Proagro é uma cadeia de quatro etapas**, não uma tabela: pedido de
  cobertura → perícia → julgamento → pagamento. Medir sinistralidade só pelo
  pedido superestima; só pela perícia ignora o que foi negado.

### 3. Dados externos, todos gratuitos e públicos

{fon['total']} fontes externas complementam o Sicor — clima, produção, uso do
solo, seguro privado, fogo e seca oficial. **Nenhuma exige cadastro, contrato
ou cota paga**, o que era condição do projeto.

Cada conector degrada em três níveis — rede, cache, tabela de referência
embutida — e **o selo de procedência viaja até a tela**. Um valor de
referência nunca é apresentado como se fosse consulta ao vivo.

Duas fontes têm tratamento próprio: fogo (INPE) e chuva medida em solo
(CEMADEN) nunca caem para referência. Sem rede, devolvem "não sei" em vez de
"zero" — um zero inventado esconderia justamente o evento que importa.

### 4. Dezesseis personas, em cinco setores

A mesma informação vira seis mensagens diferentes. O produtor familiar recebe
WhatsApp curto com ação imediata; o gerente de crédito recebe um boletim com a
exposição em reais; o subscritor de seguradora recebe o recorte de carteira; o
extensionista MEI recebe a lista de visitas priorizada.

Setores atendidos: {', '.join(SETORES.keys())}.

### 5. Funciona sem nada instalado

Sem chave de LLM, as mensagens saem por template determinístico. Sem internet,
o clima vem de um gerador sintético rotulado. Sem `pyarrow`, os dados vêm de
CSV comprimido. Sem o ETL rodado, entra uma amostra de demonstração com o
**mesmo esquema** dos dados reais — sempre identificada como tal na interface.

Nenhuma dessas degradações é silenciosa. Todas aparecem na tela.

---

## Para quais objetivos

| Objetivo do Desafio 5 | Como foi atendido |
|---|---|
| Pipeline com múltiplos agentes | 6 agentes encadeados + copiloto, com rastro de execução por etapa |
| Uso de IA generativa | Redação e revisão por LLM sobre fatos fechados, com contingência determinística |
| Aplicação de regras de negócio | {d['regras']} regras declarativas em YAML, versionadas e auditáveis |
| Comunicação dirigida | {d['personas']} personas, 6 canais, limites de tamanho por canal |
| Entrega utilizável | Aplicação web publicável de graça, com {d['filtros']} filtros e mapas em todas as páginas |

---

## Quais problemas isso resolve, e para quem

**Para o produtor rural.** Deixa de receber informação genérica e passa a
receber o que se aplica à sua lavoura, na fase em que ela está, com a ação
possível no prazo que ainda existe. E descobre, antes de precisar, qual é o
motivo de indeferimento mais comum do Proagro no seu município — que é a
informação mais acionável que existe para quem pode vir a abrir um pedido.

**Para a cooperativa e a assistência técnica.** Uma lista de visitas
priorizada por risco e por prazo, em vez de uma planilha de associados.

**Para o banco.** O risco climático deixa de ser hectares e vira reais: saldo
devedor exposto, saldo já vencido, operações renegociadas. E antecipa a
renegociação, em vez de descobrir na inadimplência.

**Para o setor de seguros.** O cruzamento entre a cobertura pública do Proagro
e a penetração do seguro privado subvencionado responde a pergunta comercial
que nenhum dos dois responde sozinho: este município está **descoberto** ou
apenas **protegido por outro instrumento**? A resposta separa oportunidade de
mercado saturado.

**Para a política pública.** Mostra onde o crédito está indo — área
consolidada ou fronteira — e onde a proteção não chegou.

---

## O que a solução já produz hoje

Execução real do pipeline, com um **cenário de seca forçado sobre toda a
carteira** para exercitar as regras de ponta a ponta — por isso a proporção de
alertas críticos é alta; numa previsão real ela seria uma fração disso. Base
de {d['origem_base']}:

- **{inteiro(d['operacoes'])} operações** monitoradas em
  **{inteiro(d['municipios'])} municípios**
- **{inteiro(d['alertas'])} alertas** gerados, dos quais
  **{inteiro(d['criticos'])} críticos**
- **{reais_compacto(d['exposicao_sinalizada'])}** de exposição sinalizada
- **{inteiro(d['mensagens'])} mensagens** redigidas e despachadas
- enriquecimentos ativos: {', '.join(enriquecidos) if enriquecidos else 'nenhum'}

Tudo isso em uma execução de poucos segundos, em uma máquina comum, sem custo.

---

## Governança

- **Nenhum dado pessoal é lido.** Os arquivos de mutuários existem e foram
  deliberadamente excluídos. A solução trabalha em nível de operação, gleba e
  município.
- **Nenhuma promessa de indenização.** O redator é proibido, por regra e por
  revisão automática, de afirmar que um sinistro será coberto.
- **Tudo auditável.** Cada alerta aponta para as regras que o dispararam e
  para os valores que as dispararam; cada mensagem fica registrada com a
  origem — modelo de linguagem ou template.
- **Toda fonte é citada**, com a licença que ela exige.

---

## O caminho para o Projeto Final

A arquitetura foi construída para ser reaproveitada, e a prévia já está no
aplicativo. Para a **Comparação de Apólices de D&O** (06/10/2026), o núcleo
muda de domínio sem mudar de forma: o mesmo motor de regras avalia cláusulas
em vez de clima; o mesmo contrato "as regras decidem, o modelo redige" impede
que um limite de cobertura saia de um modelo de linguagem; as mesmas personas,
rastro e interface.

O que é novo já existe: uma taxonomia de **{d['clausulas_do']} cláusulas** de
D&O com peso por criticidade, e um comparador que detecta o caso mais
perigoso — quando a apólice com melhor escore geral **não** é a melhor nas
cláusulas que decidem um sinistro.

---

*Fonte dos dados: [Tabelas e Microdados do Crédito Rural e do Proagro]({PAGINA_FONTE}) —
Banco Central do Brasil. Fontes externas: {fon['total']} bases públicas e
gratuitas, creditadas na aplicação. Código aberto sob licença MIT.*
"""


# ==========================================================================
# HTML para o PDF
# ==========================================================================

CSS_RESUMO = """
@page { size: A4; margin: 18mm 16mm; }
body { font-family: "DejaVu Sans", Arial, sans-serif; color: #1f2937;
       font-size: 10.5pt; line-height: 1.55; }
h1 { color: #14532d; font-size: 23pt; margin: 0 0 4px; }
h2 { color: #14532d; font-size: 14pt; margin: 22px 0 8px;
     border-bottom: 2px solid #15803d; padding-bottom: 4px; }
h3 { color: #15803d; font-size: 11.5pt; margin: 16px 0 6px; }
p  { margin: 0 0 9px; text-align: justify; }
ul, ol { margin: 0 0 10px 18px; padding: 0; list-style-position: inside; }
li { margin-bottom: 4px; }
strong { color: #14532d; }
hr { border: 0; border-top: 1px solid #d1d5db; margin: 18px 0; }
table { width: 100%; border-collapse: collapse; margin: 10px 0 14px;
        font-size: 9pt; }
th { background: #e8f1ea; color: #14532d; text-align: left;
     padding: 6px 8px; border: 1px solid #c7d2cb; }
td { padding: 6px 8px; border: 1px solid #dde5df; vertical-align: top; }
code { font-family: "DejaVu Sans Mono", monospace; font-size: 9pt;
       color: #9a3412; background: #fdf4ef; padding: 1px 3px;
       border-radius: 3px; }
em { color: #6b7280; }
.capa { text-align: center; padding: 6px 0 14px; }
.capa .sub { color: #6b7280; font-size: 10pt; }
"""


def markdown_para_html(md: str) -> str:
    """Conversão mínima e suficiente para o subconjunto usado neste documento."""
    import re

    linhas = md.split("\n")
    saida: list[str] = []
    i = 0
    em_lista: str | None = None

    def fechar_lista() -> None:
        nonlocal em_lista
        if em_lista:
            saida.append(f"</{em_lista}>")
            em_lista = None

    def inline(t: str) -> str:
        t = _html.escape(t)
        t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
        t = re.sub(r"(?<!\w)\*([^*\n]+)\*(?!\w)", r"<em>\1</em>", t)
        t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
        t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', t)
        return t

    while i < len(linhas):
        linha = linhas[i].rstrip()
        if not linha.strip():
            fechar_lista()
            i += 1
            continue

        if linha.startswith("|") and i + 1 < len(linhas) \
                and set(linhas[i + 1].strip()) <= set("|-: "):
            fechar_lista()
            cabecalho = [c.strip() for c in linha.strip("|").split("|")]
            saida.append("<table><thead><tr>"
                         + "".join(f"<th>{inline(c)}</th>" for c in cabecalho)
                         + "</tr></thead><tbody>")
            i += 2
            while i < len(linhas) and linhas[i].strip().startswith("|"):
                celulas = [c.strip() for c in linhas[i].strip().strip("|").split("|")]
                saida.append("<tr>" + "".join(f"<td>{inline(c)}</td>"
                                              for c in celulas) + "</tr>")
                i += 1
            saida.append("</tbody></table>")
            continue

        if re.fullmatch(r"-{3,}", linha.strip()):
            fechar_lista()
            saida.append("<hr/>")
            i += 1
            continue

        cab = re.match(r"^(#{1,4})\s+(.*)$", linha)
        if cab:
            fechar_lista()
            n = len(cab.group(1))
            saida.append(f"<h{n}>{inline(cab.group(2))}</h{n}>")
            i += 1
            continue

        marcador = re.match(r"^[-*+]\s+(.*)$", linha)
        if marcador:
            if em_lista != "ul":
                fechar_lista()
                saida.append("<ul>")
                em_lista = "ul"
            saida.append(f"<li>{inline(marcador.group(1))}</li>")
            i += 1
            continue

        numerada = re.match(r"^\d+[.)]\s+(.*)$", linha)
        if numerada:
            if em_lista != "ol":
                fechar_lista()
                saida.append("<ol>")
                em_lista = "ol"
            saida.append(f"<li>{inline(numerada.group(1))}</li>")
            i += 1
            continue

        fechar_lista()
        saida.append(f"<p>{inline(linha)}</p>")
        i += 1

    fechar_lista()
    corpo = "\n".join(saida)
    return (
        '<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8"/>'
        "<title>AgroSentinela — Resumo Executivo</title>"
        f"<style>{CSS_RESUMO}</style></head><body>{corpo}</body></html>"
    )


# ==========================================================================
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gera o resumo executivo em Markdown, PDF e DOCX.")
    parser.add_argument("--sem-pipeline", action="store_true",
                        help="Não executa o pipeline (números de execução ficam zerados).")
    parser.add_argument("--log", default="INFO")
    args = parser.parse_args(argv)

    configurar_logging(args.log)
    ARTEFATOS.mkdir(parents=True, exist_ok=True)

    dados = coletar(rodar_pipeline=not args.sem_pipeline)
    markdown = montar_markdown(dados)

    SAIDA_MD.write_text(markdown, encoding="utf-8")
    log.info("📝 Markdown: %s (%.0f KB)", SAIDA_MD.name,
             SAIDA_MD.stat().st_size / 1024)

    SAIDA_HTML.write_text(markdown_para_html(markdown), encoding="utf-8")
    log.info("🌐 HTML: %s", SAIDA_HTML.name)

    # PDF — reaproveita a conversão já usada pelo relatório técnico.
    import gerar_relatorio  # noqa: PLC0415

    if gerar_relatorio.html_para_pdf(SAIDA_HTML, SAIDA_PDF):
        log.info("📄 PDF: %s (%.0f KB)", SAIDA_PDF.name,
                 SAIDA_PDF.stat().st_size / 1024)
    else:
        log.warning("PDF não gerado (wkhtmltopdf ausente). O HTML e o DOCX "
                    "continuam disponíveis.")

    resultado = markdown_para_docx(
        markdown, SAIDA_DOCX,
        titulo="AgroSentinela — Resumo Executivo",
        autor=AUTOR,
        assunto="Desafio 5 — Comunicação Inteligente (InsurMinds/I2A2)",
    )
    log.info("📘 DOCX editável: %s", resultado)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
