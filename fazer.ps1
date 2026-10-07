<#
.SYNOPSIS
    Atalhos do AgroSentinela para Windows — o equivalente ao Makefile.

.DESCRIPTION
    O `make` não vem instalado no Windows, e pedir para alguém instalar um
    utilitário de Unix só para rodar quatro comandos é atrito desnecessário.
    Este script faz o mesmo que o Makefile, em PowerShell puro.

    Se preferir, todos os comandos podem ser digitados direto — nenhum deles
    depende deste arquivo. Ele existe apenas para encurtar o caminho.

.EXAMPLE
    .\fazer.ps1 instalar
    .\fazer.ps1 app
    .\fazer.ps1 teste
    .\fazer.ps1 entregaveis

.NOTES
    Se o PowerShell recusar a execução ("execução de scripts foi desabilitada
    neste sistema"), libere apenas para a sessão atual:

        Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#>

param(
    [Parameter(Position = 0)]
    [string]$Alvo = "ajuda"
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# No Windows o executável chama-se `python`; `python3` costuma ser um atalho
# da Microsoft Store que abre a loja em vez de rodar o interpretador.
$PY = "python"

function Escrever($texto, $cor = "White") {
    Write-Host $texto -ForegroundColor $cor
}

switch ($Alvo.ToLower()) {

    "ajuda" {
        Escrever "`n  AgroSentinela — atalhos para Windows`n" "Green"
        Escrever "  .\fazer.ps1 instalar      Instala as dependencias"
        Escrever "  .\fazer.ps1 app           Abre a aplicacao no navegador"
        Escrever "  .\fazer.ps1 seed          Regera a amostra de demonstracao"
        Escrever "  .\fazer.ps1 pipeline      Executa o pipeline pela linha de comando"
        Escrever "  .\fazer.ps1 teste         Roda a suite de testes"
        Escrever "  .\fazer.ps1 etl           Executa o ETL completo do Banco Central"
        Escrever "  .\fazer.ps1 entregaveis   Gera relatorio, resumo executivo e ZIP"
        Escrever "  .\fazer.ps1 diagnostico   Verifica tudo e gera diagnostico.txt"
        Escrever "  .\fazer.ps1 limpar        Remove caches e arquivos temporarios`n"
    }

    "instalar" {
        Escrever "Instalando dependencias..." "Cyan"
        & $PY -m pip install --upgrade pip
        & $PY -m pip install -r requirements.txt
        Escrever "`nPronto. Rode:  .\fazer.ps1 app" "Green"
    }

    "app" {
        Escrever "Abrindo em http://localhost:8501 ..." "Cyan"
        & $PY -m streamlit run app.py
    }

    "seed" {
        $env:PYTHONPATH = "src"
        & $PY -m agrosentinela.data.seed_builder
    }

    "pipeline" {
        $env:PYTHONPATH = "src"
        & $PY -m agrosentinela.orchestrator --cenario seca --intensidade 1.4 --modo-clima sintetico
    }

    "teste" {
        & $PY -m pytest -q
    }

    "etl" {
        Escrever "O ETL baixa arquivos grandes do Banco Central e pode levar horas." "Yellow"
        Escrever "Para uma primeira prova, use:  python etl\run_etl.py --anos 2026 --amostra 150000`n" "Yellow"
        & $PY etl\run_etl.py --anos 2025 2026
    }

    "entregaveis" {
        & $PY scripts\gerar_entregaveis.py
    }

    "diagnostico" {
        Escrever "Rodando o diagnostico completo..." "Cyan"
        & $PY scripts\diagnostico.py
    }

    "limpar" {
        Get-ChildItem -Path . -Include "__pycache__" -Recurse -Directory |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        Get-ChildItem -Path . -Include "*.pyc" -Recurse -File |
            Remove-Item -Force -ErrorAction SilentlyContinue
        Remove-Item -Recurse -Force .pytest_cache -ErrorAction SilentlyContinue
        Escrever "Caches removidos." "Green"
    }

    default {
        Escrever "Alvo desconhecido: $Alvo" "Red"
        Escrever "Rode  .\fazer.ps1 ajuda  para ver as opcoes."
        exit 1
    }
}
