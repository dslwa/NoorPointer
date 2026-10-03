# Gateway (Data Plane)

## Właściciel
**Go Developer**

---

## Stan implementacji

Działa: reverse proxy `POST /v1/chat/completions` do upstreamu, walidacja JWT RS256 (`iss`, `aud`, `exp`)
na wszystkich trasach poza `GET /healthz`, pobieranie dokumentu polityki z control plane
(`GET /api/gateway/policy` z `Bearer $GATEWAY_TOKEN`, z `ETag` i odpytywaniem co 1 s) oraz
`POST /admin/policy/reload` (Bearer `$GATEWAY_TOKEN`).

Nie jest jeszcze zaimplementowane: kontrole z punktów 3–5 i 7 (PII, sekrety, prompt injection, sygnatury
ataków, budżety, ogranicznik pętli, wywołania `semantic-service`), `GET /metrics` na porcie 9090 oraz
wysyłanie zdarzeń audytu do control plane. Zmienne środowiskowe tych integracji są już zadeklarowane
w `docker-compose.yaml`, więc nie trzeba ich dodawać.

---

## Zakres
Szybka ścieżka krytyczna (Data Plane). Komponent pośredniczący (Reverse Proxy) umieszczony pomiędzy klientami (aplikacjami, agentami AI) a modelami LLM (Ollama, OpenAI API) oraz serwerami narzędzi (MCP).
Odpowiada za deterministyczne, natychmiastowe kontrole bezpieczeństwa (low-latency, cel < 10 ms), egzekwowanie limitów budżetowych oraz orkiestrację wywołań semantycznych.

---

## Zakres odpowiedzialności

1. **OpenAI / Ollama API Reverse Proxy (`/v1/chat/completions`)**:
   - Przechwytywanie promptów użytkowników oraz odpowiedzi generowanych przez LLM.
   - Kompatybilność z protokołem OpenAI, aby agenci mogli podpiąć się przez zmianę samego `base_url`.
2. **MCP (Model Context Protocol) Proxy & Tool Governance**:
   - Kontrola wywołań narzędzi przez agentów: lista dozwolonych narzędzi dla agenta lub roli.
   - Walidacja argumentów narzędzi oraz hashowanie opisów narzędzi (ochrona przed *Tool Poisoning* i *Rug Pull*).
3. **Kontrole deterministyczne (Non-AI)**:
   - Szybkie skanowanie regex: PII (PESEL, IBAN, karty płatnicze z walidacją Luhna, adresy e-mail).
   - Detekcja wycieku sekretów: klucze API (AWS, GitHub, OpenAI), tokeny JWT, klucze prywatne.
   - Działanie w trybach: `block` (blokowanie z kodem 403), `redact` (maskowanie danych w locie), `monitor` (tylko audit log).
4. **Wykrywanie pętli i anomalii agenta (Loop Breaker)**:
   - Śledzenie liczby kroków w sesji agenta (`max_steps`).
   - Wykrywanie zapętlenia w identycznych wywołaniach narzędzi (`max_identical_tool_calls`).
5. **Zarządzanie budżetami i rate limitingiem (Redis)**:
   - Zliczanie tokenów (input/output) oraz przeliczanie kosztu (USD dla API komercyjnych, GPU-seconds dla modeli lokalnych).
   - Blokowanie żądań po przekroczeniu limitu dla agenta, zespołu lub modelu.
6. **Hot-reload polityki bezpieczeństwa**:
   - Dynamiczne przeładowywanie dokumentu polityki z control plane, bez restartu kontenera: odpytywanie co `refresh_s` oraz ręcznie przez `POST /admin/policy/reload` (Bearer `$GATEWAY_TOKEN`).
7. **Orkiestracja kontroli semantycznych**:
   - Odpytywanie `semantic-service` (gRPC/HTTP) z twardym timeoutem (np. 300 ms).
   - Obsługa strategii `fail_open` lub `fail_closed` w przypadku przekroczenia czasu.
8. **Telemetria**:
   - Wystawianie metryk Prometheus (`/metrics`) dla opóźnień (p50, p95, p99), liczby zablokowanych żądań i narzutu czasowego.

---

## Interfejsy i komunikacja
- **Port wejściowy:** `8080` (HTTP API proxy)
- **Port metryk:** `9090` (Prometheus `/metrics`)
- **Komunikacja wychodząca:**
  - `upstream LLM` (`http://mock-llm:11434` w domyślnej konfiguracji; `make ollama-up` przełącza na prawdziwą Ollamę)
  - `semantic-service` (gRPC `semantic-service:50051` lub HTTP)
  - `redis` (pamięć podręczna budżetów i liczników)
  - `postgres` / audit stream (zapis zdarzeń audytowych)

---

## Kryteria ukończenia
- [ ] Zmiana `OPENAI_BASE_URL` w agencie na adres Gatewaya działa w pełni transparentnie.
- [ ] Wykrycie numeru karty kredytowej lub klucza API natychmiast maskuje lub blokuje żądanie (< 5 ms).
- [ ] Przekroczenie budżetu tokenów w Redis zwraca błąd `429 Too Many Requests / Budget Exceeded`.
- [ ] Zmiana rewizji polityki w control plane jest uwzględniana w locie, bez restartu kontenera (także przez `make reload-policy`).

### Dashboard prompt checks

`POST /admin/check` requires `ADMIN_TOKEN` and accepts `{ "direction": "input", "messages": [{ "role": "user", "content": "text" }] }`. It uses the same scanning pipeline as the proxy and returns the decision, active policy version and mode, redacted messages, regex findings, semantic scores and individual control statuses. `audit_saved` and `audit_event_id` confirm delivery to control-plane Events using `GATEWAY_TOKEN`. Submitted text is excluded from the stored event. Signature matching, budgets and agent-session controls are not marked as passed by this text-only check.
