# Modelo integrado — como os 166 arquivos do BCB se conversam

> Documento gerado a partir de `src/agrosentinela/data/modelo_integrado.py`.
> O código é a fonte da verdade; este texto é a leitura dele.
> Regenerar com `python scripts/gerar_doc_modelo.py`.

A página *Tabelas e Microdados do Crédito Rural e do Proagro* publica
166 arquivos. A pergunta que separa uma solução real de uma
demonstração é: **como eles se ligam?**

O AgroSentinela consome **164 dos 166** (98.8%).
Os 2 restantes são os arquivos de mutuários,
deliberadamente excluídos por decisão de privacidade — a solução trabalha em
nível de operação, gleba e município, e nunca lê dado pessoal identificável.
A exclusão está registrada no catálogo (`etl_catalogo.nao_usados()`) para que
se veja que foi escolha, não esquecimento.

## Três descobertas que organizam tudo

**1. A chave universal é `(REF_BACEN, NU_ORDEM)`.**
`REF_BACEN` identifica o contrato junto ao Banco Central; `NU_ORDEM` distingue
cada empreendimento dentro dele. Quase todo microdado do Sicor carrega esse
par — é por ele que carteira, Proagro, glebas, saldos e renegociação se
encontram.

**2. A operação básica não tem município.**
`SICOR_OPERACAO_BASICA_ESTADO_AAAA.gz` só traz `CD_ESTADO`. O
`CD_IBGE_MUNICIPIO` mora em `SICOR_COMPLEMENTO_OPERACAO_BASICA.gz`. Sem essa
junção não existe georreferenciamento — e sem georreferenciamento não existe
alerta climático dirigido. É a ligação mais crítica do modelo inteiro.

**3. O Proagro é uma cadeia de quatro etapas, não uma tabela.**
COP (pedido) → RCP (perícia) → Súmula (julgamento) → Parcelas (pagamento).
Medir sinistralidade só pelo COP superestima; só pelo RCP ignora o que foi
negado. O AgroSentinela percorre a cadeia inteira e expõe as taxas separadas:
acionamento, comprovação e deferimento.

## Números do grafo

| Métrica | Valor |
|---|---|
| Entidades (tabelas lógicas) | 36 |
| — de fato | 23 |
| — de domínio | 13 |
| Ligações declaradas | 36 |
| Ligações críticas | 15 |
| Grafo conexo | sim |
| Fontes externas livres | 16 (13 ativas) |

## Ligações críticas

Sem qualquer uma delas, alguma capacidade da solução deixa de existir.

| De | Para | Chave | Para quê |
|---|---|---|---|
| Operação básica (contratada por ano) | Complemento à operação básica | `REF_BACEN + NU_ORDEM` | Traz o CD_IBGE_MUNICIPIO. Sem esta junção a operação fica sem localização e nenhum alerta pode ser dirigido. |
| Complemento à operação básica | Municípios do Sicor | `CD_IBGE_MUNICIPIO` | Nome, UF e centroide do município. |
| Operação básica (contratada por ano) | Glebas em WKT | `REF_BACEN + NU_ORDEM` | Substitui o centroide do município pelo polígono real da lavoura: ganho de precisão de ~50 km para ~1 km na consulta climática. |
| Operação básica (universo contratado) | Complemento à operação básica | `REF_BACEN + NU_ORDEM` | Mesmo papel do complemento, para o universo contratado. |
| Operação básica (contratada por ano) | Empreendimento | `CD_EMPREENDIMENTO` | Cultura, atividade, modalidade e finalidade. |
| Operação básica (contratada por ano) | Tipo de garantia/seguro | `CD_TIPO_SEGURO` | Proagro, Proagro Mais, seguro privado ou sem cobertura — o campo que mais altera o conteúdo da mensagem. |
| Complemento à operação básica | Alíquota básica do Proagro | `CD_IBGE_MUNICIPIO + CD_EMPREENDIMENTO` | Alíquota básica do Proagro — proxy oficial de risco climático daquele município para aquela cultura. |
| Operação básica (contratada por ano) | Proagro — pedido de cobertura (COP) | `REF_BACEN + NU_ORDEM` | Etapa 1: pedidos de cobertura já feitos por esta operação. |
| Proagro — pedido de cobertura (COP) | Proagro — comprovação de perdas (RCP) | `REF_BACEN + NU_ORDEM + NU_COP` | Etapa 2: o que a perícia comprovou. Comparar CD_EVENTO com CD_EVENTO_COMPROVADO mede a acurácia da declaração. |
| Proagro — pedido de cobertura (COP) | Proagro — súmula de julgamento | `REF_BACEN + NU_ORDEM + NU_COP` | Etapa 3: deferido ou indeferido, e em qual instância. Revela a taxa de negativa por evento e por motivo. |
| Proagro — pedido de cobertura (COP) | Evento do Proagro | `CD_EVENTO` | Nome oficial do evento climático. |
| Operação básica (contratada por ano) | Saldos das operações | `REF_BACEN + NU_ORDEM` | Saldo devedor e vencido por posição mensal: converte área em risco em dinheiro em risco. |
| Glebas em WKT | Clima observado e previsto (externo) | `centroide da gleba` | Consulta climática no ponto exato da lavoura. |
| Municípios do Sicor | Clima observado e previsto (externo) | `lat + lon` | Consulta climática no centroide do município quando não há gleba. |
| Municípios do Sicor | Seguro rural (externo) | `CD_IBGE_MUNICIPIO` | Apólices do PSR e sinistralidade do seguro privado, para comparar com a cobertura do Proagro na mesma região. |

