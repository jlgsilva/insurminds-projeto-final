# Regras de negócio

## Princípio

**O modelo de linguagem redige; as regras decidem.** Nenhum limiar,
severidade, score ou decisão de envio passa por IA generativa. Isso torna o
sistema reproduzível, auditável e revisável por quem entende de crédito
rural — não apenas por quem programa.

As regras vivem em `src/agrosentinela/rules/rules.yaml`, em texto, sob
controle de versão.

## Anatomia de uma regra

```yaml
- id: R-SEC-02
  nome: "Seca severa em lavoura sem irrigação"
  evento: seca
  descricao: >
    Agravamento da regra de veranico quando a operação não declara irrigação
    no Sicor (CD_TIPO_IRRIGACAO indicando sequeiro).
  quando: "dias_secos_consecutivos >= 14 and not irrigada and balanco_hidrico_14d <= -45"
  severidade_base: alerta
  escalonamento:
    - quando: "dias_secos_consecutivos >= 25"
      severidade: critico
  fases_criticas: [floracao, enchimento]
  bonus_fase: 22
  personas: [produtor_familiar, produtor_empresarial, assistencia_tecnica, gerente_credito_rural]
  janela_acao_h: 48
  acao: >
    Avaliar antecipação de comunicação de perda ao agente do Proagro e
    planejar manejo de emergência.
  base_tecnica: >
    Lavouras de sequeiro não têm mecanismo de mitigação imediata; a perda
    tende a se materializar em 2 a 3 semanas de déficit continuado.
  cobertura_proagro: true
```

| Campo | Função |
|---|---|
| `id` | Identificador estável, citado em toda mensagem e alerta (auditoria) |
| `quando` | Expressão booleana sobre os indicadores — avaliada com segurança |
| `escalonamento` | Condições que **elevam** a severidade |
| `fases_criticas` | Fases fenológicas que tornam a regra mais grave |
| `bonus_fase` | Pontos somados ao score quando a operação está em fase crítica |
| `personas` | Quem deve ser notificado (filtra a ação exibida em cada mensagem) |
| `janela_acao_h` | Prazo recomendado para a ação — define a urgência no despacho |
| `cobertura_proagro` | Se o evento é, em regra, coberto pelo Proagro |

## Avaliação segura das expressões

A chave `quando` **não** é passada para `eval()`. O módulo
`rules/engine.py` contém um mini-interpretador sobre a AST do Python que
aceita apenas:

* literais, nomes de indicadores e listas;
* operadores booleanos (`and`, `or`, `not`);
* comparações (`==`, `!=`, `<`, `<=`, `>`, `>=`, `in`, `not in`);
* aritmética simples;
* as funções `min`, `max`, `abs`, `round`, `len`, `int`, `float`, `bool`.

Qualquer outra construção (importação, atributo, chamada arbitrária,
compreensão de lista, lambda) levanta `ExpressaoInvalida` — **no momento do
carregamento do arquivo**, não em produção. Há teste automatizado cobrindo
tentativas de injeção.

Indicador ausente no contexto **não faz a regra disparar**: a comparação
devolve `False`. Isso evita que a falta de um dado produza alerta falso.

## Indicadores disponíveis

### Janela observada (passado recente, 14 dias)

| Indicador | Unidade | Descrição |
|---|---|---|
| `prec_passada_14d` | mm | Chuva acumulada nos 14 dias anteriores |
| `dias_secos_passados` | dias | Sequência de dias sem chuva encerrada hoje |
| `balanco_hidrico_14d` | mm | Chuva menos evapotranspiração de referência (ET0) |

### Janela prevista (horizonte configurável, padrão 7 dias)

