# NoorPointer — warstwa kontroli dla systemów agentowych (AI Control Layer)

NoorPointer to pośrednik (reverse proxy) między aplikacją/agentem a modelami LLM i usługami narzędziowymi.
Ruch przechodzi przez niego w obie strony: przed wysłaniem do modelu i po otrzymaniu odpowiedzi.
Warstwa ma egzekwować politykę bezpieczeństwa i budżety zdefiniowane centralnie, rejestrować decyzje
w dzienniku audytowym i udostępniać je w panelu oraz w formacie zrozumiałym dla narzędzi SIEM.

Kontrole są dwojakiego rodzaju:

- **deterministyczne** — tanie i szybkie (wzorce tekstowe, listy dozwolonych modeli i narzędzi, limity zużycia),
- **semantyczne** — klasyfikatory i modele językowe, używane tam, gdzie zwykły wzorzec nie wystarcza
  (próba manipulacji instrukcjami, dane osobowe w wolnym tekście, analiza plików modeli).

Każda kontrola ma w polityce dwie decyzje: czy jest włączona i jaka akcja jest właściwa (zablokować,
zredagować, tylko zalogować). Domyślny tryb pracy to `enforce`; tryb `monitor` nic nie blokuje i służy
do sprawdzenia reguł przed ich włączeniem.

## Stan na dziś

| Obszar | Stan | Uwagi |
| :--- | :--- | :--- |
| Uwierzytelnianie na gatewayu | działa | JWT RS256 (`iss=noorpointer-cp`, `aud=noorpointer-gateway`), wszystkie trasy poza `/healthz`; klucze generuje `make keys` |
| Pobieranie i przeładowanie polityki | działa | gateway pobiera politykę z control plane (`GET /api/gateway/policy`, `ETag`) i odświeża ją cyklicznie oraz na żądanie `make reload-policy` |
| Egzekwowanie kontroli w gatewayu | **nie zaimplementowane** | `withPolicy` na razie tylko loguje tożsamość i wersję polityki |
| Kontrole semantyczne (Python) | działa jako usługa | `/v1/scan` i `/v1/scan/model` odpowiadają poprawnie; gateway jeszcze ich nie wywołuje |
| Audyt i eksport SIEM | działa po stronie control plane | eksport CEF/JSON/CSV i panel działają; gateway nie wysyła jeszcze własnych zdarzeń, więc dziennik zawiera dane demonstracyjne z `make seed` |
| Metryki i alerty | częściowo | Prometheus zbiera `semantic-service` i `controlplane`; gateway nie wystawia jeszcze `/metrics` |
| Testy e2e | 9 z 16 przechodzi | pozostałe 7 wymagają kontroli wymienionych wyżej; szczegóły w `reports/INDEX.md` |

Wniosek dla osób oceniających: działają mechanizmy wokół polityki (uwierzytelnianie, dystrybucja polityki,
przeładowanie, audyt, panel, telemetria, testy), natomiast same kontrole w ścieżce żądania są w trakcie
implementacji po stronie gatewaya. `make verify` pokazuje ten stan bez ukrywania czegokolwiek.

## Szybki start

```bash
# Wymagane: Docker + Docker Compose, make, Go (do wystawiania tokenów), OpenSSL (do kluczy JWT).
# W tym repozytorium docker wymaga sudo (użytkownik nie należy do grupy docker).

make doctor          # sprawdzenie narzędzi, kluczy, konfiguracji compose i działania uwierzytelniania
sudo make up         # budowa i start wszystkich usług + dane demonstracyjne do dziennika
make smoke           # 16 sprawdzeń spójności stosu (health, proxy, uwierzytelnianie)
sudo make test       # testy e2e w kontenerze -> reports/test_report.html
make test-local      # to samo bez Dockera, na opublikowanych portach (pętla kilkusekundowa)
make verify          # smoke + offline-check + scenariusze demo (bez przygotowania)
sudo make checkpoint # wszystko powyżej + reports/INDEX.md + lista adresów
```

`make help` wypisuje wszystkie polecenia z podziałem na sekcje. Polecenia uruchamiane pojedynczo:

