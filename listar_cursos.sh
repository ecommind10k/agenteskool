#!/bin/bash
# ============================================================
#  Listar tus cursos de Skool
# ============================================================
#  Úsalo ANTES de configurar cursos.txt para ver exactamente
#  cómo se llaman tus cursos en Skool.
# ============================================================

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   🔍 Listando tus cursos de Skool            ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

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

./venv/bin/python main.py --list-courses

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Copia los nombres exactos que quieras procesar"
echo "y pégalos en el archivo cursos.txt (uno por línea)."
echo ""
echo "Para abrir cursos.txt:"
echo "  open cursos.txt"
echo ""