## Receita de montagem

A ordem em que o ETL executa as junções.

| # | Passo | Produz | O que faz |
|---|---|---|---|
| 1 | Referência geográfica | `municipios` | Municípios do Sicor + centroides IBGE + alíquota básica do Proagro, enriquecidos com produção agrícola (PAM) e uso do solo. |
| 2 | Carteira georreferenciada | `carteira` | Operações vigentes decodificadas, com município, cultura, datas do ciclo, cobertura e persona. Exclui operações desclassificadas. |
| 3 | Geometria fina | `glebas` | Centroide e área de cada gleba, ligados à operação — substitui o centroide do município na consulta climática quando disponível. |
| 4 | Exposição financeira | `exposicao` | Saldo devedor, saldo vencido, desembolsado e marca de renegociação por operação — e agregado por município. |
| 5 | Cadeia do Proagro | `proagro_sinistros` | Percorre COP → RCP → súmula → parcelas e agrega por município × cultura × evento: taxa de acionamento, taxa de comprovação, taxa de deferimento, perda média e prazo até o pagamento. |
| 6 | Série histórica | `serie_credito` | Contratação anual por UF e cultura desde 2013 (Sicor) com opção de estender a 1983 pelo Recor. |
| 7 | Contexto externo | `contexto_externo` | Normais climáticas, focos de calor, uso do solo, situação hídrica e penetração do seguro rural privado por município. |

## Todas as entidades

