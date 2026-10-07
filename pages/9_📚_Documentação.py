"""Documentação viva: arquitetura, uso de IA, governança e reprodutibilidade."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from agrosentinela import __version__  # noqa: E402
from agrosentinela.config import MODELOS_GROQ, ROOT_DIR, get_settings  # noqa: E402
from agrosentinela import filtros  # noqa: E402
from agrosentinela.data import modelo_integrado as modelo  # noqa: E402
from agrosentinela.etl_catalogo import (  # noqa: E402
    PAGINA_FONTE,
    nao_usados,
    resumo as resumo_catalogo,
)
from agrosentinela.orchestrator import Orquestrador  # noqa: E402
from agrosentinela.ui import (  # noqa: E402
    barra_lateral,
    base_atual,
    cabecalho,
    configurar_pagina,
    largura_total,
    obter_motor,
    tabela,
)
from agrosentinela.viz import maps  # noqa: E402
from agrosentinela.weather.indicadores import descricao_indicadores  # noqa: E402

configurar_pagina("Documentação", "📚")
barra_lateral(mostrar_execucao=False)

cabecalho(
    "Documentação",
    f"AgroSentinela v{__version__} · arquitetura, decisões técnicas e governança.",
    "📚",
)

(
    aba_arq, aba_ia, aba_dados, aba_modelo, aba_filtros, aba_gov, aba_repro
) = st.tabs(
    ["🏗️ Arquitetura", "🧠 Uso de IA", "🗂️ Dados", "🔗 Modelo integrado",
     "🔎 Filtros", "⚖️ Governança", "🔁 Reprodutibilidade"]
)

# ==========================================================================
with aba_arq:
    st.markdown(
        """
### Arquitetura multiagente

A solução é um **pipeline de seis agentes especializados**, encadeados por um
orquestrador. Cada agente tem uma responsabilidade única, um contrato de
entrada e saída explícito e um rastro próprio — tempo de execução, resumo e
métricas. É esse rastro que a página inicial exibe e que demonstra o fluxo
completo exigido pelo enunciado.

A escolha de **não** usar um framework de agentes foi deliberada: para um
pipeline determinístico de seis etapas, o encadeamento explícito é mais
auditável, tem menos dependências (o que importa na camada gratuita do
Streamlit Cloud) e deixa a arquitetura visível. O contrato de `Agente.executar`
recebe e devolve o mesmo objeto `Contexto`, que funciona como estado de grafo —
portar para LangGraph seria uma troca mecânica.
        """
    )
    st.code(
        """
Contexto (estado compartilhado)
   │
   ├─① CarteiraAgent     Sicor → operações vigentes + fase fenológica + histórico
   ├─② ClimaAgent        Open-Meteo → séries diárias + indicadores por célula
   ├─③ EventoAgent       indicadores → eventos climáticos por território
   ├─④ RegrasAgent       rules.yaml → alertas com score e justificativa
   ├─⑤ RedatorAgent      Groq → mensagens por persona e canal (+ revisão)
   └─⑥ DespachanteAgent  anti-fadiga + simulação de envio → SQLite

CopilotoAgent (fora do pipeline)  consulta em linguagem natural com ferramentas
        """,
        language="text",
    )

    orq = Orquestrador(base=base_atual(), motor=obter_motor())
    tabela(pd.DataFrame(orq.descrever_pipeline()), altura=300)

    st.markdown(
        """
#### Mapeamento com o enunciado do Desafio 5

| Etapa exigida | Onde está | Evidência na interface |
|---|---|---|
| 1. Coleta em fonte externa de dados meteorológicos | `ClimaAgent` + `weather/open_meteo.py` | Radar Climático |
| 2. Identificação de eventos relevantes | `EventoAgent` + escadas de limiares | Radar Climático / Mapa |
| 3. Aplicação de regras de negócio | `RegrasAgent` + `rules/rules.yaml` | Motor de Regras |
| 4. Geração automática das mensagens | `RedatorAgent` + `llm/prompts.py` | Central de Comunicação |
| 5. Simulação do envio | `DespachanteAgent` + `outbox/store.py` | Central de Comunicação |
| Demonstração do fluxo completo | `Orquestrador` + rastro de execução | Início |

#### Estrutura do repositório
        """
    )
    st.code(
        """
