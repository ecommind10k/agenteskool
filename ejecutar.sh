#!/bin/bash
# ============================================================
#  Ejecutar el agente - Skool Course Summarizer
# ============================================================

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   🚀 Iniciando Skool Course Summarizer       ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# Verificar instalación y configuración
if [ ! -f ".env" ]; then
    echo "❌ No encuentro tu configuración."
    echo "   Primero ejecuta: bash configurar.sh"
    echo ""
    exit 1
fi

if [ ! -d "venv" ]; then
    echo "❌ No encuentro la instalación."
    echo "   Primero ejecuta: bash setup.sh"
    echo ""
    exit 1
fi

# Mostrar qué cursos va a procesar
CURSOS_ACTIVOS=$(grep -v '^#' cursos.txt 2>/dev/null | grep -v '^$' || true)
if [ -z "$CURSOS_ACTIVOS" ]; then
    echo "📚 Cursos a procesar: TODOS los de tu cuenta"
else
    echo "📚 Cursos a procesar (según cursos.txt):"
    echo "$CURSOS_ACTIVOS" | while read -r linea; do
        echo "   ✓ $linea"
    done
fi

echo ""
echo "📁 Los PDFs se guardarán así:"
echo "   output/"
echo "   └── Nombre_del_Curso/"
echo "       ├── 01_Primer_Modulo/"
echo "       │   ├── 01_Primer_Video.pdf"
echo "       │   └── 02_Segundo_Video.pdf"
echo "       └── 02_Segundo_Modulo/"
echo "           └── 01_Video.pdf"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

./venv/bin/python main.py

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   ✅ ¡Listo! Revisa la carpeta 'output/'    ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "Para abrir la carpeta con los PDFs:"
echo "  open output/"
echo ""
