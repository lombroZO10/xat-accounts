#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Verificador do projeto.
Valida a estrutura real usada neste workspace:
- code/ para scripts Python
- config/ para configuracao e requirements
- data/ para entrada e saida
"""

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = PROJECT_ROOT / 'code'
CONFIG_DIR = PROJECT_ROOT / 'config'
DATA_DIR = PROJECT_ROOT / 'data'


def rel(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT))


def verificar_arquivo(path: Path, problemas: list[str], obrigatorio: bool = True) -> None:
    if path.exists():
        print(f"  OK {rel(path)} ({path.stat().st_size} bytes)")
    elif obrigatorio:
        problemas.append(f"Arquivo nao existe: {rel(path)}")
    else:
        print(f"  AVISO ausente: {rel(path)}")


def verificar_projeto() -> bool:
    """Verifica integridade basica do projeto."""
    print("=" * 70)
    print("  VERIFICACAO DO PROJETO - XAT Account Generator")
    print("=" * 70)

    problemas: list[str] = []
    avisos: list[str] = []

    print("\n[1] Estrutura de diretorios")
    for diretorio in [CODE_DIR, CONFIG_DIR, DATA_DIR, PROJECT_ROOT / 'docs', PROJECT_ROOT / 'scripts']:
        if diretorio.exists():
            print(f"  OK {rel(diretorio)}/")
        else:
            problemas.append(f"Diretorio nao existe: {rel(diretorio)}/")

    print("\n[2] Arquivos principais")
    for arquivo in [
        CODE_DIR / 'main.py',
        CODE_DIR / 'setup.py',
        CODE_DIR / 'verify.py',
        CONFIG_DIR / 'config.json',
        CONFIG_DIR / 'requirements.txt',
        DATA_DIR / 'emails.txt',
        DATA_DIR / 'proxies.txt',
        DATA_DIR / 'success_criacao.txt',
        PROJECT_ROOT / 'scripts' / 'run.bat',
        PROJECT_ROOT / 'scripts' / 'run.sh',
    ]:
        verificar_arquivo(arquivo, problemas)

    print("\n[3] Python")
    versao_python = f"{sys.version_info.major}.{sys.version_info.minor}"
    if sys.version_info.major == 3 and sys.version_info.minor >= 8:
        print(f"  OK Python {versao_python}")
    else:
        problemas.append(f"Python {versao_python} e antigo; minimo recomendado: 3.8")

    print("\n[4] Dependencias")
    dependencias = ['requests', 'bs4', 'urllib3']
    for dep in dependencias:
        try:
            __import__(dep)
            print(f"  OK {dep} instalado")
        except ImportError:
            problemas.append(f"Dependencia ausente: {dep}. Rode: pip install -r config/requirements.txt")
            print(f"  FALTA {dep}")

    print("\n[5] Conteudo dos dados")
    emails_path = DATA_DIR / 'emails.txt'
    if emails_path.exists():
        emails = [l.strip() for l in emails_path.read_text(encoding='utf-8').splitlines() if l.strip()]
        print(f"  OK data/emails.txt: {len(emails)} linha(s) ativa(s)")
        if not emails:
            avisos.append("data/emails.txt esta vazio")

    proxies_path = DATA_DIR / 'proxies.txt'
    if proxies_path.exists():
        proxies = [
            l.strip()
            for l in proxies_path.read_text(encoding='utf-8').splitlines()
            if l.strip() and not l.strip().startswith('#')
        ]
        print(f"  OK data/proxies.txt: {len(proxies)} proxy(ies) ativo(s)")
        if not proxies:
            avisos.append("data/proxies.txt nao tem proxies ativos")

    print("\n[6] Documentacao")
    for doc in [
        PROJECT_ROOT / 'README.md',
        PROJECT_ROOT / 'START_HERE.md',
        PROJECT_ROOT / 'STRUCTURE.txt',
        PROJECT_ROOT / 'docs' / 'INDEX.md',
    ]:
        verificar_arquivo(doc, problemas, obrigatorio=False)

    print("\n" + "=" * 70)
    print("  RESUMO")
    print("=" * 70)

    if problemas:
        print(f"\nPROBLEMAS ({len(problemas)}):")
        for problema in problemas:
            print(f"  - {problema}")

    if avisos:
        print(f"\nAVISOS ({len(avisos)}):")
        for aviso in avisos:
            print(f"  - {aviso}")

    if not problemas and not avisos:
        print("\nTudo certo para a estrutura local.")
    elif not problemas:
        print("\nSem problemas criticos; revise os avisos.")
    else:
        print("\nExistem problemas a corrigir antes da execucao.")
        return False

    print("\nComandos esperados:")
    print("  pip install -r config/requirements.txt")
    print("  python code/main.py")
    return True


def listar_arquivos() -> None:
    """Lista arquivos do projeto."""
    print("\nESTRUTURA DE ARQUIVOS:\n")

    for raiz, dirs, arquivos in os.walk(PROJECT_ROOT):
        dirs[:] = [d for d in dirs if d not in {'.git', '__pycache__', 'venv', '.venv'}]
        raiz_path = Path(raiz)
        nivel = len(raiz_path.relative_to(PROJECT_ROOT).parts)
        indent = '  ' * nivel
        nome = PROJECT_ROOT.name if raiz_path == PROJECT_ROOT else raiz_path.name
        print(f"{indent}{nome}/")

        sub_indent = '  ' * (nivel + 1)
        for arquivo in sorted(arquivos):
            if arquivo.startswith('.'):
                continue
            caminho = raiz_path / arquivo
            tamanho = caminho.stat().st_size
            print(f"{sub_indent}{arquivo} ({tamanho} bytes)")


if __name__ == '__main__':
    sucesso = verificar_projeto()
    listar_arquivos()
    if not sucesso:
        sys.exit(1)
