# NoorPointer — prosty control plane

Pierwsza wersja części zarządzającej zabezpieczeniami agentów AI: **Java 21 / Spring Boot**, dashboard React / Vite i baza PostgreSQL. Źródła frontendu znajdują się w sąsiednim katalogu `dashboard/`. Maven instaluje zależności (`npm ci`), buduje React (`npm run build`) i kopiuje wynik z `dashboard/dist/` do JAR-a. Lokalny build wymaga Node.js 22.12+ (zalecany 24), ale gotowy JAR działa bez Node i bez osobnego procesu frontendu. W Docker Compose frontend jest dodatkowo serwowany przez Nginx na porcie 3000 z proxy do API Javy.

## Uruchomienie

Komendy poniżej wykonuj w katalogu `controlplane/` (`cd controlplane`). Z katalogu głównego możesz użyć `make controlplane-run`, `make controlplane-test` i `make controlplane-build`.

Wymagany JDK 21 lub nowszy, Node.js 22.12+ (zalecany 24) i uruchomiony Docker Desktop (lub własny PostgreSQL). Maven Wrapper pobierze Maven i zależności przy pierwszym uruchomieniu.

Najprościej z głównego katalogu repo:

```sh
make controlplane-run
```

Komenda uruchamia PostgreSQL w Dockerze, czeka na gotowość bazy, buduje React i uruchamia Javę z dashboardem. Jeśli uruchamiasz aplikację bezpośrednio z `controlplane/`, najpierw wykonaj `make postgres-up` w głównym katalogu repo, a potem `./mvnw spring-boot:run`.

Otwórz **http://localhost:8082** i kliknij „Connect”. Domyślny lokalny token administratora jest wpisany w formularzu: `local-dev-admin`.

Kliknij **„Load demo”**, aby dodać przykładowe decyzje i raporty zużycia. Każde kliknięcie dodaje nową partię zdarzeń z oznaczeniem `DEMO`. Bez tego baza incydentów jest pusta. Dane, wersje polityk i sygnatury pozostają po restarcie w PostgreSQL (wolumen `postgres-data` w Compose). Poprzednie pliki H2 w `data/` nie są już używane; zachowano je, ale ich zawartość nie jest automatycznie przenoszona.

Do pracy nad frontendem uruchom w drugim terminalu `make dashboard-dev` z głównego katalogu. Vite na **http://localhost:5173** przeładowuje zmiany i przekazuje `/api` do Javy na 8082. Docker buduje React we własnym etapie Node; na hoście wymaga tylko Dockera.

## Co działa

- **Przegląd:** decyzje i blokady z ostatnich 7 dni UTC, kategorie blokad, tokeny, koszt i zużycie budżetów.
- **Polityki:** trzy profile startowe, włączanie kontroli, zmiana akcji i progu prompt injection, edytor JSON/YAML, walidacja JSON Schema, zapis nowych wersji i publikacja. Można też ponownie opublikować starszą wersję.
- **Zdarzenia:** filtrowanie po akcji, agencie i kategorii, stronicowanie, szczegóły oraz eksport JSON, CSV i CEF.
- **Sygnatury:** ręczny import JSON/YAML, walidacja i atomowe zastąpienie całego feedu. Reguły mają ID, źródło, kategorię, akcję, cel i literalny tekst do dopasowania.
- **API gateway’a:** aktualna polityka i feed z ETag/304 oraz przyjmowanie zdarzeń z ochroną przed powtórnym naliczeniem tego samego ID.

To control plane. Wykrywanie zagrożeń, proxy LLM/MCP, egzekwowanie polityki i limitów oraz modele AI należą do osobnych serwisów Go/Python. Liczba włączonych kontroli opisuje konfigurację. Polityka jest udostępniana od razu po publikacji; moment jej zastosowania zależy od implementacji i odpytywania gateway’a.

## Scenariusz demo

1. Wczytaj dane demo i obejrzyj wykres oraz budżety.
2. W „Policies” utwórz kopię `balanced`, zmień próg lub wyłącz kontrolę.
3. Sprawdź konfigurację i zapisz nową wersję. Aktywna polityka jeszcze się nie zmienia.
4. Kliknij „Publish” przy nowej wersji. `/api/v1/active-policy/document` zwraca nową konfigurację i nowy ETag.
5. W „Events” wybierz `block`, otwórz szczegóły i pobierz CSV.

Dane demo są syntetyczne i nie symulują silnika detekcji ani zastosowania zmienionej polityki w gateway’u.

