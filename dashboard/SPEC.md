# Dashboard (Security & Management UI)

## Właściciel
**Frontend Developer** / **Java / Fullstack Developer**

---

## Zakres
Interaktywny interfejs graficzny użytkownika (Dashboard UI). Stanowi **20% łącznej oceny jury** (*Security Reporting*).
Odpowiada za wizualizację postury bezpieczeństwa, prezentację wykrytych incydentów w czasie rzeczywistym, kontrolę budżetów finansowych oraz umożliwienie intuicyjnego podglądu i edycji aktywnych guardraili dla dwóch grup odbiorców: kadry zarządzającej (Management) i oficerów bezpieczeństwa (Security Team).

---

## Zakres odpowiedzialności

1. **Widok dla kadry zarządzającej (Executive / Management View)**:
   - **Wskaźnik bezpieczeństwa (*Security Posture Score*)**: syntetyczny wskaźnik (0–100%) obrazujący aktualny poziom ochrony.
   - **Wykresy budżetowe i kosztowe**:
     - Wykorzystanie tokenów i kosztów w USD w czasie dla zespołu, agenta i modelu.
     - Ostrzeżenia o zbliżaniu się do limitów budżetowych.
   - **Trendy wolumenu zapytań**: dozwolone vs zablokowane interakcje.
2. **Widok dla zespołu bezpieczeństwa (Security Operations / SOC View)**:
   - **Strumień incydentów na żywo (Threat Stream)**:
     - Tabela zdarzeń z filtrowaniem po dacie, poziomie krytyczności, akcji (`BLOCKED`, `REDACTED`, `ALLOWED`).
   - **Kategoryzacja według OWASP**:
     - Prezentacja zagrożeń pogrupowanych według *OWASP Top 10 for LLMs* (np. LLM01: Prompt Injection, LLM06: Sensitive Information Disclosure) oraz *OWASP Agentic AI Threats*.
   - **Szczegóły incydentu (Forensics Modal)**:
     - Podgląd promptu z zaznaczoną czerwoną flagą naruszenia (np. zanonimizowane PII, zablokowany exploit, dopasowana sygnatura CVE).
3. **Katalog i przełącznik kontroli (Guardrails & Policy Control)**:
   - Wyświetlenie stanu guardraili (np. Regex PII, DeBERTa Prompt Injection, Loop Breaker, Skaner Modeli).
   - Możliwość przełączania profili bezpieczeństwa (`Strict`, `Balanced`, `Permissive`) lub ręcznego włączania/wyłączania kontroli na żywo podczas prezentacji dla jury.
4. **Eksport raportów**:
   - Przycisk pobrania raportu audytowego w formacie CSV / JSON / CEF wygenerowanego przez Control Plane.

---

## Interfejsy i komunikacja
- **Port aplikacji:** `3000` (React / Vite / Next.js)
- **Komunikacja:** REST API z `controlplane:8082`
- **Technologia:** React / TypeScript + Tailwind CSS / shadcn/ui lub gotowe komponenty wykresów (Recharts / Chart.js / Tremor).

---

## Kryteria ukończenia
- [ ] Po wejściu pod `http://localhost:3000` jury widzi przejrzysty, nowoczesny dashboard bez błędów w konsoli.
- [ ] Zablokowanie niebezpiecznego promptu w teście natychmiast pojawia się na wykresie i w tabeli incydentów.
- [ ] Wykresy kosztów i tokenów poprawnie sumują zużycie zasobów.
- [ ] Dostępny jest widok kategoryzacji zagrożeń według taksonomii OWASP.