app.py                     entrada do Streamlit
pages/                     11 páginas da aplicação
src/agrosentinela/
  agents/                  os 6 agentes + copiloto
  data/                    esquemas, carregamento, gerador de demonstração
  llm/                     cliente Groq e biblioteca de prompts
  outbox/                  caixa de saída SQLite
  rules/                   catálogo de eventos/fenologia + motor + rules.yaml
  utils/                   formatação e logging
  viz/                     tema, gráficos e mapas
  weather/                 provedores meteorológicos e indicadores
  config.py  models.py  orchestrator.py  personas.py  ui.py  etl_catalogo.py
etl/                       scripts de download e curadoria dos microdados
tests/                     testes automatizados
docs/                      documentação técnica
Desafio5_Artefatos/        entregáveis gerados (fora do controle de versão)
        """,
        language="text",
    )

# ==========================================================================
with aba_ia:
    s = get_settings()
    st.markdown(
        """
### Onde a IA generativa é usada — e onde deliberadamente não é

O princípio que organiza todo o projeto: **o modelo redige, as regras
decidem**. Nenhum limiar, severidade, score ou decisão de envio passa pelo
modelo de linguagem. O que o modelo recebe é um conjunto de fatos já
apurados e uma decisão já tomada; o que ele devolve é texto.

| Tarefa | Usa LLM? | Por quê |
|---|---|---|
| Detectar evento climático | **Não** | Limiar numérico é determinístico e auditável |
| Calcular score de risco | **Não** | Precisa ser reproduzível e explicável |
| Decidir quem notificar | **Não** | É regra de negócio, revisável por especialista |
| Redigir a mensagem | **Sim** | Adaptar tom, vocabulário e tamanho por persona |
| Escrever o boletim consolidado | **Sim** | Síntese executiva a partir de métricas |
| Revisar a mensagem gerada | **Sim** | Segunda passagem barata contra alucinação |
| Responder perguntas (copiloto) | **Sim**, com ferramentas | O pandas calcula; o modelo só redige |

#### Guarda-corpos aplicados a todo prompt de redação

1. Usar **apenas** os números do bloco `DADOS`; nunca estimar.
2. **Nunca** prometer ou garantir pagamento de indenização — Proagro e seguro
   dependem de comprovação e análise técnica.
3. Nunca dar orientação jurídica, contábil ou de investimento.
4. Tratar previsão como probabilidade, não como certeza.
5. Respeitar o limite de caracteres do canal (validado em código, não só no prompt).
6. Toda mensagem termina com ação concreta.

#### Controle de custo e de cota (camada gratuita)

* orçamento de chamadas por execução (`LLM_MAX_CHAMADAS_POR_RUN`);
* cache em disco por *hash* da requisição — reexecutar não gasta cota;
* modelo rápido e barato para a revisão, modelo maior só para a redação;
* respeito ao cabeçalho `Retry-After` em HTTP 429, com *backoff* exponencial;
* telemetria de tokens e latência exibida na Central de Comunicação;
* **degradação graciosa**: sem chave, sem cota ou sem rede, o redator
  determinístico assume e a interface diz isso explicitamente.
        """
    )
    st.markdown("#### Modelos disponíveis na GroqCloud")
    tabela(
        pd.DataFrame([
            {"ID": m.id, "Modelo": m.rotulo, "Contexto": f"{m.contexto:,}".replace(",", "."),
             "Tool calling": "sim" if m.tool_calling else "não",
             "Perfil": m.perfil, "Observação": m.observacao}
            for m in MODELOS_GROQ
        ]),
        altura=260,
    )
    st.markdown("#### Configuração efetiva (sem segredos)")
    st.json(s.resumo_publico(), expanded=False)

# ==========================================================================
with aba_dados:
    base = base_atual()
    st.markdown(
        f"""
### Fonte dos dados

Toda a base vem de [Tabelas e Microdados do Crédito Rural e do Proagro]({PAGINA_FONTE}),
publicada pelo Banco Central do Brasil em dados abertos.

O catálogo completo está mapeado em `src/agrosentinela/etl_catalogo.py` e é
exibido na página **Microdados Sicor**.
        """
    )
    st.json(resumo_catalogo(), expanded=False)

    st.markdown(
        """
#### Por que a carteira de demonstração existe

Os microdados do Sicor somam dezenas de gigabytes. Não cabem no GitHub nem
na memória de um contêiner gratuito do Streamlit Cloud. A solução adotada:

