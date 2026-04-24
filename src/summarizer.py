"""
Claude-powered summarizer.

For each video transcript it generates a structured summary in the configured
language with: overview, key concepts, actionable steps, and execution guide.
"""

import anthropic
from dataclasses import dataclass

SUMMARY_PROMPT_ES = """Eres un experto en síntesis de conocimiento y aprendizaje accionable.

A continuación te comparto la transcripción de una lección de un curso online titulada:
**"{title}"**
(Módulo: {module} | Curso: {course})

---TRANSCRIPCIÓN---
{transcript}
---FIN TRANSCRIPCIÓN---

Genera un resumen DETALLADO y ACCIONABLE en español con las siguientes secciones. Usa markdown con headers ##:

## 1. Resumen Ejecutivo
Un párrafo de 3-5 oraciones que capture la esencia de la lección. ¿Qué problema resuelve y por qué importa?

## 2. Conceptos Clave
Lista con viñetas de los conceptos, frameworks o ideas principales explicadas en la lección. Explica cada uno brevemente (2-4 oraciones).

## 3. Pasos Accionables
Lista numerada de acciones concretas que el estudiante puede ejecutar HOY basándose en lo aprendido. Sé específico (evita "aprende más sobre X", en cambio di "haz X usando Y en Z minutos").

## 4. Cómo Ejecutarlo (Guía Paso a Paso)
Guía detallada de implementación. Incluye:
- Prerequisitos o herramientas necesarias
- Pasos ordenados con detalles prácticos
- Métricas o indicadores de éxito
- Errores comunes a evitar

## 5. Ejemplos y Casos de Uso
2-3 ejemplos concretos de cómo aplicar lo aprendido en situaciones reales.

## 6. Preguntas de Reflexión
3-5 preguntas para que el estudiante evalúe su comprensión y planifique su aplicación.

## 7. Recursos Mencionados
Lista cualquier herramienta, libro, método o recurso mencionado en la lección.

Sé exhaustivo, claro y orientado a la acción. El resumen debe ser útil como referencia futura sin necesidad de volver a ver el video."""

SUMMARY_PROMPT_EN = """You are an expert in knowledge synthesis and actionable learning.

Below is the transcript of an online course lesson titled:
**"{title}"**
(Module: {module} | Course: {course})

---TRANSCRIPT---
{transcript}
---END TRANSCRIPT---

Generate a DETAILED and ACTIONABLE summary in English with the following sections. Use markdown with ## headers:

## 1. Executive Summary
A 3-5 sentence paragraph capturing the essence of the lesson. What problem does it solve and why does it matter?

## 2. Key Concepts
Bulleted list of main concepts, frameworks, or ideas explained. Briefly explain each (2-4 sentences).

## 3. Actionable Steps
Numbered list of concrete actions the student can take TODAY based on what they learned. Be specific (avoid "learn more about X", instead say "do X using Y in Z minutes").

## 4. How to Execute It (Step-by-Step Guide)
Detailed implementation guide including:
- Prerequisites or tools needed
- Ordered steps with practical details
- Success metrics or indicators
- Common mistakes to avoid

## 5. Examples and Use Cases
2-3 concrete examples of how to apply what was learned in real situations.

## 6. Reflection Questions
3-5 questions for the student to assess their understanding and plan their application.

## 7. Resources Mentioned
List any tools, books, methods, or resources mentioned in the lesson.

Be thorough, clear, and action-oriented. The summary should serve as a useful future reference without needing to re-watch the video."""


@dataclass
class LessonSummary:
    course_name: str
    module_name: str
    lesson_title: str
    content: str  # Full markdown summary
    transcript_length: int
    model_used: str


class Summarizer:
    MODEL = "claude-sonnet-4-6"
    MAX_TRANSCRIPT_CHARS = 80_000  # ~20k tokens; keeps cost reasonable

    def __init__(self, api_key: str, language: str = "es"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.language = language
        self._prompt_template = (
            SUMMARY_PROMPT_ES if language == "es" else SUMMARY_PROMPT_EN
        )

    def summarize(
        self,
        title: str,
        module: str,
        course: str,
        transcript: str,
    ) -> LessonSummary:
        """Generate a structured summary using Claude. Synchronous."""
        if not transcript.strip():
            transcript = "(No hay transcripción disponible para esta lección.)"

        # Trim transcript if too long
        trimmed = transcript[: self.MAX_TRANSCRIPT_CHARS]
        if len(transcript) > self.MAX_TRANSCRIPT_CHARS:
            trimmed += "\n[... transcripción truncada por longitud ...]"

        prompt = self._prompt_template.format(
            title=title,
            module=module,
            course=course,
            transcript=trimmed,
        )

        print(f"  [Claude] Generating summary for: {title}")
        message = self.client.messages.create(
            model=self.MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        content = message.content[0].text

        return LessonSummary(
            course_name=course,
            module_name=module,
            lesson_title=title,
            content=content,
            transcript_length=len(transcript),
            model_used=self.MODEL,
        )
