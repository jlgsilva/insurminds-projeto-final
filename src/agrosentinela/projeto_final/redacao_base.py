"""
Redação-base das cláusulas de D&O, por nível de atendimento.

É o "conteúdo" de cada cláusula. Cada seguradora simulada reescreve esse
conteúdo no seu próprio dialeto (vocabulário, formato de número e data) e o
encaixa na sua própria arquitetura de documento — ver ``modelos_documento.py``.
Assim, o significado (o gabarito) é controlado, mas a forma varia como varia
no mercado real.

No texto, ``{seg}`` é o termo da seguradora para o segurado; os demais
placeholders são valores da apólice já formatados no padrão da seguradora.
"""

from __future__ import annotations

TITULOS: dict[str, tuple[str, ...]] = {
    "ESC-01": ("DEFINIÇÃO DE SEGURADO", "PESSOAS SEGURADAS"),
    "ESC-02": ("COBERTURA A — RESPONSABILIDADE DOS SEGURADOS NÃO INDENIZÁVEIS",
               "COBERTURA BÁSICA — SIDE A"),
    "ESC-03": ("COBERTURA B — REEMBOLSO À TOMADORA", "SIDE B — REEMBOLSO DA SOCIEDADE"),
    "ESC-04": ("COBERTURA C — RESPONSABILIDADE DA PESSOA JURÍDICA",
               "SIDE C — RECLAMAÇÕES DE VALORES MOBILIÁRIOS"),
    "ESC-05": ("ÂMBITO GEOGRÁFICO E JURISDIÇÃO", "TERRITORIALIDADE"),
    "ESC-06": ("SUBSIDIÁRIAS E NOVAS CONTROLADAS", "EXTENSÃO A CONTROLADAS"),
    "LIM-01": ("LIMITE MÁXIMO DE GARANTIA", "LIMITE MÁXIMO DE INDENIZAÇÃO AGREGADO"),
    "LIM-02": ("SUBLIMITES", "SUBLIMITES DE COBERTURAS ADICIONAIS"),
    "LIM-03": ("REINTEGRAÇÃO DO LIMITE", "RESTABELECIMENTO DO LIMITE"),
    "LIM-04": ("FRANQUIA E PARTICIPAÇÃO OBRIGATÓRIA", "FRANQUIA"),
    "DEF-01": ("CUSTOS DE DEFESA", "DESPESAS DE DEFESA E O LIMITE"),
    "DEF-02": ("ADIANTAMENTO DE CUSTOS DE DEFESA", "PAGAMENTO ANTECIPADO DE DESPESAS DE DEFESA"),
    "DEF-03": ("ESCOLHA DE ADVOGADOS", "NOMEAÇÃO DE PATRONO"),
    "DEF-04": ("SEPARABILIDADE", "INDIVISIBILIDADE DAS DECLARAÇÕES E CONDUTAS"),
    "DEF-05": ("MULTAS E PENALIDADES", "MULTAS CIVIS E ADMINISTRATIVAS"),
    "TMP-01": ("DATA DE RETROATIVIDADE", "PERÍODO DE RETROATIVIDADE"),
    "TMP-02": ("PRAZO ADICIONAL", "PRAZO ADICIONAL PARA APRESENTAÇÃO DE RECLAMAÇÕES"),
    "TMP-03": ("NOTIFICAÇÃO DE CIRCUNSTÂNCIAS", "AVISO DE FATOS E CIRCUNSTÂNCIAS"),
    "TMP-04": ("MUDANÇA DE CONTROLE (RUN-OFF)", "ALTERAÇÃO DE CONTROLE SOCIETÁRIO"),
    "EXC-01": ("EXCLUSÃO — ATOS DOLOSOS", "ATOS INTENCIONAIS E FRAUDULENTOS"),
    "EXC-02": ("EXCLUSÃO — RECLAMAÇÕES ENTRE SEGURADOS", "SEGURADO CONTRA SEGURADO"),
    "EXC-03": ("EXCLUSÃO — POLUIÇÃO E DANOS AMBIENTAIS", "RISCOS AMBIENTAIS"),
    "EXC-04": ("EXCLUSÃO — RISCOS CIBERNÉTICOS", "DADOS E SISTEMAS"),
    "EXC-05": ("EXCLUSÃO — FATOS CONHECIDOS E LITÍGIOS ANTERIORES", "FATOS PRETÉRITOS"),
    "OPE-01": ("CANCELAMENTO", "RESCISÃO DO CONTRATO"),
    "OPE-02": ("SOLUÇÃO DE CONTROVÉRSIAS", "ARBITRAGEM E FORO"),
    "OPE-03": ("SUB-ROGAÇÃO", "DIREITO DE REGRESSO"),
    "OPE-04": ("ORDEM DE PAGAMENTO", "PRIORIDADE DE PAGAMENTOS"),
    "OPE-05": ("MOEDA E CONVERSÃO", "MOEDA DO CONTRATO"),
    "AGR-01": ("COBERTURA ADICIONAL — CRÉDITO RURAL, SICOR E PROAGRO",
               "ATOS DE GESTÃO EM OPERAÇÕES DE CRÉDITO RURAL"),
    "AGR-02": ("COBERTURA ADICIONAL — DEFESA EM PROCESSOS AMBIENTAIS RURAIS",
               "RESPONSABILIDADE AMBIENTAL NA CADEIA DE FORNECIMENTO"),
    "AGR-03": ("RECUPERAÇÃO JUDICIAL E INSOLVÊNCIA", "INSOLVÊNCIA DA TOMADORA"),
}

