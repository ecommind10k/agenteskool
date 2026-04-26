#!/bin/bash
# ============================================================
#  Actualizar código - Skool Course Summarizer
# ============================================================

BRANCH="claude/skool-course-summarizer-YeXyU"
REPO="https://github.com/ecommind10k/agenteskool.git"
RAW="https://raw.githubusercontent.com/ecommind10k/agenteskool/$BRANCH"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   Actualizando Skool Course Summarizer       ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ── Método 1: git (más rápido y confiable) ─────────────────
if command -v git &>/dev/null; then
    echo "▸ Descargando última versión con git..."

    if [ ! -d ".git" ]; then
        git init -q
        git remote add origin "$REPO"
    fi

    # Asegurarse de que el remote apunta al repo correcto
    git remote set-url origin "$REPO" 2>/dev/null || true

    # Descargar cambios sin tocar .env ni cursos.txt
    git fetch -q origin "$BRANCH" 2>&1
    FETCH_EXIT=$?

    if [ $FETCH_EXIT -eq 0 ]; then
        # Solo actualiza archivos de código (nunca .env ni cursos.txt)
        git checkout "origin/$BRANCH" -- \
            main.py \
            requirements.txt \
            setup.sh \
            configurar.sh \
            ejecutar.sh \
            ejecutar_visible.sh \
            listar_cursos.sh \
            diagnosticar.sh \
            actualizar.sh \
            src/ 2>&1

        echo "   ✅ Código actualizado desde GitHub"
        echo ""
        echo "╔══════════════════════════════════════════════╗"
        echo "║   ✅ Listo. Ya tienes la última versión.     ║"
        echo "║                                              ║"
        echo "║   Para probar ejecuta:                       ║"
        echo "║     bash ejecutar_visible.sh                 ║"
        echo "╚══════════════════════════════════════════════╝"
        echo ""
        exit 0
    else
        echo "   ⚠️  No se pudo conectar con GitHub via git."
        echo "      Intentando con curl..."
    fi
fi

# ── Método 2: curl (fallback si git no está disponible) ────
echo "▸ Descargando archivos con curl..."

FILES=(
    "main.py"
    "requirements.txt"
    "setup.sh"
    "configurar.sh"
    "ejecutar.sh"
    "ejecutar_visible.sh"
    "listar_cursos.sh"
    "diagnosticar.sh"
    "actualizar.sh"
    "src/__init__.py"
    "src/config.py"
    "src/orchestrator.py"
    "src/pdf_generator.py"
    "src/skool_client.py"
    "src/summarizer.py"
    "src/transcript_extractor.py"
)

SUCCESS=0
FAIL=0

mkdir -p src

for FILE in "${FILES[@]}"; do
    HTTP_CODE=$(curl -s -w "%{http_code}" -o "$FILE" "$RAW/$FILE")
    if [ "$HTTP_CODE" = "200" ]; then
        SUCCESS=$((SUCCESS + 1))
    else
        echo "   ❌ Error al descargar $FILE (HTTP $HTTP_CODE)"
        FAIL=$((FAIL + 1))
    fi
done

echo ""
if [ $FAIL -eq 0 ]; then
    echo "╔══════════════════════════════════════════════╗"
    echo "║   ✅ Listo. Ya tienes la última versión.     ║"
    echo "║                                              ║"
    echo "║   Para probar ejecuta:                       ║"
    echo "║     bash ejecutar_visible.sh                 ║"
    echo "╚══════════════════════════════════════════════╝"
else
    echo "╔══════════════════════════════════════════════╗"
    echo "║   ⚠️  Algunos archivos no se actualizaron.   ║"
    echo "║                                              ║"
    echo "║   Verifica tu conexión a internet y          ║"
    echo "║   vuelve a ejecutar: bash actualizar.sh      ║"
    echo "╚══════════════════════════════════════════════╝"
fi
echo ""
