#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / 'data'
CONFIG_DIR = PROJECT_ROOT / 'config'


def setup():
    """Setup inicial do projeto."""
    print("=" * 60)
    print("XAT Account Generator - Setup Inicial")
    print("=" * 60)

    DATA_DIR.mkdir(exist_ok=True)
    CONFIG_DIR.mkdir(exist_ok=True)
    print(f"OK diretorio criado/verificado: {DATA_DIR}")
    print(f"OK diretorio criado/verificado: {CONFIG_DIR}")

    files_to_create = {
        DATA_DIR / 'emails.txt': (
            'exemplo1@gmail.com\n'
            'exemplo2@outlook.com\n'
            'exemplo3@yahoo.com\n'
        ),
        DATA_DIR / 'proxies.txt': (
            '# Formato: ip:porta ou ip:porta:user:pass\n'
            '# 192.168.1.1:8080\n'
            '# 10.0.0.1:3128:user:pass\n'
        ),
        DATA_DIR / 'success_criacao.txt': '',
        PROJECT_ROOT / '.gitignore': (
            '*.log\n'
            'data/success_criacao.txt\n'
            '__pycache__/\n'
            '*.pyc\n'
            'venv/\n'
            '.venv/\n'
        ),
    }

    for caminho, conteudo in files_to_create.items():
        if not caminho.exists():
            caminho.parent.mkdir(exist_ok=True)
            caminho.write_text(conteudo, encoding='utf-8')
            print(f"OK arquivo criado: {caminho.relative_to(PROJECT_ROOT)}")
        else:
            print(f"SKIP arquivo ja existe: {caminho.relative_to(PROJECT_ROOT)}")

    print("\n" + "=" * 60)
    print("Proximos passos:")
    print("=" * 60)
    print("1. Preencha data/emails.txt com seus emails")
    print("2. Configure proxies em data/proxies.txt")
    print("3. Instale dependencias: pip install -r config/requirements.txt")
    print("4. Execute: python code/main.py")
    print("=" * 60)


if __name__ == '__main__':
    try:
        setup()
    except Exception as e:
        print(f"ERRO durante setup: {e}")
        sys.exit(1)
