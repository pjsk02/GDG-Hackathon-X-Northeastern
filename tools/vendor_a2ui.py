"""Mirror the pinned A2UI renderer (and everything it imports) from esm.sh into api/static/vendor/,
so the /a2ui page works with no internet (audit M5). Re-run after changing a pinned version.

Usage: python tools/vendor_a2ui.py

esm.sh entry modules re-export from absolute paths ("/@a2ui/web_core@0.15.0/es2022/..."), so this
crawls the whole import graph and rewrites every specifier to the local /vendor/esm/ mirror. Modules
shared between the three entries (web_core, lit) land at one path, so the page still gets one copy.
"""

import hashlib
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests

ORIGIN = "https://esm.sh"
# Must match api/static/a2ui.html. Keys are the local entry file names the page imports.
ENTRIES = {
    "lit.js": "/@a2ui/lit@0.15.0?deps=@a2ui/web_core@0.15.0,lit@3.3.3",
    "web_core_v1_0.js": "/@a2ui/web_core@0.15.0/v1_0?deps=lit@3.3.3",
    "markdown_it.js": "/@a2ui/markdown-it@0.2.2?deps=@a2ui/web_core@0.15.0,lit@3.3.3",
}
OUT = Path(__file__).resolve().parents[1] / "api" / "static" / "vendor" / "esm"
URL_PREFIX = "/vendor/esm"

# import/export ... from "x" | import "x" | import("x")
SPEC = re.compile(r"""(\bfrom\s*|\bimport\s*\(?\s*)(["'])([^"']+)\2""")


def local_path(path_and_query: str) -> str:
    """Map an esm.sh path (+query) to a stable local file path."""
    parts = urlsplit(path_and_query)
    path = parts.path.lstrip("/")
    if parts.query:  # entry-style URLs: fold the query into the file name
        path = f"{path}__{hashlib.sha1(parts.query.encode()).hexdigest()[:10]}"
    if not path.endswith((".js", ".mjs", ".css")):
        path += ".js"
    # esm.sh paths can hold semver ranges ("zod@^3.25.28 || ^4"): keep them filesystem- and URL-safe.
    return re.sub(r"[^A-Za-z0-9._@/-]", "_", path)


def main() -> int:
    session = requests.Session()
    seen: dict[str, str] = {}  # esm.sh path+query -> local path
    queue = list(ENTRIES.values())
    while queue:
        spec = queue.pop()
        if spec in seen:
            continue
        local = local_path(spec)
        seen[spec] = local
        r = session.get(ORIGIN + spec, timeout=30)
        r.raise_for_status()
        body = r.text

        def rewrite(m: re.Match) -> str:
            target = m.group(3)
            if target.startswith(ORIGIN):
                target = target[len(ORIGIN):]
            elif target.startswith(("./", "../")):
                target = urlsplit(urljoin(ORIGIN + spec, target))._replace(scheme="", netloc="").geturl()
            elif not target.startswith("/"):
                return m.group(0)  # bare specifier: leave as is (esm.sh output has none)
            queue.append(target)
            return f"{m.group(1)}{m.group(2)}{URL_PREFIX}/{local_path(target)}{m.group(2)}"

        out = OUT / local
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(SPEC.sub(rewrite, body), encoding="utf-8")
        print(f"{len(body):>8,} B  {spec}")

    for name, spec in ENTRIES.items():  # short, stable entry names for the page to import
        (OUT / name).write_text(f'export * from "{URL_PREFIX}/{seen[spec]}";\n', encoding="utf-8")
    total = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())
    print(f"vendored {len(seen)} modules, {total / 1024:.0f} KiB -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