1. O **ETL** (`etl/`) roda localmente ou no GitHub Actions, baixa os arquivos
   oficiais, valida, agrega e grava conjuntos **curados e compactos** em
   `data/curated/` — apenas esses são versionados.
2. Enquanto os curados não existem, o aplicativo usa uma **amostra de
   demonstração** sintética, com **o mesmo esquema** e proporções calibradas
   pelo perfil público do Sicor.
3. A interface **sempre** informa qual das duas está em uso.

Isso mantém o projeto executável por qualquer avaliador em menos de um
minuto, sem esconder a diferença entre dado real e dado sintético.
        """
    )
    st.markdown("#### Indicadores meteorológicos calculados")
    tabela(pd.DataFrame(descricao_indicadores()), altura=480)

    st.markdown("#### Diagnóstico da base carregada")
    st.json(base.resumo(), expanded=False)
    st.caption(f"Mapas: {maps.disponivel()['api_de_mapas']}")

    st.markdown("#### Enriquecimentos opcionais")
    st.caption(
        "Cada um adiciona uma capacidade e nenhum é obrigatório. A solução "
        "funciona sem todos eles — apenas informa o que está e o que não está "
        "disponível, em vez de exigir dezenas de gigabytes antes da primeira tela."
    )
    st.dataframe(
        pd.DataFrame([
            {"enriquecimento": k, "disponível": "sim" if v else "—",
             "habilita": desc}
            for (k, v), desc in zip(
                base.enriquecimentos().items(),
                ["Alerta no talhão, e não no centroide do município "
                 "(etl/06_build_glebas.py)",
                 "Risco expresso em reais, e não em hectares "
                 "(etl/07_build_exposicao.py)",
                 "Normal climática, denominador produtivo, seguro privado e "
                 "seca oficial (etl/08_build_contexto_externo.py)"],
            )
        ]),
        **largura_total(), hide_index=True,
    )

# ==========================================================================
with aba_modelo:
    st.markdown(
        f"""
### Como os {resumo_catalogo()['total']} arquivos do BCB se conversam

A pergunta que separa uma solução real de uma demonstração não é "quais dados
existem?", é **"como eles se ligam?"**. Três descobertas organizam todo o resto:

**1. A chave universal é `(REF_BACEN, NU_ORDEM)`.** `REF_BACEN` identifica o
contrato junto ao Banco Central; `NU_ORDEM` distingue cada empreendimento
dentro dele. Quase todo microdado do Sicor carrega esse par.

**2. A operação básica não tem município.**
`SICOR_OPERACAO_BASICA_ESTADO_AAAA.gz` só traz `CD_ESTADO`. O
`CD_IBGE_MUNICIPIO` mora em `SICOR_COMPLEMENTO_OPERACAO_BASICA.gz`. Sem essa
junção não há georreferenciamento — e sem georreferenciamento não há alerta
climático dirigido. É a ligação mais crítica do modelo inteiro.

**3. O Proagro é uma cadeia de quatro etapas, não uma tabela.**
COP (pedido) → RCP (perícia) → Súmula (julgamento) → Parcelas (pagamento).
Medir sinistralidade só pelo COP superestima; só pelo RCP ignora o que foi
negado. A solução percorre a cadeia inteira e expõe as três taxas separadas.
        """
    )
    st.json(modelo.resumo(), expanded=False)

    st.markdown("#### Ligações críticas")
    st.caption("Sem qualquer uma delas, alguma capacidade deixa de existir.")
    tabela(pd.DataFrame([l.to_row() for l in modelo.ligacoes_criticas()]), altura=420)

    st.markdown("#### Ordem de montagem no ETL")
    tabela(pd.DataFrame(modelo.receita_tabela()), altura=340)

    st.markdown("#### Diagrama")
    st.caption(
        "Apenas as ligações críticas, para legibilidade. O grafo completo está "
        "em `docs/modelo_integrado.md`, gerado a partir do próprio código."
    )
    st.code(modelo.mermaid(somente_criticas=True), language="mermaid")

    with st.expander("Todas as entidades e ligações"):
        tabela(pd.DataFrame(modelo.tabela_entidades()), altura=380)
        tabela(pd.DataFrame(modelo.tabela_ligacoes()), altura=380)

    st.markdown("#### O que deliberadamente não é usado")
    excluidos = pd.DataFrame([a.to_row() for a in nao_usados()])
    if excluidos.empty:
        st.success("Todos os arquivos catalogados são consumidos.")
    else:
        st.caption(
            "Registrar a exclusão no catálogo — em vez de apenas omitir os "
            "arquivos — é o que permite conferir que foi escolha, e não "
            "esquecimento."
        )
        tabela(excluidos, altura=200)

# ==========================================================================
with aba_filtros:
    st.markdown(
        f"""
