# 🌾 AgroSentinela

**Inteligência climática e comunicação proativa para crédito rural e Proagro**

> Entrega do **Desafio 5 — Comunicação Inteligente** do curso
> **InsurMinds — Inteligência Artificial Aplicada a Seguros** (I2A2).
> Construído sobre as *Tabelas e Microdados do Crédito Rural e do Proagro*
> publicadas pelo **Banco Central do Brasil** (Sicor).

[![CI](https://github.com/jlgsilva/ai_to_so_desafio5_agrosentinela/actions/workflows/ci.yml/badge.svg)](https://github.com/jlgsilva/ai_to_so_desafio5_agrosentinela/actions/workflows/ci.yml)
[![Licença: MIT](https://img.shields.io/badge/licença-MIT-green.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-app-ff4b4b.svg)](https://streamlit.io/)

---

## O problema

A relação entre seguradora, banco e produtor rural quase sempre começa
**depois** do sinistro. A chuva já caiu, a geada já queimou o cafezal, a seca
já comprometeu o enchimento de grãos. A partir daí, só resta administrar a
perda: perícia, comprovação, indenização, renegociação.

## A virada

O Banco Central publica, em dados abertos, **todas as operações de crédito
rural contratadas no país** — município, cultura, área, valor, janela de
plantio e de colheita, cobertura do Proagro, irrigação — e o histórico
completo de acionamento do Proagro desde 1983.

Cruzando isso com previsão meteorológica pública é possível responder,
**antes** do evento:

> *Quem* está exposto a *qual* fenômeno, em *qual* fase da lavoura, com
> *quanto* de dinheiro em risco e *com ou sem* cobertura?

O AgroSentinela faz esse cruzamento e transforma o resultado em comunicação
personalizada para **dezesseis perfis** da cadeia do agronegócio, organizados
em cinco setores.

### O que muda na prática

| Alerta genérico | Alerta do AgroSentinela |
|---|---|
| "Risco de geada no Sul nos próximos dias." | "Sua lavoura de café em Patrocínio-MG, 42 ha, está em brotação — fase que define a safra seguinte. Mínima prevista de 1,2 °C na madrugada de quinta. Sua operação consta com Proagro; registre a ocorrência com data e fotos. Regra R-GEA-02." |

---

## Sumário

- [Arquitetura](#arquitetura)
- [Personas atendidas](#personas-atendidas)
- [O que a aplicação oferece](#o-que-a-aplicação-oferece)
- [Instalação](#instalação)
- [Execução](#execução)
- [Rodando no Windows](#rodando-no-windows)
- [Carregando os dados oficiais do BCB](#carregando-os-dados-oficiais-do-bcb)
- [Publicação no Streamlit Cloud](#publicação-no-streamlit-community-cloud)
- [Uso de IA generativa](#uso-de-ia-generativa)
- [Regras de negócio](#regras-de-negócio)
- [Fontes de dados](#fontes-de-dados)
- [Interface responsiva e filtros](#interface-responsiva-e-com-filtros-que-vieram-dos-dados)
- [Preparado para o Projeto Final](#preparado-para-o-projeto-final-comparação-de-apólices-de-do)
- [Testes](#testes)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Privacidade e limitações](#privacidade-e-limitações)
- [Licença](#licença)

---

## Arquitetura

Seis agentes especializados, encadeados por um orquestrador. Cada um tem
**responsabilidade única**, contrato explícito e rastro próprio de execução.

```
          ┌────────────────┐   ┌──────────────┐   ┌───────────────┐
          │ ① CarteiraAgent│──▶│ ② ClimaAgent │──▶│ ③ EventoAgent │
          └────────────────┘   └──────────────┘   └───────────────┘
            Sicor: operações     Open-Meteo:        limiares →
            vigentes + fase      séries diárias     eventos do
            fenológica           + indicadores      território
                                                           │
    ┌────────────────────┐   ┌────────────────┐   ┌────────▼────────┐
    │ ⑥ DespachanteAgent │◀──│ ⑤ RedatorAgent │◀──│ ④ RegrasAgent   │
    └────────────────────┘   └────────────────┘   └─────────────────┘
      anti-fadiga +            IA Generativa        rules.yaml →
      simulação de envio       por persona/canal    alertas + score
      → SQLite                 (+ revisão)          + justificativa

    ⊕ CopilotoAgent — consulta em linguagem natural com function calling
```

### Mapeamento com o enunciado

| Etapa exigida pelo Desafio 5 | Implementação | Onde ver na aplicação |
|---|---|---|
| 1. Coleta em fonte externa de dados meteorológicos | `ClimaAgent` + `weather/open_meteo.py` | Radar Climático |
| 2. Identificação de eventos relevantes | `EventoAgent` (escadas de limiares) | Radar Climático / Mapa |
| 3. Aplicação de regras de negócio | `RegrasAgent` + `rules/rules.yaml` | Motor de Regras |
| 4. Geração automática das mensagens | `RedatorAgent` + `llm/prompts.py` | Central de Comunicação |
| 5. Simulação do envio | `DespachanteAgent` + `outbox/store.py` | Central de Comunicação |
| Demonstração do fluxo completo | `Orquestrador` + rastro cronometrado | Início |

Por que **não** usar um framework de agentes: para um pipeline determinístico
de seis etapas, o encadeamento explícito é mais auditável, tem menos
dependências (o que importa na camada gratuita do Streamlit Cloud) e deixa a
arquitetura visível. O contrato de `Agente.executar` recebe e devolve o mesmo
objeto `Contexto` — portar para LangGraph seria uma troca mecânica.

---

## Personas atendidas

O enunciado pede "mensagens personalizadas para diferentes perfis de
segurados". A solução modela **toda a cadeia** que decide sobre risco
agrícola — e vai além do segurado, porque o alerta só vira ação quando chega
a quem pode agir.

São **16 personas em 5 setores**. Dois públicos
merecem destaque por terem sido incluídos deliberadamente:

- **Profissionais autônomos e MEIs** — extensionistas rurais e assessores que
  atendem dezenas de produtores. Não têm carteira própria, mas são quem vai a
  campo; para eles, uma lista de visitas priorizada por risco vale mais do que
  qualquer painel.
- **O setor de seguros por inteiro** — não só subscrição, mas perícia e
  regulação de sinistro, atuária, área comercial e corretagem. Cada papel lê o
  mesmo dado procurando coisa diferente: o perito quer a evidência documental;
  o atuário, a sinistralidade comparada ao mercado; o comercial, o município
  descoberto.

**Produção rural**

| # | Persona | Papel na cadeia | Canal | O que a mensagem precisa habilitar |
|---|---|---|---|---|
| 1 | Produtor Rural Familiar (Pronaf) | Segurado / mutuário | whatsapp | Tomar uma ação prática de campo nas próximas 72 horas e saber que existe cobertura do Proagro caso haja perda. |
| 2 | Produtor Empresarial / Médio (Pronamp e demais) | Segurado / mutuário | email | Priorizar manejo/colheita, acionar assistência técnica e avaliar antecipação de comunicação de sinistro. |
| 3 | Cooperativa Agropecuária | Intermediário / agente de campo | email | Mobilizar o corpo técnico, priorizar visitas e comunicar cooperados por microrregião. |

**Setor de seguros**

| # | Persona | Papel na cadeia | Canal | O que a mensagem precisa habilitar |
|---|---|---|---|---|
| 4 | Analista de Risco / Subscrição (Seguradora e Proagro) | Garantidor do risco | painel | Estimar sinistralidade incremental, reservar capacidade de perícia e revisar apetite por município/cultura. |
| 5 | Perito / Regulador de Sinistros (Proagro e seguro rural) | Regulação de sinistro | painel | Antecipar o volume e a localização das perícias, montar rota de campo e chegar com a evidência climática já reunida. |
| 6 | Atuário / Precificação de Seguro Rural | Precificação e resseguro | painel | Revisar taxa por município e cultura, dimensionar provisão e avaliar acionamento do contrato de resseguro. |
| 7 | Comercial / Produto de Seguro Rural (Seguradora) | Distribuição e produto | painel | Priorizar praças e culturas para expansão e ajustar o desenho do produto ao risco real da região. |
| 8 | Corretor de Seguros / Sindicato / Associação | Relacionamento e distribuição | email | Contatar produtores expostos, orientar sobre cobertura e registrar o atendimento. |

**Crédito e política pública**

| # | Persona | Papel na cadeia | Canal | O que a mensagem precisa habilitar |
|---|---|---|---|---|
| 9 | Gerente / Analista de Crédito Rural (Banco) | Credor / instituição financeira | painel | Dimensionar exposição em risco, priorizar contatos e preparar prorrogação/renegociação e provisionamento. |
| 10 | Gestor de Política Agrícola / Órgão Regulador | Política pública e supervisão | painel | Identificar municípios críticos, antecipar demanda por cobertura e subsidiar medidas de política agrícola. |

**Assistência técnica e consultoria**

| # | Persona | Papel na cadeia | Canal | O que a mensagem precisa habilitar |
|---|---|---|---|---|
| 11 | Assistência Técnica e Extensão Rural (ATER / agrônomo) | Mitigação de risco em campo | whatsapp | Emitir recomendação de manejo por cultura/fase e organizar roteiro de visitas. |
| 12 | Extensionista Rural Autônomo (MEI) | Assistência técnica independente | whatsapp | Montar o roteiro de visitas da semana e saber que recomendação levar para cada propriedade. |
| 13 | Assessor Rural / Consultor Independente | Consultoria e gestão de risco | painel | Produzir recomendação fundamentada de manejo de risco e de cobertura para a carteira de clientes assessorados. |

**Cadeia produtiva e mercado**

| # | Persona | Papel na cadeia | Canal | O que a mensagem precisa habilitar |
|---|---|---|---|---|
| 14 | Revenda de Insumos / Agroindústria | Fornecimento e crédito comercial | email | Ajustar concessão de prazo, antecipar renegociação e planejar estoque de insumos de emergência. |
| 15 | Trading / Originação e Armazenagem | Originação e logística | painel | Rever estimativa de originação por região e preparar capacidade de secagem e armazenagem. |
| 16 | Pesquisa, Ensino e Análise de Mercado | Conhecimento e transparência | painel | Produzir análise fundamentada sobre exposição climática do crédito rural, com dado rastreável até a fonte oficial. |

A persona **não é escolhida à mão**: é inferida dos campos reais da operação
no Sicor (`CategoriaEmitente` → cooperativa; `Programa` → Pronaf/Pronamp;
porte por `VL_PARC_CREDITO` e `VL_AREA_FINANC`).

---

## O que a aplicação oferece

| Página | Conteúdo |
|---|---|
| **Início** | Execução do pipeline com rastro cronometrado de cada agente |
| **Painel Executivo** | KPIs da carteira, alertas por severidade/evento/UF, municípios prioritários |
| **Mapa de Risco** | Seis mapas: alertas, carteira, **glebas (talhões)**, indicadores climáticos, histórico do Proagro e **exposição financeira** |
| **Radar Climático** | Série diária por município, eventos identificados e todos os indicadores |
| **Motor de Regras** | Catálogo navegável, **simulador interativo** e auditoria dos disparos |
| **Central de Comunicação** | Mensagens geradas, simulação de envio, personas e caixa de saída |
| **Copiloto IA** | Perguntas em português com *function calling* sobre os dados reais |
| **Microdados Sicor** | Explorador das tabelas curadas + catálogo completo dos arquivos do BCB |
| **Proagro & Sinistralidade** | Série histórica de COP/RCP, perfil de risco por município |
| **Documentação** | Arquitetura, modelo integrado de dados, catálogo de filtros, uso de IA, governança e reprodutibilidade |
| **Dados Externos** | As 16 fontes gratuitas e públicas, seu estado ao vivo, as janelas Zarc e o contexto externo no mapa |
| **Projeto Final — D&O** | Prévia do comparador de apólices, reaproveitando o mesmo núcleo |

---

## Instalação

Requisitos: **Python 3.11 ou superior**. Funciona em **Windows, macOS e
Linux** — a seção [Rodando no Windows](#rodando-no-windows) traz as
diferenças, que são poucas.

```bash
git clone https://github.com/jlgsilva/ai_to_so_desafio5_agrosentinela.git
cd ai_to_so_desafio5_agrosentinela

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

Opcional — ativar a IA generativa (gratuito):

```bash
cp .env.example .env
# edite .env e informe GROQ_API_KEY, obtida em https://console.groq.com/keys
```

---

## Execução

```bash
streamlit run app.py
```

Abra <http://localhost:8501>, ajuste os parâmetros na barra lateral e clique
em **▶️ Executar pipeline**.

> **Funciona sem nenhuma configuração.** Sem chave de API e sem internet, o
> sistema usa a amostra de demonstração, o gerador climático determinístico e
> o redator por templates — e **avisa explicitamente** que está fazendo isso.

### Linha de comando

```bash
# pipeline completo, exportando alertas, mensagens e envios
python -m agrosentinela.orchestrator --exportar saida/

# forçar um cenário climático para demonstrar uma regra específica
python -m agrosentinela.orchestrator --cenario geada --uf RS SC PR --intensidade 1.4

# execução offline e determinística (sem rede, sem IA)
python -m agrosentinela.orchestrator --clima sintetico --sem-llm --ignorar-supressao

# ver todas as opções
python -m agrosentinela.orchestrator --help
```

Cenários disponíveis: `seca`, `chuva_excessiva`, `chuva_intensa`, `granizo`,
`geada`, `onda_calor`, `vendaval`.

### Atalhos

```bash
make ajuda        # lista os alvos
make app          # abre a aplicação
make pipeline     # executa e exporta
make cenarios     # gera exemplos de mensagem para todos os cenários
make teste        # roda os testes
make etl          # carrega os dados oficiais do BCB
```

---

## Rodando no Windows

Todo o projeto foi escrito para ser portável: caminhos por `pathlib`, leitura
e escrita sempre com `encoding="utf-8"` declarado, nenhuma chamada exclusiva
de Unix. Roda no Windows sem alterar uma linha de código. As diferenças são
de linha de comando:

| Assunto | Linux / macOS | Windows |
|---|---|---|
| Interpretador | `python3` | `python` |
| Ativar o ambiente virtual | `source .venv/bin/activate` | `.venv\Scripts\activate` |
| Separador de caminho | `etl/run_etl.py` | `etl\run_etl.py` (a barra normal também funciona) |
| Atalhos | `make app` | `.\fazer.ps1 app` |

### Instalação no Windows

```powershell
git clone https://github.com/jlgsilva/ai_to_so_desafio5_agrosentinela.git
cd ai_to_so_desafio5_agrosentinela

python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt
streamlit run app.py
```

### `fazer.ps1` — o Makefile do Windows

O `make` não vem instalado no Windows, e pedir para instalar um utilitário de
Unix só para rodar quatro comandos é atrito desnecessário. O arquivo
`fazer.ps1` faz o mesmo, em PowerShell puro:

```powershell
.\fazer.ps1 instalar      # dependências
.\fazer.ps1 app           # abre a aplicação
.\fazer.ps1 teste         # suíte de testes
.\fazer.ps1 entregaveis   # relatório, resumo executivo e ZIP
```

Se o PowerShell recusar ("execução de scripts foi desabilitada neste
sistema"), libere **apenas para a sessão atual**:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Nenhum comando depende do `fazer.ps1` — ele só encurta o caminho.

### Duas armadilhas do Windows, já tratadas no código

Os logs deste projeto usam acentuação e símbolos (`✔`, `✖`, `═`) porque a
legibilidade importa: é por eles que se acompanha um ETL de uma hora. No
Windows isso esbarra em dois problemas clássicos, e ambos são resolvidos em
`src/agrosentinela/utils/logging_setup.py`:

1. **Redirecionar a saída quebrava o programa.** `python etl\run_etl.py >
   log.txt` fazia o Python voltar à codificação local (`cp1252`) e qualquer
   símbolo fora dela derrubava tudo com `UnicodeEncodeError`. Perder uma
   execução de uma hora por causa de um caractere de visto é inaceitável — o
   fluxo agora é reconfigurado para UTF-8 com `errors="replace"`.
2. **Cores ANSI viravam lixo no `cmd.exe` antigo.** A cor só é emitida depois
   de confirmar que o terminal aceita (tentando ligar o modo de terminal
   virtual do Windows 10+); se não der, sai sem cor em vez de sair com
   `←[38;5;39m` no meio do texto.

### Para gerar os PDFs

A geração do relatório e do resumo executivo em PDF usa o **wkhtmltopdf**,
que é um programa à parte:

1. Baixe em <https://wkhtmltopdf.org/downloads.html> (instalador *Windows
   64-bit*).
2. Durante a instalação, marque a opção de adicionar ao `PATH`. Se esquecer,
   acrescente `C:\Program Files\wkhtmltopdf\bin` às variáveis de ambiente.
3. Feche e reabra o terminal e confira com `wkhtmltopdf --version`.

**Sem ele nada quebra**: o gerador avisa, grava o HTML e o `.docx` normalmente,
e você pode abrir o HTML no navegador e usar *Imprimir → Salvar como PDF* —
o resultado é praticamente idêntico.

### O que não muda no Windows

- A aplicação Streamlit, incluindo todos os mapas.
- O ETL completo do Banco Central, com download, validação e hash.
- A geração do `.docx` (não depende de nada externo).
- A suíte de testes: `python -m pytest -q`.
- A publicação no Streamlit Cloud — que roda em Linux de qualquer forma, e é
  por isso que o CI testa nos dois.

---

## Carregando os dados oficiais do BCB

A aplicação já vem com uma **amostra de demonstração** (dados sintéticos com o
mesmo esquema dos microdados). Para usar os dados reais:

```bash
# núcleo: carteira, municípios e histórico do Proagro
python etl/run_etl.py --anos 2025 2026

# tudo: acrescenta glebas (talhões), exposição financeira e contexto externo
python etl/run_etl.py --anos 2025 2026 --tudo
```

Ou etapa por etapa:

```bash
python etl/00_download_dominios.py      # tabelas de domínio (poucos MB)
python etl/04_build_municipios.py       # geografia + alíquotas do Proagro
python etl/01_download_microdados.py --anos 2025 2026   # ⚠️ arquivos grandes
python etl/02_build_carteira.py --anos 2025 2026
python etl/03_build_proagro.py

# opcionais — cada um adiciona uma capacidade, nenhum é obrigatório
python etl/01_download_microdados.py --anos 2026 --glebas 2026 --saldos 2026 --financeiro
python etl/06_build_glebas.py --anos 2026         # alerta no talhão, não no município
python etl/07_build_exposicao.py --anos 2026      # risco em reais, não em hectares
python etl/08_build_contexto_externo.py           # fontes externas livres
#   use --offline para rodar a etapa externa sem rede

python etl/05_validate.py
```

Depois, escolha **"Somente dados curados do BCB"** na barra lateral.

As três últimas etapas são **opcionais por decisão de projeto**: a solução
funciona sem elas e a interface informa quais enriquecimentos estão ativos, em
vez de exigir dezenas de gigabytes antes da primeira tela.

> **Atenção ao volume.** `SICOR_OPERACAO_BASICA_ESTADO_2025.gz` passa de
> 300 MB comprimido. Em máquina modesta use `--amostra 150000`, que limita o
> número de operações por ano sem alterar a estrutura do resultado.

O ETL grava em `data/curated/` nos formatos Parquet **e** `.csv.gz`, valida o
resultado e produz `data/curated/manifesto.json` com a procedência.

O fluxo `.github/workflows/etl-mensal.yml` reexecuta o ETL todo mês e abre um
pull request com os dados atualizados.

---

## Publicação no Streamlit Community Cloud

> Resumo: conecte a conta do GitHub em <https://share.streamlit.io>, escolha
> este repositório, branch `main`, arquivo `app.py`, e selecione **Python 3.12**
> em *Advanced settings*. A chave da Groq, se você quiser usá-la, vai em
> **Settings → Secrets** — nunca em arquivo do repositório.

1. Deixe o repositório **público** no GitHub.
2. Em <https://share.streamlit.io>, aponte para `app.py` (branch `main`).
3. Em **Settings → Secrets**, cole:

```toml
GROQ_API_KEY = "gsk_sua_chave_aqui"
GROQ_MODEL_REDACAO = "openai/gpt-oss-120b"
FONTE_DADOS = "auto"
```

O `requirements.txt` está dimensionado para o contêiner gratuito. Como os
microdados brutos não são versionados, a aplicação publicada usa os conjuntos
curados que estiverem em `data/curated/` — ou a amostra de demonstração.

---

## Uso de IA generativa

Princípio que organiza o projeto: **o modelo redige, as regras decidem.**

| Tarefa | Usa LLM? | Por quê |
|---|---|---|
| Detectar evento climático | ❌ | Limiar numérico é determinístico e auditável |
| Calcular score de risco | ❌ | Precisa ser reproduzível e explicável |
| Decidir quem notificar | ❌ | É regra de negócio, revisável por especialista |
| Redigir a mensagem | ✅ | Adaptar tom, vocabulário e tamanho por persona |
| Escrever o boletim consolidado | ✅ | Síntese executiva a partir de métricas |
| Revisar a mensagem gerada | ✅ | Segunda passagem barata contra alucinação |
| Responder perguntas (copiloto) | ✅ com ferramentas | O pandas calcula; o modelo só redige |

**Guarda-corpos** aplicados a todo prompt de redação:

1. Usar apenas os números do bloco `DADOS`; nunca estimar.
2. Nunca prometer ou garantir pagamento de indenização.
3. Nunca dar orientação jurídica, contábil ou de investimento.
4. Tratar previsão como probabilidade, não como certeza.
5. Respeitar o limite de caracteres do canal — validado **em código**, não só
   no prompt.
6. Toda mensagem termina com ação concreta.

**Controle de cota** (camada gratuita da Groq): orçamento de chamadas por
execução, cache em disco por *hash* da requisição, modelo rápido na revisão,
respeito ao `Retry-After` em HTTP 429, telemetria de tokens na interface e
degradação graciosa para templates.

Modelos usados: `openai/gpt-oss-120b` (redação e copiloto) e
`openai/gpt-oss-20b` (revisão). Selecionáveis na interface.

---

## Regras de negócio

As regras vivem em um arquivo de texto versionado
(`src/agrosentinela/rules/rules.yaml`), legível por quem entende de crédito
rural sem saber programar.

```yaml
- id: R-GEA-02
  nome: "Geada severa em cultura perene"
  evento: geada
  quando: "tmin_min <= 2 and cultura in ['CAFE','UVA','MACA','LARANJA']"
  severidade_base: alerta
  escalonamento:
    - quando: "tmin_min <= 0"
      severidade: critico
  fases_criticas: [brotacao, frutificacao]
  personas: [produtor_empresarial, cooperativa, assistencia_tecnica, ...]
  janela_acao_h: 18
  acao: >
    Mobilizar equipe noturna, avaliar proteção dos talhões mais baixos e
    documentar por talhão para eventual comprovação de perdas.
```

São **15 regras** cobrindo seca, chuva excessiva, chuva intensa, granizo,
geada, onda de calor, vendaval, janela de colheita comprometida, ausência de
cobertura, vencimento próximo, recorrência histórica e concentração de
exposição.

**Score de risco (0–100)** = soma ponderada normalizada de: severidade
meteorológica (40) + sensibilidade da fase fenológica (25) + histórico do
Proagro no município (15) + exposição financeira (12) + ausência de cobertura
(8), mais o bônus de fase crítica da regra. Abaixo de 35 não vira mensagem.

O **simulador interativo** na página *Motor de Regras* executa exatamente o
mesmo motor, permitindo calibrar limiares e explicar decisões.

---

## Fontes de dados

| Fonte | Uso | Licença/custo |
|---|---|---|
| [Sicor — Tabelas e Microdados do Crédito Rural e do Proagro](https://www.bcb.gov.br/estabilidadefinanceira/tabelas-credito-rural-proagro) (BCB) | Carteira, município, cultura, ciclo, cobertura, histórico de COP/RCP | Dados abertos |
| [Open-Meteo](https://open-meteo.com/) | Previsão de até 16 dias e histórico recente | Gratuita, **sem chave** |
| [GroqCloud](https://console.groq.com/docs/models) | Redação das mensagens e copiloto | Camada gratuita |
| [Streamlit Community Cloud](https://streamlit.io/) | Hospedagem | Gratuita |

Os **166 arquivos** publicados pelo BCB estão catalogados em
`src/agrosentinela/etl_catalogo.py`, e a solução consome
**164 deles (98.8%)**. Os
2 de fora são os arquivos de mutuários,
deliberadamente excluídos por privacidade — e a exclusão fica **registrada no
catálogo**, não apenas omitida, para que se veja que foi escolha e não
esquecimento.

### Como os arquivos se ligam

A pergunta que separa uma solução real de uma demonstração não é "quais dados
existem?", é **"como eles se ligam?"**. O grafo de integração é código
executável (36 entidades, 36 ligações com chave
e cardinalidade, 15 delas críticas) e está em
`src/agrosentinela/data/modelo_integrado.py`, com a leitura em
[`docs/modelo_integrado.md`](docs/modelo_integrado.md).

Três descobertas organizam tudo:

1. **A chave universal do Sicor é `(REF_BACEN, NU_ORDEM)`.**
2. **A operação básica não tem município** — só `CD_ESTADO`. O
   `CD_IBGE_MUNICIPIO` mora em `SICOR_COMPLEMENTO_OPERACAO_BASICA.gz`. Sem
   essa junção não há georreferenciamento e, portanto, nenhum alerta pode ser
   dirigido a ninguém.
3. **O Proagro é uma cadeia de quatro etapas, não uma tabela**: pedido de
   cobertura → perícia → julgamento → pagamento. Medir sinistralidade só pelo
   pedido superestima; só pela perícia ignora o que foi negado.

### Fontes externas — 16 bases gratuitas e públicas

O Sicor conta o que foi **financiado** e o que foi **sinistrado**. Não conta o
que está acontecendo **agora**, nem o que existe **fora** do crédito rural.
Essas lacunas são preenchidas por 16 fontes externas —
**13 ativas no fluxo, todas gratuitas e nenhuma exigindo
cadastro** (restrição verificada por teste automatizado):

| Categoria | Fontes |
|---|---|
| clima | Open-Meteo, NASA POWER, INMET, Agritempo |
| monitoramento | CEMADEN, Programa Queimadas |
| seguro | Atlas do Seguro Rural / SISSER, SUSEP |
| produção | IBGE SIDRA, IBGE SIDRA, CONAB |
| território | IBGE, MapBiomas, Zarc |
| hídrico | ANA, Monitor de Secas do Brasil |

Cada conector degrada em três níveis — rede → cache → tabela de referência
embutida — e **o selo de procedência acompanha o dado até a tela** (🟢 ao
vivo, 🟡 cache, ⚪ referência). Um valor de referência nunca é apresentado
como se fosse consulta ao vivo.

Duas fontes têm tratamento próprio: **fogo** (INPE) e **chuva medida em solo**
(CEMADEN) nunca caem para referência. Sem rede, devolvem "não sei" em vez de
"zero" — um zero inventado esconderia justamente o evento que importa.

Campos do Sicor que sustentam a inteligência da solução:

| Campo | Uso |
|---|---|
| `CD_IBGE_MUNICIPIO` | Localiza a operação na grade meteorológica |
| `DT_INIC_PLANTIO` / `DT_INIC_COLHEITA` | Calcula a **fase fenológica** de hoje |
| `CD_EMPREENDIMENTO` → `Produto` | Define a cultura e sua sensibilidade |
| `CD_TIPO_SEGURO` | Proagro, Proagro Mais, seguro privado ou nada |
| `CD_TIPO_IRRIGACAO` | Distingue sequeiro de irrigado nas regras de seca |
| `VL_PARC_CREDITO`, `VL_AREA_FINANC` | Dimensionam a exposição |
| `DT_VENCIMENTO` | Antecipa risco de prorrogação e inadimplência |
| `CD_PROGRAMA` | Deriva a persona e o tom da mensagem |
| `SICOR_COP_BASICO` / `SICOR_RCP_BASICO` | Sinistralidade histórica por evento |

---

## Interface: responsiva e com filtros que vieram dos dados

A solução é consultada em três situações diferentes: **no celular**, por
produtor e extensionista em campo, muitas vezes com uma mão só e sol na tela;
**no tablet**, por assessor e perito em visita; **no desktop**, por analista de
crédito, atuário e gestor público.

Por isso o layout não é "desktop encolhido". Abaixo de 640 px as colunas
empilham em vez de espremer, os alvos de toque respeitam o mínimo de 44 px, a
tipografia é fluida e tabelas largas rolam **dentro do próprio quadro** — a
página nunca sai para o lado. Há ainda um seletor de modo de leitura, para
quem abre o painel no celular com o navegador em modo desktop.

Os **25 filtros** foram definidos **depois** de analisar a
carteira, o histórico do Proagro e os alertas produzidos — cada um registra
por que existe, em `src/agrosentinela/filtros.py`. Os quatro que mais separam
um painel útil de um painel bonito:

- **Cobertura de risco** — "sem Proagro e sem seguro" é a única combinação em
  que o produtor perde tudo.
- **Fase fenológica** — a mesma seca é irrelevante na maturação e
  potencialmente fatal na floração.
- **Janela de ação** — quem está em campo não pergunta "o que é grave?",
  pergunta "o que preciso resolver até amanhã?".
- **Aderência ao Zarc** — separa o risco que veio do céu do risco que veio da
  decisão de plantio. No primeiro caso se oferece apoio; no segundo,
  orientação.

E os dados aparecem **no mapa sempre que têm coordenada**: alertas, carteira,
glebas, indicadores climáticos, sinistros históricos, exposição financeira,
proteção do município, entrega das mensagens e focos de calor.

---

## Preparado para o Projeto Final (Comparação de Apólices de D&O)

A arquitetura foi construída para ser reaproveitada, e a prévia já está no
aplicativo. O núcleo muda de domínio sem mudar de forma: o mesmo motor de
regras avalia cláusulas em vez de clima; o mesmo contrato "as regras decidem,
o modelo redige" impede que um limite de cobertura saia de um modelo de
linguagem; as mesmas personas, rastro e interface.

O que é novo já existe em `src/agrosentinela/projeto_final/`: uma taxonomia de
**29 cláusulas** de D&O com peso por criticidade, e um
comparador que detecta o caso mais perigoso — quando a apólice de **melhor
escore geral não é a melhor nas cláusulas que decidem um sinistro**.

---

## Diagnóstico

Se alguma coisa não funcionar, este script confere tudo de uma vez — ambiente,
dependências, dados disponíveis, o pipeline completo, as onze páginas, as
regras e as fontes externas — e escreve um relatório em `diagnostico.txt`:

```bash
python scripts/diagnostico.py
```

Ele **nunca para no primeiro erro**: registra, explica o que fazer e segue.
No fim lista os problemas separados por gravidade, cada um com a correção.
Pode ser executado com o aplicativo aberto, em outra janela de terminal.

---

## Testes

```bash
pytest -q
```

**68 testes** cobrindo: avaliador seguro de expressões (incluindo bloqueio de
construções perigosas), disparo e escalonamento das regras, score, política
anti-fadiga, consistência da amostra de municípios (código IBGE × UF ×
*bounding box*), janelas agronômicas de plantio, inferência de persona,
mapeamento de produtos e eventos do Proagro, indicadores meteorológicos,
determinismo do gerador de cenários e o pipeline de ponta a ponta — incluindo
a verificação de que **nenhuma mensagem promete indenização** e de que todas
respeitam o limite de caracteres do canal.

---

## Estrutura do repositório

```
ai_to_so_desafio5_agrosentinela/
├── app.py                       entrada do Streamlit
├── pages/                       11 páginas da aplicação
├── src/agrosentinela/
│   ├── agents/                  os 6 agentes + copiloto
│   │   ├── base.py              classe base, Contexto e rastro
│   │   ├── carteira.py  clima.py  evento.py
│   │   ├── regras.py    redator.py  despachante.py  copiloto.py
│   ├── data/                    esquemas, loader, modelo integrado, demonstração
│   │   └── modelo_integrado.py  grafo de junções entre os arquivos do BCB
│   ├── external/                conectores das fontes externas livres
│   │   ├── base.py              rede → cache → referência, com procedência
│   │   ├── nasa_power.py  inmet.py  cemaden.py  queimadas.py
│   │   ├── zarc.py  psr_mapa.py  susep.py  conab.py
│   │   └── ibge_sidra.py  ibge_malhas.py  mapbiomas.py  ana.py
│   ├── llm/                     cliente Groq e biblioteca de prompts
│   ├── outbox/                  caixa de saída SQLite
│   ├── projeto_final/           prévia do comparador de apólices de D&O
│   ├── rules/                   catálogo, motor e rules.yaml
│   ├── utils/                   formatação brasileira e logging
│   ├── viz/                     tema responsivo, gráficos e 9 mapas
│   ├── weather/                 provedores e indicadores
│   ├── config.py  models.py  orchestrator.py  personas.py
│   ├── filtros.py               catálogo de filtros, com a justificativa de cada um
│   └── ui.py  etl_catalogo.py  fontes_externas.py
├── etl/                         download e curadoria dos microdados (11 scripts)
│                                (os entregáveis do desafio são gerados em
│                                 Desafio5_Artefatos/, fora do controle de versão)
├── tests/                       testes automatizados
├── docs/                        documentação técnica
├── notebooks/                   demonstração em Jupyter
├── requirements.txt  Makefile  LICENSE  .env.example
└── .github/workflows/           CI e ETL mensal
```

---

## Privacidade e limitações

**Privacidade.** Os microdados do Sicor incluem arquivos com CPF/CNPJ
(`SICOR_MUTUARIOS`). **O AgroSentinela não os utiliza.** O roteamento usa
apenas a referência da operação (`REF_BACEN` + `NU_ORDEM`), que funciona como
pseudônimo estável. Nenhum dado pessoal é enviado ao modelo de linguagem.
Princípio da minimização (LGPD, art. 6º, III).

**Limitações conhecidas.**

1. Previsão é probabilística — um alerta não é a certeza de um evento.
2. Não existe previsão pública direta de granizo; usamos um índice convectivo
   composto (CAPE + rajada + precipitação), documentado e auditável.
3. A grade da Open-Meteo é de ~11 km: o alerta é de município, não de talhão.
4. A fase fenológica é **estimada** pelas datas declaradas na operação, não
   observada em campo.
5. A amostra de demonstração **não é dado real**.
6. **Nenhuma mensagem é enviada** — todo despacho é simulado, conforme o
   enunciado.

**Evolução futura.** Alerta em nível de talhão com `SICOR_GLEBAS_WKT`;
validação da fase por NDVI/EVI; Zarc como atenuante formal no score; modelo
estatístico de probabilidade condicional de sinistro; integração real com
canais.

---

## Licença

Este projeto está licenciado sob a **Licença MIT** — veja o arquivo
[LICENSE](LICENSE).

Os dados do Sicor/Proagro são de domínio público, publicados pelo Banco
Central do Brasil. Os dados meteorológicos da Open-Meteo são distribuídos sob
CC-BY 4.0.

---

## Autoria

Desenvolvido por **Jefferson Luiz Gonçalves Silva** ([@jlgsilva](https://github.com/jlgsilva))
para o Desafio 5 do curso InsurMinds — Instituto de Inteligência Artificial
Aplicada (I2A2).

Trabalhos anteriores da mesma linha de pesquisa em seguro rural e crédito
agrícola:

- [ai_to_so](https://github.com/jlgsilva/ai_to_so)
- [ai_to_so_desafio4_nf_seguro_rural](https://github.com/jlgsilva/ai_to_so_desafio4_nf_seguro_rural)
