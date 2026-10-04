# Feed sygnatur

Plik `signatures.json`, importer, Java i obecny Go używają jednego formatu:
[`signatures.schema.json`](../controlplane/src/main/resources/contracts/signatures.schema.json).
Obsługiwane są dopasowania **literalne**, w Go bez rozróżnienia wielkości liter.
Importer nie obcina alternatyw i nie zamienia regexów na tekst. Odrzuca stary format `pattern_type` /
`target_component` oraz `match.type: regex` przed wysłaniem jakiejkolwiek reguły.

```json
{
  "id": "LOCAL-PICKLE-POSIX",
  "name": "Podejrzany argument narzędzia",
  "source": "https://genai.owasp.org/llmrisk/llm01-prompt-injection/",
  "category": "local-indicator",
  "action": "block",
  "target": "tool_arguments",
  "match": {"type": "literal", "value": "posix.system"},
  "enabled": true
}
```

`a|b` oznacza dosłowny tekst zawierający kreskę. Jeśli potrzebne jest „a lub b”, należy utworzyć
dwie reguły z różnymi ID. Reguły nowego feedu są jawnym, ręcznie opracowanym zestawem wskaźników;
nie są automatyczną, równoważną konwersją dawnych regexów.

## Zakres

13 lokalnych wskaźników obejmuje endpointy Ray w treści promptu, polecenia wykonania kodu
i ścieżki traversal w argumentach narzędzi, próby podmiany instrukcji. Endpoint `/api/jobs/`
odpowiada [dokumentacji Ray Jobs](https://docs.ray.io/en/latest/cluster/running-applications/job-submission/rest.html).
Samo wystąpienie ścieżki nie dowodzi wykorzystania podatności. Reguły mogą blokować legalne cytaty
i nie wykrywają wszystkich wariantów ataku. Nie są oficjalnym feedem OWASP ani kompletnymi sygnaturami CVE.
Pliki modeli wymagają osobnego skanowania artefaktów; dopasowanie tekstu `posix.system` go nie zastępuje.

W aktualnym Go `prompt` skanuje wszystkie łańcuchy JSON, `tool_arguments` argumenty `tool_calls`,
`tool_name` nazwy funkcji, `model_artifact` nazwę modelu, a `upstream_path` ścieżkę HTTP gatewaya.
Adres Ray umieszczony w wiadomości musi mieć `target: prompt`, a nie `upstream_path`, które
w wywołaniu chat ma wartość `/v1/chat/completions`.

## Walidacja i aktywacja

```bash
python3 scripts/signature_feed.py validate signatures-feed/signatures.json
./scripts/import-signatures.sh
make reload-policy
```

Importer wymaga Pythona 3, bez dodatkowych bibliotek. Czyta `CONTROLPLANE_URL`
(domyślnie `http://localhost:8082`) i `ADMIN_TOKEN` (lokalnie `local-dev-admin`). Dokłada 13 reguł
oraz 7 reguł startowych Javy przez `POST /api/v1/signatures`. Sprawdza cały dokument i konflikty ID
przed pierwszym zapisem. Ponowny import identycznego wpisu niczego nie zmienia; konflikt ID kończy
się błędem, istniejące wpisy pozostają nietknięte. Awaria sieci w połowie importu może zostawić część
dodanych reguł; polecenie można bezpiecznie powtórzyć.

ID `NOOR-LITERAL-V2-*` rozróżniają poprawione reguły od wcześniejszych, błędnie przekonwertowanych
wpisów. Import nie usuwa starych wpisów ani sygnatur dodanych przez panel. Ich przegląd/usunięcie
wymaga jawnej edycji katalogu. Nie czyść bazy audytu w celu aktualizacji feedu.

Go pobiera **aktywny katalog Javy** z `/api/gateway/signatures`. Nginx na porcie 8085 udostępnia
lokalny plik pomocniczy. Sama zmiana tego pliku nie aktualizuje katalogu Javy.

```bash
make new-signature PATTERN='/etc/passwd' NAME='Local path indicator' TARGET=prompt ACTION=block
```

To polecenie zapisuje regułę atomowo, importuje ją i wymusza reload gatewaya. Bez `PATTERN` używa
tekstu `HACKATHON_ZERO_DAY_PAYLOAD_TEST`. Wartości przekazywane są przez środowisko, bez
interpolowania ich w polecenia powłoki lub ręcznie sklejany JSON. Błąd importu lub reloadu daje
niezerowy kod wyjścia. Sam zapis pliku przez `push_new_signature.sh` jest chroniony blokadą plikową.

Testy importera: `semantic-service/.venv/bin/python -m pytest tests/test_signature_feed.py -q`.
Rzeczywiste dopasowania i hot-reload Go: patrz [testy gatewaya](../tests/README.md).
