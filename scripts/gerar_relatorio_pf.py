"""
Gera o Relatório Técnico do Projeto Final (PDF).

    python scripts/gerar_relatorio_pf.py

Saída: Projeto_Final_Artefatos/InsurMinds_Projeto_Final_Relatorio_Tecnico.pdf
"""

from __future__ import annotations

import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_JUSTIFY  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    Image, KeepTogether, PageBreak, Paragraph, Preformatted, SimpleDocTemplate, Spacer,
    Table, TableStyle,
)

from agrosentinela.config import APOLICES_DIR  # noqa: E402
from agrosentinela.projeto_final.clausulas import CLAUSULAS, GRUPOS_CLAUSULA  # noqa: E402
from agrosentinela.projeto_final.extracao import SISTEMA_CADASTRO  # noqa: E402

ART = ROOT / "Projeto_Final_Artefatos"
CAP = ART / "capturas"
SAIDA = ART / "InsurMinds_Projeto_Final_Relatorio_Tecnico.pdf"

def _dir_fontes() -> Path:
    """DejaVu acompanha o matplotlib em qualquer sistema operacional."""
    try:
        import matplotlib

        return Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    except ModuleNotFoundError:
        return Path(".")


FONTES = _dir_fontes()
try:
    pdfmetrics.registerFont(TTFont("Corpo", str(FONTES / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("Corpo-B", str(FONTES / "DejaVuSans-Bold.ttf")))
    pdfmetrics.registerFont(TTFont("Mono", str(FONTES / "DejaVuSansMono.ttf")))
    from reportlab.pdfbase.pdfmetrics import registerFontFamily
    registerFontFamily("Corpo", normal="Corpo", bold="Corpo-B", italic="Corpo", boldItalic="Corpo-B")
    F, FB, FM = "Corpo", "Corpo-B", "Mono"
except Exception:  # noqa: BLE001 - fontes ausentes (ex.: Windows)
    F, FB, FM = "Helvetica", "Helvetica-Bold", "Courier"

VERDE, OURO, CINZA = colors.HexColor("#1F4D36"), colors.HexColor("#D9A441"), colors.HexColor("#5f6f66")
st = {
    "t": ParagraphStyle("t", fontName=FB, fontSize=22, leading=27, textColor=VERDE, spaceAfter=10),
    "st": ParagraphStyle("st", fontName=F, fontSize=12, leading=16, textColor=CINZA),
    "h1": ParagraphStyle("h1", fontName=FB, fontSize=15, leading=19, textColor=VERDE,
                         spaceBefore=12, spaceAfter=6),
    "h2": ParagraphStyle("h2", fontName=FB, fontSize=11.5, leading=15, textColor=VERDE,
                         spaceBefore=8, spaceAfter=4),
    "p": ParagraphStyle("p", fontName=F, fontSize=9.6, leading=13.6, alignment=TA_JUSTIFY,
                        spaceAfter=5),
    "b": ParagraphStyle("b", fontName=F, fontSize=9.6, leading=13.4, leftIndent=12,
                        bulletIndent=2, spaceAfter=2),
    "c": ParagraphStyle("c", fontName=F, fontSize=8.3, leading=11, textColor=CINZA,
                        spaceAfter=8),
    "tab": ParagraphStyle("tab", fontName=F, fontSize=8.2, leading=10.6),
    "code": ParagraphStyle("code", fontName=FM, fontSize=7.4, leading=9.4,
                           backColor=colors.HexColor("#F2F5F2"), borderPadding=5),
}


def _amp(t: str) -> str:
    import re
    return re.sub(r"&(?!amp;|lt;|gt;|#)", "&amp;", t)


def P(t, s="p"):
    return Paragraph(_amp(t), st[s])


def B(itens):
    return [Paragraph(_amp(i), st["b"], bulletText="•") for i in itens]


def T(linhas, larg, cab=True):
    dados = [[Paragraph(_amp(str(c)), st["tab"]) for c in l] for l in linhas]
    t = Table(dados, colWidths=[w * cm for w in larg], repeatRows=1 if cab else 0)
    estilo = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B9CDBE")),
              ("VALIGN", (0, 0), (-1, -1), "TOP"),
              ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if cab:
        estilo += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E3ECE5"))]
    t.setStyle(TableStyle(estilo))
    return t


def img(nome, largura_cm=16.5, legenda=""):
    caminho = CAP / nome
    w, h = _abrir_imagem(caminho).size
    el = [Image(str(caminho), width=largura_cm * cm, height=largura_cm * cm * h / w)]
    if legenda:
        el.append(P(legenda, "c"))
    return KeepTogether(el)


def _abrir_imagem(caminho):
    """Abre imagem a partir dos bytes (sem open() de texto — portável)."""
    from PIL import ImageFile

    parser = ImageFile.Parser()
    parser.feed(Path(caminho).read_bytes())
    return parser.close()


def rodape(canvas, doc):
    canvas.saveState()
    canvas.setFont(F, 7.5)
    canvas.setFillColor(CINZA)
    canvas.drawString(2 * cm, 1.1 * cm, "InsurMinds/I2A2 · Projeto Final · AgroSentinela — "
                      "Plataforma de análise e comparação de apólices D&O")
    canvas.drawRightString(A4[0] - 2 * cm, 1.1 * cm, f"pág. {doc.page}")
    canvas.restoreState()


def main() -> None:
    aval = pd.read_csv(APOLICES_DIR / "avaliacao_deterministico.csv")
    aval_llm_csv = APOLICES_DIR / "avaliacao_llm.csv"
    aval_llm = pd.read_csv(aval_llm_csv) if aval_llm_csv.exists() else None

    h: list = []
    # ------------------------------------------------------------ capa
    h += [Spacer(1, 3 * cm), P("Relatório Técnico — Projeto Final", "st"),
          P("Plataforma inteligente para análise e comparação de apólices D&O do agronegócio", "t"),
          P("AgroSentinela · módulo de apólices integrado à ferramenta de comunicação proativa "
            "para crédito rural e Proagro (Desafio 5)", "st"), Spacer(1, 1.2 * cm),
          T([["Curso", "InsurMinds — Inteligência Artificial Aplicada a Seguros (I2A2)"],
             ["Entrega", "Projeto Final — Comparação de Apólices · 06/10/2026"],
             ["Integrante(s)", "Jefferson Luiz Gonçalves Silva (representante)"],
             ["Repositório", "https://github.com/jlgsilva/insurminds-projeto-final"],
             ["Licença", "MIT"]], [4, 12], cab=False),
          Spacer(1, 1 * cm),
          P("<b>Aviso.</b> Todas as apólices usadas na demonstração são <b>simuladas</b> "
            "(seguradoras, tomadoras, CNPJs e valores fictícios), geradas pelo próprio projeto "
            "com marca d'água e gabarito. A plataforma aceita apólices reais enviadas pelo usuário."),
          PageBreak()]

    # ------------------------------------------------------------ 1
    h += [P("1. Problema e objetivo", "h1"),
          P("Apólices de D&O (<i>Directors &amp; Officers</i>) protegem o patrimônio pessoal de "
            "administradores. São documentos longos e jurídicos, e as diferenças que decidem um "
            "sinistro — custos de defesa dentro ou fora do limite, retroatividade, adiantamento, "
            "exclusão de dolo por mera alegação, ordem de pagamento — raramente aparecem na proposta "
            "comercial. Comparar cotações exige horas de especialista."),
          P("No agronegócio, foco desta linha de trabalho desde o Desafio 4, a exposição do "
            "administrador inclui temas que o D&O genérico não trata: processo sancionador do Banco "
            "Central por irregularidade em crédito rural e Proagro, responsabilidade ambiental na "
            "cadeia de fornecedores e recuperação judicial de produtores e agroindústrias."),
          P("<b>Objetivo:</b> um MVP que recebe apólices (PDF ou imagem), extrai automaticamente as "
            "informações relevantes com IA generativa, armazena de forma estruturada, permite "
            "consultar e comparar duas ou mais apólices e apresenta as diferenças — como módulo da "
            "mesma aplicação do Desafio 5, reaproveitando seu núcleo de agentes e sua base do Sicor."),
          P("Atendimento aos requisitos mínimos do enunciado", "h2"),
          T([["Requisito", "Como é atendido"],
             ["Leitura de PDF ou imagem", "pdfplumber (texto), OCR Tesseract por página para digitalizadas e fotos (JPG/PNG/TIFF)"],
             ["Extração automática", "CadastroAgent e ClausulasAgent (LLM Groq) + linha de base determinística"],
             ["Estruturação organizada", "JSON validado → SQLite (6 tabelas)"],
             ["Comparar ≥ 2 apólices", "ComparadorAgent compara N apólices cláusula a cláusula"],
             ["Mostrar principais diferenças", "Placar, cláusulas críticas, diferenças relevantes, lacunas, relatório por IA"],
             ["≥ 1 modelo de IA generativa", "GPT-OSS 120B e 20B (Groq) em 4 agentes"],
             ["Interface de demonstração", "Streamlit: páginas Ingestão, Comparador e Consulta"]], [5, 11.5])]

    # ------------------------------------------------------------ 2
    h += [P("2. Arquitetura da solução", "h1"),
          img("diagrama_arquitetura.png", 16.5, "Figura 1 — 10 agentes em 3 fluxos. Dourado: usa LLM; "
              "verde: determinístico."),
          P("A arquitetura separa três fluxos. <b>Ingestão</b> transforma documentos em dados "
            "estruturados; <b>Comparação</b> transforma dados em decisão explicada; <b>Consulta</b> "
            "permite perguntas livres sobre a base. Todos os agentes herdam a classe <i>Agente</i> do "
            "Desafio 5: responsabilidade única, contrato de entrada e saída via um contexto "
            "compartilhado (o \"quadro-negro\"), cronometragem, captura de falha isolada e métricas — "
            "o rastro de cada execução aparece na interface e na tabela de auditoria."),
          P("Princípio central: o modelo lê e redige; as regras decidem", "h2"),
          P("O LLM é usado onde só ele resolve bem — entender cláusulas escritas de formas diferentes "
            "e redigir explicações para públicos distintos. Escores, lacunas e números finais são "
            "calculados por código determinístico. Ninguém deve decidir uma contratação de cobertura "
            "com base num número que não consegue refazer.")]

    # ------------------------------------------------------------ 3
    h += [P("3. Tecnologias utilizadas", "h1"),
          T([["Camada", "Tecnologia", "Uso"],
             ["Interface", "Streamlit", "Aplicação multipágina (Desafio 5 + Projeto Final)"],
             ["IA generativa", "GroqCloud — openai/gpt-oss-120b e openai/gpt-oss-20b",
              "Extração, classificação, relatório e consulta (JSON mode, tool calling, reasoning_effort)"],
             ["OCR", "Tesseract 5 (por) + pytesseract; pypdfium2", "Páginas digitalizadas e fotos"],
             ["PDF", "pdfplumber; reportlab", "Leitura; geração do acervo simulado"],
             ["Banco", "SQLite", "Armazenamento estruturado e auditoria"],
             ["Dados", "pandas; microdados Sicor/Proagro (BCB)", "Perfil de risco da tomadora"],
             ["Qualidade", "pytest + GitHub Actions (Linux e Windows)", "Testes de unidade, pipeline e páginas"]],
            [2.8, 6.2, 7.5]),
          P("Escolha do modelo: em outubro de 2026 os modelos Llama 3.x da Groq passaram ao plano "
            "Enterprise; a família GPT-OSS está em <i>produção</i> (sem risco de descontinuação "
            "súbita, ao contrário dos modelos <i>preview</i>) e disponível no plano gratuito. "
            "O modelo de 20B (≈1000 tokens/s) cuida da tarefa simples (quadro-resumo); o de 120B, "
            "das tarefas de interpretação. <i>reasoning_effort=low</i> poupa a cota de tokens por "
            "minuto sem perda relevante numa extração guiada por esquema.")]

    # ------------------------------------------------------------ 4
    h += [PageBreak(), P("4. Agentes desenvolvidos", "h1"),
          T([["Agente", "Responsabilidade", "IA?"],
             ["RecepcaoAgent", "Agrupa páginas (X_p1.jpg, X_p2.jpg), valida tipo e tamanho, SHA-256 contra duplicidade", "—"],
             ["LeituraOCRAgent", "Texto do PDF ou OCR por página; remove cabeçalho/rodapé repetidos; segmenta em seções", "—"],
             ["CadastroAgent", "Quadro-resumo → 14 campos (seguradora, tomadora, UF, vigência, retroatividade, LMG, prêmio, franquia…)", "gpt-oss-20b"],
             ["ClausulasAgent", "Mapeia seções para a taxonomia de 32 cláusulas pelo significado; nível + seção + evidência literal", "gpt-oss-120b"],
             ["ValidacaoAgent", "Esquema, evidência no texto, números LLM × regex, coerência, confiança 0–100, acurácia vs. gabarito", "—"],
             ["ArmazenamentoAgent", "Grava documento, cadastro, cláusulas, seções e auditoria no SQLite", "—"],
             ["PerfilRiscoAgent", "Indicadores Sicor/Proagro da UF + segmento → ajuste de pesos com motivo", "—"],
             ["ComparadorAgent", "Escore ponderado geral e crítico, por grupo, prêmio por ponto, lacunas, diferenças", "—"],
             ["RelatorAgent", "Relatório comparativo para 5 públicos a partir de bloco de fatos fechado", "gpt-oss-120b"],
             ["ConsultaAgent", "Perguntas em linguagem natural com 6 ferramentas sobre a base", "gpt-oss-120b"]],
            [3.6, 10.6, 2.3]),
          P("Taxonomia de cláusulas", "h2"),
          P(f"{len(CLAUSULAS)} cláusulas em {len(GRUPOS_CLAUSULA)} grupos ("
            + ", ".join(GRUPOS_CLAUSULA) + f"), {sum(c.critica for c in CLAUSULAS)} marcadas como "
            "críticas. Cada cláusula tem peso (1–5), pergunta-guia, \"por que importa\" e base "
            "legal. Níveis: ampla (1,0), padrão (0,7), restrita (0,4), ausente e excluída (0). "
            "O grupo <b>Riscos do agronegócio</b> (AGR-01 crédito rural e Proagro, AGR-02 ambiental, "
            "AGR-03 recuperação judicial) é a contribuição específica desta linha de pesquisa.")]

    # ------------------------------------------------------------ 5
    h += [P("5. Fluxo completo de processamento", "h1"),
          *B(["<b>Recebimento</b>: upload (ou seleção no acervo) → agrupamento e deduplicação.",
              "<b>Extração</b>: por página, texto nativo se houver ≥ 60 caracteres; senão rasterização a 200 dpi e OCR em português (uma passada que devolve texto e confiança).",
              "<b>Limpeza e segmentação</b>: linhas que se repetem em metade ou mais das páginas (cabeçalho, rodapé, \"pág. n\") são removidas; o texto é dividido por títulos numerados (CLÁUSULA n –, n. TÍTULO, Art. nº –).",
              "<b>Estruturação por IA</b>: quadro-resumo (20B) e cláusulas (120B), ambos em JSON, temperatura 0.",
              "<b>Validação</b>: vocabulário, evidência, números, coerência; confiança e alertas.",
              "<b>Armazenamento</b>: SQLite + trilha de auditoria por agente.",
              "<b>Comparação</b>: perfil de risco → pesos → escores, lacunas e diferenças.",
              "<b>Apresentação</b>: relatório por IA para o público escolhido, tabelas coloridas por nível, evidências literais lado a lado, download em Markdown."]),
          img("02_ingestao_resultado.png", 15, "Figura 2 — Ingestão: cláusulas com nível, seção e "
              "evidência verificada (captura em modo determinístico).")]

    # ------------------------------------------------------------ 6
    h += [PageBreak(), P("6. Uso de IA e controles", "h1"),
          T([["Agente", "Configuração", "Controle de qualidade"],
             ["CadastroAgent", "gpt-oss-20b · JSON · T=0 · ≤3,5 mil caracteres", "Regex lê o mesmo quadro; em divergência, prevalece o documento"],
             ["ClausulasAgent", "gpt-oss-120b · JSON · T=0 · seções [S1..Sn] + taxonomia", "Vocabulário fechado; evidência literal procurada no texto (busca aproximada tolerante a OCR)"],
             ["RelatorAgent", "gpt-oss-120b · T=0,3 · bloco de fatos JSON", "Verificador: todo número do texto precisa existir nos fatos"],
             ["ConsultaAgent", "gpt-oss-120b · tool calling · ≤5 iterações", "Responde só com o retorno das ferramentas; tabelas exibidas"]],
            [3, 6.3, 7.2]),
          P("Infraestrutura LLM herdada do Desafio 5: chamada HTTP direta à API compatível com "
            "OpenAI (sem SDK), cache em disco por hash do payload, orçamento de chamadas por "
            "execução, respeito a <i>Retry-After</i> em 429, <i>backoff</i> exponencial e telemetria "
            "de tokens e latência por tarefa. Sem chave ou sem cota, cada agente de IA tem caminho "
            "determinístico: a demonstração nunca fica sem resultado, e a interface indica a origem "
            "de cada dado."),
          P("Prompt do CadastroAgent (exemplo)", "h2"),
          Preformatted(SISTEMA_CADASTRO, st["code"])]

    # ------------------------------------------------------------ 7
    h += [P("7. Justificativa das decisões arquiteturais", "h1"),
          T([["Decisão", "Alternativa descartada", "Por quê"],
             ["LLM classifica, código pontua", "LLM dar nota ou ranking", "Decisão de cobertura exige número reproduzível"],
             ["Taxonomia fixa de cláusulas", "Comparação livre texto × texto", "Permite medir, comparar N apólices e auditar"],
             ["Evidência literal obrigatória", "Confiar no rótulo do modelo", "Detecção automática de alucinação"],
             ["Dois modelos (20B e 120B)", "Um modelo para tudo", "Economiza cota onde a tarefa é simples"],
             ["OCR por página", "OCR do documento inteiro", "Apólices reais misturam páginas nativas e escaneadas"],
             ["Linha de base determinística", "Só LLM", "Contingência e régua para medir o ganho da IA"],
             ["SQLite", "Postgres / NoSQL", "Zero infraestrutura; esquema migra sem alteração"],
             ["Classe Agente própria", "LangGraph / CrewAI", "Mesma do Desafio 5; explícita e auditável; contrato compatível com grafo"],
             ["Pesos ajustados pelo Sicor", "Pesos fixos", "A importância de uma cláusula depende de quem é a tomadora"],
             ["Acervo simulado com gabarito", "Apólices reais", "Apólices emitidas não são públicas; o gabarito permite medir acurácia"]],
            [4.3, 4.3, 7.9])]

    # ------------------------------------------------------------ 8
    h += [PageBreak(), P("8. Dados", "h1"),
          P("Acervo simulado", "h2"),
          P("Apólices emitidas de D&amp;O não são públicas, então o projeto gera um acervo "
            f"<b>declaradamente simulado</b>, com gabarito: <b>{len(aval)} apólices</b> de "
            "<b>6 seguradoras fictícias, 20 cada</b>, para <b>45 tomadoras</b> em 25 UFs e no DF. "
            "Como no mercado real, <b>cada seguradora tem a sua própria arquitetura de documento</b> "
            "— não é um template com nomes trocados:"),
          T([["Seguradora (fictícia)", "Arquitetura", "Inspiração estrutural"],
             ["Atalaia Linhas Financeiras", "decimal com glossário; Garantia A/B; extensões 4.x; exclusões 6.x; especificação em tabela", "C.G. públicas AIG"],
             ["Ipê-Roxo Seguradora", "dados em lista; romanos; exclusões em CAIXA ALTA; POS; valores por extenso", "C.G. públicas Allianz"],
             ["Jacarandá Cia. de Seguros", "hierárquico 2.1.1; LMI; prazo complementar/suplementar; especificação no FIM", "C.G. públicas Tokio Marine (até 2021)"],
             ["Xique-Xique Seguros Gerais", "dados em prosa; Cláusula 1ª, 2ª…; cláusulas particulares rurais; R$ 5 milhões", "C.G. públicas Sompo"],
             ["Mutirão Seguros Mútuos", "linguagem simples em perguntas e respostas; datas por extenso", "guias de seguro cooperativo"],
             ["Minuano Specialty", "Policy Schedule bilíngue (Item 1…9); Side A/B/C; endossos; BRL 5,000,000.00", "mercado de Londres"]],
            [4.2, 8.5, 3.8]),
          P("As inspirações referem-se só à organização dos documentos; nenhum texto foi copiado. "
            "As tomadoras cobrem nove perfis — associações extrativistas e cooperativas de "
            "agricultura familiar (Pronaf), pequenas agroindústrias, médios produtores (Pronamp), "
            "grandes grupos, latifúndios, cooperativas de crédito rural, cooperativas "
            "agroindustriais, agroindústrias e a cadeia (trading, insumos, securitização de CPR) — e "
            "as particularidades de cada território (Amazônia Legal, semiárido, Matopiba, Pantanal, "
            "Sul pós-enchente). Regras de coerência ligam perfil e território às cláusulas e aos "
            "valores (ex.: cooperativa familiar sem Side C, LMG até R$ 3 milhões e cobertura só no "
            "Brasil; seguradora generalista excluindo risco ambiental na Amazônia Legal). Formatos: "
            "104 PDFs com texto, 12 digitalizados e 4 fotografados. Novos lotes podem ser gerados "
            "por outra IA com o prompt de docs/PROMPT_GERAR_APOLICES.md e importados com validação "
            "(scripts/importar_apolices_externas.py)."),
          P("Sicor e Proagro (Banco Central)", "h2"),
          P("A base do Desafio 5 (operações de crédito rural, acionamento do Proagro e saldos) "
            "alimenta o PerfilRiscoAgent: crédito rural e participação da UF, % de operações sem "
            "cobertura, taxa de acionamento do Proagro na UF comparada à média nacional, evento mais "
            "frequente, % de operações em atraso e renegociadas. Regras explícitas transformam esses "
            "indicadores em fatores de peso (ex.: UF da Amazônia Legal/Matopiba → AGR-02 ×1,6)."),
          img("08_perfil.png", 13, "Figura 3 — Perfil da tomadora com indicadores do Sicor/Proagro "
              "e ajustes de peso.")]

    # ------------------------------------------------------------ 9
    nomes = {"ATA": "Atalaia (decimal + glossário)", "IPE": "Ipê-Roxo (romanos, caixa alta)",
             "JAC": "Jacarandá (hierárquico, espec. no fim)", "XIQ": "Xique-Xique (prosa, ordinais)",
             "MUT": "Mutirão (perguntas e respostas)", "MIN": "Minuano (schedule bilíngue)"}
    aval["seg"] = aval["identificador"].str.split("-").str[1]
    por_seg = aval.groupby("seg")[["acuracia_campos", "acuracia_presenca", "acuracia_clausulas"]].mean()
    linhas = [["Arquitetura (seguradora)", "Apólices", "Campos do quadro", "Presença de cláusula",
               "Nível da cláusula"]]
    for seg, r in por_seg.iterrows():
        linhas.append([nomes.get(seg, seg), str(int((aval["seg"] == seg).sum())),
                       f"{r['acuracia_campos']:.1f}%", f"{r['acuracia_presenca']:.1f}%",
                       f"{r['acuracia_clausulas']:.1f}%"])
    linhas.append(["<b>Linha de base — total</b>", str(len(aval)), f"{aval['acuracia_campos'].mean():.1f}%",
                   f"{aval['acuracia_presenca'].mean():.1f}%", f"{aval['acuracia_clausulas'].mean():.1f}%"])
    if aval_llm is not None and not aval_llm.empty:
        linhas.append(["<b>IA (Groq GPT-OSS) — total</b>", str(len(aval_llm)),
                       f"{aval_llm['acuracia_campos'].mean():.1f}%",
                       f"{aval_llm['acuracia_presenca'].mean():.1f}%",
                       f"{aval_llm['acuracia_clausulas'].mean():.1f}%"])
    resumo = {"linha_de_base": {seg: {k: round(float(v), 1) for k, v in r.items()}
                                for seg, r in por_seg.iterrows()},
              "total_linha_de_base": {k: round(float(aval[k].mean()), 1) for k in
                                      ("acuracia_campos", "acuracia_presenca", "acuracia_clausulas")},
              "apolices": int(len(aval))}
    if aval_llm is not None and not aval_llm.empty:
        resumo["total_ia"] = {k: round(float(aval_llm[k].mean()), 1) for k in
                              ("acuracia_campos", "acuracia_presenca", "acuracia_clausulas")}
        resumo["apolices_ia"] = int(len(aval_llm))
    (ART / "avaliacao_resumo.json").write_text(__import__("json").dumps(resumo, ensure_ascii=False,
                                                                        indent=1), encoding="utf-8")
    pior = por_seg["acuracia_clausulas"].idxmin()
    TB_pres = round(float(aval["acuracia_presenca"].mean()), 1)
    TB_niv = round(float(aval["acuracia_clausulas"].mean()), 1)
    h += [P("9. Resultados", "h1"),
          P("Acurácia da extração contra o gabarito, por arquitetura de documento:"),
          T(linhas, [5.4, 1.7, 2.9, 3.2, 3.3]),
          P("A linha de base determinística (rótulos conhecidos do mercado + dicionário de títulos + "
            "expressões-gatilho) lê bem o quadro de dados em quase todas as arquiteturas — inclusive "
            "a especificação no fim, o preâmbulo em prosa e o schedule bilíngue —, mas <b>não "
            "generaliza</b> na leitura das cláusulas: o nível exato fica em torno de três em cada "
            f"quatro, e despenca no documento de {nomes.get(pior, pior).split(' (')[0]} "
            f"({por_seg.loc[pior, 'acuracia_clausulas']:.0f}%), escrito em perguntas e respostas, "
            "sem os termos técnicos que o dicionário procura. É exatamente o caso em que a leitura "
            "por significado do ClausulasAgent (LLM) faz diferença. A mesma régua mede a IA: "
            "<i>python scripts/processar_acervo.py --llm</i> gera <i>avaliacao_llm.csv</i>, e a "
            "página de Ingestão mostra os dois métodos lado a lado, com matriz de confusão."),
          img("07b_diferencas.png", 15, "Figura 4 — Comparação de cotações: só as cláusulas que "
              "divergem, ordenadas pela amplitude."),
          P("Achado típico", "h2"),
          P("O comparador sinaliza quando a apólice com maior escore geral não é a melhor nas "
            "cláusulas críticas — o caso em que um ranking simples levaria à escolha errada.")]

    # ------------------------------------------------------------ 9b reais
    rr_arq = ART / "avaliacao_reais.json"
    if rr_arq.exists():
        rr = __import__("json").loads(rr_arq.read_text(encoding="utf-8")).get("deterministico", {})
        pd_ = rr.get("por_documento", {})
        h += [P("9.1 Validação com documentos reais", "h2"),
              P("Na reta final, um colega do curso enviou <b>cinco documentos reais</b>: as "
                "condições gerais de D&amp;O de três seguradoras (AXA, 104 páginas; Allianz, 75; "
                "Porto, 52 — textos públicos registrados na SUSEP) e duas apólices emitidas de "
                "<b>Seguro Garantia</b>, com dados de empresas e pessoas reais. Os PDFs não foram "
                "incluídos no repositório e nenhum dado das apólices de garantia foi copiado; os "
                "arquivos são reconhecidos pelo SHA-256 (data/apolices_reais/)."),
              P("Para as três condições gerais foi montado um gabarito das 32 cláusulas, com "
                "leitura integral assistida por IA (Claude) e evidência literal de até 25 palavras "
                "conferida por script contra o texto. Os níveis são julgamento técnico e precisam "
                "de revisão por especialista; presença/ausência é o critério mais objetivo."),
              P("<b>O que o teste revelou (antes das correções)</b>"),
              *B(["<b>O LLM via só o começo do documento.</b> O texto enviado à IA era cortado em "
                  "14 mil caracteres — cerca de 6% de uma condição geral real (170–240 mil). Na "
                  "prática, a IA lia sumário e glossário: só 5 dos 91 trechos do gabarito que "
                  "comprovam as cláusulas chegavam a ela.",
                  "<b>O sumário e o glossário enganavam as regras.</b> Cada título do índice virava "
                  "uma seção, e a definição de “multa” no glossário era lida como cobertura de "
                  "multas.",
                  "<b>Documento de outro ramo entrava como D&amp;O.</b> As duas apólices de Seguro "
                  "Garantia seriam gravadas como “apólices D&amp;O” cheias de lacunas — um "
                  "resultado errado com cara de certo.",
                  "<b>Sem quadro-resumo, a seguradora não era identificada</b> (o nome está no "
                  "cabeçalho e no rodapé, que o leitor remove)."]),
              P("<b>O que mudou</b>"),
              *B(["Agente de leitura identifica o <b>ramo</b> (D&amp;O, Seguro Garantia, RC, "
                  "patrimonial, rural, vida) e o <b>tipo</b> (condições gerais × apólice emitida); "
                  "documento fora do escopo é recusado com aviso e não vai para a base.",
                  "Remoção do sumário; cada seção recebe a <b>parte</b> do documento (glossário, "
                  "exclusões, geral): definição não conta como cobertura, e uma cobertura que só "
                  "aparece nas exclusões é classificada como excluída.",
                  "<b>Seleção de trechos para documentos longos</b> (recuperação simples, sem banco "
                  "vetorial): para cada cláusula, as seções mais prováveis por título, vocabulário e "
                  "parte do documento; a classificação vai em dois lotes de códigos, para caber no "
                  "plano gratuito da Groq. Documentos curtos continuam indo inteiros.",
                  "Vocabulário de mercado ampliado com o dos documentos reais (participação "
                  "obrigatória, limite agregado, gastos com defesa, ordem dos pagamentos, litígio "
                  "anterior e pendente…); nome da seguradora lido no cabeçalho/rodapé.",
                  "Validação ajustada: em condições gerais, a falta de tomadora e valores é esperada."]),
              P("<b>Resultado</b>"),
              T([["Indicador", "Antes", "Depois"],
                 ["Documentos de outro ramo recusados", "0 de 2",
                  f"{rr.get('fora_do_escopo_recusados', 0)} de {rr.get('fora_do_escopo_total', 0)}"],
                 ["Ramo e tipo identificados corretamente", "—",
                  f"{rr.get('ramo_correto', 0)} e {rr.get('tipo_correto', 0)} de {rr.get('documentos', 0)}"],
                 ["Seguradora identificada (condições gerais)", "—", f"{rr.get('seguradora_ok', 0)} de 3"],
                 ["Trechos do gabarito que chegam à IA", "5 de 91 (5%)", "51 de 91 (56%)"],
                 ["Presença/ausência por regras (média)", "63,6%",
                  f"{str(rr.get('acuracia_presenca')).replace('.', ',')}%"],
                 ["Nível exato por regras (média)", "33,3%",
                  f"{str(rr.get('acuracia_nivel')).replace('.', ',')}%"],
                 ["Acervo simulado — presença / nível por regras", "86,3% / 68,8%",
                  f"{str(TB_pres).replace('.', ',')}% / {str(TB_niv).replace('.', ',')}%"]],
                [8.2, 3.6, 4.7]),
              P("Por documento (depois, regras): " + "; ".join(
                  f"{k.replace('REAL-', '').title()}: presença {v['presenca']}%, nível {v['nivel']}%"
                  for k, v in pd_.items()) + ". “Trechos que chegam à IA” é uma medida estrita "
                "(o trecho exato anotado precisa estar no texto enviado); a mesma cláusula costuma "
                "aparecer em outros pontos do documento."),
              P("<b>Cuidados na leitura.</b> O vocabulário foi ampliado olhando estes mesmos "
                "documentos, então o resultado é <i>dentro da amostra</i> e tende a ser otimista; "
                "validar fora da amostra exige novas condições gerais. O nível exato por regras "
                "continua baixo (cerca de 4 em 10): é a tarefa que depende da IA. A medição com a "
                "IA nos documentos reais roda com <i>python scripts/avaliar_documentos_reais.py "
                "--llm</i> e não foi feita nesta entrega por falta de chave da Groq no ambiente "
                "de desenvolvimento.")]

    # ------------------------------------------------------------ 10-11
    h += [P("10. Limitações conhecidas", "h1"),
          *B(["Acervo simulado: 6 arquiteturas e dialetos distintos, mas o conteúdo das cláusulas parte de uma redação-base comum; apólices reais variam mais.",
              "Segmentação reconhece as convenções de mercado (numeração, ordinais, romanos, alíneas, perguntas, caixa alta); documentos sem nenhuma marcação viram poucas seções longas, com evidência menos precisa.",
              "OCR de baixa qualidade reduz a confiança (o sistema avisa e penaliza o índice).",
              "Plano gratuito da Groq limita tokens por minuto; em documentos longos a IA recebe trechos selecionados (cerca de 56% dos trechos-chave do gabarito chegam a ela), não o texto inteiro.",
              "Validação real ainda pequena: 3 condições gerais de D&O (dentro da amostra) e nenhuma apólice D&O emitida real; o gabarito real foi anotado com apoio de IA e precisa de revisão por especialista.",
              "Sistema de apoio à decisão — não é parecer jurídico nem recomendação de contratação."]),
          P("11. Possibilidades de evolução", "h1"),
          *B(["RAG sobre as Condições Gerais registradas na SUSEP de cada produto.",
              "Extração em duas passadas (localizar → classificar) para documentos longos.",
              "LLM multimodal para tabelas, carimbos e anexos escaneados.",
              "Integração com o Desafio 5: alerta climático → revisão automática de coberturas D&O de cooperativas expostas.",
              "Comparação temporal de endossos e renovações da mesma apólice.",
              "Calibração de pesos e níveis com avaliação humana de corretores."])]

    # ------------------------------------------------------------ 12-13
    h += [P("12. Instalação e execução", "h1"),
          Preformatted("git clone https://github.com/jlgsilva/insurminds-projeto-final.git\n"
                       "cd insurminds-projeto-final\n"
                       "python -m venv .venv  &&  .venv\\Scripts\\activate   (Linux: source .venv/bin/activate)\n"
                       "pip install -r requirements.txt\n"
                       "copy .env.example .env   (preencha GROQ_API_KEY)\n"
                       "streamlit run app.py", st["code"]),
          P("No Streamlit Community Cloud, o arquivo packages.txt instala o Tesseract e a chave é "
            "informada em Settings → Secrets. Instruções completas no README."),
          P("13. Referências", "h1"),
          *B(["I2A2 — InsurMinds: Desafios 3, 4, 5 e Projeto Final (enunciado).",
              "SUSEP — Circular nº 637/2021 (seguros de responsabilidade civil; revogou a Circular 553/2017).",
              "Banco Central do Brasil — Tabelas e Microdados do Crédito Rural e do Proagro (Sicor): "
              "bcb.gov.br/estabilidadefinanceira/tabelas-credito-rural-proagro.",
              "Lei 6.404/1976; Lei 13.709/2018 (LGPD); Lei 9.605/1998; Lei 12.651/2012; Lei 11.101/2005 e "
              "Lei 14.112/2020; Lei 13.506/2017; Manual de Crédito Rural (BCB).",
              "GroqCloud — Supported Models e Reasoning: console.groq.com/docs/models; console.groq.com/docs/reasoning.",
              "Tesseract OCR — github.com/tesseract-ocr."])]

    # ------------------------------------------------------------ apêndice: processo
    h += [P("Apêndice — Processo de criação e uso de IA no desenvolvimento", "h1"),
          P("Este apêndice registra, de forma transparente, como o projeto foi construído. Foram "
            "usadas três inteligências artificiais, com papéis distintos; as decisões de escopo, as "
            "premissas e a aceitação de cada entrega ficaram com o autor."),
          T([["IA", "Papel", "O que fez"],
             ["Claude (Anthropic)", "Assistente de desenvolvimento",
              "Pesquisou referências públicas, escreveu o código, os testes automáticos, a documentação, "
              "o gerador de apólices simuladas e a primeira versão do deck, do vídeo-base e deste relatório."],
             ["Groq — GPT-OSS 120B/20B", "IA dentro do aplicativo",
              "Lê as apólices (cadastro e cláusulas), redige o relatório comparativo e responde perguntas "
              "com ferramentas sobre a base."],
             ["Outra IA, à escolha", "Ampliação da base",
              "Recebe o prompt de docs/PROMPT_GERAR_APOLICES.md para gerar novos lotes; o importador "
              "confere cada lote antes de incorporá-lo. Caminho pronto e testado; ainda não usado."]],
            [3.6, 3.6, 9.3]),
          P("Etapas", "h2"),
          *B(["<b>Enunciado e decisão de escopo:</b> construir o Projeto Final como módulo do "
              "AgroSentinela (Desafio 5), mantendo o foco em seguro e crédito rural e reaproveitando a "
              "base do Sicor/Proagro e o núcleo de agentes.",
              "<b>Premissas definidas pelo autor:</b> IA generativa via Groq no plano gratuito, como "
              "premissa; preferência por agentes automatizados; cuidado com modelos próximos de sair do "
              "plano gratuito (os Llama 3 usados antes passaram a Enterprise; adotou-se GPT-OSS).",
              "<b>Primeira versão:</b> aplicação, 45 apólices simuladas (15 tomadoras, 12 nomes de "
              "seguradora), relatório, deck e vídeo-base.",
              "<b>Revisão crítica do autor:</b> apólices reais de empresas diferentes não seguem o "
              "mesmo modelo de documento; a primeira versão só trocava nome e cor. Pedido: ao menos 5 "
              "seguradoras com ao menos 20 apólices cada, cenários rurais diversos (familiar, pequeno, "
              "grande, latifúndio) e coerentes com as realidades regionais.",
              "<b>Segunda versão:</b> pesquisa de condições gerais públicas de D&amp;O (AIG, Allianz, "
              "Tokio Marine, Sompo) como referência de estrutura, sem copiar texto; 6 seguradoras "
              "fictícias com arquiteturas de documento próprias; 120 apólices; 45 tomadoras em 25 UFs "
              "e DF; regras de coerência regional; troca de um nome que coincidia com uma seguradora "
              "real; extração e testes adaptados à heterogeneidade.",
              "<b>Teste com documentos reais:</b> um colega enviou 3 condições gerais de D&amp;O e 2 "
              "apólices de Seguro Garantia. O teste revelou que a IA só via o início de documentos "
              "longos e que um documento de outro ramo entraria como D&amp;O; ambos foram corrigidos "
              "(seção 9.1). Os arquivos reais ficaram fora do repositório.",
              "<b>Ampliação por outra IA:</b> prompt de geração e importador com validações (nomes "
              "reais proibidos, marca d'água, datas, valores, taxonomia).",
              "<b>Medição e publicação:</b> avaliação contra o gabarito por arquitetura, 204 testes "
              "automáticos, README, deck, vídeo, roteiro de narração e guia de publicação."]),
          P("Lição principal: a IA acelerou a construção, mas foi a revisão humana do realismo dos "
            "dados que mudou a qualidade do resultado. Toda apólice usada é simulada e declarada como "
            "tal.")]

    doc = SimpleDocTemplate(str(SAIDA), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=1.8 * cm, bottomMargin=1.8 * cm,
                            title="InsurMinds — Projeto Final — Relatório Técnico",
                            author="Jefferson Luiz Gonçalves Silva")
    doc.build(h, onFirstPage=rodape, onLaterPages=rodape)
    print("ok", SAIDA)


if __name__ == "__main__":
    main()
