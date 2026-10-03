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

## Znane ograniczenie: dwa różne formaty sygnatur

Feed używa wyrażeń regularnych (`pattern_type: regex`, `pattern`), natomiast kontrakt control plane
(`controlplane/src/main/resources/contracts/signatures.schema.json`) dopuszcza wyłącznie dopasowanie
dosłowne (`match.type: "literal"`) i wymaga pól `source`, `category`, `target`.
Z tego powodu:

- wpisy z tego feedu nie przechodzą walidacji importu w control plane,
- skrypt `push_new_signature.sh` nie jest w stanie zsynchronizować wpisu z control plane
  (wywołuje `POST /api/v1/signatures/sync`, którego w obecnym control plane nie ma — skrypt raportuje kod odpowiedzi),
- ujednolicenie formatu (albo rozszerzenie kontraktu control plane o wyrażenia regularne) jest zadaniem otwartym.

Do czasu rozstrzygnięcia gateway korzysta z tego feedu, a control plane ma własny, węższy format.
