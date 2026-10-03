# Telemetry — Prometheus, alerty, Grafana

## Właściciel

DevOps.

## Zakres

Zbieranie metryk z działającego stosu, reguły alertów i gotowe pulpity w Grafanie.
Konfiguracja jest wersjonowana w tym katalogu i montowana do kontenerów, więc nie ma ręcznego
klikania w interfejsach.

## Zasada: żadnych wartości zastępczych

Panele pokazują **wyłącznie metryki, które naprawdę są zbierane**. Zakazane są fallbacki typu
`... or vector(3.8)`, które zamiast braku danych wyświetlają wymyśloną liczbę: juror techniczny
zada pytanie o taki wykres i nie będziemy mieli czym odpowiedzieć. Gdy metryki jeszcze nie ma,
panel ma pokazywać brak danych, a dokumentować to ma opis panelu i tabela „Stan na dziś”
w głównym `README.md`. Historia: tablica `noorpointer-overview.json` miała sześć takich fallbacków
(opóźnienie 3,8 ms, 14 zablokowanych żądań, 45 RPS), które zostały usunięte, a panel gatewaya
zamieniony na tekst wyjaśniający, że `GET /metrics` jeszcze nie istnieje.

## Co jest zbierane

| Źródło | Endpoint | Stan |
| :--- | :--- | :--- |
| `semantic-service` | `:8001/metrics` | zbierane (opóźnienia i wyniki kontroli semantycznych) |
| `controlplane` | `:8082/actuator/prometheus` | zbierane; endpoint jest dostępny tylko z tokenem administratora, dlatego w `prometheus.yml` jest wpisany nagłówek `Authorization` |
| `prometheus` | `localhost:9090` | zbierane (metryki własne, np. czas ostatniego przeładowania konfiguracji) |
| `gateway` | `:9090/metrics` | **nie zbierane** — gateway nie wystawia jeszcze tego endpointu, więc zadanie w `prometheus.yml` jest zakomentowane z komentarzem dopisującym, co zrobić po jego dodaniu |

Odstęp między odpytaniami: 2 s (`global.scrape_interval`).

Reguły alertów: `alert.rules.yml`, 9 pozycji.

| Alert | Waga | Wykrywa | Czy może zadziałać dziś |
| :--- | :--- | :--- | :--- |
| `GatewayDown` | critical | brak odpowiedzi `gateway:9090/metrics` | **nie** — nie ma zadania zbierającego, więc nie istnieje seria `up{job="noorpointer-gateway"}`; zadziała po dodaniu `/metrics` |
| `SemanticDown` | critical | brak odpowiedzi usługi semantycznej dłużej niż 2 minuty | tak (krótsze przerwy w czasie startu są normalne: kontener wczytuje modele) |
| `SemanticReplicaLost` | warning | część replik usługi semantycznej nie odpowiada, a część działa (ruch idzie dalej, spadł zapas) | tak |
| `ControlPlaneDown` | critical | brak odpowiedzi control plane (lub zerwane uwierzytelnianie metryk) | tak |
| `SemanticSlow` | warning | p95 kontroli semantycznych powyżej 200 ms (okno 5 minut) | tak |
| `SemanticCheckFailing` | warning | kontroli semantycznych kończących się błędem lub przekroczeniem czasu | tak |
| `GatewayBlockSpike` | info | skok liczby zablokowanych żądań (powyżej 5 na sekundę), etykieta `action="block"` | **nie** — czeka na `gateway_requests_total` z gatewaya |
| `SemanticNoTraffic` | info | gateway obsługuje ruch, a usługa semantyczna nie wykonuje żadnej kontroli | tak, ale dopiero gdy gateway wystawi metryki (warunek wymaga ruchu w gatewayu) |
| `GatewayMetricsMissing` | info | metryki gatewaya nie istnieją (znana luka do czasu dodania `/metrics`) | tak — to obecnie jedyny aktywny alert |

Trzy pozycje są celowe i opisują stan prac, a nie awarię. Alerty oparte na `rate()` milczą zarówno
wtedy, gdy wszystko działa, jak i wtedy, gdy danych po prostu nie ma — a to dwie różne sytuacje.
`GatewayMetricsMissing` rozpoznaje „metryki nie ma” po `absent()`, `GatewayBlockSpike` i
`SemanticNoTraffic` czekają na metryki gatewaya, a `SemanticNoTraffic` ma dodatkowy warunek ruchu,
żeby nie alarmować w przerwie w pracy zespołu.

## Pulpity Grafany

Provisioning: `telemetry/grafana/provisioning/` (źródło danych + lista pulpitów), definicje:
`telemetry/grafana/dashboards/`.

- `noorpointer-overview.json` — dostępność usług, kontrole semantyczne (opóźnienia, statusy, oznaczenia
  ryzyka) oraz ruch w control plane. Panel gatewaya jest tam opisany jako pusty do czasu `GET /metrics`.
- `semantic-controlplane.json` — szczegóły kontroli semantycznych oraz metryki HTTP control plane.

Pulpity dotyczące gatewaya pozostaną puste, dopóki nie pojawi się `gateway:9090/metrics`.
Grafana ma wyłączone logowanie (`GF_AUTH_ANONYMOUS_ENABLED`), wejście: `http://localhost:3001`.

## Jak sprawdzić, czy działa

```bash
make doctor                                     # m.in. walidacja konfiguracji compose z profilami
curl -s localhost:9091/api/v1/targets | grep -o '"job":"[^"]*"'   # semantic, controlplane, prometheus
curl -s localhost:9091/api/v1/alerts                            # aktywne alerty
curl -s --get --data-urlencode 'query=up' localhost:9091/api/v1/query
```

Po zmianie konfiguracji (`prometheus.yml` albo `alert.rules.yml`) wystarczy walidacja i przeładowanie:

```bash
sudo docker compose exec prometheus promtool check config /etc/prometheus/prometheus.yml
sudo docker compose exec prometheus promtool check rules /etc/prometheus/alert.rules.yml
curl -X POST localhost:9091/-/reload
```

Restart kontenera (`sudo docker compose up -d prometheus`) jest potrzebny tylko wtedy, gdy zmieniają się
flagi uruchomienia, na przykład przy pierwszym włączeniu `--web.enable-lifecycle`.

## Uwagi

- Scrape usługi semantycznej używa `metrics_path: /metrics/` (z ukośnikiem). Bez niego FastAPI zwraca
  307, a nginx przekazuje `Host` bez portu — Prometheus idzie za przekierowaniem na `:80` i cel jest
  `down` (fałszywy `SemanticDown`). W LB nagłówek to `$http_host`, żeby przekierowania zachowały port.
- W `prom/prometheus:v2.54.1` nie ma flagi `--config.expand-env`, dlatego token administratora jest
  wpisany w `prometheus.yml` na stałe. Przy zmianie `ADMIN_TOKEN` trzeba poprawić oba miejsca.
- Metryki z k6 nie są wysyłane do Prometheusa; wyniki widać w konsoli po `make bench`.
