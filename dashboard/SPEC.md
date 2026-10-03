# 📊 Dashboard (Security & Management UI)

## 👤 Właściciel (Owner)
**Frontend Developer** / **Java / Fullstack Developer**

---

## 🎯 Zakres (Scope)
Interaktywny interfejs graficzny użytkownika (Dashboard UI). Stanowi **aż 20% łącznej oceny jury** (*Security Reporting*). 
Odpowiada za wizualizację postury bezpieczeństwa, prezentację wykrytych incydentów w czasie rzeczywistym, kontrolę budżetów finansowych oraz umożliwia intuicyjny podgląd i edycję aktywnych guardraili dla dwóch grup odbiorców: kadry zarządzającej (Management) i oficerów bezpieczeństwa (Security Team).

---

## 🛠️ Czym się zajmuje (Kluczowe Odpowiedzialności)

1. **Widok dla Kadry Zarządzającej (Executive / Management View)**:
   - **Wskaźnik Bezpieczeństwa (*Security Posture Score*)**: syntetyczny wskaźnik (0–100%) obrazujący aktualny poziom ochrony.
   - **Wykresy Budżetowe i Kosztowe**:
     - Wykorzystanie tokenów i kosztów w USD w czasie per zespół, agent i model.
     - Ostrzeżenia o zbliżaniu się do limitów budżetowych.
   - **Trendy Wolumenu Zapytań**: dozwolone vs zablokowane interakcje.
2. **Widok dla Zespołu Bezpieczeństwa (Security Operations / SOC View)**:
   - **Strumień Incydentów na Żywo (Threat Stream)**:
     - Tabela zdarzeń z filtrowaniem po dacie, poziomie krytyczności, akcji (`BLOCKED`, `REDACTED`, `ALLOWED`).
   - **Kategoryzacja wg OWASP**:
     - Prezentacja zagrożeń pogrupowanych wg *OWASP Top 10 for LLMs* (np. LLM01: Prompt Injection, LLM06: Sensitive Information Disclosure) oraz *OWASP Agentic AI Threats*.
   - **Szczegóły Incydentu (Forensics Modal)**:
     - Podgląd promptu z zaznaczoną czerwoną flagą naruszenia (np. zanonimizowane PII, zablokowany exploit, dopasowana sygnatura CVE).
3. **Katalog i Przełącznik Kontroli (Guardrails & Policy Control)**:
   - Wyświetlenie stanu guardraili (np. Regex PII, DeBERTa Prompt Injection, Loop Breaker, Skaner Modeli).
   - Możliwość przełączania profili bezpieczeństwa (`Strict`, `Balanced`, `Permissive`) lub ręcznego włączania/wyłączania kontroli na żywo podczas prezentacji dla jury.
4. **Eksport Raportów**:
   - Przycisk pobrania raportu audytowego w formacie CSV / JSON / CEF wygenerowanego przez Control Plane.

---

## 🔌 Interfejsy i Komunikacja
- **Port aplikacji:** `3000` (React / Vite / Next.js)
- **Komunikacja:** REST API z `controlplane:8082`
- **Technologia:** React / TypeScript + Tailwind CSS / shadcn/ui lub gotowe komponenty wykresów (Recharts / Chart.js / Tremor).

---

## 🏆 Definition of Done (Kryteria Sukcesu)
- [ ] Po wejściu pod `http://localhost:3000` jury widzi przejrzysty, nowoczesny dashboard bez błędów w konsoli.
- [ ] Zablokowanie niebezpiecznego promptu w teście natychmiast pojawia się na wykresie i w tabeli incydentów.
- [ ] Wykresy kosztów i tokenów poprawnie sumują zużycie zasobów.
- [ ] Dostępny jest widok kategoryzacji zagrożeń wg taksonomii OWASP.
