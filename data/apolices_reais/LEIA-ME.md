# Documentos reais — validação fora do acervo simulado

Para testar a plataforma fora do acervo simulado, usamos **5 documentos reais**
enviados por um colega do curso:

| Identificador | O que é | Páginas | Papel no teste |
|---|---|---|---|
| REAL-AXA | Condições gerais de D&O, AXA Seguros (Processo SUSEP 15414.901016/2017-01, versão 12/2025) | 104 | Leitura e classificação das 32 cláusulas |
| REAL-ALLIANZ | Condições gerais de D&O, Allianz Seguros (Processo SUSEP 15414.901113/2017-96, versão dez/2025) | 75 | Leitura e classificação das 32 cláusulas |
| REAL-PORTO | Condições gerais de D&O para empresas de capital fechado, Porto Seguro (Processo SUSEP 15414.901349/2019-94, fev/2022) | 52 | Leitura e classificação das 32 cláusulas |
| REAL-GARANTIA-1 | Apólice emitida de **Seguro Garantia** | 21 | Precisa ser reconhecida como **fora do escopo** |
| REAL-GARANTIA-2 | Apólice emitida de **Seguro Garantia** | 13 | Precisa ser reconhecida como **fora do escopo** |

**Os PDFs não estão no repositório** (estão no `.gitignore`). As condições
gerais são textos públicos registrados na SUSEP, mas pertencem às seguradoras.
As apólices de Seguro Garantia trazem dados reais de empresas e pessoas:
nenhum dado delas foi copiado para este projeto, para o relatório ou para a
apresentação.

## Como reproduzir

1. Coloque os PDFs nesta pasta (com qualquer nome: são reconhecidos pelo
   SHA-256 registrado em `gabarito_reais.json`).
2. Rode:

   ```bash
   python scripts/avaliar_documentos_reais.py              # regras, sem IA
   python scripts/avaliar_documentos_reais.py --llm        # com Groq
   ```

3. No app, a página **Ingestão de Apólices** passa a oferecer a origem
   "Documentos reais (pasta local)".

## Gabarito

`gabarito_reais.json` traz, para cada condição geral, as 32 cláusulas com
nível, página, seção e uma evidência literal curta (até 25 palavras), checada
por script contra o texto. A anotação foi feita com apoio de IA (Claude), com
leitura integral de cada documento. **Os níveis são julgamento técnico e
precisam de revisão por um especialista**; a presença ou ausência da cláusula
é o critério mais objetivo e é o principal indicador do teste.
