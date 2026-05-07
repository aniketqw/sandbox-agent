"""
tools/educative_tool.py — Educative.io course browser and content fetcher.
Opens Chrome locally with auth cookies, scrapes course structure, and saves for agent use.
"""

import os
import sys
import json
import base64
import subprocess
import tempfile
import time

def _get_cookies_b64() -> str:
    """Get base64-encoded cookies from environment variable.

    Cookies must be exported from educative.io browser (Cookie Editor extension)
    as JSON base64 and stored in .env as EDUCATIVE_COOKIES_B64=<blob>.
    See EDUCATIVE_PATTERN.md for maintenance instructions.
    """
    val = os.getenv("EDUCATIVE_COOKIES_B64", "")
    if not val:
        raise RuntimeError(
            "EDUCATIVE_COOKIES_B64 not set in .env. "
            "Export cookies from educative.io (Cookie Editor extension → Export as JSON base64) "
            "and add EDUCATIVE_COOKIES_B64=<blob> to your .env file. "
            "See EDUCATIVE_PATTERN.md for full instructions. "
            "Cookies expire ~2026-05-14 and must be rotated when they expire."
        )
    return val

WORKSPACE_HOST = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "agent_workspace"))
COURSES_DIR = os.path.join(WORKSPACE_HOST, "educative_courses")


def _decode_cookies(cookie_str: str) -> list:
    """Decode the cookie blob.

    The stored value is a SINGLE base64 string whose decoded form is
    a semicolon-separated list of JSON cookie objects, e.g.:
        {name:..., value:...};{name:..., value:...};...
    """
    cookie_str = "".join(cookie_str.split())  # strip all whitespace / line breaks
    padding = (4 - len(cookie_str) % 4) % 4
    try:
        decoded = base64.b64decode(cookie_str + "=" * padding).decode("utf-8")
    except Exception:
        return []

    cookies = []
    for part in decoded.split(";"):
        part = part.strip()
        if not part:
            continue
        try:
            cookies.append(json.loads(part))
        except Exception:
            pass
    return cookies


def _to_playwright_cookies(raw_cookies: list) -> list:
    """Convert raw cookie dicts to Playwright-compatible format."""
    pw_cookies = []
    for c in raw_cookies:
        domain = c.get("domain", "")
        # Playwright hostOnly cookies must not have a leading dot
        if c.get("hostOnly") and domain.startswith("."):
            domain = domain[1:]

        pw_cookie = {
            "name": c["name"],
            "value": c["value"],
            "domain": domain,
            "path": c.get("path", "/"),
        }
        if "expirationDate" in c:
            pw_cookie["expires"] = int(c["expirationDate"])
        if c.get("secure"):
            pw_cookie["secure"] = True
        if c.get("httpOnly"):
            pw_cookie["httpOnly"] = True

        same_site = c.get("sameSite", "unspecified").lower()
        if same_site == "lax":
            pw_cookie["sameSite"] = "Lax"
        elif same_site == "strict":
            pw_cookie["sameSite"] = "Strict"
        elif same_site == "none":
            pw_cookie["sameSite"] = "None"

        pw_cookies.append(pw_cookie)
    return pw_cookies


# ---------------------------------------------------------------------------
# Playwright browser script (runs locally on the host, not inside Docker)
# ---------------------------------------------------------------------------
_BROWSER_SCRIPT_TEMPLATE = """
import json, sys, time
from playwright.sync_api import sync_playwright

URL = {url}
OUTPUT_FILE = {output_file}
COOKIES = {cookies}

def extract_course_content(page):
    try:
        return page.evaluate('''() => {{
            const r = {{title:"",description:"",url:window.location.href,lessons:[],current_content:""}};
            const h1 = document.querySelector("h1, .course-title, [data-testid='course-title']");
            if (h1) r.title = h1.textContent.trim();
            const desc = document.querySelector(".course-description, .description");
            if (desc) r.description = desc.textContent.trim().slice(0,600);

            // Sidebar / table of contents — try many selectors educative uses
            const selectors = [
                "[class*='SideBarItem']",
                "[class*='sidebar-item']",
                "[class*='lesson-item']",
                ".lesson-list-item",
                ".chapter-item",
                "li[class*='item']",
                "nav a",
                "[class*='TableOfContents'] a",
                "[class*='toc'] a"
            ];
            const seen = new Set();
            for (const sel of selectors) {{
                document.querySelectorAll(sel).forEach(el => {{
                    const link = el.tagName === "A" ? el : el.querySelector("a");
                    const text = el.textContent.trim().slice(0,200);
                    const href = link ? link.href : null;
                    const key = text + "|" + href;
                    if (text.length > 2 && !seen.has(key)) {{
                        seen.add(key);
                        r.lessons.push({{title:text, url:href}});
                    }}
                }});
                if (r.lessons.length > 5) break;
            }}
            r.lessons = r.lessons.slice(0, 120);

            const main = document.querySelector("main, article, .content, .lesson-content");
            if (main) r.current_content = main.textContent.trim().slice(0,3000);
            return r;
        }}''')
    except Exception as e:
        return {{"error": str(e), "url": page.url}}

with sync_playwright() as p:
    print("Opening Chrome...", flush=True)
    try:
        browser = p.chromium.launch(headless=False, channel="chrome",
                                    args=["--start-maximized"])
    except Exception:
        browser = p.chromium.launch(headless=False, args=["--start-maximized"])

    ctx = browser.new_context(
        viewport={{"width": 1920, "height": 1080}},
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )

    print(f"Injecting {{len(COOKIES)}} cookies...", flush=True)
    try:
        ctx.add_cookies(COOKIES)
    except Exception as e:
        print(f"Cookie warning: {{e}}", flush=True)

    page = ctx.new_page()
    print(f"Navigating to {{URL}} ...", flush=True)
    try:
        page.goto(URL, wait_until="domcontentloaded", timeout=40000)
        page.wait_for_timeout(4000)
        data = extract_course_content(page)
        with open(OUTPUT_FILE, "w") as f:
            json.dump(data, f, indent=2)
        print("COURSE_DATA:" + json.dumps(data), flush=True)
    except Exception as e:
        err = {{"error": str(e), "url": URL}}
        print("COURSE_DATA:" + json.dumps(err), flush=True)

    # Stay open so the user can browse
    print("Browser ready. Close the window when done.", flush=True)
    try:
        page.wait_for_timeout(600000)  # 10 min max then auto-close
    except Exception:
        pass
    browser.close()
"""