## Konfiguracja

| Zmienna | Domyślnie | Znaczenie |
| --- | --- | --- |
| `PORT` | `8082` | Port aplikacji |
| `SERVER_ADDRESS` | `127.0.0.1` | Adres nasłuchiwania |
| `ADMIN_TOKEN` | `local-dev-admin` | Dostęp do zarządzania |
| `GATEWAY_TOKEN` | `local-dev-gateway` | Pobieranie konfiguracji i wysyłanie zdarzeń |
| `DEMO_ENABLED` | `true` | Dostępność przycisku i endpointu demo |
| `DATABASE_URL` | `jdbc:postgresql://localhost:5432/noorpointer?currentSchema=controlplane` | JDBC URL bazy |
| `DATABASE_USER` | `noor` | Użytkownik bazy |
| `DATABASE_PASSWORD` | `noorpass` | Hasło bazy |

Tokeny muszą być różne i niepuste. Przy udostępnianiu aplikacji zmień je, wyłącz demo i zapewnij HTTPS. Dashboard przechowuje token w `sessionStorage` danej karty przeglądarki.

Przykład podłączenia istniejącego Postgresa:

```sh
DATABASE_URL='jdbc:postgresql://localhost:5432/noorpointer?currentSchema=controlplane' \
DATABASE_USER=noorpointer DATABASE_PASSWORD=twoje-haslo \
ADMIN_TOKEN=twoj-token-admina GATEWAY_TOKEN=twoj-token-gatewaya \
DEMO_ENABLED=false ./mvnw spring-boot:run
```

Schemat tworzą migracje Flyway. W Compose Java używa osobnego schematu `controlplane`, dzięki czemu istniejące tabele mocka w schemacie `public` pozostają zachowane. Lokalnie i w Compose aplikacja używa wyłącznie PostgreSQL; schemat `controlplane` jest tworzony automatycznie.

## Kontrakt integracji

API wymaga `Authorization: Bearer <token>`. Endpointy panelu mają wspólny prefiks `/api/v1`. Gateway może pobierać dokument aktywnej polityki, feed i schematy oraz wysyłać audyt; pozostałe operacje wymagają administratora. Healthcheck i pliki dashboardu są publiczne, dane panelu są chronione.

| Metoda / ścieżka | Funkcja |
| --- | --- |
| `GET /api/v1/dashboard` | Statystyki, budżety i aktywna polityka |
| `GET /api/v1/policy-revisions` | Wersje, najnowsze pierwsze |
| `POST /api/v1/policy-revisions` | Zapis `{ "name": "…", "description": "…", "document": "JSON lub YAML" }`; `201 Created` i `Location` |
| `GET /api/v1/policy-revisions/{version}` | Szczegóły niezmiennej wersji |
| `DELETE /api/v1/policy-revisions/{version}` | Usunięcie nieaktywnej wersji; `204`, aktywna wersja: `409` |
| `GET /api/v1/active-policy` | Aktywna wersja i czas publikacji |
| `PUT /api/v1/active-policy` | Publikacja/rollback: `{ "version": 3 }`; ponowienie tej samej wersji zachowuje czas publikacji |
| `GET /api/v1/active-policy/document` | Dokument dla gateway’a, ETag/304 |
| `POST /api/v1/policy-validations` | Walidacja `{ "document": "JSON lub YAML" }` bez zapisu |
| `GET /api/v1/policy-profiles/{name}` | `permissive`, `balanced`, `strict` |
| `GET /api/v1/schemas/{name}` | JSON Schema: `policy`, `audit`, `signatures` |
| `GET /api/v1/signature-feed` | Bieżący feed, ETag/304 |
| `POST /api/v1/signatures` | Dodaje pojedynczą sygnaturę bez usuwania pozostałych; `201 Created` i `Location`. Powtórzone ID lub przekroczenie 1000 reguł: `409 Conflict` |
| `GET /api/v1/signatures/{id}` | Szczegóły sygnatury; brak ID: `404 Not Found` |
| `PUT /api/v1/signature-feed` | `{ "document": "JSON lub YAML" }`; atomowo zastępuje cały feed, zwraca `{ "signatures": [...] }` |
| `POST /api/v1/audit-events` | Jeden event; `201 Created` i `Location` przy nowym ID, `200 OK` przy ponowieniu |
| `GET /api/v1/audit-events` | Filtry `action`, `category`, `agent`, `from`, `to`; `page`, `size` |
| `GET /api/v1/audit-events/{id}` | Szczegóły eventu |
| `GET /api/v1/audit-events/export?format=json` | `json`, `csv`, `cef`; te same filtry |
| `POST /api/v1/demo-batches` | Nowa partia demo: `201`, ID partii i liczba zdarzeń; jeśli demo jest włączone |
| `GET /actuator/health` | Healthcheck |

