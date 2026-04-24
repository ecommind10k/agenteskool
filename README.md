# Skool Course Summarizer Agent

Agente que entra a tu cuenta de Skool, navega todos los cursos que compraste, extrae la transcripción de cada video y genera un **PDF detallado por lección** con resumen ejecutivo, conceptos clave, pasos accionables y guía de ejecución paso a paso.

## Flujo del agente

```
Tu cuenta Skool
     ↓  (Playwright — browser automation)
Cursos → Módulos → Videos
     ↓  (Wistia API / yt-dlp / Whisper)
Transcripción de cada video
     ↓  (Claude claude-sonnet-4-6)
Resumen estructurado
     ↓  (ReportLab)
PDF por lección  →  ./output/<curso>/<lección>.pdf
```

## Requisitos

- Python 3.11+
- Una cuenta en [Skool](https://www.skool.com) con cursos comprados
- API key de [Anthropic](https://console.anthropic.com) (Claude)

## Instalación

```bash
# 1. Crear entorno virtual
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Instalar Playwright browsers
playwright install chromium

# 4. Configurar credenciales
cp .env.example .env
# Editar .env con tu email, password de Skool y API key de Anthropic
```

## Configuración (.env)

```env
SKOOL_EMAIL=tu@email.com
SKOOL_PASSWORD=tu_password_de_skool
ANTHROPIC_API_KEY=sk-ant-...
OUTPUT_DIR=./output          # carpeta donde se guardan los PDFs
SUMMARY_LANGUAGE=es          # es = español, en = inglés
WHISPER_MODEL=base           # tiny/base/small/medium/large
```

## Uso

```bash
# Procesar TODOS los cursos de tu cuenta
python main.py

# Solo un curso específico
python main.py --course "Nombre del Curso"

# Ver el navegador mientras trabaja (útil para debug)
python main.py --visible

# Resumir una sola lección por URL
python main.py --lesson-url "https://www.skool.com/mi-comunidad/classroom/abc123"
```

## Output

Los PDFs se guardan en `./output/<nombre_del_curso>/`:

```
output/
└── Mi_Curso_de_Marketing/
    ├── Mi_Curso__Modulo_1__Introduccion_al_funnel.pdf
    ├── Mi_Curso__Modulo_1__Estrategia_de_contenido.pdf
    └── Mi_Curso__Modulo_2__Automatizacion.pdf
```

### Estructura de cada PDF

| Sección | Contenido |
|---|---|
| **1. Resumen Ejecutivo** | 3-5 oraciones capturando la esencia del video |
| **2. Conceptos Clave** | Ideas principales con explicación breve |
| **3. Pasos Accionables** | Acciones concretas que puedes tomar HOY |
| **4. Cómo Ejecutarlo** | Guía paso a paso con prereqs, métricas y errores comunes |
| **5. Ejemplos y Casos de Uso** | 2-3 ejemplos reales de aplicación |
| **6. Preguntas de Reflexión** | Para evaluar tu comprensión |
| **7. Recursos Mencionados** | Herramientas, libros y métodos del video |

## Extracción de transcripciones

El agente usa 3 estrategias en orden:

1. **Wistia API** (más rápido) — Skool usa Wistia para videos; se obtiene el transcript directo del JSON sin descargar nada
2. **yt-dlp subtítulos** — descarga solo los subtítulos si están disponibles
3. **Whisper** (fallback) — descarga el audio y transcribe localmente con OpenAI Whisper

Si ninguna funciona (lecciones de texto puro), usa la descripción de la lección como base.

## Costo estimado (API de Anthropic)

| Videos | Costo aprox |
|---|---|
| 10 videos (~30 min c/u) | ~$0.50 USD |
| 50 videos | ~$2.50 USD |
| 100 videos | ~$5.00 USD |

Usando `claude-sonnet-4-6` con ~20k tokens por resumen.
