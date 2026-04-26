"""
Main orchestrator.

Folder structure produced:
  output/
  └── Nombre_del_Curso/
      ├── 01_Modulo_Uno/
      │   ├── 01_Intro.pdf
      │   └── 02_Segunda_Leccion.pdf
      └── 02_Modulo_Dos/
          └── 01_Otra_Leccion.pdf
"""

import asyncio
from pathlib import Path
from typing import Optional

from .config import Config
from .skool_client import SkoolClient, Course, Lesson
from .transcript_extractor import TranscriptExtractor
from .summarizer import Summarizer
from .pdf_generator import PDFGenerator


class Orchestrator:
    def __init__(self, config: Config):
        self.config = config
        self.extractor = TranscriptExtractor(whisper_model=config.WHISPER_MODEL)
        self.summarizer = Summarizer(
            api_key=config.ANTHROPIC_API_KEY,
            language=config.SUMMARY_LANGUAGE,
        )
        self.pdf_gen = PDFGenerator(output_dir=config.OUTPUT_DIR)
        self._generated: list[Path] = []

    async def run(self, headless: bool = True) -> list[Path]:
        self.config.validate()

        async with SkoolClient(
            email=self.config.SKOOL_EMAIL,
            password=self.config.SKOOL_PASSWORD,
            headless=headless,
        ) as client:
            # El filtro se aplica dentro de scrape_all ANTES de visitar classrooms
            courses = await client.scrape_all(
                cursos_incluir=self.config.CURSOS_INCLUIR or None
            )

        if not courses:
            print("[Orchestrator] No se encontraron cursos en tu cuenta de Skool.")
            return []

        for course in courses:
            course_dir = self.config.OUTPUT_DIR / _safe(course.name)
            course_dir.mkdir(parents=True, exist_ok=True)

            print(f"\n{'='*60}")
            print(f"CURSO: {course.name}")
            print(f"  {sum(len(m.lessons) for m in course.modules)} videos en {len(course.modules)} módulos")
            print(f"{'='*60}")

            for mod_index, module in enumerate(course.modules, start=1):
                # One folder per module: 01_Nombre_Modulo/
                module_dir = course_dir / f"{mod_index:02d}_{_safe(module.name)}"
                module_dir.mkdir(parents=True, exist_ok=True)

                print(f"\n  MÓDULO {mod_index}: {module.name} ({len(module.lessons)} videos)")

                for lesson in module.lessons:
                    pdf_path = await self._process_lesson(lesson, module_dir)
                    if pdf_path:
                        self._generated.append(pdf_path)

        print(f"\n{'='*60}")
        print(f"✅ Listo — {len(self._generated)} PDF(s) generados en {self.config.OUTPUT_DIR}")
        print(f"{'='*60}\n")
        return self._generated

    async def _process_lesson(self, lesson: Lesson, module_dir: Path) -> Optional[Path]:
        try:
            print(f"\n    → [{lesson.position + 1}] {lesson.title}")

            transcript = await self.extractor.extract(
                wistia_id=lesson.wistia_id,
                video_url=lesson.video_url,
                lesson_description=lesson.description,
            )

            summary = self.summarizer.summarize(
                title=lesson.title,
                module=lesson.module_name,
                course=lesson.course_name,
                transcript=transcript,
                position=lesson.position,
            )

            self.pdf_gen.output_dir = module_dir
            pdf_path = self.pdf_gen.generate(summary)
            return pdf_path

        except Exception as e:
            print(f"    [ERROR] No se pudo procesar '{lesson.title}': {e}")
            return None


def _filter_courses(courses: list[Course], include: list[str]) -> list[Course]:
    if not include:
        return courses
    filtered = []
    for course in courses:
        for name in include:
            if name.lower() in course.name.lower():
                filtered.append(course)
                break
    if not filtered:
        print("\n⚠️  Ningún curso coincide con los nombres en cursos.txt.")
        print("   Cursos disponibles:")
        for c in courses:
            print(f"     - {c.name}")
        print("   Ajusta cursos.txt o ejecuta: bash listar_cursos.sh\n")
    return filtered


def _safe(name: str) -> str:
    import re
    name = re.sub(r'[^\w\s-]', '', name)
    return re.sub(r'\s+', '_', name.strip())[:60]
