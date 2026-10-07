# E-mail de entrega — Projeto Final

**Para:** challenges@i2a2.academy
**Cc:** demais integrantes do grupo (se houver)
**Assunto:** InsurMinds – Projeto Final

---

Prezados,

Entrega do grupo: **<NOME DO GRUPO>**

Segue a entrega do Projeto Final — *Plataforma Inteligente para Análise e
Comparação de Apólices D&O*.

O projeto foi desenvolvido como um novo módulo do **AgroSentinela**, a
aplicação entregue no Desafio 5, mantendo o foco em seguro e crédito rural:
apólices D&O de empresas do agronegócio (cooperativas de crédito rural,
usinas, tradings, frigoríficos, agroindústrias), com pesos ajustados ao
perfil de crédito rural da tomadora a partir dos microdados do Sicor/Proagro
(Banco Central).

**Resumo da solução**
- Recebe apólices em PDF, PDF digitalizado ou foto; extrai o texto (OCR
  quando necessário).
- Agentes de IA (Groq, GPT-OSS 120B/20B) estruturam o quadro-resumo e
  classificam 32 cláusulas com evidência literal; um agente de validação
  confere evidências e números contra o documento (anti-alucinação).
- Armazenamento estruturado (SQLite), consulta em linguagem natural (agente
  com *tool calling*), comparação de duas ou mais apólices e relatório
  comparativo redigido por IA para cinco públicos.
- Acervo de demonstração com 120 apólices **simuladas**: 6 seguradoras
  fictícias, cada uma com seu próprio modelo de documento (20 apólices cada),
  para 45 tomadoras do agronegócio em 25 UFs e no DF — da agricultura familiar
  ao latifúndio —, com gabarito para medir a acurácia da extração.

**Links**
- Repositório (público): https://github.com/jlgsilva/insurminds-projeto-final
- Aplicação online: <URL DO STREAMLIT>

**Anexos**
1. `InsurMinds_Projeto_Final_Relatorio_Tecnico.pdf` — relatório técnico
2. `InsurMinds_Projeto_Final.pptx` — pitch deck
3. `InsurMinds_Projeto_Final.mp4` — vídeo de apresentação (até 5 min)
4. `insurminds-projeto-final.zip` — código-fonte e demais artefatos

Os mesmos arquivos estão na pasta `Projeto_Final_Artefatos/` do repositório.

Integrantes:
- Jefferson Luiz Gonçalves Silva (representante) — <e-mail> — <telefone>

Atenciosamente,
Jefferson Luiz Gonçalves Silva

---

### Antes de enviar — checklist

- [ ] Trocar `<NOME DO GRUPO>`, `<URL DO STREAMLIT>`, e-mail e telefone
- [ ] Enviar pelo e-mail do representante, com cópia para todos os integrantes
- [ ] Repositório público e com a pasta `Projeto_Final_Artefatos/`
- [ ] README com descrição, instalação, execução, tecnologias, integrantes e licença MIT ✔
- [ ] Os 4 anexos. Se o e-mail recusar o tamanho, mantenha PDF + PPTX anexados e
      envie MP4/ZIP por link (Google Drive ou o próprio GitHub)
