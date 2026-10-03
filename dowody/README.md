# Dowody z dzialania systemu

Wygenerowane **2026-10-03 23:07** z wersji kodu **94e7efb** poleceniem `make evidence`.
To zrzut wynikow, a nie dokumentacja opisowa - dokumentacje znajdziesz w głównym `README.md`,
a instrukcje uruchomienia w `START.md`.

| Plik | Co pokazuje |
| :--- | :--- |
| `raport-zbiorczy.md` | podsumowanie: co dziala, co jest w trakcie, jak odtworzyc wyniki |
| `sprawdzenia-stosu.txt` | 16 sprawdzen spójności stosu (`make smoke`) |
| `raport-testow.html` | wynik pakietu testów e2e w postaci tabeli (otworz w przeglądarce) |
| `prezentacja.pdf` | 10 slajdów zgłoszenia |
| `bench*.txt` | wyniki testów obciążeniowych, jeśli zostały zapisane |

## Jak odtworzyc te pliki

```bash
sudo make jury      # srodowisko, start stosu, wszystkie testy, ruch na panele, dowody
make evidence       # samo zebranie dowodow z katalogu reports/
```

## Uczciwa uwaga

Liczby pochodzą z maszyny zespolu (Arch Linux, 8 wątków CPU), a nie z chmury. Pakiet testów e2e
ma 25 przypadków w parach dozwolone/blokowane; część z nich dotyczy kontroli, których brama jeszcze
nie egzekwuje (sygnatury ataków, budżety, ogranicznik pętli). Pakiet odróżnia stan `PENDING`
(kontrola jeszcze nie istnieje) od `FAIL` (kontrola jest, ale nie działa) właśnie po to, żeby brak
pracy nie wyglądał jak awaria.