```bash
sudo make bench            # k6: narzut przy typowym ruchu
sudo make bench-flood      # k6: duży ruch z próbami ataku
sudo make bench-budget     # k6: równoległe żądania jednego agenta
sudo make demo-full        # scenariusze demonstracyjne agenta
make reload-policy         # natychmiastowe przeładowanie polityki w gatewayu
make new-signature         # demo: dodanie sygnatury ataku do feedu w trakcie działania
make urls                  # adresy usług i dane logowania
```

### Adresy i porty

| Usługa | Technologia | Port | Adres |
| :--- | :--- | :--- | :--- |
| Gateway | Go | 8080 | `http://localhost:8080/v1/chat/completions` (wymaga JWT: `make token`) |
| Dashboard | React + Nginx | 3000 | `http://localhost:3000` (logowanie tokenem `local-dev-admin`) |
| Control Plane | Java / Spring Boot | 8082 | `http://localhost:8082/api/v1`, eksport `?format=cef` |
| Semantic Service | Python | 8001 / 50051 | `http://localhost:8001` (HTTP) i `:50051` (gRPC) |
| Prometheus | Prometheus 2.54 | 9091 | `http://localhost:9091/targets`, `/alerts` |
| Grafana | Grafana 11 | 3001 | `http://localhost:3001` (admin / admin, logowanie wyłączone) |
| Feed sygnatur | Nginx | 8085 | `http://localhost:8085/signatures.json` |
| Mock LLM | Python (API OpenAI i Ollama) | 11434 | `http://localhost:11434` |
| PostgreSQL / Redis | — | 5432 / 6379 | dane audytu i liczniki zużycia |

## Architektura

```
                    Aplikacja / agent AI / klient MCP
                                  |
                                  |  API zgodne z OpenAI (i MCP)
                                  v
        +-------------------------------------------------+
        |  GATEWAY (Go, data plane)                       |
        |  - uwierzytelnianie i autoryzacja agentów [dziala] |
        |  - kontrole deterministyczne            [w toku] |
        |  - budżety (Redis)                      [w toku] |
        |  - limity pętli i lista narzędzi MCP    [w toku] |
        |  - sygnatury znanych ataków             [w toku] |
        |  - polityka z control plane + reload    [dziala] |
        +-------------+--------------------+--------------+
                      |                    |
        żądanie do modelu                    | gRPC :50051 (timeout z polityki)
                      v                    v
        +-------------------------+   +------------------------------+
        |  LLM (mock / Ollama)    |   |  SEMANTIC SERVICE (Python)   |
        |  domyślnie mock-llm     |   |  - klasyfikator manipulacji  |
        +-------------------------+   |  - wykrywanie danych osobowych|
                      |               |  - analiza plików modeli     |
                      |               +------------------------------+
                      | zdarzenia audytowe (docelowo)
                      v
        +---------------------------------------------+
        |  CONTROL PLANE (Java, PostgreSQL)           |
        |  - katalog polityk i wersjonowanie          |
        |  - import sygnatur z feedu                  |
        |  - dziennik audytu i eksport CEF/JSON/CSV   |
        +---------------------+-----------------------+
                              |
                              v
        +---------------------------------------------+
        |  DASHBOARD + TELEMETRIA                     |
        |  - panel zarządzania i widok zdarzeń        |
        |  - Prometheus i Grafana (opóźnienia, błędy) |
        +---------------------------------------------+
```

Opis ścieżki żądania: klient wysyła żądanie do gatewaya z tokenem JWT. Gateway sprawdza token, wczytuje
aktualną politykę i — docelowo — wykonuje kontrole deterministyczne, a w razie potrzeby pyta usługę
semantyczną. Następnie przekazuje żądanie do skonfigurowanego modelu (domyślnie `mock-llm`, opcjonalnie
prawdziwa Ollama). Decyzje trafiają do control plane i są widoczne w panelu oraz w eksporcie.
Elementy oznaczone `[w toku]` to zakres, który nie jest jeszcze włączony w ścieżce żądania.

