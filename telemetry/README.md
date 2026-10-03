# 📈 Telemetry (Observability & Performance Monitoring)

## 👤 Właściciel (Owner)
**DevOps**

---

## 🎯 Zakres (Scope)
Infrastruktura monitorowania, obserwowalności i metryk wydajnościowych całego systemu.
Realizuje kluczowy wymóg z sekcji oceny: *"You should be able to produce performance telemetry as it may be used for evaluation"*.
Zapewnia gotowe, samouruchamiające się środowisko Grafany i Prometheusa z predefiniowanymi pulpitami nawigacyjnymi (dashboard provisioning bez ręcznej konfiguracji), obrazujące stan pracy Gatewaya, zużycie zasobów i opóźnienia w czasie rzeczywistym.

---

## 🛠️ Czym się zajmuje (Kluczowe Odpowiedzialności)

1. **Konfiguracja Prometheus (`prometheus.yml`)**:
   - Skrobanie metryk co 1–3 sekundy ze wszystkich komponentów systemu:
     - `gateway:9090/metrics` (narzut latencji, liczniki zapytań, kody odpowiedzi, akcje guardraili).
     - `semantic-service:8001/metrics` (czas wnioskowania modeli DeBERTa, kolejkowanie).
     - `cadvisor` / `node-exporter` (opcjonalnie: zużycie CPU/RAM kontenerów).
2. **Predefiniowane Dashboardy Grafany (Dashboard-as-Code)**:
   - Gotowe pliki JSON umieszczone w `telemetry/grafana/dashboards/`:
     - **Dashboard 1: Gateway Performance & SLA**:
       - Wykresy latencji: percentyle p50, p90, p95, p99 (ścieżka deterministyczna vs semantyczna).
       - Wolumen ruchu i wskaźnik błędów (RPS, statusy 2xx, 4xx, 5xx).
     - **Dashboard 2: AI Guardrails & Threat Defense**:
       - Liczba zablokowanych promptów wg typów zagrożeń (Prompt Injection, PII, Sygnatury CVE).
       - Liczba wyzwolonych bezpieczników pętli agentów (Loop Breaker triggers).
     - **Dashboard 3: Budget Burndown & Cost Tracker**:
       - Zużycie tokenów i kosztów w czasie rzeczywistym z podziałem na tenantów i modele.
3. **Automatyczny Provisioning**:
   - Zero-click setup: po uruchomieniu `docker compose up` Grafana pod adresem `http://localhost:3001` jest od razu zalogowana (lub domyślne `admin/admin`) i ma załadowane wszystkie źródła danych oraz dashboardy.
4. **Log Tracing & Correlation (OpenTelemetry / Loki - opcjonalnie)**:
   - Korelacja identyfikatora żądania (`trace_id` / `request_id`) pomiędzy logami Gatewaya a zdarzeniami audytowymi.

---

## 🔌 Interfejsy i Porty
- **Prometheus:** `9091` (zewnętrzny) / `9090` (wewnętrzny)
- **Grafana UI:** `3001` (login/hasło: `admin/admin`)
- **Scrape Targets:** `gateway:9090`, `semantic-service:8001`

---

## 🏆 Definition of Done (Kryteria Sukcesu)
- [ ] Po starcie środowiska Grafana od razu wyświetla gotowe wykresy bez konieczności dodawania Data Source.
- [ ] Ruch generowany przez testy lub demo powoduje natychmiastowe ożywienie wykresów latencji i blokad.
- [ ] Na dashboardzie wyraźnie widać różnicę w narzucie czasu między ścieżką deterministyczną a semantyczną.
