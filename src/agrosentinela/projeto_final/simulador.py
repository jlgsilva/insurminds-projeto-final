"""
Simulador de apólices de D&O do agronegócio brasileiro.

POR QUE SIMULAR
---------------
Apólices de D&O emitidas são contratos privados: o que é público são as
*Condições Gerais* que cada seguradora registra na SUSEP — sem prêmio, limite
nem condições negociadas, que é o que se compara numa cotação. Para exercitar
o pipeline e medir a extração, o projeto gera um acervo **declaradamente
simulado**, com gabarito.

O QUE TORNA O ACERVO REALISTA
-----------------------------
1. **Cada seguradora tem a sua própria arquitetura de documento**, como no
   mercado real. Os seis modelos foram inspirados na *estrutura* de condições
   gerais públicas de D&O (não no texto):

   ====  ===============================  ===================================
   cód.  seguradora (fictícia)            arquitetura (inspiração estrutural)
   ====  ===============================  ===================================
   ATA   Atalaia Linhas Financeiras       decimal com glossário, "Garantia A/B",
                                          extensões 4.x, exclusões 6.x (estilo AIG)
   IPE   Ipê-Roxo Seguradora              cláusulas com itens em romanos,
                                          exclusões em CAIXA ALTA, "POS" (Allianz)
   JAC   Jacarandá Cia. de Seguros        hierárquico 2.1.1, especificação no
                                          FIM, prazo complementar/suplementar
                                          (wording legado, estilo Tokio Marine)
   XIQ   Xique-Xique Seguros Gerais       "Cláusula 1ª, 2ª…", abertura em prosa,
                                          cláusulas particulares rurais (Sompo)
   MUT   Mutirão Seguros Mútuos           linguagem simples, perguntas e
                                          respostas, foco em cooperativas
   MIN   Minuano Specialty          "Policy Schedule" bilíngue, Item 1…9,
                                          valores em BRL 1,000.00 (mercado de
                                          Londres)
   ====  ===============================  ===================================

2. **Cada seguradora fala o seu dialeto**: "Tomadora", "Sociedade",
   "Empresa", "Tomador", "Named Insured"; "custos de defesa", "gastos com
   defesa", "Defence Costs"; "LMG" ou "LMI"; valores como "R$ 5.000.000,00",
   "R$ 5 milhões", "R$ 5.000.000,00 (cinco milhões de reais)" ou
   "BRL 5,000,000.00"; datas como "01/07/2026", "1º de julho de 2026",
   "01.07.2026" ou "2026-07-01".

3. **O Brasil rural é diverso.** 45 tomadoras em 25 UFs e no DF, das cinco
   regiões, em nove perfis — da associação de quebradeiras de coco babaçu no
   Maranhão ao latifúndio de pecuária no Pantanal, da cooperativa de crédito
   solidário do Oeste catarinense à trading de Sorriso-MT. O perfil e o
   território mudam limite, prêmio e as cláusulas que fazem sentido
   (ex.: em fronteira agrícola da Amazônia Legal, seguradoras generalistas
   tendem a excluir risco ambiental; cooperativa familiar raramente tem
   Side C ou cobertura no exterior).

Nada aqui existe: seguradoras, tomadoras, CNPJs, valores e pessoas são
fictícios, e todo documento traz marca d'água e aviso de simulação.
"""

from __future__ import annotations

import random
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Any

from .clausulas import CLAUSULAS
from .redacao_base import NIVEIS_EXCLUIVEIS, TEXTOS, TITULOS

AVISO_SIMULACAO = (
    "DOCUMENTO SIMULADO PARA FINS ACADÊMICOS (InsurMinds/I2A2). Seguradora, "
    "tomadora, CNPJ, valores e pessoas são fictícios. Não constitui oferta, "
    "apólice ou condição contratual de nenhuma seguradora real."
)

APOLICES_POR_SEGURADORA = 20

UF_AMAZONIA_LEGAL = {"AC", "AM", "AP", "PA", "RO", "RR", "TO", "MT", "MA"}
UF_SEMIARIDO = {"PI", "CE", "RN", "PB", "PE", "AL", "SE", "BA"}
REGIAO = {
    **dict.fromkeys(["AC", "AM", "AP", "PA", "RO", "RR", "TO"], "Norte"),
    **dict.fromkeys(["MA", "PI", "CE", "RN", "PB", "PE", "AL", "SE", "BA"], "Nordeste"),
    **dict.fromkeys(["MT", "MS", "GO", "DF"], "Centro-Oeste"),
    **dict.fromkeys(["MG", "ES", "RJ", "SP"], "Sudeste"),
    **dict.fromkeys(["PR", "SC", "RS"], "Sul"),
}

# ==========================================================================
# Seguradoras fictícias
# ==========================================================================


@dataclass(frozen=True)
class SeguradoraFicticia:
    codigo: str
    nome: str
    cnpj: str
    modelo: str                 # arquitetura do documento (modelos_documento.py)
    generosidade: float         # tendência de redação favorável ao segurado
    vies: dict[str, float]      # ajuste por grupo de cláusula (prefixo)
    taxa_base: float            # % do LMG
    termo_segurado: str
    termo_tomadora: str
    formato_valor: str          # br | br_extenso | milhoes | brl_en
    formato_data: str           # br | extenso | ponto | iso
    fonte: str                  # Helvetica | Times | Courier
    cor: str
    afinidade: dict[str, float]  # apetite por perfil de tomadora
    especialista_agro: bool
    inspiracao: str


