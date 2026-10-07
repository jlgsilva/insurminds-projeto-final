// Gera Projeto_Final_Artefatos/InsurMinds_Projeto_Final.pptx (16 slides, com a
// narração nas notas de cada slide) e Projeto_Final_Artefatos/ROTEIRO_VIDEO.md
// (texto de narração + roteiro da demonstração ao vivo), a partir da mesma fonte.
//   node scripts/gerar_pitch_deck.js
// Requer: pptxgenjs, react, react-dom, react-icons, sharp (npm).
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const fi = require("react-icons/fi");
const APPLY = process.env.APPLY_THEME;

const RAIZ = path.resolve(__dirname, "..");
const ART = path.join(RAIZ, "Projeto_Final_Artefatos");
const CAP = (n) => path.join(ART, "capturas", n);
const SAIDA = path.join(ART, "InsurMinds_Projeto_Final.pptx");
const ROTEIRO = path.join(ART, "ROTEIRO_VIDEO.md");

const THEME = {
  name: "AgroSentinela",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "1B2A21", lt1: "FFFFFF", dk2: "1F4D36", lt2: "EEF3EE",
    accent1: "1F7A4D", accent2: "D9A441", accent3: "3E6E8E", accent4: "B03A2E",
    accent5: "6B7D72", accent6: "A9C9AE", hlink: "1F7A4D", folHlink: "3E6E8E",
  },
};
const H = THEME.colors;

// ------------------------------------------------------------------ dados
const R = JSON.parse(fs.readFileSync(path.join(ART, "avaliacao_resumo.json"), "utf8"));
const TB = R.total_linha_de_base;
const IA = R.total_ia || null; // presente depois de: processar_acervo.py --llm + gerar_relatorio_pf.py
const pct = (v) => `${Math.round(v)}%`;
const MUT = R.linha_de_base.MUT ? R.linha_de_base.MUT.acuracia_clausulas : null;
// catálogo do acervo: conta empresas/cooperativas (tomadoras) por região
const cat = fs.readFileSync(path.join(RAIZ, "data", "apolices_simuladas", "catalogo.csv"), "utf8")
  .trim().split(/\r?\n/);
const cab = cat[0].split(",");
const iTom = cab.indexOf("tomadora"), iReg = cab.indexOf("regiao");
const tomPorRegiao = {};
const vistos = new Set();
for (const linha of cat.slice(1)) {
  const c = linha.split(",");
  const reg = c[c.length - (cab.length - iReg)]; // conta a partir do fim (robusto a vírgulas no início)
  const tom = c[iTom];
  if (vistos.has(tom)) continue;
  vistos.add(tom);
  tomPorRegiao[reg] = (tomPorRegiao[reg] || 0) + 1;
}
const N_TOM = vistos.size;
// validação com documentos reais (scripts/avaliar_documentos_reais.py)
const RR = (() => {
  try {
    return JSON.parse(fs.readFileSync(path.join(ART, "avaliacao_reais.json"), "utf8")).deterministico;
  } catch (e) { return null; }
})();
const RR_PRES = RR ? pct(RR.acuracia_presenca) : "—";