Migracja V2 instaluje siedem domyślnych sygnatur z `src/main/resources/signatures/defaults.json` jednorazowo, także przy aktualizacji istniejącej bazy. Zachowuje istniejące ID i respektuje limit 1000 reguł; przy pełnym feedzie nie dokłada kolejnych. Późniejsze zmiany i usunięcia nie są cofane po restarcie. Reguły to własne przykłady inspirowane OWASP, domyślnie w trybie `monitor`.

`POST /api/v1/signatures` przyjmuje obiekt w `application/json`, a także wklejony JSON/YAML jako `text/plain`, `application/yaml` lub `application/x-yaml`. Wklejaj pojedynczą sygnaturę (bez opakowania `signatures`). Każda ścieżka wykonuje tę samą walidację i dopisuje regułę transakcyjnie.
| `GET /actuator/prometheus` | Metryki Spring/Micrometer, token administratora |

Zapis tworzy nową wersję przez `POST`; wersje są niezmienne. Zmiana pojedynczego zasobu aktywnej polityki i zastąpienie feedu używają `PUT`. Błędy zwracają jednolity JSON: `status`, `message`, `path`, `timestamp`, z odpowiednim kodem HTTP (`400`, `401`, `403`, `404`, `405`, `409`, `415`, `500`).

Przycisk **Delete** przy wersji polityki usuwa nieaktywną wersję po potwierdzeniu. Dla aktywnej wersji jest wyłączony; API również blokuje jej usunięcie. Zdarzenia audytowe i zapisany w nich numer wersji pozostają zachowane.

Starsze ścieżki integracyjne gateway’a pozostają w `controller/compatibility/`: `GET /api/gateway/policy`, `GET /api/gateway/signatures`, `POST /api/gateway/events`, `GET /api/contracts/{name}`, `GET /api/v1/policies`, `POST /api/v1/audit/events` i `GET /api/v1/audit/export`. Panel korzysta z nowego API. Starsze endpointy zarządzania `/api/policies`, `/api/events`, `/api/signatures/import` i `/api/demo/events` zostały zastąpione ścieżkami z tabeli.

Gateway powinien cyklicznie odpytywać politykę i feed, zachowywać ETag i wysyłać `If-None-Match`. Odpowiedź 304 oznacza brak zmian. W audycie raportuje zastosowaną `policy_version`. Control plane generuje `version` przy zapisie, zastępując ewentualny przesłany numer.

Przykładowa decyzja:

```sh
curl http://localhost:8082/api/v1/audit-events \
  -H 'Authorization: Bearer local-dev-gateway' \
  -H 'Content-Type: application/json' \
  -d '{
    "id": "event-unique-001",
    "occurred_at": "2026-10-03T10:00:00Z",
    "kind": "decision",
    "request_id": "request-001",
    "agent_id": "finance-agent",
    "team": "finance",
    "model": "llama3.1:8b",
    "control": "prompt_injection",
    "action": "block",
    "severity": "high",
    "category": "LLM01:2025",
    "policy_version": 2,
    "message": "Prompt injection detected",
    "context": {"reason_code": "INJECTION_THRESHOLD"}
  }'
```

Wysyłaj jedną końcową `decision` na żądanie. Zużycie raportuj osobnym eventem `kind: "usage"`, z własnym unikalnym `id`, tym samym `request_id` i polami `tokens`, `cost_usd`, `gpu_seconds`. Tylko `usage` zasila koszty i budżety. Powtórzenie `id` zwraca `accepted: false` i zachowuje pierwszy zapis, również przy innej ponowionej treści. Gateway odpowiada za stabilne ID przy retry i kontekst zredagowany bez sekretów.

Filtry czasu: ISO-8601 UTC, `from` włącznie, `to` wyłącznie. Strona: domyślnie 20, maksymalnie 100 elementów. Eksport: maksymalnie 10 000 zdarzeń, potem trzeba zawęzić filtry. Budżety dzienne/miesięczne: UTC; GPU: ruchome okno ostatnich 3600 sekund. `*` w podmiocie budżetu dopasowuje dowolny fragment identyfikatora.

