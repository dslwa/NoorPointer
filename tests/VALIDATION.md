# Walidacja 2026-10-04

Punkt odniesienia: commit `6be921f` i zmiany Python/Java/UI/feed z tego zadania.
Kod Go, `.proto`, wygenerowane stuby i adapter gRPC Pythona pozostają bez zmian.
Instrukcje odtworzenia: [README.md](README.md).

| Pakiet | Wynik | Czas |
|---|---|---|
| Szybkie testy Pythona, w tym 16 testów OUTPUT i limit współbieżności guard | 206 PASS | 8,32 s |
| Prawdziwe DeBERTa + spaCy PL/EN | 42 PASS, 1 istniejący XFAIL | 35,76 s |
| Prawdziwy Llama Guard, OUTPUT PL/EN z kontekstem, deadline 15 s | 5 PASS | 15,78 s |
| Dashboard: cały pakiet i build | 24 PASS, build OK | 1,96 s + 0,19 s |
| Java: walidacja, API, audyt, feed; 67 różnych przypadków | 66 PASS, potem klasa API 21 PASS z nowym przypadkiem | 11,71 s + 7,46 s |
| Importer: zachowanie literal/target, konflikty, błędy przed zapisem | 10 PASS | 4,05 s |
| Izolowany gateway: OUTPUT/pętle + 8 przypadków budżetowych | 5 PASS, 13 FAIL | 51,04 s |
| Izolowany gateway: nowy feed, pola docelowe i hot-reload sygnatur | 5 PASS | 3,01 s |
| Ponowne E2E: hot-reload przez Javę, odpowiedź na prompt z PESEL, redakcja PII w Pythonie | 3 PASS | 9,24 s |
| E2E działającego stosu: brak limitu / limit 0 dla sub rzeczywistego JWT | 1 PASS, 1 FAIL | 5,97 s |

`./scripts/test-without-go.sh` przeszedł w całości: 206 Python + 10 importer + 25 walidacja polityk
Java + 24 dashboard, build panelu. Nie zmienia działającego stosu ani aktywnej polityki.
Nowy przypadek API Javy potwierdza zachowanie parametrów PII/leakage przy zapisie i odczycie draftu,
włącznie z własnym `ngram`/canary, bez zmiany aktywnej polityki widocznej dla gatewaya.

Model guard: `llama-guard3:1b`, digest
`494147e06bf99e10dbe67b63a07ac81c162f18ef3341aa3390007ac828571b3b`.
DeBERTa: `protectai/deberta-v3-base-prompt-injection-v2`, załadowany z lokalnego cache.
Modele spaCy: `en_core_web_lg` i `pl_core_news_lg`.

Przypadki PL i `[REDACTED:...]` z nowego zestawu przechodzą. Znany XFAIL dotyczy zwykłej prośby
o zwrot na kartę, błędnie rozpoznawanej przez DeBERTa jako injection. Mały zestaw regresyjny nie
stanowi pomiaru ogólnej skuteczności na języku polskim.

## Konkretne braki wykazane w Go

Testowany obraz, zbudowany z aktualnych źródeł:
`noorpointer-gateway:acceptance`, ID
`sha256:915b236e609722463d6f4df4d53c4661ee8cc388050cfdfd0edde2c5859e2d7f`.

Braki OUTPUT i pętli dają pięć błędów, bez XFAIL/SKIP:

1. OUTPUT zawierający e-mail trafia do klienta bez redakcji.
2. OUTPUT zawierający syntetyczny sekret GitHub otrzymuje HTTP 200 zamiast blokady.
3. OUTPUT z niebezpieczną instrukcją otrzymuje HTTP 200.
4. OUTPUT powtarzający instrukcję systemową otrzymuje HTTP 200.
5. Cztery rzeczywiste wywołania tego samego narzędzia z tymi samymi argumentami otrzymują
   `[200, 200, 200, 200]`, pomimo limitu 3 identycznych wywołań.

