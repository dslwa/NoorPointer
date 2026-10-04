# NoorPointer — warstwa kontroli dla systemów agentowych (AI Control Layer)

> **Oceniasz projekt i chcesz go uruchomić?** Zacznij od [`START.md`](START.md): jedna komenda
> (`sudo make jury`), siedem poleceń dla osób oceniających i gotowe dowody w katalogu `dowody/`.
> Ten plik jest pełną dokumentacją techniczną, pisaną dla zespołu.

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
| Egzekwowanie kontroli w gatewayu | **częściowo** | Allowlista modeli, sekrety, PII i literalne sygnatury na wejściu; testy wykazują brak filtrowania OUTPUT, budżetów i ogranicznika pętli |
| Kontrole semantyczne (Python) | działa jako usługa i **w ścieżce żądania** | gateway woła gRPC `Analyze` dla `prompt_injection` i `content_safety` (timeout i `fail_closed` z polityki); `pii_ner` i `leakage` działają w usłudze, ale brama ich jeszcze nie woła |
| Audyt i eksport SIEM | działa po stronie control plane | Eksport CEF/JSON/CSV, panel i audyt Prompt Check działają; zwykłe wywołania proxy wymagają jeszcze wysyłania decyzji i zużycia |
| Katalog sygnatur | działa | 7 reguł startowych + 13 lokalnych literalnych wskaźników; importer zachowuje treść i target, odrzuca regex i konflikty ID |
| Metryki i alerty | częściowo | Prometheus zbiera `semantic-service` (scrape naprawiony: `metrics_path: /metrics/` + `Host $http_host` w LB) i `controlplane`; gateway nie wystawia jeszcze `/metrics` |
| Testy e2e | `tests/test_guardrails.py` — **25 przypadków** | pary dozwolone/blokowane (PII, sekrety, prompt injection, sygnatury, budżety, pętle, skaner modeli, hot-reload, eksport SIEM, kontrole semantyczne); aktualny wynik i lista otwartych pozycji w `reports/INDEX.md` |
| Testy modułów | działają | Python: 206 PASS; Java: 67 PASS w osobnej bazie; dashboard: 24 PASS; importer: 10 PASS. Bez zmiany Go: `./scripts/test-without-go.sh` |

Wniosek dla osób oceniających: działa cała otoczka wokół polityki (uwierzytelnianie, dystrybucja polityki,
przeładowanie, audyt, panel, telemetria, testy), a w samej ścieżce żądania brama egzekwuje już allowlistę
modeli, wykrywanie sekretów, redakcję danych osobowych oraz kontrole semantyczne (prompt injection,
content safety) przez gRPC oraz literalne sygnatury. Otwarte pozostają OUTPUT, budżety,
ogranicznik pętli i integracja audytu proxy. Aktualne dowody: [tests/VALIDATION.md](tests/VALIDATION.md).
Nowe profile Java `*-output` są do walidacji/draftów; obecny Go ich jeszcze nie przyjmuje.

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

Limity pamięci kontenerów (`mem_limit`) są dobrane pod maszynę 31 GiB / 8 wątków: semantyka 4 GB,
control plane 2 GB, reszta 128–1024 MB. To miękkie bezpieczniki chroniące host przed jednym rozbieganym
procesem; na mniejszej maszynie obniż je w `docker-compose.yaml`. Logi kontenerów mają rotację
(`max-size: 10m`, `max-file: 3`), żeby `json-file` nie rósł bez limitu na długo działającym stosie.

`make help` wypisuje wszystkie polecenia z podziałem na sekcje. Polecenia uruchamiane pojedynczo:

```bash
sudo make bench            # k6: pełna ścieżka kontroli przy obciążeniu, które warstwa AI wyrabia (VUS=3)
sudo make bench-stress     # k6: przeciążenie (VUS=50) — pokazuje, że brama blokuje, gdy AI nie wyrabia
sudo make bench-semantic   # przepustowość samych kontroli AI (Python, bez k6) i efekt skalowania
sudo make bench-flood      # k6: duży ruch z próbami ataku
sudo make bench-budget     # k6: równoległe żądania jednego agenta
sudo make controlplane-test  # testy modułu Java w kontenerze (nie wymaga Javy na hoście)
sudo make demo-full        # scenariusze demonstracyjne agenta
make reload-policy         # natychmiastowe przeładowanie polityki w gatewayu
make new-signature         # demo: dodanie sygnatury ataku do feedu w trakcie działania
make new-signature PATTERN='/etc/passwd' NAME='Path indicator' TARGET=prompt   # tekst literalny
sudo make db-tidy          # reset danych demo: audyt, katalog sygnatur, zdublowane rewizje polityki
sudo make db-dump          # kopia bazy audytu do backups/ (pg_dump); odtworzenie: make db-restore FILE=...
make lint                  # skladnia skryptow bash + go vet (shellcheck, jesli zainstalowany)
make urls                  # adresy usług i dane logowania
```

