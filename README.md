# 🌾 AgroSentinela · InsurMinds — Projeto Final

**Plataforma inteligente para análise e comparação de apólices D&O do agronegócio**
— integrada à ferramenta de comunicação proativa para crédito rural e Proagro
desenvolvida no Desafio 5.

> Entrega do **Projeto Final** do curso **InsurMinds — Inteligência Artificial
> Aplicada a Seguros** (I2A2), prazo 06/10/2026. O Projeto Final foi construído
> como **um módulo novo dentro da mesma aplicação do Desafio 5**: uma única
> ferramenta, um único núcleo de agentes, uma única base de dados do Sicor.

[![CI](https://github.com/jlgsilva/insurminds-projeto-final/actions/workflows/ci.yml/badge.svg)](https://github.com/jlgsilva/insurminds-projeto-final/actions/workflows/ci.yml)
[![Licença: MIT](https://img.shields.io/badge/licença-MIT-green.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-app-ff4b4b.svg)](https://streamlit.io/)
[![IA: Groq](https://img.shields.io/badge/IA-Groq%20GPT--OSS-orange.svg)](https://console.groq.com/docs/models)

---

## 1. Descrição do projeto

Apólices de D&O (*Directors & Officers*) são longas, jurídicas e diferentes
entre si justamente onde importa: custos de defesa dentro ou fora do limite,
retroatividade, adiantamento, multas, exclusões de dolo. Comparar cotações leva
horas de especialista.

No **agronegócio** a dor é maior: o administrador de uma cooperativa de crédito
rural, de uma usina ou de uma trading responde por riscos que o D&O "de
prateleira" não trata — processo sancionador do Banco Central por desvio de
crédito rural ou enquadramento indevido no Proagro, embargo ambiental na cadeia
de fornecedores, recuperação judicial de produtores.

A plataforma automatiza o ciclo completo exigido pelo enunciado:

| Etapa do enunciado | Como é feito | Agente |
|---|---|---|
| 1. Recebimento dos documentos | Upload de PDF, PDF digitalizado, fotos (várias páginas) ou TXT; validação e deduplicação por hash | `RecepcaoAgent` |
| 2. Extração automática do conteúdo | Camada de texto do PDF ou **OCR (Tesseract, português)** por página; remoção de cabeçalho/rodapé; segmentação em seções | `LeituraOCRAgent` |
| 3. Organização das informações | **LLM** estrutura o quadro-resumo e classifica **32 cláusulas** de uma taxonomia D&O + agro, com **evidência literal** | `CadastroAgent`, `ClausulasAgent` |
| 4. Armazenamento estruturado | Validação anti-alucinação e gravação em **SQLite** (documentos, apólices, cláusulas, seções, comparações, auditoria) | `ValidacaoAgent`, `ArmazenamentoAgent` |
| 5. Consulta das informações | Perguntas em linguagem natural com **tool calling** sobre a base | `ConsultaAgent` |
| 6. Comparação entre apólices | Escore ponderado por criticidade, ajustado ao **perfil de crédito rural da tomadora (Sicor/Proagro)**; lacunas e diferenças | `PerfilRiscoAgent`, `ComparadorAgent` |
| 7. Apresentação dos resultados | Relatório comparativo redigido por **LLM** para 5 públicos, com verificador de números | `RelatorAgent` |

### Acervo de demonstração: 120 apólices **simuladas**, 6 arquiteturas de documento

Apólices emitidas de D&O são contratos privados (não há base pública com
prêmio, limite e condições negociadas). Por isso o projeto inclui um
**simulador** (`src/agrosentinela/projeto_final/simulador.py` e
`modelos_documento.py`). Como no mercado real, **cada seguradora tem o seu
próprio modelo de documento** — não é um template com nomes trocados:

| Seguradora (fictícia) | Arquitetura do documento | Inspiração estrutural (C.G. públicas na SUSEP) |
|---|---|---|
| Atalaia Linhas Financeiras | numeração decimal, glossário, "Garantia A/B", extensões 4.x, exclusões 6.x, especificação em tabela | AIG |
| Ipê-Roxo Seguradora | dados em lista numerada, extensões e exclusões em romanos, exclusões em CAIXA ALTA, "POS", valores por extenso | Allianz |
| Jacarandá Cia. de Seguros | hierárquico 2.1.1, "LMI", prazo complementar/suplementar, **especificação no FIM**, datas 01.07.2026 | Tokio Marine (versões até 2021) |
| Xique-Xique Seguros Gerais | **dados em prosa** no preâmbulo, "Cláusula 1ª, 2ª…", cláusulas particulares rurais, "R$ 5 milhões" | Sompo |
| Mutirão Seguros Mútuos | **linguagem simples em perguntas e respostas**, foco em cooperativas, datas por extenso | guias de seguro cooperativo |
| Minuano Specialty | **Policy Schedule bilíngue** (Item 1…9), "Side A/B/C", endossos, "BRL 5,000,000.00" | mercado de Londres |

As inspirações referem-se à *organização* dos documentos; nenhum texto foi
copiado. Cada seguradora emite **20 apólices** para **45 tomadoras** em **25
UFs e no DF**, nas cinco regiões, em nove perfis — associações extrativistas
e cooperativas de agricultura familiar (Pronaf), pequenas agroindústrias,
médios produtores (Pronamp), grandes grupos, latifúndios de pecuária e grãos,
cooperativas de crédito rural, cooperativas agroindustriais, agroindústrias e
a cadeia (trading, insumos, securitizadora de CPR). O território muda o
risco: Amazônia Legal (embargos, CAR, Moratória da Soja), semiárido
(estiagem, Garantia-Safra), Matopiba (fronteira agrícola), Pantanal
(queimadas), Sul (integração, enchentes de 2024).

- **Formatos**: 104 PDFs com texto, 12 **digitalizados** (sem camada de
  texto) e 4 **fotografados** (JPG por página) — exercitam o OCR.
- **Gabarito** (`gabarito.json`): a verdade de cada apólice, para **medir a
  acurácia da extração** (LLM × linha de base), por seguradora/arquitetura.
- **Mais apólices**: [`docs/PROMPT_GERAR_APOLICES.md`](docs/PROMPT_GERAR_APOLICES.md)
  traz um prompt pronto para outra IA gerar novos lotes com as mesmas regras,
  e `scripts/importar_apolices_externas.py` valida e incorpora o lote.

> ⚠️ **Todos os documentos do acervo são simulados**: marca d'água "SIMULADA · USO
> ACADÊMICO", rodapé e aviso no quadro-resumo. Seguradoras, tomadoras, CNPJs e
> valores são fictícios. A estrutura e o vocabulário seguem o padrão de
> mercado do D&O no Brasil e a Circular SUSEP nº 637/2021. A aplicação aceita
> também qualquer PDF/imagem de apólice real enviada pelo usuário.

### Como o projeto foi construído

Com três IAs, em papéis distintos, e decisões do autor:

| Quem | Papel |
|---|---|
| Autor | Definiu escopo e premissas (módulo do Desafio 5, IA via Groq gratuita, agentes, foco rural), revisou cada entrega e pediu a reconstrução do acervo quando percebeu que a 1ª versão (45 apólices) usava um único modelo de documento |
| Claude (Anthropic) | Assistente de desenvolvimento: pesquisa de referências públicas, código, testes, documentação e a primeira versão de deck, vídeo-base e relatório |
| Groq (GPT-OSS) | IA dentro do app: cadastro, cláusulas, relatório e consulta |
| Outra IA, à escolha | Gera novos lotes de apólices a partir de [`docs/PROMPT_GERAR_APOLICES.md`](docs/PROMPT_GERAR_APOLICES.md); o importador confere antes de incorporar (caminho pronto, ainda não usado) |

Detalhes no apêndice do relatório técnico e na apresentação (slides 4 a 10).

### Validação com documentos reais

Na reta final, um colega enviou **5 documentos reais**: as condições gerais
de D&O da **AXA** (104 páginas), da **Allianz** (75) e da **Porto** (52) — textos
públicos registrados na SUSEP — e **2 apólices emitidas de Seguro Garantia**,
com dados de terceiros. Os PDFs **não estão no repositório**
([`data/apolices_reais/LEIA-ME.md`](data/apolices_reais/LEIA-ME.md)); só o
gabarito (32 cláusulas por condição geral, com evidência curta conferida por
script) e os resultados agregados.

O teste revelou falhas que o acervo simulado escondia, e todas foram corrigidas:

| O que o teste revelou | O que mudou | Antes → depois |
|---|---|---|
| A IA recebia só os primeiros 14 mil caracteres: ~6% de uma condição geral | Seleção de trechos por cláusula (título, vocabulário, glossário/exclusões) em 2 lotes, dentro da cota gratuita | trechos-chave que chegam à IA: 5% → 56% |
| Seguro Garantia entraria como "apólice D&O" cheia de lacunas | Identificação de **ramo** e **tipo** (condições gerais × apólice); fora do escopo é recusado | recusados: 0 de 2 → 2 de 2 |
| Sumário e glossário viravam "cláusulas" | Sumário removido; cada seção sabe se está no glossário, nas exclusões ou no texto geral | presença por regras: 63,6% → 83,3% |
| Seguradora não identificada (sem quadro-resumo) | Nome lido no cabeçalho/rodapé | 3 de 3 |

Por documento (regras, sem IA): Axa 75.0% de presença, 43.8% de nível; Allianz 93.8% de presença, 34.4% de nível; Porto 81.2% de presença, 40.6% de nível.
O acervo simulado também melhorou (presença 86,3% → 88,3%; nível 68,8% →
69,3%). **Cuidados:** o vocabulário foi ampliado olhando esses mesmos
documentos (resultado dentro da amostra), o gabarito real foi anotado com apoio
de IA e precisa de revisão de especialista, e o nível exato por regras segue
baixo — é a parte que depende da IA. Com a chave da Groq:
`python scripts/avaliar_documentos_reais.py --llm`.

---

## 2. Arquitetura

```
                 ┌──────────────────────── INGESTÃO ────────────────────────┐
 PDF / scan /    │ RecepcaoAgent → LeituraOCRAgent → CadastroAgent (LLM 20B) │
 fotos / TXT ───▶│   → ClausulasAgent (LLM 120B) → ValidacaoAgent            │──▶ SQLite
                 │   → ArmazenamentoAgent                                    │
                 └───────────────────────────────────────────────────────────┘
                                                                                   │
 Sicor / Proagro ┌────────────────────── COMPARAÇÃO ─────────────────────────┐    │
 (Desafio 5) ───▶│ PerfilRiscoAgent → ComparadorAgent (regras) → RelatorAgent│◀───┤
                 │                                              (LLM 120B)   │    │
                 └───────────────────────────────────────────────────────────┘    │
                 ┌─────────────────────── CONSULTA ──────────────────────────┐    │
 pergunta ──────▶│ ConsultaAgent (LLM 120B + 6 ferramentas sobre a base)     │◀───┘
                 └───────────────────────────────────────────────────────────┘
```

**Princípio central — "o modelo lê e redige; as regras decidem".** O LLM faz o
que só ele faz bem (entender cláusulas escritas de formas diferentes e redigir
explicações). Escores, lacunas e números finais vêm de código determinístico e
auditável. Guarda-corpos:

1. **Saída estruturada** (JSON) com vocabulário fechado de níveis.
2. **Evidência obrigatória**: cada classificação cita seção e trecho literal;
   o `ValidacaoAgent` procura o trecho no documento (busca aproximada,
   tolerante a OCR) e marca o que não encontra.
3. **Verificação cruzada de números**: LMG, prêmio e franquia lidos pelo LLM
   são conferidos com a leitura por expressão regular do quadro-resumo.
4. **Verificador de números do relatório**: todo número citado pelo relator
   precisa existir no bloco de fatos; o que não existe é sinalizado.
5. **Contingência**: sem chave/cota, cada agente de IA tem um caminho
   determinístico — a aplicação nunca fica sem resultado.

Detalhes: [`docs/projeto_final.md`](docs/projeto_final.md).

---

## 3. Tecnologias utilizadas

| Camada | Tecnologia |
|---|---|
| Linguagem | Python 3.11+ |
| Interface | Streamlit (multipágina) |
| IA Generativa | **GroqCloud** — `openai/gpt-oss-120b` (cláusulas, relatório, consulta) e `openai/gpt-oss-20b` (cadastro), API compatível com OpenAI via HTTP, *JSON mode*, *tool calling*, `reasoning_effort` |
| OCR | Tesseract 5 (`por`) via `pytesseract`; `pypdfium2` para rasterizar |
| PDF | `pdfplumber` (leitura), `reportlab` (geração do acervo simulado) |
| Banco de dados | SQLite |
| Dados | pandas; microdados do **Sicor/Proagro (BCB)** da base do Desafio 5 |
| Agentes | Classe-base própria `Agente` (rastro, métricas, isolamento de falha) — mesma do Desafio 5 |
| Testes | pytest (CI no GitHub Actions, Linux e Windows) |

**Por que GPT-OSS e não Llama?** Em outubro/2026 os modelos Llama 3.x da Groq
passaram a ser oferecidos só no plano *Enterprise*. A família GPT-OSS está em
**produção** (sem risco de descontinuação súbita, ao contrário dos modelos
*preview*) e disponível no plano gratuito/desenvolvedor. Os modelos podem ser
trocados por variável de ambiente.

---

## 4. Instalação

Pré-requisitos: **Python 3.11+**, **Git** e (para OCR) o **Tesseract**.

```bash
git clone https://github.com/jlgsilva/insurminds-projeto-final.git
cd insurminds-projeto-final
python -m venv .venv
# Windows: .venv\Scripts\activate     Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

**Tesseract (OCR)** — necessário apenas para apólices digitalizadas/fotos
enviadas por você (o acervo já vem pré-processado):

- Windows: instalador em <https://github.com/UB-Mannheim/tesseract/wiki> (marque
  "Portuguese"); o modelo `por` também está em `data/tessdata/`.
- Linux: `sudo apt install tesseract-ocr tesseract-ocr-por`
- macOS: `brew install tesseract tesseract-lang`

**Chave da Groq** (gratuita em <https://console.groq.com/keys>):

```bash
cp .env.example .env        # Windows: copy .env.example .env
# edite .env e preencha GROQ_API_KEY=gsk_...
```

---

## 5. Execução

```bash
streamlit run app.py
```

Abra <http://localhost:8501> e use as páginas do Projeto Final:

1. **📄 Ingestão de Apólices** — escolha arquivos do acervo (ou envie os seus) e
   clique em *Executar pipeline de ingestão*. Veja cada agente executando, o
   cadastro extraído, as 32 cláusulas com evidência, os alertas de validação e
   a conferência com o gabarito.
2. **⚖️ Comparador de Apólices** — escolha uma tomadora (a sugerida é a *Grão
   Norte Trading*, de Sorriso-MT, com 4 cotações de seguradoras com modelos de
   documento diferentes), o público do relatório e clique em *Comparar*.
3. **💬 Consulta às Apólices** — pergunte em português.

Atalhos (`make` ou comandos equivalentes):

```bash
make apolices    # regenera as 120 apólices simuladas
make acervo      # processa o acervo sem IA → base_inicial.sqlite
make acervo-ia   # processa o acervo COM IA (Groq) e mede a acurácia
make teste       # roda os testes
```

Medir a acurácia da extração por IA em todo o acervo (usa cache; respeita a
cota gratuita com pausa entre documentos):

```bash
python scripts/processar_acervo.py --llm --pausa 20
```

As páginas do **Desafio 5** (alertas climáticos para crédito rural) continuam
disponíveis no mesmo app — documentação em
[`docs/README_Desafio5.md`](docs/README_Desafio5.md).

---

## 6. Publicação no Streamlit Community Cloud

1. Em <https://share.streamlit.io> → **Create app** → repositório
   `jlgsilva/insurminds-projeto-final`, branch `main`, arquivo `app.py`.
2. **Advanced settings → Secrets**:
   ```toml
   GROQ_API_KEY = "gsk_..."
   GROQ_MODEL_REDACAO = "openai/gpt-oss-120b"
   GROQ_MODEL_RAPIDO = "openai/gpt-oss-20b"
   GROQ_MODEL_COPILOTO = "openai/gpt-oss-120b"
   GROQ_MODEL_EXTRACAO = "openai/gpt-oss-120b"
   LLM_REASONING_EFFORT = "low"
   ```
3. O `packages.txt` instala o Tesseract automaticamente.

---

## 7. Estrutura do repositório

```
app.py                              página inicial (Desafio 5 + Projeto Final)
pages/11_📄_Ingestão_de_Apólices.py  Projeto Final — ingestão, extração, qualidade
pages/12_⚖️_Comparador_de_Apólices.py Projeto Final — comparação e relatório
pages/13_💬_Consulta_às_Apólices.py  Projeto Final — consulta em linguagem natural
src/agrosentinela/projeto_final/
    agentes.py        agentes e orquestrador do Projeto Final
    documentos.py     recepção, leitura de PDF, OCR, sumário, segmentação (glossário/exclusões)
    tipo_documento.py ramo (D&O, Seguro Garantia…) e tipo (condições gerais × apólice)
    extracao.py       extração LLM (prompts, trechos por cláusula) + linha de base
    validacao.py      anti-alucinação, verificação cruzada, confiança
    repositorio.py    SQLite
    clausulas.py      taxonomia de 32 cláusulas (D&O + agro)
    comparador.py     escores, lacunas, diferenças
    perfil_risco.py   perfil da tomadora a partir do Sicor/Proagro
    relator.py        relatório por IA + verificador de números
    consulta.py       agente com tool calling
    avaliacao.py      acurácia contra o gabarito
    simulador.py      seguradoras, tomadoras e gabarito do acervo simulado
    modelos_documento.py  as 6 arquiteturas de documento (uma por seguradora)
data/apolices_simuladas/            120 apólices, gabarito, base inicial
data/apolices_reais/                gabarito dos 5 documentos reais (PDFs fora do Git)
scripts/gerar_apolices_simuladas.py  scripts/processar_acervo.py
scripts/importar_apolices_externas.py  docs/PROMPT_GERAR_APOLICES.md
scripts/avaliar_documentos_reais.py  validação nos documentos reais
Projeto_Final_Artefatos/            pitch deck, vídeo, relatório técnico, e-mail
src/agrosentinela/ (demais)         núcleo do Desafio 5 (clima, regras, Sicor)
tests/                              204 testes (inclui o Projeto Final e os documentos reais)
```

---

## 8. Integrantes

| Nome | Papel | Contato |
|---|---|---|
| Jefferson Luiz Gonçalves Silva | Representante — desenvolvimento, IA e dados | [@jlgsilva](https://github.com/jlgsilva) |

---

## 9. Limitações conhecidas

- Acervo **simulado**: seis arquiteturas de documento já mostram que a leitura
  por regras não generaliza (cai muito na apólice em linguagem simples), mas
  apólices reais têm ainda mais variedade — a acurácia medida aqui é um
  indicativo, não uma garantia.
- Validação real ainda pequena: 3 condições gerais de D&O (dentro da amostra)
  e nenhuma apólice D&O emitida real; gabarito real anotado com apoio de IA,
  a revisar por especialista.
- OCR de documentos de baixa qualidade reduz a confiança (o sistema avisa).
- Plano gratuito da Groq tem limite de tokens por minuto: a extração por IA é
  feita documento a documento, com *retry* e cache; em documentos longos, a IA
  recebe trechos selecionados, não o texto inteiro.
- Sistema de **apoio à decisão** — não substitui parecer jurídico.

---

## 10. Licença

Este projeto está licenciado sob a **Licença MIT** — veja [LICENSE](LICENSE).
Dados do Sicor/Proagro: domínio público (Banco Central do Brasil).
