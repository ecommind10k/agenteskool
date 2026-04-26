"""
Skool browser automation client - v6

Community discovery:
  1. Snapshot all text elements before clicking the switcher.
  2. Click the switcher button (found by current community name text).
  3. DOM-diff: any NEW text element that appeared is a dropdown item.
  4. For each item click via Playwright get_by_text (fires React events).
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

SKIP_ITEM_TEXTS = {
    'create a community', 'discover communities', 'search',
    '+ create', 'create', 'discover', 'invite friends',
}

NAV_TIMEOUT = 60_000


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
    # Community discovery                                                  #
    # ------------------------------------------------------------------ #

    async def get_my_courses(self) -> List[Course]:
        print("[Skool] Descubriendo comunidades...")

        start_url = self._page.url
        start_slug = self._slug_from_url(start_url)
        print(f"  URL: {start_url}  slug: {start_slug}")

        # Always include the community we landed on
        courses: List[Course] = []
        seen_slugs: set = set()
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

        # --- Step 1: snapshot what text is already on the page ----------
        texts_before = set(await self._page.evaluate("""
            () => {
                const out = [];
                document.querySelectorAll('*').forEach(el => {
                    const t = (el.innerText || '').trim().split('\\n')[0].slice(0, 100);
                    if (t && t.length > 1) out.push(t);
                });
                return out;
            }
        """))

        # --- Step 2: click the community switcher ----------------------
        switcher_pos = await self._find_switcher_position(start_slug)
        print(f"  Switcher click → ({switcher_pos[0]:.0f}, {switcher_pos[1]:.0f})")
        await self._page.mouse.click(switcher_pos[0], switcher_pos[1])
        await asyncio.sleep(3)

        # --- Step 3: DOM diff — find new elements ----------------------
        new_items = await self._page.evaluate(f"""
            () => {{
                const before = new Set({list(texts_before)});
                const results = [];
                const seen = new Set();

                document.querySelectorAll('*').forEach(el => {{
                    const text = (el.innerText || '').trim().split('\\n')[0].slice(0, 100);
                    if (!text || text.length < 2 || text.length > 100) return;
                    if (before.has(text) || seen.has(text)) return;

                    const rect = el.getBoundingClientRect();
                    if (rect.width < 20 || rect.height < 10 || rect.height > 200) return;
                    if (rect.x < 0 || rect.y < 0 || rect.x > 1280 || rect.y > 900) return;

                    seen.add(text);
                    results.push({{
                        text,
                        cx: Math.round(rect.x + rect.width / 2),
                        cy: Math.round(rect.y + rect.height / 2),
                        tag: el.tagName.toLowerCase(),
                        x: Math.round(rect.x),
                        y: Math.round(rect.y),
                    }});
                }});

                results.sort((a, b) => a.y - b.y);
                return results;
            }}
        """)

        print(f"  {len(new_items)} elemento(s) nuevos tras abrir el switcher:")
        for item in new_items[:30]:
            print(f"    [{item['tag']:6s}] {item['text']!r:55s} @ ({item['x']}, {item['y']})")

        if not new_items:
            print("  ⚠️  No apareció ningún elemento nuevo — el dropdown no se abrió.")
            print("       Intenta ejecutar con --visible para ver qué sucede.")
            await self._page.keyboard.press("Escape")
            return courses

        # --- Step 4: click each new community item ---------------------
        # Close dropdown first, then reopen for each click
        await self._page.keyboard.press("Escape")
        await asyncio.sleep(0.5)

        for item in new_items:
            text = item['text']
            if text.lower() in SKIP_ITEM_TEXTS:
                continue

            # Re-open switcher
            await self._page.mouse.click(switcher_pos[0], switcher_pos[1])
            await asyncio.sleep(2)

            url_before = self._page.url

            # Click the item — try get_by_text first (fires React events)
            clicked = await self._click_item_by_text(text, item['cx'], item['cy'])
            if not clicked:
                await self._page.keyboard.press("Escape")
                continue

            # Wait for navigation
            try:
                await self._page.wait_for_function(
                    f"() => window.location.href !== {repr(url_before)}",
                    timeout=6000,
                )
            except Exception:
                pass

            await asyncio.sleep(2)
            new_url = self._page.url
            slug = self._slug_from_url(new_url)

            if slug and slug not in seen_slugs and slug not in SYSTEM_SLUGS:
                seen_slugs.add(slug)
                courses.append(Course(
                    name=text,
                    url=f"https://www.skool.com/{slug}/classroom",
                    slug=slug,
                ))
                print(f"  ✅ {text}  →  {slug}")
            else:
                print(f"  ⚠️  {text!r}: slug={slug!r}  url={new_url[:60]}")

        await self._page.keyboard.press("Escape")
        await asyncio.sleep(0.3)

        print(f"\n[Skool] Total: {len(courses)} comunidad(es) encontrada(s).")
        return courses

    async def _find_switcher_position(
        self, current_slug: Optional[str]
    ) -> Tuple[float, float]:
        """
        Find the community switcher button by locating the element that
        contains the current community's slug text near the top of the page.
        Returns (cx, cy) to click.
        """
        slug_key = (current_slug or "").lower().replace("-", "")

        if len(slug_key) >= 4:
            pos = await self._page.evaluate(f"""
                () => {{
                    const key = {repr(slug_key)};
                    let best = null;
                    let bestArea = Infinity;

                    document.querySelectorAll('*').forEach(el => {{
                        if (['SCRIPT','STYLE','HEAD','HTML','BODY'].includes(el.tagName)) return;
                        const rect = el.getBoundingClientRect();
                        // Must be in top 150 px and left 700 px
                        if (rect.y > 150 || rect.x > 700) return;
                        if (rect.width < 20 || rect.height < 12) return;

                        const raw = (el.innerText || el.textContent || '')
                            .toLowerCase().replace(/[^a-z0-9]/g, '');
                        if (raw.includes(key)) {{
                            const area = rect.width * rect.height;
                            // prefer smallest matching element
                            if (area < bestArea) {{
                                bestArea = area;
                                best = {{
                                    x: rect.x + rect.width / 2,
                                    y: rect.y + rect.height / 2,
                                }};
                            }}
                        }}
                    }});
                    return best;
                }}
            """)
            if pos:
                return (pos['x'], pos['y'])

        # Fallback: top-left area where Skool's switcher typically lives
        return (100.0, 50.0)

    async def _click_item_by_text(self, text: str, cx: float, cy: float) -> bool:
        """Click a dropdown item. Tries get_by_text first (React-safe), then coords."""
        # Playwright's get_by_text fires real pointer/mouse events
        try:
            loc = self._page.get_by_text(text, exact=True)
            count = await loc.count()
            for i in range(min(count, 5)):
                el = loc.nth(i)
                if await el.is_visible():
                    await el.click()
                    return True
        except Exception:
            pass

        # Partial match fallback
        try:
            loc = self._page.get_by_text(text[:30])
            count = await loc.count()
            for i in range(min(count, 5)):
                el = loc.nth(i)
                if await el.is_visible():
                    box = await el.bounding_box()
                    if box and abs(box['x'] + box['width'] / 2 - cx) < 300:
                        await el.click()
                        return True
        except Exception:
            pass

        # Last resort: coordinate click
        await self._page.mouse.click(cx, cy)
        return True

    def _slug_from_url(self, url: str) -> Optional[str]:
        m = re.match(r'https://www\.skool\.com/([a-z0-9][a-z0-9-]*)', url)
        if m:
            slug = m.group(1)
            if slug not in SYSTEM_SLUGS:
                return slug
        return None

    # ------------------------------------------------------------------ #
    # Modules & lessons                                                    #
    # ------------------------------------------------------------------ #

    async def get_course_modules(self, course: Course) -> List[Module]:
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
            lessons = await self._get_lessons_from_module_page(mod_url, mod_name, course)
            if lessons:
                print(f"    {len(lessons)} lección(es)")
                modules.append(Module(name=mod_name, lessons=lessons))
            else:
                print(f"    ⚠️  Sin lecciones")

        total = sum(len(m.lessons) for m in modules)
        print(f"\n  ✅ Total: {total} lección(es) en {len(modules)} módulo(s)")
        return modules

    async def _find_module_card_links(self, course: Course) -> List[Tuple[str, str]]:
        slug = course.slug
        links = await self._page.evaluate(f"""
            () => {{
                const slug = {repr(slug)};
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
        self, module_url: str, module_name: str, course: Course
    ) -> List[Lesson]:
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
        print(f"    [Debug] {len(page_links)} links con /{slug}/:")
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
            if re.match(rf'^/{re.escape(slug)}/classroom/?$', href):
                continue

            seen_hrefs.add(href)
            full_url = f"https://www.skool.com{href}" if href.startswith("/") else href
            lessons.append(Lesson(
                title=text, url=full_url,
                module_name=module_name, course_name=course.name,
                position=position,
            ))
            position += 1

        return lessons

    async def _extract_lessons_as_single_module(self, course: Course) -> List[Module]:
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
    # Lesson detail                                                        #
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
    # Full pipeline                                                        #
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