// ------------------------------------------------------------------ narração
// t: início aproximado (mm:ss) de cada trecho no vídeo narrado.
const NARR = {
  1: { t: "0:00", f: "Olá, eu sou o Jefferson, e este é o meu Projeto Final do InsurMinds. Vou contar duas coisas: como eu construí este projeto, usando inteligência artificial em cada etapa, e como a aplicação funciona, mostrando ela rodando ao vivo." },
  2: { t: "0:14", f: "Primeiro, o problema. O seguro D&O protege o patrimônio pessoal de diretores e conselheiros quando eles são processados por decisões tomadas na empresa ou na cooperativa. Cada apólice tem dezenas de cláusulas, cada seguradora escreve de um jeito, e a proposta mais barata pode proteger bem menos. No agro ainda entram crédito rural, meio ambiente e recuperação judicial." },
  3: { t: "0:35", f: "A minha proposta é um assistente que lê a apólice, mesmo escaneada, organiza as informações, compara as opções lado a lado e explica as diferenças em português simples. E eu não comecei do zero: construí isso dentro do AgroSentinela, o aplicativo do Desafio 5, que já usa dados públicos de crédito rural do Banco Central." },
  4: { t: "0:53", f: "Trabalhei com três inteligências artificiais, cada uma com um papel. O Claude, da Anthropic, foi meu assistente de desenvolvimento: pesquisou referências, escreveu o código, os testes e a primeira versão deste material. A IA da Groq trabalha dentro do aplicativo: lê as apólices e escreve os relatórios. E preparei um roteiro para uma terceira IA gerar novas apólices de teste. As decisões ficaram comigo." },
  5: { t: "1:14", f: "Foram sete passos. Li o enunciado e decidi integrar ao Desafio 5. Defini as premissas: IA pela Groq no plano gratuito, agentes, foco rural e cuidado com modelos perto de sair do ar. Com o Claude, montei uma primeira versão. Revisei com olhar crítico, refiz a base e, no fim, testei com documentos reais." },
  6: { t: "1:33", f: "Por que simular apólices? Porque apólices emitidas são confidenciais: não existe uma base pública delas para testar. Só o texto-padrão, as condições gerais, é público. Com dados simulados eu tenho o gabarito, a resposta certa, para medir quanto o sistema acerta. E tudo é declarado: marca d'água, aviso em cada página e nomes inventados." },
  7: { t: "1:48", f: "Na primeira versão havia 45 apólices de 12 seguradoras, mas todas no mesmo modelo de documento: só mudavam o nome e a cor. No mundo real não é assim. Pedi para refazer: o Claude pesquisou condições gerais públicas de seguradoras reais e criou seis seguradoras fictícias, cada uma com o seu jeito de escrever, uma delas até em inglês." },
  8: { t: "2:08", f: `Também pedi diversidade de Brasil: 120 apólices para ${N_TOM} empresas e cooperativas rurais, em todos os estados, da associação de castanha no Acre ao arroz do Rio Grande do Sul. E cada região traz os seus riscos: ambiental na Amazônia, seca no semiárido, enchentes no Sul.` },
  9: { t: "2:24", f: "Para ampliar a base, preparei um prompt para outra IA gerar novas apólices em PDF. Nada entra sem conferência: um importador verifica nomes, marca d'água e valores. Esse caminho está pronto e testado, mas ainda não foi usado." },
  10: { t: "2:37", f: `Na reta final, um colega me mandou cinco documentos reais: as condições gerais de D&O de três seguradoras, de 50 a 100 páginas, e duas apólices de Seguro Garantia. Esse teste mostrou o que a simulação escondia: a IA só via o começo dos documentos longos, e uma apólice de outro ramo entraria como se fosse D&O. Corrigimos: agora o sistema reconhece o tipo de documento, recusa o que não é D&O e manda para a IA os trechos certos de cada cláusula. Os documentos reais ficaram fora do GitHub.` },
  11: { t: "3:04", f: "Por dentro, o aplicativo é uma linha de montagem com dez agentes, cada um com uma tarefa. Os dourados usam IA: ler a ficha, entender as cláusulas, escrever o relatório e responder perguntas. Notas e contas ficam com regras fixas, mais fáceis de conferir." },
  12: { t: "—", f: "(Slide de apoio, sem narração: se sobrar tempo, diga que a IA precisa citar o trecho que leu e que o sistema confere cada trecho e cada número.)" },
  13: { t: "3:17", f: "Agora vou mostrar o aplicativo funcionando. (Troque para o navegador com o app aberto e siga o roteiro da demonstração.)" },
  14: { t: "4:30", f: IA
    ? `Quanto o sistema acerta? No acervo simulado, só com regras fixas, ${pct(TB.acuracia_clausulas)} das cláusulas; com a IA, ${pct(IA.acuracia_clausulas)}. Nas condições gerais reais, as regras já encontram ${RR_PRES} das cláusulas.`
    : `Quanto o sistema acerta? No acervo simulado, as regras fixas leem bem os valores, ${pct(TB.acuracia_campos)}, mas acertam só ${pct(TB.acuracia_clausulas)} do nível das cláusulas, e ${pct(MUT)} no documento em linguagem simples. Nas condições gerais reais, encontram ${RR_PRES} das cláusulas. Classificar o nível é a parte que depende da IA.` },
  15: { t: "4:45", f: "O que eu aprendi: a IA acelerou muito, mas foi a revisão humana e o teste com documentos reais que deixaram o projeto confiável. E é uma ferramenta de apoio: não substitui o corretor nem o advogado." },
  16: { t: "4:56", f: "O código é aberto e o link está no material. Obrigado!" },
};
const DEMO = [
  { t: "3:19", tela: "Página **Ingestão de Apólices**", acao: "Mantenha a sugestão (uma apólice da Ipê-Roxo em PDF e uma *digitalizada* da Mutirão) e clique **Executar pipeline de ingestão**. Mostre os agentes aparecendo, depois role até a tabela de cláusulas.",
    f: "Aqui eu escolho duas apólices bem diferentes: uma da Ipê-Roxo e uma escaneada da Mutirão, escrita em linguagem simples. Clico em executar e cada agente aparece trabalhando. O documento escaneado passa pela leitura de imagem. No resultado, cada cláusula vem com o nível de cobertura e o trecho que comprova." },
  { t: "3:47", tela: "Página **Comparador de Apólices**", acao: "Tomadora sugerida *Grão Norte Trading* (4 cotações), relatório para *Gestor de riscos*, clique **Comparar**. Mostre as abas Relatório, Diferenças e Perfil da tomadora.",
    f: "Agora comparo as quatro propostas que a Grão Norte, uma trading de Sorriso, no Mato Grosso, recebeu. O sistema usa os dados de crédito rural da região para dar mais peso ao que importa ali, como a defesa ambiental. A IA escreve o relatório e um verificador confere cada número." },
  { t: "4:12", tela: "Página **Consulta às Apólices**", acao: "Clique na sugestão “Qual seguradora oferece, em média, a melhor cobertura para crédito rural?”. Abra o detalhe da ferramenta usada.",
    f: "Por fim, uma pergunta em português: qual seguradora oferece a melhor cobertura para crédito rural? O agente escolhe onde procurar, consulta a base e mostra a tabela que usou." },
];

async function icone(Comp, cor, tam = 256) {
  const svg = ReactDOMServer.renderToStaticMarkup(
    React.createElement(Comp, { color: "#" + cor, size: tam }));
  const buf = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}

