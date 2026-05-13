#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import re
import sys
import json
import random
import string
import logging
import time
import requests
import importlib.util
import asyncio
import html
import socket
import select
import threading
import socks
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
from urllib.parse import ParseResult, urljoin, parse_qs, urlencode, urlparse, urlsplit
from bs4 import BeautifulSoup

class ThreadedHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True

class Socks5HttpProxyHandler(BaseHTTPRequestHandler):
    server_version = "XATProxy/0.1"

    def log_message(self, format: str, *args) -> None:
        return

    def _connect_to_destination(self, host: str, port: int) -> socket.socket:
        upstream = self.server.upstream_proxy
        sock = socks.socksocket()
        proxy_scheme = upstream.get('scheme', 'socks5').lower()

        if proxy_scheme == 'socks5':
            sock.set_proxy(
                socks.SOCKS5,
                upstream['host'],
                upstream['port'],
                username=upstream.get('username'),
                password=upstream.get('password'),
                rdns=True
            )
        elif proxy_scheme == 'socks4':
            sock.set_proxy(
                socks.SOCKS4,
                upstream['host'],
                upstream['port'],
                username=upstream.get('username'),
                rdns=True
            )
        else:
            sock = socket.create_connection((host, port), timeout=10)
            return sock

        sock.settimeout(15)
        sock.connect((host, port))
        return sock

    def _relay_data(self, client: socket.socket, remote: socket.socket) -> None:
        sockets = [client, remote]
        while True:
            readable, _, _ = select.select(sockets, [], [], 10)
            if not readable:
                break

            for s in readable:
                data = s.recv(8192)
                if not data:
                    return
                if s is client:
                    remote.sendall(data)
                else:
                    client.sendall(data)

    def do_CONNECT(self) -> None:
        host, port = self.path.split(':', 1)
        port = int(port)

        try:
            remote_socket = self._connect_to_destination(host, port)
        except Exception as e:
            self.send_error(502, f"Bad gateway: {e}")
            return

        self.send_response(200, 'Connection Established')
        self.send_header('Proxy-agent', self.server_version)
        self.end_headers()

        self._relay_data(self.connection, remote_socket)

    def _proxy_request(self) -> None:
        url = self.path
        if not url.startswith('http://') and not url.startswith('https://'):
            host = self.headers.get('Host')
            if not host:
                self.send_error(400, 'Host header missing')
                return
            url = f'http://{host}{self.path}'

        parsed = urlsplit(url)
        dest_host = parsed.hostname
        dest_port = parsed.port or (443 if parsed.scheme == 'https' else 80)

        try:
            remote_socket = self._connect_to_destination(dest_host, dest_port)
        except Exception as e:
            self.send_error(502, f'Bad gateway: {e}')
            return

        request_line = f"{self.command} {parsed.path or '/'}"
        if parsed.query:
            request_line += f'?{parsed.query}'
        request_line += ' HTTP/1.1\r\n'

        self.headers['Connection'] = 'close'
        if 'Proxy-Connection' in self.headers:
            del self.headers['Proxy-Connection']
        if 'Proxy-Authorization' in self.headers:
            del self.headers['Proxy-Authorization']

        header_lines = ''.join(f"{k}: {v}\r\n" for k, v in self.headers.items())
        remote_socket.sendall(request_line.encode('utf-8') + header_lines.encode('utf-8') + b"\r\n")

        content_length = int(self.headers.get('Content-Length', 0))
        if content_length:
            body = self.rfile.read(content_length)
            if body:
                remote_socket.sendall(body)

        self._relay_data(self.connection, remote_socket)

    def do_GET(self) -> None:
        self._proxy_request()

    def do_POST(self) -> None:
        self._proxy_request()

    def do_PUT(self) -> None:
        self._proxy_request()

    def do_DELETE(self) -> None:
        self._proxy_request()

    def do_HEAD(self) -> None:
        self._proxy_request()

    def do_OPTIONS(self) -> None:
        self._proxy_request()

    def do_PATCH(self) -> None:
        self._proxy_request()

# Custom exceptions
class CloudflareHardBlockException(Exception):
    """Raised when Cloudflare presents a hard block that requires proxy rotation."""
    pass

# Playwright imports
try:
    from playwright.async_api import async_playwright, Browser, Page, BrowserContext, Locator
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    async_playwright = None

from adspowers import AdsPowerManager

if importlib.util.find_spec('cloudscraper') is not None:
    cloudscraper = importlib.import_module('cloudscraper')
else:
    cloudscraper = None

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / 'data'
CONFIG_DIR = PROJECT_ROOT / 'config'
LOG_FILE = PROJECT_ROOT / 'criacao_contas.log'
BAD_PROXIES_FILE = DATA_DIR / 'bad_proxies.log'
SHADOWBAN_LOG_FILE = DATA_DIR / 'shadowban.log'

