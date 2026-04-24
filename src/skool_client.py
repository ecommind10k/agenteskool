"""
Skool browser automation client.
Handles login, course discovery, and lesson navigation using Playwright.
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Optional
from playwright.async_api import async_playwright, Page, BrowserContext


@dataclass
class Lesson:
    title: str
    url: str
    module_name: str
    course_name: str
    position: int
    wistia_id: Optional[str] = None
    video_url: Optional[str] = None
    description: str = ""


@dataclass
class Module:
    name: str
    lessons: list[Lesson] = field(default_factory=list)


@dataclass
class Course:
    name: str
    url: str
    modules: list[Module] = field(default_factory=list)


class SkoolClient:
    def __init__(self, email: str, password: str, headless: bool = True):
        self.email = email
        self.password = password
        self.headless = headless
        self._playwright = None
        self._browser = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def start(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        self._page = await self._context.new_page()

    async def close(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def login(self) -> bool:
        print("[Skool] Navigating to login page...")
        await self._page.goto("https://www.skool.com/login", wait_until="networkidle")
        await asyncio.sleep(2)

        # Fill credentials
        await self._page.fill('input[type="email"], input[name="email"]', self.email)
        await self._page.fill('input[type="password"], input[name="password"]', self.password)
        await self._page.click('button[type="submit"]')

        # Wait for redirect after login
        try:
            await self._page.wait_for_url(
                lambda url: "skool.com" in url and "login" not in url,
                timeout=15000,
            )
            print("[Skool] Login successful.")
            return True
        except Exception:
            # Check if we're on an error page
            content = await self._page.content()
            if "incorrect" in content.lower() or "invalid" in content.lower():
                raise ValueError("Invalid Skool credentials. Check your email and password.")
            print("[Skool] Warning: could not confirm redirect after login, continuing...")
            return True

    async def get_my_courses(self) -> list[Course]:
        """Navigate to the user's courses/communities page and return all enrolled courses."""
        print("[Skool] Fetching enrolled courses...")
        await self._page.goto("https://www.skool.com/profile", wait_until="networkidle")
        await asyncio.sleep(2)

        courses: list[Course] = []

        # Look for community links — Skool groups are at skool.com/<slug>/classroom
        links = await self._page.query_selector_all("a[href*='/classroom']")
        seen_urls = set()

        for link in links:
            href = await link.get_attribute("href")
            if not href or href in seen_urls:
                continue
            seen_urls.add(href)
            text = await link.inner_text()
            full_url = (
                href if href.startswith("http") else f"https://www.skool.com{href}"
            )
            courses.append(Course(name=text.strip() or href, url=full_url))

        # Fallback: try the discover/home page
        if not courses:
            courses = await self._find_courses_from_home()

        print(f"[Skool] Found {len(courses)} course(s).")
        return courses

    async def _find_courses_from_home(self) -> list[Course]:
        """Fallback: scrape classroom links from the home feed."""
        await self._page.goto("https://www.skool.com", wait_until="networkidle")
        await asyncio.sleep(2)
        links = await self._page.query_selector_all("a[href*='/classroom']")
        courses = []
        seen = set()
        for link in links:
            href = await link.get_attribute("href")
            if not href or href in seen:
                continue
            seen.add(href)
            text = await link.inner_text()
            full_url = href if href.startswith("http") else f"https://www.skool.com{href}"
            courses.append(Course(name=text.strip() or href, url=full_url))
        return courses

    async def get_course_modules(self, course: Course) -> list[Module]:
        """Navigate to the classroom of a course and enumerate all modules and lessons."""
        print(f"[Skool] Loading classroom: {course.name}")
        await self._page.goto(course.url, wait_until="networkidle")
        await asyncio.sleep(3)

        modules: list[Module] = []

        # Skool classroom sidebar usually has module sections with lesson links
        # Try to find module headers and their child lessons
        module_elements = await self._page.query_selector_all(
            "[class*='module'], [class*='section'], [class*='unit']"
        )

        if module_elements:
            for mod_el in module_elements:
                module_name = await mod_el.inner_text()
                module_name = module_name.strip().split("\n")[0]
                module = Module(name=module_name)
                modules.append(module)
        else:
            # Fallback: single implicit module
            modules.append(Module(name="Main Content"))

        # Find all lesson links in the classroom
        lesson_links = await self._page.query_selector_all(
            "a[href*='/classroom/'], a[class*='lesson'], a[class*='video']"
        )

        position = 0
        seen_hrefs = set()
        for link in lesson_links:
            href = await link.get_attribute("href")
            if not href or href in seen_hrefs:
                continue
            # Skip the classroom index itself
            if href.rstrip("/").endswith("/classroom"):
                continue
            seen_hrefs.add(href)
            text = (await link.inner_text()).strip()
            full_url = href if href.startswith("http") else f"https://www.skool.com{href}"

            lesson = Lesson(
                title=text or f"Lesson {position + 1}",
                url=full_url,
                module_name=modules[-1].name,
                course_name=course.name,
                position=position,
            )
            modules[-1].lessons.append(lesson)
            position += 1

        # Remove empty modules
        modules = [m for m in modules if m.lessons]

        print(f"[Skool] Found {sum(len(m.lessons) for m in modules)} lessons across {len(modules)} module(s).")
        return modules

    async def get_lesson_details(self, lesson: Lesson) -> Lesson:
        """Visit a lesson page and extract video ID, description, etc."""
        print(f"  [Lesson] Loading: {lesson.title}")
        await self._page.goto(lesson.url, wait_until="networkidle")
        await asyncio.sleep(3)

        # Try to find Wistia video ID from the page source
        content = await self._page.content()
        wistia_id = self._extract_wistia_id(content)
        if wistia_id:
            lesson.wistia_id = wistia_id
            print(f"  [Lesson] Found Wistia video ID: {wistia_id}")
        else:
            # Try to find a direct video URL (e.g. mp4)
            video_src = await self._find_video_src()
            if video_src:
                lesson.video_url = video_src
                print(f"  [Lesson] Found video URL: {video_src[:60]}...")

        # Extract description / lesson text
        description = await self._extract_lesson_text()
        lesson.description = description

        return lesson

    def _extract_wistia_id(self, html: str) -> Optional[str]:
        """Extract Wistia media ID from page HTML."""
        patterns = [
            r'wistia\.com/medias/([a-z0-9]+)',
            r'wistia_async_([a-z0-9]+)',
            r'"hashed_id"\s*:\s*"([a-z0-9]+)"',
            r'embedType.*?mediaData.*?"hashedId"\s*:\s*"([a-z0-9]+)"',
            r'W\.iApi\s*\(\s*["\']([a-z0-9]+)["\']',
        ]
        for pat in patterns:
            m = re.search(pat, html, re.IGNORECASE)
            if m:
                return m.group(1)
        return None

    async def _find_video_src(self) -> Optional[str]:
        """Look for a <video> or <iframe> src on the page."""
        video_el = await self._page.query_selector("video source, video[src]")
        if video_el:
            return await video_el.get_attribute("src")
        iframe = await self._page.query_selector("iframe[src*='wistia'], iframe[src*='vimeo'], iframe[src*='youtube']")
        if iframe:
            return await iframe.get_attribute("src")
        return None

    async def _extract_lesson_text(self) -> str:
        """Extract readable text from the lesson page (description, notes, etc.)."""
        selectors = [
            "[class*='lesson-content']",
            "[class*='description']",
            "[class*='content-body']",
            "article",
            "main",
        ]
        for sel in selectors:
            el = await self._page.query_selector(sel)
            if el:
                text = await el.inner_text()
                if text and len(text.strip()) > 50:
                    return text.strip()[:4000]
        return ""

    async def scrape_all(self) -> list[Course]:
        """Full pipeline: login → get courses → get all modules and lessons."""
        await self.login()
        courses = await self.get_my_courses()

        for course in courses:
            modules = await self.get_course_modules(course)
            course.modules = modules
            for module in modules:
                for lesson in module.lessons:
                    await self.get_lesson_details(lesson)

        return courses
