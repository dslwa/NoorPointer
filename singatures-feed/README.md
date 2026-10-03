# 🛡️ Signatures Feed (Historical Attack Mitigation)

## 👤 Właściciel (Owner)
**DevOps** + **Python Developer / Security Specialist**

---

## 🎯 Zakres (Scope)
Makieta zewnętrznego, centralnie zarządzanego źródła sygnatur ataków (*Threat Intelligence Feed*).
Realizuje **Wymóg Formalny 4**: *"detect or mitigate known historical attacks on AI infrastructure (i.e. where signatures of such attacks can be fed from some externally managed system)"*.
Symuluje globalne repozytorium reguł (np. odpowiednik reguł Snort/Suricata lub bazy YARA dla LLM/Agentic AI), z którego Control Plane i Gateway cyklicznie pobierają aktualizacje.

---

## 🛠️ Czym się zajmuje (Kluczowe Odpowiedzialności)

1. **Baza Sygnatur Znanych Historycznych Ataków**:
   - Przygotowanie pliku bazy (`signatures.json` / `signatures.yaml`) zawierającego wzorce realnych incydentów bezpieczeństwa w ekosystemie AI:
     - **ShadowRay**: nieuwierzytelnione wykonanie kodu przez API dashboardu Ray (`/api/job/submit`).
     - **Probllama (CVE-2024-37032)**: Path traversal w API pobierania modeli Ollama.
     - **Pickle RCE / Arbitrary Code Execution**: niebezpieczna deserializacja w wagach modeli na Hugging Face (wzorce `os.system`, `subprocess`, `posix.system`).
     - **LangChain / LlamaIndex Code Execution**: exploity typu math/python REPL chain execution.
     - **MCP Tool Poisoning / Rug Pull**: wstrzykiwanie instrukcji do opisów narzędzi MCP lub próba nadpisania parametrów systemowych.
     - **Indirect Prompt Injection**: ukryte instrukcje w dokumentach i tagach HTML (`<instruction>ignore...</instruction>`).
2. **Struktura Rekordu Sygnatury**:
   Każda sygnatura musi zawierać metadane wymagane przez zadanie:
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
3. **Serwer Feedu**:
   - Lekki kontener HTTP (np. Nginx lub prosty serwer w Go/Pythonie) wystawiający feed pod adresem `http://signatures-feed:8085/signatures.json`.
4. **Skrypt Aktualizacji na Żywo (Dynamic Feed Update Demo)**:
   - Skrypt `./push_new_signature.sh` dodający nowy rekord do feedu, pozwalający pokazać jurorom, jak Gateway bez restartu natychmiast uczy się blokować nowo opublikowany exploit.

---

## 🔌 Interfejsy i Komunikacja
- **Port:** `8085` (HTTP)
- **Endpoint:** `GET /signatures.json`
- **Konsumenci:** `controlplane` (synchronizacja okresowa lub na żądanie) oraz `gateway` (aktywny zbiór reguł w pamięci).

---

## 🏆 Definition of Done (Kryteria Sukcesu)
- [ ] Feed zawiera minimum 5 udokumentowanych, realnych historycznych podatności ze świata AI.
- [ ] Każda sygnatura ma przypisane ID, CVE (jeśli istnieje), kategorię OWASP oraz akcję (`block`/`alert`).
- [ ] Zapytanie symulujące atak ShadowRay lub złośliwy pickle zostaje rozpoznane po sygnaturze z feedu.
- [ ] Możliwe jest zademonstrowanie jury dodania nowej sygnatury w trakcie działania systemu.
