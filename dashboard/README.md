# NoorPointer — React control panel

Panel control plane’u jest napisany w **React + Vite**, z prostym CSS. Teksty interfejsu są po angielsku. Backend pozostaje w Javie / Spring Boot, a dane w PostgreSQL.

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
- Signatures: ręczny import JSON/YAML i zastąpienie feedu.
- Token API w `sessionStorage`, odświeżanie danych co 15 sekund w Overview i Events. Niezapisane zmiany edytorów pozostają przy przełączaniu widoków i odświeżaniu danych.

## Struktura i build

- `src/App.jsx`: nawigacja, połączenie z API, token i komunikaty.
- `src/components/`: widoki i dialog.
- `src/api.js`, `src/hooks.js`: klient API i pobieranie danych.
- `src/styles.css`, `public/favicon.svg`: style i ikona.
- `npm ci && npm run build`: wynik w ignorowanym `dist/`.
- Maven pakuje ten sam wynik do JAR-a; gotowy JAR działa bez Node.

Pierwotny zakres zespołu zachowano w [SPEC.md](SPEC.md). Panel pokazuje konfigurację i raportowane dane; egzekwowanie kontroli oraz raportowanie audytu należą do gateway’a.