SEGURADORAS: tuple[SeguradoraFicticia, ...] = (
    SeguradoraFicticia(
        "ATA", "Atalaia Linhas Financeiras S.A. (fictícia)", "00.000.101/0001-10",
        "decimal_glossario", 0.80, {"DEF": .12, "AGR": -.25, "ESC": .08}, 1.30,
        "Pessoa Segurada", "Sociedade", "br", "br", "Helvetica", "#12355B",
        {"grande": 1.8, "agroindustria": 2.0, "cadeia": 2.0, "cooperativa_agroindustrial": 1.4,
         "latifundio": 1.2, "cooperativa_credito": 1.0, "medio": 0.8, "pequeno": 0.3,
         "familiar": 0.15}, False,
        "estrutura decimal com glossário e extensões numeradas (C.G. públicas de D&O da AIG)"),
    SeguradoraFicticia(
        "IPE", "Ipê-Roxo Seguradora S.A. (fictícia)", "00.000.102/0001-00",
        "clausulas_romanos", 0.62, {"LIM": -.1, "OPE": .1}, 1.05,
        "Segurado", "Empresa", "br_extenso", "extenso", "Times", "#6A1B4D",
        {"medio": 1.5, "grande": 1.3, "cooperativa_agroindustrial": 1.2, "agroindustria": 1.1,
         "latifundio": 1.1, "cadeia": 1.0, "cooperativa_credito": 1.0, "pequeno": 0.9,
         "familiar": 0.6}, False,
        "cláusulas com extensões e exclusões em romanos, exclusões em caixa alta, POS "
        "(C.G. públicas de D&O da Allianz)"),
    SeguradoraFicticia(
        "JAC", "Jacarandá Companhia de Seguros (fictícia)", "00.000.103/0001-91",
        "hierarquico_legado", 0.55, {"TMP": -.15, "EXC": .05, "AGR": .1}, 0.95,
        "Segurado", "Tomador", "br", "ponto", "Times", "#2E4A2E",
        {"cooperativa_agroindustrial": 1.8, "cooperativa_credito": 1.8, "medio": 1.4,
         "agroindustria": 1.0, "grande": 0.9, "pequeno": 0.9, "latifundio": 0.8,
         "familiar": 0.7, "cadeia": 0.8}, False,
        "numeração hierárquica 1.1.1, especificação ao final e prazo "
        "complementar/suplementar (C.G. públicas de D&O da Tokio Marine, versões até 2021)"),
    SeguradoraFicticia(
        "XIQ", "Xique-Xique Seguros Gerais S.A. (fictícia)", "00.000.104/0001-82",
        "ordinal_prosa", 0.66, {"AGR": .3, "EXC": -.05}, 1.10,
        "Segurado", "Tomadora", "milhoes", "br", "Helvetica", "#8A4B08",
        {"familiar": 1.4, "pequeno": 1.5, "medio": 1.5, "latifundio": 1.4, "grande": 1.0,
         "cooperativa_credito": 1.0, "cooperativa_agroindustrial": 0.9, "agroindustria": 0.7,
         "cadeia": 0.6}, True,
        "\"Cláusula 1ª, 2ª…\", coberturas básicas e adicionais e glossário "
        "(C.G. públicas de D&O da Sompo)"),
    SeguradoraFicticia(
        "MUT", "Mutirão Seguros Mútuos (fictícia)", "00.000.105/0001-73",
        "linguagem_simples", 0.58, {"AGR": .25, "ESC": -.1, "OPE": -.2}, 0.85,
        "dirigente segurado", "cooperativa", "milhoes", "extenso", "Helvetica", "#1B6E3C",
        {"familiar": 3.0, "pequeno": 2.2, "cooperativa_credito": 1.8,
         "cooperativa_agroindustrial": 1.0, "medio": 0.6, "grande": 0.15, "latifundio": 0.15,
         "agroindustria": 0.2, "cadeia": 0.1}, True,
        "linguagem simples em perguntas e respostas, voltada a cooperativas e "
        "associações (sem paralelo direto; inspirado em guias de seguro cooperativo)"),
    SeguradoraFicticia(
        "MIN", "Minuano Specialty Seguros S.A. (fictícia)", "00.000.106/0001-64",
        "schedule_bilingue", 0.85, {"ESC": .12, "AGR": -.1, "LIM": .08}, 1.55,
        "Insured Person (Segurado)", "Companhia Tomadora", "brl_en", "iso", "Courier",
        "#0B3954",
        {"grande": 2.2, "latifundio": 1.8, "agroindustria": 2.0, "cadeia": 2.0,
         "cooperativa_agroindustrial": 0.9, "medio": 0.6, "cooperativa_credito": 0.5,
         "pequeno": 0.1, "familiar": 0.05}, False,
        "\"Policy Schedule\" com itens numerados e endossos, típico do mercado de Londres"),
)
SEGURADORAS_POR_CODIGO = {s.codigo: s for s in SEGURADORAS}


# ==========================================================================
# Tomadoras fictícias — os vários Brasis rurais
# ==========================================================================


@dataclass(frozen=True)
class TomadoraFicticia:
    codigo: str
    razao_social: str
    segmento: str
    perfil: str           # familiar | pequeno | medio | grande | latifundio | cooperativa_credito
                          # | cooperativa_agroindustrial | agroindustria | cadeia
    municipio: str
    uf: str
    atividade: str        # culturas / criações
    escala: str           # cooperados, área, carteira…
    receita_mi: float
    capital_aberto: bool
    opera_credito_rural: bool
    exterior: bool
    contexto: str         # particularidade regional relevante para o risco

    @property
    def regiao(self) -> str:
        return REGIAO[self.uf]

    @property
    def amazonia_legal(self) -> bool:
        return self.uf in UF_AMAZONIA_LEGAL

    @property
    def semiarido(self) -> bool:
        return self.uf in UF_SEMIARIDO


def _t(c, r, seg, perf, mun, uf, ativ, esc, rec, aberto=False, credito=False, ext=False, ctx=""):
    return TomadoraFicticia(c, r, seg, perf, mun, uf, ativ, esc, rec, aberto, credito, ext, ctx)


