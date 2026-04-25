"""
Skool browser automation client - v3
Estrategia:
  - Descubrir comunidades buscando slugs válidos en la home (/slug sin subdirectorio)
  - Extraer módulos y lecciones con JavaScript para leer el DOM completo
  - Expandir módulos colapsados antes de extraer lecciones
"""

import asyncio
import re
from dataclasses import dataclass, field
from typing import Optional, List
from playwright.async_api import async_playwright, BrowserContext

# Rutas del sistema de Skool que NO son comunidades
SYSTEM_SLUGS = {
    'login', 'signup', 'profile', 'discover', 'notifications',
    'settings', 'help', 'terms', 'privacy', 'pricing', 'about',
    'careers', 'affiliate', 'new', 'search', 'blog', 'classroom',
    'feed', 'members', 'events', 'leaderboard', 'courses', 'home',
    'dashboard', 'admin', 'api', 'static', 'assets', 'community',
    'groups', 'account', 'billing', 'contact', 'g',
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
            print("[Skool] Login exitoso.")
            return True
        except Exception:
            content = await self._page.content()
            if "incorrect" in content.lower() or "invalid" in content.lower():
                raise ValueError("Credenciales incorrectas. Revisa tu email y contraseña.")
            print("[Skool] Login completado.")
            return True

    # ------------------------------------------------------------------ #
    # Descubrir cursos                                                     #
    # ------------------------------------------------------------------ #

    async def get_my_courses(self) -> List[Course]:
        """
        Busca todas las comunidades/cursos del usuario.
        Estrategia principal: hacer clic en el community switcher (↕) del
        header de Skool — ese dropdown muestra TODAS las comunidades unidas.
        Fallback: escanear links en la página principal.
        """
        print("[Skool] Buscando tus cursos...")

        # Estrategia 1: abrir el community switcher (dropdown del header)
        courses = await self._get_courses_from_switcher()

        # Estrategia 2: escanear la home si el switcher no funcionó
        if not courses:
            print("[Skool] Intentando en la página principal...")
            await self._goto("https://www.skool.com/")
            await asyncio.sleep(4)
            courses = await self._extract_community_slugs()

        if not courses:
            print("[Skool] ⚠️  No se encontraron comunidades.")
        else:
            print(f"[Skool] Total: {len(courses)} curso(s) encontrado(s).")

        return courses

    async def _get_courses_from_switcher(self) -> List[Course]:
        """
        Usa Playwright (no JS) para hacer clic en el community switcher,
        espera a que el dropdown aparezca, y extrae los links de comunidad.
        """
        print("[Skool] Buscando el community switcher...")

        # Contar los links actuales antes de abrir el dropdown
        links_before = await self._page.evaluate(
            "() => document.querySelectorAll('a[href]').length"
        )

        # Buscar el botón del switcher usando bounding_box (posición real en pantalla)
        # El switcher está en la esquina superior izquierda, tiene texto + SVG
        switcher_btn = None
        all_buttons = await self._page.query_selector_all("button")
        for btn in all_buttons:
            try:
                box = await btn.bounding_box()
                if not box:
                    continue
                # Debe estar en la franja superior (y < 80px) e izquierda (x < 500px)
                if box['y'] < 80 and box['x'] < 500 and box['width'] > 30:
                    text = (await btn.inner_text()).strip()
                    has_svg = await btn.query_selector("svg") is not None
                    if text and has_svg and len(text) > 1:
                        switcher_btn = btn
                        print(f"  [→] Switcher encontrado: '{text[:40]}'")
                        break
            except Exception:
                continue

        if not switcher_btn:
            # Segundo intento: cualquier botón con SVG en el header
            for btn in all_buttons:
                try:
                    box = await btn.bounding_box()
                    if box and box['y'] < 80 and await btn.query_selector("svg"):
                        switcher_btn = btn
                        print("  [→] Switcher encontrado (fallback)")
                        break
                except Exception:
                    continue

        if not switcher_btn:
            print("  ⚠️  No se encontró el community switcher")
            return []

        # Clic con Playwright (no JS) — esto mantiene el foco correctamente
        await switcher_btn.click()
        print("  [→] Clic en switcher. Esperando dropdown...")

        # Esperar a que aparezcan nuevos links (el dropdown se renderiza)
        try:
            await self._page.wait_for_function(
                f"() => document.querySelectorAll('a[href]').length > {links_before + 2}",
                timeout=6000,
            )
            print("  [→] Dropdown visible")
        except Exception:
            await asyncio.sleep(2.5)

        # Extraer links AHORA (mientras el dropdown está abierto)
        courses = await self._extract_community_slugs()

        # Cerrar el dropdown
        await self._page.keyboard.press("Escape")
        await asyncio.sleep(0.5)

        return courses

    async def _extract_community_slugs(self) -> List[Course]:
        """
        Escanea todos los <a href> visibles y filtra los que son slugs
        de comunidades de Skool (formato: /nombre o /nombre-1234).
        """
        raw_links = await self._page.evaluate("""
            () => Array.from(document.querySelectorAll('a[href]')).map(a => ({
                href: a.getAttribute('href') || '',
                text: (a.innerText || a.textContent || '').trim().split('\\n')[0].trim()
            }))
        """)

        seen_slugs: set = set()
        courses: List[Course] = []
        nav_words = {
            'classroom', 'members', 'events', 'about', 'feed',
            'home', 'leaderboards', 'discover', 'search',
        }

        for item in raw_links:
            href = (item.get('href') or '').strip()
            text = (item.get('text') or '').strip()

            # Slug de comunidad: /algo  o  /algo-1234  (sin subdirectorios)
            m = re.match(r'^/([a-z0-9][a-z0-9-]{1,70})/?$', href)
            if not m:
                continue

            slug = m.group(1)
            if slug in SYSTEM_SLUGS or slug in seen_slugs:
                continue
            if not text or text.lower() in nav_words or len(text) > 100:
                continue

            seen_slugs.add(slug)
            classroom_url = f"https://www.skool.com/{slug}/classroom"
            courses.append(Course(name=text, url=classroom_url, slug=slug))
            print(f"  → {text}  ({slug})")

        return courses

    # ------------------------------------------------------------------ #
    # Módulos y lecciones                                                  #
    # ------------------------------------------------------------------ #

    async def get_course_modules(self, course: Course) -> List[Module]:
        print(f"\n[Skool] Cargando classroom: {course.name}")
        print(f"  URL: {course.url}")
        await self._goto(course.url)
        await asyncio.sleep(4)

        # Imprimir URL final (por si redirigió)
        print(f"  URL actual: {self._page.url}")

        # Debug: mostrar todos los links del classroom para entender la estructura
        all_links = await self._page.evaluate("""
            () => Array.from(document.querySelectorAll('a[href]'))
                .map(a => ({ href: a.getAttribute('href'), text: (a.innerText||'').trim().slice(0,60) }))
                .filter(x => x.href && !x.href.startsWith('http'))
                .slice(0, 40)
        """)
        print(f"  [Debug] {len(all_links)} links internos en la página:")
        for lnk in all_links[:20]:
            print(f"    {lnk['href']}  →  {lnk['text']}")

        # Expandir todos los módulos colapsados
        await self._expand_all_modules()

        # Extraer módulos y lecciones
        modules = await self._extract_modules_and_lessons(course)

        if modules:
            total = sum(len(m.lessons) for m in modules)
            print(f"  ✅ {total} lección(es) en {len(modules)} módulo(s)")
        else:
            print(f"  ⚠️  No se encontraron lecciones — revisa el debug arriba")

        return modules

    async def _expand_all_modules(self):
        """
        Skool muestra los módulos colapsados. Hay que hacer click en cada
        header de módulo para ver las lecciones dentro.
        """
        print("  [→] Expandiendo módulos...")

        # Intentar con varios selectores comunes de elementos colapsables
        expand_js = """
            () => {
                // Buscar botones/elementos con aria-expanded=false
                const collapsed = document.querySelectorAll(
                    '[aria-expanded="false"], [data-expanded="false"]'
                );
                collapsed.forEach(el => {
                    try { el.click(); } catch(e) {}
                });

                // También buscar headers de sección que parezcan clicables
                const headers = document.querySelectorAll(
                    '[class*="Section"] > [class*="Header"], ' +
                    '[class*="Module"] > [class*="Title"], ' +
                    '[class*="Unit"] > [class*="Header"], ' +
                    '[class*="section-header"], [class*="module-header"]'
                );
                headers.forEach(el => {
                    try { el.click(); } catch(e) {}
                });

                return collapsed.length + headers.length;
            }
        """

        clicked = await self._page.evaluate(expand_js)
        if clicked:
            print(f"  [→] {clicked} elemento(s) expandido(s)")
            await asyncio.sleep(2)

        # Segundo intento: hacer scroll para activar lazy-loading y volver a expandir
        await self._page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
        await asyncio.sleep(1)
        await self._page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(1)

        # Tercer intento con Playwright directo
        for selector in ["button[aria-expanded='false']", "[role='button'][aria-expanded='false']"]:
            buttons = await self._page.query_selector_all(selector)
            for btn in buttons:
                try:
                    await btn.click()
                    await asyncio.sleep(0.2)
                except Exception:
                    pass

        await asyncio.sleep(1)

    async def _extract_modules_and_lessons(self, course: Course) -> List[Module]:
        """
        Extrae todas las lecciones del sidebar del classroom.
        Las lecciones tienen URLs del tipo: /<slug>/classroom/<lesson-id>
        Intenta agruparlas por módulo buscando elementos hermanos en el DOM.
        """
        slug = course.slug

        # Extraer todos los links de lección con su contexto de módulo
        lesson_data = await self._page.evaluate(f"""
            () => {{
                const SLUG = '{slug}';
                const lessonPattern = new RegExp('^/' + SLUG + '/classroom/[^/]+');
                const results = [];
                const seen = new Set();

                document.querySelectorAll('a[href]').forEach(a => {{
                    const href = a.getAttribute('href') || '';
                    if (!lessonPattern.test(href) || seen.has(href)) return;
                    seen.add(href);

                    const text = (a.innerText || a.textContent || '').trim();
                    if (!text) return;

                    // Subir por el DOM para encontrar el nombre del módulo padre
                    let moduleName = 'Módulo 1';
                    let el = a.parentElement;
                    for (let depth = 0; depth < 10; depth++) {{
                        if (!el) break;
                        // Buscar elementos hermanos anteriores que sean headers
                        let sibling = el.previousElementSibling;
                        while (sibling) {{
                            const t = (sibling.innerText || sibling.textContent || '')
                                        .trim().split('\\n')[0].trim();
                            if (t && t.length > 1 && t.length < 120 &&
                                !t.match(/^\\d+$/) ) {{
                                moduleName = t;
                                break;
                            }}
                            sibling = sibling.previousElementSibling;
                        }}
                        if (moduleName !== 'Módulo 1') break;
                        el = el.parentElement;
                    }}

                    results.push({{ href, text, moduleName }});
                }});

                return results;
            }}
        """)

        if not lesson_data:
            print("  ⚠️  No se encontraron links de lección. Intentando método alternativo...")
            return await self._extract_lessons_simple(course)

        # Construir módulos manteniendo el orden de aparición
        modules_ordered: List[str] = []
        modules_dict = {}

        for item in lesson_data:
            mod_name = item.get('moduleName', 'Módulo 1')
            if mod_name not in modules_dict:
                modules_ordered.append(mod_name)
                modules_dict[mod_name] = Module(name=mod_name)

        position_in_module = {name: 0 for name in modules_dict}

        for item in lesson_data:
            href = item.get('href', '')
            text = item.get('text', '').strip()
            mod_name = item.get('moduleName', 'Módulo 1')

            full_url = f"https://www.skool.com{href}"
            pos = position_in_module[mod_name]
            position_in_module[mod_name] += 1

            lesson = Lesson(
                title=text,
                url=full_url,
                module_name=mod_name,
                course_name=course.name,
                position=pos,
            )
            modules_dict[mod_name].lessons.append(lesson)

        return [modules_dict[n] for n in modules_ordered]

    async def _extract_lessons_simple(self, course: Course) -> List[Module]:
        """Fallback: un solo módulo con todos los links de lección encontrados."""
        slug = course.slug
        links = await self._page.query_selector_all(f"a[href*='/{slug}/classroom/']")
        module = Module(name="Contenido del Curso")
        seen: set = set()

        for i, link in enumerate(links):
            href = await link.get_attribute("href") or ""
            if href in seen:
                continue
            seen.add(href)
            text = (await link.inner_text()).strip()
            if not text:
                continue
            full_url = href if href.startswith("http") else f"https://www.skool.com{href}"
            module.lessons.append(Lesson(
                title=text, url=full_url,
                module_name=module.name, course_name=course.name, position=i,
            ))

        return [module] if module.lessons else []

    # ------------------------------------------------------------------ #
    # Detalle de lección (video ID + descripción)                         #
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
        for sel in ["video source", "video[src]",
                    "iframe[src*='wistia']", "iframe[src*='vimeo']", "iframe[src*='youtube']"]:
            el = await self._page.query_selector(sel)
            if el:
                return await el.get_attribute("src")
        return None

    async def _extract_lesson_text(self) -> str:
        for sel in ["[class*='LessonContent']", "[class*='lesson-content']",
                    "[class*='description']", "article", "main"]:
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
