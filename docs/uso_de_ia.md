# Uso de Inteligência Artificial

## Princípio: o modelo redige, as regras decidem

Num sistema que fala com produtor rural sobre risco de perder a safra e
sobre cobertura de seguro, **alucinação é dano real**. Por isso a fronteira
entre o que é decidido por regra e o que é gerado por modelo é explícita.

| Tarefa | Usa LLM? | Justificativa |
|---|---|---|
| Detectar evento climático | ❌ | Limiar numérico é determinístico e auditável |
| Calcular score de risco | ❌ | Precisa ser reproduzível e explicável linha a linha |
| Decidir quem notificar | ❌ | É regra de negócio, revisável por especialista |
| Escolher canal e horário | ❌ | Deriva do cadastro da persona |
| Aplicar anti-fadiga | ❌ | Consulta determinística ao histórico |
| **Redigir a mensagem** | ✅ | Adaptar tom, vocabulário e tamanho ao destinatário |
| **Escrever o boletim consolidado** | ✅ | Síntese executiva a partir de métricas apuradas |
| **Revisar a mensagem gerada** | ✅ | Segunda passagem barata contra alucinação |
| **Responder perguntas (copiloto)** | ✅ com ferramentas | O pandas calcula; o modelo só redige |

## Guarda-corpos de redação

Todo prompt de redação carrega o mesmo bloco de regras inegociáveis
(`llm/prompts.py::GUARDA_CORPOS`):

1. Usar **exclusivamente** os números, datas e nomes do bloco `DADOS`.
   Nunca inventar, arredondar para outro valor nem estimar.
2. **Nunca** prometer, garantir ou sugerir que uma indenização será paga.
   Proagro e seguro rural dependem de comprovação de perdas e de análise
   técnica. É permitido informar que a operação possui cobertura e orientar
   o produtor a comunicar a ocorrência ao agente financeiro.
3. Nunca dar orientação jurídica, contábil ou de investimento.
4. Não alarmar: descrever o risco com precisão e sempre indicar o que fazer.
5. Previsão é probabilística — usar "previsão", "risco", "possibilidade";
   nunca afirmar que o evento ocorrerá.
6. Português do Brasil, sem markdown, sem caixa alta, sem assinatura inventada.
7. Respeitar o limite de caracteres do canal.

Os itens 1, 2 e 7 não ficam só no prompt: são **verificados em código**.
O limite de caracteres é truncado programaticamente; a promessa de
indenização tem teste automatizado (`test_mensagem_nao_promete_indenizacao`).

## O bloco de fatos

O modelo nunca vê a base de dados. Recebe um dicionário fechado, montado em
`RedatorAgent._bloco_de_fatos`, contendo apenas o que foi apurado:

```json
{
  "municipio": "Patrocínio",
  "uf": "MG",
  "evento_principal": "Geada",
  "severidade": "critico",
  "dia_de_maior_risco": "quinta-feira, 17 de setembro",
  "janela_de_acao_horas": 18,
  "cultura": "Café",
  "fase_da_lavoura": "Brotação / floração",
  "area_financiada_ha": 42.3,
  "valor_financiado_reais": 487300.0,
  "possui_cobertura": true,
  "evento_coberto_pelo_proagro": true,
  "indicadores_chave": {"tmin_min": -0.4, "dias_tmin_le_3": 2},
  "regras_disparadas": ["R-GEA-01", "R-GEA-02"]
}
```

Além disso, só entram no prompt as **ações das regras dirigidas àquela
persona**: não faz sentido pedir a um produtor que "eleve o município para
acompanhamento diário da área de risco".

## Saída estruturada

Onde o resultado alimenta a aplicação, o modelo responde em JSON com esquema
declarado:

```json
{
  "assunto": "string curta (≤ 90 caracteres)",
  "mensagem": "texto final, respeitando o limite do canal",
  "resumo_interno": "por que esta mensagem foi gerada",
  "acoes": ["2 a 4 ações no imperativo"],
  "tom_aplicado": "3 a 6 palavras",
  "confianca": 0.0
}
```

O *parsing* é tolerante: aceita cercas de código e texto ao redor, e devolve
`{}` em caso de falha — que aciona o caminho determinístico.

## Revisão automática (segunda passagem)