TOMADORAS: tuple[TomadoraFicticia, ...] = (
    # ------------------------------------------------------------ Norte
    _t("T01", "Cooperativa Agroextrativista do Baixo Tocantins (fictícia)", "Cooperativa de agricultura familiar",
       "familiar", "Cametá", "PA", "açaí, cacau e mandioca", "860 cooperados, 92% enquadrados no Pronaf", 38,
       credito=True, ctx="várzea amazônica; crédito Pronaf via banco regional; exigência de rastreabilidade do açaí"),
    _t("T02", "Associação dos Produtores de Castanha do Alto Acre (fictícia)", "Associação extrativista",
       "familiar", "Xapuri", "AC", "castanha-do-brasil e borracha", "310 famílias associadas em reserva extrativista", 6,
       ctx="reserva extrativista; dependência de política de preço mínimo (PGPM-Bio)"),
    _t("T03", "Cooperativa dos Cafeicultores do Robusta Amazônico (fictícia)", "Cooperativa de café",
       "pequeno", "Cacoal", "RO", "café robusta (conilon) clonal", "1.100 cooperados, área média de 8 ha", 64,
       credito=True, ctx="Amazônia Legal; produtores indígenas e familiares; certificação de origem"),
    _t("T04", "Agropecuária Vale do Araguaia S.A. (fictícia)", "Pecuária de corte extensiva",
       "latifundio", "Marabá", "PA", "cria, recria e engorda de bovinos", "48 mil hectares em 3 fazendas", 210,
       ctx="sudeste do Pará: embargos ambientais, conflitos fundiários e rastreabilidade de gado"),
    _t("T05", "Grupo Lavrado Grãos Ltda. (fictícia)", "Produção de grãos",
       "grande", "Boa Vista", "RR", "soja e milho no lavrado", "22 mil hectares", 180,
       ctx="fronteira agrícola recente; logística via Venezuela/Manaus; licenciamento estadual"),
    _t("T06", "Cooperativa Mista dos Piscicultores do Amazonas (fictícia)", "Cooperativa de piscicultura",
       "pequeno", "Rio Preto da Eva", "AM", "tambaqui e matrinxã em viveiros", "140 cooperados", 12,
       ctx="outorga de uso de água e licença ambiental de viveiros"),
    _t("T07", "Tocantins Bioenergia e Grãos S.A. (fictícia)", "Grãos e arroz irrigado de várzea",
       "grande", "Lagoa da Confusão", "TO", "soja e arroz irrigado por subirrigação", "35 mil hectares", 420,
       ctx="várzea do Javaés: conflitos por captação de água em estiagem"),
    _t("T08", "Cooperativa Agroextrativista do Amapá (fictícia)", "Cooperativa de agricultura familiar",
       "familiar", "Mazagão", "AP", "açaí, mandioca e pesca artesanal", "190 cooperados", 4,
       credito=True, ctx="acesso fluvial; Pronaf B; baixa formalização dos cooperados"),
    # ------------------------------------------------------------ Nordeste
    _t("T09", "Cooperativa dos Apicultores do Sertão do Piauí (fictícia)", "Cooperativa apícola",
       "familiar", "Picos", "PI", "mel e própolis", "520 apicultores familiares", 22,
       ext=True, ctx="semiárido; exportação de mel orgânico; seca recorrente"),
    _t("T10", "Cooperativa da Agricultura Familiar do Cariri (fictícia)", "Cooperativa de agricultura familiar",
       "familiar", "Juazeiro do Norte", "CE", "milho, feijão de sequeiro e caju", "980 cooperados, adesão ao Garantia-Safra", 15,
       credito=True, ctx="semiárido; Garantia-Safra e Proagro Mais; perdas por estiagem"),
    _t("T11", "Vale do São Francisco Fruticultura Exportadora Ltda. (fictícia)", "Fruticultura irrigada",
       "grande", "Petrolina", "PE", "manga e uva de mesa irrigadas", "2.900 hectares irrigados", 520,
       ext=True, ctx="perímetro irrigado; exportação para UE/EUA; trabalho sazonal intensivo"),
    _t("T12", "Cooperativa dos Caprinocultores do Sertão Pernambucano (fictícia)", "Cooperativa de caprinos e ovinos",
       "familiar", "Sertânia", "PE", "leite de cabra e carne ovina", "340 cooperados", 9,
       credito=True, ctx="semiárido; compras públicas (PAA/PNAE) como principal canal"),
    _t("T13", "Usina Zona da Mata Alagoana Açúcar e Etanol S.A. (fictícia)", "Usina sucroenergética",
       "agroindustria", "São Miguel dos Campos", "AL", "cana-de-açúcar, açúcar e etanol", "fornecedores de cana em 14 municípios", 780,
       ctx="passivo trabalhista histórico; queima de palha; endividamento setorial"),
    _t("T14", "Algodoeira Chapadão do Oeste Baiano S.A. (fictícia)", "Algodão e soja",
       "grande", "Luís Eduardo Magalhães", "BA", "algodão, soja e milho", "68 mil hectares", 1900,
       ext=True, ctx="Matopiba; outorga de água para pivôs; exportação de pluma"),
    _t("T15", "Cooperativa Cacaueira do Sul da Bahia (fictícia)", "Cooperativa de cacau",
       "pequeno", "Ilhéus", "BA", "cacau cabruca e chocolate de origem", "640 cooperados", 41,
       credito=True, ext=True, ctx="Mata Atlântica; renegociação de dívidas da vassoura-de-bruxa"),
    _t("T16", "Agropecuária Matopiba Holding S.A. (fictícia)", "Grãos em larga escala",
       "latifundio", "Balsas", "MA", "soja, milho e algodão", "95 mil hectares", 3600,
       ext=True, ctx="Matopiba/Amazônia Legal: abertura de área, CAR e disputas fundiárias"),
    _t("T17", "Associação das Quebradeiras de Coco Babaçu do Mearim (fictícia)", "Associação extrativista",
       "familiar", "Lago do Junco", "MA", "amêndoa e óleo de babaçu", "210 associadas", 3,
       ctx="lei do babaçu livre; conflito de acesso a babaçuais em áreas privadas"),
    _t("T18", "Fazendas Reunidas do Vale do Açu Ltda. (fictícia)", "Fruticultura irrigada",
       "medio", "Mossoró", "RN", "melão e melancia para exportação", "1.400 hectares", 140,
       ext=True, ctx="semiárido; dependência de poços e de janela de exportação"),
    _t("T19", "Cooperativa de Crédito Rural do Agreste Sergipano (fictícia)", "Cooperativa de crédito rural",
       "cooperativa_credito", "Itabaiana", "SE", "crédito rural Pronaf e Pronamp", "7.800 associados, carteira de R$ 120 milhões", 120,
       credito=True, ctx="repasse de crédito rural com equalização; fiscalização do BCB"),
    _t("T20", "Laticínios Agreste Paraibano Ltda. (fictícia)", "Laticínio regional",
       "pequeno", "Campina Grande", "PB", "leite, queijo coalho e manteiga", "compra de 210 produtores", 28,
       ctx="vigilância sanitária e inspeção estadual; seca afeta oferta de leite"),
    # ------------------------------------------------------------ Centro-Oeste
    _t("T21", "Grão Norte Trading de Commodities Ltda. (fictícia)", "Trading de grãos",
       "cadeia", "Sorriso", "MT", "originação e exportação de soja e milho", "1,8 milhão de toneladas/ano", 9200,
       credito=True, ext=True, ctx="CPR e barter com produtores; Moratória da Soja; rastreabilidade EUDR"),
    _t("T22", "Agropecuária Pantanal Sul S.A. (fictícia)", "Pecuária extensiva no Pantanal",
       "latifundio", "Corumbá", "MS", "cria e recria de bovinos", "72 mil hectares", 160,
       ctx="Pantanal: queimadas, áreas de preservação e cheias sazonais"),
    _t("T23", "Frigorífico Boi do Cerrado S.A. (fictícia)", "Frigorífico",
       "agroindustria", "Rio Verde", "GO", "abate e exportação de carne bovina", "3 plantas, 4.200 empregados", 5400,
       aberto=True, ext=True, ctx="rastreabilidade de fornecedores indiretos; inspeção federal (SIF)"),
    _t("T24", "Cooperativa Agroindustrial do Sudoeste Goiano (fictícia)", "Cooperativa agroindustrial",
       "cooperativa_agroindustrial", "Jataí", "GO", "grãos, armazenagem e insumos", "2.400 cooperados", 3900,
       credito=True, ctx="repasse de crédito e venda de insumos a prazo; armazéns em 9 municípios"),
    _t("T25", "Bertoldo Agricultura Irrigada Ltda. (fictícia)", "Horticultura e grãos irrigados",
       "medio", "Cristalina", "GO", "feijão, batata e alho sob pivô", "3.200 hectares, 41 pivôs", 85,
       ctx="maior concentração de pivôs do país; outorga de água em bacia crítica"),
    _t("T26", "AgroInsumos Chapadão Comércio Ltda. (fictícia)", "Revenda de insumos",
       "cadeia", "Chapadão do Sul", "MS", "defensivos, sementes e fertilizantes", "3.100 clientes produtores", 780,
       credito=True, ctx="venda a prazo safra e CPR; inadimplência após quebra de safra"),
    _t("T27", "Sinop Florestal e Grãos S.A. (fictícia)", "Grãos e silvicultura",
       "grande", "Sinop", "MT", "soja, milho e teca", "41 mil hectares", 640,
       ext=True, ctx="norte de MT, bioma Amazônia: Moratória da Soja e embargos"),
    _t("T28", "Cooperativa da Agricultura Familiar do DF e Entorno (fictícia)", "Cooperativa de hortifrúti",
       "familiar", "Brasília (Brazlândia)", "DF", "hortaliças e morango", "420 cooperados", 18,
       credito=True, ctx="compras públicas (PNAE); feiras e entregas diretas"),
    # ------------------------------------------------------------ Sudeste
    _t("T29", "Cooperativa dos Cafeicultores de Três Pontas (fictícia)", "Cooperativa de café",
       "cooperativa_agroindustrial", "Três Pontas", "MG", "café arábica, armazenagem e exportação", "7.500 cooperados", 6200,
       credito=True, ext=True, ctx="geada e seca no Sul de Minas; certificações internacionais"),
    _t("T30", "Queijaria Familiar Serra do Serro Ltda. (fictícia)", "Agroindústria familiar",
       "pequeno", "Serro", "MG", "queijo minas artesanal", "produção própria e de 12 vizinhos", 4,
       ctx="queijo artesanal com selo de indicação geográfica; inspeção sanitária"),
    _t("T31", "Cooperativa de Crédito Rural do Vale do Paranapanema (fictícia)", "Cooperativa de crédito rural",
       "cooperativa_credito", "Assis", "SP", "crédito rural e custeio", "18 mil associados, carteira de R$ 420 milhões", 420,
       credito=True, ctx="crédito rural com recursos obrigatórios; Proagro; supervisão do BCB"),
    _t("T32", "Usina Serra Dourada Açúcar e Bioenergia S.A. (fictícia)", "Usina sucroenergética",
       "agroindustria", "Ribeirão Preto", "SP", "cana, açúcar, etanol e bioeletricidade", "fornecedores em 22 municípios", 3100,
       aberto=True, ext=True, ctx="debêntures em mercado; incêndios em canaviais"),
    _t("T33", "Citrus Paulista Agrícola Ltda. (fictícia)", "Citricultura",
       "grande", "Bebedouro", "SP", "laranja para suco", "9 mil hectares", 860,
       ext=True, ctx="greening; contratos com indústria exportadora de suco"),
    _t("T34", "Cooperativa dos Produtores de Conilon do Norte Capixaba (fictícia)", "Cooperativa de café",
       "pequeno", "São Gabriel da Palha", "ES", "café conilon", "2.100 cooperados, maioria familiar", 310,
       credito=True, ctx="irrigação e crise hídrica; Pronaf"),
    _t("T35", "Fazenda Santa Helena Agropecuária Ltda. (fictícia)", "Grãos e pecuária",
       "medio", "Unaí", "MG", "soja, milho, feijão irrigado e gado", "6.500 hectares", 120,
       ctx="Noroeste de MG: irrigação no Cerrado e Pronamp"),
    _t("T36", "CPRtech Securitizadora do Agronegócio S.A. (fictícia)", "Securitizadora de CPR e CRA",
       "cadeia", "São Paulo", "SP", "securitização de CPR e emissão de CRA", "carteira de R$ 1,2 bilhão", 160,
       aberto=True, credito=True, ctx="regulação CVM; risco de crédito de produtores"),
    # ------------------------------------------------------------ Sul
    _t("T37", "Cooperativa Agroindustrial Planalto Oeste (fictícia)", "Cooperativa agroindustrial",
       "cooperativa_agroindustrial", "Cascavel", "PR", "grãos, aves e suínos", "6.800 cooperados", 6800,
       credito=True, ext=True, ctx="integração avícola; exportação; estiagem no Oeste do PR"),
    _t("T38", "Central Solidária Oeste Catarinense de Crédito Rural (fictícia)", "Cooperativa central de crédito solidário",
       "cooperativa_credito", "Chapecó", "SC", "crédito rural para agricultura familiar", "carteira de R$ 950 milhões, 41 singulares", 950,
       credito=True, ctx="agricultura familiar; Pronaf; supervisão do BCB sobre a central"),
    _t("T39", "Cooperativa Fumageira e de Diversificação do Vale do Rio Pardo (fictícia)", "Cooperativa de fumo e diversificação",
       "familiar", "Santa Cruz do Sul", "RS", "tabaco integrado, milho e leite", "3.200 cooperados", 210,
       credito=True, ctx="sistema integrado com indústria; trabalho familiar; granizo"),
    _t("T40", "Arrozeira Fronteira Oeste Ltda. (fictícia)", "Arroz irrigado",
       "grande", "Uruguaiana", "RS", "arroz irrigado e pecuária", "14 mil hectares", 480,
       ext=True, ctx="outorga de água no Uruguai; enchentes de 2024 no RS"),
    _t("T41", "Cooperativa Leiteira dos Campos Gerais (fictícia)", "Cooperativa agroindustrial de leite",
       "cooperativa_agroindustrial", "Palmeira", "PR", "leite e derivados", "1.100 cooperados", 1200,
       credito=True, ctx="laticínio próprio; preço do leite e estiagem"),
    _t("T42", "Sucos Serra Gaúcha Agroindústria Familiar Ltda. (fictícia)", "Agroindústria familiar de sucos",
       "pequeno", "Bento Gonçalves", "RS", "uva e suco integral", "60 hectares + 35 fornecedores familiares", 14,
       ctx="granizo e geada; inspeção de bebidas (MAPA)"),
    _t("T43", "Avícola Integração Oeste Paranaense S.A. (fictícia)", "Agroindústria de aves",
       "agroindustria", "Toledo", "PR", "frango integrado e exportação", "900 integrados", 2300,
       ext=True, ctx="contratos de integração; influenza aviária; mercado externo"),
    _t("T44", "Erva-Mate Planalto Norte Ltda. (fictícia)", "Ervateira",
       "pequeno", "Canoinhas", "SC", "erva-mate sombreada", "compra de 400 produtores familiares", 36,
       ctx="Mata Atlântica; extração em sub-bosque"),
    _t("T45", "Associação de Agricultores Agroecológicos do Litoral Norte (fictícia)", "Associação agroecológica",
       "familiar", "Torres", "RS", "hortifrúti orgânico e banana", "95 famílias", 2,
       ctx="certificação participativa; enchentes de 2024"),
)
TOMADORAS_POR_CODIGO = {t.codigo: t for t in TOMADORAS}

