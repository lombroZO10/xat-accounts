#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin, parse_qs, urlparse
from bs4 import BeautifulSoup

# Playwright imports
try:
    from playwright.async_api import async_playwright, Browser, Page, BrowserContext
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
        "captcha_timeout": 120,
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
    
    # User-Agents variados
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0",
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
        """Carrega proxies pagos (apenas proxies pagos são usados)"""
        self.paid_proxies = self._load_proxy_file(DATA_DIR / 'proxies.txt')

        if not self.paid_proxies:
            logger.error("❌ Nenhum proxy pago encontrado em proxies.txt")
            return False

        logger.info(f"✅ Carregados {len(self.paid_proxies)} proxies pagos")
        return True

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
        """Valida proxies pagos testando conectividade"""
        if not self.paid_proxies:
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
        """Constrói um dicionário de proxy compatível com requests"""
        if not proxy_str:
            return None

        proxy_url = proxy_str
        if proxy_str.lower().startswith(('http://', 'https://', 'socks5://', 'socks4://')):
            proxy_url = proxy_str
        elif '@' in proxy_str:
            partes = proxy_str.split(':')
            if len(partes) == 4:
                ip, porta, user, password = partes
                proxy_url = f"http://{user}:{password}@{ip}:{porta}"
            else:
                proxy_url = f"http://{proxy_str}"
        else:
            proxy_url = f"http://{proxy_str}"

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
                
                # Verificar bloqueios
                if resposta.status_code in [403, 503] or any(term in resposta.text.lower() for term in ['checking your browser', 'cloudflare', 'cf-challenge', 'cf-browser-verification']):
                    logger.warning(f"⚠️ Bloqueio detectado com proxy atual, tentando cloudscraper...")
                    if self.scraper:
                        scraper_kwargs = {k: v for k, v in kwargs.items() if k != 'proxies'}
                        scraper_kwargs['proxies'] = current_proxy
                        scraper_response = self._fazer_requisicao_com_cloudscraper(method, url, **scraper_kwargs)
                        if scraper_response:
                            self._sync_scraper_cookies_to_session()
                            return scraper_response
                    self._set_current_proxy(None)
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
            if not self.last_recaptcha_sitekey:
                sitekey_from_js = self._extrair_sitekey_from_js_reference(texto_resposta, base_url=url)
                if sitekey_from_js:
                    self.last_recaptcha_sitekey = sitekey_from_js
                    logger.info(f"✅ Sitekey de reCAPTCHA/Turnstile capturada de script JS: {self.last_recaptcha_sitekey}")

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
                                return self._avaliar_resposta_criacao(resposta, username)
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

            return self._avaliar_resposta_criacao(resposta, username)

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

    def _resolver_recaptcha(self, sitekey: str, page_url: str) -> Optional[str]:
        provider = self.config['captcha_solver'].get('provider', '2captcha')
        api_key = self.config['captcha_solver'].get('api_key', '')

        if provider != '2captcha':
            logger.warning(f"⚠️ Provedor de captcha não suportado: {provider}")
            return None

        if not api_key:
            logger.warning("⚠️ chave API de captcha não configurada em config.json")
            return None

        try:
            method = 'turnstile' if sitekey.startswith('0x') else 'userrecaptcha'
            logger.info(f"🔐 Enviando desafio reCAPTCHA/Turnstile para 2captcha (method={method}, sitekey={sitekey[:20]}..., pageurl={self.BASE_URL})")
            resposta = requests.get(
                'http://2captcha.com/in.php',
                params={
                    'key': api_key,
                    'method': method,
                    'googlekey': sitekey,
                    'pageurl': page_url,
                    'json': 1
                },
                timeout=30
            )
            dados = resposta.json()
            if dados.get('status') != 1:
                logger.warning(f"⚠️ 2captcha in.php falhou: {dados.get('request')}")
                return None

            request_id = dados.get('request')
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
                    timeout=30
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

    def __init__(self, config: Dict, proxies: List[str]):
        self.config = config
        self.proxies = proxies
        self.playwright = None
        self.browser = None
        self.context = None
        self.current_proxy = None

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

            # Configurar proxy se disponível
            proxy_config = None
            if self.proxies and self.config['browser_automation'].get('proxy_rotation', True):
                self.current_proxy = random.choice(self.proxies)
                proxy_parts = self.current_proxy.split(':')
                if len(proxy_parts) >= 4:
                    proxy_config = {
                        'server': f'http://{proxy_parts[0]}:{proxy_parts[1]}',
                        'username': proxy_parts[2],
                        'password': proxy_parts[3]
                    }
                    logger.info(f"🌐 Usando proxy: {proxy_parts[0]}:{proxy_parts[1]}")

            # Configurações do navegador
            browser_args = [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--no-first-run',
                '--no-zygote',
                '--disable-gpu',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor'
            ]

            self.browser = await self.playwright.chromium.launch(
                headless=self.config['browser_automation'].get('headless', True),
                args=browser_args,
                proxy=proxy_config
            )

            # Criar contexto com configurações stealth
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='pt-BR',
                timezone_id='America/Sao_Paulo'
            )

            # Aplicar stealth
            stealth_config = Stealth()
            await stealth_config.apply_stealth_async(self.context)

            logger.info("✅ Navegador Playwright inicializado com stealth")

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
            logger.info("🧹 Recursos do navegador liberados")
        except Exception as e:
            logger.warning(f"⚠️ Erro ao limpar recursos: {e}")

    async def create_account(self, username: str, password: str, email: str) -> bool:
        """Cria conta XAT usando automação de navegador"""
        try:
            logger.info(f"🎭 Iniciando criação de conta: {username} | {email}")

            # Criar nova página
            page = await self.context.new_page()
            await page.set_default_timeout(self.config['browser_automation'].get('page_timeout', 30000))

            # Passo 1: Obter UserID/k2
            user_data = await self._get_user_data(page)
            if not user_data:
                await page.close()
                return False

            user_id = user_data.get('UserId')
            k2_token = user_data.get('k2')

            # Aguardar entre requisições
            await self._random_delay()

            # Passo 2: Acessar página de login
            success = await self._access_login_page(page, user_id, k2_token)
            if not success:
                await page.close()
                return False

            # Aguardar carregamento e resolução de captcha
            await self._wait_for_captcha_resolution(page)

            # Passo 3: Preencher e submeter formulário
            success = await self._fill_registration_form(page, username, password, email)
            if not success:
                await page.close()
                return False

            # Passo 4: Verificar resultado
            result = await self._verify_registration_result(page, username)
            await page.close()

            return result

        except Exception as e:
            logger.error(f"❌ Erro na automação: {e}")
            return False

    async def _get_user_data(self, page: Page) -> Optional[Dict]:
        """Obtém UserID e k2 via auser3.php"""
        try:
            logger.info("🔗 Obtendo UserID/k2 via navegador")

            # Acessar auser3.php
            await page.goto(self.AUSER_URL, wait_until='networkidle')

            # Extrair dados da resposta
            content = await page.content()
            soup = BeautifulSoup(content, 'html.parser')

            # Procurar por dados JSON na página
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string and 'UserId' in script.string:
                    # Extrair JSON da resposta
                    match = re.search(r'(\{.*\})', script.string)
                    if match:
                        data = json.loads(match.group(1))
                        user_id = data.get('UserId')
                        k2 = data.get('k2')
                        if user_id and k2:
                            logger.info(f"✅ UserData obtido: UserId={user_id} k2={k2[:30]}...")
                            return {'UserId': user_id, 'k2': k2}

            # Fallback: tentar extrair do conteúdo da página
            text_content = await page.text_content('body') if await page.query_selector('body') else ""
            if text_content:
                user_id_match = re.search(r'UserId["\s:]+(\d+)', text_content)
                k2_match = re.search(r'k2["\s:]+([a-zA-Z0-9]+)', text_content)

                if user_id_match and k2_match:
                    user_id = user_id_match.group(1)
                    k2 = k2_match.group(1)
                    logger.info(f"✅ UserData extraído: UserId={user_id} k2={k2[:30]}...")
                    return {'UserId': user_id, 'k2': k2}

            logger.warning("⚠️ Não foi possível extrair UserID/k2 da resposta")
            return None

        except Exception as e:
            logger.error(f"❌ Erro ao obter user data: {e}")
            return None

    async def _access_login_page(self, page: Page, user_id: str, k2_token: str) -> bool:
        """Acessa página de login com parâmetros"""
        try:
            logger.info(f"🔗 Acessando página de login com UserId: {user_id}")

            login_url = f"{self.LOGIN_URL}?mode=1&UserId={user_id}&k2={k2_token}"
            await page.goto(login_url, wait_until='networkidle')

            # Verificar se página carregou corretamente
            title = await page.title()
            if 'login' in title.lower() or 'xat' in title.lower():
                logger.info("✅ Página de login carregada com sucesso")
                return True
            else:
                logger.warning(f"⚠️ Página suspeita carregada: {title}")
                return False

        except Exception as e:
            logger.error(f"❌ Erro ao acessar página de login: {e}")
            return False

    async def _wait_for_captcha_resolution(self, page: Page):
        """Aguarda resolução automática do captcha pelo navegador"""
        try:
            logger.info("🔒 Aguardando resolução automática do captcha...")

            captcha_timeout = self.config['browser_automation'].get('captcha_timeout', 120)

            # Aguardar até que não haja mais elementos de captcha visíveis
            await page.wait_for_function(
                """
                () => {
                    // Verificar se não há turnstile ou recaptcha visível
                    const turnstile = document.querySelector('[data-sitekey]');
                    const recaptcha = document.querySelector('.g-recaptcha, #captcha');
                    return !turnstile && !recaptcha;
                }
                """,
                timeout=captcha_timeout * 1000
            )

            logger.info("✅ Captcha resolvido automaticamente pelo navegador")

        except Exception as e:
            logger.warning(f"⚠️ Timeout aguardando resolução do captcha: {e}")

    async def _fill_registration_form(self, page: Page, username: str, password: str, email: str) -> bool:
        """Preenche e submete o formulário de registro"""
        try:
            logger.info("📝 Preenchendo formulário de registro...")

            # Aguardar formulário estar disponível
            await page.wait_for_selector('form', timeout=10000)

            # Preencher campos
            await page.fill('input[name="Username"]', username)
            await page.fill('input[name="password"]', password)
            await page.fill('input[name="password2"]', password)
            await page.fill('input[name="email"]', email)

            # Marcar checkbox de termos se existir
            try:
                await page.check('input[name="agree"]')
            except:
                pass  # Checkbox pode não existir

            # Aguardar um pouco antes de submeter
            await page.wait_for_timeout(2000)

            # Submeter formulário
            await page.click('input[type="submit"], button[type="submit"], .submit-btn')

            # Aguardar resposta
            await page.wait_for_load_state('networkidle')

            logger.info("✅ Formulário submetido")
            return True

        except Exception as e:
            logger.error(f"❌ Erro ao preencher formulário: {e}")
            return False

    async def _verify_registration_result(self, page: Page, username: str) -> bool:
        """Verifica se a conta foi criada com sucesso"""
        try:
            content = await page.content()
            text_content = await page.text_content()

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
                logger.info(f"✅ Conta criada com sucesso: {username}")
                return True
            elif error_found:
                logger.warning(f"⚠️ Erro detectado na criação da conta: {username}")
                return False
            else:
                logger.info(f"ℹ️ Status da criação indefinido para: {username}")
                return False

        except Exception as e:
            logger.error(f"❌ Erro ao verificar resultado: {e}")
            return False

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
        if config.get('browser_automation', {}).get('enabled', True) and PLAYWRIGHT_AVAILABLE:
            logger.info("🎭 Usando Browser Automation (Playwright)")
            asyncio.run(run_browser_automation(config))
        else:
            logger.info("🔗 Usando método tradicional (Requests)")
            gerador = XATAccountGenerator()
            gerador.executar()

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

        # Inicializar automação
        async with XATBrowserAutomation(config, proxies) as automation:
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

