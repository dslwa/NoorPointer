#!/usr/bin/env bash
# Zbiera najwazniejsze dowody z katalogu reports/ do katalogu dowody/, ktory jest czescia
# repozytorium. Dzieki temu osoba oceniajaca widzi wyniki bez uruchamiania czegokolwiek.
#
# Uruchamianie: make evidence
set -euo pipefail
cd "$(dirname "$0")/.."

OUT="dowody"
mkdir -p "$OUT"

commit="$(git rev-parse --short HEAD 2>/dev/null || echo 'bez gita')"
generated="$(date '+%Y-%m-%d %H:%M')"
count=0

copy() { # $1 = plik zrodlowy, $2 = nazwa w dowody/
  if [[ -s "$1" ]]; then
    cp "$1" "$OUT/$2"
    count=$((count + 1))
    echo "  jest: $2   ($(du -h "$OUT/$2" | cut -f1))"
  else
    echo "  brak: $1 (uruchom odpowiednie polecenie, np. make smoke)"
  fi
}

echo "evidence: zbieram dowody do $OUT/"
copy reports/INDEX.md              raport-zbiorczy.md
copy reports/smoke.txt             sprawdzenia-stosu.txt
copy reports/test_report.html      raport-testow.html
copy reports/deck/NoorPointer-10-slajdow.pdf prezentacja.pdf

# Wyniki testow obciazeniowych, jesli ktos je zapisal (make bench > reports/bench.txt)
for extra in reports/bench.txt reports/bench-flood.txt reports/bench-budget.txt; do
  [[ -s "$extra" ]] && copy "$extra" "$(basename "${extra%.txt}").txt"
done

cat > "$OUT/README.md" <<TEXT
# Dowody z dzialania systemu

Wygenerowane **${generated}** z wersji kodu **${commit}** poleceniem \`make evidence\`.
To zrzut wynikow, a nie dokumentacja opisowa - dokumentacje znajdziesz w głównym \`README.md\`,
a instrukcje uruchomienia w \`START.md\`.

| Plik | Co pokazuje |
| :--- | :--- |
| \`raport-zbiorczy.md\` | podsumowanie: co dziala, co jest w trakcie, jak odtworzyc wyniki |
| \`sprawdzenia-stosu.txt\` | 16 sprawdzen spójności stosu (\`make smoke\`) |
| \`raport-testow.html\` | wynik pakietu testów e2e w postaci tabeli (otworz w przeglądarce) |
| \`prezentacja.pdf\` | 10 slajdów zgłoszenia |
| \`bench*.txt\` | wyniki testów obciążeniowych, jeśli zostały zapisane |

## Jak odtworzyc te pliki

\`\`\`bash
sudo make jury      # srodowisko, start stosu, wszystkie testy, ruch na panele, dowody
make evidence       # samo zebranie dowodow z katalogu reports/
\`\`\`

## Uczciwa uwaga

Liczby pochodzą z maszyny zespolu (Arch Linux, 8 wątków CPU), a nie z chmury. Pakiet testów e2e
ma 25 przypadków w parach dozwolone/blokowane; część z nich dotyczy kontroli, których brama jeszcze
nie egzekwuje (sygnatury ataków, budżety, ogranicznik pętli). Pakiet odróżnia stan \`PENDING\`
(kontrola jeszcze nie istnieje) od \`FAIL\` (kontrola jest, ale nie działa) właśnie po to, żeby brak
pracy nie wyglądał jak awaria.
TEXT

echo "evidence: gotowe, skopiowano $count plik(ow) do $OUT/ (razem z README.md)"