Eksport CEF zawiera akcję, kategorię OWASP, czasy zdarzenia i odbioru, dane agenta, żądania, sesji, modelu, zespołu, wersję polityki i metryki. JSON zachowuje pełny kontekst. Mapowanie pól, przykłady pobrania i wymagania importu do SIEM opisano w [SIEM.md](SIEM.md).

## Testy i budowanie

Z głównego katalogu repo:

```sh
make controlplane-test
make controlplane-build
java -jar controlplane/target/control-plane-0.1.0.jar
```

Testy używają osobnej bazy `noorpointer_test` i schematu `controlplane_test`, a nie danych aplikacji. Make tworzy bazę testową przed uruchomieniem testów. Dla własnego PostgreSQL utwórz osobną bazę i ustaw `TEST_DATABASE_URL` (domyślnie `jdbc:postgresql://localhost:5432/noorpointer_test?currentSchema=controlplane_test`), `TEST_DATABASE_USER` i `TEST_DATABASE_PASSWORD`, a następnie uruchom `./mvnw verify` w `controlplane/`.

Testy obejmują autoryzację, walidację, publikację wersji, ETag, idempotencję audytu, zużycie, filtrowanie, eksport i atomowy import feedu. Uruchamiaj je lokalnie przez `make controlplane-test`.

Zakres MVP: pojedyncza instancja, ręczny import feedu, proste tokeny API. Bez kolejek, kont użytkowników i potwierdzeń zastosowania polityki przez gateway. Publikacje są last-write-wins. Dashboard pokazuje dziewięć najnowszych wersji; pełna historia pozostaje dostępna przez API.

## Struktura i zgodność ze zdalnym repo

Kod Javy jest podzielony według odpowiedzialności w `src/main/java/pl/noorpointer/`:

- `controller/`: cienkie kontrolery REST i dobór kodów HTTP.
- `controller/compatibility/`: adaptery starszych kontraktów gateway’a.
- `service/`: logika aplikacji, transakcje, audyt, raportowanie i demo.
- `repository/`: wszystkie zapytania SQL i mapowanie rekordów PostgreSQL.
- `dto/`: typowane żądania/odpowiedzi oraz walidacja wejścia.
- `config/`: bezpieczeństwo i inicjalizacja profili.
- `document/`: parsowanie JSON/YAML i walidacja JSON Schema.
- `exception/`: wspólna obsługa błędów API.
- `web/`: ETag i odpowiedzi eksportu.

Kontrolery delegują do serwisów, a serwisy do repozytoriów. Wstrzykiwanie zależności odbywa się przez konstruktory; repozytoria nie zajmują się HTTP. Profile i migracje pozostają w `src/main/resources/`. Schemat bazy nie zmienił się w wyniku porządkowania kodu.

- `src/`, `pom.xml`, Maven Wrapper należą do `controlplane/`.
- `../dashboard/src/` jest źródłem komponentów React; Maven buduje Vite i pakuje `dashboard/dist/` do JAR-a.
- `Dockerfile` buduj z katalogu głównego repo: `docker build -f controlplane/Dockerfile .`.
- Pierwotny zakres zespołu zachowano w `SPEC.md`, a poprzedni backend Python w `mock/`.
- `POST /api/v1/audit/events` przyjmuje format starszego mocka gateway’a (`timestamp`, `ALLOWED/BLOCKED/REDACTED`, `reason`, `owasp_category`). Wymaga tokenu gateway’a; mapuje zdarzenia do natywnego audytu. `request_id` zapewnia idempotencję. Nie zapisuje surowego `prompt_snippet`.
- `GET /api/v1/audit/export` jest aliasem eksportu, wymaga tokenu administratora.
- `GET /api/v1/policies` zwraca aktualny dokument w formacie **Java JSON Schema**, tak samo jak `/api/gateway/policy`.

`config/policy.yaml` pochodzi z prototypu Go i ma starszy format niż kontrakt Java (`defaults`, `models`, `controls`, `budgets`). Zachowano go dla pracy zespołu. Obecny gateway (`gateway/api/server.go`) jest reverse proxy do upstreamu. Nie egzekwuje jeszcze kontroli, nie pobiera polityki ani nie wysyła audytu — publikacja w Javie nie zmienia jego zachowania. Następny krok po stronie Go to pobieranie i instalowanie polityki z API według `src/main/resources/contracts/policy.schema.json`. Starszy feed regex z `singatures-feed/` również wymaga adaptera do importu w Javie; obecny importer przyjmuje format opisany w kontrakcie `signatures`.
