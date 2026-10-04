# Integracja po zakończeniu testów Python / Java

Na prośbę użytkownika **nie zmieniono kodu Go, `.proto`, wygenerowanych stubów ani adaptera gRPC
w Pythonie**. Nowe pola polityki są przygotowane w Javie, ale nie są jeszcze przesyłane przez gRPC.
Nie należy publikować profili `*-output` do obecnego gatewaya: jego parser odrzuca nieznane pola,
nawet gdy kontrola jest wyłączona. Dotychczasowe profile pozostają w starym formacie.

## Co można testować teraz

`./scripts/test-without-go.sh` sprawdza Python i istniejący kontrakt gRPC, importer sygnatur,
walidację polityki Java i panel. Nie buduje Go, nie publikuje polityki ani nie zmienia kontenerów.
Nowe profile można walidować jako dokumenty/drafty w Javie. Przejście walidacji nie oznacza, że
gateway obsługuje ich pola. Testy modeli i E2E mają osobne polecenia w [README.md](README.md).

## Pola do obsługi przez gateway

| Kontrola | Pola centralnej polityki | Egzekwowanie |
|---|---|---|
| `pii_ner` | `enabled`, `action`, `directions`, `threshold`, `entities`, `timeout_ms` | input/output, block/redact/monitor; redakcja według spanów UTF-8 |
| `leakage` | `enabled`, `action`, `directions: [output]`, `threshold`, `ngram`, `canaries`, `timeout_ms` | tylko output, block/monitor |

Próg PII dotyczy pewności encji (`config.pii_ner.score_threshold` w HTTP Pythona), a próg leakage
wyniku porównania. Parametry HTTP detektorów już istnieją. Obecny `CheckSpec` przenosi tylko rodzaj
kontroli i timeout; adapter gRPC używa domyślnych parametrów Pythona, więc np. obniżenie progu PII
poniżej 0,5 w Go nie przywróci wcześniej odfiltrowanych encji.
Przekazanie `entities`, `ngram` i progu ekstrakcji wymaga późniejszego wspólnego rozszerzenia
kontraktu Go/Python. Nie utworzono niejawnego kanału parametrów ani drugiego proxy.

Obecny kontrakt już pozwala zażądać `CHECK_PII_NER` i `CHECK_SYSTEM_PROMPT_LEAK` na OUTPUT
z domyślną konfiguracją. Przekaż wszystkie wiadomości systemowe, ostatnie pytanie użytkownika
i odpowiedź modelu z poprawnymi rolami. Wymagaj wyniku dla każdej pary wiadomość/kontrola,
obsłuż błędy i timeouty, zawsze blokuj `STATUS_REJECTED`. Nie wysyłaj niesprawdzonych fragmentów
streamingu do klienta; streaming wymaga osobnej strategii i testów.

## Budżety i audyt

`tests/test_gateway_budgets.py` uruchamia rzeczywisty proces Go, własne podpisane JWT i kontrolowany
provider HTTP. Tożsamość to `sub`/`team` ze zweryfikowanego JWT; `agent_id` w JSON i nagłówki
`X-Agent-ID` / `X-Team-ID` nie nadają uprawnień. Podmioty i nazwy modeli są unikalne dla testu.
`TEST_REDIS_URL` domyślnie wskazuje bazę 15 na `127.0.0.1:6379`; testy nie wykonują FLUSHDB.

Testy wymagają faktycznego zużywania 32 tokenów na odpowiedź, utrzymania wyczerpanego limitu,
odseparowania agentów, wspólnego limitu zespołu/modelu i atomowej rezerwacji dla 12 równoległych
żądań przy limicie 96 tokenów. Odmowa to HTTP 429 / `code: BUDGET_EXCEEDED`, bez wywołania providera.
Należy egzekwować wszystkie pasujące limity; rezerwację rozliczyć z rzeczywistym zużyciem i zwolnić
niewykorzystaną część. Błąd upstream/Redis i granice okien wymagają dalszych testów po implementacji.

**Koszt i GPU: założenie do uzgodnienia.** Dwa przypadki używają rozszerzeń zaufanego adaptera
providera: `usage.cost_usd` oraz `usage.gpu_seconds`. Nie są to standardowe pola API modeli ani
nowa zmiana gRPC. Fixture symuluje telemetrię, nie mierzy GPU i nie kupuje tokenów komercyjnych.
Jeżeli Go liczy koszt z cennika/modelu i tokenów albo czyta metryki lokalnego wykonawcy, należy
podpiąć te źródła w fixture, zachowując asercje zużycia i braku przekroczeń. Kosztów i czasu GPU
nie wolno przyjmować z niezaufanego żądania klienta; czas ścienny na CPU nie jest czasem GPU.
Bez podłączenia wiarygodnego źródła nie można deklarować gotowej kontroli kosztów/compute.

Java przyjmuje decyzje/usage w istniejącym `/api/gateway/events` i agreguje je w panelu.
Zwykłe wywołania proxy powinny wysyłać tam faktyczne decyzje i zużycie, z ID do deduplikacji;
manualny Prompt Check nie zastępuje tej integracji. Trzeba potwierdzić to testami po stronie Go.

## Odbiór

```bash
semantic-service/.venv/bin/python tests/run_gateway_acceptance.py --build --budgets \
  --junitxml=/tmp/gateway-acceptance.xml
```

Brak implementacji daje FAIL, bez maskowania przez XFAIL. Testy używają osobnego gatewaya
i kontrolowanej odpowiedzi modelu; jakość prawdziwego Llama Guard jest sprawdzana oddzielnie.
Aktualne wyniki i ograniczenia: [VALIDATION.md](VALIDATION.md).
