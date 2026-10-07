#!/usr/bin/env python3
"""
Gera o **relatório técnico em PDF** exigido pelo Desafio 5.

O relatório não é escrito à mão: executa o pipeline de verdade (em modo
offline e determinístico) e incorpora as métricas e as **mensagens
realmente geradas**. Assim o documento nunca fica desatualizado em relação
ao código.

    python scripts/gerar_relatorio.py
    python scripts/gerar_relatorio.py --com-llm     # usa a Groq, se houver chave

Conversão para PDF: ``wkhtmltopdf`` quando disponível; caso contrário
``reportlab``; em último caso, entrega o HTML.
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import pandas as pd  # noqa: E402

from agrosentinela import __version__  # noqa: E402
from agrosentinela.data.loader import carregar_base, estatisticas_carteira  # noqa: E402
from agrosentinela.etl_catalogo import PAGINA_FONTE, resumo as resumo_catalogo  # noqa: E402
from agrosentinela.orchestrator import Orquestrador  # noqa: E402
from agrosentinela.outbox.store import Outbox  # noqa: E402
from agrosentinela import fontes_externas  # noqa: E402
from agrosentinela.filtros import FILTROS  # noqa: E402
from agrosentinela.projeto_final.clausulas import (  # noqa: E402
    CLAUSULAS as CLAUSULAS_DO,
    GRUPOS_CLAUSULA,
)
from agrosentinela.data import modelo_integrado  # noqa: E402
from agrosentinela.personas import (  # noqa: E402
    PERSONAS,
    PERSONAS_POR_CODIGO,
    SETORES,
)
from agrosentinela.rules.catalogo import EVENTOS  # noqa: E402
from agrosentinela.rules.engine import MotorRegras  # noqa: E402
from agrosentinela.utils.formato import (  # noqa: E402
    data_br,
    hectares,
    inteiro,
    pct,
    reais_compacto,
)
from agrosentinela.utils.logging_setup import configurar_logging, get_logger

log = get_logger("relatorio")

ARTEFATOS = RAIZ / "Desafio5_Artefatos"
DIAGRAMAS = ARTEFATOS / "diagramas"
SAIDA_HTML = ARTEFATOS / "InsurMinds_Desafio5_Relatorio_Tecnico.html"
SAIDA_PDF = ARTEFATOS / "InsurMinds_Desafio5_Relatorio_Tecnico.pdf"
SAIDA_DOCX = ARTEFATOS / "InsurMinds_Desafio5_Relatorio_Tecnico.docx"

AUTOR = "Jefferson Luiz Gonçalves Silva"
REPO = "https://github.com/jlgsilva/ai_to_so_desafio5_agrosentinela"

CENARIOS_DEMO = [
    ("seca", "MT GO BA".split(), 1.4),
    ("geada", "RS SC PR".split(), 1.3),
    ("granizo", "RS SP MG".split(), 1.5),
    ("chuva_excessiva", "PR SC RS".split(), 1.3),
    ("onda_calor", "MT MS GO".split(), 1.3),
]


# ==========================================================================
# CSS
# ==========================================================================
CSS = """
@page { size: A4; margin: 20mm 16mm 18mm 16mm; }
* { box-sizing: border-box; }
body {
  font-family: "DejaVu Sans", "Segoe UI", Arial, sans-serif;
  font-size: 10.2pt; line-height: 1.55; color: #1e293b; margin: 0;
}
h1, h2, h3, h4 { color: #14532d; line-height: 1.25; margin: 0 0 .45em; }
h1 { font-size: 21pt; }
h2 { font-size: 15pt; border-bottom: 2.5px solid #15803d; padding-bottom: 5px;
     margin-top: 26px; page-break-after: avoid; }
h3 { font-size: 12pt; margin-top: 18px; color: #166534; page-break-after: avoid; }
h4 { font-size: 10.6pt; margin-top: 13px; color: #334155; }
p  { margin: 0 0 .7em; text-align: justify; }
/* wkhtmltopdf com Qt não-patched corta marcadores 'outside'; 'inside' garante que o número apareça inteiro. */
ul, ol { margin: 0 0 .8em 0; padding-left: .4em; list-style-position: inside; }
li { padding-left: .35em; }
li { margin-bottom: .3em; }
code { font-family: "DejaVu Sans Mono", monospace; font-size: 8.8pt;
       background: #f1f5f9; padding: 1px 4px; border-radius: 3px; }
pre { background: #f8fafc; border: 1px solid #e2e8f0; border-left: 3px solid #15803d;
      border-radius: 5px; padding: 9px 11px; font-family: "DejaVu Sans Mono", monospace;
      font-size: 8.2pt; line-height: 1.42; white-space: pre-wrap; overflow-wrap: break-word;
      page-break-inside: avoid; margin: 0 0 .9em; }
table { width: 100%; border-collapse: collapse; margin: 0 0 1em; font-size: 8.8pt;
        page-break-inside: avoid; }
th { background: #15803d; color: #fff; text-align: left; padding: 6px 8px;
     font-weight: 600; }
td { padding: 5px 8px; border-bottom: 1px solid #e2e8f0; vertical-align: top; }
tr:nth-child(even) td { background: #f8fafc; }
img { max-width: 100%; }

.capa { text-align: center; padding-top: 52mm; page-break-after: always; }
.capa .selo { display: inline-block; background: #dcfce7; color: #14532d;
   border: 2px solid #15803d; border-radius: 999px; padding: 5px 20px;
   font-size: 9.5pt; font-weight: 700; letter-spacing: .05em; }
.capa h1 { font-size: 34pt; margin: 22px 0 6px; }
.capa .sub { font-size: 14pt; color: #166534; margin-bottom: 30px; }
.capa .desc { font-size: 10.5pt; color: #475569; max-width: 135mm;
   margin: 0 auto 34px; line-height: 1.65; }
.capa .meta { font-size: 10pt; color: #334155; line-height: 1.85; }

.destaque { background: #f0fdf4; border-left: 4px solid #15803d;
  padding: 11px 14px; border-radius: 0 6px 6px 0; margin: 0 0 1em;
  page-break-inside: avoid; }
.atencao { background: #fffbeb; border-left: 4px solid #d97706;
  padding: 11px 14px; border-radius: 0 6px 6px 0; margin: 0 0 1em;
  page-break-inside: avoid; }

.kpis { display: table; width: 100%; margin-bottom: 14px; border-spacing: 7px 0; }
.kpi { display: table-cell; width: 25%; background: #f0fdf4; border: 1px solid #bbf7d0;
  border-radius: 7px; padding: 10px; text-align: center; }
.kpi .v { font-size: 16pt; font-weight: 700; color: #14532d; display: block; }
.kpi .r { font-size: 7.6pt; color: #475569; text-transform: uppercase;
  letter-spacing: .04em; }

.msg { border: 1px solid #cbd5e1; border-left: 5px solid #15803d; border-radius: 6px;
  padding: 11px 13px; margin: 0 0 13px; page-break-inside: avoid; background: #fff; }
.msg.critico { border-left-color: #b91c1c; }
.msg.alerta  { border-left-color: #ea580c; }
.msg.atencao { border-left-color: #f59e0b; }
.msg .cab { font-size: 8.4pt; color: #475569; margin-bottom: 7px; }
.msg .cab b { color: #0f172a; }
.msg .corpo { font-family: "DejaVu Sans Mono", monospace; font-size: 8.3pt;
  white-space: pre-wrap; line-height: 1.48; background: #f8fafc; padding: 9px 10px;
  border-radius: 4px; }
.tag { display: inline-block; background: #e2e8f0; color: #334155; border-radius: 4px;
  padding: 1px 6px; font-size: 7.6pt; margin-right: 4px; }
.tag.sev { color: #fff; }
.tag.critico { background: #b91c1c; } .tag.alerta { background: #ea580c; }
.tag.atencao { background: #f59e0b; } .tag.informativo { background: #94a3b8; }

figure { margin: 0 0 1.1em; text-align: center; page-break-inside: avoid; }
figcaption { font-size: 8.4pt; color: #64748b; margin-top: 5px; font-style: italic; }
.quebra { page-break-before: always; }
.sumario ol { list-style: none; padding-left: 0; counter-reset: s; }
.sumario > ol > li { counter-increment: s; margin-bottom: 5px; font-weight: 600; }
.sumario > ol > li::before { content: counter(s) ". "; color: #15803d; }
.sumario ol ol { padding-left: 1.4em; margin-top: 3px; }
.sumario ol ol li { font-weight: 400; font-size: 9.4pt; color: #475569; }
.rodape { margin-top: 26px; padding-top: 9px; border-top: 1px solid #e2e8f0;
  font-size: 8.2pt; color: #64748b; text-align: center; }
"""


def esc(t) -> str:
    return html.escape(str(t))


def tabela_html(linhas: list[dict], colunas: list[str] | None = None) -> str:
    if not linhas:
        return "<p><em>Sem dados.</em></p>"
    colunas = colunas or list(linhas[0].keys())
    cab = "".join(f"<th>{esc(c)}</th>" for c in colunas)
    corpo = "".join(
        "<tr>" + "".join(f"<td>{l.get(c, '')}</td>" for c in colunas) + "</tr>"
        for l in linhas
    )
    return f"<table><thead><tr>{cab}</tr></thead><tbody>{corpo}</tbody></table>"


def figura(nome: str, legenda: str) -> str:
    caminho = DIAGRAMAS / nome
    if not caminho.exists():
        return ""
    return (
        f'<figure><img src="{caminho.as_uri()}" alt="{esc(legenda)}">'
        f"<figcaption>{esc(legenda)}</figcaption></figure>"
    )


# ==========================================================================
# Execução demonstrativa
# ==========================================================================

def executar_demonstracoes(usar_llm: bool) -> tuple[dict, list]:
    """Roda o pipeline em vários cenários e devolve métricas e mensagens."""
    import tempfile

    base = carregar_base()
    outbox = Outbox(Path(tempfile.mkdtemp()) / "relatorio.sqlite")
    orq = Orquestrador(base=base, outbox=outbox)

    principal = orq.executar(
        horizonte_dias=7, cenario="seca", intensidade_cenario=1.4,
        modo_clima="sintetico", filtros={"uf": CENARIOS_DEMO[0][1]},
        usar_llm=usar_llm, max_mensagens=10,
        respeitar_supressao=False, persistir=False,
    )

    mensagens: list = []
    vistos: set[tuple[str, str]] = set()
    for cenario, ufs, intensidade in CENARIOS_DEMO:
        res = orq.executar(
            horizonte_dias=7, cenario=cenario, intensidade_cenario=intensidade,
            modo_clima="sintetico", filtros={"uf": ufs},
            usar_llm=usar_llm, max_mensagens=8,
            respeitar_supressao=False, persistir=False,
        )
        for m in res.contexto.mensagens:
            chave = (m.persona, m.canal)
            if chave in vistos:
                continue
            vistos.add(chave)
            mensagens.append((cenario, m))
        log.info("Cenário %-16s → %d alertas, %d mensagens",
                 cenario, len(res.contexto.alertas), len(res.contexto.mensagens))

    return {"principal": principal, "base": base}, mensagens


# ==========================================================================
# Montagem do HTML
# ==========================================================================

def montar_html(contexto: dict, mensagens: list, usar_llm: bool) -> str:
    res = contexto["principal"]
    base = contexto["base"]
    motor = MotorRegras()
    stats = estatisticas_carteira(base.carteira)
    hoje = date.today()
    alertas = res.alertas_df

    # ---------------------------------------------------------- blocos
    capa = f"""
<div class="capa">
  <div class="selo">DESAFIO 5 · COMUNICAÇÃO INTELIGENTE</div>
  <h1>AgroSentinela</h1>
  <div class="sub">Inteligência climática e comunicação proativa<br>
       para crédito rural e Proagro</div>
  <div class="desc">
    Uma solução multiagente que cruza os microdados abertos do crédito rural
    e do Proagro do Banco Central do Brasil com previsão meteorológica
    pública, identifica quais operações estão sob risco climático e gera,
    com IA generativa, comunicação preventiva personalizada para dezesseis perfis
    da cadeia do agronegócio.
  </div>
  <div class="meta">
    <b>Relatório técnico</b><br>
    {esc(AUTOR)}<br>
    Curso InsurMinds — Inteligência Artificial Aplicada a Seguros<br>
    Instituto de Inteligência Artificial Aplicada — I2A2<br><br>
    Versão {esc(__version__)} · {data_br(hoje)}<br>
    <span style="font-size:9pt">{esc(REPO)}</span>
  </div>
</div>"""

    sumario = """
<h2>Sumário</h2>
<div class="sumario"><ol>
  <li>Sumário executivo
    <ol><li>Atendimento ao enunciado</li></ol></li>
  <li>O problema e a oportunidade</li>
  <li>Público-alvo: dezesseis personas em cinco setores</li>
  <li>Arquitetura da solução
    <ol><li>Visão geral</li><li>Decisões arquiteturais</li><li>Tolerância a falhas</li></ol></li>
  <li>Descrição dos agentes desenvolvidos</li>
  <li>Tecnologias utilizadas</li>
  <li>Fluxo de processamento</li>
  <li>Fontes de dados e engenharia de dados
    <ol><li>O catálogo do Banco Central</li><li>O modelo integrado</li>
        <li>Fontes externas gratuitas e públicas</li></ol></li>
  <li>Regras de negócio e score de risco</li>
  <li>Uso de Inteligência Artificial Generativa</li>
  <li>Exemplos das mensagens geradas</li>
  <li>Resultados da execução demonstrativa</li>
  <li>Qualidade e testes</li>
  <li>Privacidade, limitações e evolução</li>
  <li>Como executar</li>
  <li>Referências</li>
</ol></div>"""

    # ------------------------------------------------------ 1. executivo
    n_paginas = len(list(RAIZ.glob("pages/*.py"))) + 1
    n_testes = sum(
        len(re.findall(r"^def test_\w+", arq.read_text(encoding="utf-8"), re.M))
        for arq in sorted((RAIZ / "tests").glob("test_*.py"))
    )

    tabela_conformidade = tabela_html(
        [
            {"Requisito mínimo do enunciado": "Consumir dados de pelo menos uma "
             "API pública de informações meteorológicas",
             "Onde está": "<code>ClimaAgent</code> + <code>weather/open_meteo.py</code> — "
             "API pública Open-Meteo, sem chave",
             "Como verificar": "Página <b>Radar Climático</b>: a fonte de cada série "
             "aparece rotulada"},
            {"Requisito mínimo do enunciado": "Identificar automaticamente eventos "
             "climáticos relevantes",
             "Onde está": f"<code>EventoAgent</code> — {len(EVENTOS)} tipos de evento, "
             "com escadas de limiares",
             "Como verificar": "Página <b>Radar Climático</b> → «Eventos identificados»"},
            {"Requisito mínimo do enunciado": "Aplicar regras de decisão para "
             "determinar quem deve ser notificado",
             "Onde está": f"<code>RegrasAgent</code> + <code>rules.yaml</code> — "
             f"{len(motor.regras)} regras declarativas",
             "Como verificar": "Página <b>Motor de Regras</b>: catálogo, simulador "
             "e auditoria dos disparos"},
            {"Requisito mínimo do enunciado": "Gerar mensagens personalizadas com "
             "IA ou modelos de linguagem",
             "Onde está": "<code>RedatorAgent</code> + GroqCloud, com contingência "
             "determinística",
             "Como verificar": "Página <b>Central de Comunicação</b>: cada mensagem "
             "traz a origem (IA ou modelo de texto)"},
            {"Requisito mínimo do enunciado": "Simular o envio das notificações",
             "Onde está": "<code>DespachanteAgent</code> + <code>outbox/store.py</code> — "
             "nenhum envio real",
             "Como verificar": "Página <b>Central de Comunicação</b> → «Simulação de envio»"},
            {"Requisito mínimo do enunciado": "Demonstrar o fluxo completo, da "
             "obtenção dos dados à comunicação",
             "Onde está": "<code>Orquestrador</code>, com rastro cronometrado por agente",
             "Como verificar": "Página <b>Início</b>: o rastro das seis etapas após "
             "uma execução"},
        ],
        ["Requisito mínimo do enunciado", "Onde está", "Como verificar"],
    )

    executivo = f"""
<h2>1. Sumário executivo</h2>
<div class="destaque">
<b>Em uma frase:</b> o AgroSentinela transforma dado público que já existe —
todas as operações de crédito rural contratadas no Brasil — em aviso útil
que chega ao produtor <i>antes</i> do evento climático.
</div>

<p>A relação entre seguradora, banco e produtor rural quase sempre começa
<b>depois</b> do sinistro. A chuva já caiu, a geada já queimou o cafezal, a
seca já comprometeu o enchimento de grãos. A partir daí resta administrar a
perda: perícia, comprovação, indenização, renegociação.</p>

<p>O Banco Central publica, em dados abertos, os microdados do Sistema de
Operações do Crédito Rural e do Proagro (Sicor): município, cultura, área,
valor financiado, <b>janela de plantio e de colheita de cada operação</b>,
tipo de cobertura, irrigação — além do histórico completo de acionamento do
Proagro. Cruzando isso com previsão meteorológica pública é possível
responder, antes do evento, quem está exposto a qual fenômeno, em qual fase
da lavoura, com quanto de dinheiro em risco e com ou sem cobertura.</p>

<p>A solução implementa esse cruzamento em um pipeline de <b>seis agentes
especializados</b>, aplica <b>{len(motor.regras)} regras de negócio
declarativas</b> e gera comunicação personalizada para <b>dezesseis personas</b>
em seis canais, com simulação completa do despacho. Tudo com ferramentas
gratuitas: dados abertos do BCB, API pública Open-Meteo, camada gratuita da
GroqCloud e Streamlit Community Cloud.</p>

<div class="kpis">
  <div class="kpi"><span class="v">6</span><span class="r">agentes especializados</span></div>
  <div class="kpi"><span class="v">{len(motor.regras)}</span><span class="r">regras de negócio</span></div>
  <div class="kpi"><span class="v">{len(PERSONAS)}</span><span class="r">personas atendidas</span></div>
  <div class="kpi"><span class="v">{len(EVENTOS)}</span><span class="r">eventos climáticos</span></div>
</div>
<div class="kpis">
  <div class="kpi"><span class="v">{n_paginas}</span><span class="r">páginas na aplicação</span></div>
  <div class="kpi"><span class="v">6</span><span class="r">canais de comunicação</span></div>
  <div class="kpi"><span class="v">{n_testes}</span><span class="r">testes automatizados</span></div>
  <div class="kpi"><span class="v">{resumo_catalogo()['total']}</span><span class="r">arquivos do BCB catalogados</span></div>
</div>

<h3>1.1 Atendimento ao enunciado</h3>

<p>O enunciado do Desafio 5 pede um protótipo que monitore eventos externos e
gere comunicação preventiva para segurados. Esta solução aplica esse conceito
ao <b>seguro agrícola brasileiro</b>: o Proagro — o programa público que cobre
perdas de lavoura por evento climático — e o crédito rural que ele protege.
É o mesmo problema do enunciado (a relação que só começa depois do sinistro),
no setor em que os dados públicos permitem resolvê-lo com precisão de
operação individual.</p>

{tabela_conformidade}

<p>Todos os requisitos mínimos estão atendidos e podem ser verificados na
aplicação publicada, sem instalar nada.</p>

<h3>O que muda na prática</h3>
{tabela_html([
    {"Alerta genérico": "«Risco de geada no Sul nos próximos dias.»",
     "Alerta do AgroSentinela": "«Sua lavoura de café em Patrocínio-MG, 42 ha, está em brotação — fase que define a safra seguinte. Mínima prevista de 1,2 °C na madrugada de quinta. Sua operação consta com Proagro; registre a ocorrência com data e fotos. Regra R-GEA-02.»"},
], ["Alerta genérico", "Alerta do AgroSentinela"])}
"""

    # ------------------------------------------------------ 2. problema
    problema = f"""
<h2>2. O problema e a oportunidade</h2>

<h3>2.1 O modelo reativo e o seu custo</h3>
<p>O crédito rural brasileiro movimenta centenas de bilhões de reais por
safra. O Proagro é o mecanismo público que exonera o produtor de obrigações
financeiras quando há perda por evento climático coberto. Ambos operam,
hoje, de forma predominantemente <b>reativa</b>: o contato acontece na
comunicação de perda.</p>

<p>Três consequências decorrem disso:</p>
<ol>
  <li><b>Para o produtor</b>, a perda que poderia ser mitigada — antecipar a
  colheita, acionar irrigação, recolher máquinas — se materializa.</li>
  <li><b>Para o credor</b>, a inadimplência aparece sem aviso, quando já não
  há espaço para prorrogação negociada.</li>
  <li><b>Para o garantidor</b>, a demanda por perícia chega concentrada,
  exatamente quando a capacidade operacional está saturada.</li>
</ol>

<h3>2.2 O ativo subutilizado</h3>
<p>O que torna este projeto possível é uma característica pouco explorada
dos microdados do Sicor: eles descrevem <b>a lavoura</b>, não apenas o
contrato.</p>

{tabela_html([
    {"Campo do Sicor": "<code>CD_IBGE_MUNICIPIO</code>", "O que permite": "Localizar a operação na grade meteorológica"},
    {"Campo do Sicor": "<code>DT_INIC_PLANTIO</code> / <code>DT_INIC_COLHEITA</code>", "O que permite": "Calcular a <b>fase fenológica de hoje</b> — o coração da solução"},
    {"Campo do Sicor": "<code>CD_EMPREENDIMENTO</code> → Produto", "O que permite": "Saber a cultura e a sua sensibilidade a cada evento"},
    {"Campo do Sicor": "<code>CD_TIPO_SEGURO</code>", "O que permite": "Distinguir Proagro, seguro privado e ausência de cobertura"},
    {"Campo do Sicor": "<code>CD_TIPO_IRRIGACAO</code>", "O que permite": "Separar sequeiro de irrigado nas regras de seca"},
    {"Campo do Sicor": "<code>VL_PARC_CREDITO</code>, <code>VL_AREA_FINANC</code>", "O que permite": "Dimensionar a exposição financeira e física"},
    {"Campo do Sicor": "<code>DT_VENCIMENTO</code>", "O que permite": "Antecipar risco de prorrogação e inadimplência"},
    {"Campo do Sicor": "<code>CD_PROGRAMA</code> (Pronaf/Pronamp)", "O que permite": "Derivar a persona e o tom da comunicação"},
    {"Campo do Sicor": "<code>SICOR_COP_BASICO</code> / <code>RCP_BASICO</code>", "O que permite": "Medir a recorrência histórica de cada evento por município"},
], ["Campo do Sicor", "O que permite"])}

<div class="destaque">
Saber que <i>vai gear no Sul</i> não muda decisão nenhuma. Saber que
<i>aquela</i> operação de café, em brotação, com 42 ha financiados e sem
seguro privado, está na área da geada — muda.
</div>
"""

    # ------------------------------------------------------ 3. personas
    linhas_personas = [
        {
            "Persona": f"<b>{esc(p.nome)}</b>",
            "Papel": esc(p.papel_na_cadeia),
            "Canal": esc(p.canal_padrao),
            "Sev. mín.": esc(p.severidade_minima),
            "Decisão que a mensagem habilita": esc(p.decisao_alvo),
        }
        for p in PERSONAS
    ]
    n_personas = len(PERSONAS)
    n_setores = len(SETORES)
    setores_lista = ", ".join(f"<b>{esc(nome)}</b>" for nome in SETORES)
    personas = f"""
<h2 class="quebra">3. Público-alvo: dezesseis personas em cinco setores</h2>

<p>O enunciado pede mensagens personalizadas para diferentes perfis de
segurados. A solução vai além do segurado e modela <b>toda a cadeia</b> que
decide sobre risco agrícola — porque o alerta só vira ação quando chega a
quem pode agir.</p>

<p>São {n_personas} personas, organizadas em {n_setores} setores:
{setores_lista}. A ampliação em relação ao primeiro recorte foi deliberada e
atende a dois públicos que o modelo inicial deixava de fora:</p>

<ul>
  <li><b>Profissionais autônomos e MEIs</b> — extensionistas rurais e
  assessores que prestam serviço a dezenas de produtores. Não têm carteira
  própria, mas são quem efetivamente vai a campo, e uma lista de visitas
  priorizada por risco vale mais para eles do que qualquer painel.</li>
  <li><b>O setor de seguros por inteiro</b> — não apenas subscrição, mas
  também perícia e regulação de sinistro, atuária e precificação, área
  comercial e corretagem. Cada um desses papéis lê o mesmo dado procurando
  coisas diferentes: o perito quer a evidência documental, o atuário quer a
  sinistralidade comparada ao mercado, o comercial quer o município
  descoberto.</li>
</ul>

{tabela_html(linhas_personas, ["Persona", "Papel", "Canal", "Sev. mín.",
                               "Decisão que a mensagem habilita"])}

<h3>3.1 A persona é derivada do dado, não escolhida à mão</h3>
<p>A classificação segue a precedência abaixo, aplicada sobre os campos
reais da operação:</p>
<ol>
  <li><code>CategoriaEmitente</code> indicando cooperativa, condomínio ou
      associação → <b>Cooperativa</b></li>
  <li><code>Programa</code> contendo Pronaf → <b>Produtor familiar</b></li>
  <li><code>Programa</code> contendo Pronamp → <b>Produtor empresarial</b></li>
  <li>Sem programa identificável → desempate por porte
      (<code>VL_PARC_CREDITO</code> e <code>VL_AREA_FINANC</code>)</li>
</ol>

<p>As cinco personas institucionais não vêm da operação: recebem
<b>boletins consolidados</b>, e cada regra declara quais delas devem ser
acionadas pelo alerta que ela originou.</p>

<h3>3.2 Contratos por canal</h3>
{tabela_html([
    {"Canal": "SMS", "Limite": "320 caracteres", "Custo simulado": "R$ 0,0850", "Uso típico": "Produtor familiar sem conexão estável"},
    {"Canal": "WhatsApp", "Limite": "700 caracteres", "Custo simulado": "R$ 0,0450", "Uso típico": "Produtor familiar e assistência técnica"},
    {"Canal": "Push", "Limite": "180 caracteres", "Custo simulado": "R$ 0,0008", "Uso típico": "Aviso rápido com janela de ação curta"},
    {"Canal": "E-mail", "Limite": "2.200 caracteres", "Custo simulado": "R$ 0,0012", "Uso típico": "Produtor empresarial, cooperativa, corretor"},
    {"Canal": "Painel", "Limite": "1.600 caracteres", "Custo simulado": "—", "Uso típico": "Banco, seguradora, gestor público"},
    {"Canal": "Voz", "Limite": "550 caracteres", "Custo simulado": "R$ 0,3200", "Uso típico": "Contingência para baixa conectividade"},
], ["Canal", "Limite", "Custo simulado", "Uso típico"])}
"""

    # ------------------------------------------------------ 4. arquitetura
    n_filtros = len(FILTROS)
    arquitetura = f"""
<h2 class="quebra">4. Arquitetura da solução</h2>

<h3>4.1 Visão geral</h3>
{figura("arquitetura_pipeline.png", "Figura 1 — Pipeline multiagente do AgroSentinela.")}

<p>A solução é um pipeline determinístico de seis agentes, encadeados por um
orquestrador que mantém um estado compartilhado (<code>Contexto</code>) e
registra o rastro cronometrado de cada etapa. Um sétimo componente, o
copiloto, fica fora do pipeline e serve à consulta em linguagem natural.</p>

<h3>4.2 Decisões arquiteturais</h3>

<h4>Por que seis agentes, e não um script</h4>
<p>Cada fronteira entre agentes corresponde a uma mudança real de
responsabilidade e de fonte de verdade. A classe base captura exceções: se o
agente de clima falhar, os demais continuam e a interface mostra exatamente
onde parou. Um pipeline monolítico simplesmente quebraria.</p>

<h4>Por que não LangGraph, CrewAI ou AutoGen</h4>
<p>Para um fluxo determinístico de seis etapas, sem ramificação condicional
nem negociação entre agentes, um framework de orquestração adiciona
dependências pesadas (problemáticas no contêiner gratuito do Streamlit
Cloud), indireção que esconde justamente o que o desafio pede para
demonstrar, e risco de incompatibilidade de versões. O contrato
<code>Agente.executar(Contexto) → Contexto</code> é exatamente a assinatura
de um nó de grafo: migrar seria uma troca mecânica.</p>

<h4>Por que as regras ficam em YAML, e não em código</h4>
<p>Quem entende de crédito rural não necessariamente programa. Com as regras
em texto versionado, o especialista lê, revisa e propõe alteração de limiar
sem tocar em Python — e o histórico de mudanças fica no controle de versão.</p>

<h4>Por que o modelo de linguagem não decide nada</h4>
<p>A decisão precisa ser idêntica em duas execuções e explicável a um
auditor. O modelo redige; as regras decidem.</p>

<h3>4.3 Camadas</h3>
<pre>┌──────────────────────────────────────────────────────────┐
│ Interface (Streamlit)   app.py · pages/ · ui.py · viz/   │
├──────────────────────────────────────────────────────────┤
│ Orquestração            orchestrator.py                  │
├──────────────────────────────────────────────────────────┤
│ Agentes                 agents/*.py                      │
├──────────────────────────────────────────────────────────┤
│ Domínio                 rules/ · personas.py · models.py │
├──────────────────────────────────────────────────────────┤
│ Integrações  weather/ llm/  │  Persistência  data/ outbox/│
├──────────────────────────────────────────────────────────┤
│ Fontes externas  Sicor/BCB · Open-Meteo · GroqCloud      │
└──────────────────────────────────────────────────────────┘</pre>
<p>Nenhuma camada superior é importada por uma inferior. O núcleo <b>não
importa Streamlit</b> — é por isso que o mesmo pipeline roda na interface,
na linha de comando, nos testes e na integração contínua.</p>

<h3>4.5 Interface: três contextos de uso, não um só</h3>

<p>A solução é consultada em três situações muito diferentes: <b>no celular</b>,
por produtor, extensionista e técnico em campo — muitas vezes com uma mão só,
sol na tela e conexão ruim; <b>no tablet</b>, por assessor e perito em visita;
<b>no desktop</b>, por analista de crédito, atuário e gestor público.</p>

<p>Por isso o layout não é "desktop encolhido". Abaixo de 640&nbsp;px as
colunas <b>empilham</b> em vez de espremer — três métricas de 90&nbsp;px de
largura não são legíveis, são decorativas; os alvos de toque respeitam o
mínimo de 44&nbsp;px; a tipografia é fluida; e tabelas e gráficos largos rolam
<b>dentro do próprio quadro</b>, de modo que a página nunca saia para o lado.
Há ainda um seletor de modo de leitura, para o caso concreto de quem abre o
painel no celular com o navegador em modo desktop.</p>

<p>Os <b>{n_filtros} filtros</b> foram definidos <b>depois</b> de analisar a
carteira, o histórico do Proagro e os alertas produzidos — cada um registra no
código por que existe. Só aparecem os filtros cuja coluna existe e tem mais de
um valor no conjunto atual: filtro de uma opção só ocupa espaço e não filtra
nada. E os filtros ativos aparecem como etiquetas visíveis acima da barra,
porque um painel filtrado sem aviso é a forma mais rápida de alguém concluir
que "não há alertas" quando há.</p>

<p>Os quatro cortes que mais separam um painel útil de um painel bonito:</p>

<ul>
  <li><b>Cobertura de risco</b> — "sem Proagro e sem seguro" é a única
  combinação em que o produtor perde tudo.</li>
  <li><b>Fase fenológica</b> — a mesma seca é irrelevante na maturação e
  potencialmente fatal na floração.</li>
  <li><b>Janela de ação</b> — quem está em campo não pergunta "o que é
  grave?", pergunta "o que preciso resolver até amanhã?".</li>
  <li><b>Aderência ao Zarc</b> — separa o risco que veio do céu do risco que
  veio da decisão de plantio. No primeiro caso se oferece apoio; no segundo,
  orientação.</li>
</ul>

<p>E os dados aparecem <b>no mapa sempre que têm coordenada</b>: alertas,
carteira, glebas, indicadores climáticos, sinistros históricos, exposição
financeira, proteção do município, entrega das mensagens e focos de calor.
Tabela serve para conferir; mapa serve para decidir — e quem trabalha com
território decide olhando o mapa.</p>

<h3>4.4 Tolerância a falhas</h3>
{tabela_html([
    {"Falha": "Sem <code>GROQ_API_KEY</code>", "Comportamento": "Redator determinístico assume", "Onde o usuário vê": "Aviso na execução e etiqueta na mensagem"},
    {"Falha": "Groq fora do ar ou sem cota", "Comportamento": "Idem, após tentativas com <i>backoff</i>", "Onde o usuário vê": "Aviso e telemetria de erro"},
    {"Falha": "Open-Meteo indisponível", "Comportamento": "Gerador sintético assume aquele lote", "Onde o usuário vê": "Aviso explícito e rótulo da fonte"},
    {"Falha": "Sem dados curados do BCB", "Comportamento": "Amostra de demonstração", "Onde o usuário vê": "Faixa permanente na barra lateral"},
    {"Falha": "<code>pyarrow</code> ausente", "Comportamento": "Lê e grava <code>.csv.gz</code>", "Onde o usuário vê": "Transparente"},
    {"Falha": "Um agente lança exceção", "Comportamento": "Pipeline segue; etapa marcada como erro", "Onde o usuário vê": "Rastro de execução"},
], ["Falha", "Comportamento", "Onde o usuário vê"])}

<div class="atencao">
Essa política tem um custo: o sistema pode apresentar resultados que
<b>não são reais</b>. Por isso toda contingência é anunciada de forma
explícita na interface — nunca silenciosamente.
</div>
"""

    # ------------------------------------------------------ 5. agentes
    orq_desc = Orquestrador(base=base, motor=motor).descrever_pipeline()
    linhas_agentes = []
    entradas_saidas = {
        "CarteiraAgent": ("Microdados do Sicor", "Operações vigentes com fase fenológica, exposição e histórico"),
        "ClimaAgent": ("Coordenadas dos municípios", "Séries diárias e indicadores por célula de grade"),
        "EventoAgent": ("Indicadores meteorológicos", "Eventos climáticos por território, com severidade"),
        "RegrasAgent": ("Eventos × operações", "Alertas com score de 0 a 100 e justificativa rastreável"),
        "RedatorAgent": ("Alertas", "Mensagens por persona e canal, revisadas"),
        "DespachanteAgent": ("Mensagens", "Envios simulados registrados em SQLite"),
    }
    for a in orq_desc:
        nome = a["agente"]
        entrada, saida = entradas_saidas.get(nome, ("—", "—"))
        linhas_agentes.append({
            "#": a["ordem"],
            "Agente": f"<b>{esc(nome)}</b>",
            "Responsabilidade": esc(a["papel"]),
            "Entrada": esc(entrada),
            "Saída": esc(saida),
        })

    agentes = f"""
<h2 class="quebra">5. Descrição dos agentes desenvolvidos</h2>

{tabela_html(linhas_agentes, ["#", "Agente", "Responsabilidade", "Entrada", "Saída"])}

<h3>5.1 CarteiraAgent — preparação do universo monitorado</h3>
<p>Carrega a carteira do Sicor, filtra as operações vigentes e calcula, para
cada uma, a <b>fase fenológica de hoje</b> — a fração decorrida entre as
datas de plantio e colheita declaradas na própria operação. Anexa exposição
financeira agregada do município e o vetor de frequência histórica de cada
evento no Proagro. Operações sem ciclo declarado (típico de investimento)
entram como <code>sem_ciclo</code>: seguem na carteira para as regras
financeiras, mas não recebem alerta agronômico de fase.</p>

<h3>5.2 ClimaAgent — coleta de dados meteorológicos externos</h3>
<p>Consulta a API pública Open-Meteo. Três otimizações tornam isso viável em
uma carteira grande: <b>deduplicação por célula de grade</b> (~11 km, o que
faz municípios vizinhos compartilharem uma consulta), <b>requisições em
lote</b> (40 coordenadas por chamada) e <b>cache em disco com TTL</b>. Um
provedor sintético determinístico assume quando não há rede — e alimenta
também o modo cenário da interface.</p>

<h3>5.3 EventoAgent — identificação de eventos relevantes</h3>
<p>Classifica, por célula, quais fenômenos estão previstos e com que
severidade, usando escadas de limiares objetivas. A separação em relação ao
agente de regras é deliberada: este responde <i>"que fenômeno está previsto
neste território"</i>, independentemente da carteira de qualquer cliente.</p>

<h3>5.4 RegrasAgent — aplicação das regras de negócio</h3>
<p>Cruza três camadas — o que vem do céu (indicadores), o que está no campo
(cultura, fase, irrigação) e o que está no contrato (valor, vencimento,
cobertura) — e produz alertas com score e justificativa. Cada alerta carrega
o identificador da regra, a expressão que disparou e os valores dos
indicadores usados.</p>

<h3>5.5 RedatorAgent — geração das mensagens com IA generativa</h3>
<p>Consolida os alertas por destinatário, monta um bloco fechado de fatos
autorizados, chama o modelo com saída estruturada em JSON, submete o
resultado a uma segunda passagem de revisão de conformidade e valida o
limite de caracteres em código. Sem chave de API, monta a mensagem por
<i>template</i> determinístico. Também produz os boletins consolidados das
personas institucionais.</p>

<h3>5.6 DespachanteAgent — simulação do envio</h3>
<p>Aplica a política anti-fadiga, respeita a janela de contato de cada
persona (um alerta crítico a ignora, e o motivo fica registrado), ordena a
fila por urgência, simula latência, tentativas e falhas por canal, estima o
custo que o envio real teria e grava tudo com a marca
<code>simulado</code>.</p>

<h3>5.7 CopilotoAgent — consulta em linguagem natural</h3>
<p>Fora do pipeline. Usa <i>function calling</i>: o modelo escolhe a consulta
e os parâmetros, o pandas calcula, o modelo redige. Cinco ferramentas
disponíveis, no máximo quatro iterações por pergunta, resultado truncado em
25 linhas antes de voltar ao modelo.</p>
"""

    # ------------------------------------------------------ 6. tecnologias
    tecnologias = f"""
<h2 class="quebra">6. Tecnologias utilizadas</h2>

<div class="destaque">
<b>Restrição de projeto:</b> apenas recursos gratuitos ou de avaliação, sem
qualquer custo. Isso condicionou escolhas em toda a pilha — e é parte do
mérito técnico da solução.
</div>

{tabela_html([
    {"Camada": "Linguagem", "Tecnologia": "Python 3.11+", "Papel": "Todo o sistema", "Custo": "Livre"},
    {"Camada": "Interface", "Tecnologia": "Streamlit", "Papel": "Aplicação multipágina e publicação", "Custo": "Community Cloud gratuito"},
    {"Camada": "Dados", "Tecnologia": "pandas, NumPy, PyArrow", "Papel": "ETL, agregações e Parquet", "Custo": "Livre"},
    {"Camada": "Visualização", "Tecnologia": "Plotly", "Papel": "Gráficos e mapas sem token", "Custo": "Livre"},
    {"Camada": "Mapas", "Tecnologia": "MapLibre / carto-positron", "Papel": "Basemap sem chave", "Custo": "Livre"},
    {"Camada": "Regras", "Tecnologia": "PyYAML + AST do Python", "Papel": "Motor declarativo com avaliação segura", "Custo": "Livre"},
    {"Camada": "IA generativa", "Tecnologia": "GroqCloud (Llama 3.3 70B, Llama 3.1 8B)", "Papel": "Redação, boletins, revisão e copiloto", "Custo": "Camada gratuita"},
    {"Camada": "Meteorologia", "Tecnologia": "Open-Meteo", "Papel": "Previsão de 16 dias e histórico", "Custo": "Gratuita, sem chave"},
    {"Camada": "Dados de origem", "Tecnologia": "Sicor / Proagro — Banco Central", "Papel": "Carteira e histórico de sinistro", "Custo": "Dados abertos"},
    {"Camada": "Persistência", "Tecnologia": "SQLite", "Papel": "Caixa de saída e auditoria", "Custo": "Livre"},
    {"Camada": "Integração", "Tecnologia": "requests (REST)", "Papel": "Clientes HTTP sem SDK proprietário", "Custo": "Livre"},
    {"Camada": "Qualidade", "Tecnologia": "pytest + GitHub Actions", "Papel": "68 testes e CI em duas versões do Python", "Custo": "Livre"},
], ["Camada", "Tecnologia", "Papel", "Custo"])}

<h3>6.1 Decisões técnicas que merecem nota</h3>
<ul>
  <li><b>Sem SDK proprietário para o LLM.</b> Falamos o protocolo HTTP
      diretamente com o endpoint compatível com OpenAI. Elimina conflito de
      versão no Streamlit Cloud e deixa explícito, para fins didáticos, o que
      é enviado ao modelo.</li>
  <li><b>Avaliação segura de expressões.</b> A condição de cada regra não
      passa por <code>eval()</code>: um mini-interpretador sobre a AST aceita
      apenas comparações, operadores booleanos, aritmética simples e sete
      funções matemáticas. Há teste cobrindo tentativas de injeção.</li>
  <li><b>Dois formatos de saída no ETL.</b> Parquet (rápido e compacto) e
      <code>.csv.gz</code> (lê em qualquer instalação de pandas). A aplicação
      tenta o primeiro e cai para o segundo.</li>
  <li><b>Compatibilidade de mapas.</b> A API de mapas do Plotly mudou de
      <code>scatter_mapbox</code> para <code>scatter_map</code> na versão 6;
      o código escolhe em tempo de execução a que existir.</li>
</ul>
"""

    # ------------------------------------------------------ 7. fluxo
    linhas_rastro = [
        {
            "Etapa": e.agente,
            "Responsabilidade": e.papel,
            "Tempo": f"{e.duracao_s:.2f} s",
            "Resultado": esc(e.resumo),
        }
        for e in res.contexto.rastro
    ]
    fluxo = f"""
<h2 class="quebra">7. Fluxo de processamento</h2>

<p>A tabela abaixo é o <b>rastro real</b> de uma execução do pipeline,
capturado no momento em que este relatório foi gerado — não é ilustração.
A mesma tabela aparece na página inicial da aplicação.</p>

{tabela_html(linhas_rastro, ["Etapa", "Responsabilidade", "Tempo", "Resultado"])}

<p><b>Execução {esc(res.execucao_id)}</b> · base
{esc(res.base.origem)} · cenário {esc(res.contexto.cenario or 'previsão real')} ·
horizonte de {res.contexto.horizonte_dias} dias ·
tempo total {res.contexto.duracao_total_s:.2f} s.</p>

<h3>7.1 Detalhamento das cinco etapas exigidas</h3>
<ol>
  <li><b>Coleta em fonte externa de dados meteorológicos.</b> Os municípios
      distintos da carteira são reduzidos a células de grade; a Open-Meteo é
      consultada em lote; a resposta vira série diária normalizada.</li>
  <li><b>Identificação de eventos relevantes.</b> A série é convertida em
      ~30 indicadores derivados, separados em janela observada (14 dias) e
      janela prevista (7 dias por padrão). Escadas de limiares classificam
      cada célula em até oito tipos de evento, com quatro níveis de
      severidade.</li>
  <li><b>Aplicação de regras de negócio.</b> Para cada par
      (operação × evento presente no território), as regras aplicáveis são
      avaliadas. O score combina severidade, sensibilidade da fase, histórico
      do Proagro, exposição financeira e ausência de cobertura.</li>
  <li><b>Geração automática das mensagens.</b> Alertas do mesmo destinatário
      são consolidados; o bloco de fatos autorizados é montado; o modelo
      redige respeitando persona, canal e limite; a revisão confere.</li>
  <li><b>Simulação do envio.</b> A fila é ordenada por urgência, a política
      anti-fadiga é aplicada, a janela de contato é respeitada, e o despacho
      é simulado com latência, tentativa, falha e custo — sem enviar nada.</li>
</ol>
"""

    # ------------------------------------------------------ 8. dados
    cat = resumo_catalogo()
    mod = modelo_integrado.resumo()
    fon = fontes_externas.resumo()

    n_arquivos = inteiro(cat["total"])
    n_usados = inteiro(cat["usados"])
    n_excluidos = inteiro(cat.get("excluidos_por_privacidade", 0))
    pct_cobertura = cat.get("cobertura_pct", 0)
    n_entidades = inteiro(mod["entidades"])
    n_ligacoes = inteiro(mod["ligacoes"])
    n_fontes = inteiro(fon["total"])
    n_fontes_ativas = inteiro(fon["ativas"])

    tabela_ligacoes_criticas = tabela_html(
        [
            {
                "De": esc(l.to_row()["de"]),
                "Para": esc(l.to_row()["para"]),
                "Chave": f"<code>{esc(l.to_row()['chave'])}</code>",
                "Para quê": esc(l.to_row()["para quê"]),
            }
            for l in modelo_integrado.ligacoes_criticas()
        ],
        ["De", "Para", "Chave", "Para quê"],
    )

    tabela_fontes = tabela_html(
        [
            {
                "Fonte": f"<b>{esc(f.nome)}</b>",
                "Órgão": esc(f.orgao),
                "Licença": esc(f.licenca),
                "Liga por": f"<code>{esc(f.chave_juncao)}</code>",
                "Papel na solução": esc(f.papel),
            }
            for f in fontes_externas.FONTES
        ],
        ["Fonte", "Órgão", "Licença", "Liga por", "Papel na solução"],
    )

    dados = f"""
<h2 class="quebra">8. Fontes de dados e engenharia de dados</h2>

{figura("fluxo_dados.png", "Figura 2 — Como os arquivos do Sicor se combinam para produzir o alerta.")}

<h3>8.1 O catálogo do Banco Central</h3>
<p>Os <b>{cat['total']} arquivos</b> publicados em
<i>Tabelas e Microdados do Crédito Rural e do Proagro</i> estão mapeados no
módulo <code>etl_catalogo.py</code> — {cat['dominios']} tabelas de domínio,
{cat['microdados']} microdados do Sicor, {cat['publicos']} do crédito rural
público, {cat['contratado']} do crédito contratado e {cat['recor']} da série
histórica Recor. Desses, <b>{cat['usados']}</b> alimentam diretamente a
solução. O catálogo é exibido na própria aplicação, com indicação do papel
de cada arquivo.</p>

<h3>8.2 O elo que georreferencia tudo</h3>
<div class="atencao">
<code>SICOR_OPERACAO_BASICA_ESTADO_AAAA.gz</code> <b>não traz o
município</b> — apenas <code>CD_ESTADO</code>. O município vem de
<code>SICOR_COMPLEMENTO_OPERACAO_BASICA.gz</code>, pela chave
<code>REF_BACEN + NU_ORDEM → CD_IBGE_MUNICIPIO</code>. Sem esse arquivo o
alerta climático é inviável; por isso ele é baixado sempre, e a validação
reprova a base se menos de 50% das operações tiverem coordenada.
</div>

<h3>8.3 Particularidades tratadas no ETL</h3>
{tabela_html([
    {"Particularidade": "Codificação Latin-1 / CP1252", "Tratamento": "Detecção automática com três tentativas"},
    {"Particularidade": "Delimitador variável (<code>;</code> ou <code>,</code>)", "Tratamento": "Inferência na primeira linha"},
    {"Particularidade": "Separador decimal vírgula", "Tratamento": "Conversão com limpeza de separador de milhar"},
    {"Particularidade": "Datas em cinco formatos diferentes", "Tratamento": "Testa todos e escolhe o que converte mais"},
    {"Particularidade": "Cabeçalhos com acento e caixa variável", "Tratamento": "Normalização para <code>NU_ORDEM</code>"},
    {"Particularidade": "Arquivos de vários gigabytes", "Tratamento": "Leitura em blocos de 400 mil linhas"},
    {"Particularidade": "Integridade do download", "Tratamento": "Verificação do <code>.hash</code> publicado pelo BCB"},
], ["Particularidade", "Tratamento"])}

<h3>8.4 Por que existe uma amostra de demonstração</h3>
<p>Os microdados somam dezenas de gigabytes: não cabem no GitHub nem na
memória de um contêiner gratuito. A solução adotada tem três camadas: o ETL
roda fora da aplicação e produz conjuntos curados e compactos; enquanto
estes não existem, o aplicativo usa uma amostra sintética com <b>o mesmo
esquema</b> e proporções calibradas pelo perfil público do Sicor; e a
interface <b>sempre</b> informa qual das duas está em uso.</p>

<p>Isso mantém o projeto executável por qualquer avaliador em menos de um
minuto, sem esconder a diferença entre dado real e dado sintético.</p>

<h3>8.5 Base utilizada nesta demonstração</h3>
{tabela_html([
    {"Métrica": "Origem", "Valor": esc(base.origem)},
    {"Métrica": "Operações", "Valor": inteiro(stats.get("n_operacoes", 0))},
    {"Métrica": "Municípios", "Valor": inteiro(stats.get("n_municipios", 0))},
    {"Métrica": "Unidades da Federação", "Valor": inteiro(stats.get("n_ufs", 0))},
    {"Métrica": "Valor financiado", "Valor": reais_compacto(stats.get("valor_total", 0))},
    {"Métrica": "Área financiada", "Valor": hectares(stats.get("area_total", 0))},
    {"Métrica": "Culturas distintas", "Valor": inteiro(stats.get("n_culturas", 0))},
    {"Métrica": "Operações com cobertura declarada", "Valor": pct(stats.get("pct_coberto", 0))},
    {"Métrica": "Exposição sem cobertura", "Valor": reais_compacto(stats.get("valor_descoberto", 0))},
], ["Métrica", "Valor"])}

<h3>8.6 O modelo integrado: como {n_arquivos} arquivos conversam</h3>

<p>A pergunta que separa uma solução real de uma demonstração não é "quais
dados existem?", é <b>"como eles se ligam?"</b>. O grafo de integração é
código executável — {n_entidades} entidades e {n_ligacoes} ligações, cada uma
com chave, cardinalidade e o motivo de existir — e os testes verificam que
ele é conexo e que toda chave declarada aponta para entidade que existe.</p>

<p>Três descobertas organizam todo o resto:</p>

<ol>
  <li><b>A chave universal do Sicor é o par <code>(REF_BACEN, NU_ORDEM)</code>.</b>
  <code>REF_BACEN</code> identifica o contrato junto ao Banco Central;
  <code>NU_ORDEM</code> distingue cada empreendimento dentro dele.</li>

  <li><b>A operação básica não tem município.</b>
  <code>SICOR_OPERACAO_BASICA_ESTADO_AAAA.gz</code> só traz
  <code>CD_ESTADO</code>. O <code>CD_IBGE_MUNICIPIO</code> mora em
  <code>SICOR_COMPLEMENTO_OPERACAO_BASICA.gz</code>. Sem essa junção
  específica não existe georreferenciamento — e sem georreferenciamento
  nenhum alerta climático pode ser dirigido. É a ligação mais crítica do
  modelo inteiro.</li>

  <li><b>O Proagro é uma cadeia de quatro etapas, não uma tabela.</b>
  Pedido de cobertura → comprovação de perdas → súmula de julgamento →
  parcelas pagas. Medir sinistralidade olhando só o pedido superestima;
  olhando só a perícia, ignora o que foi negado. A solução percorre a cadeia
  inteira e expõe as três taxas separadas — acionamento, comprovação e
  deferimento — além do <b>motivo de indeferimento mais frequente do
  município</b>, que é a informação mais acionável que existe para quem pode
  vir a abrir um pedido: diz o que documentar antes de precisar.</li>
</ol>

<p>A cobertura do catálogo é de <b>{n_usados} dos {n_arquivos} arquivos
publicados ({pct_cobertura}%)</b>. Os {n_excluidos} de fora são os arquivos de
mutuários, deliberadamente excluídos por decisão de privacidade — e a exclusão
fica <b>registrada no catálogo</b>, não apenas omitida, para que se possa
conferir que foi escolha e não esquecimento.</p>

{tabela_ligacoes_criticas}

<p>Três conjuntos curados novos saíram dessa integração, todos opcionais por
construção — cada um adiciona uma capacidade e nenhum é necessário para a
solução funcionar:</p>

<ul>
  <li><b><code>glebas</code></b> — o polígono de cada talhão financiado, em
  WKT. Com ele a consulta climática deixa de ser feita no centroide do
  município e passa a ser feita na própria lavoura. Em municípios extensos,
  como Ribas do Rio Pardo ou Altamira, a distância entre os dois passa de
  80 km, o bastante para consultar uma frente de chuva que não está sobre o
  talhão. O ETL ainda compara a área declarada com a área do polígono e
  reporta a divergência — não como erro a esconder, mas como indicador de
  qualidade útil para perícia e subscrição.</li>
  <li><b><code>exposicao</code></b> — saldo devedor, saldo vencido,
  desembolso e marca de renegociação por operação. Converte "área em risco"
  em "dinheiro em risco", que é a única unidade em que gerente de crédito,
  atuário e gestor de política conversam entre si.</li>
  <li><b><code>contexto_externo</code></b> — o enriquecimento municipal
  descrito a seguir.</li>
</ul>

<h3>8.7 Fontes externas: gratuitas, públicas e livres</h3>

<p>O Sicor conta o que foi <b>financiado</b> e o que foi <b>sinistrado</b>.
Ele não conta o que está acontecendo <b>agora</b> no campo, nem o que existe
<b>fora</b> do crédito rural. São três lacunas concretas:</p>

<ul>
  <li><b>Tempo presente e futuro.</b> O Sicor é retrospectivo. Alerta útil
  exige previsão, série climática longa e monitoramento em tempo quase real.</li>
  <li><b>Denominador.</b> "1.200 operações de soja em Sorriso" só vira risco
  quando comparado à área total de soja do município.</li>
  <li><b>O outro lado da cobertura.</b> O Proagro é metade do mercado; a
  outra metade é o seguro rural privado subvencionado. Sem ele não se sabe se
  um município está <i>descoberto</i> ou apenas <i>protegido por outro
  instrumento</i> — e essa diferença muda completamente a recomendação.</li>
</ul>

<p>São {n_fontes} fontes catalogadas, {n_fontes_ativas} ativas no fluxo.
<b>Todas gratuitas e públicas, e nenhuma exige cadastro</b> — restrição
declarada do projeto, verificada por teste automatizado.</p>

{tabela_fontes}

<p>Cada conector degrada em três níveis — rede, cache, tabela de referência
embutida — e <b>o selo de procedência acompanha o dado até a tela</b>
(🟢 ao vivo, 🟡 cache, ⚪ referência). Um painel que apresenta valor
aproximado como se fosse consulta ao vivo é pior do que um painel vazio.</p>

<p>Duas fontes recebem tratamento próprio e deliberado: <b>fogo</b> (INPE) e
<b>chuva medida em solo</b> (CEMADEN) nunca caem para a tabela de referência.
Sem rede, devolvem "não sei" em vez de "zero" — porque um zero inventado
esconderia justamente o evento que importa.</p>

<p>O ganho é verificável na mensagem. Com as fontes externas ligadas, o bloco
de fatos de um alerta passa a conter, entre outros: <i>"muito abaixo da média
— 0 mm previstos contra 19,5 mm de normal para a janela, conforme a
climatologia da NASA POWER"</i>; <i>"o plantio registrado ficou 5 decêndios
fora da janela recomendada pelo Zarc"</i>; <i>"85% da área financiada do
município com cobertura no Sicor e 6% com seguro rural privado
subvencionado"</i>. Nenhum desses números existe no Sicor isoladamente — todos
nascem do cruzamento.</p>
"""

    # ------------------------------------------------------ 9. regras
    linhas_regras = [
        {
            "ID": f"<b>{esc(r.id)}</b>",
            "Nome": esc(r.nome),
            "Evento": esc(r.evento),
            "Condição": f"<code>{esc(r.quando)}</code>",
            "Sev.": esc(r.severidade_base),
            "Janela": f"{r.janela_acao_h} h",
        }
        for r in motor.regras
    ]
    regras = f"""
<h2 class="quebra">9. Regras de negócio e score de risco</h2>

<p>As regras vivem em <code>src/agrosentinela/rules/rules.yaml</code>, em
texto, sob controle de versão. São {len(motor.regras)} regras na versão
{esc(motor.versao)}.</p>

{tabela_html(linhas_regras, ["ID", "Nome", "Evento", "Condição", "Sev.", "Janela"])}

<h3>9.1 Anatomia de uma regra</h3>
<pre>- id: R-GEA-02
  nome: "Geada severa em cultura perene"
  evento: geada
  quando: "tmin_min &lt;= 2 and cultura in ['CAFE','UVA','MACA','LARANJA']"
  severidade_base: alerta
  escalonamento:
    - quando: "tmin_min &lt;= 0"
      severidade: critico
  fases_criticas: [brotacao, frutificacao]
  bonus_fase: 28
  personas: [produtor_empresarial, cooperativa, assistencia_tecnica, ...]
  janela_acao_h: 18
  acao: &gt;
    Mobilizar equipe noturna, avaliar proteção dos talhões mais baixos e
    documentar por talhão para eventual comprovação de perdas.
  base_tecnica: &gt;
    Em perenes o dano atinge a safra corrente e a seguinte, o que altera a
    capacidade de pagamento de operações de investimento.</pre>

<h3>9.2 Score de risco</h3>
{figura("score_risco.png", "Figura 3 — Composição do score e ponto de corte da notificação.")}

<p>O total é <b>normalizado pelo máximo teórico da própria regra</b>, o que
torna o score comparável entre regras com bônus diferentes e evita a
saturação em 100. O limiar de notificação é
{motor.pesos.limiar_notificacao:.0f}: abaixo disso o alerta é registrado,
mas não vira mensagem.</p>

<h3>9.3 Fenologia: o que diferencia «chove muito» de «chove muito na colheita»</h3>
<p>Cada cultura tem fases com um multiplicador de sensibilidade por evento.
Exemplo para culturas anuais de grãos:</p>

{tabela_html([
    {"Fase": "Semeadura / emergência", "% do ciclo": "0–18", "Seca": "1,6", "Chuva excessiva": "1,5", "Granizo": "0,7", "Geada": "1,2"},
    {"Fase": "Vegetativo", "% do ciclo": "18–45", "Seca": "1,3", "Chuva excessiva": "1,2", "Granizo": "1,3", "Geada": "1,4"},
    {"Fase": "<b>Floração</b>", "% do ciclo": "45–65", "Seca": "<b>2,0</b>", "Chuva excessiva": "1,5", "Granizo": "1,8", "Geada": "1,6"},
    {"Fase": "<b>Enchimento de grãos</b>", "% do ciclo": "65–85", "Seca": "<b>1,8</b>", "Chuva excessiva": "1,3", "Granizo": "<b>1,9</b>", "Geada": "<b>1,9</b>"},
    {"Fase": "Maturação", "% do ciclo": "85–96", "Seca": "0,8", "Chuva excessiva": "<b>1,9</b>", "Granizo": "<b>2,0</b>", "Geada": "1,2"},
    {"Fase": "Colheita", "% do ciclo": "96–100", "Seca": "0,5", "Chuva excessiva": "<b>2,0</b>", "Granizo": "1,6", "Geada": "0,8"},
], ["Fase", "% do ciclo", "Seca", "Chuva excessiva", "Granizo", "Geada"])}

<p>Culturas perenes usam repouso, brotação, frutificação e colheita.
Pecuária e pastagem usam rebrota, pleno pastejo, entressafra forrageira e
manejo sanitário — falar em «floração de bovinocultura» seria absurdo, e o
sistema não o faz.</p>

<h3>9.4 O índice de granizo</h3>
<p>Não existe previsão pública direta de granizo de acesso livre. Usamos um
índice convectivo composto, documentado e auditável:</p>
<pre>f_cape  = (CAPE − 800) / 2200      energia convectiva disponível
f_vento = (rajada − 40) / 50       organização da célula convectiva
f_chuva = (prec24h − 15) / 45      presença de núcleo precipitante

índice = 100 × (0,55·f_cape + 0,27·f_vento + 0,18·f_chuva)

porta de entrada: CAPE &lt; 800 J/kg  →  índice = 0</pre>
<p>O índice estima <b>ambiente favorável</b>, não ocorrência — e as
mensagens são escritas nesses termos.</p>

<h3>9.5 Política anti-fadiga</h3>
{tabela_html([
    {"Parâmetro": "Janela de repetição", "Valor": f"{motor.supressao.janela_repeticao_h} h", "Razão": "Não reenviar enquanto a situação não muda"},
    {"Parâmetro": "Máximo por destinatário/dia", "Valor": str(motor.supressao.max_msgs_destinatario_dia), "Razão": "Alerta em excesso deixa de ser lido"},
    {"Parâmetro": "Severidade mínima global", "Valor": esc(motor.supressao.severidade_minima_global), "Razão": "Ruído informativo não vira mensagem"},
    {"Parâmetro": "Consolidação por destinatário", "Valor": "sim", "Razão": "Vários eventos viram uma mensagem só"},
], ["Parâmetro", "Valor", "Razão"])}
"""

    # ------------------------------------------------------ 10. IA
    ia = f"""
<h2 class="quebra">10. Uso de Inteligência Artificial Generativa</h2>

<div class="destaque">
<b>Princípio:</b> o modelo redige, as regras decidem. Num sistema que fala
com produtor rural sobre risco de perder a safra e sobre cobertura de
seguro, alucinação é dano real.
</div>

{tabela_html([
    {"Tarefa": "Detectar evento climático", "Usa LLM?": "Não", "Justificativa": "Limiar numérico é determinístico e auditável"},
    {"Tarefa": "Calcular score de risco", "Usa LLM?": "Não", "Justificativa": "Precisa ser reproduzível e explicável linha a linha"},
    {"Tarefa": "Decidir quem notificar", "Usa LLM?": "Não", "Justificativa": "É regra de negócio, revisável por especialista"},
    {"Tarefa": "Escolher canal e horário", "Usa LLM?": "Não", "Justificativa": "Deriva do cadastro da persona"},
    {"Tarefa": "Aplicar anti-fadiga", "Usa LLM?": "Não", "Justificativa": "Consulta determinística ao histórico"},
    {"Tarefa": "<b>Redigir a mensagem</b>", "Usa LLM?": "<b>Sim</b>", "Justificativa": "Adaptar tom, vocabulário e tamanho ao destinatário"},
    {"Tarefa": "<b>Escrever o boletim consolidado</b>", "Usa LLM?": "<b>Sim</b>", "Justificativa": "Síntese executiva a partir de métricas apuradas"},
    {"Tarefa": "<b>Revisar a mensagem gerada</b>", "Usa LLM?": "<b>Sim</b>", "Justificativa": "Segunda passagem barata contra alucinação"},
    {"Tarefa": "<b>Responder perguntas (copiloto)</b>", "Usa LLM?": "<b>Sim</b>, com ferramentas", "Justificativa": "O pandas calcula; o modelo só redige"},
], ["Tarefa", "Usa LLM?", "Justificativa"])}

<h3>10.1 Guarda-corpos de redação</h3>
<ol>
  <li>Usar <b>exclusivamente</b> os números, datas e nomes do bloco
      <code>DADOS</code>. Nunca inventar nem estimar.</li>
  <li><b>Nunca</b> prometer, garantir ou sugerir que uma indenização será
      paga. Proagro e seguro dependem de comprovação de perdas e de análise
      técnica.</li>
  <li>Nunca dar orientação jurídica, contábil ou de investimento.</li>
  <li>Não alarmar: descrever o risco com precisão e sempre indicar o que fazer.</li>
  <li>Previsão é probabilística — usar «previsão», «risco», «possibilidade».</li>
  <li>Português do Brasil, sem markdown e sem assinatura inventada.</li>
  <li>Respeitar o limite de caracteres do canal.</li>
</ol>
<p>Os itens 1, 2 e 7 não ficam só no prompt: são <b>verificados em
código</b>. O limite é truncado programaticamente e a ausência de promessa
de indenização tem teste automatizado.</p>

<h3>10.2 O bloco de fatos autorizados</h3>
<p>O modelo nunca vê a base de dados. Recebe um dicionário fechado com o que
foi apurado — e apenas as ações das regras <b>dirigidas àquela persona</b>,
porque não faz sentido pedir a um produtor que «eleve o município para
acompanhamento diário da área de risco».</p>

<h3>10.3 Controle de cota da camada gratuita</h3>
{tabela_html([
    {"Mecanismo": "Orçamento de chamadas por execução", "Efeito": "Interrompe antes de estourar a cota"},
    {"Mecanismo": "Cache em disco por <i>hash</i> da requisição", "Efeito": "Reexecutar não gasta cota"},
    {"Mecanismo": "Modelo rápido na revisão", "Efeito": "A revisão custa uma fração da redação"},
    {"Mecanismo": "Respeito ao cabeçalho <code>Retry-After</code>", "Efeito": "Não insiste contra o limite de taxa"},
    {"Mecanismo": "<i>Backoff</i> exponencial", "Efeito": "Três tentativas com espera crescente"},
    {"Mecanismo": "Consolidação por destinatário", "Efeito": "Uma chamada por pessoa, não por alerta"},
    {"Mecanismo": "Teto de mensagens por execução", "Efeito": "Limita o volume total de chamadas"},
], ["Mecanismo", "Efeito"])}

<h3>10.4 Modelos utilizados</h3>
{tabela_html([
    {"Papel": "Redação e boletins", "Modelo": "<code>openai/gpt-oss-120b</code>", "Por quê": "Melhor português e aderência a instrução longa"},
    {"Papel": "Revisão de conformidade", "Modelo": "<code>openai/gpt-oss-20b</code>", "Por quê": "Tarefa simples, alta vazão, baixo consumo"},
    {"Papel": "Copiloto", "Modelo": "<code>openai/gpt-oss-120b</code>", "Por quê": "Suporte sólido a <i>function calling</i>"},
], ["Papel", "Modelo", "Por quê"])}
"""

    # ------------------------------------------------------ 11. exemplos
    blocos_msg = []
    for cenario, m in mensagens:
        persona = PERSONAS_POR_CODIGO.get(m.persona)
        origem = "IA Generativa" if m.gerado_por == "llm" else "template determinístico"
        blocos_msg.append(f"""
<div class="msg {esc(m.severidade)}">
  <div class="cab">
    <span class="tag sev {esc(m.severidade)}">{esc(m.severidade.upper())}</span>
    <span class="tag">{esc(m.canal)}</span>
    <span class="tag">{esc(m.caracteres)}/{esc(m.limite_canal)} car.</span>
    <span class="tag">score {m.score:.0f}</span>
    <span class="tag">{esc(origem)}</span><br>
    <b>{esc(persona.nome if persona else m.persona)}</b>
    · cenário: {esc(cenario)}
    {('· ' + esc(m.municipio) + '-' + esc(m.uf)) if m.municipio else ''}
    {('· evento: ' + esc(m.evento)) if m.evento else ''}
  </div>
  {('<div style="font-size:8.8pt;margin-bottom:5px"><b>Assunto:</b> ' + esc(m.assunto) + '</div>') if m.assunto else ''}
  <div class="corpo">{esc(m.texto)}</div>
</div>""")

    exemplos = f"""
<h2 class="quebra">11. Exemplos das mensagens geradas</h2>

<p>As mensagens abaixo foram <b>geradas pelo sistema durante a produção
deste relatório</b>, em {len(CENARIOS_DEMO)} cenários climáticos distintos.
Nenhuma foi escrita à mão. Cada bloco mostra a persona, o canal, o tamanho
em relação ao limite do canal, o score de risco e a origem do texto.</p>

<div class="atencao">
Nesta geração, o redator operou em modo
<b>{'IA Generativa (GroqCloud)' if usar_llm else 'template determinístico'}</b>.
{'' if usar_llm else 'Sem chave de API configurada, o sistema demonstra o caminho de contingência — que produz mensagens completas e corretas para todos os canais.'}
</div>

{''.join(blocos_msg)}
"""

    # ------------------------------------------------------ 12. resultados
    if not alertas.empty:
        por_evento = (
            alertas.groupby("evento_nome")
            .agg(alertas=("id", "count"), exposicao=("valor_credito", "sum"),
                 criticos=("severidade", lambda s: int((s == "critico").sum())))
            .sort_values("alertas", ascending=False)
            .reset_index()
        )
        linhas_evento = [
            {"Evento": esc(r["evento_nome"]), "Alertas": inteiro(r["alertas"]),
             "Críticos": inteiro(r["criticos"]),
             "Exposição": reais_compacto(r["exposicao"])}
            for _, r in por_evento.iterrows()
        ]
        por_persona = (
            alertas.groupby("persona")
            .agg(alertas=("id", "count"), exposicao=("valor_credito", "sum"))
            .sort_values("alertas", ascending=False).reset_index()
        )
        linhas_persona = [
            {"Persona": esc(PERSONAS_POR_CODIGO[r["persona"]].nome
                            if r["persona"] in PERSONAS_POR_CODIGO else r["persona"]),
             "Alertas": inteiro(r["alertas"]),
             "Exposição": reais_compacto(r["exposicao"])}
            for _, r in por_persona.iterrows()
        ]
    else:
        linhas_evento, linhas_persona = [], []

    envios = res.envios_df
    resultados = f"""
<h2 class="quebra">12. Resultados da execução demonstrativa</h2>

<p>Cenário de seca severa (intensidade 1,4) aplicado às operações de MT, GO
e BA, com horizonte de 7 dias.</p>

<div class="kpis">
  <div class="kpi"><span class="v">{inteiro(len(res.contexto.carteira))}</span><span class="r">operações monitoradas</span></div>
  <div class="kpi"><span class="v">{inteiro(len(res.contexto.alertas))}</span><span class="r">alertas gerados</span></div>
  <div class="kpi"><span class="v">{reais_compacto(alertas['valor_credito'].sum()) if not alertas.empty else '—'}</span><span class="r">exposição sinalizada</span></div>
  <div class="kpi"><span class="v">{inteiro(len(res.contexto.mensagens))}</span><span class="r">mensagens geradas</span></div>
</div>

<h3>12.1 Alertas por evento</h3>
{tabela_html(linhas_evento, ["Evento", "Alertas", "Críticos", "Exposição"])}

<h3>12.2 Alertas por persona</h3>
{tabela_html(linhas_persona, ["Persona", "Alertas", "Exposição"])}

<h3>12.3 Simulação de envio</h3>
{tabela_html([
    {"Indicador": "Entregas simuladas", "Valor": inteiro(int((envios["status"] == "simulado_entregue").sum())) if not envios.empty else "0"},
    {"Indicador": "Falhas simuladas", "Valor": inteiro(int((envios["status"] == "simulado_falha").sum())) if not envios.empty else "0"},
    {"Indicador": "Suprimidas pela política anti-fadiga", "Valor": inteiro(int((envios["status"] == "suprimido").sum())) if not envios.empty else "0"},
    {"Indicador": "Custo equivalente de um envio real", "Valor": f"R$ {envios['custo_estimado_R$'].sum():.4f}".replace(".", ",") if not envios.empty else "R$ 0,00"},
], ["Indicador", "Valor"])}

<div class="atencao">
<b>Nenhuma mensagem foi enviada.</b> O enunciado dispensa o envio real; o
agente despachante reproduz o comportamento de uma central (fila, janela de
contato, tentativa, latência, custo) e grava tudo com a marca
<code>simulado</code>.
</div>
"""

    # ------------------------------------------------------ 13. testes
    testes = f"""
<h2>13. Qualidade e testes</h2>

<p>São <b>68 testes automatizados</b>, executados em integração contínua nas
versões 3.11 e 3.12 do Python, cobrindo:</p>

{tabela_html([
    {"Arquivo": "<code>test_regras.py</code>", "Cobre": "Avaliador seguro de expressões (incluindo bloqueio de injeção), disparo e escalonamento das regras, composição e monotonicidade do score, política anti-fadiga, rastro do acionamento"},
    {"Arquivo": "<code>test_dados_e_clima.py</code>", "Cobre": "Consistência da amostra de municípios (código IBGE × UF × <i>bounding box</i>), esquema e reprodutibilidade da carteira sintética, janelas agronômicas de plantio, inferência de persona, mapeamento de produtos e eventos do Proagro, deduplicação da grade, determinismo dos cenários, cálculo dos indicadores"},
    {"Arquivo": "<code>test_pipeline.py</code>", "Cobre": "Execução de ponta a ponta, ordem e sucesso das seis etapas, respeito aos filtros, rastro completo dos alertas, limite de caracteres por canal, <b>ausência de promessa de indenização</b>, marca de simulação nos envios, persistência na caixa de saída, supressão na segunda execução, correspondência entre cenário e evento detectado"},
], ["Arquivo", "Cobre"])}

<h3>13.1 Dois defeitos reais encontrados pelos testes</h3>
<ol>
  <li>O boletim consolidado da persona de assistência técnica era despachado
      por WhatsApp e ultrapassava o limite de 700 caracteres. Correção: o
      digest passa a escolher canais que comportam texto longo (painel ou
      e-mail) e o truncamento virou garantia de código.</li>
  <li>Mensagens dirigidas a produtores incluíam ações destinadas a outras
      personas («elevar o município para acompanhamento diário»). Correção:
      só entram na mensagem as regras cuja lista de personas inclui o
      destinatário.</li>
</ol>
<p>Ambos passariam despercebidos em uma inspeção visual.</p>
"""

    # ------------------------------------------------------ 14. privacidade
    n_clausulas = len(CLAUSULAS_DO)
    n_grupos_clausula = len(GRUPOS_CLAUSULA)
    privacidade = f"""
<h2 class="quebra">14. Privacidade, limitações e evolução</h2>

<h3>14.1 Minimização de dados</h3>
<p>Os microdados do Sicor incluem arquivos com CPF/CNPJ
(<code>SICOR_MUTUARIOS</code>). <b>O AgroSentinela não os utiliza.</b> O
roteamento precisa apenas da referência da operação
(<code>REF_BACEN</code> + <code>NU_ORDEM</code>), que funciona como
pseudônimo estável; o destinatário é exibido como <code>OP-&lt;referência&gt;</code>;
e <b>nenhum dado pessoal é enviado ao modelo de linguagem</b>. É o princípio
da minimização (LGPD, art. 6º, III).</p>

<p>Em produção, o cruzamento entre a referência da operação e o contato do
cliente ficaria dentro da instituição financeira, sob a base legal adequada
— nunca no serviço de alerta.</p>

<h3>14.2 Limitações conhecidas</h3>
<ol>
  <li><b>Previsão é probabilística.</b> Um alerta não é a certeza de um evento.</li>
  <li><b>Granizo não tem previsão pública direta.</b> O índice convectivo
      estima ambiente favorável, não ocorrência.</li>
  <li><b>Resolução de ~11 km.</b> O alerta é de município, não de talhão.</li>
  <li><b>Fase fenológica estimada</b> pelas datas declaradas na operação,
      não observada em campo nem por índice de vegetação.</li>
  <li><b>A amostra de demonstração não é dado real.</b></li>
  <li><b>Nenhuma mensagem é enviada.</b></li>
</ol>

<h3>14.3 Vieses tratados</h3>
<ul>
  <li><b>Fadiga de alerta</b> — janela de repetição, teto diário, severidade
      mínima por persona e consolidação.</li>
  <li><b>Viés de porte</b> — ordenar só por exposição financeira faria as
      maiores operações consumirem todo o orçamento de mensagens. O redator
      distribui o teto em rodízio entre as personas, preservando a ordem de
      risco dentro de cada uma; assim o produtor familiar de ticket baixo
      também é avisado.</li>
  <li><b>Assimetria de custo entre erros</b> — neste domínio, falso negativo
      é mais caro que falso positivo. Os limiares foram calibrados para
      sensibilidade, e a supressão atua depois, na camada de comunicação.</li>
</ul>

<h3>14.4 Evolução futura</h3>
<ol>
  <li><b>Alerta em nível de talhão</b> com <code>SICOR_GLEBAS_WKT</code>, que
      traz a geometria das glebas financiadas.</li>
  <li><b>Validação da fase por satélite</b> (NDVI/EVI), substituindo a
      estimativa por observação.</li>
  <li><b>Zarc como atenuante formal</b> no score: operação dentro da janela
      de zoneamento tem risco estruturalmente menor.</li>
  <li><b>Modelo estatístico de probabilidade condicional de sinistro</b>
      treinado sobre a série COP/RCP completa, substituindo a frequência
      histórica simples.</li>
  <li><b>Integração real com canais</b> (WhatsApp Business API, e-mail
      transacional), com o cruzamento de contato dentro da instituição.</li>
  <li><b>RAG sobre o Manual de Crédito Rural</b> para fundamentar
      prorrogações, com citação obrigatória do trecho-fonte.</li>
</ol>

<h3>14.5 Preparação para o Projeto Final (comparação de apólices de D&amp;O)</h3>

<p>A arquitetura foi construída para ser reaproveitada, e a prévia já está no
aplicativo. O núcleo muda de domínio sem mudar de forma: o mesmo motor de
regras avalia cláusulas em vez de clima; o mesmo avaliador de expressões
baseado em AST, que nunca usa <code>eval</code>, é o mesmo; as mesmas personas,
o mesmo rastro de auditoria e a mesma interface.</p>

<p>O contrato <b>"as regras decidem, o modelo redige"</b> é o que mais importa
carregar. Em comunicação climática ele é rigor técnico; em comparação de
apólices vira requisito, porque um limite de cobertura inventado numa
recomendação é um dano concreto.</p>

<p>O que é específico do novo domínio já existe em
<code>src/agrosentinela/projeto_final/</code>: uma taxonomia de
<b>{n_clausulas} cláusulas</b> de D&amp;O em {n_grupos_clausula} grupos — cada
uma com peso por criticidade, a pergunta de verificação ("o que procurar no
texto da apólice") e o sinal de alerta ("o que costuma passar despercebido") —
e um comparador que produz escore ponderado, matriz comparativa e lacunas de
cobertura.</p>

<p>O achado mais útil que esse comparador produz é a <b>divergência de
leitura</b>: quando a apólice de melhor escore geral <b>não</b> é a melhor nas
cláusulas que decidem um sinistro. Significa que o escore geral está sendo
puxado por cláusulas que não decidem nada, e que um ranking simples levaria à
decisão errada. O sistema destaca esse caso em vez de escondê-lo atrás de um
número único.</p>

<p>Falta, para 06/10/2026: carga de apólices reais em PDF com extração
assistida por LLM <b>sempre revisada</b> contra a grade (o modelo localiza e
classifica; a pessoa confirma; o escore nunca sai do modelo), redação do
parecer por persona a partir do bloco de fatos que o comparador já produz, e
histórico de versões para comparar renovações ao longo do tempo.</p>
"""

    # ------------------------------------------------------ 15/16
    execucao = f"""
<h2>15. Como executar</h2>

<pre>git clone {REPO}
cd ai_to_so_desafio5_agrosentinela

python -m venv .venv &amp;&amp; source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # opcional: informe a GROQ_API_KEY
streamlit run app.py</pre>

<p>Sem nenhuma configuração adicional o aplicativo já funciona: usa a
amostra de demonstração, o gerador climático determinístico e o redator por
templates, sinalizando cada um desses caminhos.</p>

<h4>Linha de comando</h4>
<pre># pipeline completo, exportando os resultados
python -m agrosentinela.orchestrator --exportar saida/

# cenário de geada no Sul, sem IA generativa
python -m agrosentinela.orchestrator --cenario geada --uf RS SC PR --sem-llm

# testes
pytest -q</pre>

<h4>Carregando os dados oficiais do Banco Central</h4>
<pre>python etl/run_etl.py --anos 2025 2026
# em máquina modesta:
python etl/run_etl.py --anos 2026 --amostra 150000</pre>
<p>Depois, escolha «Somente dados curados do BCB» na barra lateral.</p>

<h4>Publicação no Streamlit Community Cloud</h4>
<ol>
  <li>Repositório público no GitHub.</li>
  <li>Em <code>share.streamlit.io</code>, apontar para <code>app.py</code>.</li>
  <li>Em <i>Settings → Secrets</i>, informar <code>GROQ_API_KEY</code>.</li>
</ol>

<h2>16. Referências</h2>
<ol>
  <li>BANCO CENTRAL DO BRASIL. <i>Tabelas e Microdados do Crédito Rural e do
      Proagro</i>. Disponível em: {esc(PAGINA_FONTE)}</li>
  <li>BANCO CENTRAL DO BRASIL. <i>Sicor — microdados do crédito rural e do
      Proagro: modelo e dicionário de dados</i>.</li>
  <li>BANCO CENTRAL DO BRASIL. <i>Sicor — modelo e dicionário dos dados
      complementares</i>.</li>
  <li>BANCO CENTRAL DO BRASIL. <i>Manual de Crédito Rural (MCR)</i>.</li>
  <li>OPEN-METEO. <i>Free Weather API</i>. https://open-meteo.com/</li>
  <li>GROQCLOUD. <i>Supported Models</i>. https://console.groq.com/docs/models</li>
  <li>ALLEN, R. G. et al. <i>Crop evapotranspiration: guidelines for computing
      crop water requirements</i>. FAO Irrigation and Drainage Paper 56, 1998.</li>
  <li>BRASIL. <i>Lei nº 13.709/2018 — Lei Geral de Proteção de Dados
      Pessoais</i>.</li>
</ol>

<div class="rodape">
  AgroSentinela v{esc(__version__)} · Relatório gerado automaticamente em
  {esc(datetime.now().strftime('%d/%m/%Y às %H:%M'))}<br>
  {esc(AUTOR)} · Desafio 5 — InsurMinds / I2A2 · Licença MIT<br>
  {esc(REPO)}
</div>
"""

    corpo = "".join([
        capa, sumario, executivo, problema, personas, arquitetura, agentes,
        tecnologias, fluxo, dados, regras, ia, exemplos, resultados, testes,
        privacidade, execucao,
    ])
    return (
        "<!DOCTYPE html><html lang='pt-BR'><head><meta charset='utf-8'>"
        "<title>AgroSentinela — Relatório Técnico · Desafio 5</title>"
        f"<style>{CSS}</style></head><body>{corpo}</body></html>"
    )


# ==========================================================================
# Conversão para PDF
# ==========================================================================

def html_para_pdf(caminho_html: Path, caminho_pdf: Path) -> bool:
    exe = shutil.which("wkhtmltopdf")
    if not exe:
        log.warning("wkhtmltopdf não encontrado — o PDF não será gerado por esta via.")
        return False
    base = [
        exe, "--enable-local-file-access",
        "--page-size", "A4",
        "--margin-top", "18mm", "--margin-bottom", "16mm",
        "--margin-left", "14mm", "--margin-right", "14mm",
        "--encoding", "utf-8",
    ]
    # Rodapé com numeração só existe em builds do wkhtmltopdf com Qt "patched".
    # Tentamos com rodapé e, se a build não suportar, repetimos sem ele.
    rodape = [
        "--footer-font-size", "7", "--footer-color", "#94a3b8",
        "--footer-right", "[page]/[topage]",
        "--footer-left", "AgroSentinela - Desafio 5 - InsurMinds/I2A2",
        "--footer-spacing", "6",
    ]
    for argumentos in (base + rodape, base):
        comando = [*argumentos, str(caminho_html), str(caminho_pdf)]
        try:
            proc = subprocess.run(comando, timeout=900,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if caminho_pdf.exists() and caminho_pdf.stat().st_size > 20_000:
                if b"unpatched qt" in proc.stderr.lower():
                    log.info("Build sem Qt patched: PDF gerado sem numeração de página.")
                return True
        except Exception as exc:  # noqa: BLE001
            log.warning("wkhtmltopdf falhou: %s", exc)
    return False


def gerar_docx(caminho_html: Path, caminho_docx: Path) -> bool:
    """
    Produz a versão editável (.docx) a partir do HTML do relatório.

    O pedido é simples e prático: o PDF serve para enviar, o DOCX para
    ajustar. Derivar os dois do mesmo HTML garante que digam a mesma coisa.
    """
    try:
        sys.path.insert(0, str(RAIZ / "scripts"))
        from docx_writer import (  # noqa: PLC0415
            html_para_markdown_simples,
            inserir_separadores_de_tabela,
            markdown_para_docx,
        )

        html_texto = caminho_html.read_text(encoding="utf-8")
        markdown = inserir_separadores_de_tabela(
            html_para_markdown_simples(html_texto)
        )
        resultado = markdown_para_docx(
            markdown, caminho_docx,
            titulo="AgroSentinela — Relatório Técnico",
            autor=AUTOR,
            assunto="Desafio 5 — Comunicação Inteligente (InsurMinds/I2A2)",
        )
        log.debug("DOCX gerado via %s", resultado.motor)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("Falha ao gerar o DOCX: %s", exc)
        return False


# ==========================================================================
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gera o relatório técnico do Desafio 5.")
    parser.add_argument("--com-llm", action="store_true",
                        help="Usa a IA generativa nos exemplos (exige GROQ_API_KEY).")
    parser.add_argument("--log", default="INFO")
    args = parser.parse_args(argv)

    configurar_logging(args.log)
    ARTEFATOS.mkdir(parents=True, exist_ok=True)

    # Garante que os diagramas existam
    if not (DIAGRAMAS / "arquitetura_pipeline.png").exists():
        log.info("Gerando os diagramas…")
        sys.path.insert(0, str(RAIZ / "scripts"))
        import gerar_diagramas  # noqa: PLC0415

        gerar_diagramas.main()

    log.info("Executando o pipeline para coletar métricas e exemplos reais…")
    contexto, mensagens = executar_demonstracoes(args.com_llm)
    log.info("%d mensagens de exemplo coletadas (persona × canal distintos).", len(mensagens))

    html_final = montar_html(contexto, mensagens, args.com_llm)
    SAIDA_HTML.write_text(html_final, encoding="utf-8")
    log.info("HTML gravado: %s (%.0f KB)", SAIDA_HTML, SAIDA_HTML.stat().st_size / 1024)

    ok_pdf = html_para_pdf(SAIDA_HTML, SAIDA_PDF)
    if ok_pdf:
        log.info("✅ PDF gerado: %s (%.0f KB)", SAIDA_PDF, SAIDA_PDF.stat().st_size / 1024)
    else:
        log.error("Não foi possível gerar o PDF. Instale o wkhtmltopdf ou abra o "
                  "HTML no navegador e use «Imprimir → Salvar como PDF».")

    # Versão editável. O DOCX é derivado do **mesmo HTML** que virou PDF, e
    # não de um texto paralelo: manter duas fontes de verdade do mesmo
    # relatório é a forma mais confiável de os dois documentos divergirem
    # com o tempo, e quem recebe os dois não tem como saber qual está certo.
    if gerar_docx(SAIDA_HTML, SAIDA_DOCX):
        log.info("📘 DOCX editável: %s (%.0f KB)",
                 SAIDA_DOCX.name, SAIDA_DOCX.stat().st_size / 1024)
    else:
        log.warning("DOCX não gerado.")

    return 0 if ok_pdf else 1


if __name__ == "__main__":
    raise SystemExit(main())
