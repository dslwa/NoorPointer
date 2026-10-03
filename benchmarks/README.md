# ⚡ Benchmarks (Performance & Latency Testing)

## 👤 Właściciel (Owner)
**DevOps**

---

## 🎯 Zakres (Scope)
Testy obciążeniowe i profilowanie wydajnościowe systemu.
Odpowiada za spełnienie kryterium oceniania: **Architecture and Performance Efficiency (20%)** oraz wymogu: *"You should be able to produce performance telemetry as it may be used for evaluation"*.
Dostarcza twardych, powtarzalnych danych liczbowych (opóźnienia p50, p95, p99, przepustowość RPS, narzut CPU/pamięci) udowadniających, że wprowadzona warstwa ochronna nie spowalnia pracy programistów ani agentów.

---

## 🛠️ Czym się zajmuje (Kluczowe Odpowiedzialności)

1. **Pomiary Narzutu Gatewaya (Overhead Benchmarks)**:
   - Skrypty testowe `k6` mierzące dokładnie czas dodawany przez Gateway w stosunku do bezpośredniego wywołania modelu:
     - **Deterministic Path (Go regex + auth + budżet Redis):** cel < 5 ms.
     - **Semantic Path (DeBERTa + Presidio + timeout check):** cel < 150 ms.
2. **Scenariusze Obciążeniowe (k6 scripts)**:
   - `benchmark_baseline.js`: ruch normalny o wysokim natężeniu (np. 50-100 VU, weryfikacja stabilności proxy).
   - `benchmark_malicious_flood.js`: zalew zapytań z payloadem ataków (weryfikacja czy mechanizm `fast-block` skutecznie chroni przed wyczerpaniem zasobów LLM).
   - `benchmark_budget_concurrency.js`: równoległe zapytania sprawdzające atomowość liczników w Redis przy wyczerpywaniu limitów tokenów.
3. **Automatyczne Raportowanie Wyników**:
   - Generowanie podsumowania tekstowego w konsoli oraz wykresów HTML (`summary.html`).
   - Ekstrakcja kluczowych wskaźników do slajdów prezentacyjnych:
     - *Narzut p95:* np. **4.2 ms** dla ścieżki deterministycznej.
     - *Throughput:* np. **2500 req/s** na pojedynczej instancji Gatewaya w Go.
4. **Zapewnienie komendy 1-Click**:
   - Uruchamianie pełnego pakietu benchmarków poleceniem `make bench`.

---

## 🔌 Narzędzia i Technologie
- **Narzędzie główne:** [k6](https://k6.io/) (konteneryzowany runner testów obciążeniowych)
- **Cel testów:** `http://gateway:8080` vs `http://ollama:11434`
- **Integracja:** Metryki z testu spływają również do Prometheus/Grafana.

---

## 🏆 Definition of Done (Kryteria Sukcesu)
- [ ] Komenda `make bench` wykonuje test obciążeniowy bez błędów w kontenerze.
- [ ] Zestawienie pokazuje p95 opóźnienia deterministycznego poniżej 10 ms.
- [ ] Wyniki testu są wyeksportowane do czytelnego pliku raportu dla jury.
