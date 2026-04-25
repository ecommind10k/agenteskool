#!/bin/bash
# ============================================================
#  Ejecutar CON el navegador visible (modo debug)
# ============================================================
#  Úsalo cuando algo falla para ver exactamente qué hace
#  el agente en tu cuenta de Skool.
# ============================================================

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   🔍 Modo debug — navegador visible          ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "Se va a abrir un navegador de Chrome automático."
echo "Verás exactamente lo que hace el agente."
echo ""

if [ ! -f ".env" ]; then
    echo "❌ Primero ejecuta: bash configurar.sh"
    exit 1
fi

if [ ! -d "venv" ]; then
    echo "❌ Primero ejecuta: bash setup.sh"
    exit 1
fi

./venv/bin/python main.py --visible