DEFAULT_CONFIG = {
    "delays": {
        "min_entre_requisicoes": 5,
        "max_entre_requisicoes": 15,
        "min_entre_contas": 30,
        "max_entre_contas": 60
    },
    "timeout": {
        "requisicao": 30,
        "proxy": 20
    },
    "retry": {
        "max_tentativas": 3,
        "delay_entre_tentativas": 5
    },
    "proxy": {
        "rotacao": "por_requisicao",
        "health_check": False,
        "use_public_fallback": True,
        "force_proxy": True,  # Forçar uso de proxy em todas as requisições
        "use_session_ids": True
    },
    "browser_automation": {
        "enabled": True,
        "headless": True,
        "proxy_rotation": True,
        "captcha_timeout": 60,
        "page_timeout": 90000,
        "home_timeout": 90000,  # Timeout para carregar página inicial (domcontentloaded)
        "login_timeout": 90000,  # Timeout para carregar página de login (networkidle)
        "use_ads_power": True,
        "ads_power_api_url": "http://127.0.0.1:20725",
        "ads_power_api_key": "64e06c1a51e916f82b06a71d921428f6008db5a025a70fb2",
        "ads_power_profile_id": "",
        "ads_power_profile_name": ""
    },
    "captcha_solver": {
        "enabled": False,
        "provider": "2captcha",
        "api_key": ""
    }
}

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class XATAccountGenerator:
    """Gerador automático de contas para XAT.COM"""
    
    BASE_URL = "https://xat.com"
    AUSER_URL = f"{BASE_URL}/web_gear/chat/auser3.php"
    LOGIN_URL = f"{BASE_URL}/login"
    
    # User-Agents variados (Windows 10/11 com Chrome/Edge realista)
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/121.0.0.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    ]
    
    def __init__(self):
        """Inicializa o gerador de contas"""
        self.emails: List[str] = []
        self.usernames: List[str] = []
        self.paid_proxies: List[str] = []
        self.public_proxies: List[str] = []
        self.proxy_indexes = {'paid': 0, 'public': 0}
        self.contas_criadas: Dict[str, Dict] = {}
        self.config = self._carregar_config()
        self.session = self._criar_sessao()
        self.scraper = self._criar_scraper()
        self.current_proxy = None  # Proxy atual para manter sessão
        self.last_recaptcha_sitekey: Optional[str] = None
        self.last_captcha_page_url: Optional[str] = None
        
        logger.info("🚀 XAT Account Generator iniciado")

    def _carregar_config(self) -> Dict:
        """Carrega configurações do arquivo config.json"""
        arquivo = CONFIG_DIR / 'config.json'
        config = json.loads(json.dumps(DEFAULT_CONFIG))

        if not arquivo.exists():
            logger.warning(f"⚠️ Arquivo de configuração não encontrado: {arquivo}. Usando valores padrão.")
            return config

        try:
            with open(arquivo, 'r', encoding='utf-8') as f:
                dados = json.load(f)

            def merge(base: Dict, extra: Dict):
                for chave, valor in extra.items():
                    if isinstance(valor, dict) and chave in base and isinstance(base[chave], dict):
                        merge(base[chave], valor)
                    else:
                        base[chave] = valor

            merge(config, dados)
            logger.info("✅ Configurações carregadas de config.json")
            return config

        except Exception as e:
            logger.warning(f"⚠️ Erro ao carregar config.json: {e}. Usando valores padrão.")
            return config
    
    def _criar_sessao(self) -> requests.Session:
        """Cria uma sessão requests com configurações padrão e cookies persistentes"""
        session = requests.Session()
        session.trust_env = False
        session.headers.update({
            'User-Agent': random.choice(self.USER_AGENTS),
            'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Referer': 'https://xat.com/'
        })
        return session

    def _criar_scraper(self):
        """Cria um cloudscraper opcional para fallback em Cloudflare"""
        if not cloudscraper:
            return None

        try:
            scraper = cloudscraper.create_scraper()
            logger.info("✅ cloudscraper disponível para fallback de Cloudflare")
            return scraper
        except Exception as e:
            logger.warning(f"⚠️ Não foi possível inicializar cloudscraper: {e}")
            return None

    def _decodificar_resposta(self, resposta: requests.Response) -> str:
        """Retorna texto decodificado mesmo quando a resposta vier comprimida em brotli."""
        if not resposta:
            return ''

        content_encoding = resposta.headers.get('Content-Encoding', '').lower()
        if 'br' in content_encoding:
            try:
                import brotli
                return brotli.decompress(resposta.content).decode(resposta.encoding or 'utf-8', errors='replace')
            except Exception as e:
                logger.warning(f"⚠️ Falha ao decodificar brotli: {e}. Tentando fallback com decode direto.")
                return resposta.content.decode(resposta.encoding or 'utf-8', errors='replace')

        return resposta.text
    
    def carregar_emails(self) -> bool:
        """Carrega emails do arquivo emails.txt"""
        arquivo = DATA_DIR / 'emails.txt'
        
        if not arquivo.exists():
            logger.error(f"❌ Arquivo {arquivo} não encontrado!")
            return False
        
        try:
            with open(arquivo, 'r', encoding='utf-8') as f:
                emails = [linha.strip() for linha in f.readlines() if linha.strip()]
            
            # Filtrar emails duplicados e inválidos
            self.emails = []
            for email in emails:
                if self._validar_email(email) and email not in self.emails:
                    self.emails.append(email)
            
            # Remover emails já processados
            self.emails = [e for e in self.emails if e not in self.contas_criadas]
            
            logger.info(f"✅ Carregados {len(self.emails)} emails válidos")
            return True
        
        except Exception as e:
            logger.error(f"❌ Erro ao carregar emails: {e}")
            return False
    
    def carregar_usernames(self) -> bool:
        """Carrega usernames do arquivo usernames.txt"""
        arquivo = DATA_DIR / 'usernames.txt'
        
        if not arquivo.exists():
            logger.error(f"❌ Arquivo {arquivo} não encontrado!")
            return False
        
        try:
            with open(arquivo, 'r', encoding='utf-8') as f:
                usernames = [linha.strip() for linha in f.readlines() if linha.strip()]
            
            # Filtrar usernames duplicados
            self.usernames = []
            for username in usernames:
                if username not in self.usernames:
                    self.usernames.append(username)
            
            logger.info(f"✅ Carregados {len(self.usernames)} usernames disponíveis")
            return True
        
        except Exception as e:
            logger.error(f"❌ Erro ao carregar usernames: {e}")
            return False
    
    def carregar_proxies(self) -> bool:
        """Carrega proxies pagos e fallback público se necessário."""
        self.paid_proxies = self._load_proxy_file(DATA_DIR / 'proxies.txt')
        self.public_proxies = self._load_proxy_file(DATA_DIR / 'public_proxies.txt')

        if self.paid_proxies:
            logger.info(f"✅ Carregados {len(self.paid_proxies)} proxies pagos")
            return True

        if self.public_proxies and self.config['proxy'].get('use_public_fallback', True):
            logger.warning("⚠️ Nenhum proxy pago encontrado em proxies.txt; usando public_proxies.txt como fallback")
            self.paid_proxies = self.public_proxies
            self.public_proxies = []
            return True

        logger.error("❌ Nenhum proxy pago encontrado em proxies.txt")
        if self.public_proxies:
            logger.warning("⚠️ Public proxies disponíveis, mas fallback está desabilitado nas configurações")
        return False

    def _load_proxy_file(self, arquivo: Path) -> List[str]:
        """Carrega proxies de um arquivo específico"""
        if not arquivo.exists():
            return []

        try:
            with open(arquivo, 'r', encoding='utf-8') as f:
                return [
                    linha.strip()
                    for linha in f.readlines()
                    if linha.strip() and not linha.strip().startswith('#')
                ]
        except Exception as e:
            logger.warning(f"⚠️ Erro ao carregar proxies de {arquivo}: {e}")
            return []
    
    def _validar_proxies(self) -> None:
        """Valida proxies pagos testando conectividade."""
        if not self.paid_proxies:
            if self.public_proxies and self.config['proxy'].get('use_public_fallback', True):
                logger.warning("⚠️ Nenhum proxy pago carregado. Usando public_proxies.txt como fallback para validação.")
                self.paid_proxies = self.public_proxies
                self.public_proxies = []
            else:
                logger.warning("⚠️ Nenhum proxy para validar")
                return

        logger.info(f"🔍 Iniciando validação de {len(self.paid_proxies)} proxies pagos...")
        
        proxies_validos = []
        total = len(self.paid_proxies)
        proxies_para_validar = self.paid_proxies[:15]
        if len(self.paid_proxies) > 15:
            logger.info(f"ℹ️ Validando apenas os primeiros 15 proxies pagos por enquanto")
        
        for i, proxy_str in enumerate(proxies_para_validar, 1):
            logger.info(f"🔍 Testando proxy {i}/{len(proxies_para_validar)}")
            
            try:
                proxy_dict = self._build_proxy_dict(proxy_str)
                if not proxy_dict:
                    continue
                
                # Teste rápido com httpbin.org/ip
                response = requests.get(
                    'https://httpbin.org/ip',
                    proxies=proxy_dict,
                    timeout=10,
                    headers={'User-Agent': random.choice(self.USER_AGENTS)}
                )
                
                if response.status_code == 200:
                    # Verificar se retornou um IP válido
                    data = response.json()
                    origin_ip = data.get('origin', '').split(',')[0].strip()
                    if origin_ip and len(origin_ip.split('.')) == 4:
                        proxies_validos.append(proxy_str)
                        logger.info(f"✅ Proxy válido: {origin_ip}")
                    else:
                        logger.warning(f"❌ Proxy inválido (resposta inesperada): {proxy_str}")
                else:
                    logger.warning(f"❌ Proxy inválido (status {response.status_code}): {proxy_str}")
                    
            except Exception as e:
                logger.warning(f"❌ Proxy falhou ({str(e)[:50]}...): {proxy_str}")
            
            # Pequena pausa para não sobrecarregar
            time.sleep(0.5)
        
        self.paid_proxies = proxies_validos
        logger.info(f"✅ Validação concluída: {len(proxies_validos)}/{total} proxies válidos")

        if not self.paid_proxies and self.public_proxies and self.config['proxy'].get('use_public_fallback', True):
            logger.warning("⚠️ Nenhum proxy pago válido após validação. Tentando public_proxies.txt como fallback.")
            self.paid_proxies = self.public_proxies
            self.public_proxies = []
            self._validar_proxies()
    
    def _validar_email(self, email: str) -> bool:
        """Valida formato básico de email"""
        padrao = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(padrao, email) is not None
    
    def gerar_username(self) -> Optional[str]:
        """Retorna um username da lista pré-definida"""
        if not self.usernames:
            logger.warning("⚠️ Lista de usernames vazia! Adicione usernames em usernames.txt")
            return None
        return random.choice(self.usernames)
    
    def remover_username(self, username: str) -> None:
        """Remove um username da lista após uso bem-sucedido"""
        if username in self.usernames:
            self.usernames.remove(username)
            # Salvar a lista atualizada no arquivo
            arquivo = DATA_DIR / 'usernames.txt'
            try:
                with open(arquivo, 'w', encoding='utf-8') as f:
                    for u in self.usernames:
                        f.write(u + '\n')
                logger.debug(f"✅ Username {username} removido da lista")
            except Exception as e:
                logger.warning(f"⚠️ Erro ao salvar usernames atualizados: {e}")
    
    def gerar_senha(self, tamanho_min: int = 8, tamanho_max: int = 16) -> str:
        """Gera senha aleatória alfanumérica forte (maiúsculas, minúsculas, números)"""
        tamanho = random.randint(tamanho_min, tamanho_max)
        
        maiusculas = random.choice(string.ascii_uppercase)
        minusculas = random.choice(string.ascii_lowercase)
        numeros = random.choice(string.digits)
        
        caracteres_restantes = string.ascii_letters + string.digits
        senha = [maiusculas, minusculas, numeros]
        senha += [random.choice(caracteres_restantes) for _ in range(tamanho - 3)]
        
        random.shuffle(senha)
        return ''.join(senha)
    
    def _obter_proxy(self, proxy_type: str = 'paid') -> Optional[Dict[str, str]]:
        """Retorna o próximo proxy da lista selecionada com rotação"""
        proxy_list = self.paid_proxies if proxy_type == 'paid' else self.public_proxies
        if not proxy_list:
            return None

        index = self.proxy_indexes.get(proxy_type, 0)
        proxy_str = proxy_list[index].strip()
        self.proxy_indexes[proxy_type] = (index + 1) % len(proxy_list)

        try:
            return self._build_proxy_dict(proxy_str)
        except Exception as e:
            logger.warning(f"⚠️ Erro ao processar proxy {proxy_str}: {e}")
            return None

    def _set_current_proxy(self, proxy_dict: Optional[Dict[str, str]]):
        """Define o proxy atual para manter sessão consistente"""
        if proxy_dict:
            proxy_url = proxy_dict.get('http', '')
            from urllib.parse import urlparse
            parsed = urlparse(proxy_url)
            proxy_ip = parsed.hostname or 'unknown'
            logger.info(f"🔄 Proxy da sessão definido: {proxy_ip}")
        self.current_proxy = proxy_dict
    
    def _get_current_proxy(self) -> Optional[Dict[str, str]]:
        """Retorna o proxy atual"""
        return self.current_proxy
    
    def _build_proxy_dict(self, proxy_str: str) -> Optional[Dict[str, str]]:
        """Constrói um dicionário de proxy compatível com requests."""
        if not proxy_str:
            return None

        proxy_str = proxy_str.strip().rstrip('/')
        if proxy_str.lower().startswith(('http://', 'https://', 'socks5://', 'socks4://')):
            proxy_url = proxy_str
        elif '@' in proxy_str and proxy_str.count(':') == 3:
            ip, porta, user, password = proxy_str.split(':', 3)
            proxy_url = f"http://{user}:{password}@{ip}:{porta}"
        elif ':' in proxy_str:
            proxy_url = f"http://{proxy_str}"
        else:
            return None

        return {
            'http': proxy_url,
            'https': proxy_url
        }
    
    def _fazer_requisicao(self, method: str, url: str, force_direct: bool = False, **kwargs) -> Optional[requests.Response]:
        """Faz requisição HTTP com opção de acesso direto ou via proxy"""
        max_tentativas = self.config['retry'].get('max_tentativas', 3)
        use_public_fallback = self.config['proxy'].get('use_public_fallback', True)
        skip_endpoints = self.config['proxy'].get('skip_for_endpoints', [])
        
        should_skip_proxy = force_direct or any(ep in url for ep in skip_endpoints)
        force_proxy = self.config['proxy'].get('force_proxy', False)
        
        if force_proxy and not should_skip_proxy:
            should_skip_proxy = False
            logger.info(f"🔒 Forçando uso de proxy para {url.split('/')[-1]} (configuração force_proxy)")
        
        if should_skip_proxy:
            logger.info(f"🔓 Acessando {url.split('/')[-1]} sem proxy (acesso direto)")
            return self._fazer_requisicao_direto(method, url, **kwargs)
        
        # Usar proxy atual se definido (para manter sessão)
        current_proxy = self._get_current_proxy()
        if current_proxy:
            logger.info(f"🔄 Usando proxy atual da sessão para {url.split('/')[-1]}")
            kwargs['proxies'] = current_proxy
            kwargs['timeout'] = self.config['timeout'].get('requisicao', 20)
            
            # Rotacionar User-Agent
            self.session.headers['User-Agent'] = random.choice(self.USER_AGENTS)
            
            try:
                if method.upper() == 'GET':
                    resposta = self.session.get(url, **kwargs)
                elif method.upper() == 'POST':
                    resposta = self.session.post(url, **kwargs)
                else:
                    return None
                
                # Verificar bloqueios - NÃO TENTAR CLOUDSCRAPER
                if resposta.status_code in [403, 503] or any(term in resposta.text.lower() for term in ['checking your browser', 'cloudflare', 'cf-challenge', 'cf-browser-verification']):
                    logger.warning(f"⚠️ Bloqueio Cloudflare detectado (status {resposta.status_code}) - Modo Playwright é obrigatório em 2026")
                    self._set_current_proxy(None)
                    return None
                else:
                    resposta.raise_for_status()
                    return resposta
            except Exception as e:
                logger.warning(f"⚠️ Proxy atual falhou: {e}")
                self._set_current_proxy(None)
        # Lógica original de rotação de proxies
        proxy_groups = []
        if self.paid_proxies:
            proxy_groups.append('paid')

        if not proxy_groups:
            logger.error("❌ Nenhum proxy pago disponível para requisição")
            return None

        for proxy_type in proxy_groups:
            for tentativa in range(max_tentativas):
                try:
                    proxy = self._obter_proxy(proxy_type)
                    kwargs['proxies'] = proxy
                    kwargs['timeout'] = self.config['timeout'].get('requisicao', 20)

                    # Rotacionar User-Agent
                    self.session.headers['User-Agent'] = random.choice(self.USER_AGENTS)

                    if method.upper() == 'GET':
                        resposta = self.session.get(url, **kwargs)
                    elif method.upper() == 'POST':
                        resposta = self.session.post(url, **kwargs)
                    else:
                        return None

                    if resposta.status_code == 429:
                        logger.warning(f"⚠️ Rate limit (429) na tentativa {tentativa + 1}/{max_tentativas}")
                        delay = self.config['delays'].get('apos_429', 30)
                        time.sleep(delay)
                        continue

                    if resposta.status_code in [403, 503] or any(term in resposta.text.lower() for term in ['checking your browser', 'cloudflare', 'cf-challenge', 'cf-browser-verification']):
                        logger.warning(f"⚠️ Cloudflare ou bloqueio detectado na tentativa {tentativa + 1}/{max_tentativas} (status {resposta.status_code})")
                        if self.scraper:
                            scraper_kwargs = {k: v for k, v in kwargs.items() if k != 'proxies'}
                            scraper_kwargs['proxies'] = proxy
                            scraper_response = self._fazer_requisicao_com_cloudscraper(method, url, **scraper_kwargs)
                            if scraper_response:
                                self._sync_scraper_cookies_to_session()
                                return scraper_response
                        time.sleep(random.uniform(1, 3))
                        continue

                    resposta.raise_for_status()
                    # Se sucesso, definir como proxy atual para próximas requisições
                    self._set_current_proxy(proxy)
                    return resposta

                except requests.exceptions.ProxyError:
                    logger.warning(f"⚠️ Erro de proxy na tentativa {tentativa + 1}/{max_tentativas} ({proxy_type})")
                    time.sleep(self.config['retry'].get('delay_entre_tentativas', 1))

                except requests.exceptions.Timeout:
                    logger.warning(f"⚠️ Timeout na tentativa {tentativa + 1}/{max_tentativas} ({proxy_type})")
                    time.sleep(self.config['retry'].get('delay_entre_tentativas', 1))

                except requests.exceptions.ConnectionError as e:
                    logger.warning(f"⚠️ Erro de conexão na tentativa {tentativa + 1}/{max_tentativas} ({proxy_type}): {e}")
                    time.sleep(self.config['retry'].get('delay_entre_tentativas', 1))

                except requests.exceptions.RequestException as e:
                    logger.warning(f"⚠️ Erro na requisição (tentativa {tentativa + 1}/{max_tentativas}, {proxy_type}): {e}")
                    time.sleep(self.config['retry'].get('delay_entre_tentativas', 1))

        return None

    def _fazer_requisicao_direto(self, method: str, url: str, **kwargs) -> Optional[requests.Response]:
        """Faz requisição direta (sem proxy) com tratamento de rate limit"""
        max_tentativas = self.config['retry'].get('max_tentativas', 3)

        for tentativa in range(max_tentativas):
            try:
                kwargs['timeout'] = self.config['timeout'].get('requisicao', 20)
                kwargs['proxies'] = None

                self.session.headers['User-Agent'] = random.choice(self.USER_AGENTS)

                if method.upper() == 'GET':
                    resposta = self.session.get(url, **kwargs)
                elif method.upper() == 'POST':
                    resposta = self.session.post(url, **kwargs)
                else:
                    return None

                if resposta.status_code == 429:
                    logger.warning(f"⚠️ Rate limit (429) na tentativa {tentativa + 1}/{max_tentativas}")
                    delay = self.config['delays'].get('apos_429', 30)
                    logger.info(f"⏳ Aguardando {delay} segundos antes de tentar novamente...")
                    time.sleep(delay)
                    continue

                if resposta.status_code in [403, 503] or any(term in resposta.text.lower() for term in ['checking your browser', 'cloudflare', 'cf-challenge', 'cf-browser-verification']):
                    logger.warning(f"⚠️ Cloudflare ou bloqueio detectado na tentativa {tentativa + 1}/{max_tentativas} (status {resposta.status_code})")
                    if self.scraper:
                        scraper_response = self._fazer_requisicao_com_cloudscraper(method, url, **kwargs)
                        if scraper_response:
                            return scraper_response
                    time.sleep(random.uniform(1, 3))
                    continue

                resposta.raise_for_status()
                return resposta

            except requests.exceptions.Timeout:
                logger.warning(f"⚠️ Timeout na tentativa {tentativa + 1}/{max_tentativas}")
                time.sleep(self.config['retry'].get('delay_entre_tentativas', 1))

            except requests.exceptions.ConnectionError as e:
                logger.warning(f"⚠️ Erro de conexão na tentativa {tentativa + 1}/{max_tentativas}: {e}")
                time.sleep(self.config['retry'].get('delay_entre_tentativas', 1))

            except requests.exceptions.RequestException as e:
                logger.warning(f"⚠️ Erro na requisição (tentativa {tentativa + 1}/{max_tentativas}): {e}")
                time.sleep(self.config['retry'].get('delay_entre_tentativas', 1))

        return None

    def _fazer_requisicao_com_cloudscraper(self, method: str, url: str, **kwargs) -> Optional[requests.Response]:
        """Faz a requisição usando cloudscraper quando Cloudflare bloqueia"""
        if not self.scraper:
            return None

        try:
            kwargs['timeout'] = kwargs.get('timeout', 20)
            if method.upper() == 'GET':
                resposta = self.scraper.get(url, **kwargs)
            elif method.upper() == 'POST':
                resposta = self.scraper.post(url, **kwargs)
            else:
                return None

            if resposta.status_code in [403, 503]:
                logger.warning(f"⚠️ Cloudflare ainda bloqueando via cloudscraper (status {resposta.status_code})")
                return None

            resposta.raise_for_status()
            return resposta
        except Exception as e:
            logger.warning(f"⚠️ Erro no fallback cloudscraper: {e}")
            return None

    def _sync_scraper_cookies_to_session(self) -> None:
        """Sincroniza cookies coletados pelo cloudscraper para a sessão requests."""
        try:
            if self.scraper is not None and hasattr(self.scraper, 'cookies'):
                cookies = self.scraper.cookies.get_dict()
                if cookies:
                    self.session.cookies.update(cookies)
                    logger.debug("✅ Cookies do cloudscraper sincronizados para a sessão requests")
        except Exception as e:
            logger.warning(f"⚠️ Erro ao sincronizar cookies do cloudscraper: {e}")
    
    def obter_user_data(self) -> Optional[Dict[str, str]]:
        """
        PASSO 1: Obter UserID, k1 e k2 via auser3.php.
        """
        try:
            logger.info(f"🔗 Obtendo UserID/k1/k2 via {self.AUSER_URL}")
            resposta = self._fazer_requisicao('GET', self.AUSER_URL)

            if not resposta:
                logger.error("❌ Falha ao obter resposta de auser3.php")
                return None

            texto_resposta = self._decodificar_resposta(resposta)
            query_data = parse_qs(texto_resposta.lstrip('&').strip())

            user_data: Dict[str, str] = {}
            for chave in ['UserId', 'k1', 'k2']:
                if query_data.get(chave):
                    user_data[chave] = query_data[chave][0]

            # Tentar JSON caso a resposta seja JSON
            if not user_data.get('UserId') or not user_data.get('k2'):
                try:
                    json_data = json.loads(texto_resposta)
                    for chave in ['UserId', 'k1', 'k2']:
                        if chave in json_data and json_data[chave]:
                            user_data[chave] = str(json_data[chave])
                except Exception:
                    pass

            # Fallback por regex
            for chave in ['UserId', 'k1', 'k2']:
                if not user_data.get(chave):
                    match = re.search(rf'{chave}["\']?\s*[:=]\s*["\']?([^&"\'\s]+)', texto_resposta, re.IGNORECASE)
                    if match:
                        user_data[chave] = match.group(1)

            if not user_data.get('UserId'):
                logger.error("❌ Não foi possível extrair UserID da resposta de auser3.php")
                logger.info(f"Resposta recebida (primeiros 1000 chars): {texto_resposta[:1000]}")
                return None

            if user_data.get('k2'):
                logger.info(f"✅ UserData obtido: UserId={user_data.get('UserId')} k2={user_data.get('k2')[:30]}...")
            else:
                logger.warning("⚠️ UserId obtido, mas k2 não foi encontrado em auser3.php")
                logger.info(f"Resposta de auser3.php: {texto_resposta[:500]}")

            return user_data

        except Exception as e:
            logger.error(f"❌ Erro ao obter dados de auser3.php: {e}")
            return None

    def acessar_pagina_login(self, user_id: str, k2_token: str = "") -> Optional[str]:
        """
        PASSO 2: Acessar página login para extrair token k2 e preparar sessão
        Retorna o token k2 ou string vazia se a página for carregada corretamente mas k2 não estiver no HTML.
        """
        try:
            self.last_recaptcha_sitekey = None
            self.last_captcha_page_url = None
            url = f"{self.LOGIN_URL}?mode=1&UserId={user_id}"
            if k2_token:
                url = f"{url}&k2={k2_token}"
            logger.info(f"🔗 Acessando página de login com UserId: {user_id} k2={k2_token[:30]}...")

            headers = dict(self.session.headers)
            headers.update({
                'Referer': f"{self.LOGIN_URL}?mode=1&UserId={user_id}",
                'Origin': self.BASE_URL,
            })

            resposta = self._fazer_requisicao('GET', url, headers=headers)

            if not resposta:
                logger.error("❌ Falha ao acessar página de login")
                return None

            texto_resposta = self._decodificar_resposta(resposta)

            # Verificar se há bloqueios ou proteção na resposta
            block_terms = [
                'checking your browser', 'cf-challenge', 'cf-browser-verification',
                'access denied', 'acesso negado', 'forbidden', 'proibido',
                'rate limit exceeded', 'limite de taxa excedido', 'too many requests',
                'blocked by cloudflare', 'bloqueado pelo cloudflare',
                'security error', 'erro de segurança', 'protection mode', 'modo de proteção'
            ]

            # Verificar por bloqueios claros
            texto_lower = texto_resposta.lower()
            found_clear_blocks = [term for term in block_terms if term in texto_lower]
            
            # Se encontrou bloqueios claros, considerar como bloqueado
            if found_clear_blocks:
                logger.warning(f"⚠️ Bloqueio detectado na página de login para UserId {user_id}")
                logger.debug(f"Indicadores de bloqueio encontrados: {found_clear_blocks}")
                
                # Tentar múltiplas vezes com cloudscraper
                max_cloudflare_attempts = 3
                for attempt in range(max_cloudflare_attempts):
                    if self.scraper:
                        logger.warning(f"🔄 Tentando novamente com cloudscraper (tentativa {attempt + 1}/{max_cloudflare_attempts})...")
                        resposta = self._fazer_requisicao_com_cloudscraper('GET', url, headers=self.session.headers)
                        if resposta:
                            texto_resposta = self._decodificar_resposta(resposta)
                            texto_lower = texto_resposta.lower()
                            # Verificar novamente se o bloqueio foi resolvido
                            new_found_blocks = [term for term in block_terms if term in texto_lower]
                            
                            if not new_found_blocks:
                                logger.info("✅ Cloudscraper resolveu o bloqueio!")
                                break
                            else:
                                logger.warning(f"⚠️ Bloqueio ainda persiste (tentativa {attempt + 1})")
                                if attempt < max_cloudflare_attempts - 1:
                                    sleep_time = 5 + attempt * 2  # 5s, 7s, 9s
                                    logger.info(f"⏳ Aguardando {sleep_time}s antes de tentar novamente...")
                                    time.sleep(sleep_time)
                        else:
                            logger.warning(f"⚠️ Cloudscraper falhou na tentativa {attempt + 1}")
                    else:
                        break
                
                # Verificar final se ainda há bloqueio
                if resposta:
                    final_texto = self._decodificar_resposta(resposta)
                    final_lower = final_texto.lower()
                    final_blocks = [term for term in block_terms if term in final_lower]
                    
                    if final_blocks:
                        logger.warning("💡 Solução: Use proxy residencial ou aguarde desbloqueio do IP")
                        return None
                else:
                    return None

            soup = BeautifulSoup(texto_resposta, 'html.parser')
            
            # ✅ Se encontrar formulário de login/registro, a página é válida
            login_forms = soup.find_all('form')
            has_login_form = any('login' in str(form).lower() or 'register' in str(form).lower() for form in login_forms)
            
            if has_login_form or soup.find('input', {'name': 'username'}) or soup.find('input', {'type': 'password'}):
                logger.info(f"✅ Página de login válida encontrada para UserId {user_id}")

            # Tentar extrair sitekey de reCAPTCHA da página de login
            self.last_recaptcha_sitekey = self._extrair_sitekey(texto_resposta)
            self.last_captcha_page_url = url
            # NÃO tentar extrair sitekey de arquivos CDN - queima proxy desnecessariamente
            # if not self.last_recaptcha_sitekey:
            #     sitekey_from_js = self._extrair_sitekey_from_js_reference(texto_resposta, base_url=url)
            #     if sitekey_from_js:
            #         self.last_recaptcha_sitekey = sitekey_from_js
            #         logger.info(f"✅ Sitekey de reCAPTCHA/Turnstile capturada de script JS: {self.last_recaptcha_sitekey}")

            if self.last_recaptcha_sitekey:
                logger.info(f"✅ Sitekey de reCAPTCHA/Turnstile capturada da página de login: {self.last_recaptcha_sitekey}")

            # Tentar extrair k2 de input hidden
            input_k2 = soup.find('input', {'name': 'k2'}) or soup.find('input', {'id': 'k2'})
            if input_k2 and input_k2.get('value'):
                k2_token = input_k2['value']
                logger.info(f"✅ Token k2 obtido de input hidden: {k2_token[:30]}...")
                return k2_token

            # Tentar extrair k2 de atributo data
            data_attr = soup.find(attrs={'data-k2': True})
            if data_attr:
                k2_token = data_attr.get('data-k2')
                if k2_token:
                    logger.info(f"✅ Token k2 obtido de data-k2: {k2_token[:30]}...")
                    return k2_token

            # Tentar extrair k2 por regex
            patterns = [
                r'["\']?k2["\']?\s*[:=]\s*["\']([^"\']+)["\']',
                r'k2\s*=\s*["\']([^"\']+)["\']',
                r'k2\s*:\s*["\']([^"\']+)["\']',
                r'data-k2=["\']([^"\']+)["\']',
                r'k2["\']?\s*[:=]\s*([0-9a-zA-Z_-]{20,})'
            ]

            for pattern in patterns:
                match = re.search(pattern, texto_resposta, re.IGNORECASE)
                if match:
                    k2_token = match.group(1)
                    logger.info(f"✅ Token k2 obtido via regex: {k2_token[:30]}...")
                    return k2_token

            # Se encontrou o formulário mas não o k2, é possível que o k2 seja gerado por JS
            if has_login_form:
                logger.warning("⚠️ Formulário encontrado mas k2 não extraído - pode ser gerado por JavaScript")
                logger.debug(f"Conteúdo da página (primeiros 1000 chars): {texto_resposta[:1000]}")
                # Retornar string vazia para permitir prosseguir
                return ""
            
            logger.warning("⚠️ Token k2 não encontrado na página")
            if any(term in texto_resposta.lower() for term in ['recaptcha', 'g-recaptcha', 'h-captcha', 'captcha']):
                logger.warning("⚠️ Parece haver um bloqueio de captcha na página de login")
            logger.debug(f"Login HTML/JS inicial: {texto_resposta[:500]}")
            return ""
        
        except Exception as e:
            logger.error(f"❌ Erro ao acessar página de login: {e}")
            return None
    
    def criar_conta(self, username: str, senha: str, email: str, user_id: str, k2_token: str = "") -> bool:
        """
        PASSO 3 e 4: Submeter formulário de cadastro e validar sucesso
        """
        try:
            logger.info(f"📝 Criando conta: {username} | {email}")

            # Preparar dados do formulário
            dados = {
                'Register': 1,
                'UserId': user_id,
                'k2': k2_token,
                'Username': username,
                'agree': 'ON',
                'password': senha,
                'password2': senha,
                'email': email
            }

            # Headers adicionais para fazer parecer um navegador real
            headers = {
                'Referer': f"{self.LOGIN_URL}?mode=1&UserId={user_id}&k2={k2_token}",
                'Origin': self.BASE_URL,
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-Requested-With': 'XMLHttpRequest',
                'Accept': 'application/json, text/javascript, */*; q=0.01'
            }

            url_registro = f"{self.BASE_URL}/web_gear/chat/register5.php"
            resposta = self._fazer_requisicao('POST', url_registro, data=dados, headers=headers)

            if not resposta:
                logger.error("❌ Falha ao submeter formulário de cadastro. Possível proxy inválido, timeout ou bloqueio do servidor.")
                return False

            texto_resposta = self._decodificar_resposta(resposta)
            if self._detectar_recaptcha(texto_resposta):
                sitekey = self._extrair_sitekey(texto_resposta)
                if sitekey:
                    logger.warning(f"⚠️ reCAPTCHA detectado para {email}. Sitekey encontrada: {sitekey}")
                else:
                    logger.warning("⚠️ reCAPTCHA detectado mas sem sitekey no retorno do register5.php")

                if not sitekey and self.last_recaptcha_sitekey:
                    sitekey = self.last_recaptcha_sitekey
                    logger.info("ℹ️ Usando sitekey extraída da página de login para resolver o reCAPTCHA")

                if not sitekey:
                    logger.warning(f"⚠️ Não foi possível criar conta devido a reCAPTCHA não resolvível para {email}")
                    logger.debug(f"Resposta suspeita de bloqueio: {texto_resposta[:500]}")
                    return False

                if self.config['captcha_solver'].get('enabled', False):
                    token = self._resolver_recaptcha(sitekey, self.last_captcha_page_url or url_registro)
                    if token:
                        response_field = 'cf-turnstile-response' if sitekey.startswith('0x') else 'g-recaptcha-response'
                        dados[response_field] = token
                        resposta = self._fazer_requisicao('POST', url_registro, data=dados, headers=headers)
                        if resposta:
                            texto_resposta = self._decodificar_resposta(resposta)
                            if not self._detectar_recaptcha(texto_resposta):
                                logger.info("✅ reCAPTCHA/Turnstile resolvido via solver")
                                sucesso = self._avaliar_resposta_criacao(resposta, username)
                                # ⚠️ FEATURE 1: Se falhou mas não é recaptcha, pode ser shadowban - blacklist IP
                                if not sucesso and not self._detectar_recaptcha(texto_resposta):
                                    self._detectar_e_processar_shadowban(username, email, texto_resposta)
                                return sucesso
                            logger.warning("⚠️ reCAPTCHA ainda presente após solver")
                        else:
                            logger.warning("⚠️ Falha ao reenviar formulário após solver de reCAPTCHA")
                    else:
                        logger.warning("⚠️ Solver de reCAPTCHA falhou ou retornou token inválido")
                else:
                    logger.warning("⚠️ Solver de reCAPTCHA não está habilitado na configuração")

                logger.warning(f"⚠️ Não foi possível criar conta devido a reCAPTCHA para {email}")
                logger.debug(f"Resposta de cadastro com recaptcha: {texto_resposta[:500]}")
                return False

            sucesso = self._avaliar_resposta_criacao(resposta, username)
            # ⚠️ FEATURE 1: Se falhou, detectar se é shadowban e blacklist IP
            if not sucesso:
                self._detectar_e_processar_shadowban(username, email, texto_resposta)
            return sucesso

        except Exception as e:
            logger.error(f"❌ Erro ao criar conta: {e}")
            return False

    def _avaliar_resposta_criacao(self, resposta: requests.Response, username: str) -> bool:
        """Avalia se a resposta indica sucesso ou falha na criação"""
        texto = self._decodificar_resposta(resposta)
        texto_lower = texto.lower()

        logger.debug(f"Status code: {resposta.status_code}")
        logger.debug(f"Headers: {dict(resposta.headers)}")
        logger.debug(f"Resposta completa (primeiros 1000 chars): {texto[:1000]}")

        json_data = None
        try:
            json_data = json.loads(texto)
        except Exception:
            json_data = None

        if isinstance(json_data, dict):
            if 'UserId' in json_data and 'k2' in json_data:
                logger.info(f"✅ Registro confirmado via resposta JSON para {username}")
                return True

            err_obj = json_data.get('Err') or json_data.get('err')
            if isinstance(err_obj, dict):
                errors = []
                success_flags = []
                for key, value in err_obj.items():
                    if value:
                        if key in ['regdone', 'captoken', 'loginok', 'Settings']:
                            success_flags.append(key)
                        else:
                            errors.append(f"{key}: {value}")

                if success_flags:
                    logger.info(f"✅ Registro atualizado via resposta JSON para {username}: {', '.join(success_flags)}")
                    return True
                if errors:
                    logger.warning(f"⚠️ Resposta JSON com erro(s) para {username}: {' | '.join(errors)}")
                    return False

        # Verificar mensagens de erro específicas no HTML/texto
        error_keywords = [
            'username already exists', 'já existe', 'username taken', 'nome de usuário já em uso',
            'email already registered', 'email já cadastrado', 'email already exists',
            'invalid username', 'username inválido', 'username not allowed',
            'password too weak', 'senha muito fraca', 'password requirements not met',
            'registration failed', 'falha no cadastro', 'account creation failed',
            'error', 'erro', 'falhou', 'invalid', 'inválido',
            'banned', 'banido', 'suspended', 'suspenso',
            'rate limit', 'limite de taxa', 'too many requests',
            'captcha', 'recaptcha', 'verification failed',
            'blocked', 'bloqueado', 'block', 'ban',
            'forbidden', 'proibido', 'access denied', 'acesso negado',
            'security', 'seguranca', 'protection', 'protecao'
        ]

        for error in error_keywords:
            if error in texto_lower:
                logger.warning(f"⚠️ Erro detectado na resposta: '{error}' para {username}")
                logger.debug(f"Resposta de erro completa: {texto}")
                return False

        # Verificar se há redirecionamento para página de sucesso ou login
        if resposta.status_code in [200, 302, 303]:
            if 'location' in resposta.headers:
                location = resposta.headers['location'].lower()
                if 'login' in location or 'home' in location or 'welcome' in location or 'success' in location:
                    logger.info(f"✅ Conta criada com sucesso: {username} (redirecionamento detectado)")
                    return True

            success_keywords = [
                'success', 'sucesso', 'account created', 'conta criada',
                'registration successful', 'cadastro realizado',
                'welcome', 'bem-vindo', 'thank you', 'obrigado',
                'confirm your email', 'confirme seu email',
                'check your email', 'verifique seu email'
            ]

            for success in success_keywords:
                if success in texto_lower:
                    logger.info(f"✅ Conta criada com sucesso: {username}")
                    return True

            if resposta.status_code == 200:
                soup = BeautifulSoup(texto, 'html.parser')
                login_form = soup.find('form', {'action': lambda x: x and 'login' in x.lower()}) or \
                            soup.find('input', {'name': 'username'}) and soup.find('input', {'name': 'password'})
                if login_form:
                    logger.warning(f"⚠️ Formulário de login detectado na resposta - conta não criada: {username}")
                    logger.debug(f"Resposta suspeita: {texto[:500]}")
                    return False

                error_elements = soup.find_all(['div', 'span', 'p'], class_=lambda x: x and ('error' in x.lower() or 'alert' in x.lower() or 'danger' in x.lower()))
                for element in error_elements:
                    if element.get_text().strip():
                        logger.warning(f"⚠️ Elemento de erro encontrado no HTML: {element.get_text().strip()}")
                        return False

                block_indicators = soup.find_all(text=lambda text: text and any(word in text.lower() for word in ['blocked', 'bloqueado', 'ban', 'banido', 'suspended', 'suspenso', 'security', 'seguranca', 'protection', 'protecao', 'firewall', 'waf']))
                if block_indicators:
                    logger.warning(f"⚠️ Indicadores de bloqueio detectados na resposta para {username}")
                    for indicator in block_indicators:
                        logger.debug(f"Indicador de bloqueio: {indicator.strip()}")
                    return False

                logger.info(f"✅ Resposta 200 OK - Conta possivelmente criada: {username} (sem confirmação clara)")
                logger.debug(f"Resposta 200 sem confirmação: {texto[:500]}")
                return True

        if resposta.status_code >= 400:
            logger.warning(f"⚠️ Status code de erro {resposta.status_code} para {username}")
            logger.debug(f"Resposta de erro: {texto[:500]}")
            return False

        logger.warning(f"⚠️ Resposta inesperada (status {resposta.status_code}) para {username}")
        logger.debug(f"Resposta: {texto[:500]}")
        return False

    def _detectar_recaptcha(self, texto: str) -> bool:
        texto_lower = texto.lower()

        if any(term in texto_lower for term in ['data-sitekey=', 'g-recaptcha', 'h-captcha', 'cf-turnstile', 'turnstile']):
            return True

        if 'registercap' in texto_lower and 'recaptcha' in texto_lower:
            return True

        if 'the recaptcha' in texto_lower or 'recaptcha wasn' in texto_lower or 'recaptcha said' in texto_lower:
            return True

        return False

    def _extrair_sitekey(self, html: str) -> Optional[str]:
        patterns = [
            r'data-sitekey=["\']([^"\']+)["\']',
            r'data-sitekey=(?:\\x22|["\'])([^"\\\']+)(?:\\x22|["\'])',
            r'sitekey=(?:["\']?)([^"\'&>\s]+)(?:["\']?)'
        ]

        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    def _extrair_sitekey_from_js_reference(self, html: str, base_url: str) -> Optional[str]:
        """Extrai sitekey de scripts JS referenciados pela página de login."""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            script_tags = [tag.get('src') for tag in soup.find_all('script', src=True) if tag.get('src')]

            for script_src in script_tags:
                script_url = script_src
                if script_src.startswith('//'):
                    script_url = f"https:{script_src}"
                elif script_src.startswith('/'):
                    script_url = urljoin(self.BASE_URL, script_src)
                elif not script_src.startswith('http'):
                    script_url = urljoin(base_url, script_src)

                logger.info(f"🔍 Tentando extrair sitekey de script {script_url}")
                response = self._fazer_requisicao('GET', script_url)
                if not response or response.status_code != 200:
                    continue

                js_text = self._decodificar_resposta(response)
                sitekey = self._extrair_sitekey(js_text)
                if sitekey:
                    return sitekey

        except Exception as e:
            logger.warning(f"⚠️ Erro ao extrair sitekey de JS: {e}")
        return None

    def carregar_contas_existentes(self):
        """Carrega contas já criadas para evitar duplicatas"""
        arquivo = DATA_DIR / 'success_criacao.txt'
        
        if not arquivo.exists():
            return
        
        try:
            with open(arquivo, 'r', encoding='utf-8') as f:
                for linha in f:
                    partes = linha.strip().split('|')
                    if len(partes) >= 3:
                        email = partes[2]
                        if len(partes) == 6:
                            user_id = partes[3]
                            k2_token = ''
                            timestamp = partes[4]
                            status = partes[5]
                        else:
                            user_id = partes[3]
                            k2_token = partes[4]
                            timestamp = partes[5] if len(partes) > 5 else ''
                            status = partes[6] if len(partes) > 6 else 'sucesso'

                        self.contas_criadas[email] = {
                            'username': partes[0],
                            'email': email,
                            'user_id': user_id,
                            'k2': k2_token,
                            'timestamp': timestamp,
                            'status': status
                        }
            
            logger.info(f"✅ Carregadas {len(self.contas_criadas)} contas já criadas")
        
        except Exception as e:
            logger.error(f"❌ Erro ao carregar contas existentes: {e}")
    
    def salvar_sucesso(self, username: str, senha: str, email: str, user_id: str, k2_token: str = "", status: str = "sucesso"):
        """Salva conta criada com sucesso em success_criacao.txt"""
        try:
            DATA_DIR.mkdir(exist_ok=True)
            arquivo = DATA_DIR / 'success_criacao.txt'
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            k2_field = k2_token if k2_token else ''
            
            linha = f"{username}|{senha}|{email}|{user_id}|{k2_field}|{timestamp}|{status}\n"
            
            with open(arquivo, 'a', encoding='utf-8') as f:
                f.write(linha)
            
            k2_log = f" k2={k2_token[:30]}..." if k2_token else ''
            logger.info(f"💾 Conta salva em success_criacao.txt{k2_log}")
        
        except Exception as e:
            logger.error(f"❌ Erro ao salvar conta: {e}")
    
    def processar_emails(self):
        """Loop principal de processamento de emails"""
        if not self.emails:
            logger.error("❌ Nenhum email para processar!")
            return
        
        total = len(self.emails)
        logger.info(f"🎯 Iniciando criação de {total} contas")
        logger.info("=" * 60)
        
        for idx, email in enumerate(self.emails, 1):
            try:
                logger.info(f"\n📧 Processando: {idx}/{total} - {email}")
                
                # Resetar proxy atual para nova conta (manter sessão consistente)
                self._set_current_proxy(None)
                
                # Gerar dados da conta
                username = self.gerar_username()
                if not username:
                    logger.error("❌ Nenhum username disponível para gerar conta")
                    continue
                senha = self.gerar_senha()
                
                # PASSO 1: Obter UserId, k1 e k2 de auser3.php
                user_data = self.obter_user_data()
                if not user_data or not user_data.get('UserId'):
                    logger.error(f"❌ Não foi possível obter UserId para {email}")
                    continue

                user_id = user_data['UserId']
                k2_token_initial = user_data.get('k2', '')

                # Delay após requisição (configurável)
                delay = random.uniform(
                    self.config['delays'].get('min_entre_requisicoes', 5),
                    self.config['delays'].get('max_entre_requisicoes', 10)
                )
                logger.info(f"⏳ Aguardando {delay:.1f}s entre requisições...")
                time.sleep(delay)

                # PASSO 2: Acessar página de login para preparar sessão (SEMPRE necessário)
                logger.info(f"🔗 Preparando sessão de login com UserId: {user_id}")
                k2_token = self.acessar_pagina_login(user_id, k2_token_initial)
                if k2_token is None:
                    logger.error(f"❌ Falha ao acessar página de login para {email}")
                    continue

                if not k2_token and k2_token_initial:
                    logger.info(f"ℹ️ Usando k2 de auser3.php porque a página não retornou um token novo")
                    k2_token = k2_token_initial
                elif not k2_token:
                    logger.warning(f"⚠️ Nenhum k2 disponível, tentando prosseguir sem ele")
                    k2_token = ""

                # Delay após requisição
                delay = random.uniform(
                    self.config['delays'].get('min_entre_requisicoes', 5),
                    self.config['delays'].get('max_entre_requisicoes', 10)
                )
                logger.info(f"⏳ Aguardando {delay:.1f}s entre requisições...")
                time.sleep(delay)

                # PASSO 3 e 4: Criar conta (usando mesmo proxy da sessão)
                sucesso = self.criar_conta(username, senha, email, user_id, k2_token)
                
                if sucesso:
                    self.remover_username(username)
                    self.salvar_sucesso(username, senha, email, user_id, k2_token)
                    self.contas_criadas[email] = {
                        'username': username,
                        'email': email,
                        'user_id': user_id,
                        'k2': k2_token,
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'status': 'sucesso'
                    }
                else:
                    logger.warning(f"⚠️ Falha ao criar conta para {email}")
                
                # Delay entre contas (configurável)
                if idx < total:
                    delay = random.uniform(
                        self.config['delays'].get('min_entre_contas', 10),
                        self.config['delays'].get('max_entre_contas', 20)
                    )
                    logger.info(f"⏳ Aguardando {delay:.1f}s antes da próxima conta...")
                    time.sleep(delay)
            
            except KeyboardInterrupt:
                logger.warning("\n⚠️ Script interrompido pelo usuário")
                logger.info(f"Progresso: {idx-1}/{total} contas criadas com sucesso")
                break
            
            except Exception as e:
                logger.error(f"❌ Erro durante processamento: {e}")
                continue
        
        logger.info("=" * 60)
        logger.info(f"✅ Processamento concluído! Total de contas criadas: {len(self.contas_criadas)}/{total}")
    
    def executar(self):
        """Executa o fluxo completo de criação de contas"""
        # Carregar configurações
        self.carregar_contas_existentes()
        
        if not self.carregar_emails():
            logger.error("❌ Falha ao carregar emails. Abortando...")
            return False
        
        if not self.carregar_usernames():
            logger.error("❌ Falha ao carregar usernames. Abortando...")
            return False
        
        if not self.carregar_proxies():
            logger.error("❌ Falha ao carregar proxies. Abortando...")
            return False
        
        # Validar proxies pagos
        self._validar_proxies()
        
        if not self.paid_proxies:
            logger.error("❌ Nenhum proxy válido encontrado. Abortando...")
            return False
        
        if not self.emails:
            logger.error("❌ Nenhum email novo para processar.")
            return False
        
        # Processar emails
        self.processar_emails()
        return True