## Struktura repozytorium

| Katalog | Właściciel | Zakres |
| :--- | :--- | :--- |
| [`gateway/`](gateway/README.md) | Go Dev | Proxy, uwierzytelnianie, kontrole deterministyczne, polityka, metryki |
| [`semantic-service/`](semantic-service/README.md) | Python Dev | Klasyfikacja treści i analiza plików modeli (HTTP + gRPC) |
| [`controlplane/`](controlplane/README.md) | Backend Dev | Polityki, audyt, import sygnatur, eksport SIEM |
| [`dashboard/`](dashboard/README.md) | Frontend Dev | Panel zarządzania i widok zdarzeń |
| [`telemetry/`](telemetry/README.md) | DevOps | Prometheus, reguły alertów, Grafana |
| [`tests/`](tests/README.md) | Python + DevOps | Testy e2e (pary przypadków dozwolonych i blokowanych) |
| [`benchmarks/`](benchmarks/README.md) | DevOps | Skrypty k6 (opóźnienia i przepustowość) |
| [`agent-demo/`](agent-demo/README.md) | DevOps + Devs | Scenariusze demonstracyjne agenta |
| [`signatures-feed/`](signatures-feed/README.md) | DevOps + Python | Feed sygnatur znanych ataków |
| [`scripts/`](scripts) | DevOps | Sprawdzenia, seed, raporty, obsługa tokenów |

## Kontrakty

### 1. Klient do gateway

Zgodny z API OpenAI; jedyne rozszerzenie to `agent_id`, którym posługują się kontrole i budżety.

```http
POST /v1/chat/completions
Authorization: Bearer <JWT RS256>
Content-Type: application/json

{"model": "mock-llm", "agent_id": "agent-sales-01", "messages": [{"role": "user", "content": "..."}]}
```

Każda trasa poza `GET /healthz` wymaga tokenu JWT (RS256, `iss=noorpointer-cp`, `aud=noorpointer-gateway`,
`exp` obowiązuje). Token wystawia się lokalnie kluczem z `gateway/keys/jwt.key` (katalog nie jest
wersjonowany; generuje go `make keys`):

```bash
TOK="$(make token)"                 # wypisuje tylko token, nadaje się do $(...)
make token-file                     # to samo, zapisane do pliku z uprawnieniami 0600
export GATEWAY_JWT="$(make token)"  # sposób, którego używają skrypty, testy i benchmarki
```

Skrypty, benchmarki i testy czytają token ze zmiennej `GATEWAY_JWT` — wewnątrz kontenera plik
z katalogu `/tmp` hosta nie istnieje (to inny system plików), a `make test` sam wstrzykuje tę zmienną
i przerywa z czytelnym komunikatem, gdy tokenu brakuje. Domyślny czas życia tokenu to 24 godziny.
Po ponownym wygenerowaniu kluczy trzeba odtworzyć kontener gatewaya
(`sudo docker compose up -d --force-recreate gateway`), bo klucz publiczny jest czytany tylko przy
starcie; `make doctor` sprawdza, czy dzialajacy gateway przyjmuje świeżo wystawiony token.

### 2. Gateway do usługi semantycznej

```http
POST http://semantic-service:8001/v1/scan
{"text": "...", "direction": "input", "checks": ["prompt_injection", "pii_ner"], "timeout_ms": 200}
```

Analiza pliku modelu (multipart, pole `file`): `POST /v1/scan/model`.
Odpowiedź zawiera `safe` (bool), `verdict` (`safe` / `suspicious` / `dangerous` / `unknown`),
`dangerous_imports` (lista) oraz szczegóły dla każdego pliku. Brak danych nigdy nie jest raportowany
jako `safe`.

### 3. Zdarzenie audytowe

```http
POST http://controlplane:8082/api/v1/audit/events
Authorization: Bearer $GATEWAY_TOKEN
```

Eksport dla narzędzi SIEM (wymaga `ADMIN_TOKEN`): `GET /api/v1/audit/export?format=cef|json|csv`.

### 4. Polityka