| Entidade | Grão | Chave primária | Volume | Usado | Papel |
|---|---|---|---|---|---|
| Operação básica (contratada por ano) | um empreendimento financiado dentro de um contrato | `REF_BACEN + NU_ORDEM` | enorme | sim | Espinha dorsal: valor, área, datas do ciclo, cobertura e alíquota. |
| Complemento à operação básica | um empreendimento financiado | `REF_BACEN + NU_ORDEM` | grande | sim | Única fonte do município — sem ela não há mapa nem alerta dirigido. |
| Operação básica (universo contratado) | um empreendimento financiado | `REF_BACEN + NU_ORDEM` | enorme | sim | Carteira 'viva': inclui operações ainda sem liberação de recursos. |
| Glebas em WKT | uma gleba (polígono) de um empreendimento | `REF_BACEN + NU_ORDEM + NU_GLEBA` | enorme | sim | Geometria real do talhão: permite alerta em nível de gleba, centroide preciso e cruzamento com uso do solo e queimadas. |
| Propriedades | uma propriedade vinculada ao empreendimento | `REF_BACEN + NU_ORDEM + NU_ORDEM_PROPRIEDADE` | grande | sim | Área total, posse e CAR — distingue arrendatário de proprietário e fecha a escala do imóvel (pequeno/médio/grande). |
| Mutuários | um mutuário do contrato | `REF_BACEN + NU_CPF_CNPJ` | grande | — | NÃO utilizado — decisão de privacidade (docs/privacidade.md). A solução trabalha em nível de operação e município. |
| Lista de cooperados | um cooperado dentro de uma operação coletiva | `REF_BACEN + NU_ORDEM + NU_SEQ_COOPERADO` | grande | sim | Explode a operação da cooperativa nos produtores beneficiados — é o que torna a persona 'cooperativa' capaz de rebater o alerta para os associados. |
| Saldos das operações | posição mensal do saldo devedor da operação | `REF_BACEN + NU_ORDEM + DT_POSICAO` | enorme | sim | Exposição financeira corrente e inadimplência — transforma 'área em risco' em 'dinheiro em risco'. |
| Liberação de recursos | uma liberação de parcela | `REF_BACEN + NU_ORDEM + NU_PARCELA` | grande | sim | Quanto do crédito já foi efetivamente desembolsado — capital exposto a perda hoje. |
| Cronograma de desembolso | uma parcela programada | `REF_BACEN + NU_ORDEM + NU_PARCELA` | grande | sim | Calendário de caixa — permite alertar antes do vencimento. |
| Renegociação (lista + operações + complemento) | uma operação renegociada | `REF_BACEN + NU_ORDEM` | grande | sim | Sinal de estresse prévio: município com renegociação recorrente recebe peso extra no escore de risco financeiro. |
| Desclassificação de operações | uma operação desclassificada | `REF_BACEN + NU_ORDEM` | médio | sim | Operações que perderam enquadramento — filtradas da carteira monitorada para não gerar alerta indevido. |
| Alterações de fonte de recursos | uma alteração de fonte | `REF_BACEN + NU_ORDEM + DT_ALTERACAO` | médio | sim | Rastreia trocas de funding que mudam taxa e enquadramento. |
| Proagro — pedido de cobertura (COP) | um pedido de cobertura | `REF_BACEN + NU_ORDEM + NU_COP` | grande | sim | Etapa 1 da cadeia: o produtor declarou perda. Base da **taxa de acionamento** por município × cultura × evento. |
| Proagro — comprovação de perdas (RCP) | um relatório de comprovação de perdas | `REF_BACEN + NU_ORDEM + NU_RCP` | grande | sim | Etapa 2: a perícia confirmou (ou não) o evento. Base da **severidade observada** e do casamento evento declarado × evento comprovado. |
| Glebas do RCP | uma gleba periciada | `REF_BACEN + NU_ORDEM + NU_RCP + NU_GLEBA` | grande | sim | Onde exatamente a perda foi comprovada — o único dado público que georreferencia sinistro em nível de talhão. |
| Proagro — súmula de julgamento | uma decisão de julgamento | `REF_BACEN + NU_ORDEM + NU_COP` | médio | sim | Etapa 3: deferimento, indeferimento e instância. Revela a **taxa de negativa** — informação que muda a comunicação com o produtor (o que documentar para não ter o pedido negado). |
| Proagro — parcelas | uma parcela de cobertura paga | `REF_BACEN + NU_ORDEM + NU_PARCELA` | grande | sim | Etapa 4: valor efetivamente coberto e prazo até o pagamento — a métrica que o produtor de fato quer saber. |
| Recor — operações 1983–2012 | uma operação histórica | `NU_OPERACAO` | enorme | sim | Série longa de 30 anos para contexto climático estrutural. Usada só em gráfico de tendência, com o disclaimer do BCB sobre 1983–1994. |
| Recor — pedidos de cobertura 1983–2012 | um pedido de cobertura histórico | `NU_OPERACAO + NU_COP` | grande | sim | Recorrência histórica de seca/excesso de chuva por UF — permite dizer 'na sua região isso acontece a cada N anos'. |
| Municípios do Sicor | um município | `CD_IBGE_MUNICIPIO` | pequeno | sim | Nome, UF e código IBGE — a ponte para todo dado externo. |
| Empreendimento | um código de empreendimento | `CD_EMPREENDIMENTO` | pequeno | sim | Decodifica o empreendimento em atividade + modalidade + finalidade + produto (a cultura). |
| Programa / linha de crédito | um programa | `CD_PROGRAMA` | pequeno | sim | Pronaf, Pronamp, Moderfrota… define porte, taxa e persona. |
| Fonte de recursos | uma fonte de recursos | `CD_FONTE_RECURSO` | pequeno | sim | Origem do funding — separa recurso controlado de livre. |
| Evento do Proagro | um evento coberto | `CD_EVENTO` | pequeno | sim | Vocabulário oficial (seca, chuva excessiva, granizo, geada…) — casado com o catálogo climático interno. |
| Zoneamento agrícola (Zarc) | um código de zoneamento | `CD_ZONEAMENTO` | pequeno | sim | Aderência ao Zarc — atenuante no escore e argumento central na mensagem ao produtor. |
| Tipo de garantia/seguro | um tipo de cobertura | `CD_TIPO_SEGURO` | pequeno | sim | Proagro, Proagro Mais, seguro privado ou **sem cobertura** — o campo que mais muda o teor da mensagem. |
| Alíquota básica do Proagro | município × empreendimento | `CD_IBGE_MUNICIPIO + CD_EMPREENDIMENTO` | pequeno | sim | Preço do risco segundo o próprio BCB — usado como proxy oficial de risco climático municipal. |
| Instituições financeiras | uma IF | `CNPJ_IF` | pequeno | sim | Nome do banco/cooperativa de crédito — persona institucional. |
| Ciclo do cultivar / fase de produção | um atributo agronômico | `CD_CICLO` | pequeno | sim | Duração do ciclo e manejo — insumo do cálculo da fase fenológica e da sensibilidade ao evento. |
| Status e motivos (COP, parcela, exclusão, rejeição) | um código de situação | `CD_STATUS` | pequeno | sim | Traduz a cadeia do Proagro em linguagem humana e explica por que um pedido foi negado. |
| Categoria de emitente / beneficiário | uma categoria | `CD_CATEG_EMITENTE` | pequeno | sim | Individual, cooperativa, condomínio — derivação direta da persona. |
| Prazos e encargos | atributos contratuais diversos | `CD_PRAZO` | pequeno | sim | Completam a leitura do contrato (prazo, encargo, unidade de medida da produtividade prevista). |
| Clima observado e previsto (externo) | ponto (lat, lon) × dia | `lat + lon + data` | médio | sim | Previsão e histórico climático nos centroides de gleba/município. |
| Território e uso do solo (externo) | município (ou polígono) × ano | `CD_IBGE_MUNICIPIO` | médio | sim | Produção, área plantada, uso do solo, focos de calor e situação hídrica — contexto que o Sicor não tem. |
| Seguro rural (externo) | município × cultura × ano | `CD_IBGE_MUNICIPIO` | médio | sim | Apólices subvencionadas, taxa média e sinistralidade do seguro privado — completa o quadro que o Proagro sozinho não fecha. |

