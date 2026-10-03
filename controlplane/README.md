# NoorPointer — prosty control plane

Pierwsza wersja części zarządzającej zabezpieczeniami agentów AI: **Java 21 / Spring Boot**, dashboard HTML/CSS/JavaScript i baza PostgreSQL. Źródła frontendu znajdują się w sąsiednim katalogu `dashboard/`. Maven kopiuje je do JAR-a, więc uruchomienie lokalne nie wymaga Node ani osobnego procesu. W Docker Compose frontend jest dodatkowo serwowany przez Nginx na porcie 3000 z proxy do API Javy.

## Uruchomienie

Komendy poniżej wykonuj w katalogu `controlplane/` (`cd controlplane`). Z katalogu głównego możesz użyć `make controlplane-run`, `make controlplane-test` i `make controlplane-build`.

Wymagany JDK 21 lub nowszy i uruchomiony Docker Desktop (lub własny PostgreSQL). Maven Wrapper pobierze Maven i zależności przy pierwszym uruchomieniu.

Najprościej z głównego katalogu repo:

```sh
make controlplane-run
```

Komenda uruchamia PostgreSQL w Dockerze, czeka na gotowość bazy i uruchamia Javę z dashboardem. Jeśli uruchamiasz aplikację bezpośrednio z `controlplane/`, najpierw wykonaj `make postgres-up` w głównym katalogu repo, a potem `./mvnw spring-boot:run`.

Otwórz **http://localhost:8082** i kliknij „Connect”. Domyślny lokalny token administratora jest wpisany w formularzu: `local-dev-admin`.

Kliknij **„Load demo”**, aby dodać przykładowe decyzje i raporty zużycia. Każde kliknięcie dodaje nową partię zdarzeń z oznaczeniem `DEMO`. Bez tego baza incydentów jest pusta. Dane, wersje polityk i sygnatury pozostają po restarcie w PostgreSQL (wolumen `postgres-data` w Compose). Poprzednie pliki H2 w `data/` nie są już używane; zachowano je, ale ich zawartość nie jest automatycznie przenoszona.

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
4. Kliknij „Publish” przy nowej wersji. `/api/gateway/policy` zwraca nową konfigurację i nowy ETag.
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

API wymaga `Authorization: Bearer <token>`. Gateway ma dostęp do `/api/gateway/**` i `/api/contracts/**`; reszta API wymaga tokenu administratora. Healthcheck i pliki dashboardu są publiczne, dane dashboardu są chronione.

| Metoda / ścieżka | Funkcja |
| --- | --- |
| `GET /api/dashboard` | Statystyki, budżety i aktywna polityka |
| `GET /api/policies` | Wersje, najnowsze pierwsze |
| `GET /api/policies/active` | Aktywna wersja i czas publikacji |
| `GET /api/policies/{version}` | Szczegóły wersji |
| `POST /api/policies/validate` | Walidacja `{ "document": "JSON lub YAML" }` |
| `POST /api/policies` | Zapis `{ "name": "…", "description": "…", "document": "…" }`; description opcjonalne |
| `POST /api/policies/{version}/publish` | Publikacja/rollback |
| `GET /api/profiles/{name}` | `permissive`, `balanced`, `strict` |
| `GET /api/contracts/{name}` | JSON Schema: `policy`, `audit`, `signatures` |
| `GET /api/gateway/policy` | Dokument polityki, ETag/304 |
| `GET /api/gateway/signatures` | Feed, ETag/304 |
| `POST /api/gateway/events` | Jeden event audytowy |
| `GET /api/events` | Filtry `action`, `category`, `agent`, `from`, `to`; `page`, `size` |
| `GET /api/events/{id}` | Szczegóły eventu |
| `GET /api/events/export?format=json` | `json`, `csv`, `cef`; te same filtry |
| `GET /api/signatures` | Bieżący feed |
| `POST /api/signatures/import` | `{ "document": "JSON lub YAML" }`; zastępuje feed |
| `POST /api/demo/events` | Zdarzenia demo, jeśli włączone |
| `GET /actuator/health` | Healthcheck |
| `GET /actuator/prometheus` | Metryki Spring/Micrometer, token administratora |

Gateway powinien cyklicznie odpytywać politykę i feed, zachowywać ETag i wysyłać `If-None-Match`. Odpowiedź 304 oznacza brak zmian. W audycie raportuje zastosowaną `policy_version`. Control plane generuje `version` przy zapisie, zastępując ewentualny przesłany numer.

Przykładowa decyzja:

```sh
curl http://localhost:8082/api/gateway/events \
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

## Testy i budowanie

Z głównego katalogu repo:

```sh
make controlplane-test
make controlplane-build
java -jar controlplane/target/control-plane-0.1.0.jar
```

Testy używają osobnej bazy `noorpointer_test` i schematu `controlplane_test`, a nie danych aplikacji. Make tworzy bazę testową przed uruchomieniem testów. Dla własnego PostgreSQL utwórz osobną bazę i ustaw `TEST_DATABASE_URL` (domyślnie `jdbc:postgresql://localhost:5432/noorpointer_test?currentSchema=controlplane_test`), `TEST_DATABASE_USER` i `TEST_DATABASE_PASSWORD`, a następnie uruchom `./mvnw verify` w `controlplane/`.

Testy obejmują autoryzację, walidację, publikację wersji, ETag, idempotencję audytu, zużycie, filtrowanie, eksport i atomowy import feedu. GitHub Actions stawia usługę PostgreSQL i uruchamia `verify` przy pushu i pull requestach.

Zakres MVP: pojedyncza instancja, ręczny import feedu, proste tokeny API. Bez kolejek, kont użytkowników i potwierdzeń zastosowania polityki przez gateway. Publikacje są last-write-wins. Dashboard pokazuje dziewięć najnowszych wersji; pełna historia pozostaje dostępna przez API.

## Struktura i zgodność ze zdalnym repo

- `src/`, `pom.xml`, Maven Wrapper należą do `controlplane/`.
- `../dashboard/` jest jedynym źródłem plików frontendu; trafiają do JAR-a podczas builda.
- `Dockerfile` buduj z katalogu głównego repo: `docker build -f controlplane/Dockerfile .`.
- Pierwotny zakres zespołu zachowano w `SPEC.md`, a poprzedni backend Python w `mock/`.
- `POST /api/v1/audit/events` przyjmuje format starszego mocka gateway’a (`timestamp`, `ALLOWED/BLOCKED/REDACTED`, `reason`, `owasp_category`). Wymaga tokenu gateway’a; mapuje zdarzenia do natywnego audytu. `request_id` zapewnia idempotencję. Nie zapisuje surowego `prompt_snippet`.
- `GET /api/v1/audit/export` jest aliasem eksportu, wymaga tokenu administratora.
- `GET /api/v1/policies` zwraca aktualny dokument w formacie **Java JSON Schema**, tak samo jak `/api/gateway/policy`.

`config/policy.yaml` pochodzi z prototypu Go i ma starszy format niż kontrakt Java (`defaults`, `models`, `controls`, `budgets`). Zachowano go dla pracy zespołu. Obecny gateway (`gateway/api/server.go`) jest reverse proxy do upstreamu. Nie egzekwuje jeszcze kontroli, nie pobiera polityki ani nie wysyła audytu — publikacja w Javie nie zmienia jego zachowania. Następny krok po stronie Go to pobieranie i instalowanie polityki z API według `src/main/resources/contracts/policy.schema.json`. Starszy feed regex z `singatures-feed/` również wymaga adaptera do importu w Javie; obecny importer przyjmuje format opisany w kontrakcie `signatures`.
