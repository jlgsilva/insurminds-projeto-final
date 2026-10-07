# Passo a passo — rodar, publicar no GitHub e colocar no ar no Streamlit

Tempo total estimado: 30–40 minutos. Comandos para **Windows (PowerShell)**;
quando diferente, a versão Linux/macOS vem ao lado.

---

## 0. Pré-requisitos (uma vez)

| Item | Onde | Observação |
|---|---|---|
| Python 3.11 ou 3.12 | python.org | marque "Add python.exe to PATH" |
| Git | git-scm.com | |
| Tesseract (opcional) | github.com/UB-Mannheim/tesseract/wiki | só para OCR de apólices **suas**; marque "Portuguese". O acervo já vem processado |
| Chave Groq | console.groq.com/keys | gratuita; começa com `gsk_` |

## 1. Descompactar e testar localmente

```powershell
# descompacte insurminds-projeto-final.zip em, por exemplo, C:\projetos\
cd C:\projetos\insurminds-projeto-final
python -m venv .venv
.venv\Scripts\activate              # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env              # Linux/macOS: cp .env.example .env
notepad .env                        # cole a chave em GROQ_API_KEY=gsk_...
streamlit run app.py
```

Abra http://localhost:8501 → **📄 Ingestão de Apólices** → na barra lateral
deve aparecer **"Groq configurada"**. Clique **Testar conexão com a Groq**.

> Se aparecer erro 400/404 de modelo: abra https://console.groq.com/docs/models,
> confirme os IDs e ajuste `GROQ_MODEL_*` no `.env`. Padrões: `openai/gpt-oss-120b`
> e `openai/gpt-oss-20b` (modelos de **produção** — não use os de *preview*).

## 2. (Recomendado) Medir a extração com IA

Isso preenche a base inicial com extração **por IA** e gera
`avaliacao_llm.csv` (o número "IA × linha de base" do relatório e do vídeo).
O acervo tem 120 apólices; no plano gratuito da Groq há limite de tokens por
dia, então comece por uma amostra que já cobre as 6 seguradoras:

```powershell
python scripts/processar_acervo.py --llm --pausa 20 --limite 30
```

Leva ~15–20 min (a pausa protege o limite de tokens/minuto). Com plano pago
ou em outro dia, rode sem `--limite` para o acervo inteiro.
As respostas ficam em cache: se cair no meio, rode de novo e ele continua
rápido. Depois, regenere o relatório PDF com o número da IA:

```powershell
python scripts/gerar_relatorio_pf.py
del data\apolices.sqlite     # Linux/macOS: rm data/apolices.sqlite (o app recria a partir da base nova)
```

Sem tempo? Pule este passo — a entrega já está completa; a IA roda ao vivo
no app quando você processar/comparar apólices.

## 3. Criar o repositório no GitHub

1. https://github.com/new
2. **Repository name:** `insurminds-projeto-final`
   (o GitHub não aceita espaços; se usar outro nome, troque nos links do README)
3. **Public** (obrigatório pelo enunciado). **Não** marque "Add a README",
   ".gitignore" nem "license" (o projeto já tem).
4. **Create repository**.

## 4. Enviar o código

```powershell
cd C:\projetos\insurminds-projeto-final
git init
git add .
git commit -m "InsurMinds - Projeto Final: análise e comparação de apólices D&O (AgroSentinela)"
git branch -M main
git remote add origin https://github.com/jlgsilva/insurminds-projeto-final.git
git push -u origin main
```

Confira no navegador: README aparece na página inicial, pasta
`Projeto_Final_Artefatos/` contém `InsurMinds_Projeto_Final.pptx` e
`InsurMinds_Projeto_Final.mp4`. O `.env` **não** deve aparecer (está no
`.gitignore`). Se o push pedir senha, use um *Personal Access Token*
(GitHub → Settings → Developer settings → Tokens) ou o GitHub Desktop.

> Se você regravar o vídeo com narração, substitua o arquivo com o **mesmo
> nome** e rode: `git add Projeto_Final_Artefatos/InsurMinds_Projeto_Final.mp4`,
> `git commit -m "vídeo narrado"`, `git push`.

## 5. Publicar no Streamlit Community Cloud

1. https://share.streamlit.io → entre com o GitHub → **Create app** →
   **Deploy a public app from GitHub**.
2. Repository: `jlgsilva/insurminds-projeto-final` · Branch: `main` ·
   Main file path: `app.py` · App URL: ex. `insurminds-projeto-final`.