def open_educative_course(url: str) -> dict:
    """
    Open Chrome with educative.io auth cookies, navigate to the given course URL,
    scrape the course structure, save it to workspace, and return a summary.
    The browser stays open so the user can interact with the course.
    """
    os.makedirs(COURSES_DIR, exist_ok=True)

    raw_cookies = _decode_cookies(_get_cookies_b64())
    pw_cookies = _to_playwright_cookies(raw_cookies)

    url_slug = url.split("educative.io/")[-1].replace("/", "_").replace("?", "_")[:80]
    output_file = os.path.join(COURSES_DIR, f"{url_slug}.json")

    script_body = _BROWSER_SCRIPT_TEMPLATE.format(
        url=json.dumps(url),
        output_file=json.dumps(output_file),
        cookies=repr(pw_cookies),
    )

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, prefix="educ_"
    ) as f:
        f.write(script_body)
        script_path = f.name

    try:
        proc = subprocess.Popen(
            [sys.executable, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        course_data = None
        lines = []
        deadline = time.time() + 50  # 50 s to get content back

        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    break
                time.sleep(0.3)
                continue
            lines.append(line.rstrip())
            if line.startswith("COURSE_DATA:"):
                try:
                    course_data = json.loads(line[len("COURSE_DATA:"):])
                except Exception:
                    pass
                break

        if course_data and "error" not in course_data:
            return {
                "success": True,
                "message": (
                    "Chrome is open and logged into educative.io. "
                    "Course content extracted and saved. Browser stays open."
                ),
                "course": {
                    "title": course_data.get("title", ""),
                    "description": course_data.get("description", ""),
                    "url": url,
                    "lesson_count": len(course_data.get("lessons", [])),
                    "lessons": course_data.get("lessons", [])[:30],
                },
                "saved_to": f"/workspace/educative_courses/{os.path.basename(output_file)}",
                "browser_pid": proc.pid,
            }
        else:
            return {
                "success": False,
                "message": "Chrome opened but content extraction timed out or failed.",
                "log": "\n".join(lines[-20:]),
                "error": course_data.get("error") if course_data else "timeout",
                "browser_pid": getattr(proc, "pid", None),
                "hint": (
                    "Playwright may not be installed locally. "
                    "Run: pip install playwright && playwright install chrome"
                ),
            }
    except FileNotFoundError:
        return {
            "error": "Playwright not found. Install with: pip install playwright && playwright install chrome"
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        try:
            os.unlink(script_path)
        except Exception:
            pass


def load_educative_course(filename: str) -> dict:
    """Load a previously saved educative course JSON from the workspace."""
    for candidate in [
        os.path.join(COURSES_DIR, filename),
        os.path.join(WORKSPACE_HOST, filename),
        filename,
    ]:
        if os.path.exists(candidate):
            try:
                with open(candidate) as f:
                    data = json.load(f)
                return {"success": True, "data": data}
            except Exception as e:
                return {"error": str(e)}
    return {"error": f"File not found: {filename}"}


def list_educative_courses() -> dict:
    """List all educative courses that have been saved to the workspace."""
    if not os.path.exists(COURSES_DIR):
        return {"courses": [], "message": "No courses saved yet. Use open_educative_course first."}

    files = sorted(
        f for f in os.listdir(COURSES_DIR) if f.endswith(".json")
    )
    courses = []
    for fname in files:
        try:
            with open(os.path.join(COURSES_DIR, fname)) as fh:
                d = json.load(fh)
            courses.append({
                "filename": fname,
                "title": d.get("title", fname),
                "url": d.get("url", ""),
                "lesson_count": len(d.get("lessons", [])),
            })
        except Exception:
            courses.append({"filename": fname, "title": fname})

    return {"courses": courses, "count": len(courses)}