PERFIS_ROTULO = {
    "familiar": "Agricultura familiar", "pequeno": "Pequeno produtor / agroindústria",
    "medio": "Médio produtor", "grande": "Grande produtor",
    "latifundio": "Latifúndio / grande extensão", "cooperativa_credito": "Cooperativa de crédito rural",
    "cooperativa_agroindustrial": "Cooperativa agroindustrial", "agroindustria": "Agroindústria",
    "cadeia": "Cadeia (trading, insumos, securitização)",
}

# Faixa de LMG (R$ milhões) por perfil — coerente com o porte
FAIXA_LMG = {
    "familiar": (0.5, 3), "pequeno": (1, 6), "medio": (3, 15), "grande": (10, 80),
    "latifundio": (10, 60), "cooperativa_credito": (5, 50),
    "cooperativa_agroindustrial": (15, 100), "agroindustria": (20, 150), "cadeia": (10, 120),
}
AJUSTE_PERFIL = {  # generosidade: estruturas maiores negociam wording melhor
    "familiar": -0.15, "pequeno": -0.10, "medio": -0.03, "grande": 0.06, "latifundio": 0.0,
    "cooperativa_credito": 0.0, "cooperativa_agroindustrial": 0.04, "agroindustria": 0.06,
    "cadeia": 0.05,
}