### Adresy i porty

| Usługa | Technologia | Port | Adres |
| :--- | :--- | :--- | :--- |
| Gateway | Go | 8080 | `http://localhost:8080/v1/chat/completions` (wymaga JWT: `make token`) |
| Dashboard | React + Nginx | 3000 | `http://localhost:3000` (logowanie tokenem `local-dev-admin`) |
| Control Plane | Java / Spring Boot | 8082 | `http://localhost:8082/api/v1`, eksport `?format=cef` |
| Semantic Service | Python | 8001 / 50051 | `http://localhost:8001` (HTTP) i `:50051` (gRPC); działa w replikach za load balancerem `semantic-lb` — patrz „Skalowanie" niżej |
| Prometheus | Prometheus 2.54 | 9091 | `http://localhost:9091/targets`, `/alerts` |
| Grafana | Grafana 11 | 3001 | `http://localhost:3001` (admin / admin, logowanie wyłączone — anonimowy admin, przeznaczone tylko do pracy lokalnej) |
| Feed sygnatur | Nginx | 8085 | `http://localhost:8085/signatures.json` |
| Mock LLM | Python (API OpenAI i Ollama) | 11434 | `http://localhost:11434` |
| PostgreSQL / Redis | — | 5432 / 6379 | dane audytu i liczniki zużycia |
| Gateway — metryki | — | 9090 | port zarezerwowany dla `GET /metrics`; brama jeszcze go nie wystawia, pilnuje tego alert `GatewayMetricsMissing` |

## Architektura

