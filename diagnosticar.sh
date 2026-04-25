#!/bin/bash
# ============================================================
#  Diagnóstico - muestra exactamente qué está fallando
# ============================================================

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   🔧 Diagnóstico del sistema                 ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

echo "▸ [1/5] Verificando Python..."
./venv/bin/python --version
echo ""

echo "▸ [2/5] Verificando librerías..."
./venv/bin/python -c "import anthropic; print('   ✅ anthropic OK')" 2>&1 || echo "   ❌ anthropic NO instalado"
./venv/bin/python -c "import playwright; print('   ✅ playwright OK')" 2>&1 || echo "   ❌ playwright NO instalado"
./venv/bin/python -c "import reportlab; print('   ✅ reportlab OK')" 2>&1 || echo "   ❌ reportlab NO instalado"
./venv/bin/python -c "import dotenv; print('   ✅ python-dotenv OK')" 2>&1 || echo "   ❌ python-dotenv NO instalado"
echo ""

echo "▸ [3/5] Verificando archivo .env..."
if [ -f ".env" ]; then
    echo "   ✅ .env existe"
    # Mostrar sin revelar contraseñas
    grep -v "PASSWORD\|API_KEY" .env | head -5
else
    echo "   ❌ .env NO existe — ejecuta: bash configurar.sh"
fi
echo ""

echo "▸ [4/5] Probando importar el agente..."
./venv/bin/python -c "
import sys
sys.path.insert(0, '.')
try:
    from src.config import config
    print('   ✅ config OK')
    print(f'   Email: {config.SKOOL_EMAIL[:4]}****')
    print(f'   API Key: {config.ANTHROPIC_API_KEY[:10]}****')
    print(f'   Cursos en cursos.txt: {config.CURSOS_INCLUIR}')
except Exception as e:
    print(f'   ❌ Error en config: {e}')

try:
    from src.skool_client import SkoolClient
    print('   ✅ SkoolClient OK')
except Exception as e:
    print(f'   ❌ Error en SkoolClient: {e}')

try:
    from src.summarizer import Summarizer
    print('   ✅ Summarizer OK')
except Exception as e:
    print(f'   ❌ Error en Summarizer: {e}')

try:
    from src.pdf_generator import PDFGenerator
    print('   ✅ PDFGenerator OK')
except Exception as e:
    print(f'   ❌ Error en PDFGenerator: {e}')
" 2>&1
echo ""

echo "▸ [5/5] Corriendo el agente (salida completa)..."
echo "   (Cualquier error aparecerá abajo)"
echo ""
./venv/bin/python -u main.py --list-courses 2>&1
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Comparte esta pantalla completa para diagnosticar."
echo ""
