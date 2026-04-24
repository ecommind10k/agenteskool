#!/bin/bash
# ============================================================
#  Asistente de configuración - Skool Course Summarizer
# ============================================================

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   Configuración de credenciales              ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "Voy a pedirte 3 datos. Escríbelos y presiona Enter."
echo ""

# ── Email de Skool ──────────────────────────────────────────
read -p "📧 Tu email de Skool: " SKOOL_EMAIL
echo ""

# ── Password de Skool ───────────────────────────────────────
read -s -p "🔒 Tu contraseña de Skool (no se muestra al escribir): " SKOOL_PASSWORD
echo ""
echo ""

# ── API Key de Anthropic ────────────────────────────────────
echo "🤖 API Key de Anthropic (Claude)"
echo ""
echo "   Si no tienes una, sigue estos pasos:"
echo "   1. Ve a: https://console.anthropic.com"
echo "   2. Crea una cuenta gratuita"
echo "   3. Ve a 'API Keys' → 'Create Key'"
echo "   4. Copia la clave (empieza con sk-ant-...)"
echo ""
read -p "   Pega tu API Key aquí: " ANTHROPIC_API_KEY
echo ""

# ── Idioma ──────────────────────────────────────────────────
echo "🌎 ¿En qué idioma quieres los resúmenes?"
echo "   1) Español (recomendado)"
echo "   2) Inglés"
read -p "   Elige 1 o 2: " LANG_CHOICE
echo ""

if [ "$LANG_CHOICE" = "2" ]; then
    LANG="en"
else
    LANG="es"
fi

# ── Guardar .env ────────────────────────────────────────────
cat > .env <<EOF
SKOOL_EMAIL=${SKOOL_EMAIL}
SKOOL_PASSWORD=${SKOOL_PASSWORD}
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
OUTPUT_DIR=./output
SUMMARY_LANGUAGE=${LANG}
WHISPER_MODEL=base
EOF

echo "╔══════════════════════════════════════════════╗"
echo "║   ✅ Configuración guardada                  ║"
echo "║                                              ║"
echo "║   Ahora ejecuta:                             ║"
echo "║     ./ejecutar.sh                            ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
