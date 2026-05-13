# ðŸš€ XAT Account Generator

Gerador automÃ¡tico de contas para **XAT.COM** com rotaÃ§Ã£o de proxies, tratamento de proteÃ§Ãµes e logging detalhado.

## ðŸ“‹ Requisitos

- Python 3.8+
- Arquivo `data/emails.txt` (um email por linha)
- Arquivo `data/proxies.txt` (proxies no formato `ip:porta` ou `ip:porta:user:pass`)

## ðŸ“‹ Configuração Atual

### 🌍 Localização e Idioma
- **Proxies**: Webshare Rotating (Estados Unidos)
- **Locale**: `en-US`
- **Timezone**: `America/New_York`
- **Accept-Language**: `en-US,en;q=0.9`

### 🛡️ Anti-Detecção
- Aquecimento de cookies reforçado (12s + interações)
- Verificação de título da página
- Interações randômicas com mouse wheel
- AdsPower CDP para bypass avançado
- **User-Agent synchronization** com 2Captcha solver
- **Canvas fingerprint noise** para evitar detecção
- **WebGL fingerprint noise** para proteção avançada
- **User-Agent Elite**: Chrome 124.0.0.0 para máxima compatibilidade
- **CDP trace removal**: Remove rastros de Runtime.enable
- **Referer spoofing**: Simula navegação orgânica do Google
- **Real viewport**: 1920x1080 (resolução de monitor padrão)

## ðŸ“‹ Requisitos

- Python 3.8+
- Arquivo `data/emails.txt` (um email por linha)
- Arquivo `data/proxies.txt` (proxies no formato `ip:porta` ou `ip:porta:user:pass`)

## ðŸ”§ InstalaÃ§Ã£o

```bash
# Instalar dependÃªncias
pip install -r config/requirements.txt

# (Opcional) Criar ambiente virtual
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac
```

## ðŸ“ Estrutura de DiretÃ³rios

```
xat-accounts/
â”œâ”€â”€ main.py                  # Script principal
â”œâ”€â”€ config/requirements.txt         # DependÃªncias Python
â”œâ”€â”€ config.json             # ConfiguraÃ§Ãµes
â”œâ”€â”€ criacao_contas.log      # Log de execuÃ§Ã£o (gerado automaticamente)
â””â”€â”€ data/
    â”œâ”€â”€ emails.txt          # Lista de emails (um por linha)
    â”œâ”€â”€ proxies.txt         # Lista de proxies (um por linha)
    â””â”€â”€ success_criacao.txt # Contas criadas com sucesso
```

## ðŸ“§ Formato dos Arquivos

### `data/emails.txt`
```
usuario1@gmail.com
usuario2@outlook.com
usuario3@yahoo.com
```

### `data/proxies.txt`
```
192.168.1.1:8080
192.168.1.2:8080:user:pass
10.0.0.1:3128
```

## ðŸŽ¯ Como Usar

```bash
# Executar o gerador
python code/main.py
```

## ðŸ“Š Funcionalidades

âœ… **Leitura automÃ¡tica de emails**
- Valida formato de email
- Remove duplicatas
- Evita reprocessar contas existentes

âœ… **GeraÃ§Ã£o segura de credenciais**
- Username: 10-18 caracteres aleatÃ³rios
- Senha: MÃ­nimo 8 caracteres (maiÃºsculas, minÃºsculas, nÃºmeros, sÃ­mbolos)

âœ… **Sistema robusto de proxy**
- RotaÃ§Ã£o automÃ¡tica de proxies
- Suporte a autenticaÃ§Ã£o (user:pass)
- Tratamento de falhas com fallback
- Retry automÃ¡tico com mÃºltiplas tentativas

âœ… **Contornamento de proteÃ§Ãµes**
- RotaÃ§Ã£o de User-Agent
- Headers realistas (Referer, Accept-Language, etc)
- Delays aleatÃ³rios entre requisiÃ§Ãµes (0.5-2s)
- DetecÃ§Ã£o de Cloudflare (503, 403)
- DetecÃ§Ã£o de reCAPTCHA

âœ… **Logging detalhado**
- Arquivo `criacao_contas.log` com histÃ³rico completo
- Mensagens em tempo real no console
- Indicadores visuais (âœ… âŒ âš ï¸ ðŸ”—)

âœ… **Salvamento de resultados**
- Formato: `username|senha|email|userid|timestamp|status`
- Permite continuaÃ§Ã£o se o script parar
- Evita criaÃ§Ã£o de duplicatas

