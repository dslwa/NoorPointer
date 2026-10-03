# NoorPointer — dowody dla oceniających

- wygenerowano: 2026-10-03T21:07:06Z
- commit: `94e7efb`

## Pliki wynikowe

- [`reports/test_report.html`](test_report.html) — zmieniony 2026-10-03T21:06:42Z
- [`reports/smoke.txt`](smoke.txt) — zmieniony 2026-10-03T21:03:13Z

## Wynik sprawdzenia spójności (smoke)

```
smoke: 16 passed, 0 failed
```

## Znane luki (stan na 2026-10-03T21:07:06Z)

- **Brama egzekwuje część kontroli**: działają allowlista modeli, sekrety, redakcja danych osobowych
  oraz kontrole semantyczne (prompt injection, content safety) przez gRPC. Otwarte pozostają:
  sygnatury ataków, budżety, ogranicznik pętli i lista narzędzi MCP.
- **Brak `GET /metrics` w bramie** (port 9090). Alert `GatewayMetricsMissing` (waga info) to
  sygnalizuje; po dodaniu endpointu odkomentuj zadanie zbierające w `telemetry/prometheus.yml`.
- **Brama nie wysyła zdarzeń audytowych** do `POST /api/v1/audit/events` — dziennik w panelu
  zasilają dane demonstracyjne z `make seed` (oznaczone jako `synthetic`).
- **PII w wolnym tekście i wyciek systemowego promptu** (`pii_ner`, `leakage`) działają w usłudze
  semantycznej, ale brama woła na razie tylko prompt injection i content safety.
- **Dwa formaty sygnatur**: feed Nginx (regex) i kontrakt control plane (dopasowanie dosłowne +
  pola `source`/`category`/`target`) to dwa różne kontrakty; gateway nie konsumuje sygnatur.
- **Testy e2e**: `tests/test_guardrails.py` ma 25 przypadków; pełny wynik tego przebiegu jest
  w raporcie HTML z `sudo make test` (PENDING = kontroli jeszcze nie ma, FAIL = kontrola nie działa).

## Jak to odtworzyć

```bash
sudo make keys        # raz na maszynie (klucze nie są wersjonowane)
sudo make up          # cały stos + dane demonstracyjne (upstream: mock-llm, bez dostępu do sieci)
make smoke            # 16 sprawdzeń spójności stosu
sudo make test        # testy e2e -> reports/test_report.html
sudo make bench       # k6: narzut przy typowym ruchu
sudo make bench-flood # k6: duży ruch z próbami ataku
sudo make demo-full   # scenariusze demonstracyjne
sudo make checkpoint  # wszystko powyżej jednym poleceniem
```
