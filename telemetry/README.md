# Telemetry — Prometheus, alerty, Grafana

## Właściciel

DevOps.

## Zakres

Zbieranie metryk z działającego stosu, reguły alertów i gotowe pulpity w Grafanie.
Konfiguracja jest wersjonowana w tym katalogu i montowana do kontenerów, więc nie ma ręcznego
klikania w interfejsach.

## Co jest zbierane

| Źródło | Endpoint | Stan |
| :--- | :--- | :--- |
| `semantic-service` | `:8001/metrics` | zbierane (opóźnienia i wyniki kontroli semantycznych) |
| `controlplane` | `:8082/actuator/prometheus` | zbierane; endpoint jest dostępny tylko z tokenem administratora, dlatego w `prometheus.yml` jest wpisany nagłówek `Authorization` |
| `prometheus` | `localhost:9090` | zbierane (metryki własne, np. czas ostatniego przeładowania konfiguracji) |
| `gateway` | `:9090/metrics` | **nie zbierane** — gateway nie wystawia jeszcze tego endpointu, więc zadanie w `prometheus.yml` jest zakomentowane z komentarzem dopisującym, co zrobić po jego dodaniu |

Odstęp między odpytaniami: 2 s (`global.scrape_interval`).

Reguły alertów: `alert.rules.yml`, 8 pozycji.

| Alert | Waga | Wykrywa |
| :--- | :--- | :--- |
| `GatewayDown` | critical | brak odpowiedzi `gateway:9090/metrics` |
| `SemanticDown` | critical | brak odpowiedzi usługi semantycznej |
| `ControlPlaneDown` | critical | brak odpowiedzi control plane (lub zerwane uwierzytelnianie metryk) |
| `SemanticSlow` | warning | p95 kontroli semantycznych powyżej 200 ms |
| `SemanticCheckFailing` | warning | kontroli semantycznych kończących się błędem lub przekroczeniem czasu |
| `GatewayBlockSpike` | info | skok liczby zablokowanych żądań (powyżej 5 na sekundę) |
| `SemanticNoTraffic` | info | usługa działa, ale nie wykonała żadnej kontroli w ostatnich 5 minutach |
| `GatewayMetricsMissing` | info | metryki gatewaya nie istnieją (znana luka do czasu dodania `/metrics`) |

Dwie ostatnie pozycje są celowe. Alerty oparte na `rate()` milczą zarówno wtedy, gdy wszystko działa,
jak i wtedy, gdy danych po prostu nie ma — a to dwie różne sytuacje. Te reguły rozróżniają je jawnie.

## Pulpity Grafany

Provisioning: `telemetry/grafana/provisioning/` (źródło danych + lista pulpitów), definicje:
`telemetry/grafana/dashboards/`.

- `noorpointer-overview.json` — opóźnienia ścieżki deterministycznej, liczba zablokowanych żądań,
  wyzwolenia ogranicznika pętli, przepustowość.
- `semantic-controlplane.json` — opóźnienia i błędy kontroli semantycznych oraz metryki HTTP control plane.

Pulpity dotyczące gatewaya pozostaną puste, dopóki nie pojawi się `gateway:9090/metrics`.
Grafana ma wyłączone logowanie (`GF_AUTH_ANONYMOUS_ENABLED`), wejście: `http://localhost:3001`.

## Jak sprawdzić, czy działa

```bash
make doctor                                     # m.in. walidacja konfiguracji compose z profilami
curl -s localhost:9091/api/v1/targets | grep -o '"job":"[^"]*"'   # semantic, controlplane, prometheus
curl -s localhost:9091/api/v1/alerts                            # aktywne alerty
curl -s --get --data-urlencode 'query=up' localhost:9091/api/v1/query
```

Po zmianie `prometheus.yml` (główny plik konfiguracyjny) potrzebny jest restart kontenera:
`sudo docker compose restart prometheus`. Plik z regułami alertów wczytuje się sam.

## Uwagi

- W `prom/prometheus:v2.54.1` nie ma flagi `--config.expand-env`, dlatego token administratora jest
  wpisany w `prometheus.yml` na stałe. Przy zmianie `ADMIN_TOKEN` trzeba poprawić oba miejsca.
- Metryki z k6 nie są wysyłane do Prometheusa; wyniki widać w konsoli po `make bench`.
