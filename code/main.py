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
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin, parse_qs, urlparse
from bs4 import BeautifulSoup

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
        "min_entre_requisicoes": 0.5,
        "max_entre_requisicoes": 2,
        "min_entre_contas": 1,
        "max_entre_contas": 3
    },
    "timeout": {
        "requisicao": 15,
        "proxy": 10
    },
    "retry": {
        "max_tentativas": 3,
        "delay_entre_tentativas": 1
    },
    "proxy": {
        "rotacao": "por_requisicao",
        "health_check": False,
        "use_public_fallback": True
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
        self.paid_proxies: List[str] = []
        self.public_proxies: List[str] = []
        self.proxy_indexes = {'paid': 0, 'public': 0}
        self.contas_criadas: Dict[str, Dict] = {}
        self.config = self._carregar_config()
        self.session = self._criar_sessao()
        self.scraper = self._criar_scraper()
        
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
            'Accept-Encoding': 'gzip, deflate, br',
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
    
    def carregar_proxies(self) -> bool:
        """Carrega proxies pagos e proxies públicos"""
        self.paid_proxies = self._load_proxy_file(DATA_DIR / 'proxies.txt')
        self.public_proxies = self._load_proxy_file(DATA_DIR / 'public_proxies.txt')

        if not self.paid_proxies and not self.public_proxies:
            logger.error("❌ Nenhum proxy encontrado em proxies.txt ou public_proxies.txt")
            return False

        if self.paid_proxies:
            logger.info(f"✅ Carregados {len(self.paid_proxies)} proxies pagos")
        else:
            logger.warning("⚠️ Nenhum proxy pago encontrado; usando apenas proxies públicos")

        if self.public_proxies:
            logger.info(f"✅ Carregados {len(self.public_proxies)} proxies públicos")

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
    
    def _validar_email(self, email: str) -> bool:
        """Valida formato básico de email"""
        padrao = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(padrao, email) is not None
    
    def gerar_username(self, tamanho_min: int = 10, tamanho_max: int = 18) -> str:
        """Gera username aleatório com 10-18 caracteres"""
        tamanho = random.randint(tamanho_min, tamanho_max)
        caracteres = string.ascii_letters + string.digits
        return ''.join(random.choice(caracteres) for _ in range(tamanho))
    
    def gerar_senha(self, tamanho_min: int = 8, tamanho_max: int = 16) -> str:
        """Gera senha aleatória forte (maiúsculas, minúsculas, números, símbolos)"""
        tamanho = random.randint(tamanho_min, tamanho_max)
        
        maiusculas = random.choice(string.ascii_uppercase)
        minusculas = random.choice(string.ascii_lowercase)
        numeros = random.choice(string.digits)
        simbolos = random.choice('!@#$%^&*-_=+')
        
        caracteres_restantes = string.ascii_letters + string.digits + '!@#$%^&*-_=+'
        senha = [maiusculas, minusculas, numeros, simbolos]
        senha += [random.choice(caracteres_restantes) for _ in range(tamanho - 4)]
        
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
        
        if should_skip_proxy:
            logger.info(f"🔓 Acessando {url.split('/')[-1]} sem proxy (acesso direto)")
            return self._fazer_requisicao_direto(method, url, **kwargs)
        
        proxy_groups = []
        if self.paid_proxies:
            proxy_groups.append('paid')
        if self.public_proxies and (use_public_fallback or not self.paid_proxies):
            proxy_groups.append('public')

        if not proxy_groups:
            logger.error("❌ Nenhum proxy disponível para requisição")
            return None

        for proxy_type in proxy_groups:
            if proxy_type == 'public':
                logger.info("🔄 Tentando proxies públicos como fallback")

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
                            scraper_response = self._fazer_requisicao_com_cloudscraper(method, url, proxies=proxy, **kwargs)
                            if scraper_response:
                                return scraper_response
                        time.sleep(random.uniform(1, 3))
                        continue

                    resposta.raise_for_status()
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
    
    def obter_user_id(self) -> Optional[str]:
        """
        PASSO 1: Fazer GET para auser3.php e extrair UserID
        """
        try:
            logger.info(f"🔗 Obtendo UserID via {self.AUSER_URL}")
            resposta = self._fazer_requisicao('GET', self.AUSER_URL)
            
            if not resposta:
                logger.error("❌ Falha ao obter resposta de auser3.php")
                return None
            
            # Extrair UserID da resposta como query string, JSON ou HTML
            query_data = parse_qs(resposta.text.lstrip('&').strip())
            if query_data.get('UserId'):
                user_id = query_data['UserId'][0]
                logger.info(f"✅ UserID obtido via query string: {user_id}")
                return user_id

            # Tentar JSON
            try:
                json_data = resposta.json()
                if 'UserId' in json_data:
                    user_id = str(json_data['UserId'])
                    logger.info(f"✅ UserID obtido via JSON: {user_id}")
                    return user_id
            except:
                pass

            match = re.search(r'UserId["\']?\s*[:=]\s*["\']?(\d+)', resposta.text, re.IGNORECASE)
            if match:
                user_id = match.group(1)
                logger.info(f"✅ UserID obtido: {user_id}")
                return user_id
            
            # Tentar alternativa (procurar em tags ou variáveis)
            match = re.search(r'(\d{5,})', resposta.text)
            if match:
                user_id = match.group(1)
                logger.info(f"✅ UserID extraído (alternativo): {user_id}")
                return user_id
            
            logger.error("❌ Não foi possível extrair UserID da resposta")
            logger.debug(f"Resposta recebida: {resposta.text[:1000]}")
            return None
        
        except Exception as e:
            logger.error(f"❌ Erro ao obter UserID: {e}")
            return None
    
    def acessar_pagina_login(self, user_id: str) -> Optional[str]:
        """
        PASSO 2: Acessar página login para extrair token k2
        Retorna o token k2
        """
        try:
            url = f"{self.LOGIN_URL}?mode=1&UserId={user_id}"
            logger.info(f"🔗 Acessando página de login com UserId: {user_id}")
            
            resposta = self._fazer_requisicao('GET', url)
            
            if not resposta:
                logger.error("❌ Falha ao acessar página de login")
                return None
            
            # Extrair token k2
            match = re.search(r'["\']?k2["\']?\s*[:=]\s*["\']([^"\']+)["\']', resposta.text)
            if match:
                k2_token = match.group(1)
                logger.info(f"✅ Token k2 obtido: {k2_token[:20]}...")
                return k2_token
            
            # Tentar alternativa: buscar em data attributes
            match = re.search(r'data-k2=["\']([^"\']+)["\']', resposta.text)
            if match:
                k2_token = match.group(1)
                logger.info(f"✅ Token k2 obtido (alternativo): {k2_token[:20]}...")
                return k2_token
            
            logger.warning("⚠️ Token k2 não encontrado, tentando prosseguir sem ele")
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
                'username': username,
                'password': senha,
                'email': email,
                'UserId': user_id,
            }

            if k2_token:
                dados['k2'] = k2_token

            # Headers adicionais para fazer parecer um navegador real
            headers = {
                'Referer': f"{self.LOGIN_URL}?mode=1&UserId={user_id}",
                'Origin': self.BASE_URL,
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            url_registro = f"{self.BASE_URL}/register"
            resposta = self._fazer_requisicao('POST', url_registro, data=dados, headers=headers)

            if not resposta:
                logger.error("❌ Falha ao submeter formulário de cadastro")
                return False

            if self._detectar_recaptcha(resposta.text):
                logger.warning(f"⚠️ reCAPTCHA detectado para {email}")
                if self.config['captcha_solver'].get('enabled', False):
                    sitekey = self._extrair_sitekey(resposta.text)
                    if sitekey:
                        token = self._resolver_recaptcha(sitekey, url_registro)
                        if token:
                            dados['g-recaptcha-response'] = token
                            resposta = self._fazer_requisicao('POST', url_registro, data=dados, headers=headers)
                            if resposta and not self._detectar_recaptcha(resposta.text):
                                logger.info("✅ reCAPTCHA resolvido via solver")
                                return self._avaliar_resposta_criacao(resposta, username)
                            logger.warning("⚠️ reCAPTCHA ainda presente após solver")
                        else:
                            logger.warning("⚠️ Solver de reCAPTCHA falhou")
                    else:
                        logger.warning("⚠️ Não foi possível extrair sitekey de reCAPTCHA")
                logger.warning(f"⚠️ Não foi possível criar conta devido a reCAPTCHA para {email}")
                return False

            return self._avaliar_resposta_criacao(resposta, username)

        except Exception as e:
            logger.error(f"❌ Erro ao criar conta: {e}")
            return False

    def _avaliar_resposta_criacao(self, resposta: requests.Response, username: str) -> bool:
        """Avalia se a resposta indica sucesso ou falha na criação"""
        texto = resposta.text.lower()

        if any(palavra in texto for palavra in ['sucesso', 'success', 'criada com sucesso', 'account created', 'bem-vindo', 'welcome', 'confirme seu email']):
            logger.info(f"✅ Conta criada com sucesso: {username}")
            return True

        if any(palavra in texto for palavra in ['já existe', 'already exists', 'duplicado', 'duplicate']):
            logger.warning(f"⚠️ Username já existe: {username}")
            return False

        if resposta.status_code == 200:
            logger.info(f"✅ Resposta 200 OK - Conta possivelmente criada: {username}")
            return True

        logger.warning(f"⚠️ Resposta inesperada (status {resposta.status_code})")
        logger.debug(f"Resposta: {resposta.text[:500]}")
        return False

    def _detectar_recaptcha(self, texto: str) -> bool:
        texto = texto.lower()
        return 'recaptcha' in texto or 'g-recaptcha' in texto or 'h-captcha' in texto or 'captcha' in texto

    def _extrair_sitekey(self, html: str) -> Optional[str]:
        match = re.search(r'data-sitekey=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if match:
            return match.group(1)

        match = re.search(r'sitekey=(["\']?)([^"\'&>\s]+)\1', html, re.IGNORECASE)
        if match:
            return match.group(2)

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
            logger.info("🔐 Enviando desafio reCAPTCHA para 2captcha")
            resposta = requests.get(
                'http://2captcha.com/in.php',
                params={
                    'key': api_key,
                    'method': 'userrecaptcha',
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
                        self.contas_criadas[email] = {
                            'username': partes[0],
                            'email': email,
                            'timestamp': partes[4] if len(partes) > 4 else '',
                            'status': partes[5] if len(partes) > 5 else 'sucesso'
                        }
            
            logger.info(f"✅ Carregadas {len(self.contas_criadas)} contas já criadas")
        
        except Exception as e:
            logger.error(f"❌ Erro ao carregar contas existentes: {e}")
    
    def salvar_sucesso(self, username: str, senha: str, email: str, user_id: str, status: str = "sucesso"):
        """Salva conta criada com sucesso em success_criacao.txt"""
        try:
            DATA_DIR.mkdir(exist_ok=True)
            arquivo = DATA_DIR / 'success_criacao.txt'
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            linha = f"{username}|{senha}|{email}|{user_id}|{timestamp}|{status}\n"
            
            with open(arquivo, 'a', encoding='utf-8') as f:
                f.write(linha)
            
            logger.info(f"💾 Conta salva em success_criacao.txt")
        
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
                
                # Gerar dados da conta
                username = self.gerar_username()
                senha = self.gerar_senha()
                
                # PASSO 1: Obter UserID
                user_id = self.obter_user_id()
                if not user_id:
                    logger.error(f"❌ Não foi possível obter UserID para {email}")
                    continue
                
                # Delay após requisição (configurável)
                delay = random.uniform(
                    self.config['delays'].get('min_entre_requisicoes', 5),
                    self.config['delays'].get('max_entre_requisicoes', 10)
                )
                logger.info(f"⏳ Aguardando {delay:.1f}s entre requisições...")
                time.sleep(delay)
                
                # PASSO 2: Acessar página de login
                k2_token = self.acessar_pagina_login(user_id)
                if k2_token is None:
                    logger.error(f"❌ Falha ao acessar login para {email}")
                    continue
                
                # Delay após requisição
                delay = random.uniform(
                    self.config['delays'].get('min_entre_requisicoes', 5),
                    self.config['delays'].get('max_entre_requisicoes', 10)
                )
                logger.info(f"⏳ Aguardando {delay:.1f}s entre requisições...")
                time.sleep(delay)
                
                # PASSO 3 e 4: Criar conta
                sucesso = self.criar_conta(username, senha, email, user_id, k2_token)
                
                if sucesso:
                    self.salvar_sucesso(username, senha, email, user_id)
                    self.contas_criadas[email] = {
                        'username': username,
                        'email': email,
                        'user_id': user_id,
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
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
        
        if not self.carregar_proxies():
            logger.error("❌ Falha ao carregar proxies. Abortando...")
            return False
        
        if not self.emails:
            logger.error("❌ Nenhum email novo para processar.")
            return False
        
        # Processar emails
        self.processar_emails()
        return True


def main():
    """Função principal"""
    try:
        # Criar diretório de dados se não existir
        DATA_DIR.mkdir(exist_ok=True)
        
        # Inicializar gerador
        gerador = XATAccountGenerator()
        
        # Executar
        gerador.executar()
    
    except KeyboardInterrupt:
        logger.warning("\n⚠️ Aplicação encerrada pelo usuário")
        sys.exit(0)
    
    except Exception as e:
        logger.error(f"❌ Erro fatal: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
