# ðŸ“š Exemplos de Uso e Troubleshooting

## ðŸš€ Como ComeÃ§ar

### 1. Setup Inicial

```bash
# Executar setup (cria diretÃ³rios e arquivos de exemplo)
python setup.py

# Ou no Windows, clique em run.bat
```

### 2. Preparar Dados

**`data/emails.txt`**
```
usuario1@gmail.com
usuario2@outlook.com
usuario3@yahoo.com
usuario4@hotmail.com
usuario5@protonmail.com
```

**`data/proxies.txt`** (obter em: [proxylist.geonode.com](https://proxylist.geonode.com))
```
192.168.1.1:8080
10.0.0.1:3128
192.0.2.1:8080:username:password
203.0.113.5:3128:user123:pass456
198.51.100.42:8080
```

### 3. Instalar DependÃªncias

```bash
# Windows
pip install -r config/requirements.txt

# Linux/Mac
pip3 install -r config/requirements.txt
```

### 4. Executar

```bash
# MÃ©todo 1: Script direto
python code/main.py

# MÃ©todo 2: Windows (double-click)
run.bat

# MÃ©todo 3: Linux/Mac
bash run.sh

# MÃ©todo 4: Python direto
python3 code/main.py
```

---

## ðŸ“Š Exemplos de SaÃ­da

### Sucesso Esperado

```
2024-05-08 10:30:45,123 - INFO - ðŸš€ XAT Account Generator iniciado
2024-05-08 10:30:45,456 - INFO - âœ… Carregados 5 emails vÃ¡lidos
2024-05-08 10:30:45,789 - INFO - âœ… Carregados 3 proxies
2024-05-08 10:30:45,999 - INFO - âœ… Carregadas 0 contas jÃ¡ criadas
2024-05-08 10:30:46,111 - INFO - ðŸŽ¯ Iniciando criaÃ§Ã£o de 5 contas
2024-05-08 10:30:46,222 - INFO - ============================================================

2024-05-08 10:30:46,333 - INFO - 
2024-05-08 10:30:46,444 - INFO - ðŸ“§ Processando: 1/5 - usuario1@gmail.com
2024-05-08 10:30:48,555 - INFO - ðŸ”— Obtendo UserID via https://xat.com/web_gear/chat/auser3.php
2024-05-08 10:30:49,666 - INFO - âœ… UserID obtido: 12345678
2024-05-08 10:30:50,777 - INFO - ðŸ”— Acessando pÃ¡gina de login com UserId: 12345678
2024-05-08 10:30:51,888 - INFO - âœ… Token k2 obtido: abc123def456ghi789...
2024-05-08 10:30:52,999 - INFO - ðŸ“ Criando conta: Xyz123Abc | usuario1@gmail.com
2024-05-08 10:30:54,111 - INFO - âœ… Conta criada com sucesso: Xyz123Abc
2024-05-08 10:30:54,222 - INFO - ðŸ’¾ Conta salva em success_criacao.txt
```

### Arquivo `success_criacao.txt` Gerado

```
Xyz123Abc|P@ssw0rd123|usuario1@gmail.com|12345678|2024-05-08 10:30:54|sucesso
AbC456xYz|Str0ng!Pass|usuario2@outlook.com|87654321|2024-05-08 10:35:20|sucesso
```

---

## ðŸ”§ ConfiguraÃ§Ãµes AvanÃ§adas

### Modificar em `config.json`

```json
{
  "delays": {
    "min_entre_requisicoes": 0.3,      // â¬‡ï¸ Mais rÃ¡pido
    "max_entre_requisicoes": 1,
    "min_entre_contas": 2,             // â¬†ï¸ Mais seguro
    "max_entre_contas": 5
  },
  "timeout": {
    "requisicao": 20                   // Aumentar se timeout
  },
  "retry": {
    "max_tentativas": 5                // Mais tentativas
  }
}
```

### Usar Arquivo de ConfiguraÃ§Ã£o (Melhorias Futuras)

```python
# Importar config em main.py
import json

with open('config.json', 'r') as f:
    CONFIG = json.load(f)

delay_min = CONFIG['delays']['min_entre_requisicoes']
delay_max = CONFIG['delays']['max_entre_requisicoes']
```

---

## ðŸ› Troubleshooting

### âŒ "ModuleNotFoundError: No module named 'requests'"

**SoluÃ§Ã£o:**
```bash
pip install requests beautifulsoup4
# ou
pip install -r config/requirements.txt
```

### âŒ "data/emails.txt nÃ£o encontrado"

**SoluÃ§Ã£o:**
```bash
python setup.py
# Depois editar data/emails.txt com seus emails
```

### âŒ "Nenhum proxy encontrado em proxies.txt"

**SoluÃ§Ã£o:**
1. Verificar se `data/proxies.txt` existe
2. Adicionar proxies vÃ¡lidos
3. Testar proxy: `curl -x http://ip:porta https://ipinfo.io`

### âŒ Erro "ProxyError" ou "Timeout"

**SoluÃ§Ã£o:**
- Usar proxies diferentes (alguns podem estar offline)
- Aumentar timeout em config.json
- Aumentar delay entre requisiÃ§Ãµes

### âŒ Cloudflare "403 Forbidden"

**SoluÃ§Ã£o (no cÃ³digo):**
```python
# main.py jÃ¡ trata automaticamente com delay
# Se persistir, adicione User-Agent mais realista
USER_AGENTS.append("Mozilla/5.0 (compatÃ­vel com Cloudflare)")
```

### âŒ "reCAPTCHA detectado"

**SoluÃ§Ã£o:**
- Script pula automaticamente
- Ou use Selenium com Chrome headless (implementaÃ§Ã£o futura)

### âŒ Script muito lento

**SoluÃ§Ã£o:**
Aumentar threads (no arquivo a implementar):
```python
# Use ThreadPoolExecutor para acelerar
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=5) as executor:
    futures = [executor.submit(criar_conta, email) for email in emails]
```

### âŒ Proxies nÃ£o funcionam

**Teste de proxy:**
```bash
# Windows
curl -x http://ip:porta https://httpbin.org/ip

# Linux/Mac
curl -x http://ip:porta https://httpbin.org/ip
```

---

## ðŸ’¡ Dicas Importantes

### 1. **Limpar logs antigos**
```bash
del criacao_contas.log  # Windows
rm criacao_contas.log   # Linux/Mac
```

### 2. **Resetar contas criadas**
```bash
del data/success_criacao.txt  # Windows
rm data/success_criacao.txt   # Linux/Mac
```

### 3. **Validar emails antes**
```bash
# Adicionar script de validaÃ§Ã£o
# ou usar: https://emaillistverify.com
```

### 4. **Monitorar em Tempo Real**
```bash
# Linux/Mac
tail -f criacao_contas.log

# Windows PowerShell
Get-Content criacao_contas.log -Wait
```

### 5. **MÃºltiplos InstÃ¢ncias**
```bash
# Criar mÃºltiplas janelas com diferentes listas de emails
# Cada uma com seu prÃ³prio data/emails.txt
```

---

## ðŸ“ˆ Melhorando a Performance

### OpÃ§Ã£o 1: Multi-threading (ImplementaÃ§Ã£o Futura)
```python
from concurrent.futures import ThreadPoolExecutor
max_workers = 5  # 5 requisiÃ§Ãµes simultÃ¢neas
```

### OpÃ§Ã£o 2: Aumentar Taxa de RequisiÃ§Ã£o
- Reduzir `min_entre_requisicoes` em config.json
- Usar proxies mais rÃ¡pidos

### OpÃ§Ã£o 3: Parallelizar por Proxy
- 1 thread por proxy
- 5 proxies = 5 threads simultÃ¢neas

---

## ðŸ”’ Boas PrÃ¡ticas de SeguranÃ§a

1. âœ… **NÃ£o commitar dados sensÃ­veis**
   - `.gitignore` jÃ¡ estÃ¡ configurado

2. âœ… **Usar proxies confiÃ¡veis**
   - Evitar proxies gratuitos lentos
   - Preferir servos dedicados

3. âœ… **Rotacionar User-Agents**
   - Script jÃ¡ faz automaticamente
   - Adicionar mais se necessÃ¡rio

4. âœ… **Respeitar Rate Limits**
   - Delays aleatÃ³rios entre requisiÃ§Ãµes
   - NÃ£o fazer mÃºltiplas requisiÃ§Ãµes simultÃ¢neas

5. âœ… **Verificar Termos de ServiÃ§o**
   - Usar script responsavelmente
   - Apenas para fins educacionais/teste

---

## ðŸ“ž Suporte Adicional

Verifique o arquivo `criacao_contas.log` para:
- Erros especÃ­ficos
- Problemas com proxies
- Detalhes de falhas

Procure por padrÃµes como:
- `ProxyError` â†’ Proxy invÃ¡lido/offline
- `Timeout` â†’ Proxy lento ou blocked
- `403/503` â†’ Cloudflare (script aguarda automaticamente)
- `recaptcha` â†’ Bot detectado (pula conta)

---

**Sucesso! ðŸš€**

