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

## Dwa formaty sygnatur (stan obecny)

Feed używa wyrażeń regularnych (`pattern_type: regex`, `pattern`), natomiast kontrakt control plane
(`controlplane/src/main/resources/contracts/signatures.schema.json`) dopuszcza wyłącznie dopasowanie
dosłowne (`match.type: "literal"`) i wymaga pól `source`, `category`, `target`. To dwa różne kontrakty,
więc nie da się ich wprost zamienić. Stan na dziś:

- **Panel (control plane)** jest zasilany: `scripts/import-signatures.sh`
  (wywoływany przez `make seed`) czyta ten plik i zapisuje sygnatury do katalogu control plane,
  biorąc z każdego wzorca **pierwszą alternatywę** jako wartość dosłowną oraz mapując
  `target_component` na pole `target`. Katalog jest podmieniany w całości, więc operacja jest powtarzalna.
- **Gateway** jeszcze nie konsumuje sygnatur — docelowo czyta ten plik pod `SIGNATURES_FEED_URL`
  i kompiluje wyrażenia regularne (`refresh_s` w polityce).
- **Ujednolicenie** formatu (wyrażenia regularne w kontrakcie control plane) jest zadaniem otwartym.

Skrypt `push_new_signature.sh` dopisuje wpis do pliku i odświeża katalog w panelu tym samym
konwerterem, więc demonstracja „dodaj sygnaturę w trakcie działania" działa dla obu odbiorców.
