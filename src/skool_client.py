"""
Skool browser automation client - v7

Estrategia para descubrir comunidades:
  1. Interceptar respuestas JSON mientras se carga la página tras el login.
     Skool hace fetch de los datos del usuario (comunidades, membresías) vía
     API REST / Next.js data.  Capturamos esas respuestas y extraemos slugs.
  2. Si la API no devuelve nada útil, buscar links <a href="/slug"> en la
     página (iconos del sidebar, etc.).
  3. Fallback: solo la comunidad actual.

Para navegar entre comunidades NO usamos el dropdown — navegamos directamente
a la URL de cada comunidad usando los slugs obtenidos en el paso anterior.
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Optional, List, Tuple
from playwright.async_api import async_playwright, BrowserContext, Response

SYSTEM_SLUGS = {
    'login', 'signup', 'profile', 'discover', 'notifications',
    'settings', 'help', 'terms', 'privacy', 'pricing', 'about',
    'careers', 'affiliate', 'new', 'search', 'blog', 'classroom',
    'feed', 'members', 'events', 'leaderboard', 'leaderboards',
    'courses', 'home', 'dashboard', 'admin', 'api', 'community',
    'groups', 'account', 'billing', 'contact', 'g', 'calendar',
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
        self._api_slugs: List[Tuple[str, str]] = []   # (slug, name)

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
    # Interceptor de respuestas API                                        #
    # ------------------------------------------------------------------ #

    def _start_api_listener(self):
        """Registra un listener que captura slugs de comunidad de las API calls."""
        self._api_slugs = []
        self._page.on("response", self._on_response)

    def _stop_api_listener(self):
        self._page.remove_listener("response", self._on_response)

    async def _on_response(self, response: Response):
        try:
            url = response.url
            if "skool.com" not in url:
                return
            ct = response.headers.get("content-type", "")
            if "json" not in ct:
                return
            data = await response.json()

            path = url.replace("https://www.skool.com", "")
            # Imprimir TODOS los endpoints JSON para ayudar a depurar
            print(f"  [API call] {path[:80]}")
            found = self._extract_slugs_from_json(data)
            if found:
                print(f"    → comunidades: {[s for s, _ in found]}")
                self._api_slugs.extend(found)
        except Exception:
            pass

    def _extract_slugs_from_json(self, data, _depth: int = 0) -> List[Tuple[str, str]]:
        """Busca recursivamente {slug, name} de comunidad en un objeto JSON."""
        if _depth > 8:
            return []
        results = []
        if isinstance(data, dict):
            # Nombres de campo que Skool podría usar para el slug
            slug = str(
                data.get("slug") or data.get("communitySlug") or
                data.get("community_slug") or data.get("domain") or
                data.get("handle") or data.get("communityDomain") or ""
            )
            name = str(
                data.get("name") or data.get("title") or
                data.get("communityName") or data.get("community_name") or ""
            )
            # Extraer slug de un campo url si lo hay
            if not slug:
                url_field = str(data.get("url") or data.get("communityUrl") or "")
                m = re.search(r'skool\.com/([a-z0-9][a-z0-9-]+)', url_field)
                if m:
                    slug = m.group(1)

            if (slug
                    and re.match(r'^[a-z0-9][a-z0-9-]{1,}$', slug)
                    and slug not in SYSTEM_SLUGS):
                results.append((slug, name or slug))
                return results
            for key in ("communities", "memberships", "member", "groups",
                        "spaces", "data", "pageProps", "props", "user",
                        "communityMember", "communityMembers", "items",
                        "results", "records", "payload"):
                if key in data:
                    results.extend(
                        self._extract_slugs_from_json(data[key], _depth + 1)
                    )
        elif isinstance(data, list):
            for item in data[:500]:
                results.extend(self._extract_slugs_from_json(item, _depth + 1))
        return results

    # ------------------------------------------------------------------ #
    # Login                                                                #
    # ------------------------------------------------------------------ #

    async def login(self) -> bool:
        print("[Skool] Abriendo página de login...")
        # Activar listener ANTES del login para capturar todas las API calls
        self._start_api_listener()

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
        except Exception:
            content = await self._page.content()
            if "incorrect" in content.lower() or "invalid" in content.lower():
                raise ValueError("Credenciales incorrectas.")

        # Esperar a que carguen las API calls post-login
        await asyncio.sleep(5)
        print(f"[Skool] Login exitoso. URL: {self._page.url}")
        return True

    # ------------------------------------------------------------------ #
    # Descubrir comunidades                                                #
    # ------------------------------------------------------------------ #

    async def get_my_courses(self) -> List[Course]:
        print("[Skool] Descubriendo comunidades...")

        # Si el listener ya estaba activo (llamado desde scrape_all),
        # detenemos y usamos lo acumulado. Si se llama suelto, hacemos
        # una recarga para capturar llamadas frescas.
        if not self._api_slugs:
            print("  Recargando página para capturar API calls...")
            await self._goto(self._page.url)
            await asyncio.sleep(5)

        self._stop_api_listener()

        # Deduplicar slugs capturados por API
        seen: set = set()
        courses: List[Course] = []

        for slug, name in self._api_slugs:
            if slug not in seen and slug not in SYSTEM_SLUGS:
                seen.add(slug)
                courses.append(Course(
                    name=name,
                    url=f"https://www.skool.com/{slug}/classroom",
                    slug=slug,
                ))

        if courses:
            print(f"  ✅ {len(courses)} comunidad(es) encontrada(s) via API:")
            for c in courses:
                print(f"    - {c.name}  ({c.slug})")
            return courses

        # ------- Fallback: links en la página con patrón /slug -----------
        print("  API no devolvió comunidades. Buscando links en la página...")
        current_slug = self._slug_from_url(self._page.url)
        page_courses = await self._courses_from_page_links(current_slug)
        if page_courses:
            print(f"  ✅ {len(page_courses)} comunidad(es) encontrada(s) via links:")
            for c in page_courses:
                print(f"    - {c.name}  ({c.slug})")
            return page_courses

        # ------- Último recurso: solo la comunidad actual ----------------
        print("  ⚠️  Solo se encontró la comunidad actual.")
        if current_slug:
            title = await self._page.title()
            name = title.split(" - ")[0].strip()
            return [Course(
                name=name,
                url=f"https://www.skool.com/{current_slug}/classroom",
                slug=current_slug,
            )]
        return []

    async def _courses_from_page_links(
        self, current_slug: Optional[str]
    ) -> List[Course]:
        """
        Extrae slugs de comunidad de CUALQUIER link en la página.
        Usa patrón amplio /slug o /slug/cualquier-cosa para capturar
        links de sidebar aunque apunten a /slug/feed, /slug/classroom, etc.
        Navega a cada slug nuevo para verificar acceso y obtener el nombre real.
        """
        raw_slugs = await self._page.evaluate(f"""
            () => {{
                const sysslugs = new Set({list(SYSTEM_SLUGS)});
                const slugs = new Set();
                // Buscar en <a href> y también en atributos data-href
                document.querySelectorAll('[href], [data-href]').forEach(el => {{
                    const href = (
                        el.getAttribute('href') || el.getAttribute('data-href') || ''
                    ).split('?')[0].split('#')[0];
                    // /slug  o  /slug/cualquier-cosa
                    const m = href.match(/^\\/([a-z0-9][a-z0-9-]{{2,}})(?:\\/|$)/);
                    if (m && !sysslugs.has(m[1])) slugs.add(m[1]);
                }});
                return Array.from(slugs);
            }}
        """)

        print(f"  Slugs en la página: {raw_slugs}")

        courses: List[Course] = []
        seen: set = set()

        # Comunidad actual (ya estamos aquí, no necesitamos navegar)
        if current_slug:
            seen.add(current_slug)
            title = await self._page.title()
            name = title.split(" - ")[0].split(" | ")[0].strip() or current_slug
            courses.append(Course(
                name=name,
                url=f"https://www.skool.com/{current_slug}/classroom",
                slug=current_slug,
            ))
            print(f"  ✅ {name}  ({current_slug})")

        # Para cada slug nuevo, navegar y verificar que es una comunidad accesible
        for slug in raw_slugs:
            if slug in seen:
                continue
            seen.add(slug)
            try:
                await self._goto(f"https://www.skool.com/{slug}/classroom")
                await asyncio.sleep(2)
                landed = self._page.url
                landed_slug = self._slug_from_url(landed)
                # Si no llegamos al slug esperado, no tenemos acceso
                if landed_slug != slug:
                    print(f"  ⚠️  {slug}: sin acceso (redirigió a {landed[:50]})")
                    continue
                title = await self._page.title()
                name = title.split(" - ")[0].split(" | ")[0].strip() or slug
                courses.append(Course(
                    name=name,
                    url=f"https://www.skool.com/{slug}/classroom",
                    slug=slug,
                ))
                print(f"  ✅ {name}  ({slug})")
            except Exception as e:
                print(f"  ⚠️  Error verificando {slug}: {e}")

        # Volver a la comunidad inicial para que el resto del flujo funcione
        if current_slug and courses:
            await self._goto(f"https://www.skool.com/{current_slug}/classroom")
            await asyncio.sleep(2)

        return courses

    def _slug_from_url(self, url: str) -> Optional[str]:
        m = re.match(r'https://www\.skool\.com/([a-z0-9][a-z0-9-]*)', url)
        if m:
            slug = m.group(1)
            if slug not in SYSTEM_SLUGS:
                return slug
        return None

    # ------------------------------------------------------------------ #
    # Módulos y lecciones                                                  #
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
            print("  ⚠️  Sin tarjetas de módulo. Buscando lecciones directamente...")
            return await self._extract_lessons_as_single_module(course)

        modules: List[Module] = []
        for mod_index, (mod_url, mod_name) in enumerate(module_links):
            print(f"\n  [Módulo {mod_index+1}] {mod_name}")
            lessons = await self._get_lessons_from_module_page(
                mod_url, mod_name, course
            )
            if lessons:
                print(f"    {len(lessons)} lección(es)")
                modules.append(Module(name=mod_name, lessons=lessons))
            else:
                print("    ⚠️  Sin lecciones")

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
                        const h = a.querySelector('h1,h2,h3,h4,h5,p,span');
                        if (h) text = h.innerText.trim().split('\\n')[0];
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
            full_url = (f"https://www.skool.com{href}"
                        if href.startswith("/") else href)
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
                .map(a => ({{href: a.getAttribute('href'),
                             text: (a.innerText||'').trim()}}))
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
        # El listener de API se activa dentro de login()
        await self.login()
        courses = await self.get_my_courses()
        for course in courses:
            modules = await self.get_course_modules(course)
            course.modules = modules
            for module in modules:
                for lesson in module.lessons:
                    await self.get_lesson_details(lesson)
        return courses
