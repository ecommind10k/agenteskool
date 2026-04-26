"""
Skool browser automation client - v5

Key change: community discovery uses pixel-coordinate mouse clicks instead of
JS .click() so React synthetic events fire correctly.
"""

import asyncio
import re
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Dict
from playwright.async_api import async_playwright, BrowserContext

SYSTEM_SLUGS = {
    'login', 'signup', 'profile', 'discover', 'notifications',
    'settings', 'help', 'terms', 'privacy', 'pricing', 'about',
    'careers', 'affiliate', 'new', 'search', 'blog', 'classroom',
    'feed', 'members', 'events', 'leaderboard', 'leaderboards',
    'courses', 'home', 'dashboard', 'admin', 'api', 'community',
    'groups', 'account', 'billing', 'contact', 'g', 'calendar',
}

NAV_TIMEOUT = 60_000

SKIP_ITEM_TEXTS = {
    'create a community', 'discover communities', 'search',
    '+ create', 'create', 'discover', 'invite friends',
}


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
    lessons: List[Lesson] = field(default_factory=list)


@dataclass
class Course:
    name: str
    url: str
    slug: str = ""
    modules: List[Module] = field(default_factory=list)


class SkoolClient:
    def __init__(self, email: str, password: str, headless: bool = True):
        self.email = email
        self.password = password
        self.headless = headless
        self._playwright = None
        self._browser = None
        self._context: Optional[BrowserContext] = None
        self._page = None

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
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        self._page = await self._context.new_page()
        self._page.set_default_timeout(NAV_TIMEOUT)

    async def close(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def _goto(self, url: str):
        await self._page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)

    # ------------------------------------------------------------------ #
    # Login                                                                #
    # ------------------------------------------------------------------ #

    async def login(self) -> bool:
        print("[Skool] Abriendo página de login...")
        await self._goto("https://www.skool.com/login")
        await asyncio.sleep(1)

        await self._page.fill('input[type="email"]', self.email)
        await asyncio.sleep(0.4)
        await self._page.fill('input[type="password"]', self.password)
        await asyncio.sleep(0.4)
        await self._page.click('button[type="submit"]')

        try:
            await self._page.wait_for_url(
                lambda url: "skool.com" in url and "login" not in url,
                timeout=20000,
            )
            await asyncio.sleep(3)
            print(f"[Skool] Login exitoso. URL: {self._page.url}")
            return True
        except Exception:
            content = await self._page.content()
            if "incorrect" in content.lower() or "invalid" in content.lower():
                raise ValueError("Credenciales incorrectas.")
            return True

    # ------------------------------------------------------------------ #
    # Descubrir comunidades                                                #
    # ------------------------------------------------------------------ #

    async def get_my_courses(self) -> List[Course]:
        """
        Discovers all communities.

        Strategy: open the community switcher, record pixel coordinates of
        each dropdown item, then close and reopen the switcher for every item
        and fire a real mouse click at those coordinates.  This is the most
        reliable approach for React SPAs where JS el.click() doesn't trigger
        synthetic events.
        """
        print("[Skool] Descubriendo comunidades...")

        start_url = self._page.url
        start_slug = self._slug_from_url(start_url)
        print(f"  Comunidad inicial: {start_slug}  ({start_url})")

        # ── Step 1: open switcher and record where each item is on screen ─
        item_positions = await self._open_switcher_and_get_positions()

        if not item_positions:
            print("  ⚠️  No se encontraron ítems en el dropdown.")
            return await self._fallback_single_course(start_slug)

        print(f"  {len(item_positions)} ítem(s) detectados en el switcher:")
        for txt, (cx, cy) in item_positions.items():
            print(f"    - {txt!r}  @ ({cx:.0f}, {cy:.0f})")

        # ── Step 2: collect courses by clicking each item ─────────────────
        courses: List[Course] = []
        seen_slugs: set = set()

        # Always include the starting community (already loaded, no click needed)
        if start_slug:
            seen_slugs.add(start_slug)
            title = await self._page.title()
            start_name = title.split(' - ')[0].strip()
            courses.append(Course(
                name=start_name,
                url=f"https://www.skool.com/{start_slug}/classroom",
                slug=start_slug,
            ))
            print(f"  ✅ (actual) {start_name}  →  {start_slug}")

        for item_text, (cx, cy) in item_positions.items():
            if item_text.lower() in SKIP_ITEM_TEXTS:
                continue

            # Re-open the switcher
            opened = await self._click_switcher()
            if not opened:
                print(f"  ⚠️  No pude abrir el switcher para: {item_text}")
                continue
            await asyncio.sleep(2)

            url_before = self._page.url

            # Click at the pixel coordinates we recorded earlier
            await self._page.mouse.click(cx, cy)

            # Wait for Skool to navigate to the community
            try:
                await self._page.wait_for_function(
                    f"() => window.location.href !== {repr(url_before)}",
                    timeout=7000,
                )
            except Exception:
                pass  # URL might not change if it's the current community

            await asyncio.sleep(2)
            new_url = self._page.url
            slug = self._slug_from_url(new_url)

            if slug and slug not in seen_slugs and slug not in SYSTEM_SLUGS:
                seen_slugs.add(slug)
                classroom_url = f"https://www.skool.com/{slug}/classroom"
                courses.append(Course(name=item_text, url=classroom_url, slug=slug))
                print(f"  ✅ {item_text}  →  {slug}")
            else:
                print(f"  ⚠️  Sin cambio para {item_text!r}: slug={slug!r}  url={new_url}")

        # Dismiss any lingering dropdown
        await self._page.keyboard.press("Escape")
        await asyncio.sleep(0.3)

        if not courses:
            return await self._fallback_single_course(start_slug)

        print(f"\n[Skool] Total: {len(courses)} comunidad(es) encontrada(s).")
        return courses

    async def _open_switcher_and_get_positions(self) -> Dict[str, Tuple[float, float]]:
        """
        Opens the community switcher and returns {text: (center_x, center_y)}
        for every item visible in the dropdown panel.
        """
        await self._click_switcher()
        await asyncio.sleep(2.5)   # give React time to render

        positions: Dict[str, Tuple[float, float]] = {}

        # Gather candidates from several element types
        for selector in ['a', 'li', '[role="option"]', '[role="menuitem"]', 'button']:
            try:
                elements = await self._page.query_selector_all(selector)
                for el in elements:
                    try:
                        if not await el.is_visible():
                            continue
                        box = await el.bounding_box()
                        if not box:
                            continue
                        # Switcher dropdown sits in left panel of the page
                        if (box['x'] > 520
                                or box['y'] < 50
                                or box['y'] > 800
                                or box['width'] < 40
                                or box['height'] < 15
                                or box['height'] > 110):
                            continue
                        text = (await el.inner_text()).strip().split('\n')[0].strip()
                        if text and 1 < len(text) < 120 and text not in positions:
                            cx = box['x'] + box['width'] / 2
                            cy = box['y'] + box['height'] / 2
                            positions[text] = (cx, cy)
                    except Exception:
                        continue
            except Exception:
                continue

        await self._page.keyboard.press("Escape")
        await asyncio.sleep(0.5)
        return positions

    async def _click_switcher(self) -> bool:
        """Clicks the community switcher button (top-left of the page)."""
        # Look for a button in the top-left with text + an SVG (typical for Skool)
        buttons = await self._page.query_selector_all("button")
        for btn in buttons:
            try:
                box = await btn.bounding_box()
                if not box:
                    continue
                if box['y'] > 90 or box['x'] > 520 or box['width'] < 20:
                    continue
                text = (await btn.inner_text()).strip()
                has_svg = await btn.query_selector("svg") is not None
                if text and has_svg:
                    await btn.click()
                    return True
            except Exception:
                continue

        # Fallback: click the area where the switcher normally lives
        await self._page.mouse.click(245, 50)
        return True

    def _slug_from_url(self, url: str) -> Optional[str]:
        m = re.match(r'https://www\.skool\.com/([a-z0-9][a-z0-9-]*)', url)
        if m:
            slug = m.group(1)
            if slug not in SYSTEM_SLUGS:
                return slug
        return None

    async def _fallback_single_course(self, start_slug: Optional[str]) -> List[Course]:
        if start_slug:
            title = await self._page.title()
            name = title.split(' - ')[0].strip()
            return [Course(
                name=name,
                url=f"https://www.skool.com/{start_slug}/classroom",
                slug=start_slug,
            )]
        return []

    # ------------------------------------------------------------------ #
    # Módulos y lecciones                                                  #
    # ------------------------------------------------------------------ #

    async def get_course_modules(self, course: Course) -> List[Module]:
        """
        Navigates to the course classroom.
        Skool shows MODULE CARDS at the classroom index — we click each card
        to reach the lessons inside.
        """
        print(f"\n[Skool] Classroom: {course.name}")
        await self._goto(course.url)
        await asyncio.sleep(4)
        print(f"  URL actual: {self._page.url}")

        module_links = await self._find_module_card_links(course)
        print(f"  Módulos encontrados: {len(module_links)}")
        for mod_url, mod_name in module_links:
            print(f"    → {mod_name}  ({mod_url})")

        if not module_links:
            print("  ⚠️  Sin módulos. Buscando lecciones directamente...")
            return await self._extract_lessons_as_single_module(course)

        modules: List[Module] = []
        for mod_index, (mod_url, mod_name) in enumerate(module_links):
            print(f"\n  [Módulo {mod_index+1}] {mod_name}")
            lessons = await self._get_lessons_from_module_page(
                module_url=mod_url,
                module_name=mod_name,
                course=course,
            )
            if lessons:
                print(f"    {len(lessons)} lección(es)")
                modules.append(Module(name=mod_name, lessons=lessons))
            else:
                print(f"    ⚠️  Sin lecciones")

        total = sum(len(m.lessons) for m in modules)
        print(f"\n  ✅ Total: {total} lección(es) en {len(modules)} módulo(s)")
        return modules

    async def _find_module_card_links(self, course: Course) -> List[Tuple[str, str]]:
        """
        Finds module card links at the classroom index.
        Skool module cards link to /<slug>/classroom/<module-id> (one extra segment).
        """
        slug = course.slug
        links = await self._page.evaluate(f"""
            () => {{
                const slug = {repr(slug)};
                // Match /slug/classroom/SOMETHING (exactly one more segment)
                const pattern = new RegExp(
                    '^\\\\/' + slug + '\\\\/classroom\\\\/[^/]+\\\\/?$'
                );
                const results = [];
                const seen = new Set();

                document.querySelectorAll('a[href]').forEach(a => {{
                    const href = a.getAttribute('href') || '';
                    if (pattern.test(href) && !seen.has(href)) {{
                        seen.add(href);
                        let text = '';
                        const titleEl = a.querySelector('h1,h2,h3,h4,h5,p,span');
                        if (titleEl) text = titleEl.innerText.trim().split('\\n')[0];
                        if (!text) text = a.innerText.trim().split('\\n')[0];
                        if (text) results.push({{href, text}});
                    }}
                }});
                return results;
            }}
        """)
        return [
            (f"https://www.skool.com{l['href']}", l['text'])
            for l in links if l.get('text')
        ]

    async def _get_lessons_from_module_page(
        self,
        module_url: str,
        module_name: str,
        course: Course,
    ) -> List[Lesson]:
        """Navigates to a module page and extracts lesson links."""
        await self._goto(module_url)
        await asyncio.sleep(3)

        slug = course.slug
        page_links = await self._page.evaluate(f"""
            () => {{
                const slug = {repr(slug)};
                return Array.from(document.querySelectorAll('a[href]'))
                    .map(a => ({{
                        href: a.getAttribute('href'),
                        text: (a.innerText || '').trim().slice(0, 80)
                    }}))
                    .filter(x => x.href && x.href.includes(slug));
            }}
        """)
        print(f"    [Debug] {len(page_links)} links con /{slug}/ en esta página:")
        for l in page_links[:15]:
            print(f"      {l['href']}  →  {l['text']!r}")

        module_path = module_url.replace("https://www.skool.com", "").rstrip("/")

        lessons = []
        seen_hrefs: set = set()
        position = 0

        for item in page_links:
            href = item.get('href', '')
            text = item.get('text', '').strip()
            if not href or not text or href in seen_hrefs:
                continue
            if href.rstrip("/") == module_path:
                continue
            if slug not in href:
                continue
            # Skip links that go back to the classroom index (no extra segment)
            if re.match(rf'^/{re.escape(slug)}/classroom/?$', href):
                continue

            seen_hrefs.add(href)
            full_url = f"https://www.skool.com{href}" if href.startswith("/") else href
            lessons.append(Lesson(
                title=text,
                url=full_url,
                module_name=module_name,
                course_name=course.name,
                position=position,
            ))
            position += 1

        return lessons

    async def _extract_lessons_as_single_module(self, course: Course) -> List[Module]:
        """Fallback: one module containing all lessons found on the classroom page."""
        slug = course.slug
        links = await self._page.evaluate(f"""
            () => Array.from(document.querySelectorAll('a[href]'))
                .map(a => ({{href: a.getAttribute('href'), text: (a.innerText||'').trim()}}))
                .filter(x => x.href && x.href.includes('/{slug}/classroom/') && x.text)
        """)
        module = Module(name="Contenido del Curso")
        seen: set = set()
        for i, l in enumerate(links):
            if l['href'] in seen:
                continue
            seen.add(l['href'])
            module.lessons.append(Lesson(
                title=l['text'],
                url=f"https://www.skool.com{l['href']}",
                module_name=module.name,
                course_name=course.name,
                position=i,
            ))
        return [module] if module.lessons else []

    # ------------------------------------------------------------------ #
    # Detalle de lección                                                   #
    # ------------------------------------------------------------------ #

    async def get_lesson_details(self, lesson: Lesson) -> Lesson:
        print(f"    [video] {lesson.title}")
        await self._goto(lesson.url)
        await asyncio.sleep(3)

        content = await self._page.content()
        wistia_id = self._extract_wistia_id(content)
        if wistia_id:
            lesson.wistia_id = wistia_id
        else:
            src = await self._find_video_src()
            if src:
                lesson.video_url = src

        lesson.description = await self._extract_lesson_text()
        return lesson

    def _extract_wistia_id(self, html: str) -> Optional[str]:
        for pat in [
            r'wistia\.com/medias/([a-z0-9]+)',
            r'wistia_async_([a-z0-9]+)',
            r'"hashed_id"\s*:\s*"([a-z0-9]+)"',
            r'hashedId["\s:]+([a-z0-9]{10,})',
        ]:
            m = re.search(pat, html, re.IGNORECASE)
            if m:
                return m.group(1)
        return None

    async def _find_video_src(self) -> Optional[str]:
        for sel in [
            "video source", "video[src]",
            "iframe[src*='wistia']", "iframe[src*='vimeo']", "iframe[src*='youtube']",
        ]:
            el = await self._page.query_selector(sel)
            if el:
                return await el.get_attribute("src")
        return None

    async def _extract_lesson_text(self) -> str:
        for sel in [
            "[class*='LessonContent']", "[class*='lesson-content']",
            "[class*='description']", "article", "main",
        ]:
            el = await self._page.query_selector(sel)
            if el:
                text = await el.inner_text()
                if text and len(text.strip()) > 50:
                    return text.strip()[:4000]
        return ""

    # ------------------------------------------------------------------ #
    # Pipeline completo                                                    #
    # ------------------------------------------------------------------ #

    async def scrape_all(self) -> List[Course]:
        await self.login()
        courses = await self.get_my_courses()
        for course in courses:
            modules = await self.get_course_modules(course)
            course.modules = modules
            for module in modules:
                for lesson in module.lessons:
                    await self.get_lesson_details(lesson)
        return courses