## Todas as ligações

| De | Para | Chave | Cardinalidade | Crítica | Para quê |
|---|---|---|---|---|---|
| Operação básica (contratada por ano) | Complemento à operação básica | `REF_BACEN + NU_ORDEM` | 1:1 | sim | Traz o CD_IBGE_MUNICIPIO. Sem esta junção a operação fica sem localização e nenhum alerta pode ser dirigido. |
| Complemento à operação básica | Municípios do Sicor | `CD_IBGE_MUNICIPIO` | N:1 | sim | Nome, UF e centroide do município. |
| Operação básica (contratada por ano) | Glebas em WKT | `REF_BACEN + NU_ORDEM` | 1:N | sim | Substitui o centroide do município pelo polígono real da lavoura: ganho de precisão de ~50 km para ~1 km na consulta climática. |
| Operação básica (contratada por ano) | Propriedades | `REF_BACEN + NU_ORDEM` | 1:N | — | Área total do imóvel, posse e CAR — define porte e vínculo com a terra. |
| Operação básica (contratada por ano) | Mutuários | `REF_BACEN` | 1:N | — | Ligação existente no modelo do BCB, mas **deliberadamente não materializada** aqui: o AgroSentinela nunca lê dado pessoal. Documentada para que a decisão fique explícita ao avaliador. |
| Operação básica (contratada por ano) | Lista de cooperados | `REF_BACEN + NU_ORDEM` | 1:N | — | Explode a operação coletiva nos produtores associados, permitindo que a cooperativa rebata o alerta individualmente. |
| Operação básica (universo contratado) | Complemento à operação básica | `REF_BACEN + NU_ORDEM` | 1:1 | sim | Mesmo papel do complemento, para o universo contratado. |
| Operação básica (contratada por ano) | Empreendimento | `CD_EMPREENDIMENTO` | N:1 | sim | Cultura, atividade, modalidade e finalidade. |
| Operação básica (contratada por ano) | Programa / linha de crédito | `CD_PROGRAMA` | N:1 | — | Programa de crédito — define porte e tom da comunicação. |
| Operação básica (contratada por ano) | Fonte de recursos | `CD_FONTE_RECURSO` | N:1 | — | Fonte de recursos e taxa aplicável. |
| Operação básica (contratada por ano) | Tipo de garantia/seguro | `CD_TIPO_SEGURO` | N:1 | sim | Proagro, Proagro Mais, seguro privado ou sem cobertura — o campo que mais altera o conteúdo da mensagem. |
| Operação básica (contratada por ano) | Categoria de emitente / beneficiário | `CD_CATEG_EMITENTE` | N:1 | — | Individual, cooperativa ou condomínio — deriva a persona. |
| Operação básica (contratada por ano) | Ciclo do cultivar / fase de produção | `CD_CICLO` | N:1 | — | Duração do ciclo do cultivar, refinando a fase fenológica. |
| Operação básica (contratada por ano) | Zoneamento agrícola (Zarc) | `CD_ZONEAMENTO` | N:1 | — | Aderência ao Zarc: atenua o escore e vira argumento na mensagem. |
| Operação básica (contratada por ano) | Instituições financeiras | `CNPJ_IF` | N:1 | — | Nome da instituição financeira (persona bancária). |
| Operação básica (contratada por ano) | Prazos e encargos | `CD_PRAZO` | N:1 | — | Prazo de vigência e encargos. |
| Complemento à operação básica | Alíquota básica do Proagro | `CD_IBGE_MUNICIPIO + CD_EMPREENDIMENTO` | N:1 | sim | Alíquota básica do Proagro — proxy oficial de risco climático daquele município para aquela cultura. |
| Operação básica (contratada por ano) | Proagro — pedido de cobertura (COP) | `REF_BACEN + NU_ORDEM` | 1:N | sim | Etapa 1: pedidos de cobertura já feitos por esta operação. |
| Proagro — pedido de cobertura (COP) | Proagro — comprovação de perdas (RCP) | `REF_BACEN + NU_ORDEM + NU_COP` | 1:N | sim | Etapa 2: o que a perícia comprovou. Comparar CD_EVENTO com CD_EVENTO_COMPROVADO mede a acurácia da declaração. |
| Proagro — comprovação de perdas (RCP) | Glebas do RCP | `REF_BACEN + NU_ORDEM + NU_RCP` | 1:N | — | Georreferencia a perda comprovada no talhão. |
| Proagro — pedido de cobertura (COP) | Proagro — súmula de julgamento | `REF_BACEN + NU_ORDEM + NU_COP` | 1:N | sim | Etapa 3: deferido ou indeferido, e em qual instância. Revela a taxa de negativa por evento e por motivo. |
| Proagro — pedido de cobertura (COP) | Proagro — parcelas | `REF_BACEN + NU_ORDEM` | 1:N | — | Etapa 4: valor pago e prazo até o pagamento. |
| Proagro — pedido de cobertura (COP) | Evento do Proagro | `CD_EVENTO` | N:1 | sim | Nome oficial do evento climático. |
| Proagro — pedido de cobertura (COP) | Status e motivos (COP, parcela, exclusão, rejeição) | `CD_STATUS_COP` | N:1 | — | Situação do pedido em linguagem humana. |
| Operação básica (contratada por ano) | Saldos das operações | `REF_BACEN + NU_ORDEM` | 1:N | sim | Saldo devedor e vencido por posição mensal: converte área em risco em dinheiro em risco. |
| Operação básica (contratada por ano) | Liberação de recursos | `REF_BACEN + NU_ORDEM` | 1:N | — | Quanto do crédito já foi desembolsado. |
| Operação básica (contratada por ano) | Cronograma de desembolso | `REF_BACEN + NU_ORDEM` | 1:N | — | Calendário de desembolso e vencimento. |
| Operação básica (contratada por ano) | Renegociação (lista + operações + complemento) | `REF_BACEN + NU_ORDEM` | 1:1 | — | Marca a operação já renegociada — estresse prévio conhecido. |
| Operação básica (contratada por ano) | Desclassificação de operações | `REF_BACEN + NU_ORDEM` | 1:1 | — | Remove da carteira monitorada o que perdeu enquadramento, evitando alerta indevido. |
| Operação básica (contratada por ano) | Alterações de fonte de recursos | `REF_BACEN + NU_ORDEM` | 1:N | — | Histórico de troca de funding. |
| Recor — operações 1983–2012 | Recor — pedidos de cobertura 1983–2012 | `NU_OPERACAO` | 1:N | — | Série histórica 1983–2012 de acionamento por evento e UF. |
| Recor — pedidos de cobertura 1983–2012 | Evento do Proagro | `CD_EVENTO` | N:1 | — | Compatibiliza o vocabulário antigo do Recor com o do Sicor. |
| Glebas em WKT | Clima observado e previsto (externo) | `centroide da gleba` | N:1 | sim | Consulta climática no ponto exato da lavoura. |
| Municípios do Sicor | Clima observado e previsto (externo) | `lat + lon` | N:1 | sim | Consulta climática no centroide do município quando não há gleba. |
| Municípios do Sicor | Território e uso do solo (externo) | `CD_IBGE_MUNICIPIO` | 1:N | — | Produção agrícola municipal (IBGE/PAM), uso do solo (MapBiomas), focos de calor (INPE) e situação hídrica (ANA). |
| Municípios do Sicor | Seguro rural (externo) | `CD_IBGE_MUNICIPIO` | 1:N | sim | Apólices do PSR e sinistralidade do seguro privado, para comparar com a cobertura do Proagro na mesma região. |

