#!/usr/bin/env python3
"""
Skool Course Summarizer Agent
==============================
Logs into your Skool account, navigates every purchased course,
extracts video transcripts, and generates a detailed PDF per lesson.

Usage:
    python main.py                  # process courses listed in cursos.txt (all if empty)
    python main.py --list-courses   # just login and show your course names, then exit
    python main.py --visible        # show the browser window (useful for debugging)
    python main.py --lesson-url URL # summarize a single lesson by its Skool URL
"""

import argparse
import asyncio
import sys

from src.config import config
from src.orchestrator import Orchestrator
from src.skool_client import SkoolClient, Lesson
from src.transcript_extractor import TranscriptExtractor
from src.summarizer import Summarizer
from src.pdf_generator import PDFGenerator


def parse_args():
    p = argparse.ArgumentParser(description="Skool Course Summarizer Agent")
    p.add_argument("--list-courses", action="store_true",
                   help="Login and list available courses, then exit")
    p.add_argument("--visible", action="store_true",
                   help="Show browser window (non-headless mode)")
    p.add_argument("--lesson-url", metavar="URL",
                   help="Summarize a single lesson by its URL")
    return p.parse_args()


async def list_courses(headless: bool):
    """Login to Skool and print all enrolled courses."""
    config.validate()
    print("\nEntrando a tu cuenta de Skool...\n")
    async with SkoolClient(config.SKOOL_EMAIL, config.SKOOL_PASSWORD, headless=headless) as client:
        await client.login()
        courses = await client.get_my_courses()

    if not courses:
        print("No se encontraron cursos en tu cuenta.")
        return

    print("=" * 50)
    print(f"  Tus cursos en Skool ({len(courses)} encontrados):")
    print("=" * 50)
    for i, course in enumerate(courses, 1):
        print(f"  {i}. {course.name}")
    print("=" * 50)
    print("\nCopia los nombres que quieras procesar y")
    print("pégalos en el archivo cursos.txt (uno por línea).")
    print("\nPara editar cursos.txt:  open -e cursos.txt")
    print("Si no funciona:          nano cursos.txt\n")


async def run_single_lesson(url: str, headless: bool):
    """Summarize one lesson given its Skool URL."""
    config.validate()
    extractor = TranscriptExtractor(whisper_model=config.WHISPER_MODEL)
    summarizer = Summarizer(api_key=config.ANTHROPIC_API_KEY, language=config.SUMMARY_LANGUAGE)
    pdf_gen = PDFGenerator(output_dir=config.OUTPUT_DIR)

    async with SkoolClient(config.SKOOL_EMAIL, config.SKOOL_PASSWORD, headless=headless) as client:
        await client.login()
        lesson = Lesson(
            title="Lección única",
            url=url,
            module_name="Manual",
            course_name="Manual",
            position=0,
        )
        lesson = await client.get_lesson_details(lesson)

    transcript = await extractor.extract(
        wistia_id=lesson.wistia_id,
        video_url=lesson.video_url,
        lesson_description=lesson.description,
    )
    summary = summarizer.summarize(
        title=lesson.title or "Lección única",
        module=lesson.module_name,
        course=lesson.course_name,
        transcript=transcript,
        position=lesson.position,
    )
    pdf_path = pdf_gen.generate(summary)
    print(f"\n✅ PDF generado: {pdf_path}\n")


async def run_all(headless: bool):
    orchestrator = Orchestrator(config)
    await orchestrator.run(headless=headless)


def main():
    args = parse_args()

    print("=" * 60)
    print("  Skool Course Summarizer Agent")
    print("=" * 60)

    try:
        if args.list_courses:
            asyncio.run(list_courses(headless=not args.visible))
        elif args.lesson_url:
            asyncio.run(run_single_lesson(args.lesson_url, headless=not args.visible))
        else:
            asyncio.run(run_all(headless=not args.visible))
    except ValueError as e:
        print(f"\n❌ Error de configuración: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n[Interrumpido] Deteniendo el agente.")
        sys.exit(0)


if __name__ == "__main__":
    main()