| Indicador | Unidade | Descrição |
|---|---|---|
| `prec_1d`, `prec_3d`, `prec_7d`, `prec_14d` | mm | Precipitação acumulada |
| `prec_max_24h` | mm | Maior acumulado diário |
| `dias_com_chuva_7d` | dias | Dias com chuva ≥ 1 mm |
| `prob_prec_max` | % | Maior probabilidade diária de precipitação |
| `dias_secos_previstos` | dias | Sequência seca iniciando amanhã |
| `dias_secos_consecutivos` | dias | Sequência observada **somada** à prevista |
| `balanco_hidrico_7d` | mm | Chuva menos ET0 na janela prevista |
| `et0_7d` | mm | Evapotranspiração de referência acumulada |
| `tmin_min`, `tmax_max` | °C | Extremos previstos |
| `dias_tmin_le_3`, `dias_tmin_le_0` | dias | Risco de geada |
| `dias_tmax_ge_32`, `dias_tmax_ge_35` | dias | Estresse térmico |
| `amplitude_max` | °C | Maior amplitude térmica diária |
| `rajada_max`, `vento_medio_max` | km/h | Vento |
| `cape_max` | J/kg | Energia potencial convectiva disponível |
| `prob_granizo` | 0–100 | Índice convectivo composto |
| `umidade_media`, `umidade_min` | % | Umidade relativa |

### Contexto da operação

`fase`, `cultura`, `cultura_grupo`, `progresso_ciclo`, `dias_para_colheita`,
`dias_para_vencimento`, `dias_desde_plantio`, `tem_cobertura`, `irrigada`,
`area_ha`, `valor_credito`, `exposicao_municipio`, `operacoes_municipio`,
`freq_evento_municipio`, `sinistralidade_municipio`, `programa`,
`modalidade`, `persona`, `uf`, `regiao`, `severidade_peso`.

## O índice de granizo

Não existe previsão pública direta de granizo de acesso livre. O sistema usa
um **índice convectivo composto**, documentado e auditável:

```
f_cape  = (CAPE − 800) / 2200     energia convectiva disponível
f_vento = (rajada − 40) / 50      organização da célula convectiva
f_chuva = (prec24h − 15) / 45     presença de núcleo precipitante

índice = 100 × (0,55·f_cape + 0,27·f_vento + 0,18·f_chuva)
```

Com **porta de entrada**: se CAPE < 800 J/kg o índice é zero, porque sem
energia convectiva não há formação de granizo relevante. Cada fator é
limitado ao intervalo [0, 1].

O índice estima **ambiente favorável**, não ocorrência. As mensagens são
escritas nesses termos.

## As 15 regras

### Eventos climáticos

| ID | Nome | Evento | Disparo essencial |
|---|---|---|---|
| R-SEC-01 | Veranico prolongado com déficit hídrico | seca | ≥ 10 dias secos **e** balanço 14 d ≤ −30 mm |
| R-SEC-02 | Seca severa em lavoura sem irrigação | seca | ≥ 14 dias secos, sequeiro, balanço ≤ −45 mm |
| R-SEC-03 | Estresse hídrico em pastagem e pecuária | seca | ≥ 18 dias secos em atividade pecuária |
| R-CHU-01 | Chuva acumulada excessiva | chuva excessiva | ≥ 120 mm em 7 dias |
| R-CHU-02 | Chuva intensa em 24 horas | chuva intensa | ≥ 50 mm em um dia |
| R-CHU-03 | Janela de colheita comprometida | umidade na colheita | colheita em ≤ 21 d, ≥ 4 dias de chuva, UR ≥ 75 % |
| R-GRA-01 | Probabilidade elevada de granizo | granizo | índice ≥ 45 |
| R-GEA-01 | Risco de geada | geada | mínima ≤ 4 °C |
| R-GEA-02 | Geada severa em cultura perene | geada | mínima ≤ 2 °C em café, uva, maçã ou citros |
| R-CAL-01 | Onda de calor | onda de calor | ≥ 3 dias com máxima ≥ 35 °C |
| R-VEN-01 | Rajadas de vento severas | vendaval | rajada ≥ 60 km/h |

### Regras financeiras e de carteira (qualquer evento)

| ID | Nome | Disparo essencial | Personas |
|---|---|---|---|
| R-COB-01 | Exposição sem cobertura de risco | sem cobertura **e** severidade ≥ alerta | corretor, banco, produtor, gestor |
| R-FIN-01 | Vencimento próximo sob evento climático | vence em ≤ 90 d **e** severidade ≥ alerta | banco, seguradora, gestor |
| R-HIS-01 | Município com histórico recorrente | ≥ 25 % dos sinistros históricos são deste evento | seguradora, gestor, cooperativa, banco |
| R-CON-01 | Concentração de exposição no município | ≥ R$ 5 mi expostos e severidade ≥ alerta | banco, seguradora, gestor |