# ==========================================================================
# Formatos de valor e data (o "dialeto" numérico de cada seguradora)
# ==========================================================================

_UNID = ["", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez",
         "onze", "doze", "treze", "quatorze", "quinze", "dezesseis", "dezessete", "dezoito",
         "dezenove"]
_DEZ = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta",
        "noventa"]
_CEM = ["", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos", "seiscentos",
        "setecentos", "oitocentos", "novecentos"]


def _ate_999(n: int) -> str:
    if n == 100:
        return "cem"
    partes = []
    c, r = divmod(n, 100)
    if c:
        partes.append(_CEM[c])
    if r < 20:
        if r:
            partes.append(_UNID[r])
    else:
        d, u = divmod(r, 10)
        partes.append(_DEZ[d] + (f" e {_UNID[u]}" if u else ""))
    return " e ".join(partes)


def por_extenso(valor: float) -> str:
    """Inteiros até bilhões, em reais. Ex.: 5.250.000 → 'cinco milhões, duzentos e cinquenta mil reais'."""
    n = int(round(valor))
    if n == 0:
        return "zero reais"
    blocos = []
    for div, sing, plur in ((1_000_000_000, "bilhão", "bilhões"), (1_000_000, "milhão", "milhões"),
                            (1_000, "mil", "mil")):
        q, n = divmod(n, div)
        if q:
            txt = "mil" if (div == 1_000 and q == 1) else f"{_ate_999(q)} {sing if q == 1 else plur}"
            blocos.append(txt)
    if n:
        blocos.append(_ate_999(n))
    texto = ", ".join(blocos[:-1]) + (" e " if len(blocos) > 1 else "") + blocos[-1] \
        if len(blocos) > 1 else blocos[0]
    sufixo = " de reais" if valor >= 1_000_000 and int(valor) % 1_000_000 == 0 else " reais"
    return texto + sufixo


def formatar_valor(v: float, estilo: str) -> str:
    br = "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if estilo == "br_extenso":
        return f"{br} ({por_extenso(v)})"
    if estilo == "milhoes":
        if v >= 1_000_000:
            m = v / 1_000_000
            txt = f"{m:,.1f}".replace(".", ",") if m % 1 else f"{int(m)}"
            return f"R$ {txt} {'milhão' if m < 2 else 'milhões'}"
        if v >= 1_000 and v % 1_000 == 0:
            return f"R$ {int(v / 1000)} mil"
        return br
    if estilo == "brl_en":
        return f"BRL {v:,.2f}"
    return br


_MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
          "setembro", "outubro", "novembro", "dezembro"]


def formatar_data(d: date | None, estilo: str) -> str:
    if d is None:
        return ""
    if estilo == "extenso":
        dia = "1º" if d.day == 1 else str(d.day)
        return f"{dia} de {_MESES[d.month - 1]} de {d.year}"
    if estilo == "ponto":
        return d.strftime("%d.%m.%Y")
    if estilo == "iso":
        return d.isoformat()
    return d.strftime("%d/%m/%Y")


# ==========================================================================
# Dialetos de vocabulário
# ==========================================================================

