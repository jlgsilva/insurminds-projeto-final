# Prompt para gerar mais apólices simuladas (para usar em outra IA)

Como usar:

1. Copie **todo o bloco entre as linhas `=====`** e cole numa IA que execute
   código e devolva arquivos (ChatGPT com análise de dados, Claude com
   ferramentas de arquivo, Gemini com execução de código). Se a IA não
   executar código, ela vai entregar o script Python; rode-o você mesmo
   (`pip install reportlab` e `python gerar_lote.py`).
2. Peça **um lote por vez** (ex.: "lote 1: seguradoras A e B, 20 apólices
   cada"). Lotes grandes estouram o limite de saída das IAs.
3. Importe cada lote no app:
   ```bash
   python scripts/importar_apolices_externas.py --pasta caminho/do/lote
   python scripts/processar_acervo.py          # reconstrói a base inicial
   ```
   O importador recusa o lote inteiro se o gabarito estiver inconsistente
   (código de cláusula inválido, nível fora do vocabulário, seguradora real,
   arquivo faltando) e diz o que corrigir.

=====================================================================

Você vai gerar um lote de APÓLICES DE SEGURO D&O (Responsabilidade Civil de
Administradores e Diretores) SIMULADAS, em PDF, para um dataset acadêmico de
avaliação de extração automática por IA. O foco é o AGRONEGÓCIO BRASILEIRO.
Cada PDF vem acompanhado de um GABARITO estruturado (JSON) que descreve
exatamente o que está escrito nele.

## 1. Regras inegociáveis

1. Tudo é FICTÍCIO. Não use nome, marca, logotipo, CNPJ, número de processo
   SUSEP ou texto literal de nenhuma seguradora real (ex.: AIG, Allianz,
   Tokio Marine, Sompo, Chubb, Zurich, Mapfre, Porto, Bradesco, Itaú,
   SulAmérica, Liberty/Yelum, Fairfax, AXA, Swiss Re, Berkley, Junto, BB/
   Brasilseg, Caixa, HDI, Austral, Pottencial, Ezze, Excelsior, Newe, Sancor,
   Essor). Nem de cooperativas ou empresas reais (ex.: Coamo, Cooxupé, Sicredi,
   Sicoob, Cresol, Castrolanda, Frísia, C.Vale, Lar, JBS, Marfrig, Raízen).
   Invente nomes e acrescente " (fictícia)" ao nome de TODA seguradora e
   tomadora. CNPJs devem ser claramente falsos (ex.: 00.000.2NN/0001-NN).
2. Todo PDF deve ter, visível em todas as páginas: marca d'água diagonal
   "SIMULADA · USO ACADÊMICO" (desenhada como IMAGEM, para não poluir a
   camada de texto) e rodapé "DOCUMENTO SIMULADO — InsurMinds/I2A2 — não é
   apólice real". Na primeira página, este aviso exato:
   "DOCUMENTO SIMULADO PARA FINS ACADÊMICOS (InsurMinds/I2A2). Seguradora,
   tomadora, CNPJ, valores e pessoas são fictícios. Não constitui oferta,
   apólice ou condição contratual de nenhuma seguradora real."
3. Você pode se INSPIRAR na estrutura de condições gerais públicas de D&O
   registradas na SUSEP, mas escreva o texto com suas próprias palavras.
4. Português do Brasil. No máximo uma seguradora do lote pode usar wording
   bilíngue (inglês/português), como no mercado de Londres.

## 2. Diversidade de SEGURADORAS (o mais importante)

No mundo real, apólices de seguradoras diferentes NÃO seguem o mesmo modelo.
Cada seguradora fictícia do lote deve ter uma ARQUITETURA DE DOCUMENTO
própria, diferente das outras em pelo menos 5 destes eixos:

- Onde ficam os dados (limite, prêmio, franquia, vigência): tabela no
  início; lista numerada; parágrafo corrido (preâmbulo); "Especificação" no
  FIM do documento; quadro-resumo em linguagem simples; "Policy Schedule"
  com Item 1…9.
- Numeração: "CLÁUSULA 4 –"; "Cláusula 4ª –"; "4.2.1"; algarismos romanos
  "IV –"; alíneas "a)"; "Art. 4º"; perguntas ("Até quanto o seguro paga?").
- Organização das exclusões: uma cláusula por exclusão; todas numa lista com
  alíneas; exclusões em CAIXA ALTA; "Riscos não cobertos e prejuízos não
  indenizáveis".
- Vocabulário: Tomadora / Tomador / Sociedade / Empresa / Named Insured;
  Segurado / Pessoa Segurada / dirigente segurado; LMG / LMI / Limit of
  Liability; franquia / POS / participação obrigatória / Retention; custos de
  defesa / gastos com defesa / Defence Costs; prazo adicional / prazo
  complementar e suplementar; Cobertura A / Garantia A / Side A.
- Formato de valores: "R$ 5.000.000,00"; "R$ 5 milhões"; "R$ 1,5 milhão";
  "R$ 5.000.000,00 (cinco milhões de reais)"; "BRL 5,000,000.00".
- Formato de datas: 01/07/2026; 01.07.2026; 2026-07-01; "1º de julho de 2026".
- Identidade visual: fonte (Helvetica, Times, Courier), cor, cabeçalho
  (faixa, moldura, logotipo textual), tabelas com ou sem grade.
- Seções opcionais: glossário/definições; "informações do risco"; ouvidoria;
  endossos ou "cláusulas particulares rurais" no final.

Dentro de uma mesma seguradora, mantenha a arquitetura, mas varie: ordem de
algumas cláusulas, presença de seções opcionais, redação de 2–3 cláusulas
(versões diferentes de wording) e tamanho do documento (2 a 5 páginas).

Traços de documentos REAIS que vale reproduzir (observados em condições
gerais públicas de D&O de 50 a 100 páginas — imite a estrutura, nunca o texto):

- SUMÁRIO no início, com linhas pontilhadas e número de página
  ("4. EXCLUSÕES ........ 12"); cabeçalho e rodapé repetidos em toda página
  com o nome da seguradora, um "Processo SUSEP" FICTÍCIO (ex.: 00000.000000/
  2026-00) e "Página N de M".
- Glossário longo (30 a 60 definições) ANTES das coberturas, com termos que
  também nomeiam coberturas ("Multa", "Custos de Defesa") — a definição não é
  cobertura.
- Coberturas opcionais em "Condições Especiais" / "Coberturas Adicionais" no
  fim, contratadas mediante prêmio adicional, cada uma com suas próprias
  exclusões; "Cláusulas Particulares" que alteram as gerais.
- Exclusões com exceções embutidas ("esta exclusão não se aplica a…") e
  parágrafos inteiros em CAIXA ALTA.
- Em 1 de cada 10 apólices, inclua no fim as "Condições Gerais" completas
  (documento de 15 a 30 páginas), para exercitar a leitura de documentos longos.

## 3. Diversidade de TOMADORAS — os vários Brasis rurais

Distribua as tomadoras por TODAS as regiões e por vários estados; nenhuma UF
com mais de 15% das apólices do lote. Misture perfis:

| Perfil | Exemplos de tomadora (D&O protege os DIRIGENTES de pessoas jurídicas) | Faixa de LMG |
|---|---|---|
| Agricultura familiar | cooperativa ou associação de agricultores familiares, de assentados da reforma agrária, de extrativistas, de pescadores artesanais, de quilombolas | R$ 0,5–3 mi |
| Pequeno | agroindústria familiar (queijo, cachaça, mel, polpa), cooperativa pequena, laticínio regional | R$ 1–6 mi |
| Médio | produtor PJ / holding familiar enquadrado no Pronamp, fruticultura irrigada média | R$ 3–15 mi |
| Grande | grupo agrícola de grãos, algodão, citros, café; exportadores | R$ 10–80 mi |
| Latifúndio / grande extensão | pecuária extensiva, grandes fazendas de grãos em fronteira agrícola | R$ 10–60 mi |
| Cooperativa de crédito rural | singular ou central, com repasse de Pronaf/Pronamp | R$ 5–50 mi |
| Cooperativa agroindustrial | grãos, leite, aves/suínos, café | R$ 15–100 mi |
| Agroindústria | usina, frigorífico, esmagadora, integradora | R$ 20–150 mi |
| Cadeia | trading, revenda de insumos, armazém, securitizadora de CPR/CRA | R$ 10–120 mi |

Cada apólice deve trazer um bloco "informações do risco" coerente com o
território e o perfil (atividade, porte em cooperados/hectares/carteira,
município/UF, particularidades). Exemplos de particularidades reais:

- Norte / Amazônia Legal: embargos do Ibama, CAR, rastreabilidade de gado e
  açaí, Moratória da Soja, logística fluvial, reservas extrativistas.
- Nordeste / semiárido: estiagem, Garantia-Safra, Proagro Mais, perímetros
  irrigados do São Francisco, exportação de frutas, compras públicas
  (PAA/PNAE), cana na Zona da Mata.
- Matopiba (MA, TO, PI, BA): fronteira agrícola, disputas fundiárias, outorga
  de água para pivôs.
- Centro-Oeste: grãos e pecuária em escala, Pantanal (queimadas, cheias),
  CPR e barter, pivôs em bacias críticas.
- Sudeste: café (geada, seca), citros (greening), cana (incêndios),
  agroindústria familiar com indicação geográfica.
- Sul: cooperativismo forte, integração de aves/suínos/fumo, estiagem no
  Oeste, enchentes de 2024 no RS, granizo e geada.

Prefira municípios e perfis diferentes destes, que já existem no dataset:
Cametá-PA, Xapuri-AC, Cacoal-RO, Marabá-PA, Boa Vista-RR, Rio Preto da Eva-AM,
Lagoa da Confusão-TO, Mazagão-AP, Picos-PI, Juazeiro do Norte-CE, Petrolina-PE,
Sertânia-PE, São Miguel dos Campos-AL, Luís Eduardo Magalhães-BA, Ilhéus-BA,
Balsas-MA, Lago do Junco-MA, Mossoró-RN, Itabaiana-SE, Campina Grande-PB,
Sorriso-MT, Corumbá-MS, Rio Verde-GO, Jataí-GO, Cristalina-GO, Chapadão do
Sul-MS, Sinop-MT, Brazlândia-DF, Três Pontas-MG, Serro-MG, Assis-SP,
Ribeirão Preto-SP, Bebedouro-SP, São Gabriel da Palha-ES, Unaí-MG, São Paulo-SP,
Cascavel-PR, Chapecó-SC, Santa Cruz do Sul-RS, Uruguaiana-RS, Palmeira-PR,
Bento Gonçalves-RS, Toledo-PR, Canoinhas-SC, Torres-RS. (O Rio de Janeiro
ainda não tem nenhuma tomadora.)

Cada tomadora deve receber de 2 a 4 cotações de seguradoras DIFERENTES do
lote, para permitir comparação.

## 4. Coerência (o gabarito precisa fazer sentido)

- Cooperativa/associação familiar: sem Cobertura C (valores mobiliários),
  cobertura territorial restrita ao Brasil, franquia de R$ 0 a 50 mil, prêmio
  mínimo em torno de R$ 3,5 mil.
- Cobertura C só para quem tem valores mobiliários emitidos (S.A. aberta,
  debêntures, CRA).
- Quem exporta ou tem investidor estrangeiro: cobertura mundial mais comum.
- Amazônia Legal e latifúndio: seguradoras generalistas tendem a EXCLUIR risco
  ambiental; seguradoras especializadas em agro oferecem defesa ambiental com
  sublimite.
- Quem concede, repassa ou intermedia crédito rural: a cláusula de atos de
  gestão em crédito rural/Proagro (AGR-01) é relevante; algumas seguradoras a
  excluem como "atividade financeira".
- Prêmio entre 0,5% e 3% do LMG, maior para capital aberto, crédito rural,
  Amazônia Legal e porte muito pequeno.
- Retroatividade "ilimitada" ou uma data anterior ao início da vigência.
- Vigência de 12 meses começando entre jul/2026 e jun/2027.

## 5. Taxonomia de cláusulas (use EXATAMENTE estes códigos no gabarito)

Para CADA apólice, classifique as 32 cláusulas abaixo com um destes níveis:

- "ampla": protege integralmente, sem condicionantes relevantes (para
  exclusões: exclusão estreita, favorável ao segurado);
- "padrao": nos termos usuais de mercado;
- "restrita": com sublimite, condição, carência, painel de advogados,
  franquia incidente ou redação desfavorável relevante;
- "excluida": o documento trata do tema PARA EXCLUIR a proteção;
- "ausente": o tema NÃO aparece no documento.

| Código | Cláusula |
|---|---|
| ESC-01 | Definição de segurado (quem é protegido) |
| ESC-02 | Side A — administrador não indenizado pela empresa |
| ESC-03 | Side B — reembolso à companhia |
| ESC-04 | Side C — cobertura da pessoa jurídica (valores mobiliários) |
| ESC-05 | Âmbito geográfico e jurisdicional |
| ESC-06 | Cobertura de subsidiárias e controladas |
| LIM-01 | Limite Máximo de Garantia (LMG) |
| LIM-02 | Sublimites por cobertura |
| LIM-03 | Reintegração do limite |
| LIM-04 | Franquia / participação obrigatória |
| DEF-01 | Custos de defesa dentro ou fora do LMG |
| DEF-02 | Adiantamento de custos de defesa |
| DEF-03 | Livre escolha do advogado |
| DEF-04 | Separabilidade (severability) |
| DEF-05 | Multas e penalidades administrativas |
| TMP-01 | Retroatividade |
| TMP-02 | Prazo adicional (antigo complementar/suplementar) |
| TMP-03 | Notificação de circunstâncias |
| TMP-04 | Run-off em mudança de controle |
| EXC-01 | Conduta dolosa e ato fraudulento |
| EXC-02 | Reclamações entre segurados |
| EXC-03 | Danos ambientais e poluição |
| EXC-04 | Cibernético e vazamento de dados |
| EXC-05 | Fatos conhecidos e anteriores |
| OPE-01 | Cancelamento e rescisão |
| OPE-02 | Arbitragem e foro |
| OPE-03 | Sub-rogação contra segurados |
| OPE-04 | Ordem de pagamento das coberturas (prioridade do Side A) |
| OPE-05 | Idioma, moeda e correção do limite |
| AGR-01 | Atos de gestão em crédito rural e Proagro (BCB/MAPA, MCR, Sicor) |
| AGR-02 | Responsabilidade ambiental do administrador rural (defesa) |
| AGR-03 | Recuperação judicial e insolvência no agro |

Regras de presença: ESC-01, ESC-02, LIM-01, LIM-04, TMP-01 e EXC-01 aparecem
em toda apólice. Entre 15% e 35% das demais devem ficar "ausente". Use
"excluida" com moderação (só EXC-*, DEF-05, AGR-01, AGR-03 e equivalentes).
O texto de cada cláusula deve permitir que um especialista chegue ao MESMO
nível do gabarito — se o gabarito diz "restrita", o texto tem de mostrar a
restrição (sublimite, condição, exclusão parcial).

## 6. Entregáveis do lote

1. Um PDF por apólice, nome `EXTnnn-SSS-TTT.pdf` (nnn = sequencial de 3
   dígitos no lote; SSS = código de 3 letras da seguradora; TTT = código da
   tomadora, ex. X01). Opcional: em ~10% das apólices, gerar também uma versão
   "digitalizada" (páginas como imagem, leve inclinação e ruído) com nome
   `EXTnnn-SSS-TTT_digitalizada.pdf` NO LUGAR do PDF de texto.
2. Um arquivo `gabarito_externo.json`: lista de objetos, um por apólice, com
   EXATAMENTE estas chaves:

```json
{
  "identificador": "EXT001-CAA-X01",
  "numero_apolice": "CAA-0042-2026",
  "seguradora_codigo": "CAA",
  "seguradora": "Carnaúba Seguros Gerais S.A. (fictícia)",
  "seguradora_cnpj": "00.000.201/0001-10",
  "modelo_documento": "descreva a arquitetura em 3-6 palavras",
  "tomadora_codigo": "X01",
  "tomadora": "Cooperativa dos Assentados do Vale do Jaguaribe (fictícia)",
  "tomadora_cnpj": "00.000.301/0001-55",
  "segmento": "Cooperativa de assentados da reforma agrária",
  "perfil": "familiar",
  "municipio": "Limoeiro do Norte",
  "uf": "CE",
  "regiao": "Nordeste",
  "lmg": 1500000.0,
  "premio": 21450.0,
  "franquia": 25000.0,
  "sub_multas": 150000.0,
  "vigencia_inicio": "2026-09-01",
  "vigencia_fim": "2027-09-01",
  "retroatividade": "2024-03-01",
  "retroatividade_ilimitada": false,
  "dias_adiantamento": 45,
  "anos_prazo_adicional": 2,
  "avaliacoes": {"ESC-01": "padrao", "ESC-02": "restrita", "...": "...  (as 32 chaves)"},
  "formato": "pdf",
  "arquivos": ["EXT001-CAA-X01.pdf"]
}
```

`perfil` ∈ {familiar, pequeno, medio, grande, latifundio, cooperativa_credito,
cooperativa_agroindustrial, agroindustria, cadeia}; `regiao` ∈ {Norte,
Nordeste, Centro-Oeste, Sudeste, Sul}; `formato` ∈ {pdf, pdf_digitalizado};
`retroatividade` = null quando `retroatividade_ilimitada` = true.
Os valores numéricos do gabarito devem ser EXATAMENTE os que aparecem no PDF.

3. Um `LEIA-ME.md` do lote: seguradoras criadas e a arquitetura de cada uma,
   tabela de tomadoras (perfil, município/UF) e distribuição por região.

## 7. Como produzir (se você executa código)

Escreva um script Python com `reportlab` que: (a) define as seguradoras do lote,
cada uma com uma FUNÇÃO DE MONTAGEM própria (não um único template com
variáveis); (b) define as tomadoras; (c) sorteia, com semente fixa, os níveis das
32 cláusulas respeitando a seção 4; (d) escreve o texto de cada cláusula a
partir do nível; (e) gera PDFs e o JSON a partir das MESMAS estruturas (para o
gabarito nunca divergir do texto); (f) valida no final que toda cláusula com
nível ≠ "ausente" aparece no PDF e vice-versa. Rode o script, confira 3 PDFs
abrindo-os e devolva um ZIP com PDFs + gabarito_externo.json + LEIA-ME.md +
o próprio script.

Se você NÃO executa código, entregue apenas o script completo e as instruções
para rodá-lo.

## 8. Este lote

<<< PREENCHA: ex. "Lote 1: 2 seguradoras novas (uma nacional generalista,
uma especializada em agro do Nordeste), 20 apólices cada, para tomadoras do
Nordeste e do Norte, incluindo pelo menos 1 cooperativa de assentados, 1
associação de pescadores artesanais e 1 agroindústria familiar de cachaça;
códigos de seguradora CAA e BUR; códigos de tomadora X01–X15." >>>

=====================================================================