class XATBrowserAutomation:
    """Automação de navegador para XAT usando Playwright"""

    BASE_URL = "https://xat.com"
    AUSER_URL = f"{BASE_URL}/web_gear/chat/auser3.php"
    LOGIN_URL = f"{BASE_URL}/login"
    VALID_XAT_SITEKEYS = {"0x4AAAAAAA9W0lpWWjpGMSxN"}

    def __init__(self, config: Dict, proxies: List[str], bad_proxies: Optional[Set[str]] = None):
        self.config = config
        self.proxies = [p for p in proxies if p not in (bad_proxies or set())]
        self.bad_proxies: Set[str] = bad_proxies or set()
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.ads_manager: Optional[AdsPowerManager] = None
        self.use_ads_power = self.config.get('browser_automation', {}).get('use_ads_power', True)
        self.ads_power_api_url = self.config.get('browser_automation', {}).get('ads_power_api_url', 'http://127.0.0.1:50325')
        self.ads_power_api_key = self.config.get('browser_automation', {}).get('ads_power_api_key')
        self.ads_power_profile_id = self.config.get('browser_automation', {}).get('ads_power_profile_id')
        self.ads_power_profile_name = self.config.get('browser_automation', {}).get('ads_power_profile_name')
        self.current_proxy_base = None
        self.current_proxy = None
        self.proxy_session_id = None
        self.proxy_session_restart_pending = False
        self.proxy_index = 0  # Índice para rastrear proxy atual
        self.local_proxy_server = None
        self.local_proxy_thread = None
        self.last_login_block_reason: Optional[str] = None
        self.last_captcha_block_reason: Optional[str] = None
        self.proxy_session_enabled = self.config.get('proxy', {}).get('use_session_ids', True)
        self.last_proxy_test_error: Optional[str] = None
        self.user_agents = [
            # User-Agents atualizados para 2026 - compatíveis com IPs brasileiros
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/131.0.0.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/130.0.0.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1.1 Safari/605.1.15"
        ]
        self.screen_resolutions = [
            {'width': 1366, 'height': 768},
            {'width': 1440, 'height': 900},
            {'width': 1536, 'height': 864},
            {'width': 1600, 'height': 900},
            {'width': 1920, 'height': 1080},
            {'width': 1920, 'height': 1200},
            {'width': 2560, 'height': 1440}
        ]

        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError("❌ Playwright não está instalado. Execute: pip install playwright")

        # 🔥 FORCE: Inicializar com o primeiro proxy da lista imediatamente
        # Isso garante que NENHUMA requisição seja feita sem proxy
        if self.proxies:
            try:
                self._select_first_paid_proxy()
                logger.info(f"✅ Proxy inicial definido obrigatoriamente: {self.current_proxy}")
            except Exception as e:
                logger.warning(f"⚠️ Falha ao definir proxy inicial: {e}")

        logger.info("🎭 XAT Browser Automation inicializado")

    async def __aenter__(self):
        try:
            await self.initialize()
            return self
        except Exception:
            await self.cleanup()
            raise

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()

    async def initialize(self):
        """Inicializa o navegador Playwright ou AdsPower via CDP."""
        try:
            self.playwright = await async_playwright().start()
            attempt = 0
            max_attempts = len(self.proxies) if self.proxies else 3

            while attempt < max_attempts:
                # 🔥 FORCE: Na primeira tentativa, usar o proxy já definido no __init__
                # Nas tentativas seguintes, rotacionar para próximos proxies
                if attempt == 0 and self.current_proxy:
                    logger.info(f"ℹ️ Tentativa {attempt + 1}: Usando proxy inicial obrigatório já definido no __init__")
                else:
                    logger.info(f"ℹ️ Tentativa {attempt + 1}: Rotacionando para novo proxy...")
                    self._choose_next_proxy(exclude_current=(attempt > 0))
                
                # ⚠️ Teste de IP/país é obrigatório para proxies residenciais.
                # Se falhar, rotacionar proxy antes de criar o contexto.
                try:
                    if not self._test_proxy_ip_and_country(self.current_proxy, timeout=15):
                        logger.warning(f"⚠️ Proxy {self.current_proxy} falhou no teste de IP/país. Tentando criar contexto direto como fallback antes de rotacionar...")
                        try:
                            await self._create_browser_context()
                            logger.info("✅ Contexto criado com o proxy atual mesmo sem teste de IP bem-sucedido")
                            return
                        except Exception as fallback_error:
                            logger.warning(f"⚠️ Fallback direto falhou: {fallback_error}")

                        if attempt >= max_attempts - 1:
                            raise Exception("Falha no teste de IP/país para todos os proxies")
                        self._choose_next_proxy(exclude_current=True)
                        attempt += 1
                        continue
                except Exception as test_error:
                    logger.warning(f"⚠️ Teste de IP/país falhou: {test_error}")
                    if attempt >= max_attempts - 1:
                        raise
                    self._choose_next_proxy(exclude_current=True)
                    attempt += 1
                    continue
                
                try:
                    await self._create_browser_context()
                    logger.info("✅ Browser inicializado via AdsPower/Playwright")
                    return
                except Exception as e:
                    logger.error(f"❌ Erro ao inicializar contexto com proxy {self.current_proxy}: {e}")
                    attempt += 1
                    if attempt >= max_attempts:
                        raise
                    logger.info("🔄 Tentando próximo proxy para inicializar o navegador")

        except Exception as e:
            logger.error(f"❌ Erro ao inicializar navegador: {e}")
            raise

    async def cleanup(self):
        """Limpa recursos do navegador"""
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            self._stop_local_http_proxy()
            logger.info("🧹 Recursos do navegador liberados")
        except Exception as e:
            logger.warning(f"⚠️ Erro ao limpar recursos: {e}")

    def _choose_next_proxy(self, exclude_current: bool = True) -> Optional[str]:
        """Escolhe o próximo proxy da lista, validando conectividade."""
        if not self.proxies:
            logger.error("❌ Nenhum proxy disponível na lista. Não há fallback para Tor quando proxies SOCKS5 autenticados são usados.")
            return None

        current_base = self.current_proxy_base or self._normalize_proxy_base(self.current_proxy) or self.current_proxy
        options = [p for p in self.proxies if p != current_base] if exclude_current else list(self.proxies)
        if not options:
            options = list(self.proxies)

        random.shuffle(options)  # Embaralhar para tentar diferentes proxies

        for proxy_candidate in options:
            # ⚠️ Validar o PROXY BASE (sem Session ID) antes de aplicar Session ID
            normalized_base = self._normalize_proxy_base(proxy_candidate)
            if normalized_base and not self._validate_proxy_connectivity(normalized_base):
                logger.warning(f"🚫 Proxy base {normalized_base} falhou na validação, tentando próximo...")
                continue
            
            # Se proxy base passou, aplicar Session ID
            self.current_proxy_base = normalized_base or proxy_candidate
            session_ok = True
            if self.proxy_session_enabled:
                session_ok = self._refresh_proxy_session_with_retries(self.current_proxy_base, max_retries=3, timeout=15)
                if not session_ok:
                    logger.warning("⚠️ Nenhum Session ID válido encontrado para este proxy. Mantendo proxy base sem Session ID como fallback.")
            else:
                self.current_proxy = self.current_proxy_base

            if self.current_proxy and not self._test_proxy_ip_and_country(self.current_proxy, timeout=15):
                logger.warning(f"⚠️ Proxy {self.current_proxy} falhou no teste de IP/país: tentando próximo proxy...")
                continue

            proxy_display = self.current_proxy.replace('http://', '').replace('https://', '')
            if '@' in proxy_display:
                proxy_display = proxy_display.split('@', 1)[1]
            logger.info(f"🌐 Proxy selecionado e validado: {proxy_display}")
            if self.current_proxy.startswith('socks5://'):
                logger.info("✅ Proxy SOCKS5 selecionado")
            return self.current_proxy
        
        logger.error("❌ Nenhum proxy passou na validação de conectividade")
        return None

    def _set_current_proxy(self, proxy: Optional[str]) -> None:
        """Define o proxy atual."""
        self.current_proxy = proxy

    def _get_current_proxy(self) -> Optional[str]:
        """Retorna o proxy atual."""
        return self.current_proxy

    def _build_proxy_settings(self, proxy: Optional[str]) -> Optional[Dict[str, str]]:
        """Constrói as configurações de proxy para o Playwright.

        Suporta URLs completas como socks5://user:pass@ip:port e http://user:pass@ip:port.
        O campo 'server' contém a URL completa de host:port, e credenciais são passadas separadamente.
        """
        if not proxy:
            return None

        proxy = proxy.strip().rstrip('/')
        try:
            parsed = urlparse(proxy if '://' in proxy else f'http://{proxy}')
            if not parsed.hostname or not parsed.port:
                logger.warning(f"⚠️ Proxy {proxy} não tem hostname ou porta válida")
                return None
        except Exception as e:
            logger.warning(f"⚠️ Erro ao fazer parse do proxy {proxy}: {e}")
            return None

        if parsed.scheme.lower() == 'socks5' and parsed.username and parsed.password:
            upstream = {
                'scheme': 'socks5',
                'host': parsed.hostname,
                'port': parsed.port,
                'username': parsed.username,
                'password': parsed.password
            }
            return self._start_local_http_proxy(upstream)

        proxy_config: Dict[str, str] = {
            'server': f'{parsed.scheme}://{parsed.hostname}:{parsed.port}'
        }
        if parsed.username and parsed.password:
            proxy_config['username'] = parsed.username
            proxy_config['password'] = parsed.password

        return proxy_config

    def _build_proxy_dict(self, proxy_str: str) -> Optional[Dict[str, str]]:
        """Constrói um dicionário de proxy compatível com requests."""
        if not proxy_str:
            return None

        proxy_str = proxy_str.strip().rstrip('/')
        if proxy_str.lower().startswith(('http://', 'https://', 'socks5://', 'socks4://')):
            proxy_url = proxy_str
        elif '@' in proxy_str and proxy_str.count(':') == 3:
            ip, porta, user, password = proxy_str.split(':', 3)
            proxy_url = f"http://{user}:{password}@{ip}:{porta}"
        elif ':' in proxy_str:
            proxy_url = f"http://{proxy_str}"
        else:
            return None

        return {
            'http': proxy_url,
            'https': proxy_url
        }

    def _parse_proxy_string(self, proxy_str: str) -> Optional[ParseResult]:
        if not proxy_str:
            return None

        normalized = proxy_str.strip().rstrip('/')
        if '://' not in normalized:
            normalized = f'http://{normalized}'

        try:
            return urlparse(normalized)
        except Exception:
            return None

    def _normalize_proxy_base(self, proxy_str: str) -> Optional[str]:
        parsed = self._parse_proxy_string(proxy_str)
        if not parsed or not parsed.hostname or not parsed.port:
            return None

        username = parsed.username or ''
        password = parsed.password or ''
        scheme = parsed.scheme or 'http'

        # Remover session suffix antiga ao normalizar proxy base
        username = re.sub(r'(-session-[A-Za-z0-9]+)$', '', username)

        if username and password:
            return f"{scheme}://{username}:{password}@{parsed.hostname}:{parsed.port}"
        elif username:
            return f"{scheme}://{username}@{parsed.hostname}:{parsed.port}"
        return f"{scheme}://{parsed.hostname}:{parsed.port}"

    def _generate_proxy_session_id(self) -> str:
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))

    def _proxy_supports_session(self, proxy_str: str) -> bool:
        parsed = self._parse_proxy_string(proxy_str)
        return bool(parsed and parsed.username and parsed.password)

    def _apply_proxy_session(self, proxy_str: str, session_id: Optional[str] = None) -> str:
        parsed = self._parse_proxy_string(proxy_str)
        if not parsed or not parsed.hostname or not parsed.port:
            return proxy_str

        username = parsed.username or ''
        password = parsed.password or ''
        scheme = parsed.scheme or 'http'

        if not username or not password:
            return proxy_str

        base_username = re.sub(r'(-session-[A-Za-z0-9]+)$', '', username)
        session_id = session_id or self._generate_proxy_session_id()
        proxy_username = f"{base_username}-session-{session_id}"

        return f"{scheme}://{proxy_username}:{password}@{parsed.hostname}:{parsed.port}"

    def _refresh_proxy_session(self, proxy_base: Optional[str] = None) -> Optional[str]:
        if proxy_base:
            normalized_base = self._normalize_proxy_base(proxy_base)
            if normalized_base:
                self.current_proxy_base = normalized_base
        if not self.current_proxy_base:
            return None

        if not self._proxy_supports_session(self.current_proxy_base):
            logger.warning("⚠️ Proxy atual não suporta Session ID. Mantendo proxy sem sessão personalizada.")
            self.proxy_session_id = None
            self.current_proxy = self.current_proxy_base
            return self.current_proxy

        self.proxy_session_id = self._generate_proxy_session_id()
        self.current_proxy = self._apply_proxy_session(self.current_proxy_base, self.proxy_session_id)
        session_suffix = self.proxy_session_id[-6:] if self.proxy_session_id else 'unknown'
        masked = self.current_proxy
        try:
            if '@' in self.current_proxy:
                parts = self.current_proxy.split('@')
                masked = f"***@{parts[-1]}"
        except Exception:
            masked = self.current_proxy
        logger.info(f"🔐 [Session ID: ...{session_suffix}] Proxy renovado: {masked}")
        return self.current_proxy

    def _refresh_proxy_session_with_retries(self, proxy_base: Optional[str] = None, max_retries: int = 3, timeout: int = 15) -> bool:
        if proxy_base:
            normalized_base = self._normalize_proxy_base(proxy_base)
            if normalized_base:
                self.current_proxy_base = normalized_base

        if not self.current_proxy_base:
            logger.error("❌ Nenhum proxy base disponível para renovar Session ID")
            return False

        if not self._proxy_supports_session(self.current_proxy_base):
            logger.warning("⚠️ Proxy atual não suporta Session ID. Mantendo proxy sem sessão personalizada.")
            self.proxy_session_id = None
            self.current_proxy = self.current_proxy_base
            return True

        # 🔥 Webshare bloqueia testes de IP com Session ID (407/400), então gera um Session ID e usa direto
        # Sem fazer testes adicionais que resultariam em falsos negativos
        self._refresh_proxy_session(self.current_proxy_base)
        logger.info(f"✅ Proxy com Session ID definido (sem teste, Webshare não permite): {self.current_proxy}")
        self.last_proxy_test_error = None
        return True

    async def _refresh_proxy_session_and_recreate(self) -> bool:
        if self.current_proxy_base is None and self.proxies:
            self.current_proxy_base = self.proxies[0]

        if not self.current_proxy_base:
            logger.error("❌ Nenhum proxy base disponível para renovar Session ID")
            return False

        session_ok = self._refresh_proxy_session_with_retries(self.current_proxy_base, max_retries=3, timeout=15)
        if not session_ok:
            logger.warning("⚠️ Não foi possível gerar um Session ID válido. Recriando contexto usando proxy base sem Session ID.")

        try:
            await self._create_browser_context()
            if session_ok:
                logger.info("🔄 Contexto recriado com novo Session ID de proxy")
            else:
                logger.info("🔄 Contexto recriado usando proxy base sem Session ID")
            return True
        except Exception as e:
            logger.error(f"❌ Falha ao recriar contexto com novo Session ID: {e}")
            return False

    def _current_proxy_for_blacklist(self) -> Optional[str]:
        if self.proxy_session_enabled and self.current_proxy_base:
            return self.current_proxy_base
        return self.current_proxy

    def _validate_proxy_connectivity(self, proxy_str: str) -> bool:
        """Valida se o proxy responde a uma requisição rápida antes de abrir o navegador."""
        try:
            proxy_dict = self._build_proxy_dict(proxy_str)
            if not proxy_dict:
                return False

            # Teste rápido com httpbin.org/ip (timeout de 15s para proxies residenciais)
            try:
                with requests.Session() as session:
                    session.trust_env = False
                    response = session.get(
                        'http://httpbin.org/ip',
                        proxies=proxy_dict,
                        timeout=15,
                        verify=False,
                        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                    )
                return response.status_code == 200
            except requests.exceptions.Timeout:
                logger.debug(f"⚠️ Timeout na validação de conectividade: {proxy_str}")
                return False
            except requests.exceptions.ProxyError:
                logger.debug(f"⚠️ Erro de proxy na validação: {proxy_str}")
                return False
            except Exception as e:
                logger.debug(f"⚠️ Erro na validação: {str(e)[:80]}")
                return False
                
        except Exception as e:
            logger.warning(f"⚠️ Proxy {proxy_str} falhou na validação: {str(e)[:80]}")
            return False

    def _select_first_paid_proxy(self) -> None:
        """
        🔥 FORCE: Seleciona obrigatoriamente o primeiro proxy da lista de proxies pagos.
        Garante que NENHUMA requisição é feita sem proxy no início.
        """
        if not self.proxies:
            logger.error("❌ Nenhum proxy pago disponível!")
            raise Exception("Nenhum proxy pago na lista")
        
        # Pegar o primeiro proxy da lista
        first_proxy = self.proxies[0].strip()
        self.current_proxy_base = self._normalize_proxy_base(first_proxy) or first_proxy
        
        # ⚠️ Testar o PROXY BASE (sem Session ID) antes de aplicar Session ID
        # Isto garante que a autenticação básica funciona.
        logger.info(f"🔍 Testando proxy base (sem Session ID) antes de aplicar Session ID...")
        logger.debug(f"📌 Proxy base a testar: {self.current_proxy_base}")
        if not self._test_proxy_ip_and_country(self.current_proxy_base):
            logger.warning(f"⚠️ Proxy base falhou no teste. Rotacionando para próximo proxy obrigatório...")
            if len(self.proxies) > 1:
                next_proxy = self._choose_next_proxy(exclude_current=True)
                if not next_proxy:
                    logger.error("❌ Não foi possível encontrar proxy válido após falha no teste de proxy base")
                    raise Exception("Falha no teste de proxy base e nenhum proxy alternativo válido encontrado")
                logger.info(f"✅ Proxy alternativo selecionado: {next_proxy}")
            else:
                logger.error("❌ Falha no teste de proxy base e não há proxies alternativos disponíveis")
                raise Exception("Falha no teste de proxy base e não há proxies alternativos disponíveis")
        else:
            logger.info(f"✅ Proxy base passou no teste de IP/país")

        # Aplicar Session ID se habilitado
        if self.proxy_session_enabled:
            logger.info(f"🔄 Renovando Session ID para proxy base: {self.current_proxy_base}")
            session_ok = self._refresh_proxy_session_with_retries(self.current_proxy_base, max_retries=3, timeout=15)
            if not session_ok:
                self.proxy_session_id = None
                self.current_proxy = self.current_proxy_base
                logger.warning(
                    "⚠️ Proxy base passou no teste, mas todos os Session IDs falharam. Continuando com o proxy base sem Session ID como fallback."
                )
            else:
                logger.info(f"✅ Proxy com Session ID definido: {self.current_proxy}")
        else:
            self.current_proxy = self.current_proxy_base
            logger.info(f"✅ Session ID desabilitado, usando proxy base: {self.current_proxy_base}")

        self.proxy_index = 0
        
        # Log com o proxy definido
        logger.info(f"✅ Proxy inicial OBRIGATÓRIO selecionado: {self.current_proxy_base}")

    def _test_proxy_ip_and_country(self, proxy_str: str, timeout: int = 15) -> bool:
        """Testa se o proxy está funcionando com múltiplos endpoints de teste."""
        try:
            proxy_dict = self._build_proxy_dict(proxy_str)
            if not proxy_dict:
                logger.warning(f"⚠️ Não foi possível construir proxy_dict para: {proxy_str}")
                return False

            # 🔥 MELHORIA: Testar com múltiplos endpoints para máxima resiliência
            # Se um endpoint falhar/timeout, tenta o próximo
            # Cada endpoint retorna um formato JSON diferente:
            # - httpbin.org/ip: {"origin": "1.2.3.4"}
            # - ifconfig.me/json: {"ip": "1.2.3.4"}
            # - api.ipify.org: {"ip": "1.2.3.4"}
            ip_test_endpoints = [
                'http://httpbin.org/ip',              # testar primeiro em HTTP para proxies que falham em HTTPS/TLS
                'https://httpbin.org/ip',             # httpbin é mais robusto
                'https://ifconfig.me/json',           # ifconfig como fallback
                'https://api.ipify.org?format=json'   # ipify como último recurso
            ]
            
            ip = None
            endpoint_name = "desconhecido"
            endpoint_errors: List[str] = []
            for endpoint_url in ip_test_endpoints:
                try:
                    endpoint_name = endpoint_url.split('/')[2]
                    logger.debug(f"🔗 Testando endpoint: {endpoint_url}")
                    with requests.Session() as session:
                        session.trust_env = False
                        response = session.get(
                            endpoint_url,
                            proxies=proxy_dict,
                            timeout=timeout,
                            verify=False,
                            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                        )
                    if response.status_code == 200:
                        ip_data = response.json()
                        logger.debug(f"📊 Resposta JSON de {endpoint_url}: {ip_data}")
                        
                        # Tentar extrair IP de diferentes chaves (origin para httpbin, ip para outros)
                        ip = ip_data.get('origin') or ip_data.get('ip')
                        
                        if ip and ip != 'Desconhecido':
                            logger.info(f"✅ IP obtido via {endpoint_name}: {ip}")
                            break  # Sucesso - parar de tentar outros endpoints
                        else:
                            logger.debug(f"⚠️ {endpoint_url} retornou JSON sem IP válido: {ip_data}")
                            endpoint_errors.append(f"{endpoint_name}: JSON inválido")
                            continue
                    else:
                        logger.debug(f"⚠️ Endpoint {endpoint_url} retornou status {response.status_code}")
                        logger.debug(f"📄 Corpo de resposta de {endpoint_url}: {response.text[:200]}")
                        endpoint_errors.append(f"{endpoint_name}: status {response.status_code}")
                        continue
                except requests.exceptions.Timeout as te:
                    error_msg = f"{endpoint_name}: Timeout ({te})"
                    endpoint_errors.append(error_msg)
                    logger.debug(f"⏱️ {error_msg}")
                    continue
                except requests.exceptions.ProxyError as pe:
                    error_msg = f"{endpoint_name}: ProxyError ({pe})"
                    endpoint_errors.append(error_msg)
                    logger.debug(f"🚫 {error_msg}")
                    continue
                except requests.exceptions.ConnectionError as ce:
                    error_msg = f"{endpoint_name}: ConnectionError ({ce})"
                    endpoint_errors.append(error_msg)
                    logger.debug(f"🔌 {error_msg}")
                    continue
                except Exception as e:
                    error_msg = f"{endpoint_name}: {type(e).__name__} ({e})"
                    endpoint_errors.append(error_msg)
                    logger.debug(f"❌ {error_msg}")
                    continue
            
            if not ip:
                self.last_proxy_test_error = '; '.join(endpoint_errors[-5:]) if endpoint_errors else 'Nenhum detalhe disponível'
                logger.warning(
                    f"⚠️ Nenhum endpoint de IP conseguiu responder com IP válido para proxy: {proxy_str[:50]}... Erros: {self.last_proxy_test_error}"
                )
                return False
            
            logger.info(f"🌍 IP detectado via proxy: {ip}")

            # Teste de país é OPCIONAL - falha silenciosa
            # Se o proxy funciona, aceitamos mesmo que não seja Brasil (por compatibilidade)
            # O importante é que o proxy RESPONDEU a uma requisição com IP válido
            try:
                with requests.Session() as session:
                    session.trust_env = False
                    country_response = session.get(
                        f'http://ip-api.com/json/{ip}',
                        timeout=5,
                        verify=False,
                        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                    )
                if country_response.status_code == 200:
                    country_data = country_response.json()
                    country = country_data.get('country', 'Desconhecido')
                    country_code = country_data.get('countryCode', 'XX')
                    logger.info(f"🗺️  País detectado: {country} ({country_code})")
                    
                    # Verificar se é Brasil
                    if country_code == 'BR':
                        logger.info(f"✅ IP brasileiro confirmado: {ip}")
                        return True
                    else:
                        # ⚠️ Não é Brasil, mas proxy funciona - retornar True mesmo assim
                        logger.warning(f"⚠️ IP não é brasileiro. País detectado: {country} ({country_code}), mas proxy funciona OK")
                        return True
                else:
                    logger.warning(f"⚠️ Country lookup falhou (status {country_response.status_code}), mas IP test passou")
                    return True  # Proxy funciona mesmo que país falhe
            except Exception as e:
                logger.debug(f"⚠️ Erro ao verificar país (continuando): {str(e)[:100]}")
                return True  # Proxy funciona mesmo que país falhe
        
        except Exception as e:
            logger.warning(f"⚠️ Proxy {proxy_str} falhou no teste geral: {str(e)[:100]}")
            return False

    def _start_local_http_proxy(self, upstream_proxy: Dict[str, str]) -> Optional[Dict[str, str]]:
        """Inicia um proxy HTTP local que encaminha tráfego via SOCKS5 autenticado."""
        self._stop_local_http_proxy()

        server = ThreadedHTTPServer(('127.0.0.1', 0), Socks5HttpProxyHandler)
        server.upstream_proxy = upstream_proxy
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        self.local_proxy_server = server
        self.local_proxy_thread = thread
        logger.info(f"🔁 Proxy local iniciado em http://127.0.0.1:{server.server_port} para SOCKS5 autenticado")

        return {'server': f'http://127.0.0.1:{server.server_port}'}

    def _stop_local_http_proxy(self) -> None:
        """Para o proxy HTTP local, se estiver ativo."""
        if self.local_proxy_server:
            try:
                self.local_proxy_server.shutdown()
                self.local_proxy_server.server_close()
            except Exception as e:
                logger.warning(f"⚠️ Falha ao desligar proxy local: {e}")
            finally:
                self.local_proxy_server = None

        if self.local_proxy_thread:
            self.local_proxy_thread.join(timeout=2)
            self.local_proxy_thread = None

    # DESABILITADO: Função para Bright Data (agora usando Webshare Rotating Endpoint)
    # def _apply_brightdata_session(self, proxy_str: str) -> str:
    #     """Aplica um sufixo de sessão aleatório em Bright Data para trocar IP sem trocar proxy."""
    #     if not proxy_str:
    #         return proxy_str
    #
    #     if not proxy_str.lower().startswith(('http://', 'https://', 'socks5://', 'socks4://')):
    #         proxy_str = f'http://{proxy_str}'
    #
    #     try:
    #         parsed = urlparse(proxy_str)
    #         if not parsed.hostname or parsed.hostname.lower() != 'brd.superproxy.io':
    #             return proxy_str
    #
    #         username = parsed.username or ''
    #         password = parsed.password or ''
    #         if username and '-session-' not in username:
    #             suffix = f'-session-{random.randint(100000, 999999)}'
    #             username = f'{username}{suffix}'
    #
    #         scheme = parsed.scheme or 'http'
    #         return f"{scheme}://{username}:{password}@{parsed.hostname}:{parsed.port}"
    #     except Exception as e:
    #         logger.warning(f"⚠️ Erro ao aplicar sessão Bright Data no proxy {proxy_str}: {e}")
    #         return proxy_str

    async def _block_unnecessary_assets(self, route, request) -> None:
        """Bloqueia imagens e mídia para reduzir uso de banda e acelerar o cadastro."""
        if request.resource_type in ['image', 'media', 'font', 'video']:
            await route.abort()
        else:
            await route.continue_()

    async def _create_browser_context(self) -> None:
        """Cria ou recria o navegador/contexto Playwright com o proxy atual."""
        if self.context:
            await self.context.close()
            self.context = None
        if self.browser:
            await self.browser.close()
            self.browser = None

        self._stop_local_http_proxy()
        proxy_config = self._build_proxy_settings(self.current_proxy)
        browser_args = [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-accelerated-2d-canvas',
            '--no-first-run',
            '--no-zygote',
            '--disable-gpu',
            '--disable-web-security',
            '--disable-features=VizDisplayCompositor',
            '--disable-background-networking',
            '--disable-client-side-phishing-detection',
            '--disable-component-update'
        ]

        try:
            if self.use_ads_power:
                try:
                    if not self.ads_manager:
                        self.ads_manager = AdsPowerManager(
                            api_url=self.ads_power_api_url,
                            api_key=self.ads_power_api_key
                        )

                    logger.info(f"🔌 Iniciando AdsPower browser via API local: {self.ads_power_api_url}")
                    ws_endpoint = await asyncio.to_thread(
                        self.ads_manager.start_browser,
                        self.ads_power_profile_id,
                        self.ads_power_profile_name
                    )
                    logger.info(f"✅ AdsPower retornou endpoint CDP: {ws_endpoint}")

                    self.browser = await self.playwright.chromium.connect_over_cdp(ws_endpoint)
                    self.context = self.browser.contexts[0] if self.browser.contexts else await self.browser.new_context()
                    self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
                    await self.context.route('**/*', self._block_unnecessary_assets)
                    logger.info("✅ Conectado ao AdsPower via CDP")
                    return

                except Exception as ads_error:
                    logger.warning(f"⚠️ AdsPower falhou ({ads_error}), fazendo fallback para Playwright normal")
                    self.use_ads_power = False  # Desabilita temporariamente para esta sessão

            # Fallback para Playwright normal
            self.browser = await self.playwright.chromium.launch(
                headless=self.config['browser_automation'].get('headless', True),
                args=browser_args
            )

            viewport = random.choice(self.screen_resolutions)
            self.context = await self.browser.new_context(
                viewport=viewport,
                device_scale_factor=1,
                has_touch=False,
                locale='pt-BR',
                timezone_id='America/Sao_Paulo',
                ignore_https_errors=True
            )
            self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
            await self.context.route('**/*', self._block_unnecessary_assets)

        except Exception as e:
            logger.error(f"❌ Falha ao criar contexto Playwright com proxy {self.current_proxy}: {e}")
            await self.cleanup()
            raise

    async def _clear_browser_context_identity(self) -> None:
        """Limpa cookies e permissões do contexto antes de iniciar um novo username."""
        try:
            if self.context:
                await self.context.clear_cookies()
                await self.context.clear_permissions()
                logger.info("✅ Cookies e permissões do contexto limpos para nova tentativa")
        except Exception as e:
            logger.warning(f"⚠️ Falha ao limpar identidade do contexto: {e}")

    def _is_allowed_sitekey(self, sitekey: Optional[str]) -> bool:
        """Valida se o sitekey pertence ao widget XAT Turnstile esperado."""
        if not sitekey:
            return False
        return sitekey in self.VALID_XAT_SITEKEYS

    async def _rotate_proxy_and_recreate(self) -> bool:
        """Seleciona um novo proxy ou renova Session ID e recria o contexto do navegador."""
        if self.proxy_session_enabled and self.current_proxy_base:
            logger.info("🔄 Renovando Session ID do proxy atual em vez de trocar endpoint")
            if not await self._refresh_proxy_session_and_recreate():
                return False
            return True

        if not self.proxies:
            logger.error("❌ Nenhum proxy disponível para rotacionar")
            return False

        self._choose_next_proxy()
        try:
            await self._create_browser_context()
            logger.info("🔄 Proxy rotacionado e contexto recriado")
            return True
        except Exception as e:
            logger.error(f"❌ Falha ao recriar contexto com novo proxy: {e}")
            return False

    def _blacklist_current_proxy(self, reason: str) -> None:
        """Adiciona o proxy atual à blacklist e registra no log."""
        proxy_to_blacklist = self._current_proxy_for_blacklist()
        if not proxy_to_blacklist:
            return

        if proxy_to_blacklist in self.bad_proxies:
            return

        self.bad_proxies.add(proxy_to_blacklist)
        if proxy_to_blacklist in self.proxies:
            self.proxies.remove(proxy_to_blacklist)

        try:
            BAD_PROXIES_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(BAD_PROXIES_FILE, 'a', encoding='utf-8') as f:
                f.write(f"{proxy_to_blacklist}  # {reason}  [{datetime.now().isoformat()}]\n")
            logger.warning(f"🚫 Proxy blacklistado: {proxy_to_blacklist} ({reason})")
        except Exception as e:
            logger.warning(f"⚠️ Não foi possível gravar bad_proxies.log: {e}")

    def _log_shadowban(self, username: str, email: str, reason: str) -> None:
        """Registra suspeita de shadowban em arquivo dedicado."""
        try:
            SHADOWBAN_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(SHADOWBAN_LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(f"{datetime.now().isoformat()} | {username} | {email} | {reason}\n")
            logger.warning(f"⚠️ Possível shadowban detectado para {username}: {reason}")
        except Exception as e:
            logger.warning(f"⚠️ Não foi possível gravar shadowban.log: {e}")

    def _detectar_e_processar_shadowban(self, username: str, email: str, texto_resposta: str) -> None:
        """
        FEATURE 1: Rotação Obrigatória de Proxy (Shadow Ban)
        Detecta indicadores de shadowban na resposta e força rotação de proxy (IP) para próxima tentativa.
        Nunca usa o mesmo IP após uma falha de registro.
        """
        # Indicadores de shadowban/ID shadow ban
        shadowban_keywords = [
            'shadow ban', 'shadowban', 'id already', 'id in use',
            'banned', 'bloqueado', 'banido', 'banned temporarily',
            'account banned', 'id banned', 'user banned',
            'temporarily banned', 'suspension', 'suspenso',
            'access revoked', 'access denied', 'acesso negado',
            'user not allowed', 'user cannot', 'não permitido'
        ]
        
        texto_lower = texto_resposta.lower()
        detected_reasons = [kw for kw in shadowban_keywords if kw in texto_lower]
        session_id_display = self.proxy_session_id[-6:] if self.proxy_session_id else 'N/A'
        
        if detected_reasons:
            logger.warning(f"🚫 [Session ID: ...{session_id_display}] SHADOW BAN DETECTADO para {username}: {', '.join(detected_reasons)}")
            self._log_shadowban(username, email, f"Indicadores: {', '.join(detected_reasons)}")
            if self.proxy_session_enabled and self.current_proxy_base:
                logger.info(f"🔄 [Session ID: ...{session_id_display}] Shadow Ban detectado. Renovando Session ID do proxy atual e reiniciando fluxo sem trocar endpoint.")
                self.proxy_session_restart_pending = True
            else:
                # ⚠️ Blacklist o IP/proxy atual obrigatoriamente
                if self.current_proxy:
                    self._blacklist_current_proxy(f"Shadow Ban detectado para {username} - indicadores: {', '.join(detected_reasons)}")
                    logger.info(f"🔄 [Session ID: ...{session_id_display}] Rotação de proxy OBRIGATÓRIA: IP será trocado antes do próximo username")
                else:
                    logger.warning(f"⚠️ [Session ID: ...{session_id_display}] Nenhum proxy atual para blacklistar (possível erro de estado)")
                # Resetar proxy para forçar rotação na próxima conta
                self._set_current_proxy(None)
        else:
            # Outros motivos de falha - registrar para análise
            logger.debug(f"❌ Falha ao criar conta {username}, mas não foi detectado shadowban específico")

    async def create_account(self, username: str, password: str, email: str) -> bool:
        """
        Cria conta XAT usando automação de navegador.

        Segurança Sticky IP (IP Fixo por Sessão):
        - O proxy é definido UMA VEZ no início (self.current_proxy)
        - Mantém a mesma conexão TCP durante TODO o processo de registro
        - Só renova o Session ID se houver bloqueio Cloudflare, shadowban ou IP change
        - Garante que o token do Turnstile não fica inválido por troca de IP durante o registro
        """
        max_account_attempts = self.config['browser_automation'].get('max_proxy_retries', 3)

        for account_attempt in range(max_account_attempts):
            if account_attempt > 0 or self.proxy_session_restart_pending:
                session_id_display = self.proxy_session_id[-6:] if self.proxy_session_id else 'unknown'
                logger.info(f"🔄 [Session ID: ...{session_id_display}] Reiniciando fluxo da conta do zero com novo Session ID de proxy")
                self.proxy_session_restart_pending = False
                if self.proxy_session_enabled:
                    if not await self._refresh_proxy_session_and_recreate():
                        return False
                else:
                    if not await self._rotate_proxy_and_recreate():
                        return False

            try:
                proxy_inicial = self.current_proxy
                session_id_display = self.proxy_session_id[-6:] if self.proxy_session_id else 'N/A'
                logger.info(f"🎭 [Session ID: ...{session_id_display}] Iniciando criação de conta: {username} | {email}")
                logger.info(f"🔒 [Session ID: ...{session_id_display}] Sticky IP ativado - Mantendo mesma sessão TCP durante todo o registro")

                await self._clear_browser_context_identity()
                page = await self.context.new_page()
                page.set_default_timeout(self.config['browser_automation'].get('page_timeout', 90000))

                # Passo 1: Obter UserID/k2 com retry de proxy em caso de bloqueio
                user_data = None
                for attempt in range(max_account_attempts):
                    user_data = await self._get_user_data(page)
                    if user_data:
                        break

                    session_id_display = self.proxy_session_id[-6:] if self.proxy_session_id else 'N/A'
                    logger.warning(f"⚠️ [Session ID: ...{session_id_display}] Falha ao obter UserID/k2 no attempt {attempt + 1}/{max_account_attempts}")
                    await page.close()
                    if attempt == max_account_attempts - 1:
                        return False
                    if not await self._rotate_proxy_and_recreate():
                        return False
                    proxy_inicial = self.current_proxy
                    page = await self.context.new_page()
                    page.set_default_timeout(self.config['browser_automation'].get('page_timeout', 90000))

                user_id = user_data.get('UserId')
                k2_token = user_data.get('k2')

                await self._random_delay()

                # Passo 2: Acessar página de login com retry de proxy ao detectar bloqueio ou shadowban
                login_success = False
                for attempt in range(max_account_attempts):
                    try:
                        if attempt > 0:
                            await self._clear_browser_context_identity()
                            logger.info("🔄 Obtendo novo UserID/k2 para nova tentativa de login")
                            new_user_data = await self._get_user_data(page)
                            if new_user_data and new_user_data.get('UserId'):
                                user_id = new_user_data.get('UserId')
                                if new_user_data.get('k2'):
                                    k2_token = new_user_data.get('k2')
                                logger.info(f"✅ Novo UserID obtido para retry: {user_id}")
                            else:
                                logger.warning("⚠️ Falha ao obter novo UserID/k2 no retry; usando UserID anterior")

                        login_success = await self._access_login_page(page, user_id, k2_token)
                        if login_success:
                            proxy_inicial = self.current_proxy
                            break

                    except CloudflareHardBlockException as e:
                        logger.warning(f"🚫 Cloudflare Hard Block detectado: {e}")
                        login_success = False
                        await page.close()
                        if attempt == max_account_attempts - 1:
                            return False
                        if not await self._rotate_proxy_and_recreate():
                            return False
                        page = await self.context.new_page()
                        page.set_default_timeout(self.config['browser_automation'].get('page_timeout', 90000))
                        continue

                    if login_success:
                        break

                    session_id_display = self.proxy_session_id[-6:] if self.proxy_session_id else 'N/A'
                    logger.warning(f"⚠️ [Session ID: ...{session_id_display}] Bloqueio na página de login detectado no attempt {attempt + 1}/{max_account_attempts}")
                    await page.close()
                    if attempt == max_account_attempts - 1:
                        return False
                    if not await self._rotate_proxy_and_recreate():
                        return False
                    page = await self.context.new_page()
                    page.set_default_timeout(self.config['browser_automation'].get('page_timeout', 90000))

                if not login_success:
                    await page.close()
                    return False

                # Aguardar carregamento do widget e resolver captcha
                captcha_resolved = False
                for attempt in range(max_account_attempts):
                    try:
                        captcha_resolved = await self._wait_for_captcha_resolution(page)
                        if captcha_resolved:
                            break
                    except CloudflareHardBlockException as e:
                        session_id_display = self.proxy_session_id[-6:] if self.proxy_session_id else 'N/A'
                        logger.warning(f"🚫 [Session ID: ...{session_id_display}] Cloudflare Hard Block detectado durante resolução de captcha: {e}")
                        captcha_resolved = False

                    if captcha_resolved:
                        break

                    session_id_display = self.proxy_session_id[-6:] if self.proxy_session_id else 'N/A'
                    logger.warning(f"⚠️ [Session ID: ...{session_id_display}] Widget de Turnstile não carregou ou captcha não foi resolvido no attempt {attempt + 1}/{max_account_attempts}")
                    await page.close()
                    if attempt == max_account_attempts - 1:
                        return False
                    if not await self._rotate_proxy_and_recreate():
                        return False
                    proxy_inicial = self.current_proxy
                    page = await self.context.new_page()
                    page.set_default_timeout(self.config['browser_automation'].get('page_timeout', 90000))
                    if attempt > 0:
                        await self._clear_browser_context_identity()
                        logger.info("🔄 Obtendo novo UserID/k2 para nova tentativa após erro de captcha")
                        new_user_data = await self._get_user_data(page)
                        if new_user_data and new_user_data.get('UserId'):
                            user_id = new_user_data.get('UserId')
                            if new_user_data.get('k2'):
                                k2_token = new_user_data.get('k2')
                            logger.info(f"✅ Novo UserID obtido após captcha fail: {user_id}")
                        else:
                            logger.warning("⚠️ Falha ao obter novo UserID/k2 após captcha fail; usando UserID anterior")
                    try:
                        login_success = await self._access_login_page(page, user_id, k2_token)
                        if login_success:
                            proxy_inicial = self.current_proxy
                        if not login_success:
                            continue
                    except CloudflareHardBlockException as e:
                        logger.warning(f"🚫 Cloudflare Hard Block detectado ao re-acessar login: {e}")
                        continue

                if not captcha_resolved:
                    session_id_display = self.proxy_session_id[-6:] if self.proxy_session_id else 'N/A'
                    reason = self.last_captcha_block_reason or "Falha na resolução do captcha"
                    logger.warning(f"⚠️ [Session ID: ...{session_id_display}] TURNSTILE TIMEOUT - Captcha não resolvido. Abortando criação de conta. Motivo: {reason}")
                    await page.close()
                    return False

                # Passo 3: Preencher e submeter formulário com loop de re-tentativa para captcha
                registration_success = False
                captcha_retry_attempts = 0
                max_captcha_retries = 3

                while captcha_retry_attempts < max_captcha_retries and not registration_success:
                    try:
                        session_id_display = self.proxy_session_id[-6:] if self.proxy_session_id else 'N/A'
                        logger.info(f"📝 [Session ID: ...{session_id_display}] Tentativa de registro {captcha_retry_attempts + 1}/{max_captcha_retries}")
                        success = await self._fill_registration_form(page, username, password, email, proxy_inicial)
                        if success:
                            registration_success = True
                            break
                        else:
                            logger.warning(f"⚠️ Tentativa {captcha_retry_attempts + 1} falhou")
                            captcha_retry_attempts += 1

                    except Exception as e:
                        error_msg = str(e).lower()
                        if 'sticky ip' in error_msg or 'proxy foi rotacionado' in error_msg:
                            session_id_display = self.proxy_session_id[-6:] if self.proxy_session_id else 'N/A'
                            logger.warning(f"🚨 [Session ID: ...{session_id_display}] Sticky IP detectado na tentativa {captcha_retry_attempts + 1}: {e}")
                            if self.proxy_session_enabled:
                                self.proxy_session_restart_pending = True
                                await page.close()
                                break
                            await page.close()
                            return False
                        if 'captcha error detected' in error_msg or 'captcha' in error_msg:
                            session_id_display = self.proxy_session_id[-6:] if self.proxy_session_id else 'N/A'
                            logger.warning(f"🚨 [Session ID: ...{session_id_display}] Erro de captcha detectado na tentativa {captcha_retry_attempts + 1}: {e}")
                            if captcha_retry_attempts < max_captcha_retries - 1:
                                session_id_display = self.proxy_session_id[-6:] if self.proxy_session_id else 'N/A'
                                logger.info(f"🔄 [Session ID: ...{session_id_display}] Aguardando 3s antes de re-tentar captcha...")
                                await page.wait_for_timeout(3000)
                                captcha_retry_attempts += 1
                                continue
                            else:
                                session_id_display = self.proxy_session_id[-6:] if self.proxy_session_id else 'N/A'
                                logger.error(f"❌ [Session ID: ...{session_id_display}] Máximo de {max_captcha_retries} tentativas de registro atingido devido a erro de captcha")
                                await page.close()
                                return False
                        else:
                            logger.error(f"❌ Erro não relacionado a captcha: {e}")
                            await page.close()
                            return False

                if self.proxy_session_restart_pending:
                    logger.info("🔄 Shadowban ou Sticky IP detectado. Reiniciando o fluxo da conta do zero.")
                    await page.close()
                    continue

                if not registration_success:
                    logger.error("❌ Todas as tentativas de registro falharam")
                    await page.close()
                    return False

                # Passo 4: Verificar resultado
                result = await self._verify_registration_result(page, username, email)
                await page.close()

                if result:
                    return True
                if self.proxy_session_restart_pending:
                    session_id_display = self.proxy_session_id[-6:] if self.proxy_session_id else 'N/A'
                    logger.info(f"🔄 [Session ID: ...{session_id_display}] Shadowban detectado após verificação. Reiniciando fluxo da conta do zero.")
                    continue

                return False

            except Exception as e:
                logger.error(f"❌ Erro na automação: {e}")
                return False

        logger.error("❌ Todas as tentativas completas de criação de conta falharam")
        return False

    async def _get_user_data(self, page: Page) -> Optional[Dict]:
        """Obtém UserID e k2 via auser3.php"""
        try:
            logger.info("🔗 Obtendo UserID/k2 via navegador")

            # Acessar auser3.php (timeout aumentado para proxies residenciais)
            response = await page.goto(self.AUSER_URL, wait_until='networkidle', timeout=45000)
            final_url = page.url if page else self.AUSER_URL
            response_status = response.status if response else 'sem resposta'
            logger.info(f"📡 Navegado para auser3.php: {final_url} status={response_status}")

            if response and response.status in [403, 503]:
                logger.warning(f"⚠️ Bloqueio detectado ao acessar auser3.php: {response.status}")
                logger.info("🔁 Tentando fallback direto de auser3.php via requisição HTTP após bloqueio do navegador")
                try:
                    direct_user_data = await asyncio.to_thread(self.obter_user_data)
                    if direct_user_data:
                        logger.info("✅ Fallback direto obteve UserID/k2 com sucesso")
                        return direct_user_data
                    logger.warning("⚠️ Fallback direto não obteve UserID/k2 após bloqueio do navegador")
                except Exception as fallback_error:
                    logger.warning(f"⚠️ Erro no fallback direto após bloqueio do navegador: {fallback_error}")
                self._blacklist_current_proxy(f"Bloqueio 403/503 em auser3.php")
                return None

            # Extrair conteúdo HTML
            content = await page.content()
            if not content or not content.strip():
                logger.warning("⚠️ Conteúdo de auser3.php via navegador vazio ou ausente")
            soup = BeautifulSoup(content, 'html.parser')

            # Procurar por inputs hidden com name="UserId" ou similar
            user_id = None
            k2 = None

            # Método 1: Procurar em inputs hidden
            for input_tag in soup.find_all('input', {'type': 'hidden'}):
                name = input_tag.get('name', '').lower()
                value = input_tag.get('value', '')
                
                if 'userid' in name and value:
                    user_id = value
                    logger.info(f"✅ UserID encontrado em input hidden: {value}")
                elif name == 'k2' and value:
                    k2 = value
                    logger.info(f"✅ k2 encontrado em input hidden: {value[:30]}...")

            # Método 2: Procurar em scripts/divs com atributos data-
            if not user_id or not k2:
                for tag in soup.find_all(['script', 'div']):
                    content_text = tag.get_text() if hasattr(tag, 'get_text') else str(tag)
                    
                    if 'UserId' in content_text and not user_id:
                        match = re.search(r'UserId["\s:]+(\d+)', content_text)
                        if match:
                            user_id = match.group(1)
                            logger.info(f"✅ UserID extraído do conteúdo: {user_id}")
                    
                    if 'k2' in content_text and not k2:
                        match = re.search(r'k2["\s:=]+([a-zA-Z0-9_-]+)', content_text)
                        if match:
                            k2 = match.group(1)
                            logger.info(f"✅ k2 extraído do conteúdo: {k2[:30]}...")

            # Método 3: Procurar no texto da página com HTML entities
            if not user_id or not k2:
                try:
                    body_text = await page.text_content('body')
                except Exception:
                    body_text = None

                if body_text:
                    decoded_text = html.unescape(body_text)

                    if not user_id:
                        match = re.search(r'(?:&amp;|&)UserId=(\d+)', decoded_text)
                        if match:
                            user_id = match.group(1)
                            logger.info(f"✅ UserID extraído do texto da página: {user_id}")

                    if not k2:
                        match = re.search(r'(?:&amp;|&)k2=([a-zA-Z0-9_-]+)', decoded_text)
                        if match:
                            k2 = match.group(1)
                            logger.info(f"✅ k2 extraído do texto da página: {k2[:30]}...")

            # Método 4: Via JavaScript (última opção)
            if not user_id or not k2:
                try:
                    js_user_id = await page.evaluate("""
                        () => {
                            let val = document.querySelector('input[name="UserId"]')?.value || 
                                     document.querySelector('[data-userid]')?.getAttribute('data-userid') ||
                                     window.UserId || null;
                            return val;
                        }
                    """)
                    if js_user_id:
                        user_id = str(js_user_id)
                        logger.info(f"✅ UserID extraído via JavaScript: {user_id}")
                except:
                    pass
                
                try:
                    js_k2 = await page.evaluate("""
                        () => {
                            let val = document.querySelector('input[name="k2"]')?.value || 
                                     document.querySelector('[data-k2]')?.getAttribute('data-k2') ||
                                     window.k2 || null;
                            return val;
                        }
                    """)
                    if js_k2:
                        k2 = str(js_k2)
                        logger.info(f"✅ k2 extraído via JavaScript: {k2[:30]}...")
                except:
                    pass

            if not k2:
                try:
                    js_k2 = await page.evaluate("""
                        () => {
                            const all = Array.from(document.querySelectorAll('*'));
                            const found = all.find(el => {
                                const name = (el.getAttribute('name') || '').toLowerCase();
                                const id = (el.getAttribute('id') || '').toLowerCase();
                                const attrs = Array.from(el.attributes).map(a => a.name.toLowerCase());
                                return name.includes('k2') || id.includes('k2') || attrs.some(attr => attr.includes('k2'));
                            });
                            if (found) {
                                return found.value || found.getAttribute('data-k2') || found.getAttribute('value');
                            }
                            return window.k2 || window.__k2 || null;
                        }
                    """)
                    if js_k2:
                        k2 = str(js_k2)
                        logger.info(f"✅ k2 extraído via fallback genérico: {k2[:30]}...")
                except Exception:
                    pass

            if user_id and k2:
                logger.info(f"✅ UserData obtido com sucesso: UserId={user_id}")
                return {'UserId': user_id, 'k2': k2}

            logger.warning("⚠️ Não foi possível extrair UserID/k2 da resposta")
            logger.info(f"📄 Conteúdo da página (primeiros 500 chars): {content[:500]}")

            # Fallback para extração direta via HTTP se a extração do Playwright falhar
            logger.info("🔁 Tentando fallback direto de auser3.php via requisição HTTP")
            try:
                direct_user_data = await asyncio.to_thread(self.obter_user_data)
                if direct_user_data:
                    logger.info("✅ Fallback direto obteve UserID/k2 com sucesso")
                    return direct_user_data
                logger.warning("⚠️ Fallback direto não obteve UserID/k2")
            except Exception as fallback_error:
                logger.warning(f"⚠️ Erro no fallback direto de auser3.php: {fallback_error}")

            return None

        except Exception as e:
            logger.error(f"❌ Erro ao obter user data: {e}")
            return None

    async def _access_login_page(self, page: Page, user_id: str, k2_token: str) -> bool:
        """Acessa página de login com parâmetros"""
        try:
            logger.info(f"🔗 Acessando página de login com UserId: {user_id}")

            login_url = f"{self.LOGIN_URL}?mode=1&UserId={user_id}&k2={k2_token}"
            await self._patch_turnstile_callbacks(page)

            logger.info("🧍 Acessando /login diretamente para reduzir exposição a Cloudflare")
            login_timeout = self.config['browser_automation'].get('login_timeout', 90000)
            try:
                response = await page.goto(login_url, wait_until='domcontentloaded', timeout=login_timeout)
            except Exception as e:
                msg = str(e).lower()
                if 'timeout' in msg or 'timed out' in msg:
                    logger.warning(f"⚠️ Timeout ao acessar login: {e}")
                    self.proxy_session_restart_pending = True
                    return False
                logger.warning(f"⚠️ Falha ao acessar login diretamente: {e}")
                return False

            # Pequena espera para DOM inicial e scripts básicos
            await page.wait_for_timeout(2000)

            blocked_status = False
            if response and response.status in [403, 503]:
                blocked_status = True
                reason = f"Status de bloqueio na página de login: {response.status}"
                logger.warning(f"⚠️ {reason} (aguardando validação adicional antes de descartar)")
                self.last_login_block_reason = reason
                # Não blacklistar automaticamente; pode haver sitekey Turnstile válida na página.

            title = await page.title()
            
            # Detecção de página intersticial Cloudflare: "Just a moment..."
            if not title or 'just a moment' in title.lower() or 'checking your browser' in title.lower() or 'cloudflare' in title.lower():
                logger.warning(f"⚠️ Página intersticial Cloudflare detectada (título: '{title}'). Aguardando até 15s...")
                try:
                    await page.wait_for_load_state('networkidle', timeout=15000)
                    await page.wait_for_timeout(3000)  # Extra 3s para garantir que carregou
                    title = await page.title()
                    logger.info(f"✅ Página carregou após intersticial: {title}")
                    
                    # Failsafe: se título continua vazio após intersticial, é bloqueio hard
                    if not title or title.strip() == '':
                        logger.warning("🚫 Cloudflare Hard Block detectado - título permanece vazio após 15s")
                        self._blacklist_current_proxy("Página login com título vazio após Cloudflare bypass")
                        return False
                except Exception as e:
                    logger.warning(f"⚠️ Timeout aguardando página após Cloudflare: {e}")
                    self._blacklist_current_proxy(f"Página intersticial Cloudflare não carregou ou título vazio: {e}")
                    return False
            
            if 'login' in title.lower() or 'xat' in title.lower():
                logger.info("✅ Página de login carregada com sucesso")
                # Movimento de mouse aleatório para simular comportamento humano
                await self._simulate_mouse_movement(page)
            else:
                # Se título vazio/suspeito mesmo após aguardar Cloudflare, é bloqueio persistente
                if not title or title.strip() == '':
                    logger.warning(f"⚠️ Página carregou com título vazio - provável bloqueio Cloudflare persistente")
                    self._blacklist_current_proxy("Página login com título vazio após Cloudflare bypass")
                    return False
                else:
                    logger.info(f"ℹ️ Página suspeita carregada: {title}. Tentando continuar...")
            # Dar um breve tempo para o DOM ser atualizado pelo JavaScript
            await page.wait_for_timeout(1000)
            await self._simulate_human_interaction(page)

            # Extrair k2 do formulário renderizado, se disponível
            k2_page = None
            try:
                k2_page = await page.get_attribute('input[name="k2"]', 'value')
            except Exception:
                pass

            if not k2_page:
                try:
                    content = await page.content()
                    soup = BeautifulSoup(content, 'html.parser')
                    hidden_k2 = soup.find('input', {'name': 'k2'})
                    if hidden_k2 and hidden_k2.get('value'):
                        k2_page = hidden_k2['value']
                    else:
                        match = re.search(r'(?:&amp;|&)k2=([A-Za-z0-9_-]+)', content)
                        if match:
                            k2_page = match.group(1)
                except Exception:
                    pass

            if k2_page:
                logger.info(f"✅ Token k2 obtido da página de login: {k2_page[:30]}...")
            else:
                logger.warning("⚠️ Token k2 não encontrado por atributo; continuando sem ele")

            # Extrair sitekey do widget presente na página
            sitekey = await self._extract_sitekey_from_page(page)
            if sitekey:
                if not self._is_allowed_sitekey(sitekey):
                    logger.warning(f"⚠️ Sitekey de Cloudflare challenge detectada e ignorada: {sitekey}")
                    return False
                logger.info(f"✅ Sitekey extraída do login via navegador: {sitekey}")
            elif blocked_status:
                title_lower = title.lower() if title else ''
                if not title_lower.strip() or 'access denied' in title_lower or 'forbidden' in title_lower:
                    logger.warning("🚫 Proxy realmente bloqueado: 403/503 sem sitekey e título de acesso negado")
                    self._blacklist_current_proxy("Proxy bloqueado por 403/503 sem sitekey")
                    return False

            return True

        except Exception as e:
            logger.error(f"❌ Erro ao acessar página de login: {e}")
            return False

    async def _extract_turnstile_payload(self, page: Page) -> Dict[str, Optional[str]]:
        """Extrai payload adicional de Turnstile para enviar ao solver de captcha."""
        try:
            result = await page.evaluate(
                """
                () => {
                    const widget = document.querySelector('[data-sitekey], .cf-turnstile, .cf-turnstile-widget');
                    const action = widget?.getAttribute('data-action') || widget?.dataset?.action || null;
                    const extraData = widget?.getAttribute('data') || widget?.dataset?.data || null;
                    const config = window.__cf_turnstile_config || window.turnstileConfig || {};
                    return {
                        action: action || config.action || null,
                        data: extraData || config.data || null
                    };
                }
                """
            )
            if isinstance(result, dict):
                return {
                    'action': result.get('action'),
                    'data': result.get('data')
                }
        except Exception:
            pass
        return {'action': None, 'data': None}

    async def _wait_for_captcha_resolution(self, page: Page) -> bool:
        """Resolve o captcha usando solver e injeta o token no formulário."""
        try:
            if not self.config['captcha_solver'].get('enabled', False):
                logger.warning("⚠️ Solver de captcha não está habilitado na configuração")
                return False

            logger.info("🔒 Aguardando carregamento do widget de captcha...")
            await self._simulate_human_interaction(page)

            captcha_timeout = max(self.config['browser_automation'].get('captcha_timeout', 15), 15)
            wait_timeout = min(captcha_timeout * 1000, 60000)  # Até 60s para widgets de Turnstile

            await page.wait_for_load_state('networkidle', timeout=wait_timeout)

            sitekey = await self._extract_sitekey_from_page(page)
            if sitekey:
                logger.info(f"ℹ️ Sitekey Turnstile detectada antes de checar bloqueio: {sitekey}")
            else:
                widget_selector = 'iframe[src*="turnstile"], iframe[src*="captcha"], [data-sitekey], .cf-turnstile, .g-recaptcha'
                try:
                    logger.info(f"🔍 Aguardando widget Turnstile por até {wait_timeout // 1000}s")
                    await page.wait_for_selector(widget_selector, timeout=wait_timeout)
                    logger.info("✅ Widget Turnstile detectado via seletor")
                except Exception as e:
                    logger.warning(f"⚠️ Widget Turnstile não detectado via seletor: {e}")

                sitekey = await self._extract_sitekey_from_page(page)
                if not sitekey:
                    sitekey = await self._extract_sitekey_from_full_page_content(page)

            if sitekey:
                if not self._is_allowed_sitekey(sitekey):
                    logger.warning(f"⚠️ Sitekey inválida detectada no HTML e ignorada: {sitekey}")
                    sitekey = None
                else:
                    logger.info(f"✅ Sitekey encontrada via regex/HTML antes do widget visível: {sitekey}")
                    # Se encontrou via HTML, não precisa esperar widget - envia imediatamente
            if not sitekey:
                logger.info(f"🔍 Sitekey não encontrada no HTML, aguardando widget visível por até {wait_timeout // 1000}s")
                try:
                    await page.wait_for_function(
                        """
                        () => {
                            return document.querySelector('[data-sitekey]')
                                || document.querySelector('.cf-turnstile')
                                || document.querySelector('.g-recaptcha')
                                || document.querySelector('iframe[src*="turnstile"]')
                                || document.querySelector('iframe[src*="captcha"]')
                                || window.__cf_turnstile_config
                                || window.turnstile;
                        }
                        """,
                        timeout=wait_timeout,
                        polling=1000
                    )
                except Exception as e:
                    reason = f"Turnstile não carregou em {wait_timeout // 1000}s: {e}"
                    logger.warning(f"⚠️ {reason}")
                    self.last_captcha_block_reason = reason
                    self._blacklist_current_proxy(reason)
                    return False
                sitekey = await self._extract_sitekey_from_page(page)
                if sitekey:
                    if sitekey and not self._is_allowed_sitekey(sitekey):
                        logger.warning(f"⚠️ Sitekey inválida detectada no DOM e ignorada: {sitekey}")
                        sitekey = None
                    elif sitekey:
                        logger.info("✅ Sitekey encontrada via DOM após widget visível")
                else:
                    logger.info("🔍 Sitekey não encontrada via DOM; tentando HTML novamente")
                    sitekey = await self._extract_sitekey_from_full_page_content(page)
                    if sitekey:
                        if not self._is_allowed_sitekey(sitekey):
                            logger.warning(f"⚠️ Sitekey inválida detectada no HTML após espera e ignorada: {sitekey}")
                            sitekey = None
                        else:
                            logger.info("✅ Sitekey encontrada no HTML após aguardar widget")

            if not sitekey:
                # Só verifica bloqueio se não encontrou captcha na página
                try:
                    page_content = await page.content()
                    if any(indicator in page_content for indicator in ['403', 'Forbidden', 'Access Denied', '503 Service Unavailable', 'blocked', 'cloudflare']):
                        logger.warning("⚠️ Página bloqueada (403/503) detectada - proxy inválido")
                        self._blacklist_current_proxy("Página de login retornou erro de bloqueio (403/503)")
                        return False
                except Exception:
                    pass

                reason = "Turnstile widget não carregou / sitekey não encontrado"
                logger.warning(f"⚠️ {reason}")
                self.last_captcha_block_reason = reason
                self._blacklist_current_proxy(reason)
                return False

            page_url = page.url
            payload = await self._extract_turnstile_payload(page)

            # Upgrade Final: Clique Humanizado no Widget antes de enviar para 2Captcha
            logger.info("🖱️ Preparando clique humanizado no widget Turnstile...")

            if not await self._humanize_turnstile_click(page):
                logger.warning("⚠️ Clique humanizado falhou, mas continuando mesmo assim...")

            # Aguardar um pouco após o clique para o widget processar
            await self._random_delay(page, 1800, 2500)

            # Obter user-agent do navegador para sincronização com 2Captcha
            user_agent = await page.evaluate("navigator.userAgent")
            token = self._resolver_recaptcha(sitekey, page_url, payload, user_agent=user_agent)
            if not token:
                reason = "Solver de captcha não retornou token"
                logger.warning(f"⚠️ {reason}")
                self.last_captcha_block_reason = reason
                self._blacklist_current_proxy(reason)
                return False

            await self._inject_captcha_token(page, token)
            logger.info("✅ Token de captcha injetado na página")
            
            # ⏳ CRITICAL: Esperar que o formulário de registro carregue após injetar o token
            logger.info("⏳ Aguardando carregamento do formulário de registro após resolução de captcha...")
            try:
                # Tentar esperar por qualquer um dos campos de entrada de registro
                registration_form_selectors = [
                    'input#registername',
                    'input[name="name"]',
                    'input#name',
                    'input[name="user"]',
                    'input[name="Username"]',
                    'input#regpass',
                    'input[name="pass"]',
                    'input#pass',
                    'input[name="password"]',
                ]
                
                registration_selector = ', '.join(registration_form_selectors)
                await page.wait_for_selector(registration_selector, timeout=15000)
                logger.info("✅ Formulário de registro carregou com sucesso")
                
                # Aguardar um pouco mais para garantir que a página está totalmente pronta
                await self._random_delay(page, 1500, 2500)
                
            except Exception as e:
                logger.warning(f"⚠️ Timeout aguardando formulário de registro após injetar token: {e}")
                # Tentar verificar se há navegação pendente
                try:
                    await page.wait_for_load_state('networkidle', timeout=5000)
                except Exception:
                    pass
            
            return True

        except Exception as e:
            logger.warning(f"⚠️ Erro ao resolver captcha: {e}")
            return False

    async def _simulate_human_interaction(self, page: Page) -> None:
        """Simula movimento humano para ajudar o Turnstile a carregar."""
        try:
            x1 = random.randint(80, 160)
            y1 = random.randint(80, 160)
            x2 = random.randint(160, 320)
            y2 = random.randint(120, 220)
            await page.mouse.move(x1, y1, steps=random.randint(8, 14))
            await page.wait_for_timeout(random.randint(150, 350))
            await page.mouse.wheel(0, random.randint(300, 600))
            await page.wait_for_timeout(random.randint(150, 350))
            await page.mouse.move(x2, y2, steps=random.randint(8, 14))
            await page.wait_for_timeout(random.randint(150, 350))
        except Exception as e:
            logger.debug(f"⚠️ Falha ao simular interação humana: {e}")

    async def _random_delay(self, page: Optional[Page] = None, min_ms: int = 900, max_ms: int = 2500) -> None:
        """Espera um tempo aleatório para simular comportamento humano.

        Se um objeto Page for passado, usa wait_for_timeout em milissegundos.
        Caso contrário, aguarda com asyncio.sleep em segundos.
        """
        delay = int(random.uniform(min_ms, max_ms))
        if page is not None:
            await page.wait_for_timeout(delay)
        else:
            seconds = delay / 1000.0
            logger.info(f"⏳ Aguardando {seconds:.1f}s...")
            await asyncio.sleep(seconds)

    async def _simulate_mouse_movement(self, page: Page) -> None:
        """Simula movimento de mouse aleatório para despertar o Turnstile."""
        try:
            logger.info("🐭 Simulando movimento de mouse aleatório para despertar Turnstile...")
            duration = random.randint(2200, 3400)
            start_time = asyncio.get_event_loop().time()

            while (asyncio.get_event_loop().time() - start_time) < (duration / 1000):
                x = random.randint(50, 1600)
                y = random.randint(50, 900)
                steps = random.randint(6, 18)
                await page.mouse.move(x, y, steps=steps)
                await page.wait_for_timeout(random.randint(120, 360))

                if random.random() < 0.4:
                    delta_y = random.randint(-250, 250)
                    await page.mouse.wheel(0, delta_y)
                    await page.wait_for_timeout(random.randint(200, 520))

            logger.info("✅ Movimento de mouse concluído")
        except Exception as e:
            logger.debug(f"⚠️ Falha ao simular movimento de mouse: {e}")

    async def _hesitate_before_final_click(self, page: Page) -> None:
        """Simula hesitação humana antes do clique final do botão de registro."""
        try:
            x = random.randint(100, 1500)
            y = random.randint(100, 900)
            steps = random.randint(8, 16)
            await page.mouse.move(x, y, steps=steps)
            await page.wait_for_timeout(random.randint(200, 600))
            logger.debug(f"🐭 Hesitação antes do clique final: moved to ({x}, {y}) in {steps} steps")
        except Exception as e:
            logger.debug(f"⚠️ Falha ao simular hesitação antes do clique final: {e}")

    async def _detect_cloudflare_challenge(self, page: Page, context: str = 'home') -> bool:
        """Detecta se a página atual está passando por Cloudflare challenge/bloqueio."""
        try:
            title = (await page.title() or '').lower()
            if not title or 'just a moment' in title or 'checking your browser' in title or 'cloudflare' in title or 'browser integrity' in title:
                sitekey = await self._extract_sitekey_from_page(page)
                if sitekey:
                    logger.info(f"ℹ️ Página de Cloudflare aparenta ter widget Turnstile/sitekey: {sitekey}. Ignorando falso positivo.")
                else:
                    logger.warning(f"⚠️ Cloudflare challenge detectado na {context} (título: '{title}')")
                    try:
                        await page.wait_for_load_state('networkidle', timeout=15000)
                        await self._random_delay(page, 2500, 4000)
                    except Exception:
                        pass
                    return True

            content = (await page.content()).lower()
            if any(marker in content for marker in ['cloudflare', 'checking your browser', 'verify you are human', 'browser integrity', 'access denied', 'forbidden', 'captcha']):
                sitekey = await self._extract_sitekey_from_page(page)
                if sitekey:
                    logger.info(f"ℹ️ Conteúdo menciona Cloudflare, mas widget Turnstile/sitekey está presente ({sitekey}). Ignorando falso positivo.")
                else:
                    logger.warning(f"⚠️ Cloudflare challenge detectado na {context} via conteúdo da página")
                    return True
        except Exception as e:
            logger.debug(f"⚠️ Erro ao detectar Cloudflare challenge na {context}: {e}")
        return False

    async def _perform_pre_login_home_flow(self, page: Page) -> None:
        """Visita a home e tenta clicar em CTA de login para criar um histórico humano antes de /login."""
        try:
            if await self._detect_cloudflare_challenge(page, 'home inicial'):
                logger.info("ℹ️ Página inicial abriu um Cloudflare challenge; aguardando e tentando novamente...")
                await self._random_delay(page, 3000, 5200)
                reload_timeout = self.config['browser_automation'].get('home_timeout', 90000)
                await page.reload(wait_until='networkidle', timeout=reload_timeout)
                await self._random_delay(page, 1600, 3200)

            await self._simulate_mouse_movement(page)
            await self._simulate_human_interaction(page)
            await self._random_delay(page, 1200, 2800)

            await page.evaluate(
                """
                () => {
                    window.scrollBy({ top: window.innerHeight * 0.35, left: 0, behavior: 'smooth' });
                }
                """
            )
            await self._random_delay(page, 1200, 2800)

            clicked = await page.evaluate(
                """
                () => {
                    const selectors = ['a', 'button', '[role="button"]'];
                    const elements = selectors.flatMap(sel => Array.from(document.querySelectorAll(sel)));
                    const target = elements.find(el => {
                        const text = (el.textContent || '').trim().toLowerCase();
                        return /login|entrar|sign in|sign-in|sign_in/.test(text);
                    });
                    if (!target) return false;
                    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    target.click();
                    return true;
                }
                """
            )

            if clicked:
                await self._random_delay(page, 2500, 4200)
                await page.wait_for_load_state('networkidle', timeout=10000)
                logger.info("✅ CTA de login clicado na home para simular navegação humana")
            else:
                await self._random_delay(page, 1300, 2400)
                logger.info("ℹ️ Não encontrou CTA de login visível na home; continuará com a navegação direta")
        except Exception as e:
            logger.warning(f"⚠️ Falha na pré-navegação da home antes do login: {e}")

    async def _patch_turnstile_callbacks(self, page: Page) -> None:
        """Instala um patch no Turnstile para capturar callbacks e aceitar token injetado."""
        try:
            await page.add_init_script(
                """
                () => {
                    const setupTurnstileInterceptor = () => {
                        if (window.turnstile && typeof window.turnstile === 'object') {
                            const originalTurnstile = window.turnstile;
                            const patched = { ...originalTurnstile };
                            if (typeof originalTurnstile.render === 'function') {
                                patched.render = function(...args) {
                                    if (args.length > 0 && typeof args[0] === 'object') {
                                        const options = args[0];
                                        if (typeof options.callback === 'function') {
                                            window.__playwright_turnstile_callback = options.callback;
                                        }
                                        if (typeof options['data-callback'] === 'function') {
                                            window.__playwright_turnstile_callback = options['data-callback'];
                                        }
                                    }
                                    return originalTurnstile.render.apply(this, args);
                                };
                            }
                            if (typeof originalTurnstile.ready === 'function') {
                                patched.ready = function(cb) {
                                    if (typeof cb === 'function') {
                                        window.__playwright_turnstile_ready_callback = cb;
                                    }
                                    return originalTurnstile.ready.apply(this, [cb]);
                                };
                            }
                            Object.defineProperty(window, 'turnstile', {
                                configurable: true,
                                enumerable: true,
                                writable: true,
                                value: patched
                            });
                        }
                    };

                    Object.defineProperty(window, '__playwright_dispatch_turnstile_token', {
                        configurable: true,
                        enumerable: true,
                        writable: true,
                        value: (token) => {
                            try {
                                window.cf_token = token;
                                window.turnstileToken = token;
                                window.grecaptchaResponse = token;
                                window.recaptchaResponse = token;
                                window.xatCaptchaToken = token;
                                if (typeof window.__playwright_turnstile_callback === 'function') {
                                    window.__playwright_turnstile_callback(token);
                                }
                                if (typeof window.__playwright_turnstile_ready_callback === 'function') {
                                    window.__playwright_turnstile_ready_callback();
                                }
                            } catch (e) {}
                        }
                    });

                    const originalSet = Object.getOwnPropertyDescriptor(window, 'turnstile');
                    if (!originalSet || !originalSet.configurable) {
                        let storedValue = window.turnstile;
                        Object.defineProperty(window, 'turnstile', {
                            configurable: true,
                            enumerable: true,
                            get() {
                                return storedValue;
                            },
                            set(value) {
                                storedValue = value;
                                try {
                                    if (value && typeof value === 'object') {
                                        const originalRender = value.render;
                                        if (typeof originalRender === 'function') {
                                            value.render = function(...args) {
                                                if (args.length > 0 && typeof args[0] === 'object') {
                                                    const options = args[0];
                                                    if (typeof options.callback === 'function') {
                                                        window.__playwright_turnstile_callback = options.callback;
                                                    }
                                                    if (typeof options['data-callback'] === 'function') {
                                                        window.__playwright_turnstile_callback = options['data-callback'];
                                                    }
                                                }
                                                return originalRender.apply(this, args);
                                            };
                                        }
                                        const originalReady = value.ready;
                                        if (typeof originalReady === 'function') {
                                            value.ready = function(cb) {
                                                if (typeof cb === 'function') {
                                                    window.__playwright_turnstile_ready_callback = cb;
                                                }
                                                return originalReady.apply(this, [cb]);
                                            };
                                        }
                                    }
                                } catch (e) {}
                                return storedValue;
                            }
                        });
                    }

                    window.addEventListener('DOMContentLoaded', setupTurnstileInterceptor);
                    setupTurnstileInterceptor();
                }
                """
            )
            logger.debug("✅ Patch de Turnstile instalado no page.init_script")
        except Exception as e:
            logger.warning(f"⚠️ Falha ao instalar patch de Turnstile: {e}")

    async def _get_element_coordinates(self, page: Page, selector: str) -> Optional[Tuple[int, int]]:
        """
        Obtém as coordenadas (x, y) do centro de um elemento na página.
        Retorna None se o elemento não for encontrado ou não estiver visível.
        """
        try:
            # Obter bounding box do elemento
            bbox = await page.locator(selector).bounding_box()
            if not bbox:
                return None

            # Calcular coordenadas do centro do elemento
            center_x = int(bbox['x'] + bbox['width'] / 2)
            center_y = int(bbox['y'] + bbox['height'] / 2)

            logger.debug(f"📍 Coordenadas do elemento {selector}: ({center_x}, {center_y})")
            return (center_x, center_y)

        except Exception as e:
            logger.warning(f"⚠️ Erro ao obter coordenadas do elemento {selector}: {e}")
            return None

    async def _click_element_with_mouse_coordinates(self, page: Page, selector: str) -> bool:
        """
        Clica em um elemento usando coordenadas do mouse em vez de page.click().
        Isso simula um clique mais humano e pode ajudar com detecção anti-bot.
        """
        try:
            # Obter coordenadas do elemento
            coords = await self._get_element_coordinates(page, selector)
            if not coords:
                logger.warning(f"⚠️ Não foi possível obter coordenadas do elemento {selector}")
                return False

            x, y = coords

            # Mover mouse para a posição (com movimento natural)
            await page.mouse.move(x, y, steps=random.randint(5, 10))

            # Pequena pausa antes do clique (simula reflexão humana)
            await page.wait_for_timeout(random.randint(100, 300))

            # Clicar com o mouse
            await page.mouse.click(x, y, button='left', delay=random.randint(50, 150))

            logger.info(f"🖱️ Clique executado via coordenadas do mouse em {selector} ({x}, {y})")
            return True

        except Exception as e:
            logger.warning(f"⚠️ Erro ao clicar via coordenadas do mouse em {selector}: {e}")
            return False

    async def _validate_sticky_ip(self, page: Page, proxy_inicial: Optional[str]) -> bool:
        """
        Valida que a sessão mantém o mesmo IP durante o registro (Sticky IP).
        Retorna True se o IP não mudou, False se mudou (o que invalidaria o token Turnstile).
        """
        try:
            # O IP não deve mudar durante a sessão de registro
            # Verificamos apenas se self.current_proxy não foi alterado (indicativo de rotação)
            if self.current_proxy != proxy_inicial:
                logger.warning(f"⚠️ AVISO: IP foi rotacionado durante o registro! Proxy mudou de {proxy_inicial.split('@')[1] if proxy_inicial and '@' in proxy_inicial else 'N/A'} para {self.current_proxy.split('@')[1] if self.current_proxy and '@' in self.current_proxy else 'N/A'}")
                logger.warning(f"⚠️ Isto pode invalidar o token Turnstile! O registro pode falhar com 'captcha verification not successful'")
                return False
            else:
                logger.debug(f"✅ Sticky IP validado - IP mantém a mesma sessão TCP")
                return True
        except Exception as e:
            logger.warning(f"⚠️ Erro ao validar Sticky IP: {e}")
            return True  # Não falhar se não conseguir validar

    async def _fill_registration_form(self, page: Page, username: str, password: str, email: str, proxy_inicial: Optional[str] = None) -> bool:
        """Preenche e submete o formulário de registro usando digitação simulada."""
        try:
            logger.info("📝 Preenchendo formulário de registro...")

            # Aguardar campo de registro visível em qualquer frame
            registration_field = await self._wait_for_registration_fields(page, 25000)
            if not registration_field:
                raise Exception("Campos de registro não foram encontrados na página ou em iframes")

            logger.info("⏳ Aguardando 2s para garantir que o formulário está pronto...")
            await page.wait_for_timeout(2000)

            # Extrair k2 direto do formulário renderizado
            k2_value = await self._extract_attribute_from_any_frame(page, 'input[name="k2"]', 'value')
            if k2_value:
                logger.info(f"✅ Token k2 extraído da página: {k2_value[:30]}...")

            # Seletores XAT reais (IDs atualizados 2026)
            username_selectors = [
                'input#registername',
                'input[name="name"]',
                'input#name',
                'input[name="user"]',
                'input[name="Username"]',
            ]
            password_selectors = [
                'input#regpass',
                'input[name="pass"]',
                'input#pass',
                'input[name="password"]',
            ]
            password2_selectors = [
                'input#regpass2',
                'input[name="pass2"]',
                'input[name="password2"]',
            ]
            email_selectors = [
                'input#regemail',
                'input[name="email"]',
                'input#email',
            ]

            # Encontrar locators com busca aprofundada em iframes
            username_locator = await self._find_first_locator_in_frames(page, username_selectors)
            password_locator = await self._find_first_locator_in_frames(page, password_selectors)
            password2_locator = await self._find_first_locator_in_frames(page, password2_selectors)
            email_locator = await self._find_first_locator_in_frames(page, email_selectors)

            if not username_locator:
                logger.warning("⚠️ Campo de username não encontrado!")
                raise Exception("Username field not found")
            if not email_locator:
                logger.warning("⚠️ Campo de email não encontrado!")
                raise Exception("Email field not found")
            if not password_locator:
                logger.warning("⚠️ Campo de password não encontrado!")
                raise Exception("Password field not found")

            logger.info("✅ Todos os campos de formulário encontrados. Preenchendo...")

            # Preencher campos com click e type (forçar foco)
            # Usando digitação simulada (type) com delays entre 80-160ms para humanizar entrada
            await self._fill_form_field(page, username_locator, username, "username", delay=120)
            await self._fill_form_field(page, password_locator, password, "password", delay=120)
            if password2_locator:
                await self._fill_form_field(page, password2_locator, password, "password2", delay=120)
            await self._fill_form_field(page, email_locator, email, "email", delay=120)

            logger.info("✅ Campos preenchidos com sucesso")

            # ⚠️ Validar Sticky IP ANTES de submeter o formulário
            # Isto garante que o token Turnstile não foi invalidado por rotação de IP
            if proxy_inicial and not await self._validate_sticky_ip(page, proxy_inicial):
                logger.warning("⚠️ CRÍTICO: IP foi rotacionado durante o preenchimento do formulário!")
                logger.warning("⚠️ O token Turnstile pode estar inválido. Abortando submissão para evitar erro de captcha.")
                raise Exception("Sticky IP violation: proxy foi rotacionado durante o registro")

            # Tentar marcar checkbox de concordância
            try:
                # Tentar ID específico do XAT primeiro
                terms_checkbox = page.locator('input#registerterms')
                if await terms_checkbox.count() > 0:
                    await terms_checkbox.check(force=True)
                    logger.info("✅ Checkbox de termos marcado com force=True")
                else:
                    # Tentar label associado
                    terms_label = page.locator('label[for="registerterms"]')
                    if await terms_label.count() > 0:
                        await terms_label.click(force=True)
                        logger.info("✅ Label de termos clicado com force=True")
            except Exception as e:
                logger.warning(f"⚠️ Não foi possível marcar terms: {e}")

            await page.wait_for_timeout(1500)
            
            # 🔥 NOVO: Detectar e resolver novo Turnstile no formulário de registro
            logger.info("🔍 Verificando se há novo Turnstile no formulário de registro...")
            has_additional_captcha = await self._detect_and_resolve_additional_turnstile(page)
            if has_additional_captcha:
                logger.info("✅ Novo Turnstile resolvido com sucesso")
            else:
                logger.info("ℹ️ Nenhum Turnstile adicional detectado no formulário")

            # Upgrade Final: Safety Gate + Clique Humanizado + Loop de Re-tentativa
            captcha_retry_count = 0
            max_captcha_retries = 3
            captcha_success = False

            while captcha_retry_count < max_captcha_retries and not captcha_success:
                logger.info(f"🔄 Tentativa de captcha {captcha_retry_count + 1}/{max_captcha_retries}")

                # 1. Injetar token do captcha
                await self._inject_captcha_token_if_missing(page)
                logger.info("⏳ Aguardando processamento do token injetado...")

                # 2. Safety Gate: Validar sucesso do captcha por até 20 segundos
                if await self._validate_captcha_success(page, timeout_seconds=15):
                    logger.info("✅ Captcha validado com sucesso - prosseguindo para submissão")
                    captcha_success = True
                else:
                    logger.warning(f"❌ Captcha não validado na tentativa {captcha_retry_count + 1}")

                    if captcha_retry_count < max_captcha_retries - 1:
                        # Limpar campo de captcha para nova tentativa
                        await page.evaluate("""
                            () => {
                                const fields = document.querySelectorAll('input[name="cf-turnstile-response"], textarea[name="cf-turnstile-response"]');
                                fields.forEach(field => {
                                    field.value = '';
                                    field.removeAttribute('value');
                                });
                                // Limpar variáveis globais
                                window.cf_token = null;
                                window.turnstileToken = null;
                                window.grecaptchaResponse = null;
                            }
                        """)
                        logger.info("🧹 Campo de captcha limpo para nova tentativa")

                        # Aguardar um pouco antes de tentar novamente
                        await page.wait_for_timeout(2000)

                        captcha_retry_count += 1
                        continue
                    else:
                        logger.error(f"❌ Máximo de {max_captcha_retries} tentativas de captcha atingido")
                        raise Exception("Captcha validation failed after maximum retries")

            # Se chegou aqui, captcha foi validado com sucesso
            logger.info("🎯 Captcha validado - iniciando submissão do formulário")

            await page.evaluate(
                """
                () => {
                    const registerButton = document.querySelector('a#butregister');
                    if (registerButton) {
                        registerButton.classList.remove('disabled');
                        registerButton.removeAttribute('disabled');
                    }
                }
                """
            )

            await page.evaluate(
                """
                () => {
                    const token = window.cf_token || window.turnstileToken || window.grecaptchaResponse || window.recaptchaResponse || window.xatCaptchaToken || document.querySelector('input[name="cf-turnstile-response"]')?.value || document.querySelector('textarea[name="cf-turnstile-response"]')?.value || document.querySelector('input[name="g-recaptcha-response"]')?.value || document.querySelector('textarea[name="g-recaptcha-response"]')?.value;
                    if (!token) {
                        return;
                    }

                    const invoke = (name) => {
                        if (!name) return;
                        const fn = window[name];
                        if (typeof fn === 'function') {
                            try {
                                fn(token);
                            } catch (e) {}
                        }
                    };

                    document.querySelectorAll('[data-callback], [data-recaptcha-callback]').forEach(element => {
                        invoke(element.getAttribute('data-callback'));
                        invoke(element.getAttribute('data-recaptcha-callback'));
                    });

                    if (window.__cf_turnstile_config) {
                        invoke(window.__cf_turnstile_config.callback || window.__cf_turnstile_config['data-callback']);
                    }

                    if (window.turnstile) {
                        try {
                            if (typeof window.turnstile.execute === 'function') {
                                window.turnstile.execute();
                            }
                        } catch (e) {}
                        try {
                            if (typeof window.turnstile === 'function') {
                                window.turnstile(token);
                            }
                        } catch (e) {}
                    }
                }
                """
            )

            logger.info("✅ Aguarde concluído; enviando o registro imediatamente a seguir")

            # � PRÉ-SUBMIT DEBUG: Capturar estado do formulário antes do envio
            logger.info("🔍 ===== DEBUG PRÉ-SUBMIT: Capturando estado do formulário =====")
            pre_submit_state = await page.evaluate("""
                () => {
                    const xat_token_fields = [
                        '#registercap input[name="cf-turnstile-response"]',
                        '#registercap textarea[name="cf-turnstile-response"]',
                        'form#regform input[name="cf-turnstile-response"]',
                        'form#regform textarea[name="cf-turnstile-response"]',
                        'input[name="cf-turnstile-response"]',
                        'textarea[name="cf-turnstile-response"]'
                    ];
                    
                    const tokenInfo = {};
                    xat_token_fields.forEach(selector => {
                        const field = document.querySelector(selector);
                        if (field) {
                            tokenInfo[selector] = {
                                has_value: !!field.value,
                                value_length: field.value ? field.value.length : 0,
                                first_50: field.value ? field.value.substring(0, 50) : null,
                                visible: field.offsetParent !== null
                            };
                        }
                    });
                    
                    const form = document.querySelector('form#regform') || document.querySelector('form');
                    const form_data = new FormData(form);
                    const form_entries = {};
                    for (const [key, value] of form_data.entries()) {
                        if (key.includes('captcha') || key.includes('turnstile') || key.includes('recaptcha')) {
                            form_entries[key] = {
                                value_length: value.length,
                                first_50: value.substring(0, 50)
                            };
                        } else {
                            form_entries[key] = typeof value === 'string' ? value : '[FILE]';
                        }
                    }
                    
                    return {
                        token_fields: tokenInfo,
                        form_data: form_entries,
                        form_action: form ? form.action : null,
                        form_method: form ? form.method : null
                    };
                }
            """)
            
            logger.info(f"🔍 Token Fields Pre-Submit: {pre_submit_state.get('token_fields')}")
            logger.info(f"🔍 Form Data (captcha-related): {pre_submit_state.get('form_data')}")
            logger.info(f"🔍 Form Action: {pre_submit_state.get('form_action')}")
            logger.info(f"🔍 Form Method: {pre_submit_state.get('form_method')}")

            # 🔍 Interceptar requisições POST após o submit
            post_requests = []
            post_responses = []
            
            async def handle_request(request):
                if request.method == 'POST':
                    try:
                        post_body = await request.post_data()
                        if post_body:
                            post_requests.append({
                                'url': request.url,
                                'method': request.method,
                                'body_size': len(post_body),
                                'body_preview': post_body[:200] if isinstance(post_body, str) else str(post_body)[:200]
                            })
                            logger.info(f"🔍 POST Request interceptado: URL={request.url}, body_size={len(post_body)}")
                    except:
                        pass
            
            async def handle_response(response):
                if response.request.method == 'POST':
                    try:
                        response_text = await response.text()
                        post_responses.append({
                            'url': response.url,
                            'status': response.status,
                            'body_size': len(response_text),
                            'body_preview': response_text[:500]
                        })
                        logger.info(f"🔍 POST Response interceptado: URL={response.url}, status={response.status}, size={len(response_text)}")
                        if response.status != 200:
                            logger.warning(f"⚠️ POST Error Response (status {response.status}): {response_text[:500]}")
                    except:
                        pass
            
            # Registrar handlers
            page.on('request', handle_request)
            page.on('response', handle_response)

            # �🔥 FORCE SUBMIT INTELIGENTE - Múltiplas estratégias de fallback
            submit_found = False
            submit_selectors = [
                'a#butregister',  # Link de submit (ID real do XAT)
                'button:has-text("register")',
                'button:has-text("Register")',
                'input[type="submit"]',
                'button[type="submit"]',
                '.submit-btn'
            ]
            
            # Estratégia 1: Remover atributos disabled e preparar o botão
            logger.info("🔧 Estratégia 1: Preparando botão - removendo atributo disabled...")
            try:
                await page.evaluate("""
                    () => {
                        document.querySelectorAll('button, input[type="submit"], a').forEach(el => {
                            if (el.hasAttribute('disabled')) {
                                el.removeAttribute('disabled');
                                console.log('[Playwright] Atributo disabled removido de:', el.tagName, el.id, el.className);
                            }
                        });
                    }
                """)
                logger.info("✅ Atributos disabled removidos de todos os botões possíveis")
            except Exception as e:
                logger.debug(f"⚠️ Falha ao remover disabled: {e}")
            
            # Estratégia 2: Tentar clicar via múltiplas formas
            for selector in submit_selectors:
                try:
                    button = page.locator(selector).first
                    if await button.count() > 0:
                        logger.info(f"✅ Botão de submit encontrado: {selector}")
                        
                        # Método A: Coordenadas do mouse (mais humanizado)
                        try:
                            if await self._click_element_with_mouse_coordinates(page, selector):
                                logger.info(f"✅ Botão clicado via coordenadas do mouse: {selector}")
                                submit_found = True
                                break
                        except Exception as e:
                            logger.debug(f"  Coordenadas falhou: {e}")
                        
                        # Método B: Clique normal do Playwright
                        try:
                            await self._hesitate_before_final_click(page)
                            await button.click()
                            logger.info(f"✅ Botão clicado via Playwright click(): {selector}")
                            submit_found = True
                            break
                        except Exception as e:
                            logger.debug(f"  Clique normal falhou: {e}")
                        
                        # Método C: Clique via JavaScript
                        try:
                            await page.evaluate(f'document.querySelector("{selector}").click()')
                            logger.info(f"✅ Botão clicado via JavaScript: {selector}")
                            submit_found = True
                            break
                        except Exception as e:
                            logger.debug(f"  Clique JS falhou: {e}")
                        
                        # Método D: Dispatch MouseEvent (mais realista)
                        try:
                            await page.evaluate(f"""
                                () => {{
                                    const el = document.querySelector("{selector}");
                                    if (el) {{
                                        const event = new MouseEvent('click', {{
                                            bubbles: true,
                                            cancelable: true,
                                            view: window
                                        }});
                                        el.dispatchEvent(event);
                                    }}
                                }}
                            """)
                            logger.info(f"✅ Botão clicado via MouseEvent dispatch: {selector}")
                            submit_found = True
                            break
                        except Exception as e:
                            logger.debug(f"  MouseEvent falhou: {e}")
                        
                except Exception as e:
                    logger.debug(f"  Seletor {selector} não encontrado: {e}")
                    continue

            # Estratégia 3: Fallback nuclear - Forçar submit do formulário
            if not submit_found:
                logger.warning("⚠️ Cliques normais não funcionaram. Tentando fallback nuclear...")
                
                # Tentativa 1: Procurar e fazer submit do formulário pai
                try:
                    form_submitted = await page.evaluate("""
                        () => {
                            // Procura o formulário de registro
                            const form = document.querySelector('form') || 
                                       document.querySelector('[role="form"]') ||
                                       document.querySelector('.form-register');
                            
                            if (form && typeof form.submit === 'function') {
                                console.log('[Playwright] Submetendo formulário via form.submit()');
                                form.submit();
                                return true;
                            }
                            return false;
                        }
                    """)
                    
                    if form_submitted:
                        logger.info("✅ Formulário submetido via form.submit()")
                        submit_found = True
                    else:
                        logger.warning("⚠️ form.submit() não foi possível")
                except Exception as e:
                    logger.warning(f"⚠️ Fallback form.submit() falhou: {e}")
                
                # Tentativa 2: Clique direto no link específico do XAT
                if not submit_found:
                    try:
                        await self._hesitate_before_final_click(page)
                        await page.click('a#butregister', force=True)
                        logger.info("✅ Clique force=True em a#butregister funcionou")
                        submit_found = True
                    except Exception as e:
                        logger.warning(f"⚠️ force=True falhou: {e}")
                
                # Tentativa 3: Navegar para a ação do formulário se tudo mais falhar
                if not submit_found:
                    try:
                        action_url = await page.evaluate("document.querySelector('form')?.action")
                        if action_url:
                            logger.warning(f"⚠️ Navegando para URL de ação do formulário: {action_url}")
                            # Aqui poderíamos fazer POST via Playwright, mas é mais arriscado
                            logger.warning("⚠️ Fallback de navegação não implementado - requer POST manual")
                    except Exception as e:
                        logger.debug(f"  Não foi possível extrair action URL: {e}")

            if submit_found:
                logger.info("✅ Submit bem-sucedido! Aguardando resposta...")
            else:
                logger.error("❌ Nenhuma estratégia de submit funcionou")

            # Esperar um pouco após o clique para o XAT processar o registro
            logger.info("⏳ Aguardando 3s após o clique para a mensagem final aparecer...")
            await page.wait_for_timeout(3000)

            # 🔍 PÓS-SUBMIT DEBUG: Capturar resposta e estado da página
            logger.info("🔍 ===== DEBUG PÓS-SUBMIT: Capturando estado da página =====")
            logger.info(f"🔍 POST Requests Interceptados: {len(post_requests)}")
            for i, req in enumerate(post_requests):
                logger.info(f"  [{i+1}] URL: {req['url']}, body_size: {req['body_size']}, preview: {req['body_preview']}")
            
            logger.info(f"🔍 POST Responses Interceptadas: {len(post_responses)}")
            for i, resp in enumerate(post_responses):
                logger.info(f"  [{i+1}] URL: {resp['url']}, status: {resp['status']}, size: {resp['body_size']}")
                if resp['status'] != 200:
                    logger.warning(f"⚠️ Response Body ({resp['status']}): {resp['body_preview']}")
            
            # Desregistrar handlers
            try:
                page.remove_listener('request', handle_request)
                page.remove_listener('response', handle_response)
            except:
                pass

            # Captura de diagnóstico após o submit, especialmente útil quando o bot sai cedo demais
            screenshot_path = f"post_submit_{username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            try:
                await page.screenshot(path=screenshot_path, full_page=True)
                logger.info(f"📸 Screenshot pós-submit salva em {screenshot_path}")
            except Exception as e:
                logger.warning(f"⚠️ Falha ao salvar screenshot pós-submit: {e}")

            await page.wait_for_timeout(2000)
            await page.wait_for_load_state('networkidle', timeout=15000)
            
            # 🔍 ANÁLISE DE ERRO DETALHADA PÓS-SUBMIT
            logger.info("🔍 ===== DEBUG PÓS-RESPOSTA: Analisando página de resposta =====")
            post_response_state = await page.evaluate("""
                () => {
                    // Procurar erro mais específico
                    const error_selectors = [
                        'div.alert-danger',
                        '.alert.alert-danger',
                        '.popover-body',
                        '#errore-msg',
                        '.error',
                        '[role="alert"]'
                    ];
                    
                    const errors_found = {};
                    error_selectors.forEach(selector => {
                        const el = document.querySelector(selector);
                        if (el) {
                            errors_found[selector] = {
                                text: el.textContent ? el.textContent.trim() : '[empty]',
                                html: el.innerHTML ? el.innerHTML.substring(0, 200) : '[empty]',
                                visible: el.offsetParent !== null
                            };
                        }
                    });
                    
                    // Verificar URL
                    const url = window.location.href;
                    
                    // Verificar se há sucesso
                    const success_indicators = [
                        'welcome', 'home', 'success', 'created', 'registered',
                        'conta criada', 'bem-vindo', 'sucesso'
                    ];
                    const page_text = document.body.textContent.toLowerCase();
                    const has_success = success_indicators.some(ind => page_text.includes(ind));
                    
                    // Capturar todo o body text (primeiros 1000 chars)
                    const body_text = document.body.textContent.substring(0, 1000);
                    
                    return {
                        current_url: url,
                        errors_found: errors_found,
                        has_success: has_success,
                        body_text: body_text
                    };
                }
            """)
            
            logger.info(f"🔍 Current URL: {post_response_state.get('current_url')}")
            logger.info(f"🔍 Has Success Indicators: {post_response_state.get('has_success')}")
            if post_response_state.get('errors_found'):
                for selector, error_info in post_response_state['errors_found'].items():
                    logger.warning(f"⚠️ Error Element [{selector}]:")
                    logger.warning(f"   Text: {error_info['text']}")
                    logger.warning(f"   HTML: {error_info['html']}")
            logger.info(f"🔍 Body Text (first 500): {post_response_state.get('body_text')[:500]}")

            error_message = await self._monitor_submission_result(page)
            if error_message:
                screenshot_path = f"erro_submit_{username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                try:
                    await page.screenshot(path=screenshot_path, full_page=True)
                    logger.info(f"📸 Screenshot de erro pós-submit salva em {screenshot_path}")
                except Exception as e:
                    logger.warning(f"⚠️ Falha ao salvar screenshot de erro pós-submit: {e}")
                logger.warning(f"⚠️ Detecção de erro após submissão: {error_message}")

                # Upgrade Final: Loop de Re-tentativa para erro de captcha
                if 'captcha' in error_message.lower() or 'verification' in error_message.lower():
                    logger.warning("🚨 Erro de captcha detectado! Iniciando loop de re-tentativa...")

                    # Resetar estado do captcha para nova tentativa
                    await page.evaluate("""
                        () => {
                            // Limpar campos de captcha
                            const fields = document.querySelectorAll('input[name="cf-turnstile-response"], textarea[name="cf-turnstile-response"]');
                            fields.forEach(field => {
                                field.value = '';
                                field.removeAttribute('value');
                            });

                            // Limpar variáveis globais
                            window.cf_token = null;
                            window.turnstileToken = null;
                            window.grecaptchaResponse = null;

                            // Resetar widget Turnstile se possível
                            if (window.turnstile && typeof window.turnstile.reset === 'function') {
                                try {
                                    window.turnstile.reset();
                                } catch (e) {}
                            }
                        }
                    """)

                    # Aguardar widget resetar
                    await page.wait_for_timeout(3000)

                    # Tentar resolver captcha novamente (isso irá incrementar captcha_retry_count)
                    logger.info("🔄 Tentando resolver captcha novamente...")
                    raise Exception(f"Captcha error detected: {error_message}")

            result = await self._verify_registration_result(page, username, email)

            logger.info("✅ Formulário submetido")
            return result

        except Exception as e:
            logger.error(f"❌ Erro ao preencher formulário: {e}")
            try:
                await page.screenshot(path='erro_registro.png', full_page=True)
                logger.info("📸 Screenshot de erro salva em erro_registro.png")
            except Exception as screenshot_error:
                logger.warning(f"⚠️ Falha ao salvar screenshot de erro: {screenshot_error}")
            try:
                html_content = await page.content()
                Path('erro_registro.html').write_text(html_content, encoding='utf-8')
                logger.info("📝 Conteúdo HTML salvo em erro_registro.html")
            except Exception as html_error:
                logger.warning(f"⚠️ Falha ao salvar HTML de erro: {html_error}")
            return False

    async def _type_with_delay(self, page: Page, selector_or_locator, value: str, delay: int = 120) -> None:
        """Preenche um campo usando digitação simulada."""
        try:
            if isinstance(selector_or_locator, str):
                locator = page.locator(selector_or_locator).first
            else:
                locator = selector_or_locator

            await locator.wait_for(timeout=20000)
            await locator.scroll_into_view_if_needed()
            await locator.click(click_count=3)
            await locator.fill("")
            for char in value:
                await locator.type(char, delay=random.randint(delay - 40, delay + 40))
            await page.wait_for_timeout(200)
        except Exception:
            try:
                if isinstance(selector_or_locator, str):
                    await page.fill(selector_or_locator, value)
            except Exception:
                logger.warning(f"⚠️ Não foi possível preencher o campo {selector_or_locator}")

    async def _wait_for_registration_fields(self, page: Page, timeout: int = 35000) -> Optional[Locator]:
        """Aguarda o primeiro campo de registro ficar disponível em qualquer iframe."""
        selectors = [
            'input#registername',
            'input#regpass',
            'input#regemail',
            'input[name="name"]',
            'input[name="email"]',
            'input[type="text"]',
        ]
        deadline = time.time() + timeout / 1000.0
        while time.time() < deadline:
            locator = await self._find_first_locator_in_frames(page, selectors)
            if locator:
                logger.info("✅ Campos de registro encontrados na página")
                return locator
            await page.wait_for_timeout(500)
        logger.warning(f"⚠️ Campos de registro não encontrados após {timeout}ms")
        return None

    async def _extract_attribute_from_any_frame(self, page: Page, selector: str, attribute: str) -> Optional[str]:
        """Extrai atributo de um seletor em qualquer frame."""
        for frame in page.frames:
            try:
                element = await frame.query_selector(selector)
                if element:
                    value = await element.get_attribute(attribute)
                    if value:
                        return value
            except Exception:
                continue
        return None

    async def _find_first_locator_in_frames(self, page: Page, selectors: List[str]) -> Optional[Locator]:
        """Encontra o primeiro locator visível em qualquer frame da página."""
        # Primeiro tenta na página principal
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if await locator.count() > 0 and await locator.is_visible():
                    logger.debug(f"✅ Seletor encontrado na página principal: {selector}")
                    return locator
            except Exception:
                continue

        # Depois procura em todos os iframes
        for frame in page.frames:
            for selector in selectors:
                try:
                    locator = frame.locator(selector).first
                    if await locator.count() > 0 and await locator.is_visible():
                        logger.debug(f"✅ Seletor encontrado em iframe: {selector}")
                        return locator
                except Exception:
                    continue

        return None

    async def _fill_form_field(self, page: Page, locator: Locator, value: str, field_name: str, delay: int = 120) -> None:
        """
        Preenche um campo de formulário com clique forçado e tipagem simulada humanizada.
        
        Estratégia:
        - Clique forçado para garantir foco
        - Digitação letra por letra com delays aleatórios (100-300ms) para simular digitação humana
        - Aguardas estratégicas entre passadas para o Turnstile processar a entrada
        """
    async def _fill_form_field(self, page: Page, locator: Locator, value: str, field_name: str, delay: int = 120) -> None:
        """
        Preenche um campo de formulário com clique forçado e tipagem simulada humanizada.
        
        Estratégia:
        - Clique forçado para garantir foco
        - Digitação letra por letra com delays aleatórios (100-300ms) para simular digitação humana
        - Aguardas estratégicas entre passadas para o Turnstile processar a entrada
        """
        try:
            logger.info(f"📝 Preenchendo {field_name} com digitação humanizada...")
            
            # Aguardar que o campo esteja visível
            await locator.wait_for(timeout=20000)
            
            # Scroll para o campo
            await locator.scroll_into_view_if_needed()
            
            # Forçar clique para garantir foco
            await locator.click(click_count=1)
            await page.wait_for_timeout(300)
            
            # Limpar qualquer conteúdo anterior
            await locator.fill("")
            await page.wait_for_timeout(200)
            
            # ⚠️ Digitar letra por letra com delays aleatórios de 100-300ms para humanizar entrada
            # Isto evita que o padrão de preenchimento pareça automático
            for i, char in enumerate(value):
                # Delays aleatórios: 100-300ms entre teclas (ajustável via 'delay' parameter)
                char_delay = random.randint(100, 300)
                await locator.type(char, delay=char_delay)
                
                # A cada 3-5 caracteres, aguardar um pouco mais para simular reflexão humana
                if (i + 1) % random.randint(3, 5) == 0:
                    await page.wait_for_timeout(random.randint(200, 400))
            
            await page.wait_for_timeout(300)
            logger.info(f"✅ {field_name} preenchido com sucesso (digitação humanizada: {len(value)} caracteres)")
            
        except Exception as e:
            logger.warning(f"⚠️ Erro ao preencher {field_name}: {e}")
            # Tentar alternativa com fill direto
            try:
                await locator.fill(value)
                logger.info(f"✅ {field_name} preenchido via fill (alternativa, não humanizado)")
            except Exception as e2:
                logger.error(f"❌ Falha ao preencher {field_name}: {e2}")
                raise

    async def _find_first_locator(self, page: Page, selectors: List[str]) -> Optional[Locator]:
        """Retorna o primeiro locator válido encontrado na página ou em iframes."""
        first_found: Optional[Locator] = None
        for frame in page.frames:
            for selector in selectors:
                try:
                    locator = frame.locator(selector).first
                    if await locator.count() > 0:
                        if not first_found:
                            first_found = locator
                        if await locator.is_visible():
                            return locator
                except Exception:
                    continue
        return first_found

    async def _extract_sitekey_from_page(self, page: Page) -> Optional[str]:
        """Extrai o sitekey do widget de Turnstile/Recaptcha na página."""
        try:
            sitekey = await page.evaluate(
                """
                () => {
                    const getSitekeyFromElement = (element) => {
                        if (!element) return null;
                        return element.dataset?.sitekey || element.dataset?.cfTurnstileSitekey || element.getAttribute('data-sitekey') || element.getAttribute('data-cf-turnstile-sitekey') || element.getAttribute('sitekey');
                    };

                    const isVisible = (element) => {
                        if (!element) return false;
                        const rect = element.getBoundingClientRect();
                        const style = window.getComputedStyle(element);
                        return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none' && style.opacity !== '0';
                    };

                    const visibleKeys = [];
                    const hiddenKeys = [];
                    const widgets = document.querySelectorAll('[data-sitekey], [data-cf-turnstile-sitekey], .cf-turnstile, .g-recaptcha');
                    widgets.forEach(widget => {
                        const key = getSitekeyFromElement(widget);
                        if (!key) return;
                        if (isVisible(widget)) {
                            visibleKeys.push(key);
                        } else {
                            hiddenKeys.push(key);
                        }
                    });

                    if (visibleKeys.length) {
                        return visibleKeys[0];
                    }
                    if (hiddenKeys.length) {
                        return hiddenKeys[0];
                    }

                    const iframe = document.querySelector('iframe[src*="turnstile"]');
                    if (iframe) {
                        try {
                            return new URL(iframe.src).searchParams.get('sitekey');
                        } catch (e) {
                            return null;
                        }
                    }

                    const captchaIframe = document.querySelector('iframe[src*="captcha"]');
                    if (captchaIframe) {
                        try {
                            return new URL(captchaIframe.src).searchParams.get('sitekey');
                        } catch (e) {
                            return null;
                        }
                    }

                    if (window.__cf_turnstile_config && window.__cf_turnstile_config.sitekey) {
                        return window.__cf_turnstile_config.sitekey;
                    }

                    if (window.turnstile && typeof window.turnstile === 'object' && window.turnstile.sitekey) {
                        return window.turnstile.sitekey;
                    }

                    if (window.grecaptcha && typeof window.grecaptcha === 'object' && window.grecaptcha.sitekey) {
                        return window.grecaptcha.sitekey;
                    }

                    return null;
                }
                """
            )
            if sitekey and not self._is_allowed_sitekey(sitekey):
                logger.warning(f"⚠️ Sitekey de DOM não permitida detectada e ignorada: {sitekey}")
                return None
            return sitekey
        except Exception as e:
            logger.warning(f"⚠️ Erro ao extrair sitekey do DOM: {e}")
            return None

    def _extract_sitekey_from_html(self, html_content: str) -> Optional[str]:
        """Extrai sitekey de conteúdo HTML usando regex e fallback em texto/bruto."""
        try:
            if not html_content:
                return None

            html_content = html.unescape(html_content)
            patterns = [
                r'data-sitekey=["\']([^"\']+)["\']',
                r'data-cf-turnstile-sitekey=["\']([^"\']+)["\']',
                r'sitekey\s*[:=]\s*["\'](0x4[a-zA-Z0-9_-]{18,30})["\']',
                r'"sitekey"\s*:\s*"(0x4[a-zA-Z0-9_-]{18,30})"',
                r'\bsitekey=(0x4[a-zA-Z0-9_-]{18,30})\b',
                r'(0x4[a-zA-Z0-9_-]{18,30})'
            ]
            for pattern in patterns:
                match = re.search(pattern, html_content)
                if match:
                    sitekey = match.group(1)
                    if self._is_allowed_sitekey(sitekey):
                        return sitekey
                    logger.warning(f"⚠️ Sitekey HTML não permitida detectada e ignorada: {sitekey}")
            return None
        except Exception as e:
            logger.warning(f"⚠️ Erro ao extrair sitekey do HTML: {e}")
            return None

    async def _extract_sitekey_from_full_page_content(self, page: Page) -> Optional[str]:
        """Busca sitekey no HTML completo da página principal, em frames e no texto da página."""
        try:
            page_content = await page.content()
            sitekey = self._extract_sitekey_from_html(page_content)
            if sitekey:
                return sitekey

            for frame in page.frames:
                try:
                    frame_html = await frame.content()
                    sitekey = self._extract_sitekey_from_html(frame_html)
                    if sitekey:
                        return sitekey
                except Exception:
                    continue

            try:
                body_text = await page.text_content('body')
                if body_text:
                    sitekey = self._extract_sitekey_from_html(body_text)
                    if sitekey:
                        return sitekey
            except Exception:
                pass

            return None
        except Exception as e:
            logger.warning(f"⚠️ Erro ao buscar sitekey no conteúdo completo da página: {e}")
            return None

    def _build_extra_http_headers(self, user_agent: str) -> Dict[str, str]:
        """Retorna cabeçalhos Client Hints compatíveis com o User-Agent escolhido."""
        return {
            'sec-ch-ua': self._get_sec_ch_ua(user_agent),
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': self._get_sec_ch_ua_platform(user_agent)
        }

    def _get_sec_ch_ua(self, user_agent: str) -> str:
        if 'Edg/' in user_agent or 'Edge/' in user_agent:
            return '"Chromium";v="140", "Microsoft Edge";v="140", ";Not A Brand";v="99"'
        if 'Firefox/' in user_agent:
            return '"Mozilla";v="140", "Firefox";v="140", ";Not A Brand";v="99"'
        if 'Safari/' in user_agent and 'Chrome/' not in user_agent:
            return '"Safari";v="18", "Apple WebKit";v="605", ";Not A Brand";v="99"'
        return '"Chromium";v="140", "Google Chrome";v="140", ";Not A Brand";v="99"'

    def _get_sec_ch_ua_platform(self, user_agent: str) -> str:
        if 'Windows NT' in user_agent:
            return '"Windows"'
        if 'Macintosh' in user_agent:
            return '"macOS"'
        if 'Android' in user_agent or 'iPhone' in user_agent or 'iPad' in user_agent:
            return '"Android"'
        return '"Windows"'

    def _get_navigator_platform_override(self, user_agent: str) -> str:
        if 'Windows NT' in user_agent:
            return 'Win32'
        if 'Macintosh' in user_agent:
            return 'MacIntel'
        if 'Android' in user_agent:
            return 'Android'
        return 'Win32'

    def _get_navigator_vendor_override(self, user_agent: str) -> str:
        if 'Safari/' in user_agent and 'Chrome/' not in user_agent:
            return 'Apple Computer, Inc.'
        return 'Google Inc.'

    async def _detect_and_resolve_additional_turnstile(self, page: Page) -> bool:
        """
        Detecta se há um novo Turnstile no formulário de registro (após preencher campos)
        e resolve automaticamente se encontrado.
        Retorna True se detectou e resolveu, False caso contrário.
        """
        try:
            logger.info("🔍 Procurando novo Turnstile no formulário de registro...")
            
            # Verificar se há um novo sitekey diferente ou outro Turnstile
            new_sitekey = await self._extract_sitekey_from_page(page)
            
            if not new_sitekey:
                logger.debug("  ℹ️ Nenhum sitekey Turnstile encontrado no formulário")
                return False
            
            logger.info(f"🔓 Novo sitekey Turnstile detectado: {new_sitekey}")
            
            # Simular clique humanizado no novo widget
            if not await self._humanize_turnstile_click(page):
                logger.warning("⚠️ Clique humanizado falhou, mas continuando mesmo assim...")
            
            # Aguardar um pouco
            await self._random_delay(page, 1800, 2500)
            
            # Obter configuração de página
            page_url = page.url
            payload = await self._extract_turnstile_payload(page)
            user_agent = await page.evaluate("navigator.userAgent")
            
            logger.info(f"🔐 Resolvendo novo Turnstile (sitekey={new_sitekey[:20]}..., url={page_url})")
            
            # Resolver com 2Captcha
            token = self._resolver_recaptcha(new_sitekey, page_url, payload, user_agent=user_agent)
            if not token:
                logger.warning("⚠️ Novo Turnstile não foi resolvido pelo 2Captcha")
                return False
            
            logger.info(f"✅ Novo Turnstile resolvido: {token[:30]}...")
            
            # Injetar o token
            await self._inject_captcha_token(page, token)
            logger.info("✅ Novo token injetado com sucesso")
            
            # Aguardar validação
            await self._random_delay(page, 1500, 2500)
            
            return True
            
        except Exception as e:
            logger.warning(f"⚠️ Erro ao detectar/resolver novo Turnstile: {e}")
            return False

    async def _validate_captcha_success(self, page: Page, timeout_seconds: int = 15) -> bool:
        """
        Safety Gate: Valida visualmente se o Turnstile/reCAPTCHA foi resolvido com sucesso.
        
        IMPORTANTE: Procura APENAS em campos reais do XAT reCAPTCHA (não em tokens órfãos aleatórios).
        Valida que o token está associado a um widget visível na página.
        """
        logger.info(f"🔒 Safety Gate: Validando sucesso do captcha XAT por até {timeout_seconds}s...")

        # Campos possíveis do XAT reCAPTCHA/ReCaptcha em ordem de prioridade
        xat_captcha_fields = [
            ('#registercap input[name="cf-turnstile-response"]', 'Cloudflare Turnstile (input, registercap)'),
            ('#registercap textarea[name="cf-turnstile-response"]', 'Cloudflare Turnstile (textarea, registercap)'),
            ('#registercap input[name="g-recaptcha-response"]', 'Google reCAPTCHA (input, registercap)'),
            ('#registercap textarea[name="g-recaptcha-response"]', 'Google reCAPTCHA (textarea, registercap)'),
            ('form#regform input[name="cf-turnstile-response"]', 'Cloudflare Turnstile (input, regform)'),
            ('form#regform textarea[name="cf-turnstile-response"]', 'Cloudflare Turnstile (textarea, regform)'),
            ('form#regform input[name="g-recaptcha-response"]', 'Google reCAPTCHA (input, regform)'),
            ('form#regform textarea[name="g-recaptcha-response"]', 'Google reCAPTCHA (textarea, regform)'),
            ('input[name="cf-turnstile-response"]', 'Cloudflare Turnstile (input)'),
            ('textarea[name="cf-turnstile-response"]', 'Cloudflare Turnstile (textarea)'),
            ('input[name="g-recaptcha-response"]', 'Google reCAPTCHA (input)'),
            ('textarea[name="g-recaptcha-response"]', 'Google reCAPTCHA (textarea)'),
        ]

        start_time = asyncio.get_event_loop().time()
        check_count = 0
        
        while (asyncio.get_event_loop().time() - start_time) < timeout_seconds:
            check_count += 1
            elapsed = int(asyncio.get_event_loop().time() - start_time)
            
            try:
                # Procurar token em CADA campo específico do XAT
                validation_result = await page.evaluate(
                    """
                    (fields_specs) => {
                        const results = [];
                        
                        for (const [selector, fieldType] of fields_specs) {
                            const field = document.querySelector(selector);
                            if (!field) {
                                results.push({
                                    selector: selector,
                                    fieldType: fieldType,
                                    found: false,
                                    tokenLength: 0,
                                    hasWidget: false,
                                    fieldValue: null
                                });
                                continue;
                            }
                            
                            const tokenValue = field.value || '';
                            const tokenLength = tokenValue.length;
                            
                            // Verificar se há um widget visível associado a este campo
                            let hasWidget = false;
                            try {
                                // Procurar iframe de Turnstile/reCAPTCHA na página
                                const turnstileIframe = document.querySelector('iframe[src*="challenges.cloudflare.com"], iframe[src*="turnstile"], iframe[src*="recaptcha"], iframe[src*="captcha"]');
                                if (turnstileIframe && turnstileIframe.offsetParent !== null) {
                                    hasWidget = true;
                                }
                                
                                // Verificar data-sitekey (indicador de widget)
                                const widgetElement = document.querySelector('[data-sitekey], .cf-turnstile, .g-recaptcha');
                                if (widgetElement && widgetElement.offsetParent !== null) {
                                    hasWidget = true;
                                }
                            } catch (e) {
                                // Ignorar erros ao verificar widget
                            }
                            
                            results.push({
                                selector: selector,
                                fieldType: fieldType,
                                found: true,
                                tokenLength: tokenLength,
                                hasWidget: hasWidget,
                                fieldValue: tokenValue.substring(0, 50) + (tokenValue.length > 50 ? '...' : '')
                            });
                        }
                        
                        return results;
                    }
                    """,
                    xat_captcha_fields
                )
                
                # Processar resultados
                for field_info in validation_result:
                    if field_info['found'] and field_info['tokenLength'] > 50 and field_info['hasWidget']:
                        # Aceitamos somente campos reais do XAT dentro de #registercap ou form#regform
                        if field_info['selector'].startswith('#registercap') or field_info['selector'].startswith('form#regform'):
                            logger.info(
                                f"✅ Safety Gate: Token VÁLIDO encontrado! "
                                f"Campo: {field_info['selector']} | "
                                f"Tipo: {field_info['fieldType']} | "
                                f"Comprimento: {field_info['tokenLength']} chars | "
                                f"Widget visível: SIM | "
                                f"Preview: {field_info['fieldValue']}"
                            )
                            
                            # Validação extra: verificar callback disparado
                            callback_fired = await page.evaluate("() => !!window.__playwright_turnstile_callback_fired")
                            if callback_fired:
                                logger.info("✅ Safety Gate: Callback do Turnstile foi disparado com sucesso")
                            
                            return True
                        else:
                            logger.warning(
                                f"⚠️ Safety Gate: Token encontrado em campo genérico, mas não aceito como campo XAT real: {field_info['selector']}"
                            )
                    elif field_info['found']:
                        logger.debug(
                            f"  [Check #{check_count}, {elapsed}s] Campo: {field_info['selector']} | "
                            f"Token: {field_info['tokenLength']} chars | "
                            f"Widget: {'SIM' if field_info['hasWidget'] else 'NÃO'}"
                        )
                
            except Exception as e:
                logger.debug(f"  [Safety Gate - Check #{check_count}] Erro durante validação (continuando): {e}")
            
            await page.wait_for_timeout(1000)

        logger.warning(
            f"❌ Safety Gate: Timeout de {timeout_seconds}s atingido após {check_count} verificações. "
            f"Nenhum token válido com widget visível foi encontrado nos campos do XAT reCAPTCHA."
        )
        
        # Tirar screenshot do estado final para debug
        try:
            screenshot_path = "safety_gate_timeout.png"
            await page.screenshot(path=screenshot_path)
            logger.info(f"📸 Screenshot do Safety Gate timeout salva em {screenshot_path}")
            
            html_path = "safety_gate_timeout.html"
            html_content = await page.content()
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            logger.info(f"📝 HTML do Safety Gate timeout salva em {html_path}")
            
            # Também salvar informações dos campos encontrados
            fields_debug = await page.evaluate("""
                () => {
                    const allInputs = document.querySelectorAll('input[name*="captcha"], input[name*="recaptcha"], input[name*="cf-turnstile"], textarea[name*="captcha"], textarea[name*="recaptcha"], textarea[name*="cf-turnstile"]');
                    return Array.from(allInputs).map(el => ({
                        tag: el.tagName,
                        name: el.name,
                        type: el.type,
                        valueLength: el.value ? el.value.length : 0,
                        visible: el.offsetParent !== null
                    }));
                }
            """)
            logger.warning(f"🔍 Campos de captcha encontrados na página: {fields_debug}")
            
        except Exception as e:
            logger.warning(f"⚠️ Erro ao salvar debug info: {e}")
        
        return False

    async def _humanize_turnstile_click(self, page: Page) -> bool:
        """
        Clique Humanizado no Widget: Move mouse de forma curva até o centro do widget Turnstile.
        """
        try:
            logger.info("🖱️ Humanizando clique no widget Turnstile...")

            # Obter bounding box do widget Turnstile
            bbox = await page.evaluate("""
                () => {
                    const iframe = document.querySelector('iframe[src*="challenges.cloudflare.com"], iframe[src*="turnstile"], iframe[src*="captcha"]');
                    if (iframe) {
                        const rect = iframe.getBoundingClientRect();
                        return {
                            x: rect.left,
                            y: rect.top,
                            width: rect.width,
                            height: rect.height
                        };
                    }
                    return null;
                }
            """)

            if not bbox:
                logger.warning("⚠️ Widget Turnstile não encontrado para clique humanizado")
                return False

            # Calcular centro do widget
            center_x = bbox['x'] + bbox['width'] / 2
            center_y = bbox['y'] + bbox['height'] / 2

            logger.debug(f"📍 Centro do widget Turnstile: ({center_x}, {center_y})")

            # Movimento de mouse curvo/aleatório até o centro
            # Começar de uma posição aleatória na tela
            start_x = random.randint(100, 500)
            start_y = random.randint(100, 400)

            # Mover para posição inicial
            await page.mouse.move(start_x, start_y, steps=random.randint(8, 12))

            # Pausa antes do movimento final
            await page.wait_for_timeout(random.randint(300, 700))

            # Movimento curvo até o centro do widget
            await page.mouse.move(center_x, center_y, steps=random.randint(12, 18))

            # Pequena pausa antes do clique
            await page.wait_for_timeout(random.randint(200, 500))

            # Clique humanizado
            await page.mouse.click(center_x, center_y, button='left', delay=random.randint(50, 150))

            logger.info("✅ Clique humanizado executado no widget Turnstile")
            return True

        except Exception as e:
            logger.warning(f"⚠️ Erro no clique humanizado do Turnstile: {e}")
            return False

    async def _inject_captcha_token(self, page: Page, token: str) -> None:
        """
        FEATURE 2: Sincronização do Captcha (Bot)
        Injeta o token do solver nos campos escondidos e invoca callbacks JavaScript.
        Garante que window.cf_callback é notificado ANTES da submissão do formulário.
        """
        callback_stats = await page.evaluate(
            """
            (token) => {
                window.__playwright_turnstile_callback_fired = false;

                const dispatchChange = (element) => {
                    if (!element) return;
                    element.value = token;
                    element.setAttribute('value', token);
                    element.dispatchEvent(new Event('input', { bubbles: true }));
                    element.dispatchEvent(new Event('change', { bubbles: true }));
                    element.dispatchEvent(new Event('blur', { bubbles: true }));
                };

                const findOrCreateField = (selector) => {
                    let element = document.querySelector(selector);
                    if (element) {
                        return { element, created: false };
                    }
                    const tag = selector.includes('textarea') ? 'textarea' : 'input';
                    const name = selector.includes('cf-turnstile-response') ? 'cf-turnstile-response' : 'g-recaptcha-response';
                    const container = document.querySelector('#registercap') || document.querySelector('form#regform') || document.body;
                    element = document.createElement(tag);
                    element.setAttribute('name', name);
                    element.style.display = 'none';
                    container.appendChild(element);
                    return { element, created: true };
                };

                const selectors = [
                    '#registercap textarea[name="cf-turnstile-response"]',
                    '#registercap input[name="cf-turnstile-response"]',
                    '#registercap textarea[name="g-recaptcha-response"]',
                    '#registercap input[name="g-recaptcha-response"]',
                    'form#regform textarea[name="cf-turnstile-response"]',
                    'form#regform input[name="cf-turnstile-response"]',
                    'form#regform textarea[name="g-recaptcha-response"]',
                    'form#regform input[name="g-recaptcha-response"]',
                    'textarea[name="cf-turnstile-response"]',
                    'input[name="cf-turnstile-response"]',
                    'textarea[name="g-recaptcha-response"]',
                    'input[name="g-recaptcha-response"]'
                ];

                const injected = [];
                selectors.forEach(selector => {
                    const { element, created } = findOrCreateField(selector);
                    dispatchChange(element);
                    injected.push({ selector, created });
                });

                const ensureRealXatField = () => {
                    const realSelectors = [
                        '#registercap input[name="cf-turnstile-response"]',
                        '#registercap textarea[name="cf-turnstile-response"]',
                        'form#regform input[name="cf-turnstile-response"]',
                        'form#regform textarea[name="cf-turnstile-response"]'
                    ];

                    for (const selector of realSelectors) {
                        const field = document.querySelector(selector);
                        if (field && field.value && field.value.length > 30) {
                            return true;
                        }
                    }

                    const targetContainer = document.querySelector('#registercap') || document.querySelector('form#regform');
                    if (!targetContainer) {
                        return false;
                    }

                    let realField = targetContainer.querySelector('input[name="cf-turnstile-response"], textarea[name="cf-turnstile-response"]');
                    if (!realField) {
                        realField = document.createElement('input');
                        realField.setAttribute('type', 'hidden');
                        realField.setAttribute('name', 'cf-turnstile-response');
                        realField.style.display = 'none';
                        targetContainer.appendChild(realField);
                    }
                    dispatchChange(realField);
                    return true;
                };

                if (!ensureRealXatField()) {
                    console.log('[Playwright] Aviso: não foi possível injetar token em campo real do XAT');
                }

                const invokeCallback = (callbackName) => {
                    if (!callbackName) return false;
                    const callback = window[callbackName];
                    if (typeof callback === 'function') {
                        callbackCount += 1;
                        callbackNames.push(callbackName);
                        try {
                            callback(token);
                            window.__playwright_turnstile_callback_fired = true;
                            callbackInvokedCount += 1;
                            return true;
                        } catch (e) {
                            window.__playwright_turnstile_callback_fired = true;
                            callbackInvokedCount += 1;
                            console.log('[Playwright] callback falhou:', callbackName, e);
                            return false;
                        }
                    }
                    return false;
                };

                const invokeCallbackFunction = (callbackFn) => {
                    if (typeof callbackFn !== 'function') return false;
                    callbackCount += 1;
                    callbackNames.push(callbackFn.name || 'anonymous');
                    try {
                        callbackFn(token);
                        window.__playwright_turnstile_callback_fired = true;
                        callbackInvokedCount += 1;
                        return true;
                    } catch (e) {
                        window.__playwright_turnstile_callback_fired = true;
                        callbackInvokedCount += 1;
                        console.log('[Playwright] callback function falhou:', e);
                        return false;
                    }
                };

                // ⚠️ Armazena token em múltiplas variáveis para compatibilidade máxima
                window.cf_token = token;
                window.turnstileToken = token;
                window.grecaptchaResponse = token;
                window.recaptchaResponse = token;
                window.xatCaptchaToken = token;

                let cfCallbackInvoked = false;
                // ⚠️ FEATURE 2: Notifica o xat via window.cf_callback() ANTES de qualquer outro evento
                // Isto garante que o JavaScript do xat sabe que o token está pronto
                if (typeof window.cf_callback === 'function') {
                    try {
                        window.cf_callback(token);
                        cfCallbackInvoked = true;
                        console.log('[Playwright] cf_callback invocado com sucesso');
                    } catch (e) {
                        cfCallbackInvoked = true;
                        console.log('[Playwright] cf_callback falhou:', e);
                    }
                }

                let callbackCount = 0;
                let callbackInvokedCount = 0;
                let dispatcherInvoked = false;
                const callbackNames = [];

                // 🔥 BUSCA PROFUNDA DE CALLBACKS - Procura em múltiplos locais
                const deepSearchCallbacks = () => {
                    const potentialCallbacks = [
                        // Callbacks padrão do Turnstile
                        window.__cf_turnstile_config?.callback,
                        window.__cf_turnstile_config?.['data-callback'],
                        window.__turnstile_config?.callback,
                        window.__turnstile_config?.['data-callback'],
                        // Callbacks customizados do XAT
                        window.__xat_callbacks?.turnstile,
                        window.__xat_callbacks?.captcha,
                        window.onTurnstileComplete,
                        window.onCaptchaComplete,
                        window.turnstileOnComplete,
                        // Via render
                        window.__playwright_turnstile_callback,
                        window.__playwright_turnstile_ready_callback,
                        // Busca dinâmica em todos os on*** handlers
                        ...Object.keys(window)
                            .filter(k => k.startsWith('on') && typeof window[k] === 'function')
                            .map(k => window[k])
                    ];

                    for (const cb of potentialCallbacks) {
                        if (typeof cb === 'function') {
                            try {
                                console.log('[Playwright] Invocando callback encontrado via busca profunda');
                                cb(token);
                                return true;
                            } catch (e) {
                                console.log('[Playwright] Callback de busca profunda falhou:', e);
                            }
                        }
                    }
                    return false;
                };

                // Invoca callbacks de elementos que têm data-callback
                document.querySelectorAll('[data-callback], [data-recaptcha-callback], [data-sitekey]').forEach(element => {
                    const callbackName = element.getAttribute('data-callback') || element.getAttribute('data-recaptcha-callback');
                    if (callbackName) {
                        console.log('[Playwright] Disparando callback do Turnstile:', callbackName);
                        if (invokeCallback(callbackName)) {
                            dispatcherInvoked = true;
                        }
                    }
                });

                // Callback de config do Turnstile
                if (window.__cf_turnstile_config && window.__cf_turnstile_config.sitekey) {
                    const cfgCallback = window.__cf_turnstile_config.callback || window.__cf_turnstile_config['data-callback'];
                    if (typeof cfgCallback === 'function') {
                        console.log('[Playwright] Disparando callback de configuração do Turnstile');
                        if (invokeCallbackFunction(cfgCallback)) {
                            dispatcherInvoked = true;
                        }
                    } else {
                        console.log('[Playwright] Disparando callback nomeado de configuração do Turnstile:', cfgCallback);
                        if (invokeCallback(cfgCallback)) {
                            dispatcherInvoked = true;
                        }
                    }
                }

                // Se nenhum callback foi encontrado, fazer busca profunda
                if (callbackCount === 0) {
                    console.log('[Playwright] Nenhum callback padrão encontrado, iniciando busca profunda...');
                    if (deepSearchCallbacks()) {
                        dispatcherInvoked = true;
                        callbackCount += 1;
                        callbackInvokedCount += 1;
                        callbackNames.push('deepSearch');
                    }
                }

                const externalCallbackElements = Array.from(document.querySelectorAll('[data-callback], [data-recaptcha-callback], [data-sitekey]'));
                if (externalCallbackElements.length === 0) {
                    console.log('[Playwright] Nenhum callback data-callback encontrado no Turnstile');
                }

                let turnstileExecuteInvoked = false;
                // 🔥 TRIGGER CALLBACK: Tentar executar turnstile.execute() se disponível
                if (window.turnstile && typeof window.turnstile.execute === 'function') {
                    try {
                        console.log('[Playwright] Executando turnstile.execute()');
                        window.turnstile.execute();
                        window.__playwright_turnstile_callback_fired = true;
                        turnstileExecuteInvoked = true;
                    } catch (e) {
                        console.log('[Playwright] turnstile.execute() falhou:', e);
                    }
                }

                return {
                    callbackCount,
                    callbackInvokedCount,
                    callbackNames,
                    cfCallbackInvoked,
                    dispatcherInvoked,
                    turnstileExecuteInvoked,
                    callbackFired: !!window.__playwright_turnstile_callback_fired
                };

                // Não clicar no widget após injetar o token; a injeção + callback é o passo final antes do registro.
            }
            """,
            token
        )

        logger.info(
            f"🔍 Callbacks do Turnstile: found={callback_stats.get('callbackCount')} "
            f"invoked={callback_stats.get('callbackInvokedCount')} "
            f"names={callback_stats.get('callbackNames')} "
            f"cf_callback={callback_stats.get('cfCallbackInvoked')} "
            f"dispatch={callback_stats.get('dispatcherInvoked')} "
            f"turnstile_execute={callback_stats.get('turnstileExecuteInvoked')} "
            f"callbackFired={callback_stats.get('callbackFired')}"
        )
        
        # ✅ VERIFICAÇÃO CRÍTICA: Confirmar que o token foi injetado em campo REAL do XAT
        logger.info("🔍 Verificando injeção de token em campos específicos do XAT...")
        try:
            injected_info = await page.evaluate("""
                () => {
                    // Campos específicos do XAT reCAPTCHA (em ordem de importância)
                    const xat_fields = [
                        { selector: '#registercap input[name="cf-turnstile-response"]', type: 'Cloudflare Turnstile (input, registercap)' },
                        { selector: '#registercap textarea[name="cf-turnstile-response"]', type: 'Cloudflare Turnstile (textarea, registercap)' },
                        { selector: '#registercap input[name="g-recaptcha-response"]', type: 'Google reCAPTCHA (input, registercap)' },
                        { selector: '#registercap textarea[name="g-recaptcha-response"]', type: 'Google reCAPTCHA (textarea, registercap)' },
                        { selector: 'form#regform input[name="cf-turnstile-response"]', type: 'Cloudflare Turnstile (input, regform)' },
                        { selector: 'form#regform textarea[name="cf-turnstile-response"]', type: 'Cloudflare Turnstile (textarea, regform)' },
                        { selector: 'form#regform input[name="g-recaptcha-response"]', type: 'Google reCAPTCHA (input, regform)' },
                        { selector: 'form#regform textarea[name="g-recaptcha-response"]', type: 'Google reCAPTCHA (textarea, regform)' },
                        { selector: 'input[name="cf-turnstile-response"]', type: 'Cloudflare Turnstile (input)' },
                        { selector: 'textarea[name="cf-turnstile-response"]', type: 'Cloudflare Turnstile (textarea)' },
                        { selector: 'input[name="g-recaptcha-response"]', type: 'Google reCAPTCHA (input)' },
                        { selector: 'textarea[name="g-recaptcha-response"]', type: 'Google reCAPTCHA (textarea)' }
                    ];
                    
                    const results = [];
                    
                    for (const fieldSpec of xat_fields) {
                        const field = document.querySelector(fieldSpec.selector);
                        if (field && field.value && field.value.length > 30) {
                            // Verificar se há um widget associado
                            const hasWidget = !!document.querySelector('iframe[src*="challenges.cloudflare.com"], iframe[src*="turnstile"], iframe[src*="recaptcha"], [data-sitekey], .cf-turnstile, .g-recaptcha');
                            
                            results.push({
                                selector: fieldSpec.selector,
                                type: fieldSpec.type,
                                found: true,
                                tokenLength: field.value.length,
                                preview: field.value.substring(0, 40) + '...',
                                hasWidget: hasWidget,
                                fieldVisible: field.offsetParent !== null,
                                isInFrame: field.ownerDocument !== window.document ? 'SIM' : 'NÃO'
                            });
                        } else if (field) {
                            results.push({
                                selector: fieldSpec.selector,
                                type: fieldSpec.type,
                                found: true,
                                tokenLength: field.value ? field.value.length : 0,
                                hasWidget: false,
                                fieldVisible: field.offsetParent !== null,
                                note: 'Campo vazio ou token muito pequeno'
                            });
                        }
                    }
                    
                    return results;
                }
            """)
            
            # Logar cada campo encontrado
            if injected_info:
                for field_info in injected_info:
                    if field_info.get('found'):
                        if field_info.get('tokenLength', 0) > 30 and field_info.get('hasWidget'):
                            logger.info(
                                f"✅ TOKEN INJETADO COM SUCESSO: "
                                f"Campo=[{field_info['selector']}] | "
                                f"Tipo=[{field_info['type']}] | "
                                f"Tamanho=[{field_info['tokenLength']} chars] | "
                                f"Widget Visível=[{'SIM' if field_info.get('hasWidget') else 'NÃO'}] | "
                                f"Campo Visível=[{'SIM' if field_info.get('fieldVisible') else 'NÃO'}] | "
                                f"Dentro de iframe=[{field_info.get('isInFrame', 'NÃO')}]"
                            )
                        else:
                            logger.warning(
                                f"⚠️ Campo encontrado mas INCOMPLETO: "
                                f"Campo=[{field_info['selector']}] | "
                                f"Tamanho=[{field_info.get('tokenLength', 0)} chars] | "
                                f"Nota=[{field_info.get('note', 'N/A')}]"
                            )
            else:
                logger.warning("⚠️ Nenhum campo de captcha do XAT foi encontrado na página após injeção!")
                
        except Exception as e:
            logger.debug(f"⚠️ Erro ao verificar injeção de token: {e}")

        # ⚠️ FEATURE 2: Aguarda um momento MAIOR para garantir que o callback foi processado
        # Isto dá tempo para o JavaScript do xat processar a notificação cf_callback/Turnstile
        # Aumentado de 3.5s para 10s para dar ao Turnstile tempo suficiente de processar o token
        # e evitar o erro "The captcha verification was not successful"
        wait_time = random.uniform(8, 15)
        await asyncio.sleep(wait_time)
        logger.info(f"✅ Aguardado {wait_time:.1f}s após injetar captcha para sincronizar callbacks do Turnstile")


    async def _inject_captcha_token_if_missing(self, page: Page) -> None:
        """Garante que o token de captcha está presente antes de submeter o formulário."""
        token_present = await page.evaluate(
            """
            () => {
                const selectors = [
                    '#registercap textarea[name="cf-turnstile-response"]',
                    '#registercap input[name="cf-turnstile-response"]',
                    '#registercap textarea[name="g-recaptcha-response"]',
                    '#registercap input[name="g-recaptcha-response"]',
                    'form#regform textarea[name="cf-turnstile-response"]',
                    'form#regform input[name="cf-turnstile-response"]',
                    'form#regform textarea[name="g-recaptcha-response"]',
                    'form#regform input[name="g-recaptcha-response"]'
                ];
                return selectors.some(selector => {
                    const field = document.querySelector(selector);
                    return field && field.value && field.value.length > 30;
                });
            }
            """
        )

        if not token_present:
            # Garantir que o formulário de registro já contém o campo real antes de tentar resolver novamente
            try:
                await page.wait_for_selector('#registercap, form#regform', timeout=7000)
            except Exception:
                logger.debug('⚠️ registercap/form#regform não encontrado antes de injetar token faltante')

            sitekey = await self._extract_sitekey_from_full_page_content(page)
            if sitekey:
                page_url = page.url
                user_agent = await page.evaluate("navigator.userAgent")
                token = self._resolver_recaptcha(sitekey, page_url, user_agent=user_agent)
                if token:
                    await self._inject_captcha_token(page, token)
                    logger.info("✅ Token de captcha injetado antes do envio do form")

    def _get_requests_proxy_config(self) -> Optional[Dict[str, str]]:
        """Retorna configuração de proxy compatível com requests, a partir do proxy atual do Playwright."""
        if not self.current_proxy:
            return None

        proxy_clean = self.current_proxy.replace('http://', '').replace('https://', '')
        if '@' in proxy_clean:
            creds, host_port = proxy_clean.rsplit('@', 1)
            if ':' not in host_port:
                return None
            username, password = creds.split(':', 1)
            host, port = host_port.rsplit(':', 1)
            server = f'http://{username}:{password}@{host}:{port}'
        else:
            if ':' not in proxy_clean:
                return None
            host, port = proxy_clean.rsplit(':', 1)
            server = f'http://{host}:{port}'

        return {
            'http': server,
            'https': server
        }

    def _normalize_captcha_pageurl(self, page_url: str) -> str:
        """Normaliza pageurl para enviar ao solver, removendo parâmetros sensíveis."""
        try:
            # Sempre retornar a URL estrita para o 2Captcha
            return "https://xat.com/login?mode=1"
        except Exception:
            return page_url

    def _resolver_recaptcha(self, sitekey: str, page_url: str, payload: Optional[Dict[str, str]] = None, proxies: Optional[Dict[str, str]] = None, user_agent: Optional[str] = None) -> Optional[str]:
        """
        Resolve reCAPTCHA/Turnstile usando 2captcha com Proxy-On e User-Agent synchronization.
        Passa as credenciais do proxy atual e o mesmo User-Agent do navegador para que o captcha
        seja resolvido com o mesmo IP e fingerprint digital, evitando detecção de validação cruzada.
        """
        provider = self.config['captcha_solver'].get('provider', '2captcha')
        api_key = self.config['captcha_solver'].get('api_key', '')
        api_key = api_key.strip()

        if provider != '2captcha':
            logger.warning(f"⚠️ Provedor de captcha não suportado: {provider}")
            return None

        if not api_key:
            logger.warning("⚠️ chave API de captcha não configurada em config.json")
            return None

        try:
            method = 'turnstile' if sitekey.startswith('0x') else 'userrecaptcha'
            normalized_pageurl = self._normalize_captcha_pageurl(page_url)
            logger.info(f"🔐 Enviando desafio reCAPTCHA/Turnstile para 2captcha (method={method}, sitekey={sitekey[:20]}..., pageurl={normalized_pageurl})")

            params = {
                'key': api_key,
                'method': method,
                'pageurl': normalized_pageurl,
                'json': 1
            }

            # ⚠️ FEATURE: 2Captcha Proxy-On + User-Agent Synchronization
            # Para resolver o erro "The captcha verification was not successful"
            # O xat detecta quando o IP/fingerprint do solver != IP/fingerprint do navegador
            if self.current_proxy and '@' in self.current_proxy:
                try:
                    # ⚠️ Usar credenciais específicas do Webshare BR-rotate conforme solicitado
                    # Isso garante que o 2Captcha resolva o captcha com IP brasileiro
                    webshare_proxy = "cqgsjjoe-BR-rotate:syeim3ngqut4@p.webshare.io:80"
                    params['proxy'] = webshare_proxy
                    params['proxytype'] = 'HTTP'
                    logger.info(f"🔒 2Captcha Proxy-On ativado: usando proxy brasileiro {webshare_proxy} para resolver captcha")
                except Exception as proxy_error:
                    logger.warning(f"⚠️ Erro ao configurar 2Captcha Proxy-On: {proxy_error}")
            else:
                logger.info("ℹ️ 2Captcha sem Proxy-On (proxy atual não disponível ou não autenticado)")

            # ⚠️ FEATURE: User-Agent Synchronization
            # Enviar o mesmo User-Agent do navegador para o 2Captcha
            # Se não fornecido, usar um padrão compatível
            if user_agent:
                params['userAgent'] = user_agent
                logger.info(f"🎭 User-Agent synchronization: enviando mesmo UA do navegador para 2Captcha")
            else:
                # User-Agent padrão compatível com IPs brasileiros (Chrome 131)
                default_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                params['userAgent'] = default_ua
                logger.info(f"🎭 User-Agent padrão: {default_ua[:50]}...")

            if method == 'turnstile':
                params['sitekey'] = sitekey.strip()
                # Forçar action padrão para xat login se não houver action explícito
                action = payload.get('action') if payload else None
                if not action and 'xat.com' in normalized_pageurl:
                    action = 'login'
                if action and action.strip():
                    params['data[action]'] = action.strip()
                extra_data = payload.get('data') if payload else None
                if extra_data and extra_data.strip():
                    params['data'] = extra_data.strip()

                # Log detalhado dos parâmetros sendo enviados
                logger.info(f"🔍 Parâmetros 2Captcha: key=***, method={method}, sitekey={params['sitekey']}, pageurl={normalized_pageurl}")
                if 'proxy' in params:
                    logger.info(f"🔍 proxy={params['proxy']}, proxytype={params['proxytype']}")
                if 'data[action]' in params:
                    logger.info(f"🔍 data[action]={params['data[action]']}")
            else:
                params['googlekey'] = sitekey
                if payload:
                    action = payload.get('action')
                    extra_data = payload.get('data')
                    if action:
                        params['data[action]'] = action
                    if extra_data:
                        params['data'] = extra_data

            response = requests.post('http://2captcha.com/in.php', data=params, timeout=90, proxies=proxies)
            data = response.json()
            if data.get('status') != 1:
                logger.warning(f"⚠️ 2captcha in.php falhou: {data.get('request')}")
                return None

            request_id = data.get('request')
            for _ in range(24):
                time.sleep(5)
                status_resp = requests.get(
                    'http://2captcha.com/res.php',
                    params={
                        'key': api_key,
                        'action': 'get',
                        'id': request_id,
                        'json': 1
                    },
                    timeout=90,
                    proxies=proxies
                )
                status_data = status_resp.json()
                if status_data.get('status') == 1:
                    logger.info("✅ Retorno de reCAPTCHA recebido")
                    return status_data.get('request')
                if status_data.get('request') not in ['CAPCHA_NOT_READY', 'CAPTCHA_NOT_READY']:
                    logger.warning(f"⚠️ 2captcha erro: {status_data.get('request')}")
                    return None

            logger.warning("⚠️ Tempo esgotado aguardando 2captcha")
            return None

        except Exception as e:
            logger.warning(f"⚠️ Erro no solver de reCAPTCHA: {e}")
            return None

    async def _verify_registration_result(self, page: Page, username: str, email: str) -> bool:
        """Verifica se a conta foi criada com sucesso"""
        try:
            content = await page.content()
            try:
                text_content = await page.text_content('body')
            except:
                text_content = content

            # Verificar indicadores de sucesso
            success_indicators = [
                'conta criada',
                'account created',
                'success',
                'sucesso',
                'welcome',
                'bem-vindo',
                f'{username}'
            ]

            # Verificar indicadores de erro
            error_indicators = [
                'error',
                'erro',
                'failed',
                'falhou',
                'invalid',
                'inválido',
                'already exists',
                'já existe',
                'captcha',
                'verification'
            ]

            success_found = any(indicator.lower() in text_content.lower() for indicator in success_indicators)
            error_found = any(indicator.lower() in text_content.lower() for indicator in error_indicators)

            if success_found and not error_found:
                if any(term in text_content.lower() for term in ['check your email', 'confirm your email', 'verifique seu email', 'confirme seu email']):
                    logger.warning(f"⚠️ Conta parece ter sido aceita, mas requer confirmação de email: {username}")
                    self._log_shadowban(username, email, 'Possível shadowban ou bloqueio silencioso após aceitação do formulário')
                logger.info(f"✅ Conta criada com sucesso: {username}")
                return True
            elif error_found:
                logger.warning(f"⚠️ Erro detectado na criação da conta: {username}")
                # ⚠️ FEATURE 1: Detectar e processar shadowban se houver indicadores
                self._detectar_e_processar_shadowban(username, email, text_content)
                return False
            else:
                logger.warning(f"⚠️ Status da criação indefinido para: {username} - possivel shadowban")
                self._log_shadowban(username, email, 'Status indefinido após submissão de registro')
                if self.proxy_session_enabled and self.current_proxy_base:
                    logger.info("🔄 Renewing proxy session due to undefined status instead of blacklisting base endpoint.")
                    self.proxy_session_restart_pending = True
                else:
                    # ⚠️ FEATURE 1: Forçar blacklist quando status é indefinido (pode ser shadowban silencioso)
                    if self.current_proxy:
                        self._blacklist_current_proxy(f"Status indefinido para {username} - possível shadowban silencioso")
                    self._set_current_proxy(None)
                return False

        except Exception as e:
            logger.error(f"❌ Erro ao verificar resultado: {e}")
            return False

    async def _monitor_submission_result(self, page: Page) -> Optional[str]:
        """Monitora a submissão do formulário para detectar sucesso ou erro imediato."""
        try:
            expected_success = ['welcome', 'home', 'success']
            error_selectors = [
                'div.alert-danger',
                '.alert.alert-danger',
                '.popover-body',
                '#errore-msg',
                '.error',
                '.field-error',
                '.has-error',
                '.error-message'
            ]

            try:
                await page.wait_for_function(
                    """
                    () => {
                        const url = window.location.href.toLowerCase();
                        return url.includes('welcome') || url.includes('home') || url.includes('success');
                    }
                    """,
                    timeout=15000
                )
                logger.info("✅ URL de sucesso detectada após submissão")
                return None
            except Exception:
                pass

            for selector in error_selectors:
                try:
                    const_error = await page.query_selector(selector)
                    if const_error:
                        text = await const_error.text_content()
                        error_text = text.strip() if text else 'sem texto'
                        logger.warning(f"⚠️ Erro visível detectado após submissão ({selector}): {error_text}")
                        return error_text
                except Exception:
                    continue

            current_url = page.url.lower()
            if any(keyword in current_url for keyword in expected_success):
                logger.info("✅ URL de sucesso detectada após submissão")
                return None

            return None
        except Exception as e:
            logger.warning(f"⚠️ Falha ao monitorar submissão: {e}")
            return None



def main():
    """Função principal"""
    try:
        # Criar diretório de dados se não existir
        DATA_DIR.mkdir(exist_ok=True)

        # Carregar configuração
        config_file = CONFIG_DIR / 'config.json'
        config = json.loads(json.dumps(DEFAULT_CONFIG))

        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
            def merge(base, extra):
                for chave, valor in extra.items():
                    if isinstance(valor, dict) and chave in base and isinstance(base[chave], dict):
                        merge(base[chave], valor)
                    else:
                        base[chave] = valor
            merge(config, user_config)

        # Verificar se deve usar browser automation
        # Força Playwright como padrão em 2026 - cloudscraper é inútil contra Turnstile
        if PLAYWRIGHT_AVAILABLE:
            logger.info("🎭 Usando Browser Automation (Playwright) - Método Obrigatório para 2026")
            asyncio.run(run_browser_automation(config))
        else:
            logger.error("❌ Playwright não está disponível. Por favor, execute: pip install playwright")
            sys.exit(1)

    except KeyboardInterrupt:
        logger.warning("\n⚠️ Aplicação encerrada pelo usuário")
        sys.exit(0)

    except Exception as e:
        logger.error(f"❌ Erro fatal: {e}")
        sys.exit(1)


async def run_browser_automation(config: Dict):
    """Executa automação usando Playwright"""
    try:
        # Carregar proxies
        proxies = []
        proxy_file = DATA_DIR / 'proxies.txt'
        if proxy_file.exists():
            with open(proxy_file, 'r', encoding='utf-8') as f:
                proxies = [line.strip() for line in f.readlines() if line.strip() and not line.strip().startswith('#')]

        # Carregar bad proxies
        bad_proxies: Set[str] = set()
        if BAD_PROXIES_FILE.exists():
            with open(BAD_PROXIES_FILE, 'r', encoding='utf-8') as f:
                bad_proxies = {
                    line.split('#', 1)[0].strip()
                    for line in f.readlines()
                    if line.strip() and not line.strip().startswith('#')
                }
        if bad_proxies:
            logger.info(f"🛑 Blacklist de proxies carregada: {len(bad_proxies)} proxy(s) banido(s)")
            logger.info(f"📝 Proxies blacklistados: {', '.join(list(bad_proxies)[:10])}{'...' if len(bad_proxies) > 10 else ''}")
            original_count = len(proxies)
            proxies = [p for p in proxies if p not in bad_proxies]
            logger.info(f"ℹ️ Filtrados {original_count - len(proxies)} proxies blacklistados de bad_proxies.log")
            if proxy_file.exists() and original_count > 0 and not proxies:
                logger.error("❌ Nenhum proxy válido disponível após filtrar bad_proxies.log")
                return

        # Carregar emails
        emails = []
        email_file = DATA_DIR / 'emails.txt'
        if email_file.exists():
            with open(email_file, 'r', encoding='utf-8') as f:
                emails = [line.strip() for line in f.readlines() if line.strip()]

        # Carregar usernames
        usernames = []
        username_file = DATA_DIR / 'usernames.txt'
        if username_file.exists():
            with open(username_file, 'r', encoding='utf-8') as f:
                usernames = [line.strip() for line in f.readlines() if line.strip()]

        if not emails:
            logger.error("❌ Nenhum email encontrado em emails.txt")
            return

        if not usernames:
            logger.error("❌ Nenhum username encontrado em usernames.txt")
            return

        logger.info(f"📧 Processando {len(emails)} emails com {len(usernames)} usernames disponíveis")
        
        # Verificar configuração crítica
        if not config.get('captcha_solver', {}).get('enabled', False):
            logger.error("❌ ERRO CRÍTICO: Solver de captcha NÃO está habilitado no config.json")
            logger.info("🔧 Habilite: config.json -> captcha_solver -> enabled: true")
            return
        
        api_key = config.get('captcha_solver', {}).get('api_key', '')
        if not api_key or api_key == '':
            logger.error("❌ ERRO CRÍTICO: API key de 2captcha NÃO configurada")
            logger.info("🔧 Configure: config.json -> captcha_solver -> api_key: '<sua_chave>'")
            return
        
        logger.info("✅ Configuração crítica OK: Browser Automation + 2Captcha habilitados")

        # Inicializar automação
        async with XATBrowserAutomation(config, proxies, bad_proxies) as automation:
            contas_criadas = 0

            for i, email in enumerate(emails, 1):
                logger.info(f"📧 Processando: {i}/{len(emails)} - {email}")

                # Selecionar username aleatório
                if not usernames:
                    logger.warning("⚠️ usernames esgotados")
                    break

                username = random.choice(usernames)
                usernames.remove(username)  # Remover para não reutilizar

                # Gerar senha
                senha = ''.join(random.choices(string.ascii_letters + string.digits, k=config.get('senha', {}).get('tamanho_min', 8)))

                # Criar conta
                sucesso = await automation.create_account(username, senha, email)

                if sucesso:
                    contas_criadas += 1
                    logger.info(f"✅ Conta criada: {username} | {email}")

                    # Salvar em success_criacao.txt
                    success_file = DATA_DIR / 'success_criacao.txt'
                    with open(success_file, 'a', encoding='utf-8') as f:
                        f.write(f"{username}:{senha}:{email}\n")
                else:
                    logger.warning(f"❌ Falha ao criar conta para {email}")

                # Aguardar entre contas
                if i < len(emails):
                    delay = random.uniform(
                        config['delays'].get('min_entre_contas', 30),
                        config['delays'].get('max_entre_contas', 60)
                    )
                    logger.info(f"⏳ Aguardando {delay:.1f}s antes da próxima conta...")
                    await asyncio.sleep(delay)

            logger.info(f"🎉 Processo concluído! {contas_criadas}/{len(emails)} contas criadas com sucesso")

    except Exception as e:
        logger.error(f"❌ Erro na automação: {e}")


if __name__ == "__main__":
    main()

