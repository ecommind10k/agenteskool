"""
Skool browser automation client.
Handles login, course discovery, and lesson navigation using Playwright.
"""

import asyncio
import re
from dataclasses import dataclass, field
from typing import Optional, List
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
    lessons: List[Lesson] = field(default_factory=list)


@dataclass
class Course:
    name: str
    url: str
    modules: List[Module] = field(default_factory=list)


# Timeout usado en todas las navegaciones (ms)
NAV_TIMEOUT = 60_000


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

    # ------------------------------------------------------------------ #
    # Login                                                                #
    # ------------------------------------------------------------------ #

    async def login(self) -> bool:
        print("[Skool] Abriendo página de login...")
        await self._goto("https://www.skool.com/login")

        await self._page.fill('input[type="email"]', self.email)
        await asyncio.sleep(0.5)
        await self._page.fill('input[type="password"]', self.password)
        await asyncio.sleep(0.5)
        await self._page.click('button[type="submit"]')

        try:
            await self._page.wait_for_url(
                lambda url: "skool.com" in url and "login" not in url,
                timeout=20000,
            )
            print("[Skool] Login exitoso.")
            await asyncio.sleep(2)
            return True
        except Exception:
            content = await self._page.content()
            if "incorrect" in content.lower() or "invalid" in content.lower():
                raise ValueError(
                    "Credenciales incorrectas. Revisa tu email y contraseña de Skool."
                )
            print("[Skool] Login aparentemente exitoso, continuando...")
            return True

    # ------------------------------------------------------------------ #
    # Course discovery                                                     #
    # ------------------------------------------------------------------ #

    async def get_my_courses(self) -> List[Course]:
        """Busca todos los cursos/comunidades del usuario."""
        print("[Skool] Buscando tus cursos...")

        courses: List[Course] = []

        # Intento 1: página principal post-login (sidebar con comunidades)
        courses = await self._scrape_courses_from_page("https://www.skool.com/")
        if courses:
            print(f"[Skool] {len(courses)} curso(s) encontrados.")
            return courses

        # Intento 2: página de perfil
        courses = await self._scrape_courses_from_page("https://www.skool.com/profile")
        if courses:
            print(f"[Skool] {len(courses)} curso(s) encontrados.")
            return courses

        # Intento 3: buscar cualquier enlace /*/classroom en la página actual
        courses = await self._extract_classroom_links()
        if courses:
            print(f"[Skool] {len(courses)} curso(s) encontrados.")
            return courses

        print("[Skool] No se encontraron cursos automáticamente.")
        return courses

    async def _scrape_courses_from_page(self, url: str) -> List[Course]:
        """Navega a una URL y extrae links de classroom."""
        try:
            await self._goto(url)
            await asyncio.sleep(3)
            return await self._extract_classroom_links()
        except Exception as e:
            print(f"[Skool] Error al cargar {url}: {e}")
            return []

    async def _extract_classroom_links(self) -> List[Course]:
        """Extrae todos los links /*/classroom de la página actual."""
        courses: List[Course] = []
        seen: set = set()

        links = await self._page.query_selector_all("a[href*='/classroom']")
        for link in links:
            href = await link.get_attribute("href")
            if not href or href in seen:
                continue
            if href.rstrip("/").endswith("/classroom") is False and "/classroom/" not in href:
                continue
            # Normalizar: quedarse con la URL base del classroom
            base = re.sub(r'/classroom/.*', '/classroom', href)
            if base in seen:
                continue
            seen.add(base)

            text = (await link.inner_text()).strip()
            full_url = base if base.startswith("http") else f"https://www.skool.com{base}"

            # Extraer nombre del slug si no hay texto
            if not text or len(text) < 2:
                slug = base.strip("/").split("/")[-2] if "/classroom" in base else base.strip("/").split("/")[-1]
                text = slug.replace("-", " ").title()

            courses.append(Course(name=text, url=full_url))

        return courses

    # ------------------------------------------------------------------ #
    # Module & lesson discovery                                            #
    # ------------------------------------------------------------------ #

    async def get_course_modules(self, course: Course) -> List[Module]:
        """Navega al classroom y mapea módulos y lecciones."""
        print(f"\n[Skool] Cargando classroom: {course.name}")
        await self._goto(course.url)
        await asyncio.sleep(4)

        # Intentar hacer scroll para que cargue contenido lazy
        await self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(2)

        # Extraer estructura de módulos y lecciones del sidebar
        modules = await self._extract_modules(course)

        if not modules:
            print(f"  ⚠️  No se encontraron lecciones en {course.name}")
        else:
            total = sum(len(m.lessons) for m in modules)
            print(f"  → {total} lección(es) en {len(modules)} módulo(s)")

        return modules

    async def _extract_modules(self, course: Course) -> List[Module]:
        """
        Extrae módulos y lecciones del sidebar del classroom de Skool.
        Skool renderiza el sidebar con secciones colapsables.
        """
        modules: List[Module] = []
        current_module: Optional[Module] = None
        position = 0
        seen_hrefs: set = set()

        # Obtener todos los elementos del sidebar en orden DOM
        # Skool usa divs con clases como 'styled__UnitContainer', 'styled__LessonRow', etc.
        # Intentamos con múltiples selectores para cubrir diferentes versiones del UI
        all_items = await self._page.query_selector_all(
            "[class*='Unit'], [class*='unit'], [class*='Section'], [class*='section'], "
            "[class*='Module'], [class*='module'], "
            "a[href*='/classroom/']"
        )

        for item in all_items:
            tag = await item.evaluate("el => el.tagName.toLowerCase()")
            href = await item.get_attribute("href") if tag == "a" else None

            if href and "/classroom/" in href:
                # Es un link de lección
                if href in seen_hrefs:
                    continue
                seen_hrefs.add(href)

                text = (await item.inner_text()).strip()
                if not text:
                    continue

                full_url = href if href.startswith("http") else f"https://www.skool.com{href}"

                if current_module is None:
                    current_module = Module(name="Módulo 1")
                    modules.append(current_module)

                lesson = Lesson(
                    title=text,
                    url=full_url,
                    module_name=current_module.name,
                    course_name=course.name,
                    position=position,
                )
                current_module.lessons.append(lesson)
                position += 1
            else:
                # Puede ser un header de módulo/sección
                text = (await item.inner_text()).strip().split("\n")[0]
                if text and len(text) > 1 and len(text) < 120:
                    # Crear nuevo módulo solo si parece un título
                    new_mod = Module(name=text)
                    modules.append(new_mod)
                    current_module = new_mod

        # Eliminar módulos vacíos
        modules = [m for m in modules if m.lessons]

        # Si no encontramos nada con el método anterior, buscar solo links
        if not modules:
            modules = await self._extract_lessons_fallback(course)

        # Renumerar posiciones por módulo
        for module in modules:
            for i, lesson in enumerate(module.lessons):
                lesson.position = i

        return modules

    async def _extract_lessons_fallback(self, course: Course) -> List[Module]:
        """Fallback simple: un módulo con todos los links de classroom."""
        links = await self._page.query_selector_all("a[href*='/classroom/']")
        module = Module(name="Contenido del Curso")
        seen: set = set()
        position = 0

        for link in links:
            href = await link.get_attribute("href")
            if not href or href in seen:
                continue
            if href.rstrip("/").endswith("/classroom"):
                continue
            seen.add(href)

            text = (await link.inner_text()).strip()
            if not text:
                continue

            full_url = href if href.startswith("http") else f"https://www.skool.com{href}"
            module.lessons.append(Lesson(
                title=text,
                url=full_url,
                module_name=module.name,
                course_name=course.name,
                position=position,
            ))
            position += 1

        return [module] if module.lessons else []

    # ------------------------------------------------------------------ #
    # Lesson details                                                       #
    # ------------------------------------------------------------------ #

    async def get_lesson_details(self, lesson: Lesson) -> Lesson:
        """Visita una lección y extrae el ID de video y descripción."""
        print(f"    [video] {lesson.title}")
        await self._goto(lesson.url)
        await asyncio.sleep(3)

        content = await self._page.content()
        wistia_id = self._extract_wistia_id(content)
        if wistia_id:
            lesson.wistia_id = wistia_id
        else:
            video_src = await self._find_video_src()
            if video_src:
                lesson.video_url = video_src

        lesson.description = await self._extract_lesson_text()
        return lesson

    def _extract_wistia_id(self, html: str) -> Optional[str]:
        patterns = [
            r'wistia\.com/medias/([a-z0-9]+)',
            r'wistia_async_([a-z0-9]+)',
            r'"hashed_id"\s*:\s*"([a-z0-9]+)"',
            r'hashedId["\s:]+([a-z0-9]{10,})',
            r'W\.iApi\s*\(\s*["\']([a-z0-9]+)["\']',
        ]
        for pat in patterns:
            m = re.search(pat, html, re.IGNORECASE)
            if m:
                return m.group(1)
        return None

    async def _find_video_src(self) -> Optional[str]:
        video_el = await self._page.query_selector("video source, video[src]")
        if video_el:
            return await video_el.get_attribute("src")
        iframe = await self._page.query_selector(
            "iframe[src*='wistia'], iframe[src*='vimeo'], iframe[src*='youtube']"
        )
        if iframe:
            return await iframe.get_attribute("src")
        return None

    async def _extract_lesson_text(self) -> str:
        selectors = [
            "[class*='lesson-content']",
            "[class*='LessonContent']",
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

    # ------------------------------------------------------------------ #
    # Full pipeline                                                        #
    # ------------------------------------------------------------------ #

    async def scrape_all(self) -> List[Course]:
        """Login → descubrir cursos → mapear módulos y lecciones."""
        await self.login()
        courses = await self.get_my_courses()

        for course in courses:
            modules = await self.get_course_modules(course)
            course.modules = modules
            for module in modules:
                for lesson in module.lessons:
                    await self.get_lesson_details(lesson)

        return courses

    # ------------------------------------------------------------------ #
    # Helper                                                               #
    # ------------------------------------------------------------------ #

    async def _goto(self, url: str):
        """Navega a una URL usando domcontentloaded (mucho más rápido que networkidle)."""
        await self._page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