# Nos textos, {seg} é o termo da seguradora para "Segurado"/"Pessoa Segurada".

TEXTOS: dict[str, dict[str, str]] = {
    "ESC-01": {
        "ampla": "Considera-se {seg} toda pessoa física que tenha sido, seja ou venha a ser administrador, diretor, conselheiro de administração ou fiscal, membro de comitê estatutário, procurador com poderes de gestão ou administrador de fato da Tomadora e de suas controladas, estendendo-se a cobertura a cônjuges, companheiros, herdeiros, espólio e representantes legais, exclusivamente por atos de gestão do {seg}.",
        "padrao": "Considera-se {seg} a pessoa física eleita ou nomeada para cargo de administrador, diretor ou conselheiro da Tomadora, bem como seus cônjuges e espólio, por atos praticados no exercício dessas funções.",
        "restrita": "Considera-se {seg} exclusivamente a pessoa física eleita para cargo estatutário de diretor ou conselheiro de administração da Tomadora, conforme ata registrada. Não são considerados segurados os procuradores, administradores de fato ou membros do conselho fiscal.",
    },
    "ESC-02": {
        "ampla": "A Seguradora pagará, em nome do {seg}, as perdas decorrentes de reclamações por ato danoso, quando a Tomadora não puder ou não estiver obrigada a indenizá-lo, inclusive por insolvência, vedação legal ou recusa. Esta cobertura conta com limite adicional exclusivo (Side A DIC) de {side_a_dic}, sem franquia.",
        "padrao": "A Seguradora pagará, em nome do {seg}, as perdas decorrentes de reclamações por ato danoso, quando não houver indenização pela Tomadora, sem incidência de franquia.",
        "restrita": "A Seguradora pagará as perdas do {seg} não indenizadas pela Tomadora somente nos casos de insolvência declarada judicialmente, aplicando-se a franquia prevista no quadro-resumo.",
    },
    "ESC-03": {
        "ampla": "A Seguradora reembolsará a Tomadora pelos valores que esta, por força de lei ou estatuto, tiver adiantado ou pago ao {seg} a título de perdas ou custos de defesa, aplicando-se a franquia de {franquia}.",
        "padrao": "Fica garantido o reembolso à Tomadora das quantias pagas em favor do {seg}, observada a franquia de {franquia} por reclamação.",
        "restrita": "O reembolso à Tomadora limita-se aos custos de defesa efetivamente pagos e comprovados, sujeito à franquia de {franquia} e à prévia anuência da Seguradora a cada desembolso.",
    },
    "ESC-04": {
        "ampla": "Fica garantida a responsabilidade da própria Tomadora por reclamações relativas a valores mobiliários, com limite próprio, que não reduz o Limite Máximo de Garantia das Coberturas A e B.",
        "padrao": "Fica garantida a responsabilidade da Tomadora por reclamações relativas a valores mobiliários, compartilhando o Limite Máximo de Garantia com as demais coberturas.",
        "restrita": "A Cobertura C aplica-se somente a reclamações relativas a valores mobiliários registrados em bolsa brasileira, com sublimite de 20% do Limite Máximo de Garantia, compartilhado com as Coberturas A e B.",
    },
    "ESC-05": {
        "ampla": "Esta apólice cobre atos danosos praticados e reclamações apresentadas em qualquer parte do mundo, inclusive Estados Unidos da América e Canadá, onde legalmente permitido.",
        "padrao": "Esta apólice cobre reclamações apresentadas em qualquer parte do mundo, excetuadas aquelas ajuizadas nos Estados Unidos da América ou no Canadá, salvo se para execução de sentença proferida no Brasil.",
        "restrita": "Esta apólice cobre exclusivamente reclamações apresentadas no território brasileiro e julgadas segundo a lei brasileira.",
    },
    "ESC-06": {
        "ampla": "Estão automaticamente incluídas as controladas existentes e as que vierem a ser constituídas ou adquiridas durante a vigência, independentemente de porte, mediante simples comunicação na renovação.",
        "padrao": "Novas controladas são incluídas automaticamente desde que seus ativos não excedam 25% dos ativos consolidados da Tomadora; acima disso, mediante aceitação expressa.",
        "restrita": "A cobertura alcança apenas as controladas nominalmente relacionadas no quadro-resumo. A inclusão de qualquer nova sociedade depende de proposta e aceitação expressa.",
    },
    "LIM-01": {
        "ampla": "O Limite Máximo de Garantia é de {lmg}, por reclamação e no agregado anual, aplicável a todas as coberturas contratadas.",
        "padrao": "O Limite Máximo de Garantia é de {lmg}, no agregado por período de vigência, para todas as coberturas e reclamações somadas.",
        "restrita": "O Limite Máximo de Garantia é de {lmg}, no agregado por período de vigência, nele incluídos custos de defesa, coberturas adicionais e a Cobertura C.",
    },
    "LIM-02": {
        "ampla": "As coberturas adicionais não possuem sublimite, respondendo até o Limite Máximo de Garantia.",
        "padrao": "Aplicam-se os seguintes sublimites: multas e penalidades, {sub_multas}; custos emergenciais, 30% do LMG; custos de publicidade, 10% do LMG.",
        "restrita": "Aplicam-se os seguintes sublimites: multas e penalidades, {sub_multas}; custos emergenciais, 10% do LMG; custos de publicidade, 5% do LMG; processos ambientais, 5% do LMG.",
    },
    "LIM-03": {
        "ampla": "Esgotado o Limite Máximo de Garantia, este será automaticamente reintegrado uma vez por vigência, sem cobrança de prêmio adicional, exclusivamente para a Cobertura A.",
        "padrao": "O Limite Máximo de Garantia poderá ser reintegrado uma vez por vigência, mediante pagamento de prêmio adicional calculado pro rata.",
        "restrita": "A reintegração do limite dependerá de análise de aceitação e pagamento de prêmio adicional a ser fixado pela Seguradora.",
    },
    "LIM-04": {
        "ampla": "Não se aplica franquia às Coberturas A e às coberturas adicionais. Para as Coberturas B e C aplica-se franquia de {franquia} por reclamação.",
        "padrao": "Aplica-se franquia de {franquia} por reclamação às Coberturas B e C. A Cobertura A não está sujeita a franquia.",
        "restrita": "Aplica-se franquia de {franquia} por reclamação a todas as coberturas, inclusive à Cobertura A, e participação obrigatória de 10% sobre cada perda.",
    },
    "DEF-01": {
        "ampla": "Os custos de defesa são pagos em adição ao Limite Máximo de Garantia, até montante equivalente a 100% do LMG, não reduzindo o valor disponível para indenizações.",
        "padrao": "Os custos de defesa são pagos em adição ao Limite Máximo de Garantia até 50% do LMG; excedido esse montante, passam a integrá-lo.",
        "restrita": "Os custos de defesa integram e reduzem o Limite Máximo de Garantia, estando sujeitos ao sublimite de 30% do LMG.",
    },
    "DEF-02": {
        "ampla": "A Seguradora adiantará os custos de defesa em até {dias_adiant} dias contados do recebimento dos documentos, independentemente de definição sobre a cobertura, cabendo devolução somente se comprovada, por decisão final, a exclusão aplicável.",
        "padrao": "A Seguradora adiantará os custos de defesa razoáveis em até {dias_adiant} dias, mediante aprovação prévia do orçamento.",
        "restrita": "Os custos de defesa serão reembolsados ao final do processo, após comprovação, não havendo adiantamento salvo deliberação discricionária da Seguradora.",
    },
    "DEF-03": {
        "ampla": "O {seg} poderá escolher livremente seus advogados, cabendo à Seguradora apenas verificar a razoabilidade dos honorários.",
        "padrao": "O {seg} poderá indicar advogado de sua escolha, sujeito à anuência prévia da Seguradora, que não será negada sem justo motivo.",
        "restrita": "A defesa do {seg} será conduzida por escritório integrante do painel credenciado da Seguradora.",
    },
    "DEF-04": {
        "ampla": "As declarações da proposta e o conhecimento de qualquer {seg} não serão imputados aos demais; a conduta de um {seg} não prejudicará a cobertura dos outros.",
        "padrao": "A conduta de um {seg} não será imputada aos demais para fins de aplicação das exclusões. As declarações da proposta são consideradas em conjunto.",
        "restrita": "As declarações prestadas na proposta pela Tomadora vinculam todos os Segurados, e sua inexatidão poderá acarretar a perda do direito à indenização para todos.",
    },
    "DEF-05": {
        "ampla": "Estão cobertas multas e penalidades civis e administrativas impostas ao {seg} (inclusive CVM, CADE, ANPD, BCB e órgãos ambientais), onde legalmente segurável, até o sublimite de {sub_multas}.",
        "padrao": "Estão cobertas multas administrativas impostas ao {seg} por órgãos reguladores, onde legalmente seguráveis, até o sublimite de {sub_multas}.",
        "restrita": "Estão cobertas exclusivamente multas civis impostas ao {seg} em processos judiciais, até o sublimite de {sub_multas}. Multas administrativas não estão cobertas.",
        "excluida": "Estão excluídas quaisquer multas, penalidades, sanções ou indenizações punitivas, de qualquer natureza.",
    },
    "TMP-01": {
        "ampla": "A cobertura retroage sem limite de data (retroatividade ilimitada), ressalvados os fatos conhecidos na data de início da primeira apólice.",
        "padrao": "Data de retroatividade: {retro}.",
        "restrita": "Data de retroatividade: {retro}. Atos danosos anteriores a essa data não estão cobertos, ainda que a reclamação seja apresentada na vigência.",
    },
    "TMP-02": {
        "ampla": "Na hipótese de não renovação, fica concedido automaticamente prazo adicional de 12 meses, sem cobrança de prêmio, podendo ser contratado prazo adicional opcional de até {anos_prazo} anos.",
        "padrao": "Na hipótese de não renovação, fica concedido prazo adicional de 6 meses sem custo, e prazo adicional opcional de até {anos_prazo} anos, mediante prêmio adicional.",
        "restrita": "O prazo adicional será o mínimo previsto na regulamentação vigente, sem prazo adicional opcional.",
    },
    "TMP-03": {
        "ampla": "Fatos ou circunstâncias notificados durante a vigência serão considerados reclamações apresentadas nesta apólice, desde que comunicados em até 60 dias do conhecimento pelo {seg}.",
        "padrao": "Circunstâncias notificadas durante a vigência, com descrição detalhada do ato danoso, serão consideradas reclamações desta apólice.",
        "restrita": "Circunstâncias somente serão consideradas se notificadas com identificação do reclamante e do valor pretendido, durante a vigência.",
    },
    "TMP-04": {
        "ampla": "Em caso de alteração de controle, a apólice permanece vigente até o término e converte-se automaticamente em run-off de 6 anos para atos anteriores, com prêmio adicional de 150% do prêmio anual.",
        "padrao": "Em caso de alteração de controle, a cobertura fica restrita a atos anteriores, podendo ser contratado run-off de até 3 anos mediante prêmio adicional.",
        "restrita": "Em caso de alteração de controle, a apólice será cancelada, ressalvada a contratação de prazo adicional nos termos da regulamentação.",
    },
    "EXC-01": {
        "ampla": "Exclui-se a reclamação decorrente de ato doloso ou fraudulento do {seg}, somente após decisão judicial ou arbitral final e irrecorrível que o reconheça. Os custos de defesa serão adiantados até essa decisão.",
        "padrao": "Exclui-se a reclamação decorrente de ato doloso do {seg} reconhecido por decisão judicial ou administrativa, ainda que não definitiva, ou por confissão.",
        "restrita": "Exclui-se a reclamação em que se alegue ato doloso, fraudulento ou com culpa grave do {seg}, ressalvado o reembolso de custos de defesa caso a alegação seja afastada.",
        "excluida": "Exclui-se qualquer reclamação em que se alegue ato doloso, fraudulento, culpa grave ou violação intencional da lei pelo {seg}, inclusive custos de defesa.",
    },
    "EXC-02": {
        "ampla": "A exclusão de reclamações entre Segurados não se aplica a ações derivadas de acionistas, a reclamações de administrador judicial ou liquidante, a reclamações de ex-administradores desligados há mais de 2 anos e a reclamações fora do Brasil.",
        "padrao": "Excluem-se reclamações movidas pela Tomadora ou por outro Segurado, salvo ações derivadas propostas por acionistas minoritários sem participação dos Segurados.",
        "restrita": "Excluem-se reclamações movidas pela Tomadora, por suas controladas ou por qualquer Segurado, sem exceções.",
    },
    "EXC-03": {
        "ampla": "A exclusão de poluição não se aplica aos custos de defesa do Segurado nem a reclamações de acionistas decorrentes de evento ambiental.",
        "padrao": "Excluem-se reparação e remediação de danos ambientais; ficam cobertos os custos de defesa do Segurado até o sublimite de 10% do LMG.",
        "restrita": "Excluem-se reclamações decorrentes de poluição ou dano ambiental, ressalvadas ações derivadas de acionistas.",
        "excluida": "Excluem-se quaisquer reclamações, custos de defesa ou multas decorrentes, direta ou indiretamente, de poluição, contaminação, desmatamento ou dano ambiental de qualquer natureza.",
    },
    "EXC-04": {
        "ampla": "A exclusão de riscos cibernéticos não se aplica a reclamações por falha de supervisão ou governança do Segurado sobre segurança da informação e proteção de dados.",
        "padrao": "Excluem-se danos a sistemas e dados; permanecem cobertas reclamações contra o Segurado por violação de dever de diligência relativo à LGPD.",
        "restrita": "Excluem-se reclamações decorrentes de incidentes cibernéticos, ressalvadas ações de acionistas.",
        "excluida": "Excluem-se quaisquer reclamações decorrentes de incidente cibernético, vazamento de dados ou violação da LGPD, inclusive por falha de supervisão.",
    },
    "EXC-05": {
        "ampla": "Excluem-se fatos conhecidos apenas pelo Diretor-Presidente ou Diretor Jurídico da Tomadora na data de início da primeira apólice ininterrupta, conforme declarado na proposta.",
        "padrao": "Excluem-se reclamações relativas a fatos conhecidos por qualquer Segurado signatário da proposta antes do início de vigência.",
        "restrita": "Excluem-se reclamações relativas a fatos de que qualquer Segurado ou empregado da Tomadora tivesse ou devesse ter conhecimento antes do início de vigência.",
    },
    "OPE-01": {
        "ampla": "Esta apólice não poderá ser cancelada pela Seguradora, salvo por falta de pagamento do prêmio, com aviso prévio de 30 dias.",
        "padrao": "A apólice poderá ser cancelada por qualquer das partes, mediante aviso prévio de 30 dias, com devolução do prêmio pro rata.",
        "restrita": "A Seguradora poderá cancelar a apólice a qualquer tempo, mediante aviso prévio de 10 dias, retendo o prêmio pelo prazo decorrido conforme tabela de prazo curto.",
    },
    "OPE-02": {
        "ampla": "Divergências serão resolvidas por arbitragem na Câmara indicada pela Tomadora, ou, a critério do Segurado, no foro de seu domicílio.",
        "padrao": "Eventuais divergências serão submetidas ao foro do domicílio do Segurado.",
        "restrita": "Divergências serão resolvidas exclusivamente por arbitragem em câmara indicada pela Seguradora, com custos antecipados pelas partes.",
    },
    "OPE-03": {
        "ampla": "A Seguradora renuncia expressamente ao direito de sub-rogação contra os Segurados, salvo em caso de dolo reconhecido por decisão final.",
        "padrao": "A Seguradora sub-roga-se nos direitos contra terceiros, não exercendo regresso contra os Segurados salvo em caso de dolo.",
        "restrita": "A Seguradora sub-roga-se em todos os direitos e ações do Segurado e da Tomadora, inclusive contra outros Segurados.",
    },
    "OPE-04": {
        "ampla": "Havendo insuficiência de limite, as perdas da Cobertura A serão pagas com prioridade sobre as demais, podendo a Seguradora suspender pagamentos das Coberturas B e C.",
        "padrao": "Os pagamentos serão realizados na ordem de apresentação das reclamações, ressalvada a prioridade das perdas da Cobertura A.",
        "restrita": "Os pagamentos serão realizados na ordem cronológica de apresentação das reclamações, sem prioridade entre coberturas.",
    },
    "OPE-05": {
        "ampla": "Os valores são expressos em reais e atualizados pelo IPCA entre a data do sinistro e a do efetivo pagamento.",
        "padrao": "Os valores são expressos em reais, atualizados conforme a regulamentação vigente.",
        "restrita": "Os valores são expressos em dólares norte-americanos e convertidos pela taxa PTAX de venda do dia útil anterior ao aviso.",
    },
    "AGR-01": {
        "ampla": "Estão cobertas reclamações e processos administrativos sancionadores do Banco Central do Brasil, do MAPA e do Ministério Público contra o {seg} decorrentes de atos de gestão em operações de crédito rural, inclusive enquadramento no Proagro, registro no Sicor e desvio de finalidade, até o LMG.",
        "padrao": "Estão cobertos custos de defesa do {seg} em processos administrativos do Banco Central relativos a operações de crédito rural e ao Proagro, até o sublimite de {sub_agro}.",
        "restrita": "Estão cobertos custos de defesa do {seg} em processos administrativos do Banco Central relativos a crédito rural, até o sublimite de {sub_agro}, excluídas multas e reclamações de mutuários.",
        "excluida": "Excluem-se reclamações decorrentes da concessão, repasse, fiscalização ou cobrança de crédito, inclusive crédito rural e operações vinculadas ao Proagro.",
    },
    "AGR-02": {
        "ampla": "Estão cobertos custos de defesa do {seg} em inquéritos e processos ambientais (Ibama, órgãos estaduais e Ministério Público), inclusive embargos, CAR e fornecedores rurais da cadeia, até o LMG.",
        "padrao": "Estão cobertos custos de defesa do {seg} em processos ambientais relativos às propriedades da Tomadora, até o sublimite de {sub_amb}.",
        "restrita": "Estão cobertos custos de defesa do {seg} exclusivamente em ações penais ambientais, até o sublimite de {sub_amb}.",
    },
    "AGR-03": {
        "ampla": "O pedido de recuperação judicial, extrajudicial ou falência da Tomadora não afeta a cobertura; a Cobertura A permanece integral e prioritária, e a apólice não poderá ser cancelada por esse motivo.",
        "padrao": "Em caso de recuperação judicial da Tomadora, a cobertura permanece vigente para atos anteriores ao pedido.",
        "restrita": "Em caso de recuperação judicial ou falência da Tomadora, a cobertura limita-se à Cobertura A para atos anteriores ao pedido.",
        "excluida": "Excluem-se reclamações apresentadas após pedido de recuperação judicial, extrajudicial ou falência da Tomadora.",
    },
}

NIVEIS_EXCLUIVEIS = {c for c, t in TEXTOS.items() if "excluida" in t}