DIALETOS: dict[str, list[tuple[str, str]]] = {
    "ATA": [("Tomadora", "Sociedade"), ("Cobertura A", "Garantia A"), ("Cobertura B", "Garantia B"),
            ("Cobertura C", "Garantia C"), ("Coberturas A", "Garantias A"),
            ("Coberturas B e C", "Garantias B e C"), ("custos de defesa", "Custos de Defesa"),
            ("perdas", "Perdas Indenizáveis"), ("reclamações", "Reclamações"),
            ("reclamação", "Reclamação"), ("quadro-resumo", "Especificação")],
    "IPE": [("Tomadora", "Empresa"), ("custos de defesa", "gastos com defesa"),
            ("Cobertura A", "Cobertura de Pagamento ao Segurado (A)"),
            ("Coberturas A", "Coberturas de Pagamento ao Segurado (A)"),
            ("Cobertura B", "Cobertura de Reembolso da Empresa (B)"),
            ("Coberturas B e C", "Coberturas de Reembolso (B) e de Valores Mobiliários (C)"),
            ("Cobertura C", "Cobertura de Valores Mobiliários (C)"),
            ("franquia", "franquia (POS)"), ("quadro-resumo", "Condições Particulares")],
    "JAC": [("Tomadora", "Tomador"), ("Limite Máximo de Garantia", "Limite Máximo de Indenização"),
            ("LMG", "LMI"), ("Cobertura A", "Cobertura Básica nº 1"),
            ("Coberturas A", "Coberturas Básicas nº 1"), ("Coberturas B e C", "Coberturas Básicas nº 2 e nº 3"),
            ("Cobertura B", "Cobertura Básica nº 2"), ("Cobertura C", "Cobertura Básica nº 3"),
            ("quadro-resumo", "Especificação da Apólice")],
    "XIQ": [("Cobertura A", "Cobertura Básica A"), ("Cobertura B", "Cobertura Básica B"),
            ("Cobertura C", "Cobertura Básica C"), ("custos de defesa", "Custos de Defesa"),
            ("franquia", "participação obrigatória do Segurado (franquia)"),
            ("quadro-resumo", "preâmbulo desta apólice")],
    "MUT": [("A Seguradora", "A Mutirão"), ("a Seguradora", "a Mutirão"), ("Tomadora", "cooperativa"),
            ("Limite Máximo de Garantia", "valor máximo do seguro (LMG)"),
            ("custos de defesa", "despesas com advogados e processos (custos de defesa)"),
            ("Cobertura A", "proteção do dirigente (Cobertura A)"),
            ("Coberturas A", "proteções do dirigente (Coberturas A)"),
            ("Coberturas B e C", "Coberturas B e C"),
            ("Cobertura B", "reembolso à cooperativa (Cobertura B)"),
            ("quadro-resumo", "resumo do seu seguro")],
    "MIN": [("Tomadora", "Companhia Tomadora"),
            ("Limite Máximo de Garantia", "Limit of Liability (Limite Máximo de Garantia)"),
            ("custos de defesa", "Defence Costs (custos de defesa)"),
            ("Cobertura A", "Side A"), ("Coberturas A", "Side A"),
            ("Coberturas B e C", "Sides B and C"), ("Cobertura B", "Side B"),
            ("Cobertura C", "Side C"), ("franquia", "Retention (franquia)"),
            ("quadro-resumo", "Policy Schedule")],
}

# Redações próprias de algumas seguradoras (além da troca de vocabulário)
TEXTOS_PROPRIOS: dict[str, dict[str, dict[str, str]]] = {
    "JAC": {"TMP-02": {
        "ampla": "Na hipótese de não renovação, fica concedido Prazo Complementar de 12 meses, sem cobrança de prêmio, e facultada a contratação de Prazo Suplementar de até {anos_prazo} anos.",
        "padrao": "Na hipótese de não renovação, fica concedido Prazo Complementar de 6 meses, sem custo, e facultada a contratação de Prazo Suplementar de até {anos_prazo} anos, mediante prêmio adicional.",
        "restrita": "Aplica-se exclusivamente o Prazo Complementar mínimo previsto na regulamentação, não sendo oferecido Prazo Suplementar.",
    }},
    "MUT": {"DEF-02": {
        "ampla": "Sim. Pagamos as despesas com advogados em até {dias_adiant} dias depois de recebermos os documentos, mesmo antes de concluir a análise do caso. Só pedimos o dinheiro de volta se, ao final, ficar provado em decisão definitiva que o caso não estava coberto.",
        "padrao": "Sim, em até {dias_adiant} dias, depois que aprovarmos o orçamento do advogado.",
        "restrita": "Não há adiantamento. As despesas são reembolsadas ao final do processo, com os comprovantes, salvo decisão da Mutirão em sentido contrário.",
    }},
}

# Seguradoras especialistas oferecem as coberturas agro com mais frequência
PERFIS_FAMILIARES = {"familiar", "pequeno"}


@dataclass
class EspecApolice:
    """O gabarito: tudo o que a extração deveria recuperar do documento."""

    identificador: str
    numero_apolice: str
    seguradora_codigo: str
    seguradora: str
    seguradora_cnpj: str
    modelo_documento: str
    tomadora_codigo: str
    tomadora: str
    tomadora_cnpj: str
    segmento: str
    perfil: str
    municipio: str
    uf: str
    regiao: str
    lmg: float
    premio: float
    franquia: float
    sub_multas: float
    vigencia_inicio: date
    vigencia_fim: date
    retroatividade: date | None
    retroatividade_ilimitada: bool
    dias_adiantamento: int
    anos_prazo_adicional: int
    avaliacoes: dict[str, str] = field(default_factory=dict)
    formato: str = "pdf"            # pdf | pdf_digitalizado | imagem
    estilo_titulo: int = 0
    semente: int = 0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for k in ("vigencia_inicio", "vigencia_fim", "retroatividade"):
            d[k] = d[k].isoformat() if d[k] else None
        return d


def _cnpj(rng: random.Random, base: str) -> str:
    return f"{base}.{rng.randint(100, 999)}.{rng.randint(100, 999)}/0001-{rng.randint(10, 99)}"


def _sortear_nivel(rng: random.Random, g: float, codigo: str) -> str:
    g = max(0.05, min(0.97, g))
    u = rng.random()
    p_ampla = 0.55 * g
    p_padrao = p_ampla + 0.35
    p_restrita = p_padrao + 0.35 * (1 - g)
    if u < p_ampla:
        return "ampla"
    if u < p_padrao:
        return "padrao"
    if u < p_restrita:
        return "restrita"
    if codigo in NIVEIS_EXCLUIVEIS and rng.random() < 0.6:
        return "excluida"
    return "ausente"


SEMPRE_PRESENTES = {"ESC-01", "ESC-02", "LIM-01", "TMP-01", "EXC-01", "LIM-04"}


