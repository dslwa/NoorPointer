# 🚪 Gateway (Data Plane)

## 👤 Właściciel (Owner)
**Go Developer**

---

## 🎯 Zakres (Scope)
Szybka ścieżka krytyczna (Data Plane). Komponent pośredniczący (Reverse Proxy) umieszczony pomiędzy klientami (aplikacjami, agentami AI) a modelami LLM (Ollama, OpenAI API) oraz serwerami narzędzi (MCP).
Odpowiada za deterministyczne, natychmiastowe kontrole bezpieczeństwa (low-latency, cel < 10 ms), egzekwowanie limitów budżetowych oraz orkiestrację wywołań semantycznych.

---

## 🛠️ Czym się zajmuje (Kluczowe Odpowiedzialności)

1. **OpenAI / Ollama API Reverse Proxy (`/v1/chat/completions`)**:
   - Przechwytywanie promptów użytkowników oraz odpowiedzi generowanych przez LLM.
   - Kompatybilność z protokołem OpenAI, aby agenci mogli podpiąć się przez zmianę samego `base_url`.
2. **MCP (Model Context Protocol) Proxy & Tool Governance**:
   - Kontrola wywołań narzędzi przez agentów: allowlista dozwolonych narzędzi per agent/rola.
   - Walidacja argumentów narzędzi oraz hashowanie opisów narzędzi (ochrona przed *Tool Poisoning* i *Rug Pull*).
3. **Kontrole Deterministyczne (Non-AI)**:
   - Szybkie skanowanie regex: PII (PESEL, IBAN, karty płatnicze z walidacją Luhna, adresy e-mail).
   - Detekcja wycieku sekretów: klucze API (AWS, GitHub, OpenAI), tokeny JWT, klucze prywatne.
   - Działanie w trybach: `block` (blokowanie z kodem 403), `redact` (maskowanie danych w locie), `monitor` (tylko audit log).
4. **Wykrywanie Pętli i Anomalii Agenta (Loop Breaker)**:
   - Śledzenie liczby kroków w sesji agenta (`max_steps`).
   - Wykrywanie zapętlenia w identycznych wywołaniach narzędzi (`max_identical_tool_calls`).
5. **Zarządzanie Budżetami i Rate Limitingiem (Redis)**:
   - Zliczanie tokenów (input/output) oraz przeliczanie kosztu (USD dla API komercyjnych, GPU-seconds dla modeli lokalnych).
   - Blokowanie żądań po przekroczeniu limitu per agent, zespół lub model.
6. **Hot-Reload Polityki Bezpieczeństwa**:
   - Dynamiczne przeładowywanie konfiguracji (`policy.yaml`) bez restartu kontenera (przez `fsnotify` lub endpoint `/admin/policy/reload`).
7. **Orkiestracja Kontroli Semantycznych**:
   - Odpytywanie `semantic-service` (gRPC/HTTP) z twardym timeoutem (np. 300 ms).
   - Obsługa strategii `fail_open` lub `fail_closed` w przypadku przekroczenia czasu.
8. **Telemetria**:
   - Wystawianie metryk Prometheus (`/metrics`) dla opóźnień (p50, p95, p99), liczby zablokowanych żądań i narzutu czasowego.

---

## 🔌 Interfejsy i Komunikacja
- **Port wejściowy:** `8080` (HTTP API proxy)
- **Port metryk:** `9090` (Prometheus `/metrics`)
- **Komunikacja wychodząca:**
  - `upstream LLM` (np. `http://ollama:11434` lub API komercyjne)
  - `semantic-service` (gRPC `semantic-service:50051` lub HTTP)
  - `redis` (pamięć podręczna budżetów i liczników)
  - `postgres` / audit stream (zapis zdarzeń audytowych)

---

## 🏆 Definition of Done (Kryteria Sukcesu)
- [ ] Zmiana `OPENAI_BASE_URL` w agencie na Gateway działa w 100% transparentnie.
- [ ] Wykrycie numeru karty kredytowej lub klucza API natychmiast maskuje lub blokuje request (< 5 ms).
- [ ] Przekroczenie budżetu tokenów w Redis zwraca błąd `429 Too Many Requests / Budget Exceeded`.
- [ ] Zmiana pliku `policy.yaml` jest uwzględniana w locie w trakcie testów jury.