Przechodzą: niezmieniona bezpieczna odpowiedź, redakcja e-maila i PESEL **przed** modelem,
hot-reload `200 → 403 → 200` bez restartu procesu i dwa różne wywołania narzędzia.
Testy OUTPUT potwierdzają, że bezpieczny prompt dotarł do modelu, zanim ten zwrócił zagrożenie.
Stanowią kryteria odbioru dalszej implementacji gatewaya, nie dowód gotowego filtrowania OUTPUT.

Nowe testy budżetów dają kolejnych osiem błędów: brak wyczerpania, niezależności limitów tożsamości,
limitu zespołu/modelu i rezerwacji. Przy limicie 96 tokenów przechodzi 12 równoległych wywołań
po 32 tokeny, czyli **384 tokeny**. Nawet limit 0 dla `sub` poprawnie podpisanego JWT daje HTTP 200.
Potwierdzono to również na działającym stosie z prawdziwą odpowiedzią Ollamy; test przywrócił politykę.
Dwa przypadki finansowe/compute zakładają symulowane `usage.cost_usd` / `usage.gpu_seconds`
z zaufanego adaptera providera. Nie potwierdzają rozliczeń realnego API ani pomiaru GPU;
wymagana integracja źródła telemetrii jest opisana w [GO_HANDOFF.md](GO_HANDOFF.md).

Poprawione sygnatury działają na obecnym Go: literalny endpoint w prompcie i wskaźnik w argumentach
narzędzia są blokowane przed modelem, bezpieczny tekst przechodzi. Reguła argumentów nie blokuje
jej cytatu w prompcie. Reload wyłącza i przywraca blokadę, zachowując dosłowne `first|second`.

## Ograniczenia pomiaru i pozostałego E2E

Pierwszy pełny przebieg istniejącego E2E: 16 PASS, 9 FAIL. Wystąpiły timeout odpowiedzi lokalnego LLM,
`503 SEMANTIC_UNAVAILABLE` oraz błędne wcześniejsze założenie, że LLM powtórzy znacznik redakcji.
Poprawiono założenie o echo, ograniczono generowaną odpowiedź i odseparowano test hot-reload PII
od obciążenia detektorów. Trzy zmienione przypadki sprawdzono ponownie z wynikiem PASS, włącznie
z przywróceniem poprzedniej polityki. Nie deklarujemy przejścia całego E2E ani potwierdzenia budżetów.

Czas jednej kontroli prawdziwego Llama Guard w powtórzonym przebiegu z `GUARD_CONCURRENCY=1`
wyniósł 1825–3390 ms (mediana 2684 ms). W poprzednim przebiegu było 3399–8459 ms (mediana 7819 ms).
To dwa małe pomiary na współdzielonym CPU, bez izolacji obciążenia: nie dowodzą przyspieszenia ani SLA.
Test jakości używa teraz budżetu **15 s** i wymaga statusu `ok`; timeout nie oznacza wykrycia ataku.
Pakiet akceptacyjny używa polityki z limitem 10 s. Limit klienta gRPC w gatewayu i faktyczna latencja
modelu muszą zostać uzgodnione przed oceną dostępności całej ścieżki.

Nowe profile mają 15 s, a Compose z Ollamą ogranicza współbieżność. Nie przebudowywano działających
kontenerów i nie opublikowano nowych profili. Wersje `*-output` pozostają draftami do integracji,
ponieważ obecny Go odrzuca ich nowe pola. Przekazywanie parametrów przez gRPC jest celowo odłożone.

Raporty JUnit z sesji: `/tmp/noorpointer-semantic.xml`, `/tmp/noorpointer-models.xml`,
`/tmp/noorpointer-ollama.xml`, `/tmp/noorpointer-gateway-acceptance.xml`,
`/tmp/noorpointer-e2e.xml`, `/tmp/noorpointer-e2e-changed.xml`.
Nowsze przebiegi: `/tmp/noorpointer-semantic-v2.xml`, `/tmp/noorpointer-ollama-v2.xml`,
`/tmp/noorpointer-gateway-v2.xml`, `/tmp/noorpointer-signature-gateway.xml`,
`/tmp/noorpointer-e2e-budgets.xml`, `/tmp/noorpointer-without-go.log`.
Raporty Javy: `controlplane/target/surefire-reports/`.