def _ajustes_de_contexto(nivel: str, codigo: str, seg: SeguradoraFicticia,
                         tom: TomadoraFicticia, rng: random.Random) -> str:
    """Regras de coerência entre perfil, território, seguradora e cláusula."""
    p = tom.perfil
    # Side C só faz sentido com valores mobiliários emitidos
    if codigo == "ESC-04" and not tom.capital_aberto:
        return "ausente" if rng.random() < 0.85 else "restrita"
    # Familiar/pequeno: cobertura nacional, sem run-off nem controladas
    if p in PERFIS_FAMILIARES:
        if codigo == "ESC-05":
            return "restrita" if rng.random() < 0.7 else "padrao"
        if codigo in ("TMP-04", "ESC-06", "OPE-05") and rng.random() < 0.65:
            return "ausente"
    if tom.exterior and codigo == "ESC-05" and nivel in ("restrita", "ausente"):
        return "padrao" if rng.random() < 0.7 else nivel
    # Fronteira agrícola: generalistas restringem ambiental; especialistas
    # oferecem defesa ambiental com sublimite
    if tom.amazonia_legal or p == "latifundio":
        if codigo == "EXC-03" and not seg.especialista_agro and rng.random() < 0.55:
            return "excluida"
        if codigo == "AGR-02":
            if seg.especialista_agro:
                return rng.choice(["padrao", "padrao", "restrita", "ampla"])
            return "ausente" if rng.random() < 0.6 else "restrita"
    # Quem concede ou repassa crédito rural: cobertura regulatória BCB/Proagro
    if codigo == "AGR-01":
        if tom.opera_credito_rural:
            if seg.codigo in ("ATA", "MIN") and rng.random() < 0.35:
                return "excluida"   # exclusão de "atividade financeira"
            if nivel == "ausente":
                return "restrita" if not seg.especialista_agro else "padrao"
        elif rng.random() < 0.5:
            return "ausente"
    # Semiárido e Sul pós-enchente: insolvência/RJ por quebra de safra
    if codigo == "AGR-03" and (tom.semiarido or tom.uf == "RS") and nivel == "ausente" \
            and seg.especialista_agro:
        return "padrao"
    # Linguagem simples da mútua omite cláusulas operacionais menos usadas
    if seg.modelo == "linguagem_simples" and codigo in ("OPE-02", "OPE-05", "TMP-04") \
            and rng.random() < 0.6:
        return "ausente"
    return nivel


def _distribuir_cotacoes(rng: random.Random) -> list[tuple[str, str]]:
    """Pares (seguradora, tomadora): 20 por seguradora, 2+ cotações por tomadora."""
    cap = {s.codigo: APOLICES_POR_SEGURADORA for s in SEGURADORAS}
    pares: set[tuple[str, str]] = set()

    def escolher(tom: TomadoraFicticia) -> str | None:
        opcoes = [s for s in SEGURADORAS if cap[s.codigo] > 0 and (s.codigo, tom.codigo) not in pares]
        if not opcoes:
            return None
        pesos = [s.afinidade.get(tom.perfil, 0.5) for s in opcoes]
        return rng.choices(opcoes, weights=pesos, k=1)[0].codigo

    ordem = list(TOMADORAS)
    for rodada in range(2):
        rng.shuffle(ordem)
        for tom in ordem:
            s = escolher(tom)
            if s:
                pares.add((s, tom.codigo))
                cap[s] -= 1
    # sobras: tomadoras maiores recebem mais cotações
    grandes = sorted(TOMADORAS, key=lambda t: -t.receita_mi)
    while sum(cap.values()) > 0:
        for tom in grandes:
            if sum(cap.values()) == 0:
                break
            if rng.random() < 0.55:
                s = escolher(tom)
                if s:
                    pares.add((s, tom.codigo))
                    cap[s] -= 1
        # garante término mesmo com afinidades baixas
        for s_cod, c in list(cap.items()):
            if c > 0 and rng.random() < 0.2:
                livres = [t for t in TOMADORAS if (s_cod, t.codigo) not in pares]
                t = rng.choice(livres)
                pares.add((s_cod, t.codigo))
                cap[s_cod] -= 1
    return sorted(pares, key=lambda p: (p[1], p[0]))


def gerar_especificacoes(semente: int = 2026) -> list[EspecApolice]:
    """Gera o acervo determinístico (mesma semente → mesmo acervo)."""
    rng = random.Random(semente)
    cnpj_tom = {t.codigo: _cnpj(rng, f"{rng.randint(10, 99)}") for t in TOMADORAS}
    inicio_tom = {t.codigo: date(2026, rng.choice([7, 8, 9, 10, 11, 12]), 1) for t in TOMADORAS}
    especs: list[EspecApolice] = []
    for n, (s_cod, t_cod) in enumerate(_distribuir_cotacoes(rng), start=1):
        seg, tom = SEGURADORAS_POR_CODIGO[s_cod], TOMADORAS_POR_CODIGO[t_cod]
        gen = seg.generosidade + AJUSTE_PERFIL[tom.perfil] + rng.uniform(-0.1, 0.1)
        avaliacoes: dict[str, str] = {}
        for c in CLAUSULAS:
            nivel = _sortear_nivel(rng, gen + seg.vies.get(c.codigo[:3], 0.0), c.codigo)
            nivel = _ajustes_de_contexto(nivel, c.codigo, seg, tom, rng)
            if nivel == "ausente" and c.codigo in SEMPRE_PRESENTES:
                nivel = "restrita"
            if nivel == "excluida" and c.codigo not in NIVEIS_EXCLUIVEIS:
                nivel = "ausente"
            avaliacoes[c.codigo] = nivel

        lo, hi = FAIXA_LMG[tom.perfil]
        escala = min(1.0, (tom.receita_mi / 3000) ** 0.35)
        bruto = lo + (hi - lo) * escala * rng.uniform(0.55, 1.25)
        passo = 0.5 if bruto < 5 else (1 if bruto < 20 else 5)
        lmg = max(lo, round(bruto / passo) * passo) * 1_000_000
        taxa = seg.taxa_base * rng.uniform(0.85, 1.2) / 100
        taxa *= {"familiar": 1.25, "pequeno": 1.15}.get(tom.perfil, 1.0)   # escala mínima
        taxa *= 1.18 if tom.capital_aberto else 1.0
        taxa *= 1.12 if tom.opera_credito_rural else 1.0
        taxa *= 1.20 if (tom.amazonia_legal or tom.perfil == "latifundio") else 1.0
        premio = max(3_500.0, round(lmg * taxa / 50) * 50)
        franquias = ([0, 10_000, 25_000, 50_000] if tom.perfil in PERFIS_FAMILIARES
                     else [0, 50_000, 100_000, 250_000, 500_000])
        franquia = float(rng.choice(franquias))
        if avaliacoes["LIM-04"] == "restrita" and franquia == 0:
            franquia = float(franquias[1])
        sub_pct = {"ampla": 0.5, "padrao": 0.25, "restrita": 0.1}.get(avaliacoes["DEF-05"], 0.1)
        sub_multas = max(50_000.0, round(lmg * sub_pct / 50_000) * 50_000)
        retro_ilim = avaliacoes["TMP-01"] == "ampla"
        retro = None if retro_ilim else date(
            rng.choice(range(2010, 2019) if avaliacoes["TMP-01"] == "padrao" else range(2022, 2026)),
            rng.choice([1, 3, 6, 7, 10]), 1)
        dias = {"ampla": rng.choice([15, 20, 30]), "padrao": rng.choice([30, 45, 60])}.get(
            avaliacoes["DEF-02"], 0)
        anos = {"ampla": rng.choice([5, 6]), "padrao": rng.choice([2, 3])}.get(avaliacoes["TMP-02"], 0)
        ini = inicio_tom[t_cod]
        especs.append(EspecApolice(
            identificador=f"AP{n:03d}-{s_cod}-{t_cod}",
            numero_apolice=_numero_apolice(rng, s_cod),
            seguradora_codigo=s_cod, seguradora=seg.nome, seguradora_cnpj=seg.cnpj,
            modelo_documento=seg.modelo, tomadora_codigo=t_cod, tomadora=tom.razao_social,
            tomadora_cnpj=cnpj_tom[t_cod], segmento=tom.segmento, perfil=tom.perfil,
            municipio=tom.municipio, uf=tom.uf, regiao=tom.regiao, lmg=lmg, premio=premio,
            franquia=franquia, sub_multas=sub_multas, vigencia_inicio=ini,
            vigencia_fim=ini.replace(year=ini.year + 1), retroatividade=retro,
            retroatividade_ilimitada=retro_ilim, dias_adiantamento=dias,
            anos_prazo_adicional=anos, avaliacoes=avaliacoes,
            estilo_titulo=rng.randint(0, 1), semente=rng.randint(0, 10**6),
        ))
    # formatos: ~10% digitalizadas e ~5% fotografadas, espalhadas entre seguradoras
    for s in SEGURADORAS:
        do_seg = [e for e in especs if e.seguradora_codigo == s.codigo]
        rng.shuffle(do_seg)
        for e in do_seg[:2]:
            e.formato = "pdf_digitalizado"
        do_seg[2].formato = "imagem" if s.codigo in ("MUT", "XIQ", "JAC", "IPE") else "pdf"
    return especs


