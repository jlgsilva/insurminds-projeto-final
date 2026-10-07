# Apólices D&O SIMULADAS

DOCUMENTO SIMULADO PARA FINS ACADÊMICOS (InsurMinds/I2A2). Seguradora, tomadora, CNPJ, valores e pessoas são fictícios. Não constitui oferta, apólice ou condição contratual de nenhuma seguradora real.

**120 apólices**, 6 seguradoras fictícias (cada uma com arquitetura de documento própria), 45 tomadoras fictícias em 26 unidades da federação e nas 5 regiões.

| Seguradora (fictícia) | Modelo de documento | Apólices | Inspiração estrutural |
|---|---|---|---|
| Atalaia Linhas Financeiras S.A. (fictícia) | `decimal_glossario` | 20 | estrutura decimal com glossário e extensões numeradas (C.G. públicas de D&O da AIG) |
| Ipê-Roxo Seguradora S.A. (fictícia) | `clausulas_romanos` | 20 | cláusulas com extensões e exclusões em romanos, exclusões em caixa alta, POS (C.G. públicas de D&O da Allianz) |
| Jacarandá Companhia de Seguros (fictícia) | `hierarquico_legado` | 20 | numeração hierárquica 1.1.1, especificação ao final e prazo complementar/suplementar (C.G. públicas de D&O da Tokio Marine, versões até 2021) |
| Xique-Xique Seguros Gerais S.A. (fictícia) | `ordinal_prosa` | 20 | "Cláusula 1ª, 2ª…", coberturas básicas e adicionais e glossário (C.G. públicas de D&O da Sompo) |
| Mutirão Seguros Mútuos (fictícia) | `linguagem_simples` | 20 | linguagem simples em perguntas e respostas, voltada a cooperativas e associações (sem paralelo direto; inspirado em guias de seguro cooperativo) |
| Minuano Specialty Seguros S.A. (fictícia) | `schedule_bilingue` | 20 | "Policy Schedule" com itens numerados e endossos, típico do mercado de Londres |

As inspirações referem-se apenas à *organização* de condições gerais públicas de D&O registradas na SUSEP; nenhum texto foi copiado.

## Distribuição

| regiao       |   apólices |
|:-------------|-----------:|
| Centro-Oeste |         23 |
| Nordeste     |         33 |
| Norte        |         20 |
| Sudeste      |         20 |
| Sul          |         24 |

| perfil                     |   apólices |
|:---------------------------|-----------:|
| agroindustria              |         10 |
| cadeia                     |          9 |
| cooperativa_agroindustrial |         11 |
| cooperativa_credito        |         10 |
| familiar                   |         28 |
| grande                     |         19 |
| latifundio                 |          8 |
| medio                      |          7 |
| pequeno                    |         18 |

| formato          |   apólices |
|:-----------------|-----------:|
| imagem           |          4 |
| pdf              |        104 |
| pdf_digitalizado |         12 |

Gerado por `scripts/gerar_apolices_simuladas.py`. `gabarito.json` é a verdade de referência para medir a extração.
