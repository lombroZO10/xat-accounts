#!/bin/bash

cd ~/xat-accounts

echo "=== TESTE DE FUNCIONAMENTO DO SCRIPT MODIFICADO ==="
echo ""

# Teste básico dos proxies pagos
echo "Testando proxies pagos (primeiros 3):"
head -3 data/proxies.txt | while read proxy; do
    echo "Testando $proxy..."
    if curl -s --max-time 10 --proxy "$proxy" https://httpbin.org/ip > /dev/null 2>&1; then
        ip=$(curl -s --max-time 10 --proxy "$proxy" https://httpbin.org/ip | grep -o '"origin":"[^"]*"' | cut -d'"' -f4)
        echo "✅ OK - IP: $ip"
    else
        echo "❌ FAIL"
    fi
    sleep 1
done

echo ""
echo "=== EXECUTANDO SCRIPT PYTHON (teste com 1 email) ==="

# Executar o script com timeout para não travar
timeout 300 python3 code/main.py

echo ""
echo "=== VERIFICANDO LOGS RECENTES ==="
tail -20 criacao_contas.log