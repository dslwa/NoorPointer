# NoorPointer — React control panel

Panel control plane’u jest napisany w **React + Vite**, z prostym CSS. Teksty interfejsu są po angielsku. Backend pozostaje w Javie / Spring Boot, a dane w PostgreSQL.

Control plane zarządza politykami i sygnaturami oraz udostępnia je gatewayowi Go:
`GET /api/gateway/policy` zwraca opublikowaną politykę, a `GET /api/gateway/signatures`
aktualny feed sygnatur. Oba endpointy wymagają tokenu gatewaya i obsługują `ETag` / `If-None-Match`.
Kontrole treści i decyzje o blokowaniu należą do gatewaya; panel nie wysyła tekstu do serwisu Python.

## Uruchomienie

Najprościej z głównego katalogu repo:

```sh
make controlplane-run
```

Wymaga Docker Desktop, JDK 21+ i Node.js 22.12+ (zalecany 24). Make uruchamia PostgreSQL, a Maven wykonuje `npm ci`, buduje React i uruchamia Javę. Panel: **http://localhost:8082**. Kliknij **Connect** (lokalny token `local-dev-admin`), a następnie opcjonalnie **Load demo**.

Do pracy nad frontendem, kiedy Java już działa, w drugim terminalu:

```sh
make dashboard-dev
```

Vite działa na **http://localhost:5173**, przeładowuje zmiany i przekazuje `/api` do Javy na 8082. Inny backend można wskazać przez `CONTROLPLANE_URL`, np. `CONTROLPLANE_URL=http://127.0.0.1:8181 make dashboard-dev`.

W Docker Compose panel jest dostępny na **http://localhost:3000**. Obraz buduje Vite w etapie Node, a Nginx serwuje `dist/` i przekazuje `/api` do `controlplane:8082`. Node nie jest wymagany na hoście przy użyciu Dockera.

## Funkcje

- Overview: statystyki, wykres, kategorie blokad i budżety.
- Policies: profile, przełączniki kontroli, próg prompt injection, edytor JSON/YAML, walidacja, wersje i publikacja.
- Events: filtry, stronicowanie, szczegóły i eksport JSON/CSV/CEF.
- Signatures: siedem reguł domyślnych jest instalowanych jednorazowo przez migrację bazy. Istniejące reguły o tym samym ID pozostają niezmienione; restart nie przywraca usuniętych reguł. Zestaw w `../controlplane/src/main/resources/signatures/defaults.json` zawiera własne przykłady NoorPointer inspirowane scenariuszami OWASP (LLM01/02/07), z linkami do źródeł; nie jest oficjalnym feedem OWASP. Domyślna akcja to `monitor`. Dopasowanie jest dosłowne i może oznaczyć cytaty edukacyjne; reguły nie zastępują kontroli semantycznych ani ochrony wyjścia. Brak automatycznej synchronizacji z OWASP.
- **Add signature -> Paste JSON / YAML** pozwala wkleić pojedynczy obiekt sygnatury. **Load example** pokazuje wymagany format. **Save signature** dopisuje regułę bez usuwania pozostałych; backend sprawdza poprawność i unikalność ID. **Use form** pozwala wypełnić pola ręcznie. W sekcji **Replace entire feed** można zaimportować cały JSON/YAML; zastąpienie usuwa reguły nieobecne w dokumencie.
- Token API w `sessionStorage`, odświeżanie danych co 15 sekund w Overview i Events. Niezapisane zmiany edytorów pozostają przy przełączaniu widoków i odświeżaniu danych.

## Struktura i build

Testy frontendu: `make dashboard-test` z katalogu głównego lub `npm test` w `dashboard/`
po instalacji zależności (`npm ci`). Vitest i React Testing Library sprawdzają klienta API,
usuwanie polityk oraz zachowanie niezapisanych
zmian edytora. Odpowiedzi usług są zastępowane w testach; backendy i modele nie muszą działać.
`npm run test:watch` uruchamia testy przy zmianach plików. Integrację Javy z PostgreSQL
sprawdza osobno `make controlplane-test`.

- `src/app/`: główny komponent aplikacji i definicja nawigacji.
- `src/pages/`: osobne widoki Overview, Policies, Events i Signatures.
- `src/components/layout/`: układ panelu i nagłówek strony.
- `src/components/common/`: wspólny dialog i komunikaty.
- `src/features/auth/`: formularz połączenia i obsługa tokenu.
- `src/api/`: klient HTTP oraz ścieżki REST pod `/api/v1`.
- `src/hooks/`: pobieranie danych, odświeżanie, akcje i komunikaty.
- `src/utils/`, `src/constants/`: formatowanie, eksport, filtry i stałe.
- `src/styles/global.css`, `public/favicon.svg`: style i ikona.
- `npm run format` / `npm run format:check`: formatowanie i sprawdzenie stylu kodu.
- `npm ci && npm run build`: wynik w ignorowanym `dist/`.
- Maven pakuje ten sam wynik do JAR-a; gotowy JAR działa bez Node.

Pierwotny zakres zespołu zachowano w [SPEC.md](SPEC.md). Panel pokazuje konfigurację i raportowane dane; egzekwowanie kontroli oraz raportowanie audytu należą do gateway’a.
