#!/usr/bin/env python3
"""Renderuje deck/slajdy.md do HTML gotowego na wydruk 16:9 (1280x720 na slajd).

Konwencja pliku wejsciowego:
  # Naglowek slajdu          -> tytul
  ## Podtytul                -> podtytul
  - punkt                    -> lista punktowana
  > zdanie                   -> ramka z wazna informacja
  ``` ... ```                -> blok tekstu (np. schemat ASCII)
  ---                        -> granica slajdu
Skrypt nie korzysta z zadnych bibliotek zewnetrznych; uruchamia go deck/build.sh.
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "slajdy.md"
TARGET = ROOT.parent / "reports" / "deck" / "deck.html"
FOOTER = "NoorPointer — AI Control Layer"

STYLE = """
  @page { size: 1280px 720px; margin: 0; }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; background: #ffffff; color: #12202e;
    font-family: "DejaVu Sans", "Liberation Sans", Arial, sans-serif; }
  .slide { position: relative; width: 1280px; height: 720px; padding: 46px 60px 64px;
    page-break-after: always; overflow: hidden; }
  .slide:last-child { page-break-after: auto; }
  h1 { margin: 0 0 6px; font-size: 36px; line-height: 1.2; color: #0b3d63; }
  h2 { margin: 0 0 22px; font-size: 19px; font-weight: normal; color: #4a5b6a; }
  ul { margin: 0; padding-left: 26px; }
  li { font-size: 19px; line-height: 1.5; margin-bottom: 11px; }
  li b { color: #0b3d63; }
  code { font-family: "DejaVu Sans Mono", monospace; font-size: 17px;
    background: #eef3f8; padding: 1px 5px; border-radius: 3px; }
  pre { font-family: "DejaVu Sans Mono", monospace; font-size: 12px; line-height: 1.25;
    background: #f5f8fb; border: 1px solid #d8e2ec; border-radius: 6px;
    padding: 12px 14px; margin: 14px 0 0; white-space: pre; }
  .callout { margin-top: 20px; padding: 14px 18px; border-left: 5px solid #1c6ea4;
    background: #eef6fd; font-size: 18px; line-height: 1.45; }
  p { font-size: 19px; line-height: 1.5; margin: 0 0 12px; }
  .number { position: absolute; right: 60px; top: 46px; font-size: 15px; color: #8595a5; }
  footer { position: absolute; left: 60px; bottom: 22px; font-size: 13px; color: #9aa8b6; }
"""


def inline(text: str) -> str:
    escaped = html.escape(text, quote=False)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"`(.+?)`", r"<code>\1</code>", escaped)
    return escaped


def render_slide(lines: list[str], index: int, total: int) -> str:
    parts: list[str] = []
    in_list = False
    in_code = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            parts.append("</ul>")
            in_list = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("```"):
            close_list()
            if in_code:
                parts.append("</pre>")
            else:
                parts.append("<pre>")
            in_code = not in_code
            continue

        if in_code:
            parts.append(html.escape(line, quote=False))
            continue

        if not stripped:
            continue
        if stripped.startswith("# "):
            close_list()
            parts.append(f"<h1>{inline(stripped[2:])}</h1>")
        elif stripped.startswith("## "):
            close_list()
            parts.append(f"<h2>{inline(stripped[3:])}</h2>")
        elif stripped.startswith("- "):
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{inline(stripped[2:])}</li>")
        elif stripped.startswith("> "):
            close_list()
            parts.append(f'<div class="callout">{inline(stripped[2:])}</div>')
        else:
            close_list()
            parts.append(f"<p>{inline(stripped)}</p>")

    close_list()
    if in_code:
        parts.append("</pre>")

    body = "\n    ".join(parts)
    return (
        f'  <section class="slide">\n'
        f'    <div class="number">{index}/{total}</div>\n'
        f"    {body}\n"
        f"    <footer>{FOOTER}</footer>\n"
        f"  </section>"
    )


def main() -> int:
    if not SOURCE.exists():
        print(f"build: brak {SOURCE}", file=sys.stderr)
        return 1

    text = SOURCE.read_text(encoding="utf-8")
    raw_slides = [block for block in re.split(r"^---\s*$", text, flags=re.MULTILINE)]
    slides = [block.strip().splitlines() for block in raw_slides if block.strip()]
    if not slides:
        print("build: plik nie zawiera zadnego slajdu", file=sys.stderr)
        return 1

    rendered = "\n".join(
        render_slide(lines, number, len(slides))
        for number, lines in enumerate(slides, start=1)
    )
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(
        "<!DOCTYPE html>\n<html lang=\"pl\">\n<head>\n"
        '<meta charset="utf-8">\n'
        f"<title>{FOOTER}</title>\n<style>{STYLE}</style>\n</head>\n<body>\n"
        f"{rendered}\n</body>\n</html>\n",
        encoding="utf-8",
    )
    print(f"build: {len(slides)} slajdow -> {TARGET.relative_to(TARGET.parents[1])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
