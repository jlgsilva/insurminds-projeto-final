# Roteiro do vídeo narrado (máx. 5 min)

Texto de referência para gravar a narração **em primeira pessoa**, alternando a apresentação
(`InsurMinds_Projeto_Final.pptx`) e o **app rodando ao vivo** no Streamlit. O mesmo texto está nas
notas de cada slide (modo apresentador do PowerPoint). Gerado por `node scripts/gerar_pitch_deck.js`.

## Antes de gravar

- Abra o app (local ou Streamlit Cloud) com a chave da Groq configurada e **rode a ingestão e a comparação uma vez antes**: as respostas ficam em cache e a gravação fica mais rápida.
- Deixe duas janelas prontas: a apresentação em tela cheia e o navegador com o app (zoom em 90%).
- Feche notificações. Se a Groq demorar (limite do plano gratuito), corte a espera na edição.
- O tempo total fica perto de **5 min**, o limite do enunciado: o slide 12 não tem narração (passe direto) e as falas podem ser encurtadas.
- **Não mostre na tela as apólices de Seguro Garantia** enviadas pelo colega: têm dados reais de empresas e pessoas. Se quiser mostrar um documento real, use uma das condições gerais públicas de D&O (página Ingestão → origem "Documentos reais (pasta local)").
- Tudo o que está no texto aconteceu de fato no projeto. Se algo mudar (por exemplo, se você já tiver usado o prompt com outra IA), ajuste a fala do slide 9.

## Narração

### 0:00 · Slide 1 — Capa

> Olá, eu sou o Jefferson, e este é o meu Projeto Final do InsurMinds. Vou contar duas coisas: como eu construí este projeto, usando inteligência artificial em cada etapa, e como a aplicação funciona, mostrando ela rodando ao vivo.

### 0:14 · Slide 2 — O problema

> Primeiro, o problema. O seguro D&O protege o patrimônio pessoal de diretores e conselheiros quando eles são processados por decisões tomadas na empresa ou na cooperativa. Cada apólice tem dezenas de cláusulas, cada seguradora escreve de um jeito, e a proposta mais barata pode proteger bem menos. No agro ainda entram crédito rural, meio ambiente e recuperação judicial.

### 0:35 · Slide 3 — A ideia

> A minha proposta é um assistente que lê a apólice, mesmo escaneada, organiza as informações, compara as opções lado a lado e explica as diferenças em português simples. E eu não comecei do zero: construí isso dentro do AgroSentinela, o aplicativo do Desafio 5, que já usa dados públicos de crédito rural do Banco Central.

### 0:53 · Slide 4 — Três IAs, três papéis

> Trabalhei com três inteligências artificiais, cada uma com um papel. O Claude, da Anthropic, foi meu assistente de desenvolvimento: pesquisou referências, escreveu o código, os testes e a primeira versão deste material. A IA da Groq trabalha dentro do aplicativo: lê as apólices e escreve os relatórios. E preparei um roteiro para uma terceira IA gerar novas apólices de teste. As decisões ficaram comigo.

### 1:14 · Slide 5 — Passo a passo

> Foram sete passos. Li o enunciado e decidi integrar ao Desafio 5. Defini as premissas: IA pela Groq no plano gratuito, agentes, foco rural e cuidado com modelos perto de sair do ar. Com o Claude, montei uma primeira versão. Revisei com olhar crítico, refiz a base e, no fim, testei com documentos reais.

### 1:33 · Slide 6 — Por que simular

> Por que simular apólices? Porque apólices emitidas são confidenciais: não existe uma base pública delas para testar. Só o texto-padrão, as condições gerais, é público. Com dados simulados eu tenho o gabarito, a resposta certa, para medir quanto o sistema acerta. E tudo é declarado: marca d'água, aviso em cada página e nomes inventados.

### 1:48 · Slide 7 — Antes e depois

> Na primeira versão havia 45 apólices de 12 seguradoras, mas todas no mesmo modelo de documento: só mudavam o nome e a cor. No mundo real não é assim. Pedi para refazer: o Claude pesquisou condições gerais públicas de seguradoras reais e criou seis seguradoras fictícias, cada uma com o seu jeito de escrever, uma delas até em inglês.

### 2:08 · Slide 8 — Os vários Brasis

> Também pedi diversidade de Brasil: 120 apólices para 45 empresas e cooperativas rurais, em todos os estados, da associação de castanha no Acre ao arroz do Rio Grande do Sul. E cada região traz os seus riscos: ambiental na Amazônia, seca no semiárido, enchentes no Sul.

