#!/bin/bash
# ============================================================
#  Instalador automático - Skool Course Summarizer
# ============================================================

set -e

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   Instalador - Skool Course Summarizer       ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ── Verificar Python ────────────────────────────────────────
echo "▸ Verificando Python..."
if ! command -v python3 &>/dev/null; then
    echo ""
    echo "❌ Python no está instalado."
    echo ""
    echo "   1. Abre este enlace en tu navegador:"
    echo "      https://www.python.org/downloads/macos/"
    echo "   2. Descarga e instala la versión más reciente"
    echo "   3. Vuelve a ejecutar este script"
    echo ""
    exit 1
fi

PY_VERSION=$(python3 --version 2>&1)
echo "   ✅ $PY_VERSION encontrado"

# ── Crear entorno virtual ───────────────────────────────────
echo ""
echo "▸ Creando entorno virtual..."
python3 -m venv venv
echo "   ✅ Entorno virtual creado"

# ── Instalar dependencias ───────────────────────────────────
echo ""
echo "▸ Instalando librerías (puede tardar 2-3 minutos)..."
./venv/bin/pip install --upgrade pip --quiet
./venv/bin/pip install -r requirements.txt --quiet
echo "   ✅ Librerías instaladas"

# ── Instalar Playwright (navegador automatizado) ────────────
echo ""
echo "▸ Instalando navegador automático (Chromium)..."
./venv/bin/playwright install chromium
echo "   ✅ Navegador instalado"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   ✅ Instalación completa                    ║"
echo "║                                              ║"
echo "║   Ahora ejecuta:                             ║"
echo "║     ./configurar.sh                          ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
