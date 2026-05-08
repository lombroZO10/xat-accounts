#!/bin/bash
set -e

cd "$(dirname "$0")/.."

echo "============================================================"
echo "  XAT Account Generator - Linux/Mac Launcher"
echo "============================================================"
echo ""

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: Python 3 nao esta instalado"
    echo "Instale Python 3 e pip antes de continuar"
    exit 1
fi

echo "OK Python encontrado: $(python3 --version)"
echo ""

mkdir -p data

if [ ! -f "data/emails.txt" ]; then
    echo "AVISO: data/emails.txt nao encontrado."
    echo "Rode: python3 code/setup.py"
    echo ""
fi

if [ ! -f "data/proxies.txt" ]; then
    echo "AVISO: data/proxies.txt nao encontrado."
    echo "Rode: python3 code/setup.py"
    echo ""
fi

if ! python3 -c "import requests, bs4" 2>/dev/null; then
    echo "Instalando dependencias..."
    pip3 install -r config/requirements.txt
fi

echo ""
echo "OK Tudo pronto."
echo "============================================================"
echo ""

python3 code/main.py
