# Prezentacja zgłoszeniowa (10 slajdów)

Źródłem treści jest **`slajdy.md`** — zwykły Markdown, więc każdy może go poprawić (także agent).
Z niego powstaje HTML i PDF:

```bash
make deck          # albo: ./deck/build.sh
```

Wynik:

- `reports/deck/NoorPointer-10-slajdow.pdf` — plik do wysłania na HackTribe (10 stron, format 1280×720),
- `reports/deck/deck.html` — podgląd w przeglądarce; `Ctrl+P` z formatem poziomym i bez marginesów
  daje ten sam PDF, jeśli ktoś woli wydrukować ręcznie.

`reports/` nie jest wersjonowane, więc po sklonowaniu repo wystarczy `make deck`, żeby odtworzyć plik.

## Konwencja `slajdy.md`

| Składnia | Efekt |
| :--- | :--- |
| `# Nagłówek` | tytuł slajdu |
| `## Podtytuł` | podtytuł |
| `- punkt` | lista punktowana (obsługuje `**pogrubienie**` i `` `kod` ``) |
| `> zdanie` | ramka z najważniejszą informacją |
| ```` ``` ```` … ```` ``` ```` | blok tekstu, np. schemat architektury |
| `---` | granica slajdu |

Wymaganie regulaminu to **maksymalnie 10 slajdów** — obecnie jest dokładnie 10, po jednym na:
tytuł, problem, rozwiązanie, guardrails (30%), politykę i sygnatury, raportowanie (20%),
architekturę i wydajność (20%), pakiet testów (20%), wdrażalność (10%), stan i plan.

## Do uzupełnienia przed wysłaniem

1. **Zrzuty ekranu** (opcjonalnie, wzmacniają kryterium raportowania): panel incydentów, katalog
   sygnatur, Grafana. Wstaw je do slajdu 6 jako linię `![opis](img/plik.png)` — katalog `deck/img/`
   jest wersjonowany, a `build.py` obsługuje obrazy w linii.

Nazwa zespołu, skład i liczby z k6 (p95 2,28 ms przy 506 żądaniach na sekundę) są już w treści.
