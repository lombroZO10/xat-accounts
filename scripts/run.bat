@echo off
REM XAT Account Generator - Windows Launcher
REM Verifica dependencias e executa o script

cd /d "%~dp0\.."
cls
echo ============================================================
echo   XAT Account Generator - Windows Launcher
echo ============================================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python nao esta instalado ou nao esta no PATH
    echo Baixe Python em: https://www.python.org/downloads/
    echo Durante a instalacao, marque a opcao "Add Python to PATH"
    pause
    exit /b 1
)

echo OK Python encontrado
echo.

if not exist "data" (
    echo Criando diretorio data...
    mkdir data
)

if not exist "data\emails.txt" (
    echo AVISO: data\emails.txt nao encontrado.
    echo Rode: python code\setup.py
    echo.
)

if not exist "data\proxies.txt" (
    echo AVISO: data\proxies.txt nao encontrado.
    echo Rode: python code\setup.py
    echo.
)

python -c "import requests, bs4" >nul 2>&1
if %errorlevel% neq 0 (
    echo Instalando dependencias...
    pip install -r config\requirements.txt
    if %errorlevel% neq 0 (
        echo ERROR: Falha ao instalar dependencias
        pause
        exit /b 1
    )
)

echo.
echo OK Tudo pronto.
echo ============================================================
echo.

python code\main.py

echo.
pause
