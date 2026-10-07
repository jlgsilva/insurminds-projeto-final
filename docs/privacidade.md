# Privacidade, ética e governança

## Minimização de dados

Os microdados do Sicor incluem arquivos com identificação pessoal:
`SICOR_MUTUARIOS` e `SICOR_MUTUARIOS_CONTRAT` trazem CPF/CNPJ, sexo, tipo de
beneficiário e número da DAP.

**O AgroSentinela não utiliza nenhum desses arquivos.** A decisão é de
projeto, não de conveniência:

* o roteamento da comunicação precisa apenas da **referência da operação**
  (`REF_BACEN` + `NU_ORDEM`), que funciona como pseudônimo estável;
* o destinatário é exibido como `OP-<referência>` — nunca como pessoa
  identificada;
* **nenhum dado pessoal é enviado ao modelo de linguagem**;
* o catálogo `etl_catalogo.py` marca esses arquivos com a observação
  "não utilizado por decisão de privacidade".

Isso realiza o princípio da **minimização** (LGPD, art. 6º, III): tratar
apenas os dados necessários para a finalidade.

## Como seria em produção

Numa implantação real, o cruzamento entre a referência da operação e o
contato do cliente (telefone, e-mail) ficaria **dentro da instituição
financeira**, sob a base legal adequada — execução de contrato ou legítimo
interesse, com transparência ao titular. O serviço de alerta receberia de
volta apenas um identificador opaco.

Arquitetura recomendada:

```
AgroSentinela  →  [OP-123456-1, canal=whatsapp, texto]  →  Instituição
                                                              │
                                            resolve contato ──┘  (dentro do perímetro)
                                                              │
                                                              ▼  envio real
```

## Modo simulação

O enunciado do Desafio 5 dispensa o envio real. O sistema **nunca** envia
mensagem: o `DespachanteAgent` grava tudo com `simulado = verdadeiro`, e a
configuração `MODO_SIMULACAO` é verdadeira por padrão. A interface diz isso
de forma explícita na Central de Comunicação.

## Transparência com o destinatário

Toda mensagem:

* identifica-se como comunicação automática (`AgroSentinela — alerta automático`);
* informa que se baseia em **previsão meteorológica pública**, que muda;
* indica a fonte do risco e a ação recomendada;
* jamais promete pagamento de indenização.

Na interface, cada mensagem mostra o rastro das regras que a originaram
(identificador, indicadores e valores) — o equivalente operacional do
"direito à explicação".

## Vieses e efeitos indesejados

### Fadiga de alerta

Um sistema que avisa demais deixa de ser lido — e passa a causar dano.
Mitigações: janela de repetição de 48 h, teto de 3 mensagens por
destinatário por dia, severidade mínima por persona, consolidação de
múltiplos eventos numa mensagem só.

### Viés de porte

Ordenar a fila apenas por exposição financeira faria as maiores operações
consumirem todo o orçamento de mensagens — e o produtor familiar, que é
quem tem menos capacidade de absorver a perda, nunca seria avisado.

Mitigação: `RedatorAgent._distribuir_por_persona` distribui o teto em
**rodízio entre as personas**, preservando a ordem de risco dentro de cada
uma. Há verificação disso na interface (mensagens por persona e canal).

### Assimetria de custo entre erros

Neste domínio, **falso negativo é mais caro que falso positivo**: deixar de
avisar sobre uma geada custa a safra; avisar sem que ela ocorra custa uma
noite de preocupação. Os limiares foram calibrados para sensibilidade, e a
supressão atua depois, na camada de comunicação — não na de detecção.

### Cobertura geográfica desigual

Municípios sem centroide não recebem consulta meteorológica. O ETL relata a
proporção, e a validação reprova a base se menos de 50 % das operações
tiverem coordenada.

## Limitações que precisam ser ditas ao usuário

1. **Previsão é probabilística.** Um alerta não é a certeza de um evento.
2. **Granizo não tem previsão pública direta.** Usamos um índice convectivo
   composto, que estima ambiente favorável — não ocorrência.
3. **Resolução de ~11 km.** O alerta é de município, não de talhão.
4. **Fase fenológica estimada**, não observada em campo.
5. **A amostra de demonstração não é dado real.**
6. **Nenhuma mensagem é enviada.**

Todas aparecem na página de Documentação da aplicação e no relatório técnico.

## Licenciamento dos dados

| Fonte | Condição |
|---|---|
| Sicor / Proagro (BCB) | Dados abertos, domínio público |
| Open-Meteo | CC-BY 4.0, uso não comercial sem chave |
| GroqCloud | Termos da camada gratuita |
| Código do AgroSentinela | MIT |

O disclaimer do Banco Central sobre os microdados de 1983 a junho de 1994
(curadoria incipiente e sucessão de moedas por conta da inflação) é
respeitado: a série Recor só é usada para contexto histórico, nunca para
cálculo de risco corrente.