### 2:24 · Slide 9 — Outra IA para ampliar a base

> Para ampliar a base, preparei um prompt para outra IA gerar novas apólices em PDF. Nada entra sem conferência: um importador verifica nomes, marca d'água e valores. Esse caminho está pronto e testado, mas ainda não foi usado.

### 2:37 · Slide 10 — O teste com documentos reais

> Na reta final, um colega me mandou cinco documentos reais: as condições gerais de D&O de três seguradoras, de 50 a 100 páginas, e duas apólices de Seguro Garantia. Esse teste mostrou o que a simulação escondia: a IA só via o começo dos documentos longos, e uma apólice de outro ramo entraria como se fosse D&O. Corrigimos: agora o sistema reconhece o tipo de documento, recusa o que não é D&O e manda para a IA os trechos certos de cada cláusula. Os documentos reais ficaram fora do GitHub.

### 3:04 · Slide 11 — Linha de montagem de agentes

> Por dentro, o aplicativo é uma linha de montagem com dez agentes, cada um com uma tarefa. Os dourados usam IA: ler a ficha, entender as cláusulas, escrever o relatório e responder perguntas. Notas e contas ficam com regras fixas, mais fáceis de conferir.

### — · Slide 12 — Como evitamos que a IA invente (apoio, sem narração)

> (Slide de apoio, sem narração: se sobrar tempo, diga que a IA precisa citar o trecho que leu e que o sistema confere cada trecho e cada número.)

### 3:17 · Slide 13 — Demonstração (transição)

> Agora vou mostrar o aplicativo funcionando. (Troque para o navegador com o app aberto e siga o roteiro da demonstração.)

#### Demonstração ao vivo (no app)

**3:19 · Demo 1 — Página **Ingestão de Apólices****

*O que fazer:* Mantenha a sugestão (uma apólice da Ipê-Roxo em PDF e uma *digitalizada* da Mutirão) e clique **Executar pipeline de ingestão**. Mostre os agentes aparecendo, depois role até a tabela de cláusulas.

> Aqui eu escolho duas apólices bem diferentes: uma da Ipê-Roxo e uma escaneada da Mutirão, escrita em linguagem simples. Clico em executar e cada agente aparece trabalhando. O documento escaneado passa pela leitura de imagem. No resultado, cada cláusula vem com o nível de cobertura e o trecho que comprova.

**3:47 · Demo 2 — Página **Comparador de Apólices****

*O que fazer:* Tomadora sugerida *Grão Norte Trading* (4 cotações), relatório para *Gestor de riscos*, clique **Comparar**. Mostre as abas Relatório, Diferenças e Perfil da tomadora.

> Agora comparo as quatro propostas que a Grão Norte, uma trading de Sorriso, no Mato Grosso, recebeu. O sistema usa os dados de crédito rural da região para dar mais peso ao que importa ali, como a defesa ambiental. A IA escreve o relatório e um verificador confere cada número.

**4:12 · Demo 3 — Página **Consulta às Apólices****

*O que fazer:* Clique na sugestão “Qual seguradora oferece, em média, a melhor cobertura para crédito rural?”. Abra o detalhe da ferramenta usada.

> Por fim, uma pergunta em português: qual seguradora oferece a melhor cobertura para crédito rural? O agente escolhe onde procurar, consulta a base e mostra a tabela que usou.

*Volte para a apresentação no slide 14.*

### 4:30 · Slide 14 — Resultados

> Quanto o sistema acerta? No acervo simulado, as regras fixas leem bem os valores, 96%, mas acertam só 69% do nível das cláusulas, e 38% no documento em linguagem simples. Nas condições gerais reais, encontram 83% das cláusulas. Classificar o nível é a parte que depende da IA.

### 4:45 · Slide 15 — Aprendizados

> O que eu aprendi: a IA acelerou muito, mas foi a revisão humana e o teste com documentos reais que deixaram o projeto confiável. E é uma ferramenta de apoio: não substitui o corretor nem o advogado.

### 4:56 · Slide 16 — Obrigado

> O código é aberto e o link está no material. Obrigado!

## Se o app falhar durante a gravação

O vídeo-base `InsurMinds_Projeto_Final.mp4` (sem áudio) tem as mesmas telas da demonstração em capturas.
Você pode narrar por cima dele ou usar o slide 12, que mostra as três telas.
