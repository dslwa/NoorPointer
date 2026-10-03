# Control Plane (Policy & Audit Engine)

## Właściciel
**Java Developer** / **Go Developer**

---

## Zakres
Mózg zarządzający i rejestrujący całego systemu (Management Plane). Odpowiada za centralne zarządzanie katalogiem polityk bezpieczeństwa, wersjonowanie reguł, importowanie sygnatur historycznych ataków z zewnętrznych feedów, trwały zapis zdarzeń audytowych w bazie danych oraz udostępnianie interfejsu raportowania i eksportu danych dla zespołów bezpieczeństwa i dashboardu.

---

## Stan obecny

Działa: publikowanie i historia rewizji polityki, walidacja szkiców polityki, katalog sygnatur
(7 reguł startowych z migracji `V2__Seed_default_signatures` + wpisy dodawane pojedynczo przez API
i panel), przyjmowanie zdarzeń audytowych (`POST /api/v1/audit-events`), lista i szczegóły zdarzeń,
eksport CEF/JSON/CSV z filtrami (szczegóły w `SIEM.md`), API panelu, dane demonstracyjne
(`POST /api/v1/demo-batches`) oraz metryki dla Prometheusa.

Jeszcze nie działa: gateway nie egzekwuje kontroli, nie wysyła zdarzeń audytowych i nie pobiera
sygnatur, więc wpisy w panelu pochodzą z `make seed`, a katalog sygnatur jest uzupełniany przez
`scripts/import-signatures.sh`. Automatyczny import feedu regex wymaga adaptera
(patrz `signatures-feed/README.md`).

---

## Zakres odpowiedzialności

1. **Centralny katalog kontroli (Policy Catalog & Management)**:
   - Zarządzanie i walidacja schematu polityki bezpieczeństwa (JSON Schema w `src/main/resources/contracts/`; prototypowy `config/policy.yaml` został usunięty z repozytorium).
   - Obsługa profili rygorystyczności (np. `strict`, `balanced`, `permissive`).
   - Publikacja i propagowanie zmian reguł do Gatewaya.
2. **Import feedu sygnatur historycznych ataków**:
   - Cykliczny lub sterowany webhookiem pobór feedu sygnatur z zewnętrznego źródła (`signatures-feed`).
   - Parsowanie reguł (identyfikatory CVE, wektory ataków, np. ShadowRay, Probllama, złośliwe wywołania MCP).
   - Przekształcanie sygnatur w aktywny zestaw reguł dla Gatewaya.
3. **Audit Log i bezpieczna persystencja zdarzeń**:
   - Odbiór strumienia zdarzeń audytowych z Gatewaya (każde zablokowane i dozwolone żądanie, wykryte naruszenie, zużycie budżetu).
   - Trwały zapis w bazie danych (PostgreSQL).
   - Zapis metadanych: `timestamp`, `agent_id`, `action (block/redact/allow)`, `matched_rule`, `prompt_snippet`, `tokens_used`, `cost_usd`.
4. **Eksport dla systemów SIEM i audytorów (Wymóg 5)**:
   - Endpointy umożliwiające eksport logów w ustandaryzowanych formatach:
     - **JSON** (strukturalny pełny eksport)
     - **CSV** (dla analityków biznesowych)
     - **CEF (Common Event Format)** (standard dla systemów SIEM takich jak Splunk, Elastic, Sentinel).
5. **API dla dashboardu (Backend for Frontend)**:
   - Udostępnianie zagregowanych statystyk:
     - Stan postury bezpieczeństwa (*Security Posture Score*).
     - Zagrożenia według taksonomii OWASP Top 10 for LLMs / Agentic AI.
     - Zużycie budżetów finansowych i tokenowych dla zespołu lub agenta.
     - Ostatnie incydenty z pełnym kontekstem (forensics).

---

## Interfejsy i komunikacja
- **Port wejściowy:** `8082` (REST API)
- **Kluczowe endpointy** (stan obecny, sprawdzone na działającym serwisie):
  - `GET /api/v1/active-policy` – aktywna rewizja; `PUT /api/v1/active-policy` z `{"version": N}` publikuje istniejącą rewizję
  - `GET /api/v1/active-policy/document` – sam dokument polityki (nagłówki `ETag` i `If-None-Match`)
  - `GET /api/v1/policy-revisions`, `GET /api/v1/policy-revisions/{version}` – historia rewizji
  - `POST /api/v1/policy-revisions` – utworzenie rewizji (szkic: `name`, `description`, `document` jako string z JSON-em)
  - `GET /api/v1/signature-feed`, `PUT /api/v1/signature-feed` – katalog sygnatur (podmieniana jest całość)
  - `POST /api/v1/signatures` – dodanie pojedynczej sygnatury (`application/json` albo wklejony dokument jako `text/plain`/YAML); `409`, gdy ID już istnieje
  - `GET /api/v1/signatures/{id}` – pojedyncza sygnatura
  - `POST /api/v1/policy-validations` – walidacja szkicu dokumentu polityki
  - `GET /api/v1/policy-profiles/{name}` – wbudowany profil (`permissive`, `balanced`, `strict`)
  - `POST /api/v1/audit-events` – przyjęcie zdarzenia audytowego z gatewaya (rola `ADMIN` lub `GATEWAY`)
  - `GET /api/v1/audit-events`, `GET /api/v1/audit-events/{id}` – lista i pojedyncze zdarzenie do panelu
  - `GET /api/v1/audit-events/export?format=cef|json|csv` (alias: `/api/v1/audit/export`) – eksport audytowy; limity i filtry opisuje `SIEM.md`
  - `GET /api/v1/dashboard` – zagregowane metryki dla panelu
  - `POST /api/v1/demo-batches` – dane demonstracyjne do panelu (używa ich `make seed`)
  - `GET /api/gateway/policy`, `GET /api/gateway/signatures`, `POST /api/gateway/events` – trasy dla gatewaya
  - `GET /actuator/health`, `GET /actuator/prometheus` – stan usługi i metryki dla Prometheusa
- **Zależności:**
  - Baza danych: PostgreSQL (`postgres:5432`)
  - Źródło feedu: `signatures-feed:8085`

---

## Kryteria ukończenia
- [ ] Każde zablokowane żądanie z Gatewaya trafia do bazy Postgres w czasie poniżej 1 sekundy.
- [ ] Wywołanie endpointu eksportu generuje poprawny plik w formacie CEF akceptowalny przez narzędzia SIEM.
- [ ] Zmiana progu czułości lub dodanie sygnatury w pliku feedu jest poprawnie przetwarzana i rozgłaszana do Gatewaya.
- [ ] API zwraca czytelne statystyki pogrupowane według kategorii OWASP.
