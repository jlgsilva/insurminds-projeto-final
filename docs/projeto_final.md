# Projeto Final — arquitetura, decisões e limitações

Plataforma inteligente para análise e comparação de apólices D&O, construída
como módulo do AgroSentinela (Desafio 5). Este documento complementa o
README e é a base do relatório técnico em PDF.

## 1. Fluxo completo de processamento

```
① RecepcaoAgent      agrupa páginas (X_p1.jpg, X_p2.jpg → X), valida tipo/tamanho,
                     calcula SHA-256 e ignora documento já processado
② LeituraOCRAgent    por página: camada de texto (pdfplumber) ou, se < 60
                     caracteres, rasteriza (pypdfium2, 200 dpi) e aplica OCR
                     (Tesseract 'por', psm 6, uma passada com confiança);
                     remove cabeçalho/rodapé repetidos; segmenta em seções
                     (CLÁUSULA n – / n. TÍTULO / Art. nº –)
③ CadastroAgent      LLM gpt-oss-20b lê o quadro-resumo → JSON (seguradora,
                     tomadora, UF, vigência, retroatividade, LMG, prêmio,
                     franquia); regex lê o mesmo quadro em paralelo
④ ClausulasAgent     LLM gpt-oss-120b recebe as seções numeradas [S1..Sn] e a
                     taxonomia (32 cláusulas, pergunta-guia de cada uma) →
                     JSON com nível + seção + evidência literal + justificativa
⑤ ValidacaoAgent     esquema; evidência existe na seção? (busca aproximada);
                     números LLM × regex; coerência de datas e taxa de prêmio;
                     confiança 0–100; acurácia contra o gabarito (acervo)
⑥ ArmazenamentoAgent SQLite: documentos, apolices, clausulas, secoes,
                     comparacoes, auditoria

⑦ PerfilRiscoAgent   indicadores do Sicor/Proagro na UF da tomadora (crédito
                     rural, % sem cobertura, acionamento do Proagro × Brasil,
                     % em atraso) + segmento → fatores de peso com motivo
⑧ ComparadorAgent    escore ponderado (geral e só críticas), escore por grupo,
                     prêmio por ponto, lacunas com melhor alternativa,
                     diferenças relevantes, alerta de "leitura divergente"
⑨ RelatorAgent       LLM gpt-oss-120b redige para o público escolhido a partir
                     de um bloco de fatos fechado; verificador de números

⊕ ConsultaAgent      LLM + 6 ferramentas: listar_apolices, apolices_por_clausula,
                     detalhar_apolice, buscar_texto, ranking_seguradoras, taxonomia
```

## 2. Taxonomia de cláusulas

32 cláusulas em 7 grupos (escopo, limites, defesa, vigência, exclusões,
operação do contrato e **riscos do agronegócio**), cada uma com peso 1–5,
marcação de criticidade (15 críticas), "por que importa", pergunta-guia,
sinal de alerta e base legal. Níveis: ampla (1,0), padrão (0,7), restrita
(0,4), ausente (0) e excluída (0). "Ausente" ≠ "restrita": silêncio
contratual tende a ser resolvido contra o segurado.

Grupo agro (novo no Projeto Final):

| Código | Cláusula | Por que |
|---|---|---|
| AGR-01 | Atos de gestão em crédito rural e Proagro | processo sancionador do BCB (MCR, Sicor, Proagro, Lei 13.506/2017) |
| AGR-02 | Responsabilidade ambiental do administrador rural | Código Florestal, embargos, CAR, cadeia de fornecedores |
| AGR-03 | Recuperação judicial e insolvência no agro | Lei 11.101/2005 alterada pela Lei 14.112/2020 |

## 3. Decisões arquiteturais (e por quê)

| Decisão | Alternativa descartada | Justificativa |
|---|---|---|
| LLM classifica, código pontua | LLM dar nota/ranking direto | número que ninguém refaz não sustenta decisão de cobertura |
| Taxonomia fixa | comparação livre texto × texto | permite medir, comparar N apólices e auditar |
| Evidência literal obrigatória | confiar no rótulo do modelo | permite detectar alucinação automaticamente |
| Dois modelos (20B cadastro, 120B cláusulas) | um modelo para tudo | tarefa simples em modelo rápido economiza cota |
| `reasoning_effort=low` | padrão (medium) | extração guiada por esquema não precisa de raciocínio longo; poupa TPM |
| OCR por página | OCR do documento inteiro | apólices reais misturam páginas nativas e anexos escaneados |
| Linha de base determinística | só LLM | contingência sem cota + régua para medir o ganho da IA |
| SQLite | Postgres/NoSQL | zero infraestrutura; esquema migra sem mudança |
| Classe `Agente` própria | LangGraph/CrewAI | mesma do Desafio 5, explícita e auditável; contrato compatível com grafo |
| Perfil de risco via Sicor | pesos fixos | o que importa depende de quem é a tomadora |
| Acervo simulado com gabarito | apólices reais | apólices emitidas não são públicas; gabarito permite medir acurácia |

## 4. Uso de IA (onde, como, com que controle)

