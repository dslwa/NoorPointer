# Decyzja: silnik wykrywania danych osobowych — Presidio, nie GLiNER

## Decyzja

Kontrolę `pii_ner` realizuje **Presidio** (NER + rozpoznawacze wzorców) z modelem spaCy
`en_core_web_lg` oraz własnym rozpoznawaczem PESEL z sumą kontrolną. **GLiNER nie został włączony**
do rozwiązania, choć na etapie planowania był naszym pierwszym wyborem.

## Kontekst

- GLiNER podobał nam się z dwóch powodów: działa **zero-shot** (nowy typ encji opisuje się słowami,
  bez trenowania) i jest **wielojęzyczny**, więc nie wymaga osobnego modelu dla polskiego.
- Wymagania mówią o wykrywaniu i redakcji danych osobowych oraz o tym, że decyzja kontroli musi być
  możliwa do wyjaśnienia i zapisania w audycie.
- Moduł semantyczny pracuje w trybie fail-closed, z twardym limitem czasu na kontrolę.

## Uzasadnienie

1. **Identyfikatory rządzą się wzorcem i sumą kontrolną, nie statystyką.** PESEL, IBAN i numer karty
   to problem formatu i poprawności, a nie rozumienia języka. W Presidio rejestrujemy
   `PatternRecognizer` z `validate_result`, który liczy sumę kontrolną PESEL, więc wynik jest
   **odtwarzalny** (ten sam tekst daje zawsze tę samą decyzję) i **audytowalny** — umiemy powiedzieć
   „wzorzec + poprawna suma kontrolna”. Model probabilistyczny takiego uzasadnienia nie daje.
2. **GLiNER nie zastępuje Presidio, tylko jedno z jego ogniw.** Wykrywanie danych osobowych mamy
   dwuwarstwowe: rozpoznawacze wzorców dla identyfikatorów i NER dla nazw, adresów czy organizacji.
   GLiNER jest **silnikiem NER**, który w Presidio podłącza się w miejsce spaCy — a nie zamiast całej
   biblioteki. Prawdziwy wybór brzmiał więc „który silnik NER”, a nie „która biblioteka”.
3. **Redakcja i offsety i tak wymagały własnego kodu.** Pracujemy na przedziałach znaków, scalanie
   nakładających się encji robimy liniowo, a do gatewaya wysyłamy offsety w **bajtach UTF-8**
   (Presidio liczy znaki). Ta warstwa jest nasza; została zbudowana na wynikach Presidio.
4. **Budżet obrazu i pamięci.** Kontener uruchamia już model DeBERTa (prompt injection) i wywołuje
   Llama Guard. Kolejny model to większy obraz, więcej pamięci i dłuższy start. Presidio jest
   biblioteką, a model spaCy jest częścią obrazu — nic nie jest pobierane w czasie działania.
5. **Ryzyko podmiany na dobę przed zgłoszeniem.** GLiNER nie był u nas mierzony na żadnym zbiorze.
   Wymiana działającego detektora na niezmierzony w ostatniej dobie to zły stosunek zysku do ryzyka,
   zwłaszcza że interfejs zostaje ten sam i ścieżka rozwoju jest otwarta (patrz „Warunek powrotu”).

Dodatkowo same wyniki nie zawierają dopasowanych wartości — do audytu trafiają typy encji, offsety
i wyniki, więc dziennik zdarzeń nie staje się drugim zbiorem danych osobowych.

## Czego świadomie się wyrzekliśmy

- **Zero-shot**: nowy typ encji wymaga u nas nowego rozpoznawacza, a nie samego opisu słownego.
- **Jakości na polskim tekście**: używamy modelu angielskiego i to jest nasza realna słabość —
  w pomiarach słowo „Dane” zostało rozpoznane jako `PERSON` (0,85). To najważniejszy argument
  za GLiNER-em i dlatego mamy zdefiniowany warunek powrotu.

## Dowody z pomiarów (ta maszyna, `POST /v1/scan`, kontrola `pii_ner`)

| Tekst wejściowy | Wynik |
| :--- | :--- |
| `PESEL 44051401359` | `PL_PESEL`, score 1,0 |
| `IBAN PL61109010140000071219812874` | `IBAN_CODE`, score 1,0 |
| `jan.kowalski@example.com` | `EMAIL_ADDRESS`, score 1,0 |
| `Jan Kowalski, PESEL 44051401359, …` | `PERSON` 0,85 + `EMAIL_ADDRESS` 1,0 + `IBAN_CODE` 1,0, czas 6,7 ms |
| `PESEL 95081212345` (błędna suma kontrolna) | brak encji — zgodnie z projektem |
| `Please summarize the quarterly sales report.` | `DATE_TIME` na słowie „quarterly” — fałszywy alarm do wyciszenia w `NOISY_ENTITIES` |

## Warunek powrotu do GLiNER-a

Podmiana ma sens, gdy spełnione są łącznie trzy warunki:

1. mamy **etykietowany zbiór polskich tekstów** (nazwiska, adresy, identyfikatory), na którym można
   porównać modele,
2. GLiNER **poprawia czułość** (recall) na tym zbiorze bez pogorszenia precyzji względem spaCy,
3. czas analizy mieści się w budżecie kontroli wyznaczonym przez politykę (`semantic_timeout_ms`).

Podmiana dotyczy jednego miejsca — `PiiDetector`. Rejestrujemy inny silnik NER; kontrakty HTTP i gRPC,
schematy odpowiedzi, panel i polityka pozostają bez zmian, bo offsety i typy encji są już ustalone.

## Konsekwencje dla reszty systemu

Identyfikatory o znanym formacie są rozstrzygane **również deterministycznie w gatewayu** (kontrola
`pii_regex` w polityce: PESEL, IBAN, e-mail, karta, akcja `redact`). Dzięki temu blokada i redakcja
nie zależą od jakości modelu NER — model dodaje warstwę dla tekstu swobodnego, a nie warunek
konieczny. To także powód, dla którego przykłady w testach i demo muszą mieć **poprawne sumy
kontrolne**, jeśli mają być wykrywane przez model, a nie tylko przez wzorce.
