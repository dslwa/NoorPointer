#!/usr/bin/env bash
# Buduje prezentacje: deck/slajdy.md -> HTML -> PDF (chromium, bez zadnych zaleznosci poza pythonem).
# Uruchamianie: ./deck/build.sh   (albo: make deck)
set -euo pipefail

cd "$(dirname "$0")/.."
OUT_DIR="reports/deck"
PDF="$OUT_DIR/NoorPointer-10-slajdow.pdf"

python3 deck/build.py
test -s "$OUT_DIR/deck.html" || { echo "build: nie powstal plik HTML" >&2; exit 1; }

chromium_bin="$(command -v chromium || command -v chromium-browser || command -v google-chrome || true)"
if [[ -z "$chromium_bin" ]]; then
  echo "build: brak chromium - HTML jest gotowy, wydrukuj go recznie (Ctrl+P, format poziomy, bez marginesow)" >&2
  exit 1
fi

"$chromium_bin" --headless --disable-gpu --no-sandbox --no-pdf-header-footer \
  --print-to-pdf="$PWD/$PDF" "file://$PWD/$OUT_DIR/deck.html" >/dev/null 2>&1

test -s "$PDF" || { echo "build: nie powstal plik PDF" >&2; exit 1; }
echo "build: PDF $PDF ($(du -h "$PDF" | cut -f1))"
echo "build: podglad HTML $OUT_DIR/deck.html (na slajd 1280x720)"
