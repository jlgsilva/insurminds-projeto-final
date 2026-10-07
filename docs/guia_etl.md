# Guia do ETL — dos microdados do BCB aos conjuntos curados

## Por que existe um ETL

Os microdados do Sicor somam dezenas de gigabytes. Não cabem no GitHub nem
na memória de um contêiner gratuito do Streamlit Cloud. O ETL roda **fora**
da aplicação — na sua máquina ou no GitHub Actions — e produz conjuntos
curados e compactos, que são os únicos versionados.

```
BCB (dezenas de GB)  ──ETL──▶  data/curated/ (poucos MB)  ──▶  aplicação
```

## Execução completa

```bash
python etl/run_etl.py --anos 2025 2026
```

Etapas, na ordem:

| # | Script | O que faz | Tempo típico |
|---|---|---|---|
| 00 | `00_download_dominios.py` | Baixa as tabelas de domínio | 1–3 min |
| 04 | `04_build_municipios.py` | Geografia + alíquotas do Proagro | < 1 min |
| 01 | `01_download_microdados.py` | Baixa os microdados dos anos escolhidos | 20–90 min |
| 02 | `02_build_carteira.py` | Monta a carteira | 5–25 min |
| 03 | `03_build_proagro.py` | Histórico de COP/RCP + série de crédito | 5–20 min |
| 05 | `05_validate.py` | Valida e grava o manifesto | < 1 min |

Em máquina modesta:

```bash
python etl/run_etl.py --anos 2026 --amostra 150000
```

`--amostra` limita o número de operações por ano **sem alterar a estrutura**
do resultado — a aplicação funciona igual, com menos linhas.

## Particularidades dos arquivos do BCB

Um `read_csv` ingênuo falha. O módulo `etl/_comum.py` trata:

| Particularidade | Tratamento |
|---|---|
| Codificação Latin-1 / CP1252 | Detecção automática, com fallback |
| Delimitador variável (`;` ou `,`) | Sniffing na primeira linha |
| Separador decimal vírgula | `para_numero()` com limpeza de milhar |
| Datas em vários formatos | `para_data()` testa 5 formatos e escolhe o que converte mais |
| Cabeçalhos com acento e caixa variável | `normalizar_coluna()` → `NU_ORDEM` |
| Arquivos de vários GB | Leitura em blocos de 400 mil linhas |
| Integridade | Verificação do `.hash` publicado pelo BCB |

## O elo que georreferencia tudo

`SICOR_OPERACAO_BASICA_ESTADO_AAAA.gz` **não traz o município** — só
`CD_ESTADO`. O município vem de
`SICOR_COMPLEMENTO_OPERACAO_BASICA.gz`, que tem
`REF_BACEN + NU_ORDEM → CD_IBGE_MUNICIPIO`.

Sem esse arquivo o alerta climático é inviável. Por isso ele é baixado
**sempre**, independentemente dos anos escolhidos, e a validação reprova a
base se menos de 50 % das operações tiverem coordenada.

## Centroides municipais

A previsão do tempo precisa de latitude e longitude. O ETL tenta, nesta
ordem:

1. arquivo local `data/raw/municipios_centroides.csv`;
2. base pública consolidada de municípios brasileiros (baixada uma vez e
   guardada localmente);
3. a amostra embarcada no projeto (cobertura parcial).

Para usar uma base própria:

```bash
python etl/04_build_municipios.py --centroides caminho/meus_municipios.csv
```

O CSV precisa ter colunas reconhecíveis de código IBGE, latitude e
longitude. As coordenadas são validadas contra o *bounding box* aproximado
de cada UF, o que detecta erro de junção e de sinal.

## Decodificação do empreendimento

`CD_EMPREENDIMENTO` é o código que diz **o que está sendo financiado**.
`Empreendimento.csv` o decompõe em atividade, modalidade, finalidade,
produto e variedade. O produto é então mapeado para o catálogo fenológico
interno (`mapear_produto_para_cultura`), que define as fases e as
sensibilidades.

Se `Empreendimento.csv` ou `Produto.csv` não forem baixados, a cultura cai
em `OUTRAS` e a validação emite aviso quando isso passa de 40 % da carteira.

## Saída

```
data/curated/
├── municipios.parquet          municipios.csv.gz
├── carteira.parquet            carteira.csv.gz
├── proagro_sinistros.parquet   proagro_sinistros.csv.gz
├── serie_credito.parquet       serie_credito.csv.gz
└── manifesto.json              procedência, contagens, avisos e erros
```

Dois formatos por conjunto: Parquet (rápido e compacto) e `.csv.gz`
(garante leitura em qualquer instalação de pandas, mesmo sem `pyarrow`).

## Validação

```bash
python etl/05_validate.py            # avisos não bloqueiam
python etl/05_validate.py --estrito  # avisos viram erro (uso em CI)
```

Verifica presença e esquema dos conjuntos, cobertura geográfica, coerência
das datas do ciclo, valores negativos, chaves duplicadas, coordenadas fora
da UF, integridade referencial entre carteira e municípios, e proporção de
eventos do Proagro mapeados.

## Automação mensal

O fluxo `.github/workflows/etl-mensal.yml` roda todo dia 5, reconstrói os
conjuntos e abre um pull request com a atualização — a mesma cadência com
que o Banco Central republica os microdados.

## Solução de problemas

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| "colunas ausentes" | O BCB renomeou uma coluna | Rodar com `--espiar` e ajustar o mapa de apelidos |
| Carteira sem coordenada | Falta `SICOR_COMPLEMENTO_OPERACAO_BASICA.gz` | Rebaixar os microdados |
| Cultura quase toda "OUTRAS" | Falta `Empreendimento.csv` ou `Produto.csv` | `python etl/00_download_dominios.py --forcar` |
| Memória insuficiente | Arquivo anual muito grande | Usar `--amostra 100000` |
| Hash divergente | Download interrompido | Rebaixar com `--forcar` |
| Nenhum Proagro cruzou | Carteira cobre anos recentes, COP é antigo | Ampliar `--anos` no ETL 02 |
