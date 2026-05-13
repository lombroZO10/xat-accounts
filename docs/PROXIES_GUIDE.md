# ðŸŒ Guia Completo de Proxies e Recursos

## ðŸ”§ Configuração Atual - Webshare Rotating Proxies

### Proxy Ativo (Estados Unidos)
```
Host: p.webshare.io
Port: 80
Username: cqgsjjoe-US-rotate
Password: syeim3ngqut4
Formato: http://cqgsjjoe-US-rotate:syeim3ngqut4@p.webshare.io:80
```

### Como Funciona
- **Rotating**: IP muda automaticamente a cada requisição
- **Geo-targeting**: Rota dos EUA para melhor compatibilidade
- **Session IDs**: Suporte a sessões persistentes para evitar detecção
- **Rate Limits**: Adequado para automação moderada

### Arquivo de Configuração
O proxy está configurado em `data/proxies.txt`:
```
http://cqgsjjoe-US-rotate:syeim3ngqut4@p.webshare.io:80
```

---

## ðŸ“ Onde Obter Proxies

### OpÃ§Ã£o 1: Listas PÃºblicas (Gratuitas - âš ï¸ InstÃ¡veis)

| Site | Tipo | Qualidade |
|------|------|-----------|
| [ProxyList.geonode.com](https://proxylist.geonode.com) | HTTP/HTTPS | â­â­â­ |
| [proxy-list.download](https://www.proxy-list.download) | HTTP/HTTPS/SOCKS | â­â­â­ |
| [free-proxy-list.net](https://free-proxy-list.net) | HTTP | â­â­ |
| [proxyscrape.com](https://proxyscrape.com) | HTTP/SOCKS5 | â­â­â­ |
| [github.com/clarketm/proxy-list](https://github.com/clarketm/proxy-list) | VÃ¡rios | â­â­ |

### OpÃ§Ã£o 2: Proxies Pagos (Recomendado)

| Provedor | PreÃ§o | Velocidade | Uptime |
|----------|-------|-----------|--------|
| [Bright Data](https://brightdata.com) | $$ | â­â­â­â­â­ | 99.9% |
| [Oxylabs](https://oxylabs.io) | $$ | â­â­â­â­â­ | 99.8% |
| [ScraperAPI](https://www.scraperapi.com) | $ | â­â­â­â­ | 99.9% |
| [Smartproxy](https://smartproxy.com) | $ | â­â­â­â­ | 99.6% |
| [GeoSurf](https://www.geosurf.com) | $$ | â­â­â­â­ | 99.7% |

### OpÃ§Ã£o 3: Script de Coleta AutomÃ¡tica

```python
import requests
from bs4 import BeautifulSoup

def coletar_proxies():
    url = "https://free-proxy-list.net"
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    proxies = []
    for row in soup.find_all('tr')[1:11]:  # Primeiros 10
        cols = row.find_all('td')
        if len(cols) >= 2:
            ip = cols[0].text.strip()
            porta = cols[1].text.strip()
            proxies.append(f"{ip}:{porta}")
    
    return proxies

# Salvar
proxies = coletar_proxies()
with open('data/proxies.txt', 'w') as f:
    f.write('\n'.join(proxies))
```

---

## âœ… Teste de Proxy

### Validar Proxy

```bash
# Teste simples (qualquer sistema)
curl -x http://ip:porta https://httpbin.org/ip

# Com autenticaÃ§Ã£o
curl -x http://user:pass@ip:porta https://httpbin.org/ip

# Python
python -c "
import requests
proxies = {'http': 'http://ip:porta', 'https': 'http://ip:porta'}
r = requests.get('https://httpbin.org/ip', proxies=proxies, timeout=5)
print('Status:', r.status_code)
print('IP:', r.json())
"
```

### Script de ValidaÃ§Ã£o em Python

```python
# validate_proxies.py
import requests
from pathlib import Path

def validar_proxy(proxy):
    try:
        proxies = {'http': f'http://{proxy}', 'https': f'http://{proxy}'}
        r = requests.get('https://httpbin.org/ip', proxies=proxies, timeout=5)
        return r.status_code == 200
    except:
        return False

# Testar proxies
proxies = Path('data/proxies.txt').read_text().strip().split('\n')
validos = [p for p in proxies if validar_proxy(p)]

print(f"VÃ¡lidos: {len(validos)}/{len(proxies)}")
Path('data/proxies.txt').write_text('\n'.join(validos))
```

---

## ðŸ” Proxies com AutenticaÃ§Ã£o

### Formato

```
ip:porta:username:password
```

### Exemplo

```
192.168.1.1:8080:meuuser:meupass
10.0.0.1:3128:admin:senha123
203.0.113.5:8080:user_xat:pass_secure
```

### Como Usar em main.py

JÃ¡ estÃ¡ implementado! Apenas adicione ao `data/proxies.txt`:

```python
# O script detecta automaticamente
if '@' in proxy_str:
    ip, porta, user, password = proxy_str.split(':')
    proxy_url = f"http://{user}:{password}@{ip}:{porta}"
```

---

## ðŸš€ Recursos Ãšteis

### Ferramentas de Teste

| Ferramenta | Uso |
|-----------|-----|
| [httpbin.org](https://httpbin.org) | Testar headers, proxy, IP |
| [whatismyipaddress.com](https://whatismyipaddress.com) | Ver IP pÃºblico |
| [curl.se](https://curl.se) | Cliente HTTP avanÃ§ado |
| [Postman](https://postman.com) | Testar APIs e proxies |

### Bibliotecas Python Ãšteis

```bash
# JÃ¡ instaladas
pip install requests beautifulsoup4

# Opcionais para melhorias
pip install selenium         # Para render JS
pip install fake-useragent   # User-Agents automÃ¡ticos
pip install cloudscraper     # Contornar Cloudflare
pip install pysocks          # SOCKS proxy support
```

### Melhorias PrÃ¡ticas

```python
# 1. Usar fake-useragent
from fake_useragent import UserAgent
ua = UserAgent()
headers['User-Agent'] = ua.random

# 2. Usar cloudscraper para Cloudflare
import cloudscraper
scraper = cloudscraper.create_scraper()
response = scraper.get(url)

# 3. Selenium para JS
from selenium import webdriver
driver = webdriver.Chrome()
driver.get(url)
```

---

## ðŸ“Š Monitoramento de Proxies

### Script de Health Check (ImplementaÃ§Ã£o Futura)

```python
import threading
import requests

class ProxyMonitor:
    def __init__(self, proxies, check_interval=60):
        self.proxies = proxies
        self.healthy = {}
        self.check_interval = check_interval
    
    def verificar_proxy(self, proxy):
        try:
            proxies = {'http': f'http://{proxy}'}
            r = requests.get('https://httpbin.org/ip', 
                           proxies=proxies, 
                           timeout=5)
            self.healthy[proxy] = r.status_code == 200
        except:
            self.healthy[proxy] = False
    
    def verificar_todos(self):
        threads = []
        for proxy in self.proxies:
            t = threading.Thread(target=self.verificar_proxy, args=(proxy,))
            t.start()
            threads.append(t)
        
        for t in threads:
            t.join()
        
        return [p for p, ok in self.healthy.items() if ok]
```

---

## ðŸ”’ SeguranÃ§a de Proxy

### Riscos Conhecidos

âš ï¸ **Proxies Gratuitos:**
- Podem roubar dados
- Injetar malware
- Rastrear trÃ¡fego
- InstÃ¡veis (queda frequente)

âœ… **Melhores PrÃ¡ticas:**

1. **Use HTTPS** (nÃ£o HTTP)
   ```python
   proxies = {
       'https': 'http://ip:porta'  # Usar para HTTPS
   }
   ```

2. **Proxies Pagos ConfiÃ¡veis**
   - Maiores velocidades
   - Uptime garantido
   - Suporte tÃ©cnico

3. **Rotar Proxies**
   - Script jÃ¡ faz automaticamente
   - Reduz rate limiting

4. **Verificar IP do Proxy**
   ```bash
   curl -x http://ip:porta https://api.myip.com
   ```

---

## ðŸ“ˆ OtimizaÃ§Ã£o de Proxies

### SeleÃ§Ã£o por Performance

```python
import time
import requests

def medir_latencia(proxy):
    """Mede tempo de resposta do proxy"""
    try:
        start = time.time()
        proxies = {'http': f'http://{proxy}'}
        requests.get('https://httpbin.org/ip', 
                    proxies=proxies, 
                    timeout=5)
        return time.time() - start
    except:
        return float('inf')

# Ordenar por latÃªncia
proxies = ['ip1:porta1', 'ip2:porta2', ...]
ranking = sorted(proxies, key=medir_latencia)
```

### Pool de Proxies (ImplementaÃ§Ã£o Futura)

```python
class ProxyPool:
    def __init__(self, proxies):
        self.proxies = proxies
        self.index = 0
        self.falhas = {p: 0 for p in proxies}
    
    def obter_proxy(self):
        """Retorna prÃ³ximo proxy funcional"""
        tentativas = 0
        while tentativas < len(self.proxies):
            proxy = self.proxies[self.index]
            self.index = (self.index + 1) % len(self.proxies)
            
            if self.falhas[proxy] < 5:  # Max 5 falhas
                return proxy
            
            tentativas += 1
        
        return None  # Nenhum proxy disponÃ­vel
    
    def registrar_falha(self, proxy):
        """Registra falha de proxy"""
        self.falhas[proxy] += 1
```

---

## ðŸŒ Proxies por RegiÃ£o

### Recomendado para XAT.COM

Se XAT.COM estÃ¡ em servidor especÃ­fico, usar proxy da mesma regiÃ£o:

```
USA:        199.X.X.X a 207.X.X.X
Brasil:     177.X.X.X a 187.X.X.X
Europa:     31.X.X.X a 95.X.X.X
Ãsia:       1.X.X.X a 103.X.X.X
```

### DetecÃ§Ã£o de LocalizaÃ§Ã£o

```bash
curl -s https://ipinfo.io/{ip}/json | jq '.country'
```

---

## ðŸ’° OrÃ§amento Recomendado

| Volume | SoluÃ§Ã£o | Custo/mÃªs |
|--------|---------|-----------|
| 1-100 contas | Gratuitos | $0 |
| 100-1000 | SmartProxy | $10-50 |
| 1000+ | Bright Data | $50-500 |
| Ultra grande | SoluÃ§Ãµes custom | Custom |

---

## ðŸ“ž Suporte de Proxy

### Problemas Comuns

| Problema | SoluÃ§Ã£o |
|----------|---------|
| 407 Proxy Auth Required | Adicionar user:pass |
| 504 Bad Gateway | Proxy offline, usar prÃ³ximo |
| Timeout | Proxy lento, aumentar timeout |
| 403 Forbidden | IP bloqueado, trocar proxy |

---

**Atualizado: 2024**
**Ãšltimo teste de proxies: [ProxyList.geonode.com](https://proxylist.geonode.com)**