def _numero_apolice(rng: random.Random, s: str) -> str:
    padroes = {
        "ATA": lambda: f"01.10.{rng.randint(1000000, 9999999)}",
        "IPE": lambda: f"5177{rng.randint(100000000, 999999999)}",
        "JAC": lambda: f"{rng.randint(100, 999)}.{rng.randint(10000, 99999)}-{rng.randint(0, 9)}",
        "XIQ": lambda: f"XQ-DO-2026-{rng.randint(10000, 99999)}",
        "MUT": lambda: f"MUT/{rng.randint(1000, 9999)}/26",
        "MIN": lambda: f"MSP-FL-{rng.randint(100000, 999999)}-BR",
    }
    return padroes[s]()


# ==========================================================================
# Conteúdo de cada cláusula no dialeto da seguradora
# ==========================================================================

def parametros(espec: EspecApolice) -> dict[str, str]:
    seg = SEGURADORAS_POR_CODIGO[espec.seguradora_codigo]
    fv = lambda v: formatar_valor(v, seg.formato_valor)  # noqa: E731
    return {
        "seg": seg.termo_segurado,
        "lmg": fv(espec.lmg), "franquia": fv(espec.franquia), "premio": fv(espec.premio),
        "sub_multas": fv(espec.sub_multas),
        "sub_agro": fv(max(50_000, round(espec.lmg * 0.2 / 50_000) * 50_000)),
        "sub_amb": fv(max(50_000, round(espec.lmg * 0.15 / 50_000) * 50_000)),
        "side_a_dic": fv(max(100_000, round(espec.lmg * 0.5 / 100_000) * 100_000)),
        "dias_adiant": str(espec.dias_adiantamento or 30),
        "anos_prazo": str(espec.anos_prazo_adicional or 2),
        "retro": formatar_data(espec.retroatividade, seg.formato_data) or "ilimitada",
    }


def _aplicar_dialeto(texto: str, s_cod: str) -> str:
    """Troca de vocabulário em passada única (um termo trocado não é retrocado)."""
    import re

    pares = DIALETOS.get(s_cod, [])
    if not pares:
        return texto
    mapa = dict(pares)
    padrao = re.compile("|".join(re.escape(k) for k in sorted(mapa, key=len, reverse=True)))
    return padrao.sub(lambda m: mapa[m.group(0)], texto)


def corpo_clausula(espec: EspecApolice, codigo: str) -> str | None:
    nivel = espec.avaliacoes.get(codigo, "ausente")
    if nivel == "ausente":
        return None
    proprio = TEXTOS_PROPRIOS.get(espec.seguradora_codigo, {}).get(codigo, {})
    modelo = proprio.get(nivel) or TEXTOS[codigo].get(nivel)
    if modelo is None:
        return None
    texto = modelo.format(**parametros(espec))
    if not proprio.get(nivel):
        texto = _aplicar_dialeto(texto, espec.seguradora_codigo)
    if espec.seguradora_codigo == "MUT":
        texto = texto.replace("Considera-se dirigente segurado", "É considerado dirigente segurado")
    return texto


def titulo_base(espec: EspecApolice, codigo: str) -> str:
    return TITULOS[codigo][espec.estilo_titulo % len(TITULOS[codigo])]


def descricao_risco(espec: EspecApolice) -> str:
    """Bloco 'Informações do risco' — contexto da tomadora (coerente por região)."""
    tom = TOMADORAS_POR_CODIGO[espec.tomadora_codigo]
    bioma = ("Amazônia Legal" if tom.amazonia_legal else
             "semiárido nordestino" if tom.semiarido else f"região {tom.regiao}")
    return (f"Atividade: {tom.segmento.lower()} — {tom.atividade}. Porte: {tom.escala}. "
            f"Localização: {tom.municipio}/{tom.uf} ({bioma}). Perfil: "
            f"{PERFIS_ROTULO[tom.perfil].lower()}. Particularidades informadas na proposta: "
            f"{tom.contexto}." + (" A Tomadora concede, repassa ou intermedia crédito rural."
                                  if tom.opera_credito_rural else ""))


def sem_acentos(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))


def acervo(semente: int = 2026):
    from .modelos_documento import montar_documento

    return [montar_documento(e) for e in gerar_especificacoes(semente)]
