# Projeto_Final_Artefatos

Artefatos exigidos pelo enunciado do Projeto Final (InsurMinds/I2A2).

| Arquivo | Conteúdo |
|---|---|
| `InsurMinds_Projeto_Final.pptx` | Apresentação (16 slides) para público geral: o problema, **como o projeto foi construído** (papéis do autor, do Claude e da IA da Groq; por que e como as apólices foram simuladas; a revisão que refez a base; o teste com 5 documentos reais), como o app funciona, demonstração, resultados e aprendizados. Narração nas notas de cada slide |
| `InsurMinds_Projeto_Final.mp4` | Vídeo-base (4 min 29 s, sem áudio): slides + capturas da aplicação com legendas. A versão narrada é gravada pelo autor com `ROTEIRO_VIDEO.md` |
| `InsurMinds_Projeto_Final_Relatorio_Tecnico.pdf` | Relatório técnico: arquitetura, tecnologias, agentes, fluxo, decisões, limitações, evolução |
| `capturas/` | Capturas de tela da aplicação em execução e diagrama de arquitetura |
| `EMAIL_ENTREGA.md` | Texto do e-mail de entrega e checklist |
| `PASSO_A_PASSO_PUBLICACAO.md` | Como rodar, publicar no GitHub e no Streamlit Cloud |
| `ROTEIRO_VIDEO.md` | Texto de narração em primeira pessoa, com tempos, e roteiro da demonstração ao vivo no app |
| `../docs/PROMPT_GERAR_APOLICES.md` | Prompt para outra IA gerar novos lotes de apólices simuladas (e `scripts/importar_apolices_externas.py` para importá-los) |

Regenerar: `node scripts/gerar_pitch_deck.js` (gera o deck e o roteiro) · `python scripts/gerar_relatorio_pf.py` ·
`python scripts/gerar_video_pf.py <slides_png>`.

O acervo de apólices simuladas, o gabarito e a base inicial estão em
`data/apolices_simuladas/`.
