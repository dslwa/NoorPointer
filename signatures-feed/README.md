# Signatures Feed — sygnatury znanych ataków

## Właściciel

DevOps + Python.

## Zakres

Statyczny serwer pliku z sygnaturami znanych podatności w ekosystemie AI.
Feed jest udostępniany przez Nginx i pobierany przez gateway oraz control plane.

## Zawartość

`signatures.json` zawiera 5 wpisów, m.in. ShadowRay (CVE-2023-48022), Probllama (CVE-2024-37032),
niebezpieczną deserializację w plikach modeli, wykonanie kodu przez łańcuchy LangChain/LlamaIndex
oraz próby manipulacji opisami narzędzi MCP.

Format wpisu (obecnie używany, oparty na wyrażeniach regularnych):

```json
{
  "id": "SIG-2024-001",
  "name": "ShadowRay Remote Code Execution",
  "cve": "CVE-2023-48022",
  "owasp_category": "LLM02: Sensitive Information Disclosure / Insecure Output Handling",
  "target_component": "ray_api",
  "pattern_type": "regex",
  "pattern": "(/api/job/submit|ray\\.remote.*__import__)",
  "action": "block",
  "severity": "CRITICAL",
  "description": "Próba wykorzystania luki w dashboardzie Ray do nieautoryzowanego wykonania kodu."
}
```

## Interfejs

- `GET http://localhost:8085/signatures.json` (port kontenera: 8085)
- Konsumenci: gateway (`SIGNATURES_FEED_URL`) oraz control plane (import sygnatur).

## Aktualizacja sygnatury w trakcie działania

```bash
./signatures-feed/push_new_signature.sh
```

Skrypt dopisuje nowy wpis do `signatures.json`; plik jest widoczny w feedzie natychmiast, bez restartu
kontenera. Wykorzystujemy to w demonstracji dla jury.

## Decyzja o formatach sygnatur

**Rozstrzygnięcie: jedno źródło prawdy — ten plik. Katalog w panelu jest z niego wyprowadzany,
a docelowo kontrakt control plane dostaje obsługę wyrażeń regularnych.**

Uzasadnienie: wzorce regex są potrzebne w gatewayu (np. ShadowRay to alternatywa dwóch wzorców,
której nie da się zapisać jako dopasowanie dosłowne), a panel potrzebuje listy sygnatur. Zamiast
utrzymywać dwa ręcznie pisane dokumenty, mamy jeden plik i konwerter.

Stan obecny (działa):

- **Gateway** czyta ten plik pod `SIGNATURES_FEED_URL` i skompiluje wyrażenia regularne
  (`refresh_s` w polityce). Na razie nie konsumuje sygnatur.
- **Control plane** ma własny katalog sygnatur i dwa sposoby jego zapełniania:
  - migracja `V2__Seed_default_signatures` wgrywa 7 reguł startowych z
    `controlplane/src/main/resources/signatures/defaults.json` (frazy prompt injection, EN i PL,
    `action: monitor`), przy pierwszym starcie, nie nadpisując istniejących ID;
  - `POST /api/v1/signatures` dodaje **pojedynczy** wpis (409, gdy ID już istnieje), a panel ma do tego
    formularz (JSON albo wklejony dokument tekstowy/YAML);
  - `PUT /api/v1/signature-feed` podmienia **cały** katalog — panel używa go w przycisku
    „Replace feed”, który jest świadomą operacją zbiorczą.
- **`scripts/import-signatures.sh`** (wywoływany przez `make seed`) dokłada brakujące wpisy **addytywnie**:
  importuje najpierw reguły startowe aplikacji, potem ten feed, i nie kasuje niczego, co dodano z panelu.
  Dla wpisów z feedu bierze pierwszą alternatywę wzorca jako wartość dosłowną, mapuje `target_component`
  na pole `target`, a pełny wzorzec zachowuje w `description`. Powtórne uruchomienie kończy się na
  „juz bylo”, więc operacja jest idempotentna.
- Konwerter **preferuje jawne pola kontraktu** (`match`, `source`, `category`, `target`, `description`),
  jeśli wpis je ma — czyli wpisy zgodne z kontraktem control plane przechodzą bez zmian.

**Historia: pierwsza wersja importu używała `PUT /api/v1/signature-feed`, czyli podmiany całości.
Po dołożeniu przez backend reguł startowych i formularza w panelu takie zachowanie kasowałoby ich wpisy,
dlatego `make seed` korzysta wyłącznie ze ścieżki addytywnej.**

Docelowo (zadanie dla części Java, około 15 minut): rozszerzyć kontrakt control plane tak, aby
przyjmował wyrażenia regularne:

```json
"match": {
  "type":  { "enum": ["literal", "regex"] },
  "value": { "type": "string", "minLength": 1, "maxLength": 2000 }
}
```

oraz w miejscu dopasowania: gdy `type == "regex"`, kompilować `value` jako wyrażenie regularne
i przy błędnym wzorcu odrzucać sygnaturę (fail-closed), a nie przepuszczać ruch. Po tej zmianie
wpisy z tego feedu można przenosić do katalogu bez konwersji.

Skrypt `push_new_signature.sh` dopisuje wpis do pliku i odświeża katalog w panelu tym samym
konwerterem, więc demonstracja „dodaj sygnaturę w trakcie działania" działa dla obu odbiorców.

Po demonstracji wróć do stanu z repozytorium, żeby wpis testowy nie został w materiałach końcowych:

```bash
git checkout -- signatures-feed/signatures.json
make seed                      # odświeża katalog w panelu do pięciu sygnatur z repo
```
