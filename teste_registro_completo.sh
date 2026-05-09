#!/bin/bash

cd ~/xat-accounts

echo "=== TESTE COMPLETO DO FLUXO DE REGISTRO ==="
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
echo "🔄 Renovando circuito Tor..."
sudo killall -HUP tor 2>/dev/null || echo "Tor não foi encontrado"
sleep 3

echo ""
echo "=== SIMULAÇÃO COMPLETA DO REGISTRO ==="

# PASSO 1: Obter UserId
echo "📍 PASSO 1: Obtendo UserId..."
response1=$(curl -s --max-time 15 --socks5 127.0.0.1:9050 -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" "https://xat.com/web_gear/chat/auser3.php" 2>/dev/null)

if echo "$response1" | grep -q "UserId"; then
    user_id=$(echo "$response1" | grep -o 'UserId["\s]*[:=]["\s]*[0-9]*' | grep -o '[0-9]*' | head -1)
    echo "✅ UserId obtido: $user_id"
else
    echo "❌ Falha ao obter UserId"
    exit 1
fi

sleep 3

# PASSO 2: Obter token k2 da página de login
echo "📍 PASSO 2: Obtendo token k2..."
response2=$(curl -s --max-time 15 --socks5 127.0.0.1:9050 -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" "https://xat.com/login?mode=1&UserId=$user_id" 2>/dev/null)

if echo "$response2" | grep -q "k2"; then
    k2_token=$(echo "$response2" | grep -o 'k2["\s]*[:=]["\s]*["]*[^"]*["]*' | grep -o '["]*[^"]*["]*$' | tr -d '"' | head -1)
    echo "✅ Token k2 obtido: ${k2_token:0:20}..."
else
    echo "❌ Falha ao obter token k2 - BLOQUEADO!"
    echo "Resposta: $(echo "$response2" | head -c 150)..."
    exit 1
fi

sleep 3

# PASSO 3: Simular submissão do formulário de registro
echo "📍 PASSO 3: Testando submissão do registro..."
test_email="teste$(date +%s)@gmail.com"
test_username="testuser$(date +%s)"
test_password="TestPass123!"

# Preparar dados do formulário
form_data="username=$test_username&password=$test_password&email=$test_email&UserId=$user_id&k2=$k2_token"

echo "📝 Enviando formulário..."
echo "   Email: $test_email"
echo "   Username: $test_username"
echo "   UserId: $user_id"
echo "   k2: ${k2_token:0:20}..."

response3=$(curl -s --max-time 20 --socks5 127.0.0.1:9050 \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" \
  -H "Referer: https://xat.com/login?mode=1&UserId=$user_id" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -X POST \
  -d "$form_data" \
  "https://xat.com/register" 2>/dev/null)

# Verificar resposta do registro
if echo "$response3" | grep -qi "success\|sucesso\|welcome\|bem.vindo\|confirm\|confirme"; then
    echo "✅ REGISTRO BEM-SUCEDIDO!"
elif echo "$response3" | grep -qi "error\|erro\|failed\|falhou\|invalid\|exists\|já existe"; then
    echo "⚠️ REGISTRO FALHOU - Erro nos dados"
    echo "Resposta: $(echo "$response3" | head -c 200)..."
elif echo "$response3" | grep -qi "cloudflare\|blocked\|challenge"; then
    echo "⚠️ REGISTRO BLOQUEADO - Cloudflare"
else
    echo "❓ REGISTRO - Resposta desconhecida"
    echo "Resposta: $(echo "$response3" | head -c 200)..."
fi

echo ""
echo "=== RESULTADO FINAL ==="
echo "Se PASSO 2 falhar, o problema é o bloqueio na obtenção do token k2."
echo "Se PASSO 2 passar mas PASSO 3 falhar, o problema é no formulário de registro."