## Fenologia e sensibilidade

Cada cultura tem fases com um **multiplicador de sensibilidade** por evento.
É o que diferencia "chove muito" de "chove muito em plena colheita".

Exemplo — soja (culturas anuais de grãos):

| Fase | % do ciclo | Seca | Chuva excessiva | Granizo | Geada | Calor |
|---|---|---|---|---|---|---|
| Semeadura / emergência | 0–18 % | 1,6 | 1,5 | 0,7 | 1,2 | 1,2 |
| Vegetativo | 18–45 % | 1,3 | 1,2 | 1,3 | 1,4 | 1,1 |
| **Floração** | 45–65 % | **2,0** | 1,5 | 1,8 | 1,6 | **2,0** |
| **Enchimento de grãos** | 65–85 % | **1,8** | 1,3 | **1,9** | **1,9** | 1,7 |
| Maturação | 85–96 % | 0,8 | **1,9** | **2,0** | 1,2 | 1,0 |
| Colheita | 96–100 % | 0,5 | **2,0** | 1,6 | 0,8 | 0,9 |

Culturas perenes (café, uva, maçã, citros, cana) usam repouso, brotação /
floração, frutificação e colheita. Pecuária e pastagem usam rebrota, pleno
pastejo, entressafra forrageira e manejo sanitário — falar em "floração de
bovinocultura" seria absurdo, e o sistema não o faz.

A fase corrente é calculada pela fração decorrida entre `DT_INIC_PLANTIO` e
`DT_INIC_COLHEITA` **declaradas na própria operação** do Sicor. Operações sem
essas datas (típico de investimento) entram como `sem_ciclo`: continuam na
carteira para as regras financeiras, mas não recebem alerta agronômico.

## Score de risco

```
score = 100 × ( 40·severidade + 25·sensibilidade_da_fase
              + 15·histórico_do_município + 12·exposição_financeira
              +  8·ausência_de_cobertura  + bônus_de_fase_crítica )
        ÷ máximo_teórico_da_regra
```

| Componente | Peso | Normalização |
|---|---|---|
| Severidade meteorológica | 40 | peso da severidade ÷ 4 |
| Sensibilidade da fase | 25 | (sensibilidade − 0,5) ÷ 1,8, limitado a [0, 1] |
| Histórico do Proagro | 15 | participação do evento ÷ 0,5, limitado a [0, 1] |
| Exposição financeira | 12 | (log₁₀(valor) − 4) ÷ 2,7, limitado a [0, 1] |
| Ausência de cobertura | 8 | 0 ou 1 |
| Bônus de fase crítica | 0–28 | definido por regra |

A divisão pelo máximo teórico **da própria regra** torna o score comparável
entre regras com bônus diferentes e evita a saturação em 100.

**Limiar de notificação: 35.** Abaixo disso o alerta é registrado, mas não
gera mensagem.

## Política anti-fadiga

| Parâmetro | Padrão | Razão |
|---|---|---|
| Janela de repetição | 48 h | Não reenviar enquanto a situação não muda |
| Máximo por destinatário/dia | 3 | Alerta em excesso deixa de ser lido |
| Severidade mínima global | atenção | Ruído informativo não vira mensagem |
| Consolidação por destinatário | sim | Vários eventos viram uma mensagem só |

Além disso, cada persona declara a sua **severidade mínima** (o gerente de
crédito só é acionado a partir de "alerta") e a sua **janela de contato**
(o produtor familiar entre 6 h e 19 h). Um alerta crítico ignora a janela de
contato: o custo de esperar supera o incômodo — e o motivo fica registrado
no envio.

## Como alterar as regras

1. Edite `src/agrosentinela/rules/rules.yaml`.
2. Rode `pytest tests/test_regras.py` — a sintaxe é validada no carregamento.
3. Use o **simulador** na página *Motor de Regras* para conferir o efeito.
4. Confira a aba *Disparos da execução*: regras que nunca disparam estão com
   limiar alto demais; regras que disparam sempre, baixo demais.

Nenhuma linha de Python precisa mudar.
