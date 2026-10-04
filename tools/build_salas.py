"""Regenerate the four iframe pages (public/sala1-4) from the storyboard page.

public/guion/index.html is the single source: edit it, then run
    python3 tools/build_salas.py && npm run build
Each sala page is the same file with window.KIOSK set to one room id.
"""
from pathlib import Path

root = Path(__file__).resolve().parent.parent / "public"
page = (root / "guion" / "index.html").read_text()
head, rest = page.split("<title>", 1)
for n, room in enumerate(["rain", "shield", "dose", "error"], 1):
    out = root / f"sala{n}" / "index.html"
    out.write_text(head.replace('lang="es"', 'lang="en"') + f'<script>window.KIOSK="{room}"</script>\n<title>' + rest)
    print("wrote", out.relative_to(root.parent))
