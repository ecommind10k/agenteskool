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

# Verificar que las dependencias están instaladas
echo "▸ Verificando dependencias..."
if ! ./venv/bin/python -c "import anthropic, playwright, reportlab" 2>/dev/null; then
    echo "❌ Faltan librerías. Ejecuta: bash setup.sh"
    echo ""
    exit 1
fi
echo "   ✅ Todo instalado correctamente"
echo ""

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

# Ejecutar el agente y capturar el código de salida
./venv/bin/python main.py
EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    # Verificar si realmente se crearon PDFs
    PDF_COUNT=$(find output/ -name "*.pdf" 2>/dev/null | wc -l | tr -d ' ')
    if [ "$PDF_COUNT" -gt "0" ]; then
        echo "╔══════════════════════════════════════════════╗"
        echo "║   ✅ ¡Listo! Se generaron $PDF_COUNT PDF(s)              ║"
        echo "╚══════════════════════════════════════════════╝"
        echo ""
        echo "Para abrir la carpeta con los PDFs:"
        echo "  open output/"
        echo ""
        open output/
    else
        echo "⚠️  El agente terminó pero no generó PDFs."
        echo ""
        echo "Posibles causas:"
        echo "  1. Las credenciales de Skool son incorrectas"
        echo "  2. Los nombres en cursos.txt no coinciden con Skool"
        echo "  3. Los cursos no tienen videos accesibles"
        echo ""
        echo "Prueba ejecutar con el navegador visible para ver qué pasa:"
        echo "  bash ejecutar_visible.sh"
    fi
else
    echo "❌ El agente encontró un error (código $EXIT_CODE)."
    echo ""
    echo "Revisa los mensajes de error arriba para más detalles."
    echo "Si el error dice 'Invalid credentials', vuelve a ejecutar:"
    echo "  bash configurar.sh"
fi