(async () => {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
  pres.title = "InsurMinds — Projeto Final — como construí e como funciona";
  pres.author = "Jefferson Luiz Gonçalves Silva";
  pres.company = "InsurMinds / I2A2";
  pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
  const C = pres.SchemeColor;

  // ---------------------------------------------------------------- layouts
  pres.defineSlideMaster({
    title: "Capa escura",
    background: { color: H.dk2 },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.8, y: 1.9, w: 11.7, h: 2.1,
        fontSize: 40, bold: true, color: C.background1, valign: "bottom" }, text: "" } },
      { placeholder: { options: { name: "body", type: "body", x: 0.8, y: 4.2, w: 11.7, h: 1.6,
        fontSize: 18, color: C.background2, valign: "top" }, text: "" } },
    ],
  });
  pres.defineSlideMaster({
    title: "Demonstração",
    background: { color: H.dk2 },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.4, w: 12.1, h: 0.95,
        fontSize: 32, bold: true, color: C.background1, valign: "middle" }, text: "" } },
    ],
    slideNumber: { x: 12.3, y: 7.0, w: 0.5, h: 0.3, fontSize: 10, color: H.accent6 },
  });
  pres.defineSlideMaster({
    title: "Conteúdo",
    background: { color: H.lt1 },
    margin: [0.5, 0.6, 0.6, 0.6],
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.35, w: 12.1, h: 0.95,
        fontSize: 30, bold: true, color: C.text2, valign: "middle" }, text: "" } },
      { text: { text: "AgroSentinela · Projeto Final InsurMinds/I2A2 · apólices simuladas, nomes fictícios", options: {
        x: 0.6, y: 7.0, w: 9, h: 0.3, fontSize: 10, color: C.accent5 } } },
    ],
    slideNumber: { x: 12.3, y: 7.0, w: 0.5, h: 0.3, fontSize: 10, color: H.accent5 },
  });

  // helpers
  const card = (s, x, y, w, h, fill = C.background2) =>
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.12,
      fill: { color: fill }, line: { color: fill } });
  const txt = (s, t, o) => s.addText(t, { isTextBox: true, margin: 0, ...o });
  const bolinha = async (s, ic, x, y, d = 0.9, fundo = H.dk2, cor = H.accent2) => {
    s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fundo }, line: { color: fundo } });
    s.addImage({ data: await icone(ic, cor), x: x + d * 0.24, y: y + d * 0.24, w: d * 0.52, h: d * 0.52 });
  };
  const notas = (s, n) => s.addNotes(`[${NARR[n].t}] ${NARR[n].f}`);

  // ================================================================ 1 capa
  pres.addSection({ title: "Abertura" });
  let s = pres.addSlide({ masterName: "Capa escura", sectionTitle: "Abertura" });
  s.addText("Comparar o seguro dos dirigentes do agro, com ajuda de inteligência artificial",
    { placeholder: "title" });
  s.addText([
    { text: "Projeto Final InsurMinds / I2A2 · como eu construí e como funciona", options: { breakLine: true } },
    { text: "Jefferson Luiz Gonçalves Silva · outubro de 2026", options: { color: C.accent2 } },
  ], { placeholder: "body" });
  s.addImage({ data: await icone(fi.FiShield, H.accent2), x: 0.8, y: 0.8, w: 0.9, h: 0.9 });
  notas(s, 1);

  // ================================================================ 2 problema
  pres.addSection({ title: "Problema e ideia" });
  s = pres.addSlide({ masterName: "Conteúdo", sectionTitle: "Problema e ideia" });
  s.addText("Um seguro importante, que quase ninguém consegue comparar", { placeholder: "title" });
  card(s, 0.6, 1.5, 5.2, 5.2, H.dk2);
  await bolinha(s, fi.FiShield, 0.95, 1.85, 1.0, H.accent2, H.dk2);
  txt(s, "O que é o seguro D&O?", { x: 0.95, y: 3.05, w: 4.5, h: 0.5, fontSize: 22, bold: true, color: C.background1 });
  txt(s, "Protege o patrimônio pessoal de diretores e conselheiros quando são processados por decisões tomadas na empresa ou na cooperativa.",
    { x: 0.95, y: 3.65, w: 4.5, h: 1.5, fontSize: 17, color: C.background1 });
  txt(s, "D&O = Directors and Officers (dirigentes)", { x: 0.95, y: 5.9, w: 4.5, h: 0.4, fontSize: 13, italic: true, color: C.accent6 });
  const dores = [
    [fi.FiFileText, "Letras miúdas", "Cada apólice tem de 20 a 40 cláusulas, em linguagem jurídica."],
    [fi.FiShuffle, "Cada seguradora escreve de um jeito", "A mesma cobertura muda de nome, de lugar e de redação."],
    [fi.FiTrendingDown, "A mais barata pode proteger menos", "As diferenças que pesam num processo ficam escondidas no texto."],
    [fi.FiSun, "No agro, riscos próprios", "Crédito rural e Proagro, meio ambiente, recuperação judicial."],
  ];
  let y = 1.5;
  for (const [ic, t, d] of dores) {
    await bolinha(s, ic, 6.2, y + 0.12, 0.85);
    txt(s, t, { x: 7.3, y: y + 0.05, w: 5.4, h: 0.45, fontSize: 18, bold: true, color: C.text2 });
    txt(s, d, { x: 7.3, y: y + 0.52, w: 5.4, h: 0.6, fontSize: 15, color: C.text1 });
    y += 1.33;
  }
  notas(s, 2);

  // ================================================================ 3 ideia
  s = pres.addSlide({ masterName: "Conteúdo", sectionTitle: "Problema e ideia" });
  s.addText("A ideia: um assistente que lê, organiza, compara e explica", { placeholder: "title" });
  const passos = [
    [fi.FiCamera, "Lê", "PDF, documento escaneado ou foto da apólice"],
    [fi.FiGrid, "Organiza", "Valores e 32 tipos de cláusula numa base de dados"],
    [fi.FiColumns, "Compara", "Lado a lado, com as lacunas de cobertura"],
    [fi.FiMessageCircle, "Explica", "Relatório em português e respostas a perguntas"],
  ];
  passos.forEach(([ic, t, d], i) => {
    const x = 0.6 + i * 3.1;
    card(s, x, 1.6, 2.85, 3.1);
    txt(s, t, { x: x + 0.3, y: 2.95, w: 2.3, h: 0.55, fontSize: 24, bold: true, color: C.text2 });
    txt(s, d, { x: x + 0.3, y: 3.55, w: 2.35, h: 1.0, fontSize: 15, color: C.text1 });
  });
  for (let i = 0; i < passos.length; i++) await bolinha(s, passos[i][0], 0.9 + i * 3.1, 1.85, 0.95);
  card(s, 0.6, 5.0, 12.1, 1.7, H.dk2);
  s.addImage({ data: await icone(fi.FiLink, H.accent2), x: 0.95, y: 5.5, w: 0.7, h: 0.7 });
  txt(s, [
    { text: "Não comecei do zero. ", options: { bold: true, color: C.accent2 } },
    { text: "O projeto é um módulo novo do AgroSentinela, o app que fiz no Desafio 5, que já usa dados públicos de crédito rural e do Proagro (Banco Central). Uma ferramenta só: do alerta de risco no campo ao seguro de quem dirige a empresa." },
  ], { x: 1.95, y: 5.15, w: 10.5, h: 1.4, fontSize: 16, color: C.background1, valign: "middle" });
  notas(s, 3);

  // ================================================================ 4 três IAs
  pres.addSection({ title: "Como trabalhei" });
  s = pres.addSlide({ masterName: "Conteúdo", sectionTitle: "Como trabalhei" });
  s.addText("Três IAs, três papéis — e as decisões ficaram comigo", { placeholder: "title" });
  const papeis = [
    [fi.FiUser, "Eu", "Direção e revisão", "Defini as premissas, revisei cada entrega, critiquei o que não estava realista e decidi o que entrava.", H.accent1],
    [fi.FiCode, "Claude (Anthropic)", "Assistente de desenvolvimento", "Pesquisou referências, escreveu o código, os testes, a documentação e a primeira versão desta apresentação.", H.accent3],
    [fi.FiCpu, "IA da Groq (GPT-OSS)", "Dentro do aplicativo", "Lê as apólices, preenche a ficha, entende as cláusulas, escreve relatórios e responde perguntas.", H.accent2],
    [fi.FiCopy, "Outra IA, à escolha", "Para ampliar a base", "Recebe um roteiro pronto (prompt) para gerar novas apólices simuladas em PDF.", H.accent5],
  ];
  for (let i = 0; i < papeis.length; i++) {
    const [ic, t, sub, d, cor] = papeis[i];
    const x = 0.6 + i * 3.1;
    card(s, x, 1.6, 2.85, 4.0);
    await bolinha(s, ic, x + 0.3, 1.9, 1.0, cor, H.lt1);
    txt(s, t, { x: x + 0.3, y: 3.1, w: 2.35, h: 0.55, fontSize: 19, bold: true, color: C.text2, valign: "top" });
    txt(s, sub, { x: x + 0.3, y: 3.7, w: 2.35, h: 0.6, fontSize: 14, bold: true, color: C.accent5, valign: "top" });
    txt(s, d, { x: x + 0.3, y: 4.4, w: 2.35, h: 1.15, fontSize: 14, color: C.text1, valign: "top" });
  }
  card(s, 0.6, 5.85, 12.1, 0.85, H.dk2);
  txt(s, [
    { text: "Na prática: ", options: { bold: true, color: C.accent2 } },
    { text: "eu descrevia em português o que queria; o Claude implementava e mostrava o resultado; eu revisava e pedia ajustes." },
  ], { x: 0.95, y: 5.85, w: 11.5, h: 0.85, fontSize: 16, color: C.background1, valign: "middle" });
  notas(s, 4);

  // ================================================================ 5 linha do tempo
  s = pres.addSlide({ masterName: "Conteúdo", sectionTitle: "Como trabalhei" });
  s.addText("Como o trabalho aconteceu, passo a passo", { placeholder: "title" });
  const etapas = [
    ["Ler o enunciado", "Decidi não começar do zero: integrar ao app do Desafio 5."],
    ["Definir premissas", "IA pela Groq (plano gratuito), agentes, foco rural, modelos sem data de saída próxima."],
    ["Construir com o Claude", "1ª versão completa: app, 45 apólices simuladas, relatório e apresentação."],
    ["Revisar com olhar crítico", "“Apólices de empresas diferentes não seguem o mesmo modelo.”"],
    ["Refazer a base", "6 seguradoras, 120 apólices, todas as regiões."],
    ["Testar com docs reais", "5 documentos enviados por um colega mostraram falhas novas."],
    ["Medir e publicar", "Gabaritos, 204 testes automáticos, GitHub e Streamlit."],
  ];
  s.addShape(pres.shapes.LINE, { x: 1.1, y: 2.35, w: 10.6, h: 0, line: { color: H.accent6, width: 3 } });
  etapas.forEach(([t, d], i) => {
    const x = 0.6 + i * 1.755;
    const destaque = i === 3 || i === 5;
    s.addShape(pres.shapes.OVAL, { x: x + 0.38, y: 1.9, w: 0.9, h: 0.9,
      fill: { color: destaque ? H.accent4 : H.accent1 }, line: { color: H.lt1, width: 2 } });
    txt(s, String(i + 1), { x: x + 0.38, y: 1.9, w: 0.9, h: 0.9, fontSize: 26, bold: true,
      color: C.background1, align: "center", valign: "middle" });
    card(s, x, 3.05, 1.665, 3.3, destaque ? "FBEDEB" : C.background2);
    txt(s, t, { x: x + 0.13, y: 3.2, w: 1.42, h: 0.8, fontSize: 15, bold: true,
      color: destaque ? C.accent4 : C.text2, valign: "top" });
    txt(s, d, { x: x + 0.13, y: 4.1, w: 1.42, h: 2.15, fontSize: 14, color: C.text1, valign: "top",
      italic: i === 3 });
  });
  notas(s, 5);

  // ================================================================ 6 por que simular
  pres.addSection({ title: "Apólices simuladas" });
  s = pres.addSlide({ masterName: "Conteúdo", sectionTitle: "Apólices simuladas" });
  s.addText("Por que simular apólices em vez de usar reais?", { placeholder: "title" });
  const motivos = [
    [fi.FiLock, "Apólices emitidas são confidenciais", "Trazem dados de empresas, pessoas e valores. Só as condições gerais (texto-padrão) são públicas."],
    [fi.FiCheckSquare, "Simulação tem gabarito", "Sei a resposta certa de cada apólice e posso medir quanto o sistema acerta, como numa prova corrigida."],
    [fi.FiMap, "Cobre o Brasil inteiro", "Dá para montar cenários de todas as regiões e portes, que uma amostra real pequena não teria."],
  ];
  for (let i = 0; i < motivos.length; i++) {
    const [ic, t, d] = motivos[i];
    const yy = 1.55 + i * 1.75;
    card(s, 0.6, yy, 7.3, 1.55);
    await bolinha(s, ic, 0.9, yy + 0.3, 0.95);
    txt(s, t, { x: 2.15, y: yy + 0.2, w: 5.5, h: 0.45, fontSize: 18, bold: true, color: C.text2 });
    txt(s, d, { x: 2.15, y: yy + 0.68, w: 5.5, h: 0.8, fontSize: 15, color: C.text1 });
  }
  card(s, 8.2, 1.55, 4.5, 5.05, H.dk2);
  s.addImage({ data: await icone(fi.FiAlertTriangle, H.accent2), x: 8.55, y: 1.85, w: 0.7, h: 0.7 });
  txt(s, "Tudo declarado", { x: 9.4, y: 1.9, w: 3.1, h: 0.6, fontSize: 22, bold: true, color: C.background1 });
  txt(s, [
    { text: "Marca d'água “USO ACADÊMICO” em todas as páginas", options: { bullet: true, breakLine: true } },
    { text: "Aviso de documento simulado no topo e no rodapé", options: { bullet: true, breakLine: true } },
    { text: "Seguradoras, empresas, CNPJs e valores inventados", options: { bullet: true, breakLine: true } },
    { text: "Nenhuma empresa real é imitada: um nome que coincidia com uma seguradora real foi trocado", options: { bullet: true } },
  ], { x: 8.55, y: 2.8, w: 3.9, h: 3.6, fontSize: 15, color: C.background1, paraSpaceAfter: 10, valign: "top" });
  notas(s, 6);

  // ================================================================ 7 antes e depois
  s = pres.addSlide({ masterName: "Conteúdo", sectionTitle: "Apólices simuladas" });
  s.addText("A revisão que mudou o projeto: antes e depois", { placeholder: "title" });
  txt(s, "ANTES · 1ª versão", { x: 0.6, y: 1.45, w: 5.7, h: 0.4, fontSize: 16, bold: true, color: C.accent4 });
  s.addImage({ path: CAP("v1_modelo_unico.png"), x: 0.6, y: 1.9, w: 5.7, h: 2.6 });
  txt(s, "45 apólices e 12 nomes de seguradora, mas um único modelo de documento: só mudavam o nome e a cor.",
    { x: 0.6, y: 4.6, w: 5.7, h: 0.75, fontSize: 14, color: C.text1 });
  card(s, 0.6, 5.5, 5.7, 1.25);
  txt(s, [
    { text: "O mesmo valor, quatro jeitos de escrever:", options: { bold: true, color: C.text2, breakLine: true } },
    { text: "R$ 5.000.000,00 · R$ 5 milhões · BRL 5,000,000.00 · cinco milhões de reais" },
  ], { x: 0.85, y: 5.6, w: 5.3, h: 1.05, fontSize: 14, color: C.text1, valign: "middle" });
  txt(s, "DEPOIS · 2ª versão", { x: 6.7, y: 1.45, w: 6.0, h: 0.4, fontSize: 16, bold: true, color: C.accent1 });
  s.addImage({ path: CAP("modelos_documento.png"), x: 6.7, y: 1.9, w: 6.0, h: 3.76 });
  txt(s, "6 seguradoras fictícias, cada uma com o seu jeito: numeração, ordem, vocabulário, perguntas e respostas, até em inglês. Estrutura inspirada em condições gerais públicas (AIG, Allianz, Tokio Marine, Sompo), sem copiar texto.",
    { x: 6.7, y: 5.75, w: 6.0, h: 1.0, fontSize: 14, color: C.text1 });
  notas(s, 7);

  // ================================================================ 8 brasis
  s = pres.addSlide({ masterName: "Conteúdo", sectionTitle: "Apólices simuladas" });
  s.addText("Os vários Brasis rurais dentro da base", { placeholder: "title" });
  const stats = [["120", "apólices"], ["6", "seguradoras"], [String(N_TOM), "empresas e cooperativas"], ["25 + DF", "estados"]];
  stats.forEach(([n, l], i) => {
    const x = 0.6 + i * 3.05;
    card(s, x, 1.45, 2.85, 1.35);
    txt(s, n, { x, y: 1.5, w: 2.85, h: 0.85, fontSize: 40, bold: true, color: C.accent1, align: "center", valign: "middle" });
    txt(s, l, { x, y: 2.35, w: 2.85, h: 0.35, fontSize: 14, color: C.text1, align: "center" });
  });
  const ordem = ["Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul"];
  s.addChart(pres.charts.BAR, [{ name: "Empresas e cooperativas", labels: ordem, values: ordem.map((r) => tomPorRegiao[r] || 0) }], {
    x: 0.6, y: 3.05, w: 4.9, h: 3.75, barDir: "bar", showTitle: true,
    title: "Empresas e cooperativas por região", titleFontSize: 13, titleColor: H.dk1, titleFontFace: "+mn-lt",
    chartColors: [H.accent1], showValue: true, dataLabelPosition: "outEnd", dataLabelColor: H.dk1,
    dataLabelFontSize: 12, dataLabelFontFace: "+mn-lt", catAxisLabelColor: H.dk1, catAxisLabelFontSize: 12,
    catAxisLabelFontFace: "+mn-lt", valAxisHidden: true, valGridLine: { style: "none" },
    catGridLine: { style: "none" }, showLegend: false, catAxisOrientation: "maxMin" });
  card(s, 5.8, 3.05, 6.9, 3.75);
  txt(s, [
    { text: "Norte: ", options: { bold: true, color: C.accent1 } },
    { text: "castanha em Xapuri (AC), açaí em Cametá (PA). Pesa o risco ambiental.", options: { breakLine: true } },
    { text: "Nordeste: ", options: { bold: true, color: C.accent1 } },
    { text: "mel em Picos (PI), frutas irrigadas em Petrolina (PE). Pesa a seca.", options: { breakLine: true } },
    { text: "Centro-Oeste: ", options: { bold: true, color: C.accent1 } },
    { text: "trading de grãos em Sorriso (MT), pecuária no Pantanal.", options: { breakLine: true } },
    { text: "Sudeste: ", options: { bold: true, color: C.accent1 } },
    { text: "café em Três Pontas (MG), queijo artesanal no Serro (MG).", options: { breakLine: true } },
    { text: "Sul: ", options: { bold: true, color: C.accent1 } },
    { text: "arroz em Uruguaiana (RS), crédito cooperativo em Chapecó (SC).", options: { breakLine: true } },
    { text: "Do pequeno ao grande: limite de R$ 500 mil (cooperativa familiar) a R$ 160 milhões (agroindústria).", options: { italic: true, color: C.accent5 } },
  ], { x: 6.1, y: 3.2, w: 6.35, h: 3.45, fontSize: 14, color: C.text1, paraSpaceAfter: 6, valign: "top" });
  notas(s, 8);

  // ================================================================ 9 outra IA
  s = pres.addSlide({ masterName: "Conteúdo", sectionTitle: "Apólices simuladas" });
  s.addText("Usar outra IA para ampliar a base, sem perder o controle", { placeholder: "title" });
  const fluxo = [
    [fi.FiEdit3, "Prompt pronto", "Regras: só nomes fictícios, marca d'água, regiões, 32 tipos de cláusula, gabarito."],
    [fi.FiCpu, "Outra IA gera", "Novas apólices em PDF e o gabarito de cada uma."],
    [fi.FiFilter, "Importador confere", "Nome de empresa real? Marca d'água? Datas e valores coerentes? Códigos válidos?"],
    [fi.FiDatabase, "Entra na base", "E passa a fazer parte da medição de acerto."],
  ];
  for (let i = 0; i < fluxo.length; i++) {
    const [ic, t, d] = fluxo[i];
    const x = 0.6 + i * 3.1;
    card(s, x, 1.6, 2.75, 3.2, i === 2 ? "FBF3E2" : C.background2);
    await bolinha(s, ic, x + 0.3, 1.85, 0.95);
    txt(s, t, { x: x + 0.3, y: 2.95, w: 2.25, h: 0.5, fontSize: 19, bold: true, color: C.text2 });
    txt(s, d, { x: x + 0.3, y: 3.5, w: 2.25, h: 1.25, fontSize: 14, color: C.text1, valign: "top" });
    if (i < 3) s.addShape(pres.shapes.LINE, { x: x + 2.8, y: 3.2, w: 0.25, h: 0,
      line: { color: H.accent5, width: 2, endArrowType: "triangle" } });
  }
  card(s, 0.6, 5.1, 12.1, 1.6, H.dk2);
  s.addImage({ data: await icone(fi.FiInfo, H.accent2), x: 0.95, y: 5.55, w: 0.7, h: 0.7 });
  txt(s, [
    { text: "Sendo transparente: ", options: { bold: true, color: C.accent2 } },
    { text: "o prompt e o importador estão prontos e cobertos por testes automáticos, mas ainda não foram usados. As 120 apólices atuais foram geradas por um programa que escrevi com o Claude." },
  ], { x: 1.95, y: 5.2, w: 10.5, h: 1.4, fontSize: 16, color: C.background1, valign: "middle" });
  notas(s, 9);

  // ================================================================ 10 documentos reais
  s = pres.addSlide({ masterName: "Conteúdo", sectionTitle: "Apólices simuladas" });
  s.addText("O teste com documentos reais: o que quebrou e o que mudou", { placeholder: "title" });
  card(s, 0.6, 1.5, 3.9, 5.1, H.dk2);
  await bolinha(s, fi.FiFolder, 0.9, 1.8, 0.9, H.accent2, H.dk2);
  txt(s, "5 documentos reais", { x: 0.9, y: 2.9, w: 3.4, h: 0.5, fontSize: 20, bold: true, color: C.background1 });
  txt(s, [
    { text: "3 condições gerais de D&O: AXA (104 p.), Allianz (75 p.) e Porto (52 p.)", options: { bullet: true, breakLine: true } },
    { text: "2 apólices de Seguro Garantia, outro ramo, com dados de terceiros", options: { bullet: true, breakLine: true } },
    { text: "Enviados por um colega; ficaram fora do GitHub", options: { bullet: true } },
  ], { x: 0.9, y: 3.5, w: 3.4, h: 2.9, fontSize: 14, color: C.background1, paraSpaceAfter: 8, valign: "top" });
  card(s, 4.75, 1.5, 3.9, 5.1);
  await bolinha(s, fi.FiAlertTriangle, 5.05, 1.8, 0.9, H.accent4, H.lt1);
  txt(s, "O que o teste revelou", { x: 5.05, y: 2.9, w: 3.4, h: 0.5, fontSize: 20, bold: true, color: C.text2 });
  txt(s, [
    { text: "A IA só via o começo dos documentos longos: cerca de 6% do texto", options: { bullet: true, breakLine: true } },
    { text: "Um Seguro Garantia entraria na base como se fosse D&O", options: { bullet: true, breakLine: true } },
    { text: "Sumário e glossário confundiam a leitura", options: { bullet: true } },
  ], { x: 5.05, y: 3.5, w: 3.4, h: 2.9, fontSize: 14, color: C.text1, paraSpaceAfter: 8, valign: "top" });
  card(s, 8.9, 1.5, 3.8, 5.1);
  await bolinha(s, fi.FiCheckCircle, 9.2, 1.8, 0.9, H.accent1, H.lt1);
  txt(s, "Depois das correções", { x: 9.2, y: 2.9, w: 3.3, h: 0.5, fontSize: 20, bold: true, color: C.text2 });
  const antesDepois = [
    ["Trechos-chave que chegam à IA", "5%", "56%"],
    ["Outro ramo recusado", "0 de 2", RR ? `${RR.fora_do_escopo_recusados} de ${RR.fora_do_escopo_total}` : "—"],
    ["Cláusulas encontradas (regras)", "64%", RR_PRES],
  ];
  antesDepois.forEach(([rot, a, d], k) => {
    const yy = 3.5 + k * 0.98;
    txt(s, rot, { x: 9.2, y: yy, w: 3.3, h: 0.35, fontSize: 14, color: C.text1 });
    txt(s, [
      { text: a, options: { color: C.accent5 } },
      { text: "  →  ", options: { color: C.accent5 } },
      { text: d, options: { bold: true, color: C.accent1 } },
    ], { x: 9.2, y: yy + 0.36, w: 3.3, h: 0.45, fontSize: 20 });
  });
  txt(s, "Gabarito dos documentos reais anotado com apoio de IA e conferido por script; os níveis precisam de revisão de especialista. Medido nos mesmos documentos usados para ajustar o sistema.",
    { x: 0.6, y: 6.65, w: 11.6, h: 0.3, fontSize: 10, italic: true, color: C.accent5 });
  notas(s, 10);


  // ================================================================ 10 agentes
  pres.addSection({ title: "Como funciona" });
  s = pres.addSlide({ masterName: "Conteúdo", sectionTitle: "Como funciona" });
  s.addText("Por dentro do app: uma linha de montagem de 10 agentes", { placeholder: "title" });
  const linhas = [
    ["LER A APÓLICE", 1.5, [["Recebe", 0], ["Lê o texto (e a foto)", 0], ["Preenche a ficha", 1], ["Entende as cláusulas", 1], ["Confere", 0], ["Guarda", 0]]],
    ["COMPARAR", 2.85, [["Perfil da região (dados do BCB)", 0], ["Compara e dá nota", 0], ["Escreve o relatório", 1]]],
    ["PERGUNTAR", 4.2, [["Responde perguntas consultando a base", 1]]],
  ];
  for (const [nome, yy, ags] of linhas) {
    txt(s, nome, { x: 0.6, y: yy + 0.25, w: 1.9, h: 0.5, fontSize: 14, bold: true, color: C.accent5 });
    const w = ags.length > 3 ? 1.55 : (ags.length > 1 ? 3.25 : 5.0);
    ags.forEach(([a, ia], i) => {
      const x = 2.6 + i * (w + 0.13);
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: yy, w, h: 1.0, rectRadius: 0.1,
        fill: { color: ia ? H.accent2 : H.accent1 }, line: { color: ia ? H.accent2 : H.accent1 } });
      txt(s, a, { x: x + 0.08, y: yy, w: w - 0.16, h: 1.0, fontSize: 14, bold: true,
        color: ia ? C.text1 : C.background1, align: "center", valign: "middle" });
    });
  }
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 8.0, y: 4.55, w: 0.35, h: 0.3, rectRadius: 0.05, fill: { color: H.accent2 }, line: { color: H.accent2 } });
  txt(s, "usa IA (Groq)", { x: 8.45, y: 4.53, w: 1.6, h: 0.35, fontSize: 13, color: C.text1 });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 10.15, y: 4.55, w: 0.35, h: 0.3, rectRadius: 0.05, fill: { color: H.accent1 }, line: { color: H.accent1 } });
  txt(s, "regras fixas", { x: 10.6, y: 4.53, w: 1.6, h: 0.35, fontSize: 13, color: C.text1 });
  card(s, 0.6, 5.45, 12.1, 1.3);
  txt(s, [
    { text: "Por que nem tudo é IA? ", options: { bold: true, color: C.accent1 } },
    { text: "A IA é ótima para ler textos escritos de jeitos diferentes e para escrever. Notas, contas e comparações ficam com regras fixas: sempre dão o mesmo resultado e podem ser conferidas. Modelos: GPT-OSS na Groq; os Llama 3 usados antes saíram do plano gratuito.", options: {} },
  ], { x: 0.9, y: 5.55, w: 11.5, h: 1.1, fontSize: 15, color: C.text1, valign: "middle" });
  notas(s, 11);

  // ================================================================ 11 não inventar
  s = pres.addSlide({ masterName: "Conteúdo", sectionTitle: "Como funciona" });
  s.addText("Como evitamos que a IA invente coisas", { placeholder: "title" });
  const gc = [
    [fi.FiList, "Respostas em formato fechado", "Para cada cláusula, a IA só pode escolher: ampla, padrão, restrita, ausente ou excluída."],
    [fi.FiSearch, "Prova do que leu", "Cada resposta cita o trecho do documento. O sistema confere se o trecho existe mesmo."],
    [fi.FiHash, "Números conferidos", "Limite, preço e franquia são checados no texto da apólice. Em caso de dúvida, vale o documento."],
    [fi.FiCheckSquare, "Relatório auditado", "Todo número citado no relatório precisa existir nos dados. Se não existir, aparece um alerta."],
  ];
  for (let i = 0; i < 4; i++) {
    const [ic, t, d] = gc[i];
    const x = 0.6 + (i % 2) * 6.15, yy = 1.55 + Math.floor(i / 2) * 2.6;
    card(s, x, yy, 5.95, 2.35);
    await bolinha(s, ic, x + 0.3, yy + 0.35, 0.95);
    txt(s, t, { x: x + 1.5, y: yy + 0.35, w: 4.2, h: 0.5, fontSize: 19, bold: true, color: C.text2 });
    txt(s, d, { x: x + 1.5, y: yy + 0.9, w: 4.2, h: 1.3, fontSize: 15, color: C.text1 });
  }
  notas(s, 12);

  // ================================================================ 12 demo
  pres.addSection({ title: "Demonstração" });
  s = pres.addSlide({ masterName: "Demonstração", sectionTitle: "Demonstração" });
  s.addText("Agora, o aplicativo funcionando", { placeholder: "title" });
  const demo = [
    ["1", "Ler", "Duas apólices bem diferentes: uma da Ipê-Roxo e uma escaneada da Mutirão", "02_ingestao_resultado.png"],
    ["2", "Comparar", "As 4 propostas da Grão Norte, trading de Sorriso (MT)", "07b_diferencas.png"],
    ["3", "Perguntar", "“Qual seguradora tem a melhor cobertura para crédito rural?”", "09_consulta.png"],
  ];
  demo.forEach(([n, t, d, img], i) => {
    const x = 0.6 + i * 4.1;
    s.addImage({ path: CAP(img), x, y: 1.6, w: 3.85, h: 2.66 });
    s.addShape(pres.shapes.OVAL, { x, y: 4.5, w: 0.7, h: 0.7, fill: { color: H.accent2 }, line: { color: H.accent2 } });
    txt(s, n, { x, y: 4.5, w: 0.7, h: 0.7, fontSize: 22, bold: true, color: C.text1, align: "center", valign: "middle" });
    txt(s, t, { x: x + 0.9, y: 4.5, w: 2.9, h: 0.7, fontSize: 22, bold: true, color: C.background1, valign: "middle" });
    txt(s, d, { x, y: 5.35, w: 3.85, h: 1.1, fontSize: 15, color: C.background2, valign: "top" });
  });
  s.addNotes(`[${NARR[13].t}] ${NARR[13].f}\n\n` + DEMO.map((d, i) =>
    `DEMO ${i + 1} [${d.t}] ${d.tela.replace(/\*/g, "")}: ${d.acao.replace(/\*/g, "")}\nFala: ${d.f}`).join("\n\n"));

  // ================================================================ 13 resultados
  pres.addSection({ title: "Resultados" });
  s = pres.addSlide({ masterName: "Conteúdo", sectionTitle: "Resultados" });
  s.addText("Quanto o sistema acerta, medido contra o gabarito", { placeholder: "title" });
  const NOMES = { ATA: "Atalaia", IPE: "Ipê-Roxo", JAC: "Jacarandá", XIQ: "Xique-Xique",
                  MUT: "Mutirão (linguagem simples)", MIN: "Minuano (bilíngue)" };
  const segs = Object.keys(R.linha_de_base);
  s.addChart(pres.charts.BAR, [
    { name: "Valores da apólice", labels: segs.map((k) => NOMES[k] || k), values: segs.map((k) => R.linha_de_base[k].acuracia_campos) },
    { name: "Cláusulas", labels: segs.map((k) => NOMES[k] || k), values: segs.map((k) => R.linha_de_base[k].acuracia_clausulas) },
  ], {
    x: 0.6, y: 1.45, w: 7.4, h: 5.3, barDir: "bar", barGrouping: "clustered", showTitle: true,
    title: `Acerto (%) só com regras fixas, por seguradora · ${R.apolices} apólices`,
    titleFontSize: 13, titleColor: H.dk1, titleFontFace: "+mn-lt", chartColors: [H.accent3, H.accent2],
    showValue: true, dataLabelPosition: "outEnd", dataLabelColor: H.dk1, dataLabelFontSize: 11,
    dataLabelFontFace: "+mn-lt", dataLabelFormatCode: "0", valAxisMaxVal: 100, valAxisMinVal: 0,
    catAxisLabelColor: H.dk1, catAxisLabelFontSize: 12, catAxisLabelFontFace: "+mn-lt",
    valAxisHidden: true, valGridLine: { style: "none" }, catAxisOrientation: "maxMin",
    catGridLine: { style: "none" }, showLegend: true, legendPos: "b", legendFontFace: "+mn-lt", legendFontSize: 12 });
  card(s, 8.3, 1.45, 4.4, 5.3);
  const ladoIA = IA
    ? [{ text: `Com a IA (Groq): ${pct(IA.acuracia_campos)} dos valores e ${pct(IA.acuracia_clausulas)} das cláusulas, em ${R.apolices_ia} apólices.`, options: { bullet: true, bold: true } }]
    : [{ text: "Com a IA: a mesma régua mede a leitura pela Groq. Na demonstração, a aba “Qualidade da extração” mostra a conferência ao vivo.", options: { bullet: true } }];
  txt(s, [
    { text: "Como ler o gráfico", options: { bold: true, color: C.accent1, breakLine: true } },
    { text: `Só com regras fixas, o sistema lê bem os valores: ${pct(TB.acuracia_campos)} no total.`, options: { bullet: true, breakLine: true } },
    { text: `Mas acerta só ${pct(TB.acuracia_clausulas)} das cláusulas, e ${pct(MUT)} no documento em linguagem simples, que não usa os termos técnicos.`, options: { bullet: true, breakLine: true } },
    { text: `Nas 3 condições gerais reais: ${RR_PRES} das cláusulas encontradas.`, options: { bullet: true, breakLine: true } },
    ...ladoIA,
  ], { x: 8.55, y: 1.65, w: 3.95, h: 4.9, fontSize: 15, color: C.text1, paraSpaceAfter: 9, valign: "top" });
  notas(s, 14);

  // ================================================================ 14 aprendizados
  s = pres.addSlide({ masterName: "Conteúdo", sectionTitle: "Resultados" });
  s.addText("O que aprendi, os limites e os próximos passos", { placeholder: "title" });
  const col = [
    [fi.FiStar, "Aprendi", H.accent1, [
      "A IA acelera muito, mas foi a revisão humana que deixou o projeto realista",
      "Documento real mostra o que a simulação esconde",
      "IA para ler e escrever; regras para decidir e calcular"]],
    [fi.FiAlertCircle, "Limites", H.accent4, [
      "Teste real ainda pequeno: 3 condições gerais",
      "Plano gratuito da Groq limita a velocidade",
      "Ferramenta de apoio: não substitui corretor nem advogado"]],
    [fi.FiArrowRightCircle, "Próximos passos", H.accent3, [
      "Testar com apólices D&O emitidas, com autorização",
      "Gerar novos lotes com outra IA",
      "Ajustar os pesos ouvindo corretores"]],
  ];
  for (let i = 0; i < 3; i++) {
    const [ic, t, cor, itens] = col[i];
    const x = 0.6 + i * 4.1;
    card(s, x, 1.5, 3.85, 4.5);
    await bolinha(s, ic, x + 0.3, 1.8, 0.85, cor, H.lt1);
    txt(s, t, { x: x + 1.35, y: 1.95, w: 2.3, h: 0.55, fontSize: 21, bold: true, color: C.text2 });
    txt(s, itens.map((it, j) => ({ text: it, options: { bullet: true, breakLine: j < itens.length - 1 } })),
      { x: x + 0.3, y: 2.95, w: 3.3, h: 2.9, fontSize: 15, color: C.text1, paraSpaceAfter: 12, valign: "top" });
  }
  notas(s, 15);

  // ================================================================ 15 fechamento
  pres.addSection({ title: "Fechamento" });
  s = pres.addSlide({ masterName: "Capa escura", sectionTitle: "Fechamento" });
  s.addText("Obrigado!", { placeholder: "title" });
  s.addText([
    { text: "github.com/jlgsilva/insurminds-projeto-final · código aberto, licença MIT", options: { breakLine: true, color: C.accent2 } },
    { text: "Feito com Python, Streamlit, Groq (GPT-OSS), Tesseract e dados públicos do Banco Central.", options: { breakLine: true } },
    { text: "Desenvolvido com apoio do Claude (Anthropic). Acervo de demonstração simulado; validado também em 5 documentos reais." },
  ], { placeholder: "body" });
  notas(s, 16);

  await pres.writeFile({ fileName: SAIDA });
  if (APPLY) {
    const { applyTheme } = require(APPLY);
    await applyTheme(SAIDA, THEME);
  }
  console.log("ok", SAIDA);

  // ---------------------------------------------------------------- roteiro
  const TELAS = { 1: "Capa", 2: "O problema", 3: "A ideia", 4: "Três IAs, três papéis", 5: "Passo a passo",
    6: "Por que simular", 7: "Antes e depois", 8: "Os vários Brasis", 9: "Outra IA para ampliar a base",
    10: "O teste com documentos reais", 11: "Linha de montagem de agentes",
    12: "Como evitamos que a IA invente (apoio, sem narração)", 13: "Demonstração (transição)",
    14: "Resultados", 15: "Aprendizados", 16: "Obrigado" };
  const md = [];
  md.push("# Roteiro do vídeo narrado (máx. 5 min)", "",
    "Texto de referência para gravar a narração **em primeira pessoa**, alternando a apresentação",
    "(`InsurMinds_Projeto_Final.pptx`) e o **app rodando ao vivo** no Streamlit. O mesmo texto está nas",
    "notas de cada slide (modo apresentador do PowerPoint). Gerado por `node scripts/gerar_pitch_deck.js`.", "",
    "## Antes de gravar", "",
    "- Abra o app (local ou Streamlit Cloud) com a chave da Groq configurada e **rode a ingestão e a comparação uma vez antes**: as respostas ficam em cache e a gravação fica mais rápida.",
    "- Deixe duas janelas prontas: a apresentação em tela cheia e o navegador com o app (zoom em 90%).",
    "- Feche notificações. Se a Groq demorar (limite do plano gratuito), corte a espera na edição.",
    "- O tempo total fica perto de **5 min**, o limite do enunciado: o slide 12 não tem narração (passe direto) e as falas podem ser encurtadas.",
    "- **Não mostre na tela as apólices de Seguro Garantia** enviadas pelo colega: têm dados reais de empresas e pessoas. Se quiser mostrar um documento real, use uma das condições gerais públicas de D&O (página Ingestão → origem \"Documentos reais (pasta local)\").",
    "- Tudo o que está no texto aconteceu de fato no projeto. Se algo mudar (por exemplo, se você já tiver usado o prompt com outra IA), ajuste a fala do slide 9.", "",
    "## Narração", "");
  for (let n = 1; n <= 16; n++) {
    md.push(`### ${NARR[n].t} · Slide ${n} — ${TELAS[n]}`, "", `> ${NARR[n].f}`, "");
    if (n === 13) {
      md.push("#### Demonstração ao vivo (no app)", "");
      DEMO.forEach((d, i) => {
        md.push(`**${d.t} · Demo ${i + 1} — ${d.tela}**`, "", `*O que fazer:* ${d.acao}`, "", `> ${d.f}`, "");
      });
      md.push("*Volte para a apresentação no slide 14.*", "");
    }
  }
  md.push("## Se o app falhar durante a gravação", "",
    "O vídeo-base `InsurMinds_Projeto_Final.mp4` (sem áudio) tem as mesmas telas da demonstração em capturas.",
    "Você pode narrar por cima dele ou usar o slide 12, que mostra as três telas.", "");
  fs.writeFileSync(ROTEIRO, md.join("\n"), "utf8");
  console.log("ok", ROTEIRO);
})();
