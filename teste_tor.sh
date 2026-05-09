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

# Teste auser3.php
echo "1. Testando auser3.php..."
response=$(curl -s --max-time 15 --socks5 127.0.0.1:9050 -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" "https://xat.com/web_gear/chat/auser3.php" 2>/dev/null)

if echo "$response" | grep -q "UserId"; then
    echo "✅ OK - UserId encontrado"
elif echo "$response" | grep -qi "cloudflare\|blocked\|challenge"; then
    echo "⚠️ BLOQUEADO - Cloudflare detectado"
else
    echo "❌ FAIL - Sem resposta ou erro"
fi

sleep 2

# Teste página de login (simulada)
echo "2. Testando página de login..."
user_id="1556420951"  # Usar um ID de teste
response=$(curl -s --max-time 15 --socks5 127.0.0.1:9050 -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" "https://xat.com/login?mode=1&UserId=$user_id" 2>/dev/null)

if echo "$response" | grep -q "k2"; then
    echo "✅ OK - Token k2 encontrado"
elif echo "$response" | grep -qi "cloudflare\|blocked\|challenge\|checking your browser"; then
    echo "⚠️ BLOQUEADO - Cloudflare detectado"
    echo "Resposta suspeita: $(echo "$response" | head -c 200)..."
else
    echo "❌ FAIL - Sem resposta ou erro"
fi

echo ""
echo "=== DIAGNÓSTICO ==="
echo "Se ambos os testes falham, o IP do VPS está banido no Xat."
echo "Isso é comum com VPS de datacenters baratos."
echo ""
echo "💡 SOLUÇÕES:"
echo "1. Mudar de VPS/datacenter (AWS, DigitalOcean, Linode)"
echo "2. Usar proxies residenciais premium"
echo "3. Aguardar 24-48h (ban temporário)"
echo "4. Usar IP dedicado limpo"
echo ""
echo "=== EXECUTAR SCRIPT? ==="
echo "python3 code/main.py"