### Filtros definidos **depois** de olhar para os dados

Filtro bom não é filtro para toda coluna — é filtro para as perguntas que as
pessoas de fato fazem. Os {len(filtros.FILTROS)} cortes abaixo saíram da
análise da carteira do Sicor, do histórico do Proagro e dos alertas
produzidos pelo motor de regras. Cada um registra **por que existe**, para
que a escolha possa ser discutida em vez de aceita.

Os quatro que mais separam um painel útil de um painel bonito:

* **Cobertura de risco** — "sem Proagro e sem seguro" é a única combinação em
  que o produtor perde tudo.
* **Fase fenológica** — a mesma seca é irrelevante na maturação e
  potencialmente fatal na floração.
* **Janela de ação** — quem está em campo não pergunta "o que é grave?",
  pergunta "o que preciso resolver até amanhã?".
* **Aderência ao Zarc** — separa o risco que veio do céu do risco que veio da
  decisão de plantio. No primeiro caso se oferece apoio; no segundo,
  orientação.
        """
    )
    tabela(pd.DataFrame(filtros.tabela()), altura=620)
    st.caption(
        f"{len(filtros.essenciais())} filtros são marcados como essenciais e "
        "aparecem na barra compacta, inclusive no celular. Os demais ficam "
        "agrupados por tema e só são exibidos quando a coluna existe e tem "
        "mais de um valor no conjunto atual — filtro de uma opção só ocupa "
        "espaço e não filtra nada."
    )

# ==========================================================================
with aba_gov:
    st.markdown(
        """
### Privacidade e proteção de dados

Os microdados do Sicor incluem arquivos com CPF/CNPJ de mutuários
(`SICOR_MUTUARIOS`). **O AgroSentinela não os utiliza.** A decisão é de
projeto, não de conveniência:

* o roteamento da comunicação precisa apenas da **referência da operação**
  (`REF_BACEN` + `NU_ORDEM`), que funciona como pseudônimo estável;
* o destinatário é exibido como `OP-<referência>` — nunca como pessoa
  identificada;
* nenhum dado pessoal é enviado ao modelo de linguagem;
* princípio da **minimização** (LGPD, art. 6º, III): coleta-se o mínimo
  necessário para a finalidade.

Em uma implantação real, o cruzamento entre a referência da operação e o
contato do cliente ficaria dentro da instituição financeira, sob a base
legal adequada — nunca no serviço de alerta.

### Limitações conhecidas

1. **Previsão é probabilística.** Um alerta não é a certeza de um evento.
   O texto das mensagens é explícito quanto a isso.
2. **Granizo não tem previsão pública direta.** Usamos um índice convectivo
   composto (CAPE + rajada + precipitação), documentado e auditável, que é
   uma estimativa de *ambiente favorável* — não uma previsão determinística.
3. **Resolução de grade.** A Open-Meteo entrega ~11 km; o alerta é de
   município, não de talhão. Com `SICOR_GLEBAS_WKT` seria possível descer ao
   talhão — está mapeado como evolução.
4. **Fase fenológica estimada.** É calculada pela fração decorrida entre as
   datas de plantio e colheita declaradas na operação, não por observação de
   campo nem por índice de vegetação.
5. **A amostra de demonstração não é dado real.** Reproduz estrutura e
   proporções, não fatos.
6. **Nenhuma mensagem é enviada.** Todo despacho é simulado, conforme o
   enunciado.

### Vieses e efeitos indesejados

* **Fadiga de alerta**: mitigada por janela de repetição, teto diário e
  consolidação por destinatário.
* **Viés de porte**: ordenar só por exposição financeira faria a fila ser
  tomada pelas maiores operações. O redator distribui o teto de mensagens
  entre as personas em rodízio, preservando a ordem de risco dentro de cada
  uma — assim o produtor familiar de ticket baixo também é avisado.
