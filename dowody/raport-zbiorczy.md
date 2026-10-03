# NoorPointer — dowody dla oceniających

- wygenerowano: 2026-10-03T19:53:02Z
- commit: `1474222`

## Pliki wynikowe

- [`reports/test_report.html`](test_report.html) — zmieniony 2026-10-03T19:18:13Z
- [`reports/smoke.txt`](smoke.txt) — zmieniony 2026-10-03T19:04:23Z

## Wynik sprawdzenia spójności (smoke)

```
smoke: 16 passed, 0 failed
```

## Znane luki (stan na 2026-10-03T19:53:02Z)

- **Gateway (Go)**: kontrole w ścieżce żądania nie są jeszcze włączone (dane osobowe, sekrety,
  sygnatury ataków, ogranicznik pętli, budżety), brakuje `GET /metrics` oraz wysyłania zdarzeń
  audytowych do `POST /api/v1/audit/events`. Z tego powodu 6 z 16 testów e2e nie przechodzi,
  a pulpit gatewaya w Grafanie pozostaje pusty.
- **Kontrole semantyczne nie są w ścieżce żądania**: gateway nie wywołuje jeszcze `/v1/scan`.
  Osobny alert `SemanticNoTraffic` sygnalizuje brak ruchu do tej usługi.
- **Dwa formaty sygnatur**: feed Nginx (`signatures-feed/signatures.json`, wyrażenia regularne)
  i kontrakt control plane (dopasowanie dosłowne oraz pola `source`/`category`/`target`) to dwa
  różne kontrakty. Katalog w panelu zawiera reguły startowe aplikacji (migracja V2) oraz wpisy
  z naszego feedu, dodawane pojedynczo przez `scripts/import-signatures.sh` (pierwsza alternatywa
  wzorca jako wartość dosłowna); gateway jeszcze nie konsumuje sygnatur.
- **Dane audytu są demonstracyjne**: panel pokazuje wpisy utworzone przez `make seed`,
  a nie rzeczywiste decyzje gatewaya.
- **Metryki gatewaya**: alert `GatewayMetricsMissing` (waga info) sygnalizuje brak `/metrics`.
  Po dodaniu endpointu trzeba odkomentować zadanie zbierające w `telemetry/prometheus.yml`.

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