## Diagrama

```mermaid
graph LR
  subgraph Núcleo_da_carteira["Núcleo da carteira"]
    operacao["Operação básica (contratada por ano)"]
    operacao_contratada["Operação básica (universo contratado)"]
    complemento["Complemento à operação básica"]
    glebas["Glebas em WKT"]
    propriedades["Propriedades"]
    cooperados["Lista de cooperados"]
    mutuarios["Mutuários ✖"]
  end
  subgraph Cadeia_do_Proagro["Cadeia do Proagro"]
    cop["Proagro — pedido de cobertura (COP)"]
    rcp["Proagro — comprovação de perdas (RCP)"]
    rcp_glebas["Glebas do RCP"]
    sumula["Proagro — súmula de julgamento"]
    parcelas_proagro["Proagro — parcelas"]
  end
  subgraph Financeiro["Financeiro"]
    saldos["Saldos das operações"]
    liberacao["Liberação de recursos"]
    parcelas_desembolso["Cronograma de desembolso"]
    renegociacao["Renegociação (lista + operações + complemento)"]
    desclassificacao["Desclassificação de operações"]
    alteracao_fonte["Alterações de fonte de recursos"]
  end
  subgraph Histórico_(Recor)["Histórico (Recor)"]
    recor_operacao["Recor — operações 1983–2012"]
    recor_cop["Recor — pedidos de cobertura 1983–2012"]
  end
  subgraph Tabelas_de_domínio["Tabelas de domínio"]
    d_municipios["Municípios do Sicor"]
    d_empreendimento["Empreendimento"]
    d_programa["Programa / linha de crédito"]
    d_fonte["Fonte de recursos"]
    d_evento["Evento do Proagro"]
    d_zoneamento["Zoneamento agrícola (Zarc)"]
    d_seguro["Tipo de garantia/seguro"]
    d_aliquota["Alíquota básica do Proagro"]
    d_ifs["Instituições financeiras"]
    d_ciclo["Ciclo do cultivar / fase de produção"]
    d_status["Status e motivos (COP, parcela, exclusão, rejeição)"]
    d_emitente["Categoria de emitente / beneficiário"]
    d_prazos["Prazos e encargos"]
  end
  subgraph Fontes_externas_livres["Fontes externas livres"]
    ext_clima["Clima observado e previsto (externo)"]
    ext_territorio["Território e uso do solo (externo)"]
    ext_seguro["Seguro rural (externo)"]
  end
  operacao ==>|REF_BACEN + NU_ORDEM| complemento
  complemento ==>|CD_IBGE_MUNICIPIO| d_municipios
  operacao ==>|REF_BACEN + NU_ORDEM| glebas
  operacao_contratada ==>|REF_BACEN + NU_ORDEM| complemento
  operacao ==>|CD_EMPREENDIMENTO| d_empreendimento
  operacao ==>|CD_TIPO_SEGURO| d_seguro
  complemento ==>|CD_IBGE_MUNICIPIO + CD_EMPREENDIMENTO| d_aliquota
  operacao ==>|REF_BACEN + NU_ORDEM| cop
  cop ==>|REF_BACEN + NU_ORDEM + NU_COP| rcp
  cop ==>|REF_BACEN + NU_ORDEM + NU_COP| sumula
  cop ==>|CD_EVENTO| d_evento
  operacao ==>|REF_BACEN + NU_ORDEM| saldos
  glebas ==>|centroide da gleba| ext_clima
  d_municipios ==>|lat + lon| ext_clima
  d_municipios ==>|CD_IBGE_MUNICIPIO| ext_seguro
```