* **Falso negativo é mais caro que falso positivo** neste domínio: os
  limiares foram calibrados para sensibilidade, e a supressão atua depois,
  na camada de comunicação.

### Evolução futura

* alerta em nível de **talhão** com as glebas em WKT;
* incorporação de **NDVI/EVI** (satélite) para validar a fase estimada;
* **Zarc** como atenuante formal no score;
* modelo estatístico de probabilidade condicional de sinistro treinado sobre
  a série COP/RCP completa;
* integração real com canais (WhatsApp Business API, e-mail transacional).
        """
    )

# ==========================================================================
with aba_repro:
    st.markdown(
        """
### Como reproduzir

```bash
git clone <url-do-repositório>
cd ai_to_so_desafio5_agrosentinela

python -m venv .venv && source .venv/bin/activate    # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt

cp .env.example .env          # opcional: informe a GROQ_API_KEY
streamlit run app.py
```

Sem nenhuma configuração adicional o aplicativo já funciona: usa a amostra
de demonstração, o gerador climático determinístico e o redator por
templates, sinalizando cada um desses fallbacks.

### Linha de comando

```bash
# pipeline completo, exportando os resultados
python -m agrosentinela.orchestrator --exportar saida/

# cenário de geada no Sul, sem IA generativa
python -m agrosentinela.orchestrator --cenario geada --uf RS SC PR --sem-llm

# apenas dados sintéticos (sem rede)
python -m agrosentinela.orchestrator --clima sintetico --ignorar-supressao
```

### Carregando os dados oficiais do Banco Central

```bash
python etl/run_etl.py --anos 2025 2026        # baixa, valida e cura
# ou, em partes:
python etl/00_download_dominios.py
python etl/01_download_microdados.py --anos 2025 2026
python etl/02_build_carteira.py
python etl/03_build_proagro.py
python etl/05_validate.py
```

Depois disso, escolha **"Somente dados curados do BCB"** na barra lateral.

### Testes

```bash
pytest -q
```

### Publicação no Streamlit Community Cloud

1. Suba o repositório público no GitHub.
2. Em share.streamlit.io, aponte para `app.py`.
3. Em *Settings → Secrets*, adicione:

```toml
GROQ_API_KEY = "gsk_..."
GROQ_MODEL_REDACAO = "openai/gpt-oss-120b"
```

O `requirements.txt` já está dimensionado para o contêiner gratuito.
        """
    )
    st.markdown("#### Variáveis de ambiente reconhecidas")
    tabela(
        pd.DataFrame([
            {"Variável": "GROQ_API_KEY", "Padrão": "—", "Para que serve": "Ativa a IA generativa"},
            {"Variável": "GROQ_MODEL_REDACAO", "Padrão": "openai/gpt-oss-120b",
             "Para que serve": "Modelo que redige as mensagens"},
            {"Variável": "GROQ_MODEL_RAPIDO", "Padrão": "openai/gpt-oss-20b",
             "Para que serve": "Modelo da revisão de conformidade"},
            {"Variável": "GROQ_MODEL_COPILOTO", "Padrão": "openai/gpt-oss-120b",
             "Para que serve": "Modelo do copiloto com ferramentas"},
            {"Variável": "LLM_MAX_CHAMADAS_POR_RUN", "Padrão": "40",
             "Para que serve": "Guarda-corpo de cota gratuita"},
            {"Variável": "LLM_CACHE_ATIVO", "Padrão": "true",
             "Para que serve": "Cache em disco das respostas do modelo"},
            {"Variável": "CLIMA_MAX_MUNICIPIOS", "Padrão": "250",
             "Para que serve": "Teto de municípios por consulta meteorológica"},
            {"Variável": "DIAS_PREVISAO", "Padrão": "10",
             "Para que serve": "Horizonte padrão da previsão"},
            {"Variável": "FONTE_DADOS", "Padrão": "auto",
             "Para que serve": "auto | curated | seed"},
            {"Variável": "TIMEZONE", "Padrão": "America/Sao_Paulo",
             "Para que serve": "Fuso das séries e do agendamento"},
            {"Variável": "LOG_LEVEL", "Padrão": "INFO", "Para que serve": "Verbosidade do log"},
        ]),
        altura=440,
    )
    st.caption(f"Raiz do projeto em execução: `{ROOT_DIR}`")