Gateway pobiera ją z `GET {CONTROLPLANE_URL}/api/gateway/policy` (nagłówek `Authorization: Bearer $GATEWAY_TOKEN`).
Kształt dokumentu (`config/policy.yaml` w repozytorium jest starszym plikiem prototypowym i nie jest tym,
co widzi gateway):

```json
{
  "version": 2,
  "defaults": {"mode": "enforce", "semantic_timeout_ms": 300, "on_semantic_timeout": "fail_closed"},
  "models": {"allowed": ["llama3.1:8b", "qwen2.5:7b"]},
  "controls": {
    "pii_regex": {"enabled": true, "action": "redact", "types": ["email", "pesel", "iban", "card"]},
    "secrets": {"enabled": true, "action": "block"},
    "prompt_injection": {"enabled": true, "action": "block", "threshold": 0.85},
    "content_safety": {"enabled": true, "action": "block", "categories": ["S1", "S2", "S9"]},
    "attack_signatures": {"enabled": true, "action": "block", "refresh_s": 60},
    "agent_loops": {"enabled": true, "action": "block", "max_steps": 25, "max_identical_tool_calls": 3},
    "mcp_tools": {"enabled": true, "action": "block", "allowed": {"demo-agent": ["search", "calculator"]}}
  },
  "budgets": [
    {"subject": "team:finance", "monthly_usd": 50, "daily_tokens": 200000, "on_exceed": "block"},
    {"subject": "model:local/*", "gpu_seconds_per_hour": 600, "on_exceed": "block"}
  ]
}
```

Parser w gatewayu odrzuca dokument z nieznanymi polami, więc każda zmiana kształtu polityki wymaga
uzgodnienia obu stron.

### 5. Opcjonalny prawdziwy model (Ollama)

```bash
sudo make ollama-up     # start Ollamy, pobranie llama3.2:1b, przełączenie gatewaya na nią
sudo make ollama-down   # powrót na mock-llm (potrzebny do testów oczekujących odpowiedzi echo)
```

Konfiguracja `docker-compose.ollama.yaml` nie publikuje portu Ollamy na hoście, więc nie koliduje
z `mock-llm`. Pierwsza odpowiedź trwa dłużej (ładowanie modelu na CPU), a nazwa modelu musi być wpisana
na liście `models.allowed` w polityce.

## Jak odnosimy się do kryteriów oceny

| Kryterium | Nasz materiał |
| :--- | :--- |
| Kontrole i odporność (30%) | Kontrole deterministyczne i semantyczne są opisane i częściowo wdrożone (usługa semantyczna działa i jest testowana). Brakujące elementy są wymienione w `reports/INDEX.md` i widoczne w wynikach testów. |
| Architektura i wydajność (20%) | Jasny podział na płaszczyznę danych (Go) i usługi pomocnicze, pomiar narzutu przez `make bench`, wyniki w Grafanie i w `reports/`. |
| Raportowanie bezpieczeństwa (20%) | Panel z widokiem zdarzeń i eksport CEF/JSON/CSV; dziennik zasilany obecnie danymi demonstracyjnymi. |
| Kompletność testów (15%) | 16 testów e2e w parach dozwolone/blokowane, uruchamiane jednym poleceniem, z raportem HTML. 9 przechodzi, 7 czeka na kontrole w gatewayu. |
| Wdrożenie i skalowanie (15%) | Start całego stosu jedną komendą, brak pobierania czegokolwiek w czasie działania (`make offline-check`), podmiana modelu bez zmian w kodzie. |

## Zasady pracy w zespole

1. Przed wypchnięciem zmian na `main` uruchom `sudo make test` i `make smoke` — oczekujemy, że stan na `main` jest znany, a nie że wszystko jest zielone.
2. W czasie działania żaden kontener nie może pobierać modeli ani pakietów — to sprawdza `make offline-check`.
3. Serwisy logują na standardowe wyjście, żeby dało się je zebrać przez `make logs`.
4. Dopóki moduł nie jest gotowy, pracujemy przeciwko mockom (`mock-llm`), żeby nie blokować innych.
