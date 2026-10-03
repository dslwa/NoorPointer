# NoorPointer — opis projektu (do formularza zgłoszenia)

**Tytuł projektu:** NoorPointer — warstwa kontroli dla systemów agentowych (AI Control Layer)

**Nazwa zespołu:** NoorPointer

**Członkowie zespołu (1–6):** Kacper Bołdak (Go/gateway), Daniel Salawa (Python/semantyka), Robert Kania (Java/panel), Dawid Żarnecki (DevOps/infrastruktura)

**Repozytorium:** github.com/dslwa/NoorPointer

**Prezentacja:** `reports/deck/NoorPointer-10-slajdow.pdf` (10 slajdów, generowana z `deck/slajdy.md`)

## Opis

NoorPointer to warstwa kontroli wstawiana między agenta AI a model oraz narzędzia. Agent nie zmienia
swojego kodu: wystarczy wskazać mu adres gatewaya, który mówi protokołem zgodnym z API OpenAI. Cała
reszta dzieje się po stronie warstwy kontroli: uwierzytelnienie żądania, egzekwowanie polityki
bezpieczeństwa, rozliczanie budżetów, wykrywanie pętli oraz zapis każdej decyzji do dziennika audytu.

Rozwiązanie składa się z czterech elementów. **Gateway** (Go) jest punktem wejścia: weryfikuje token
JWT RS256, pobiera dokument polityki z control plane i przelicza go na decyzje w ścieżce żądania.
**Control plane** (Java, Spring Boot) przechowuje politykę jako wersjonowane rewizje, prowadzi katalog
sygnatur znanych ataków i trwały dziennik audytu, a także udostępnia eksport w formatach CEF, JSON
i CSV dla systemów SIEM. **Usługa semantyczna** (Python) wykonuje kontrole, których nie da się wyrazić
wyrażeniem regularnym: klasyfikację prompt injection modelem DeBERTa, rozpoznawanie danych osobowych
przez Presidio i spaCy (z sumą kontrolną PESEL), ocenę treści przez Llama Guard oraz analizę
bezpieczeństwa artefaktów modeli (poligloty, zip-bomby, szablony czatu GGUF analizowane jako AST,
bez odpicklowywania czegokolwiek). **Panel i telemetria** dają zespołowi bezpieczeństwa widok
incydentów, rewizji polityki, katalogu sygnatur i budżetów, a Prometheus z Grafaną — metryki i osiem
reguł alertów.

Najważniejszą cechą architektury jest to, że **polityka, sygnatury i budżety są danymi, nie kodem**.
Nową regułę można dodać w trakcie działania systemu (także z panelu), a gateway uwzględnia ją bez
restartu. Kontrole semantyczne działają w trybie fail-closed: wynik „odrzucone” blokuje żądanie zawsze,
niezależnie od konfiguracji timeoutu, a brak wyniku nigdy nie jest interpretowany jako „czysto”.

Stan prac opisujemy wprost. Działają: uwierzytelnianie, dystrybucja i hot-reload polityki, katalog
sygnatur (12 reguł), cztery detektory semantyczne i skaner artefaktów, audyt z eksportem dla SIEM,
panel, telemetria oraz testy modułów. Egzekwowanie kontroli w gatewayu jest w trakcie implementacji,
dlatego w pakiecie testów e2e 10 z 16 przypadków przechodzi, a sześć czerwonych dotyczy właśnie tych
kontroli. Scenariusze demonstracyjne rozróżniają stan `PENDING` (kontrola jeszcze nie istnieje) od
`FAIL` (błąd), żeby brak implementacji nie był mylony z awarią.

Całość uruchamia się jedną komendą (`sudo make up`), działa bez dostępu do internetu w czasie
działania i nie wymaga żadnej usługi w chmurze — model klasyfikujący jest częścią obrazu, a domyślnym
modelem językowym jest lokalny mock, którego jednym poleceniem można zamienić na prawdziwą Ollamę.
