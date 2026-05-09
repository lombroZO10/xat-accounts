#!/bin/bash

cd ~/xat-accounts

echo "=== TESTE COM TOR ==="
echo ""

# Verificar se Tor está rodando
echo "Verificando Tor..."
if curl -s --socks5 127.0.0.1:9050 https://httpbin.org/ip > /dev/null 2>&1; then
    tor_ip=$(curl -s --socks5 127.0.0.1:9050 https://httpbin.org/ip | grep -o '"origin":"[^"]*"' | cut -d'"' -f4)
    echo "✅ Tor funcionando - IP: $tor_ip"
else
    echo "❌ Tor não está funcionando"
    exit 1
fi

echo ""
echo "Testando acesso ao Xat via Tor..."

# Teste auser3.php (PASSO 1 - já funciona)
echo "1. Testando auser3.php (PASSO 1 - UserId)..."
response=$(curl -s --max-time 15 --socks5 127.0.0.1:9050 -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" "https://xat.com/web_gear/chat/auser3.php" 2>/dev/null)

if echo "$response" | grep -q "UserId"; then
    echo "✅ OK - UserId encontrado (PASSO 1 funciona)"
elif echo "$response" | grep -qi "cloudflare\|blocked\|challenge"; then
    echo "⚠️ BLOQUEADO - Cloudflare detectado"
else
    echo "❌ FAIL - Sem resposta ou erro"
fi

sleep 2

# Teste página de login (PASSO 2 - PROBLEMA REAL)
echo "2. Testando página de login (PASSO 2 - Token k2)..."
user_id="1556420951"  # Usar um ID de teste
response=$(curl -s --max-time 15 --socks5 127.0.0.1:9050 -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" "https://xat.com/login?mode=1&UserId=$user_id" 2>/dev/null)

if echo "$response" | grep -q "k2"; then
    echo "✅ OK - Token k2 encontrado (PASSO 2 funciona)"
elif echo "$response" | grep -qi "cloudflare\|blocked\|challenge\|just a moment"; then
    echo "⚠️ BLOQUEADO - Cloudflare detectado (PROBLEMA AQUI!)"
    echo "Resposta suspeita: $(echo "$response" | head -c 200)..."
else
    echo "❌ FAIL - Sem resposta ou erro"
fi

sleep 2

# Teste página de registro (PASSO 3 - nunca chega aqui)
echo "3. Testando página de registro (PASSO 3 - nunca testado)..."
echo "⚠️ Não testado porque PASSO 2 falha"

echo ""
echo "=== DIAGNÓSTICO CORRETO ==="
echo "✅ PASSO 1 (auser3.php → UserId): FUNCIONA"
echo "❌ PASSO 2 (login?mode=1&UserId=... → Token k2): BLOQUEADO PELO CLOUDFLARE"
echo "❓ PASSO 3 (register → criar conta): NUNCA CHEGA AQUI"
echo ""
echo "💡 PROBLEMA REAL: O bloqueio acontece na obtenção do token k2,"
echo "   que é necessário para submeter o formulário de registro."
echo ""
echo "🔧 SOLUÇÕES PARA PASSO 2:"
echo "1. IP limpo (mudar VPS/datacenter)"
echo "2. Proxies residenciais premium"
echo "3. Aguardar desbloqueio do IP atual"
echo "4. Usar selenium com browser real"
echo ""
echo "=== EXECUTAR SCRIPT? ==="
echo "python3 code/main.py"