```
                    Aplikacja / agent AI / klient MCP
                                  |
                                  |  API zgodne z OpenAI (i MCP)
                                  v
        +-------------------------------------------------+
        |  GATEWAY (Go, data plane)                       |
        |  - uwierzytelnianie i autoryzacja agentów [dziala] |
        |  - kontrole deterministyczne            [dziala] |
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
aktualną politykę, egzekwuje allowlistę modeli oraz kontrole deterministyczne (sekrety, redakcja danych
osobowych) i — w razie potrzeby — pyta usługę semantyczną przez gRPC (prompt injection, content safety).
Następnie przekazuje żądanie do skonfigurowanego modelu (domyślnie `mock-llm`, opcjonalnie prawdziwa Ollama).
Elementy oznaczone `[w toku]` (sygnatury ataków, budżety, pętle, narzędzia MCP) nie są jeszcze włączone
w ścieżce żądania; decyzje trafiają do control plane dopiero, gdy brama zacznie wysyłać zdarzenia audytowe.

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
| [`mock-llm/`](mock-llm) | DevOps | Mock modelu (format OpenAI i Ollama), domyślny upstream gatewaya |
| [`proto/`](proto) | Python + Go | Wspólny kontrakt gRPC `semantic.v1` |
| [`deck/`](deck/README.md) | DevOps | Prezentacja zgłoszeniowa (10 slajdów: źródło Markdown + build do PDF) |
| [`START.md`](START.md) | DevOps | Wejście dla osób oceniających: jedna komenda, siedem poleceń, lista ograniczeń |
| [`dowody/`](dowody/README.md) | DevOps | Zrzut wyników z działającego systemu (raporty, testy, prezentacja PDF) |

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
Prototypowy `config/policy.yaml` został usunięty z repozytorium: nie był czytany przez żaden komponent,
a jego format różnił się od poniższego. Kształt dokumentu, który widzi gateway:

<!-- DEVOPS-REVIEW (2026-10-03): typ "phone" w pii_regex dopisany przez DevOps, nie przez Java/Go.
     Zmiana w trzech profilach w controlplane/src/main/resources/profiles/ i w tym przykładzie.
     Kod Go juz obslugiwal telefon (gateway/scan/rules.go) - brakowalo go tylko w danych polityki.
     Zmiana czeka na review wlasciciela control plane. -->

```json
{
  "version": 4,
  "defaults": {"mode": "enforce", "semantic_timeout_ms": 8000, "on_semantic_timeout": "fail_closed"},
  "models": {"allowed": ["llama3.1:8b", "llama3.2:1b", "mock-llm", "qwen2.5:7b"]},
  "controls": {
    "pii_regex": {"enabled": true, "action": "redact", "types": ["email", "pesel", "iban", "card", "phone"]},
    "secrets": {"enabled": true, "action": "block"},
    "prompt_injection": {"enabled": true, "action": "block", "threshold": 0.85},
    "content_safety": {"enabled": true, "action": "block", "categories": ["S1", "S2", "S9"]},
    "attack_signatures": {"enabled": true, "action": "block", "refresh_s": 60},
    "agent_loops": {"enabled": true, "action": "block", "max_steps": 25, "max_identical_tool_calls": 3},
    "mcp_tools": {"enabled": true, "action": "block", "allowed": {"demo-agent": ["search", "calculator"]}}
  },
  "budgets": [
    {"subject": "team:finance", "monthly_usd": 50, "daily_tokens": 200000, "on_exceed": "block"},
    {"subject": "model:local/*", "gpu_seconds_per_hour": 600, "on_exceed": "block"},
    {"subject": "agent:agent-budget-exhausted", "daily_tokens": 0, "on_exceed": "block"}
  ]
}
```

Aktywna rewizja to `balanced-demo` (`v4`): zawiera modele używane w testach, benchmarkach i demo
(`mock-llm`, `llama3.2:1b`) oraz deterministyczny wpis budżetowy opisany niżej. Publikuje ją
`scripts/publish-policy.sh`, wywoływany przez `make seed` — skrypt jest powtarzalny, więc nie tworzy
kolejnej rewizji, gdy polityka już spełnia wymagania. Nową rewizję tworzy
`POST /api/v1/policy-revisions` (dokument jako string), a aktywuje `PUT /api/v1/active-policy`
z numerem wersji.

Parser w gatewayu odrzuca dokument z nieznanymi polami, więc każda zmiana kształtu polityki wymaga
uzgodnienia obu stron.

### 5. Kody błędów i budżety (zamrożone)

Te napisy są kryterium akceptacji w `tests/test_guardrails.py`. Zmiana nazwy po stronie gatewaya
oznacza czerwony test mimo działającej funkcji, dlatego traktujemy je jako zamrożony kontrakt.

| Kontrola | Kod | Napis w ciele odpowiedzi |
|---|---|---|
| Wyciek sekretów | 403 | `SECRET_LEAKAGE_DETECTED` |
| Prompt injection | 403 | `PROMPT_INJECTION_DETECTED` |
| Sygnatura znanego ataku | 403 | `HISTORICAL_EXPLOIT_SIGNATURE_MATCHED` |
| Przekroczony budżet | 429 | `BUDGET_EXCEEDED` |
| Ogranicznik pętli | 403 | `RUNAWAY_LOOP_DETECTED` |

Ciało odpowiedzi: `{"error": "<NAZWA>", "detail": "<krótki opis>"}` — taki sam kształt jak przy
błędach uwierzytelniania. Odpowiedź po redakcji pozostaje `200`, a informację o tym, co zostało
zredagowane, niesie nagłówek `X-NoorPointer-Redactions` (np. `pii_ner`); nie zmienia to tego,
czego oczekują testy.

Budżety pozostają wymaganiem do implementacji w Go. Podmiot agenta musi pochodzić z `sub`
zweryfikowanego JWT, zespołu z jego `team`; `agent_id` w ciele nie jest tożsamością.
Należy egzekwować wszystkie pasujące limity agenta, zespołu i modelu, z atomową rezerwacją
przed wywołaniem i rozliczeniem rzeczywistego zużycia po odpowiedzi. Sama atomowość końcowego
`INCRBY` nie zapobiega przekroczeniu limitu przez równoległe żądania.
`test_gateway_budgets.py` sprawdza wyczerpanie, wyścigi i podmianę tożsamości; test E2E z limitem 0
ustawia limit dla rzeczywistego JWT. Kontrakt telemetrii kosztu/GPU i pozostałe uzgodnienia:
[tests/GO_HANDOFF.md](tests/GO_HANDOFF.md).

### 6. Opcjonalny prawdziwy model (Ollama)

```bash
sudo make up-real      # pelny stos + prawdziwe modele jednym poleceniem (pyta przed pobraniem ~2,9 GB)
sudo make ollama-up    # tylko przelaczenie na Ollame, gdy stos juz dziala
sudo make ollama-down   # powrót na mock-llm (potrzebny do testów oczekujących odpowiedzi echo)
```

`make up-real` uruchamia `make up`, a następnie przełącza gateway i `content_safety` na prawdziwe modele
przez `make ollama-up`. Zanim cokolwiek pobierze, sprawdza w wolumenie `ollama-data`, czy `llama3.2:1b`
i `llama-guard3:1b` są obecne. Gdy ich nie ma, zatrzymuje się z komunikatem — pobranie ok. 2,9 GB przy
0,7 MB/s trwa ponad godzinę, więc wymaga świadomej zgody: `sudo make up-real ALLOW_DOWNLOAD=1`.
Modele zostają w wolumenie, więc pobierają się tylko raz.

Domyślnie (`make up`) mockowane są tylko te modele, które idą przez Ollamę: odpowiedzi czatu
(`mock-llm` odsyła echo) oraz `content_safety` (mock reaguje na słowa kluczowe). Prompt injection
(DeBERTa) i dane osobowe (spaCy en+pl) to prawdziwe modele wbudowane w obraz usługi semantycznej,
więc działają od razu po `make up`. Testy e2e i benchmarki zakładają odpowiedzi echo z mocka — przed
nimi wróć na `make ollama-down`. Uwaga wydajnościowa: prawdziwy Llama Guard na CPU odpowiada ok. 0,9 s,
a kontrola ma budżet `defaults.semantic_timeout_ms` (8000 ms) — z zapasem na zimny start (pierwsze zapytanie do Llama Guarda trwa ok. 4 s).

Konfiguracja `docker-compose.ollama.yaml` nie publikuje portu Ollamy na hoście, więc nie koliduje
z `mock-llm`. Pierwsza odpowiedź trwa dłużej (ładowanie modelu na CPU), a nazwa modelu musi być wpisana
na liście `models.allowed` w polityce.

## Scenariusz prezentacji

Kolejność, w której pokazujemy działanie systemu (wszystkie polecenia działają na obecnym stanie
repozytorium):

1. `make doctor` — narzędzia, klucze, konfiguracja, działające uwierzytelnianie.
2. `make smoke` — 16 sprawdzeń spójności stosu.
3. `make verify` — smoke + kontrola braku zależności sieciowych w runtime + scenariusze agenta.
4. `make demo` — pięć scenariuszy agenta przez gateway.
5. `make reload-policy` — żywa zmiana konfiguracji, odpowiedź `{"status":"reloaded","version":N}`.
6. `make new-signature` — dodanie sygnatury ataku w trakcie działania: wpis pojawia się w feedzie
   i w katalogu w panelu (po pokazie: `git checkout -- signatures-feed/signatures.json && make seed`).
7. `make traffic` — realny ruch na panele: zadania przez gateway oraz skany semantyczne, które
   oznaczają próbę prompt injection i dane osobowe. Bez tego kroku panele usługi semantycznej są puste,
   bo gateway nie wywołuje jej jeszcze w ścieżce żądania.
8. Panel `http://localhost:3000` (login `local-dev-admin`) — incydenty, rewizje polityki i katalog sygnatur.
   Control plane udostępnia opublikowaną politykę oraz sygnatury gatewayowi Go.