## ðŸ“ Fluxo de CriaÃ§Ã£o

```
1. GET /web_gear/chat/auser3.php
   â””â”€> Extrai UserID

2. GET /login?mode=1&UserId={UserId}
   â””â”€> Extrai token k2

3. POST /register
   â””â”€> Username, Senha, Email, UserID, k2

4. ValidaÃ§Ã£o
   â””â”€> Salva em success_criacao.txt se sucesso
```

## âš™ï¸ ConfiguraÃ§Ãµes (config.json)

- `delays.min_entre_requisicoes`: Delay mÃ­nimo entre requisiÃ§Ãµes (padrÃ£o: 0.5s)
- `delays.max_entre_requisicoes`: Delay mÃ¡ximo entre requisiÃ§Ãµes (padrÃ£o: 2s)
- `delays.min_entre_contas`: Delay mÃ­nimo entre contas (padrÃ£o: 1s)
- `delays.max_entre_contas`: Delay mÃ¡ximo entre contas (padrÃ£o: 3s)
- `timeout.requisicao`: Timeout para requisiÃ§Ãµes HTTP (padrÃ£o: 15s)
- `retry.max_tentativas`: MÃ¡ximo de tentativas por requisiÃ§Ã£o (padrÃ£o: 3)
- `username.tamanho_min/max`: Tamanho do username (padrÃ£o: 10-18)
- `senha.tamanho_min/max`: Tamanho da senha (padrÃ£o: 8-16)

## ðŸ“Š SaÃ­da Esperada

```
2024-05-08 10:30:45 - INFO - ðŸš€ XAT Account Generator iniciado
2024-05-08 10:30:45 - INFO - âœ… Carregados 50 emails vÃ¡lidos
2024-05-08 10:30:45 - INFO - âœ… Carregados 10 proxies
2024-05-08 10:30:45 - INFO - ðŸŽ¯ Iniciando criaÃ§Ã£o de 50 contas
2024-05-08 10:30:47 - INFO - ðŸ“§ Processando: 1/50 - usuario1@gmail.com
2024-05-08 10:30:48 - INFO - ðŸ”— Obtendo UserID via https://xat.com/web_gear/chat/auser3.php
2024-05-08 10:30:49 - INFO - âœ… UserID obtido: 123456
2024-05-08 10:30:50 - INFO - ðŸ”— Acessando pÃ¡gina de login com UserId: 123456
2024-05-08 10:30:51 - INFO - âœ… Token k2 obtido: abc123def456...
2024-05-08 10:30:52 - INFO - ðŸ“ Criando conta: AbC123xYz | usuario1@gmail.com
2024-05-08 10:30:54 - INFO - âœ… Conta criada com sucesso: AbC123xYz
2024-05-08 10:30:54 - INFO - ðŸ’¾ Conta salva em success_criacao.txt
```

## ðŸ› Tratamento de Erros

O script trata automaticamente:

- âŒ **ProxyError**: PrÃ³ximo proxy na rotaÃ§Ã£o
- âŒ **Timeout**: Retry com proxy diferente
- âŒ **ConnectionError**: Retry automÃ¡tico
- âŒ **Cloudflare** (503/403): Aguarda e tenta novamente
- âŒ **reCAPTCHA**: Registra e pula conta
- âŒ **Username duplicado**: Registra e tenta outro

## ðŸ“ˆ Melhorias Futuras

- [ ] Database SQLite para rastreamento
- [ ] Multi-threading para processamento paralelo
- [ ] NotificaÃ§Ãµes por Discord/Webhook
- [ ] Health check de proxies antes de usar
- [ ] ImplementaÃ§Ã£o com Selenium para JS rendering

## âš–ï¸ Aviso Legal

Este script Ã© fornecido **APENAS PARA FINS EDUCACIONAIS**. Respeite os Termos de ServiÃ§o do XAT.COM e leis locais.

**Responsabilidade**: O usuÃ¡rio Ã© responsÃ¡vel pelo uso deste script. Use por sua conta e risco.

## ðŸ“ž Suporte

Para erros, verifique:
1. `criacao_contas.log` - Logs detalhados
2. Validade de emails em `data/emails.txt`
3. Conectividade dos proxies em `data/proxies.txt`
4. ConexÃ£o com internet

---

**Desenvolvido com â¤ï¸**