Um modelo rápido e barato (`openai/gpt-oss-20b`, temperatura 0) confere a
mensagem contra os fatos autorizados:

```json
{"aprovada": false,
 "problemas": ["cita 62 sacas/ha, valor ausente nos dados"],
 "numeros_nao_autorizados": ["62"],
 "promessa_de_pagamento": false,
 "excede_limite": false,
 "mensagem_corrigida": "..."}
```

Quando reprovada e há correção, a versão corrigida é usada. O resultado da
revisão fica visível na interface, em cada mensagem.

## Copiloto com *function calling*

O copiloto responde perguntas sobre a carteira sem nunca calcular nada. O
modelo escolhe **qual consulta fazer** e **com quais parâmetros**; o pandas
executa; o modelo só redige o resultado.

| Ferramenta | O que faz |
|---|---|
| `consultar_carteira` | Agrega por UF, município, cultura, programa, instituição, persona, safra |
| `consultar_alertas` | Alertas da execução por evento, severidade, município, cultura, regra |
| `consultar_proagro` | Histórico de COP e RCP por município, cultura e evento |
| `consultar_clima` | Indicadores meteorológicos de um município |
| `explicar_regra` | Definição completa de uma regra pelo identificador |

Salvaguardas: no máximo 4 iterações de ferramenta por pergunta; cada
resultado é truncado em 25 linhas antes de voltar ao modelo; toda resposta
exibe as ferramentas chamadas e os argumentos usados, para conferência.

Sem chave de API, o copiloto funciona em **modo determinístico**: interpreta
a pergunta por palavras-chave, executa a consulta e devolve a tabela.

## Controle de custo e de cota

A camada gratuita da Groq tem limite de requisições por minuto e por dia. As
proteções implementadas:

| Mecanismo | Onde | Efeito |
|---|---|---|
| Orçamento por execução | `GroqClient._orcamento` | Interrompe antes de estourar a cota |
| Cache em disco por *hash* | `data/cache_llm/` | Reexecutar não gasta cota |
| Modelo rápido na revisão | `GROQ_MODEL_RAPIDO` | Revisão custa uma fração da redação |
| Respeito ao `Retry-After` | `_post` | Não insiste contra o limite de taxa |
| *Backoff* exponencial | `_post` | 3 tentativas, espera crescente |
| Teto de mensagens por execução | interface e CLI | Limita o volume de chamadas |
| Consolidação por destinatário | `RedatorAgent` | Uma chamada por pessoa, não por alerta |

A telemetria (chamadas, tokens de entrada e saída, latência, respostas
servidas pelo cache, erros) é exibida na *Central de Comunicação*.

## Degradação graciosa

Sem chave, sem cota, sem rede ou com erro da API, o `RedatorAgent` cai para
templates determinísticos que produzem mensagens completas e corretas para
todos os canais. A interface **diz explicitamente** qual caminho foi usado,
em cada mensagem (`🤖 IA Generativa` ou `🧩 Template determinístico`).

Essa decisão é deliberada: um sistema de alerta de risco não pode ficar mudo
porque um serviço externo caiu.

## Modelos utilizados

| Papel | Modelo padrão | Por quê |
|---|---|---|
| Redação e boletins | `openai/gpt-oss-120b` | Melhor português e aderência a instrução longa |
| Revisão de conformidade | `openai/gpt-oss-20b` | Tarefa simples, alta vazão, baixo consumo |
| Copiloto | `openai/gpt-oss-120b` | Suporte sólido a *function calling* |

Alternativas disponíveis na interface: `openai/gpt-oss-120b`,
`openai/gpt-oss-20b`, `groq/compound-mini`. Fonte da lista:
<https://console.groq.com/docs/models>.

## O que não foi feito, e por quê

* **RAG sobre o Manual de Crédito Rural.** Seria útil para fundamentar
  prorrogações, mas adiciona dependência de banco vetorial e risco de
  citação incorreta de norma. Fica como evolução, com citação obrigatória do
  trecho-fonte.
* **Modelo de linguagem decidindo severidade.** Testado conceitualmente e
  descartado: a decisão precisa ser idêntica em duas execuções e explicável
  a um auditor.
* **Fine-tuning.** Desnecessário: a variação de tom entre personas é
  perfeitamente alcançável por *prompt*, e um modelo ajustado seria mais
  difícil de auditar.