9. Grafana `http://localhost:3001` (admin/admin) — dostępność usług, kontrole semantyczne, ruch
   w control plane i alerty. Panel gatewaya jest tam opisany jako pusty do czasu `GET /metrics`.
10. `sudo make test` — pakiet testów, `reports/test_report.html` i `reports/INDEX.md` z listą
    otwartych pozycji wraz z właścicielami; `sudo make controlplane-test` uruchamia dodatkowo testy
    modułu Java w kontenerze.

Stan testów: `tests/test_guardrails.py` ma **25 przypadków** w parach dozwolone/blokowane. Część z nich
dotyczy kontroli, których brama jeszcze nie egzekwuje (sygnatury ataków, budżety, ogranicznik pętli) —
aktualny wynik i lista otwartych pozycji są w `reports/INDEX.md`. Mówimy o tym wprost i nie obiecujemy
kontroli, których jeszcze nie ma.

## Skalowanie usługi semantycznej

Najcięższa część systemu (modele AI) działa w replikach za load balancerem, a nie w jednym kontenerze.

Jak to jest zrobione i dlaczego właśnie tak:

- Samo `--scale` **nie wystarcza**: Docker DNS zwraca adresy wszystkich replik, ale klient HTTP
  rozwiązuje nazwę raz i trzyma połączenie z jedną repliką. Wtedy zwiększenie liczby replik nic nie daje.
