# Benchmarks — pomiar narzutu gatewaya

## Właściciel

DevOps.

## Zakres

Pomiar czasu dodawanego przez gateway względem bezpośredniego wywołania modelu.
Testy są uruchamiane w kontenerze k6 i mierzą pełną ścieżkę HTTP do `http://gateway:8080`.

## Skrypty

| Plik | Ruch | Progi |
| :--- | :--- | :--- |
| `benchmark_baseline.js` | 20 do 50 użytkowników wirtualnych (5 s narastania, 10 s obciążenia, 5 s wygaszania) | p95 poniżej 10 ms, mniej niż 1% błędów, pojedyncze żądanie poniżej 15 ms |
| `benchmark_malicious_flood.js` | 30 do 80 użytkowników z treścią przypominającą atak | p95 poniżej 25 ms, mniej niż 5% błędów, pojedyncze żądanie poniżej 50 ms |
| `benchmark_budget_concurrency.js` | 40 użytkowników przez 20 s, równoległe żądania jednego agenta | p95 poniżej 25 ms, mniej niż 5% błędów |

Każdy skrypt na starcie wykonuje `setup()` z kilkoma żądaniami rozgrzewającymi. Bez tego pierwsze
żądania trafiają na zimny start (połączenie, ładowanie modelu po stronie usługi) i zawyżają percentyle.

Token gatewaya jest brany ze zmiennej `GATEWAY_JWT`, którą podstawiają polecenia `make`.

## Uruchomienie

```bash
sudo make bench           # ruch typowy
sudo make bench-flood     # duży ruch z próbami ataku
sudo make bench-budget    # równoległe żądania jednego agenta
```

## Wyniki

Wynik trafia na standardowe wyjście: podsumowanie k6 z percentylami, liczbą błędów i informacją,
czy progi zostały spełnione. Przekroczenie progu kończy się niezerowym kodem wyjścia, więc polecenie
nadaje się do użycia w skryptach.

## Dwa tryby pomiaru i granica warstwy AI

Od czasu włączenia kontroli w bramie ścieżka żądania obejmuje sprawdzanie treści modelem, więc
o przepustowości decyduje **warstwa AI, a nie sam pośrednik**. Dlatego pomiar ma dwa tryby:

| Polecenie | Co mierzy | Uwaga |
| :--- | :--- | :--- |
| `sudo make bench` | pełną ścieżkę kontroli przy obciążeniu, które warstwa AI wyrabia (VUS=3) | domyślne, porównywalne między uruchomieniami |
| `sudo make bench-stress` | przeciążenie (VUS=50) | brama zaczyna blokować, bo tak działa tryb fail-closed |
| `make bench-semantic` | przepustowość samych kontroli AI (Python) i efekt skalowania | 13,4 żądań/s, 26,8 kontroli/s na tej maszynie |

Zmierzona przepustowość warstwy AI na tej maszynie (8 wątków CPU) to **13,4 żądań/s** (26,8 kontroli
na sekundę). Poprzedni pomiar samego pośrednika dawał p95 w granicach 2,3 ms, bo nie wykonywał
żadnych kontroli. Przy 50 klientach naraz (ok. 77 żądań/s, czyli sześć razy więcej niż możliwości
modeli) brama zablokowała 98,8% żądań — nie z powodu błędu, ale dlatego, że budżet kontroli
(`semantic_timeout_ms`) mijał, a tryb `fail_closed` woli zablokować niż przepuścić niesprawdzony ruch.

Wniosek architektoniczny: **wąskim gardłem jest wnioskowanie modelu, nie brama.** Zwiększanie
przepustowości robi się replikami na osobnych maszynach (patrz „Skalowanie" w głównym README), a nie
podnoszeniem liczby klientów w teście.

## Uwagi

- Testy zakładają, że upstream odpowiada szybko i deterministycznie, dlatego domyślnie mierzymy na
  `mock-llm`. Po przełączeniu na prawdziwą Ollamę (`make ollama-up`) czasy rosną i progi trzeba
  podnieść — to ograniczenie sprzętowe, nie błąd gatewaya.
- Parametry uruchomienia: `VUS` (liczba klientów), `DURATION` (czas obciążenia), `LATENCY_MS`
  (budżet czasu na żądanie, domyślnie 1500 ms — zgodny z `semantic_timeout_ms` w polityce).
- Budżet kontroli jest **danymi**: po pomiarach podnieśliśmy go z 300 ms do 1500 ms jedną rewizją
  polityki, bez restartu i bez przebudowy obrazów.
