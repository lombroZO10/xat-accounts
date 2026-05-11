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
from urllib.parse import urljoin, parse_qs, urlencode, urlparse, urlsplit
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
    from playwright_stealth import Stealth
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    async_playwright = None

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
        "force_proxy": True  # Forçar uso de proxy em todas as requisições
    },
    "browser_automation": {
        "enabled": True,
        "headless": True,
        "proxy_rotation": True,
        "captcha_timeout": 60,
        "page_timeout": 30000
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
        self.current_proxy = None
        self.local_proxy_server = None
        self.local_proxy_thread = None
        self.last_login_block_reason: Optional[str] = None
        self.last_captcha_block_reason: Optional[str] = None
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.6419.46 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:139.0) Gecko/20100101 Firefox/139.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.6490.102 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/126.0.2429.60",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:137.0) Gecko/20100101 Firefox/137.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.6480.88 Safari/537.36"
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
            raise ImportError("❌ Playwright não está instalado. Execute: pip install playwright playwright-stealth")

        logger.info("🎭 XAT Browser Automation inicializado")

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()

    async def initialize(self):
        """Inicializa o navegador Playwright com stealth"""
        try:
            self.playwright = await async_playwright().start()
            attempt = 0
            max_attempts = len(self.proxies) if self.proxies else 3

            while attempt < max_attempts:
                self._choose_next_proxy(exclude_current=(attempt > 0))
                
                # Teste de IP/país antes de criar o contexto
                if not self._test_proxy_ip_and_country(self.current_proxy):
                    logger.warning(f"⚠️ Proxy {self.current_proxy} falhou no teste de IP/país, tentando próximo...")
                    attempt += 1
                    if attempt >= max_attempts:
                        raise Exception("❌ Nenhum proxy passou no teste de IP/país")
                    continue
                
                try:
                    await self._create_browser_context()
                    logger.info("✅ Navegador Playwright inicializado com stealth")
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

        options = [p for p in self.proxies if p != self.current_proxy] if exclude_current else list(self.proxies)
        if not options:
            options = list(self.proxies)

        random.shuffle(options)  # Embaralhar para tentar diferentes proxies

        for proxy_candidate in options:
            # Nota: Webshare é um rotating endpoint, não precisa de sufixo de sessão
            if self._validate_proxy_connectivity(proxy_candidate):
                self.current_proxy = proxy_candidate
                proxy_display = self.current_proxy.replace('http://', '').replace('https://', '')
                if '@' in proxy_display:
                    proxy_display = proxy_display.split('@', 1)[1]
                logger.info(f"🌐 Proxy selecionado e validado: {proxy_display}")
                if self.current_proxy.startswith('socks5://'):
                    logger.info("✅ Proxy SOCKS5 selecionado")
                return self.current_proxy
            else:
                logger.warning(f"🚫 Proxy {proxy_candidate} falhou na validação, tentando próximo...")

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

    def _validate_proxy_connectivity(self, proxy_str: str) -> bool:
        """Valida se o proxy responde a uma requisição rápida antes de abrir o navegador."""
        try:
            proxy_dict = self._build_proxy_dict(proxy_str)
            if not proxy_dict:
                return False

            # Teste rápido com httpbin.org/ip (timeout de 10s)
            response = requests.get(
                'https://httpbin.org/ip',
                proxies=proxy_dict,
                timeout=10,
                verify=False,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"⚠️ Proxy {proxy_str} falhou na validação: {e}")
            return False

    def _test_proxy_ip_and_country(self, proxy_str: str) -> bool:
        """Testa se o proxy está funcionando e se o IP é brasileiro."""
        try:
            proxy_dict = self._build_proxy_dict(proxy_str)
            if not proxy_dict:
                return False

            # Teste com ipify para obter IP
            response = requests.get(
                'https://api.ipify.org?format=json',
                proxies=proxy_dict,
                timeout=10,
                verify=False,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
            if response.status_code != 200:
                return False

            try:
                ip_data = response.json()
                ip = ip_data.get('ip', 'Desconhecido')
                logger.info(f"🌍 IP detectado via proxy: {ip}")
                
                # Teste com ip-api.com para obter país (limite: 45 requisições por minuto)
                country_response = requests.get(
                    f'http://ip-api.com/json/{ip}',
                    timeout=10,
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
                        logger.warning(f"⚠️ IP não é brasileiro. País detectado: {country} ({country_code})")
                        return False
                else:
                    logger.warning(f"⚠️ Não foi possível obter informações do país para {ip}")
                    return True  # Mesmo sem confirmar país, proxy funciona
            except Exception as e:
                logger.warning(f"⚠️ Erro ao processar resposta de IP: {e}")
                return True
        except Exception as e:
            logger.warning(f"⚠️ Proxy {proxy_str} falhou no teste de IP/país: {e}")
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

        self.browser = await self.playwright.chromium.launch(
            headless=self.config['browser_automation'].get('headless', True),
            args=browser_args
        )

        try:
            user_agent = random.choice(self.user_agents)
            viewport = random.choice(self.screen_resolutions)
            self.context = await self.browser.new_context(
                viewport=viewport,
                device_scale_factor=1,
                has_touch=False,
                user_agent=user_agent,
                locale='pt-BR',
                timezone_id='America/Sao_Paulo',
                extra_http_headers=self._build_extra_http_headers(user_agent),
                proxy=proxy_config,
                ignore_https_errors=True
            )
            await self.context.route('**/*', self._block_unnecessary_assets)

            try:
                logger.info("🎭 Aplicando configurações de stealth (playwright-stealth)...")
                stealth_config = Stealth(
                    webgl_vendor_override='Intel Inc.',
                    webgl_renderer_override='Intel(R) Iris(TM) Graphics 6100',
                    navigator_vendor_override='Google Inc.',
                    navigator_platform_override='Win32',
                    navigator_languages_override=('pt-BR', 'pt', 'en-US', 'en'),
                    chrome_app=True,
                    chrome_csi=True,
                    chrome_load_times=True,
                    chrome_runtime=False,
                    hairline=True,
                    iframe_content_window=True,
                    media_codecs=True,
                    navigator_hardware_concurrency=True,
                    navigator_languages=True,
                    navigator_permissions=True,
                    navigator_platform=True,
                    navigator_plugins=True,
                    navigator_webdriver=True,
                    error_prototype=True,
                    sec_ch_ua=True,
                    webgl_vendor=True
                )
                await stealth_config.apply_stealth_async(self.context)
                logger.info("✅ Stealth aplicado com sucesso")
            except AttributeError as ae:
                logger.warning(f"⚠️ Erro AttributeError ao aplicar stealth: {ae}")
                logger.info("💡 Tentando aplicar stealth sem sobrescrita de user_agent...")
                try:
                    stealth_minimal = Stealth(
                        chrome_app=True,
                        navigator_webdriver=True,
                        hairline=True,
                        webgl_vendor=True
                    )
                    await stealth_minimal.apply_stealth_async(self.context)
                    logger.info("✅ Stealth mínimo aplicado com sucesso")
                except Exception as e2:
                    logger.warning(f"⚠️ Stealth mínimo também falhou: {e2}, continuando sem stealth")
            except Exception as e:
                logger.warning(f"⚠️ Erro geral ao aplicar stealth: {e}, continuando sem stealth")

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
        """Seleciona um novo proxy e recria o contexto do navegador."""
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
        if not self.current_proxy:
            return

        if self.current_proxy in self.bad_proxies:
            return

        self.bad_proxies.add(self.current_proxy)
        if self.current_proxy in self.proxies:
            self.proxies.remove(self.current_proxy)

        try:
            BAD_PROXIES_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(BAD_PROXIES_FILE, 'a', encoding='utf-8') as f:
                f.write(f"{self.current_proxy}  # {reason}  [{datetime.now().isoformat()}]\n")
            logger.warning(f"🚫 Proxy blacklistado: {self.current_proxy} ({reason})")
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
        
        if detected_reasons:
            logger.warning(f"🚫 SHADOW BAN DETECTADO para {username}: {', '.join(detected_reasons)}")
            self._log_shadowban(username, email, f"Indicadores: {', '.join(detected_reasons)}")
            
            # ⚠️ Blacklist o IP/proxy atual obrigatoriamente
            if self.current_proxy:
                self._blacklist_current_proxy(f"Shadow Ban detectado para {username} - indicadores: {', '.join(detected_reasons)}")
                logger.info(f"🔄 Rotação de proxy OBRIGATÓRIA: IP será trocado antes do próximo username")
            else:
                logger.warning(f"⚠️ Nenhum proxy atual para blacklistar (possível erro de estado)")
            
            # Resetar proxy para forçar rotação na próxima conta
            self._set_current_proxy(None)
        else:
            # Outros motivos de falha - registrar para análise
            logger.debug(f"❌ Falha ao criar conta {username}, mas não foi detectado shadowban específico")

    async def create_account(self, username: str, password: str, email: str) -> bool:
        """Cria conta XAT usando automação de navegador"""
        try:
            logger.info(f"🎭 Iniciando criação de conta: {username} | {email}")

            max_proxy_retries = self.config['browser_automation'].get('max_proxy_retries', 3)
            await self._clear_browser_context_identity()
            page = await self.context.new_page()
            page.set_default_timeout(self.config['browser_automation'].get('page_timeout', 30000))

            # Passo 1: Obter UserID/k2 com retry de proxy em caso de bloqueio
            user_data = None
            for attempt in range(max_proxy_retries):
                user_data = await self._get_user_data(page)
                if user_data:
                    break

                logger.warning(f"⚠️ Falha ao obter UserID/k2 no attempt {attempt + 1}/{max_proxy_retries}")
                await page.close()
                if attempt == max_proxy_retries - 1:
                    return False
                if not await self._rotate_proxy_and_recreate():
                    return False
                page = await self.context.new_page()
                page.set_default_timeout(self.config['browser_automation'].get('page_timeout', 30000))

            user_id = user_data.get('UserId')
            k2_token = user_data.get('k2')

            await self._random_delay()

            # Passo 2: Acessar página de login com retry de proxy ao detectar bloqueio ou shadowban
            login_success = False
            for attempt in range(max_proxy_retries):
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
                        break
                except CloudflareHardBlockException as e:
                    logger.warning(f"🚫 Cloudflare Hard Block detectado: {e}")
                    # Força rotação imediata de proxy
                    login_success = False
                    await page.close()
                    if attempt == max_proxy_retries - 1:
                        return False
                    if not await self._rotate_proxy_and_recreate():
                        return False
                    page = await self.context.new_page()
                    page.set_default_timeout(self.config['browser_automation'].get('page_timeout', 30000))
                    continue  # Pula para próxima iteração do loop

                if login_success:
                    break

                logger.warning(f"⚠️ Bloqueio na página de login detectado no attempt {attempt + 1}/{max_proxy_retries}")
                await page.close()
                if attempt == max_proxy_retries - 1:
                    return False
                if not await self._rotate_proxy_and_recreate():
                    return False
                page = await self.context.new_page()
                page.set_default_timeout(self.config['browser_automation'].get('page_timeout', 30000))

            if not login_success:
                return False

            # Aguardar carregamento do widget e resolver captcha
            captcha_resolved = False
            for attempt in range(max_proxy_retries):
                try:
                    captcha_resolved = await self._wait_for_captcha_resolution(page)
                    if captcha_resolved:
                        break
                except CloudflareHardBlockException as e:
                    logger.warning(f"🚫 Cloudflare Hard Block detectado durante resolução de captcha: {e}")
                    # Pular diretamente para próximo proxy sem tentar resolver captcha
                    captcha_resolved = False

                if captcha_resolved:
                    break

                logger.warning(f"⚠️ Widget de Turnstile não carregou ou captcha não foi resolvido no attempt {attempt + 1}/{max_proxy_retries}")
                await page.close()
                if attempt == max_proxy_retries - 1:
                    return False
                if not await self._rotate_proxy_and_recreate():
                    return False
                page = await self.context.new_page()
                page.set_default_timeout(self.config['browser_automation'].get('page_timeout', 30000))
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
                    if not login_success:
                        continue
                except CloudflareHardBlockException as e:
                    logger.warning(f"🚫 Cloudflare Hard Block detectado ao re-acessar login: {e}")
                    continue

            if not captcha_resolved:
                reason = self.last_captcha_block_reason or "Falha na resolução do captcha"
                logger.warning(f"⚠️ Captcha não resolvido. Abortando criação de conta. Motivo: {reason}")
                await page.close()
                return False

            # Passo 3: Preencher e submeter formulário
            success = await self._fill_registration_form(page, username, password, email)
            if not success:
                await page.close()
                return False

            # Passo 4: Verificar resultado
            result = await self._verify_registration_result(page, username, email)
            await page.close()

            return result

        except Exception as e:
            logger.error(f"❌ Erro na automação: {e}")
            return False

    async def _get_user_data(self, page: Page) -> Optional[Dict]:
        """Obtém UserID e k2 via auser3.php"""
        try:
            logger.info("🔗 Obtendo UserID/k2 via navegador")

            # Acessar auser3.php (timeout aumentado para proxies residenciais)
            response = await page.goto(self.AUSER_URL, wait_until='networkidle', timeout=45000)
            
            if response and response.status in [403, 503]:
                logger.warning(f"⚠️ Bloqueio detectado ao acessar auser3.php: {response.status}")
                self._blacklist_current_proxy(f"Bloqueio 403/503 em auser3.php")
                return None

            # Extrair conteúdo HTML
            content = await page.content()
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
            response = await page.goto(login_url, wait_until='networkidle', timeout=45000)

            # Aguardar a página intersticial do Cloudflare sumir ("Checking your browser")
            logger.info("⏳ Aguardando 5s para página intersticial Cloudflare carregar/sumir...")
            await page.wait_for_timeout(5000)

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
            token = self._resolver_recaptcha(sitekey, page_url, payload)
            if not token:
                reason = "Solver de captcha não retornou token"
                logger.warning(f"⚠️ {reason}")
                self.last_captcha_block_reason = reason
                self._blacklist_current_proxy(reason)
                return False

            await self._inject_captcha_token(page, token)
            logger.info("✅ Token de captcha injetado na página")
            return True

        except Exception as e:
            logger.warning(f"⚠️ Erro ao resolver captcha: {e}")
            return False

    async def _simulate_human_interaction(self, page: Page) -> None:
        """Simula movimento humano para ajudar o Turnstile a carregar."""
        try:
            await page.mouse.move(100, 100, steps=8)
            await page.wait_for_timeout(200)
            await page.mouse.wheel(0, 500)
            await page.wait_for_timeout(200)
            await page.mouse.move(200, 150, steps=8)
            await page.wait_for_timeout(200)
        except Exception as e:
            logger.debug(f"⚠️ Falha ao simular interação humana: {e}")

    async def _simulate_mouse_movement(self, page: Page) -> None:
        """Simula movimento de mouse aleatório para despertar o Turnstile."""
        try:
            logger.info("🐭 Simulando movimento de mouse aleatório para despertar Turnstile...")
            # Movimento aleatório por 2-3 segundos
            duration = random.randint(2000, 3000)
            start_time = asyncio.get_event_loop().time()
            
            while (asyncio.get_event_loop().time() - start_time) < (duration / 1000):
                # Movimento para posição aleatória na tela
                x = random.randint(50, 1800)
                y = random.randint(50, 900)
                steps = random.randint(5, 15)
                await page.mouse.move(x, y, steps=steps)
                await page.wait_for_timeout(random.randint(100, 300))
                
                # Ocasionalmente scroll
                if random.random() < 0.3:
                    delta_y = random.randint(-200, 200)
                    await page.mouse.wheel(0, delta_y)
                    await page.wait_for_timeout(random.randint(200, 500))
            
            logger.info("✅ Movimento de mouse concluído")
        except Exception as e:
            logger.debug(f"⚠️ Falha ao simular movimento de mouse: {e}")

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

    async def _fill_registration_form(self, page: Page, username: str, password: str, email: str) -> bool:
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
            await self._fill_form_field(page, username_locator, username, "username")
            await self._fill_form_field(page, password_locator, password, "password")
            if password2_locator:
                await self._fill_form_field(page, password2_locator, password, "password2")
            await self._fill_form_field(page, email_locator, email, "email")

            logger.info("✅ Campos preenchidos com sucesso")

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

            # Não clicar mais no widget do Turnstile. Injetar token e seguir direto para o submit.
            await self._inject_captcha_token_if_missing(page)
            logger.info("⏳ Aguardando 3.5s para o Cloudflare processar o token injetado antes de enviar o registro...")
            await page.wait_for_timeout(3500)

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

            # Clicar no botão de submit (é um <a>, não <button>)
            submit_found = False
            submit_selectors = [
                'a#butregister',  # Link de submit (ID real do XAT)
                'button:has-text("register")',
                'button:has-text("Register")',
                'input[type="submit"]',
                'button[type="submit"]',
                '.submit-btn'
            ]
            
            for selector in submit_selectors:
                try:
                    button = page.locator(selector).first
                    if await button.count() > 0:
                        logger.info(f"✅ Botão de submit encontrado: {selector}")
                        try:
                            await button.click()
                        except Exception as click_error:
                            logger.warning(f"⚠️ Clique normal falhou para {selector}: {click_error}. Tentando JS .click()")
                            try:
                                await page.evaluate(f'document.querySelector("{selector}")?.click()')
                                logger.info(f"✅ Clique JS executado em {selector}")
                            except Exception as js_click_error:
                                logger.warning(f"⚠️ Clique JS falhou para {selector}: {js_click_error}")
                                raise
                        submit_found = True
                        break
                except Exception as e:
                    logger.debug(f"  Seletor {selector} não encontrado ou click falhou: {e}")
                    continue

            if not submit_found:
                logger.warning("⚠️ Botão de submit não foi encontrado")
                # Último fallback: tentar clicar diretamente no link
                try:
                    await page.click('a#butregister', force=True)
                    logger.info("✅ Botão de submit clicado via fallback force=True")
                    submit_found = True
                except Exception as e:
                    logger.warning(f"⚠️ Fallback do submit também falhou: {e}. Tentando JS .click() no link direto")
                    try:
                        await page.evaluate('document.querySelector("a#butregister")?.click()')
                        logger.info("✅ Clique JS executado em a#butregister")
                        submit_found = True
                    except Exception as js_error:
                        logger.warning(f"⚠️ Clique JS em a#butregister falhou: {js_error}")

            # Esperar um pouco após o clique para o XAT processar o registro
            logger.info("⏳ Aguardando 3s após o clique para a mensagem final aparecer...")
            await page.wait_for_timeout(3000)

            # Captura de diagnóstico após o submit, especialmente útil quando o bot sai cedo demais
            screenshot_path = f"post_submit_{username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            try:
                await page.screenshot(path=screenshot_path, full_page=True)
                logger.info(f"📸 Screenshot pós-submit salva em {screenshot_path}")
            except Exception as e:
                logger.warning(f"⚠️ Falha ao salvar screenshot pós-submit: {e}")

            await page.wait_for_timeout(2000)
            await page.wait_for_load_state('networkidle', timeout=15000)
            error_message = await self._monitor_submission_result(page)
            if error_message:
                screenshot_path = f"erro_submit_{username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                try:
                    await page.screenshot(path=screenshot_path, full_page=True)
                    logger.info(f"📸 Screenshot de erro pós-submit salva em {screenshot_path}")
                except Exception as e:
                    logger.warning(f"⚠️ Falha ao salvar screenshot de erro pós-submit: {e}")
                logger.warning(f"⚠️ Detecção de erro após submissão: {error_message}")

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

    async def _wait_for_registration_fields(self, page: Page, timeout: int = 25000) -> Optional[Locator]:
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
        """Preenche um campo de formulário com clique forçado e tipagem simulada."""
        try:
            logger.info(f"📝 Preenchendo {field_name}...")
            
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
            
            # Digitar com delay simulado
            for char in value:
                await locator.type(char, delay=random.randint(delay - 40, delay + 40))
            
            await page.wait_for_timeout(300)
            logger.info(f"✅ {field_name} preenchido com sucesso")
            
        except Exception as e:
            logger.warning(f"⚠️ Erro ao preencher {field_name}: {e}")
            # Tentar alternativa com fill direto
            try:
                await locator.fill(value)
                logger.info(f"✅ {field_name} preenchido via fill (alternativa)")
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
        if 'Edg/' in user_agent or 'Edge/' in user_agent:
            brand = '"Chromium";v="140", "Microsoft Edge";v="140", ";Not A Brand";v="99"'
        elif 'Firefox/' in user_agent:
            brand = '"Mozilla";v="135", "Firefox";v="135", ";Not A Brand";v="99"'
        else:
            brand = '"Chromium";v="140", "Google Chrome";v="140", ";Not A Brand";v="99"'

        platform = '"Windows"' if 'Windows' in user_agent else '"Linux"'

        return {
            'sec-ch-ua': brand,
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': platform
        }

    async def _inject_captcha_token(self, page: Page, token: str) -> None:
        """
        FEATURE 2: Sincronização do Captcha (Bot)
        Injeta o token do solver nos campos escondidos e invoca callbacks JavaScript.
        Garante que window.cf_callback é notificado ANTES da submissão do formulário.
        """
        await page.evaluate(
            """
            (token) => {
                const dispatchChange = (element) => {
                    if (!element) return;
                    element.value = token;
                    element.setAttribute('value', token);
                    element.dispatchEvent(new Event('input', { bubbles: true }));
                    element.dispatchEvent(new Event('change', { bubbles: true }));
                    element.dispatchEvent(new Event('blur', { bubbles: true }));
                };

                const selectors = [
                    'textarea[name="cf-turnstile-response"]',
                    'input[name="cf-turnstile-response"]',
                    'textarea[name="g-recaptcha-response"]',
                    'input[name="g-recaptcha-response"]'
                ];

                selectors.forEach(selector => {
                    let element = document.querySelector(selector);
                    if (!element) {
                        const tag = selector.startsWith('textarea') ? 'textarea' : 'input';
                        element = document.createElement(tag);
                        element.setAttribute('name', selector.includes('cf-turnstile-response') ? 'cf-turnstile-response' : 'g-recaptcha-response');
                        element.style.display = 'none';
                        document.body.appendChild(element);
                    }
                    dispatchChange(element);
                });

                const invokeCallback = (callbackName) => {
                    if (!callbackName) return;
                    const callback = window[callbackName];
                    if (typeof callback === 'function') {
                        try {
                            callback(token);
                        } catch (e) {}
                    }
                };

                // ⚠️ Armazena token em múltiplas variáveis para compatibilidade máxima
                window.cf_token = token;
                window.turnstileToken = token;
                window.grecaptchaResponse = token;
                window.recaptchaResponse = token;
                window.xatCaptchaToken = token;

                // ⚠️ FEATURE 2: Notifica o xat via window.cf_callback() ANTES de qualquer outro evento
                // Isto garante que o JavaScript do xat sabe que o token está pronto
                if (typeof window.cf_callback === 'function') {
                    try {
                        window.cf_callback(token);
                        console.log('[Playwright] cf_callback invocado com sucesso');
                    } catch (e) {
                        console.log('[Playwright] cf_callback falhou:', e);
                    }
                }

                // Dispatcher de token do Playwright
                if (typeof window.__playwright_dispatch_turnstile_token === 'function') {
                    try {
                        window.__playwright_dispatch_turnstile_token(token);
                    } catch (e) {}
                }

                // Invoca callbacks de elementos que têm data-callback
                document.querySelectorAll('[data-callback], [data-recaptcha-callback], [data-sitekey]').forEach(element => {
                    const callbackName = element.getAttribute('data-callback') || element.getAttribute('data-recaptcha-callback');
                    invokeCallback(callbackName);
                });

                // Callback de config do Turnstile
                if (window.__cf_turnstile_config && window.__cf_turnstile_config.sitekey) {
                    invokeCallback(window.__cf_turnstile_config.callback || window.__cf_turnstile_config['data-callback']);
                }

                // Não clicar no widget após injetar o token; a injeção + callback é o passo final antes do registro.
            }
            """,
            token
        )
        
        # ⚠️ FEATURE 2: Aguarda um momento maior para garantir que o callback foi processado
        # Isto dá tempo para o JavaScript do xat processar a notificação cf_callback/Turnstile
        await page.wait_for_timeout(3500)
        logger.debug("✅ Aguardado 3500ms para sincronizar callbacks do captcha")


    async def _inject_captcha_token_if_missing(self, page: Page) -> None:
        """Garante que o token de captcha está presente antes de submeter o formulário."""
        token_field = await page.query_selector('textarea[name="cf-turnstile-response"], input[name="cf-turnstile-response"], textarea[name="g-recaptcha-response"], input[name="g-recaptcha-response"]')
        if not token_field:
            sitekey = await self._extract_sitekey_from_full_page_content(page)
            if sitekey:
                page_url = page.url
                token = self._resolver_recaptcha(sitekey, page_url)
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

    def _resolver_recaptcha(self, sitekey: str, page_url: str, payload: Optional[Dict[str, str]] = None, proxies: Optional[Dict[str, str]] = None) -> Optional[str]:
        """Resolve reCAPTCHA/Turnstile usando 2captcha."""
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
                if 'data[action]' in params:
                    logger.info(f"🔍 data[action]={params['data[action]']}")
                if 'data' in params:
                    logger.info(f"🔍 data={params['data']}")
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

    async def _random_delay(self):
        """Aguarda delay aleatório entre ações"""
        min_delay = self.config['delays'].get('min_entre_requisicoes', 5)
        max_delay = self.config['delays'].get('max_entre_requisicoes', 15)
        delay = random.uniform(min_delay, max_delay)
        logger.info(f"⏳ Aguardando {delay:.1f}s...")
        await asyncio.sleep(delay)


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

