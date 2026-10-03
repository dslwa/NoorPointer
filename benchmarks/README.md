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

Zmierzony narzut utrzymuje się w granicach 2–6 ms dla p95 przy aktualnym gatewayu (uwierzytelnianie JWT
i przekazanie żądania do modelu), co mieści się w założonym progu 10 ms.

## Uwagi

- Testy zakładają, że upstream odpowiada szybko i deterministycznie, dlatego domyślnie mierzymy na
  `mock-llm`. Po przełączeniu na prawdziwą Ollamę (`make ollama-up`) czasy rosną i progi nie będą
  spełnione — to ograniczenie sprzętowe, nie błąd gatewaya.
- Wraz z włączeniem kontroli w gatewayu (blokowanie, budżety) zmienią się wartości przepustowości
  i trzeba będzie zaktualizować progi.