- Dlatego przed replikami stoi `semantic-lb` (nginx): pyta Dockera o adresy **przy każdym żądaniu**
  (`resolver 127.0.0.11`), więc ruch rozkłada się na wszystkie repliki, a nowe repliki wchodzą do gry
  w ciągu 5 sekund.
- Load balancer **dziedziczy nazwę `semantic-service`**, więc brama, testy e2e
  i skrypty nadal rozmawiają z `semantic-service:8001` — nie trzeba było zmieniać niczyjego kodu.
- gRPC (`:50051`) przechodzi przez tę samą barierę jako przekazanie TCP: każde nowe połączenie trafia
  do kolejnej repliki (jedna sesja klienta pracuje z jedną repliką — tak działa multipleksowanie gRPC).
- Prometheus nie ma już wpisanego adresu na sztywno: używa `dns_sd_configs`, więc zbiera metryki
  z **każdej** repliki osobno. Dzięki temu wykresy i alerty nie „skaczą" między kontenerami.
- Alerty rozróżniają dwa przypadki: `SemanticReplicaLost` (część replik padła — ruch idzie dalej)
  i `SemanticDown` (żadna nie odpowiada).

```bash
make bench-semantic              # przepustowość przy 1 replice: punkt odniesienia
sudo make scale REPLIKI=3        # 3 repliki usługi semantycznej
sudo make scale-check            # dowód: licznik kontroli przyrasta w każdej replice
make bench-semantic              # ten sam pomiar po skalowaniu
sudo make scale REPLIKI=1        # powrót do jednej repliki
```

`make scale-check` czyta licznik wykonanych kontroli z każdego kontenera osobno i pokazuje przyrosty.
Trzy linie po ~33% znaczą, że load balancing działa; jedna linia z 100% znaczyłaby, że cały ruch idzie
do jednego kontenera i skalowanie jest pozorne.

### Co pokazał pomiar i gdzie jest granica

Zmierzone na tej maszynie (8 wątków CPU, Intel i7-1165G7), 100 żądań po 10 naraz, 2 kontrole na żądanie,
po rozgrzewce. Każdy wiersz to jeden przebieg `make bench-semantic`:

| Konfiguracja (repliki × wątki na analizę × równoległe analizy) | Wątków razem | Przepustowość | Mediana / p95 |
| :--- | :--- | :--- | :--- |
| 1 × 4 × 2 (domyślna) | 8 | **13,4 żądań/s** (26,8 kontroli/s) | 736 ms / 785 ms |
| 1 × 2 × 1 | 2 | 3,7 żądań/s (7,4 kontroli/s) | 2842 ms / 3078 ms |
| 3 × 2 × 1 (ta sama konfiguracja na replikę) | 6 | **4,7 żądań/s** (9,4 kontroli/s) | 1628 ms / 4060 ms |
| 3 × 4 × 2 (domyślna na trzech replikach) | 24 | 5,4 żądań/s (10,9 kontroli/s) | 1645 ms / 3123 ms |

Co z tego wynika — trzy wnioski, wszystkie oparte na pomiarze:

1. **Skalowanie poziome działa.** Przy identycznej konfiguracji każdej repliki trzy repliki dają
   +27% przepustowości (3,7 → 4,7 żądań/s) i wyraźnie lepszą medianę (2842 → 1628 ms) niż jedna.
   Rozkład ruchu potwierdza osobno `make scale-check`.
2. **Największą dźwignią na tej maszynie jest liczba wątków na jedno wnioskowanie, nie liczba replik.**
   Zejście z 4 wątków na 2 w jednej replice obniżyło przepustowość z 13,4 do 3,7 żądań/s — analiza
   modelu jest po prostu ciężka i równoległa w środku.
3. **Sufit wyznacza procesor.** Trzy repliki z domyślnymi ustawieniami proszą o 24 wątki na ośmiu,
   więc dostają 5,4 żądań/s, czyli 2,5× mniej niż jedna replika używająca ośmiu wątków. Dokładanie
   replik z tymi samymi ustawieniami nie mnoży mocy, dopóki nie dołożymy rdzeni (osobne maszyny, węzły).