3. **Advanced settings** → Python **3.11** (ou 3.12) → **Secrets**, cole:

   ```toml
   GROQ_API_KEY = "gsk_SUA_CHAVE"
   GROQ_MODEL_REDACAO = "openai/gpt-oss-120b"
   GROQ_MODEL_RAPIDO = "openai/gpt-oss-20b"
   GROQ_MODEL_COPILOTO = "openai/gpt-oss-120b"
   GROQ_MODEL_EXTRACAO = "openai/gpt-oss-120b"
   LLM_REASONING_EFFORT = "low"
   FONTE_DADOS = "auto"
   ```
4. **Deploy**. A primeira instalação leva 3–6 min (o `packages.txt` instala o
   Tesseract).
5. Teste: Ingestão (com uma `_digitalizada`), Comparador, Consulta.
6. Copie a URL do app e cole no README (seção 6) e no e-mail.

Problemas comuns: *ModuleNotFoundError* → confira se `requirements.txt` está
na raiz; app "dormindo" → é normal no plano gratuito, ele acorda ao abrir.

## 6. Gravar o vídeo narrado (recomendado)

O `InsurMinds_Projeto_Final.mp4` incluído (4 min 29 s, sem áudio, com
legendas) já cumpre o entregável como vídeo-base. A versão recomendada é a
**sua**, narrada em primeira pessoa, alternando a apresentação e o **app ao
vivo** (com a chave da Groq). O texto de narração, com tempos e o roteiro da
demonstração, está em `ROTEIRO_VIDEO.md`; o mesmo texto está nas **notas de
cada slide** do `.pptx` (modo apresentador). Grave com **Win + G** (Xbox Game
Bar), OBS Studio ou Loom. Limite: **5 minutos** (o slide 12 não tem narração). Salve como `InsurMinds_Projeto_Final.mp4` e substitua o arquivo em
`Projeto_Final_Artefatos/`.

Observação: as capturas do vídeo-base foram feitas sem chave da Groq (modo por
regras, por isso o contador "Extraídas com IA" aparece zerado). Na sua gravação,
com a chave configurada, a leitura por IA aparece de verdade.

Se medir a IA antes (`python scripts/processar_acervo.py --llm --limite 30` e
depois `python scripts/gerar_relatorio_pf.py`), rode `node scripts/gerar_pitch_deck.js`:
o slide 14 e a narração passam a mostrar também o acerto da IA.

## 6b. Documentos reais (só na sua máquina)

Os 5 documentos reais enviados pelo colega **não vão para o GitHub** (estão no
`.gitignore`). Para usá-los localmente, copie os PDFs para
`data/apolices_reais/` (qualquer nome). A página **Ingestão** passa a oferecer
a origem "Documentos reais (pasta local)", e
`python scripts/avaliar_documentos_reais.py` (ou `--llm`) refaz a validação.
No vídeo, **não mostre as apólices de Seguro Garantia** (dados de terceiros);
as condições gerais de D&O são públicas.

## 7. ZIP para o e-mail

Use o `insurminds-projeto-final.zip` que acompanha esta entrega. Se você
alterar algo (ex.: base com IA, vídeo narrado), gere um novo pelo GitHub:
página do repositório → **Code → Download ZIP** (sai sem `.venv` e sem `.env`).

## 8. (Depois) Acrescentar apólices geradas por outra IA

1. Abra `docs/PROMPT_GERAR_APOLICES.md`, copie o bloco entre as linhas `=====`,
   preencha a seção 8 ("Este lote") e cole na outra IA.
2. Baixe o lote (PDFs + `gabarito_externo.json`) numa pasta, ex.: `C:\lotes\lote1`.
3. Valide e importe:
   ```powershell
   python scripts/importar_apolices_externas.py --pasta C:\lotes\lote1 --simular   # só valida
   python scripts/importar_apolices_externas.py --pasta C:\lotes\lote1             # importa
   python scripts/processar_acervo.py                                               # reconstrói a base
   del data\apolices.sqlite
   ```
4. `git add -A`, `git commit -m "lote 1 de apólices externas"`, `git push`.

O importador recusa o lote inteiro se encontrar seguradora real, código de
cláusula ou nível inválido, arquivo faltando ou PDF sem o aviso de simulação.

## 9. Enviar o e-mail

Use `EMAIL_ENTREGA.md` (para, assunto, corpo e anexos). Prazo: **06/10/2026,
23h59**.
