# Arquitetura da solução

## Visão geral

O AgroSentinela é um **pipeline determinístico de seis agentes**, encadeados
por um orquestrador que mantém um estado compartilhado (`Contexto`) e
registra o rastro de cada etapa.

```
Contexto (estado compartilhado, análogo ao estado de um grafo)
   │
   ├─① CarteiraAgent      Sicor → operações vigentes + fase fenológica + histórico
   ├─② ClimaAgent         Open-Meteo → séries diárias + indicadores por célula
   ├─③ EventoAgent        indicadores → eventos climáticos por território
   ├─④ RegrasAgent        rules.yaml → alertas com score e justificativa
   ├─⑤ RedatorAgent       Groq → mensagens por persona e canal (+ revisão)
   └─⑥ DespachanteAgent   anti-fadiga + simulação de envio → SQLite

CopilotoAgent (fora do pipeline) — consulta em linguagem natural com ferramentas
```

## Por que seis agentes, e não um script

O enunciado do Desafio 5 sugere modelar a solução como um fluxo de agentes
especializados. A decomposição adotada não é decorativa: cada fronteira
entre agentes corresponde a uma **mudança real de responsabilidade e de
fonte de verdade**.

| Agente | Entrada | Saída | Falha isolada significa |
|---|---|---|---|
| CarteiraAgent | microdados do Sicor | operações enriquecidas | não sabemos *quem* monitorar |
| ClimaAgent | coordenadas | séries + indicadores | não sabemos *o que vem aí* |
| EventoAgent | indicadores | eventos por território | não sabemos *o que é relevante* |
| RegrasAgent | eventos + operações | alertas com score | não sabemos *quem avisar* |
| RedatorAgent | alertas | mensagens | temos o alerta, falta a comunicação |
| DespachanteAgent | mensagens | envios simulados | temos a mensagem, falta o despacho |

A classe base `Agente` captura exceções: se o `ClimaAgent` falhar, os demais
continuam e a interface mostra exatamente onde parou. Um pipeline monolítico
simplesmente quebraria.

## O estado compartilhado

`agents/base.py::Contexto` é o "quadro-negro" da arquitetura. Cada agente lê
o que precisa e escreve o seu produto, **sem conhecer os demais**. Isso torna
possível:

* reordenar ou substituir um agente sem tocar nos outros;
* testar cada agente isoladamente com um contexto sintético;
* exibir o rastro completo na interface.

Campos do contexto:

```python
# entrada
data_ref, horizonte_dias, filtros, cenario, modo_clima,
usar_llm, max_mensagens, canais_ativos, respeitar_supressao

# produtos de cada etapa
base, carteira, clima_diario, indicadores,
eventos_municipio, alertas, mensagens, envios

# observabilidade
rastro, avisos, telemetria_llm, iniciado_em
```

## Por que não LangGraph, CrewAI ou AutoGen

Para um fluxo determinístico de seis etapas, sem ramificação condicional nem
negociação entre agentes, um framework de orquestração adiciona:

* **dependências pesadas**, problemáticas no contêiner gratuito do Streamlit
  Cloud (limite de memória e de tempo de build);
* **indireção**, que esconde justamente aquilo que o desafio pede para
  demonstrar — o fluxo;
* **risco de incompatibilidade** entre versões, num projeto que precisa
  rodar para um avaliador em menos de um minuto.

O contrato `Agente.executar(Contexto) -> Contexto` é exatamente a assinatura
de um nó de grafo. Migrar para LangGraph, caso a solução evolua para fluxos
condicionais (por exemplo, "se o evento for granizo, consultar radar
meteorológico antes de decidir"), é uma troca mecânica.

## Camadas

```
┌──────────────────────────────────────────────────────────┐
│ Interface (Streamlit)                                    │
│   app.py + pages/ + ui.py + viz/                         │
├──────────────────────────────────────────────────────────┤
│ Orquestração                                             │
│   orchestrator.py                                        │
├──────────────────────────────────────────────────────────┤
│ Agentes                                                  │
│   agents/*.py                                            │
├──────────────────────────────────────────────────────────┤
│ Domínio                                                  │
│   rules/ (catálogo + motor)  personas.py  models.py      │
├──────────────────────────────────────────────────────────┤
│ Integrações            │ Persistência                    │
│   weather/  llm/       │   data/  outbox/                │
├──────────────────────────────────────────────────────────┤
│ Fontes externas                                          │
│   Sicor/BCB · Open-Meteo · GroqCloud                     │
└──────────────────────────────────────────────────────────┘
```

Nenhuma camada superior é importada por uma inferior. O núcleo
(`agents`, `rules`, `data`, `weather`, `llm`) **não importa Streamlit** — é
por isso que o pipeline roda igualmente pela linha de comando, em teste
automatizado e em CI.

## Tolerância a falhas

O projeto foi desenhado para **nunca deixar o avaliador sem nada para ver**.

| Falha | Comportamento | Onde fica visível |
|---|---|---|
| Sem `GROQ_API_KEY` | Redator determinístico assume | Aviso na execução e etiqueta na mensagem |
| Groq fora do ar ou sem cota | Idem, após tentativas com *backoff* | Aviso + telemetria de erro |
| Open-Meteo indisponível | Gerador sintético assume aquele lote | Aviso explícito + rótulo da fonte |
| Sem dados curados do BCB | Amostra de demonstração | Faixa permanente na barra lateral |
| `pyarrow` ausente | Lê e grava `.csv.gz` | Transparente |
| Um agente lança exceção | Pipeline segue, etapa marcada como erro | Rastro de execução |

Essa política tem um custo: o sistema pode apresentar resultados que **não
são reais**. Por isso, toda contingência é anunciada de forma explícita na
interface — nunca silenciosamente.

## Desempenho

Execução típica com a amostra de demonstração (3.600 operações, 103
municípios), em contêiner modesto:

| Etapa | Tempo |
|---|---|
| CarteiraAgent | ~0,05 s |
| ClimaAgent (sintético) | ~0,3 s |
| ClimaAgent (Open-Meteo, 100 células) | 3–8 s |
| EventoAgent | ~0,03 s |
| RegrasAgent | ~0,7 s |
| RedatorAgent (templates) | ~0,1 s |
| RedatorAgent (LLM, 12 mensagens) | 15–40 s |
| DespachanteAgent | < 0,01 s |

Três decisões sustentam esses números:

1. **Deduplicação por célula de grade** (~11 km): 103 municípios viram ~100
   células, e municípios vizinhos passam a compartilhar uma única consulta.
2. **Requisições em lote** à Open-Meteo (40 coordenadas por chamada).
3. **Cache em disco** com TTL para clima e por *hash* para o LLM.

## Extensibilidade

| Para adicionar… | Altere |
|---|---|
| um evento climático | `rules/catalogo.py` (`EVENTOS`) + escada em `agents/evento.py` |
| uma cultura | `rules/catalogo.py` (`CULTURAS`) e o mapa de produtos |
| uma regra de negócio | apenas `rules/rules.yaml` — nenhum código |
| uma persona | `personas.py` |
| um canal | `personas.py` (`LIMITE_CANAL`) + `agents/despachante.py` (`PERFIL_CANAL`) |
| uma fonte meteorológica | nova classe que implemente `ClimaProvider` |
| um conjunto de dados | `data/schemas.py` + um script em `etl/` |
