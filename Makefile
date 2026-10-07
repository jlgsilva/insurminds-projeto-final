# ==========================================================================
# AgroSentinela — atalhos de desenvolvimento
# ==========================================================================
PY ?= python3
export PYTHONPATH := src

.DEFAULT_GOAL := ajuda

.PHONY: ajuda instalar seed app pipeline cenarios etl etl-rapido teste limpar zip apolices acervo acervo-ia

ajuda:  ## Mostra esta ajuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	 | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

instalar:  ## Instala as dependências
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements.txt

seed:  ## (Re)gera a amostra de demonstração
	$(PY) -m agrosentinela.data.seed_builder

apolices:  ## Projeto Final: (re)gera as 45 apólices D&O simuladas (PDF/digitalizada/foto)
	$(PY) scripts/gerar_apolices_simuladas.py

acervo:  ## Projeto Final: processa o acervo sem IA e gera a base inicial
	$(PY) scripts/processar_acervo.py

acervo-ia:  ## Projeto Final: processa o acervo COM IA (Groq) e mede a acurácia
	$(PY) scripts/processar_acervo.py --llm --saida data/apolices_simuladas/base_inicial.sqlite --pausa 20

app:  ## Abre a aplicação Streamlit
	streamlit run app.py

pipeline:  ## Executa o pipeline pela linha de comando
	$(PY) -m agrosentinela.orchestrator --exportar saida/

cenarios:  ## Gera um exemplo de mensagem para cada cenário climático
	@for c in seca chuva_excessiva chuva_intensa granizo geada onda_calor vendaval; do \
		echo "▶ cenário $$c"; \
		$(PY) -m agrosentinela.orchestrator --cenario $$c --clima sintetico \
			--max-mensagens 6 --ignorar-supressao --sem-persistencia \
			--exportar saida/cenario_$$c --log WARNING; \
	done

etl:  ## ETL completo dos microdados do BCB (download pesado)
	$(PY) etl/run_etl.py --anos 2025 2026

etl-rapido:  ## ETL com amostra reduzida (máquina modesta)
	$(PY) etl/run_etl.py --anos 2026 --amostra 150000

teste:  ## Roda os testes automatizados
	$(PY) -m pytest -q

limpar:  ## Remove caches e saídas temporárias
	rm -rf saida/ data/cache_clima data/cache_llm .pytest_cache
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

zip:  ## Empacota o código-fonte para entrega
	$(PY) scripts/gerar_entregaveis.py --zip
