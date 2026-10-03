# Control Plane (Policy & Audit Engine)

## Właściciel
**Java Developer** / **Go Developer**

---

## Zakres
Mózg zarządzający i rejestrujący całego systemu (Management Plane). Odpowiada za centralne zarządzanie katalogiem polityk bezpieczeństwa, wersjonowanie reguł, importowanie sygnatur historycznych ataków z zewnętrznych feedów, trwały zapis zdarzeń audytowych w bazie danych oraz udostępnianie interfejsu raportowania i eksportu danych dla zespołów bezpieczeństwa i dashboardu.

---

## Zakres odpowiedzialności

1. **Centralny katalog kontroli (Policy Catalog & Management)**:
   - Zarządzanie i walidacja schematu polityki bezpieczeństwa (`policy.yaml` / JSON Schema).
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
- **Kluczowe endpointy**:
  - `GET /api/v1/policies` – aktualna polityka i reguły
  - `POST /api/v1/policies/reload` – wymuszenie przeładowania
  - `GET /api/v1/signatures/sync` – synchronizacja z feedem ataków
  - `GET /api/v1/audit/logs` – lista zdarzeń (filtrowanie po dacie, agencie, akcji)
  - `GET /api/v1/audit/export?format=cef|json|csv` – eksport audytowy
  - `GET /api/v1/stats/posture` – zagregowane metryki do dashboardu
- **Zależności:**
  - Baza danych: PostgreSQL (`postgres:5432`)
  - Źródło feedu: `signatures-feed:8085`

---

## Kryteria ukończenia
- [ ] Każde zablokowane żądanie z Gatewaya trafia do bazy Postgres w czasie poniżej 1 sekundy.
- [ ] Wywołanie endpointu eksportu generuje poprawny plik w formacie CEF akceptowalny przez narzędzia SIEM.
- [ ] Zmiana progu czułości lub dodanie sygnatury w pliku feedu jest poprawnie przetwarzana i rozgłaszana do Gatewaya.
- [ ] API zwraca czytelne statystyki pogrupowane według kategorii OWASP.