> Acima, apenas as ligações críticas, para legibilidade. O grafo completo sai de `modelo_integrado.mermaid()` e é desenhado na página *Documentação* do aplicativo.

## Fontes externas

Todas gratuitas, públicas e livres; nenhuma exige cadastro.

| Fonte | Órgão | Categoria | Licença | Liga por | Papel |
|---|---|---|---|---|---|
| Open-Meteo — previsão e reanálise ERA5 | Open-Meteo (open data, ECMWF/DWD/NOAA) | clima | CC BY 4.0 — uso não comercial livre e sem chave | lat/lon do centroide (célula de grade ~11 km) | Previsão de 16 dias e histórico diário no centroide da gleba ou do município. É a fonte que dispara o alerta. |
| NASA POWER — agroclimatologia | NASA Langley Research Center | clima | Domínio público (NASA open data) — sem chave | lat/lon do centroide | Normais climáticas de 1981 em diante no mesmo ponto. É o que transforma '80 mm de chuva' em '80 mm, o triplo da média histórica desta semana aqui' — o número que dá contexto à mensagem e evita alarme falso. |
| INMET — estações automáticas e BDMEP | Instituto Nacional de Meteorologia | clima | Dados abertos (Lei 12.527/2011) — API pública sem chave | estação mais próxima do centroide (raio configurável) | Observação de superfície em estação real, usada para conferir a previsão (skill check) e como evidência em perícia. |
| Agritempo — monitoramento agrometeorológico | Embrapa Informática Agropecuária / Unicamp | clima | Dados abertos governamentais | código IBGE | Boletins agrometeorológicos e balanço hídrico por município, em linguagem já agronômica. |
| CEMADEN — pluviômetros automáticos e alertas | Centro Nacional de Monitoramento e Alertas de Desastres Naturais | monitoramento | Dados abertos (Ministério da Ciência e Tecnologia) | código IBGE do município | Chuva acumulada medida em solo e alertas oficiais de desastre. Quando o CEMADEN já emitiu alerta para o município, o AgroSentinela **cita o alerta oficial** em vez de criar um aviso concorrente — evita ruído e aumenta a credibilidade. |
| Programa Queimadas — focos de calor | INPE | monitoramento | Dados abertos — CSV diário de acesso livre | código IBGE / ponto (lat,lon) dentro da gleba | Focos de calor por município nas últimas 24h/7d/30d. Fogo é evento coberto pelo Proagro e é o risco mais subnotificado em pastagem e cana. Também identifica queima de resteva vizinha que ameaça a lavoura segurada. |
| Atlas do Seguro Rural / SISSER — apólices do PSR | Ministério da Agricultura e Pecuária (MAPA) | seguro | Dados abertos — dados.gov.br, uso livre com citação | código IBGE + cultura + ano-safra | Apólices subvencionadas, área segurada, prêmio, taxa média e indenizações por município × cultura × ano. É o **outro lado da cobertura**: permite dizer se um município está de fato descoberto ou apenas protegido por seguro privado em vez do Proagro — e é a base do argumento comercial das personas de seguradora e corretora. |
| SUSEP — dados abertos do mercado segurador | Superintendência de Seguros Privados | seguro | Dados abertos — uso livre | UF + ramo (agrupamento 'rural') + mês | Prêmios emitidos e sinistros retidos do ramo rural por empresa e UF. Dá a sinistralidade de mercado com que o atuário e a área de subscrição comparam a carteira própria. |
| IBGE SIDRA — Produção Agrícola Municipal (PAM) | Instituto Brasileiro de Geografia e Estatística | produção | Dados abertos — API SIDRA pública, sem chave | código IBGE + produto (mapeado para a cultura interna) | Área plantada, quantidade produzida e rendimento médio por município e cultura. É o **denominador** de tudo: converte 'área financiada' em 'percentual da lavoura do município', e permite estimar a perda em toneladas e em reais. |
| IBGE SIDRA — Pesquisa da Pecuária Municipal (PPM) | IBGE | produção | Dados abertos — API SIDRA pública | código IBGE + espécie | Rebanho por município e espécie — denominador das operações de bovinocultura, que hoje são um ponto cego do alerta climático agrícola. |
| CONAB — safras, custos e preços mínimos | Companhia Nacional de Abastecimento | produção | Dados abertos — uso livre com citação | UF + produto + safra | Preço mínimo e preço de mercado por produto e UF, e custos de produção. Converte perda física em perda financeira usando preço oficial, não estimativa — diferença que importa ao banco e à seguradora. |
| IBGE — malhas territoriais e localidades | IBGE | território | Dados abertos — API de serviços pública, sem chave | código IBGE | Geometria e centroide oficial de cada município — base de todos os mapas e o ponto usado quando não há gleba. |
| MapBiomas — uso e cobertura do solo | Rede MapBiomas | território | CC BY-SA 4.0 — uso livre com atribuição | código IBGE + ano | Área de lavoura, pastagem e vegetação nativa por município e ano. Mostra se a expansão do crédito está indo para área já consolidada ou para fronteira — leitura essencial para política pública e para subscrição com critério socioambiental. |
| Zarc — Zoneamento Agrícola de Risco Climático | MAPA / Embrapa (Zarc Plantio Certo) | território | Dados abertos — portarias e API pública do Plantio Certo | código IBGE + cultura + tipo de solo + ciclo | Janela de plantio recomendada por município, cultura, tipo de solo e ciclo, com o nível de risco (20%, 30%, 40%). Duas aplicações: (a) atenua o escore de quem plantou dentro da janela; (b) explica ao produtor **por que** o risco daquela data é maior — argumento que o Sicor sozinho não fornece. |
| ANA — HidroWeb / Sala de Situação | Agência Nacional de Águas e Saneamento Básico | hídrico | Dados abertos — série histórica pública | estação da bacia mais próxima do município | Nível e vazão de rios e situação de reservatórios. Em lavoura irrigada, a restrição de outorga chega **antes** da seca agronômica: é o alerta mais antecipado disponível. |
| Monitor de Secas do Brasil | ANA / FUNCEME / INMET e parceiros estaduais | hídrico | Dados abertos — mapas mensais públicos | código IBGE | Classificação oficial de severidade de seca (S0 a S4) por município. Quando existe, o AgroSentinela **usa a classificação oficial** em vez da própria — alinhamento que importa para laudo de Proagro e para política pública. |
