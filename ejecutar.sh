#!/bin/bash
# ============================================================
#  Ejecutar el agente - Skool Course Summarizer
# ============================================================

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   🚀 Iniciando Skool Course Summarizer       ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "El agente va a:"
echo "  1. Entrar a tu cuenta de Skool"
echo "  2. Buscar todos tus cursos comprados"
echo "  3. Entrar a cada video y extraer la transcripción"
echo "  4. Generar un resumen PDF por cada video"
echo ""
echo "Los PDFs se guardarán en la carpeta 'output/'"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Verificar que .env existe
if [ ! -f ".env" ]; then
    echo "❌ No encuentro tu configuración."
    echo "   Primero ejecuta: ./configurar.sh"
    echo ""
    exit 1
fi

# Verificar que el entorno virtual existe
if [ ! -d "venv" ]; then
    echo "❌ No encuentro la instalación."
    echo "   Primero ejecuta: ./setup.sh"
    echo ""
    exit 1
fi

# Opción: solo un curso
if [ "$1" != "" ]; then
    echo "▸ Procesando solo el curso: $1"
    ./venv/bin/python main.py --course "$1"
else
    ./venv/bin/python main.py
fi

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   ✅ ¡Listo! Revisa la carpeta 'output/'    ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "Para abrir la carpeta con los PDFs:"
echo "  open output/"
echo ""