| Agente | Modelo | Entrada | Saída | Controle |
|---|---|---|---|---|
| CadastroAgent | gpt-oss-20b, T=0, JSON | quadro-resumo (≤3,5 mil car.) | 14 campos | regex cruzada; regex prevalece em divergência |
| ClausulasAgent | gpt-oss-120b, T=0, JSON | seções [S1..Sn] + taxonomia | 32 × (nível, seção, evidência) | vocabulário fechado; evidência verificada |
| RelatorAgent | gpt-oss-120b, T=0,3 | bloco de fatos (JSON) | Markdown | verificador de números; aviso obrigatório |
| ConsultaAgent | gpt-oss-120b, tools | pergunta + histórico | resposta + tabelas | só dados das ferramentas; máx. 5 iterações |

Infraestrutura LLM (herdada do Desafio 5): HTTP direto na API compatível com
OpenAI, cache em disco por hash do payload, orçamento de chamadas por
execução, respeito a `Retry-After` em 429, *backoff* exponencial e telemetria
(tokens, latência, cache) por tarefa.

## 5. Avaliação

`scripts/processar_acervo.py` processa as 120 apólices e compara com o gabarito (resultado por seguradora/arquitetura no relatório técnico):

- **Linha de base determinística** (dicionário de títulos + gatilhos):
  campos 99,7% · nível de cláusula ≈80% · presença/ausência ≈97,6%.
- **Extração por IA**: rode `python scripts/processar_acervo.py --llm --pausa 20`
  (gera `data/apolices_simuladas/avaliacao_llm.csv`). A página de ingestão
  mostra a comparação lado a lado e a matriz de confusão dos níveis.

## 5b. O acervo simulado

Seis seguradoras fictícias, cada uma com **arquitetura de documento própria**
(inspirada na organização de condições gerais públicas de D&O — AIG, Allianz,
Tokio Marine, Sompo —, num modelo de linguagem simples para cooperativas e num
*Policy Schedule* bilíngue do mercado de Londres), 20 apólices cada, para 45
tomadoras em 25 UFs e no DF, de associações de agricultura familiar a
latifúndios. Regras de coerência ligam perfil e território às cláusulas
(ex.: familiar sem Side C e com cobertura só no Brasil; Amazônia Legal com
exclusão ambiental mais frequente nas generalistas; quem opera crédito rural
com AGR-01 presente ou expressamente excluída).

## 5c. Validação com documentos reais

Cinco documentos reais enviados por um colega (3 condições gerais de D&O —
AXA, Allianz, Porto — e 2 apólices de Seguro Garantia) mostraram falhas que o
acervo simulado escondia: a IA via só ~6% de um documento longo; um documento
de outro ramo entraria como D&O; sumário e glossário confundiam a leitura. As
correções — identificação de ramo/tipo (`tipo_documento.py`), remoção do
sumário, partes do documento (glossário/exclusões) e seleção de trechos por
cláusula em dois lotes para o LLM — e os números antes/depois estão no README
e na seção 9.1 do relatório técnico. Os PDFs ficam fora do repositório
(`data/apolices_reais/LEIA-ME.md`).

## 6. Limitações conhecidas

- Acervo simulado: 6 arquiteturas de documento e dialetos diferentes, mas o
  conteúdo de cada cláusula parte de uma redação-base comum; apólices reais
  variam mais. Novos lotes podem ser gerados com `docs/PROMPT_GERAR_APOLICES.md`.
- Segmentação depende de títulos numerados; apólices sem títulos caem numa
  seção única (o LLM ainda classifica, mas com evidência menos precisa).
- OCR de baixa qualidade (foto torta, carimbo) reduz a confiança.
- Plano gratuito da Groq: limite de tokens por minuto; documentos longos
  (> 14 mil caracteres de condições) são truncados no prompt.
- Comparação é apoio à decisão; não é parecer jurídico.

## 7. Evolução futura

- RAG sobre as Condições Gerais registradas na SUSEP de cada produto.
- Extração em duas passadas (localizar → classificar) para documentos longos.
- LLM multimodal para tabelas e assinaturas em apólices digitalizadas.
- Integração com o Desafio 5: alerta climático → revisão automática das
  coberturas D&O de cooperativas expostas.
- Endossos e renovações: comparação temporal da mesma apólice.
- Avaliação humana (corretores) para calibrar pesos e níveis.

## 8. Fontes e referências

- Enunciado InsurMinds/I2A2 — Desafios 3, 4, 5 e Projeto Final.
- Circular SUSEP nº 637/2021 (seguros de responsabilidade civil; revogou a
  Circular 553/2017; unificou prazo complementar/suplementar em "prazo adicional").
- Banco Central do Brasil — Tabelas e Microdados do Crédito Rural e do Proagro
  (Sicor): <https://www.bcb.gov.br/estabilidadefinanceira/tabelas-credito-rural-proagro>.
- Lei 6.404/1976; Lei 13.709/2018 (LGPD); Lei 9.605/1998; Lei 12.651/2012;
  Lei 11.101/2005 e Lei 14.112/2020; Lei 13.506/2017.
- GroqCloud — modelos suportados e parâmetros de raciocínio:
  <https://console.groq.com/docs/models>, <https://console.groq.com/docs/reasoning>.
