#!/usr/bin/env python3
"""
Skool Course Summarizer Agent
==============================
Logs into your Skool account, navigates every course you've purchased,
extracts video transcripts, and generates a detailed PDF summary per lesson.

Usage:
    python main.py                     # full run (all courses)
    python main.py --course "Name"     # only the course matching "Name"
    python main.py --visible           # show the browser window (debug)
    python main.py --lesson-url URL    # summarize a single lesson URL
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
    p.add_argument("--course", metavar="NAME", help="Only process courses matching this name (case-insensitive)")
    p.add_argument("--visible", action="store_true", help="Show browser window (non-headless mode)")
    p.add_argument("--lesson-url", metavar="URL", help="Summarize a single lesson by its URL")
    return p.parse_args()


async def run_single_lesson(url: str, headless: bool):
    """Quick mode: summarize one lesson given its URL."""
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
    )
    pdf_path = pdf_gen.generate(summary)
    print(f"\nPDF generado: {pdf_path}")


async def run_all(args):
    orchestrator = Orchestrator(config)

    if args.course:
        # Filter courses by name after discovery
        async with SkoolClient(
            config.SKOOL_EMAIL, config.SKOOL_PASSWORD, headless=not args.visible
        ) as client:
            await client.login()
            all_courses = await client.get_my_courses()

        matching = [c for c in all_courses if args.course.lower() in c.name.lower()]
        if not matching:
            print(f"No courses found matching '{args.course}'.")
            print(f"Available courses: {[c.name for c in all_courses]}")
            sys.exit(1)

        async with SkoolClient(
            config.SKOOL_EMAIL, config.SKOOL_PASSWORD, headless=not args.visible
        ) as client:
            await client.login()
            for course in matching:
                modules = await client.get_course_modules(course)
                course.modules = modules
                for module in modules:
                    for lesson in module.lessons:
                        await client.get_lesson_details(lesson)

        from src.orchestrator import _safe
        for course in matching:
            course_dir = config.OUTPUT_DIR / _safe(course.name)
            course_dir.mkdir(parents=True, exist_ok=True)
            for module in course.modules:
                for lesson in module.lessons:
                    await orchestrator._process_lesson(lesson, course_dir)
    else:
        await orchestrator.run(headless=not args.visible)


def main():
    args = parse_args()

    print("=" * 60)
    print("  Skool Course Summarizer Agent")
    print("=" * 60)

    try:
        if args.lesson_url:
            asyncio.run(run_single_lesson(args.lesson_url, headless=not args.visible))
        else:
            asyncio.run(run_all(args))
    except ValueError as e:
        print(f"\n[Config Error] {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n[Interrupted] Stopping agent.")
        sys.exit(0)


if __name__ == "__main__":
    main()