Zasada, którą stosujemy przy strojeniu:

```
repliki × PI_WORKERS × TORCH_THREADS  ≤  liczba wątków CPU
```

Poprawny pomiar efektu skalowania polega na zmianie **tylko liczby replik**, przy niezmienionej
konfiguracji każdej z nich — inaczej porównujemy ze sobą dwa różne budżety wątków, a nie skalowanie:

```bash
# ta sama konfiguracja na replikę (1 × 1 × 2 watki), zmieniamy tylko liczbe replik
sudo FORCE=1 TORCH_THREADS=2 PI_WORKERS=1 make scale REPLIKI=1 && make bench-semantic
sudo FORCE=1 TORCH_THREADS=2 PI_WORKERS=1 make scale REPLIKI=3 && make bench-semantic
```

Czego oczekiwać i co to znaczy: na jednej maszynie przepustowość jest ograniczona procesorem, więc
repliki dają przede wszystkim **dostępność** (jedna pada — ruch idzie dalej) i możliwość
**wykorzystania kolejnych maszyn**. Zysk liniowy pojawia się, gdy repliki stoją na osobnych
maszynach lub węzłach; na jednym laptopie dzielą ten sam procesor i tę samą pamięć.

Uczciwa uwaga o koszcie: każda replika to osobna kopia modeli w pamięci, więc zużycie RAM rośnie
liniowo z liczbą replik. To normalny kompromis skalowania poziomego, ale trzeba go mieć świadomie.

## Jak odnosimy się do kryteriów oceny

Wagi i nazwy kryteriów są przepisane z regulaminu konkursu.

| Kryterium | Nasz materiał |
| :--- | :--- |
| Kontrole i odporność (30%) | Kontrole deterministyczne i semantyczne: 4 detektory AI, skaner plików modeli, 12 sygnatur ataków, zasady jako dane z przeładowaniem bez restartu. Kontrole działają w usłudze semantycznej i są testowane; brama egzekwuje już allowlistę modeli, sekrety, redakcję PII i kontrole semantyczne, a otwarte pozostają sygnatury, budżety i ogranicznik pętli — brakujące elementy są wypisane w `reports/INDEX.md`. |
| Architektura i wydajność (20%) | Rozdzielone płaszczyzny: brama (Go), zasady i audyt (Java), kontrole AI (Python w replikach), panel i telemetria. Pomiary: `make bench` (k6, p95 2,28 ms przy 50 klientach) oraz `make bench-semantic` (przepustowość kontroli AI i efekt skalowania). |
| Raportowanie bezpieczeństwa (20%) | Panel z incydentami, wersjami zasad, katalogiem sygnatur i budżetami; eksport CEF/JSON/CSV do SIEM z filtrami; 9 reguł alertów i tablice Grafany. Dziennik jest zasilany danymi demonstracyjnymi (oznaczonymi jako `synthetic`), bo brama nie wysyła jeszcze własnych zdarzeń. |
| Kompletność pakietu testów (20%) | **181** testów usługi semantycznej (`make test-semantic`), **25 przypadków e2e**, 3 scenariusze obciążeniowe, 16 sprawdzeń stosu, 14 kontroli przed startem, 9 sprawdzeń trybu offline, a do tego testy modułów Go, Java i panelu. Wszystko uruchamiane z `make`, a ścieżka dla osoby oceniającej jest jedną komendą: `sudo make jury`. |
| Wdrożenie i skalowanie (10%) | Start całego stosu jedną komendą, brak pobierania czegokolwiek w czasie działania (`make offline-check`), podmiana modelu bez zmian w kodzie oraz skalowanie poziome usługi semantycznej z dowodem rozkładu ruchu (`make scale`, `make scale-check`). |

## Zasady pracy w zespole

1. Przed wypchnięciem zmian na `main` uruchom `sudo make test` i `make smoke` — oczekujemy, że stan na `main` jest znany, a nie że wszystko jest zielone.
2. W czasie działania żaden kontener nie może pobierać modeli ani pakietów — to sprawdza `make offline-check`.
3. Serwisy logują na standardowe wyjście, żeby dało się je zebrać przez `make logs`.
4. Dopóki moduł nie jest gotowy, pracujemy przeciwko mockom (`mock-llm`), żeby nie blokować innych.

Prompt check in the control panel sends text to Go `/admin/check`. Go applies the active policy; the result and control details are recorded in Events. No upstream model completion is requested.
