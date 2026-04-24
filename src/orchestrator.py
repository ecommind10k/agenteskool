"""
Main orchestrator.

Wires together:
  SkoolClient → TranscriptExtractor → Summarizer → PDFGenerator

Produces one PDF per lesson in the output directory.
"""

import asyncio
from pathlib import Path

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
        """Full pipeline. Returns list of generated PDF paths."""
        self.config.validate()

        async with SkoolClient(
            email=self.config.SKOOL_EMAIL,
            password=self.config.SKOOL_PASSWORD,
            headless=headless,
        ) as client:
            courses = await client.scrape_all()

        if not courses:
            print("[Orchestrator] No courses found. Check your Skool account.")
            return []

        for course in courses:
            course_dir = self.config.OUTPUT_DIR / _safe(course.name)
            course_dir.mkdir(parents=True, exist_ok=True)
            print(f"\n{'='*60}")
            print(f"COURSE: {course.name}")
            print(f"{'='*60}")

            for module in course.modules:
                print(f"\n  MODULE: {module.name}")
                for lesson in module.lessons:
                    pdf_path = await self._process_lesson(lesson, course_dir)
                    if pdf_path:
                        self._generated.append(pdf_path)

        print(f"\n[Done] Generated {len(self._generated)} PDF(s) in {self.config.OUTPUT_DIR}")
        return self._generated

    async def _process_lesson(self, lesson: Lesson, output_dir: Path) -> Path | None:
        try:
            print(f"\n  → {lesson.title}")

            # 1. Get transcript
            transcript = await self.extractor.extract(
                wistia_id=lesson.wistia_id,
                video_url=lesson.video_url,
                lesson_description=lesson.description,
            )

            # 2. Summarize with Claude
            summary = self.summarizer.summarize(
                title=lesson.title,
                module=lesson.module_name,
                course=lesson.course_name,
                transcript=transcript,
            )

            # 3. Generate PDF inside the course directory
            self.pdf_gen.output_dir = output_dir
            pdf_path = self.pdf_gen.generate(summary)
            return pdf_path

        except Exception as e:
            print(f"  [ERROR] Failed to process '{lesson.title}': {e}")
            return None


def _safe(name: str) -> str:
    import re
    name = re.sub(r'[^\w\s-]', '', name)
    return re.sub(r'\s+', '_', name.strip())[:60]
