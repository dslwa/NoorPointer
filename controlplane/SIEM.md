# Eksport audytu dla zespołu bezpieczeństwa

Control plane eksportuje zapisane zdarzenia do **CEF 0**, **JSON** i CSV. W panelu React: **Events → CEF / JSON**. Eksport korzysta z tych samych filtrów co lista i obejmuje wszystkie pasujące zdarzenia, niezależnie od bieżącej strony tabeli. Maksymalnie 10 000 rekordów; po przekroczeniu limitu API zwraca `413` i należy zawęzić filtry czasu.

## Pobieranie

Wymagany token administratora. Przykład pobrania blokad jako pliku CEF:

```sh
curl --fail --show-error --get 'http://localhost:8082/api/v1/audit-events/export' \
  --header "Authorization: Bearer ${ADMIN_TOKEN:-local-dev-admin}" \
  --data-urlencode 'format=cef' \
  --data-urlencode 'action=block' \
  --output audit.cef
```

Dla JSON zmień `format=cef` na `format=json` i nazwę pliku na `audit.json`. W Compose można użyć adresu `http://localhost:3000`, ponieważ Nginx przekazuje `/api` do Javy. Dodatkowe filtry: `agent`, `category`, `from`, `to`. Daty są w ISO-8601 UTC; `from` jest włącznie, `to` wyłącznie.

Odpowiedź ma nagłówek `Content-Disposition: attachment`, właściwy typ zawartości i `Cache-Control: no-store`. CEF ma kodowanie UTF-8 i po jednym zdarzeniu na linię. JSON to tablica pełnych rekordów, z oryginalnymi nazwami pól, czasami UTC, kontekstem i metrykami liczbowymi.

## Format CEF

Nagłówek ma postać:

```text
CEF:0|NoorPointer|Gateway|0.1.0|DeviceEventClassID|EventName|Severity|extensions
```

Przykładowy początek zdarzenia blokującego prompt injection:

```text
CEF:0|NoorPointer|Gateway|0.1.0|PROMPT_INJECTION|Prompt injection|8|externalId=event-001 act=BLOCKED cat=LLM01:2025 end=1767225600000 rt=1767225601000 cs1Label=AgentId cs1=agent-01
```

Rzeczywisty eksport zawiera również pola korelacji i metryki z poniższej tabeli. Produkt `Gateway` opisuje źródło decyzji; plik generuje control plane. `0.1.0` jest wersją produktu, a `CEF:0` wersją formatu. Dane demo mają oznaczenie `Demo=1`; nie stanowią dowodu wykrycia rzeczywistego ataku.

| Pole CEF | Znaczenie / pole audytu |
| --- | --- |
| `DeviceEventClassID` | `signature_id`, jeśli podano; w przeciwnym razie nazwa kontroli wielkimi literami. Raporty zużycia mają `USAGE` |
| `EventName` | Czytelna nazwa rodzaju zdarzenia, np. `Prompt injection`, `Secret leakage`, `LLM usage` |
| `Severity` | `info=1`, `low=3`, `medium=5`, `high=8`, `critical=10` |
| `act` | `ALLOWED`, `BLOCKED`, `REDACTED`, `MONITORED`, `TIMEOUT` |
| `cat` | Kategoria OWASP z pola `category` |
| `externalId` | ID zdarzenia; dla ID dłuższego niż 40 znaków stabilny identyfikator UUID |
| `end` | Czas zdarzenia `occurred_at`, milisekundy od epoki Unix |
| `rt` | Czas odebrania `received_at`, milisekundy od epoki Unix |
| `cs1`, `cs1Label=AgentId` | ID agenta |
| `cs2`, `cs2Label=Team` | Zespół |
| `cs3`, `cs3Label=Model` | Model |
| `cs4`, `cs4Label=RequestId` | ID żądania, wspólne dla decyzji i raportu zużycia |
| `cs5`, `cs5Label=SessionId` | ID sesji |
| `cs6`, `cs6Label=Control` | Nazwa kontroli |
| `flexString1`, `flexString1Label=EventId` | Pełne oryginalne ID zdarzenia, także gdy przekracza limit `externalId` |
| `flexString2`, `flexString2Label=EventKind` | `decision` lub `usage` |
| `cn1`, `cn1Label=Tokens` | Liczba tokenów |
| `cn2`, `cn2Label=PolicyVersion` | Wersja polityki, jeśli została zgłoszona |
| `cfp1`, `cfp1Label=CostUSD` | Koszt w USD |
| `cfp2`, `cfp2Label=GPUSeconds` | Zużycie GPU |
| `cfp3`, `cfp3Label=LatencyMs` | Opóźnienie |
| `flexNumber1`, `flexNumber1Label=Demo` | `1` dla danych demo, w pozostałych przypadkach `0` |
| `msg` | Opis; maksymalnie 1023 znaki zgodnie ze słownikiem CEF |

Puste opcjonalne pola są pomijane. ID agenta trafia do `cs1`, ponieważ `src` oznacza adres IP. Nie generujemy fikcyjnego adresu IP. W nagłówku escapowane są `|` i `\`; w rozszerzeniach `=`, `\`, CR i LF. Treść żądania nie może w ten sposób dopisać drugiego rekordu lub własnego pola `act`. Pełny opis i kontekst pozostają w JSON, nawet gdy opis CEF musi zostać skrócony.

## Import do SIEM

Format plikowy nie zawiera prefiksu Syslog — specyfikacja CEF dopuszcza taki eksport. Import wymaga skonfigurowanego parsera CEF lub JSON w docelowym systemie. Dla Microsoft Sentinel standardowy konektor CEF via AMA korzysta z transportu Syslog: kolektor musi przekazać rekordy CEF z odpowiednim prefiksem. Aplikacja udostępnia pliki i API eksportu; nie uruchamia wysyłki do zewnętrznego SIEM-u.

Zgodność formatu i mapowanie pól sprawdzają testy formattera oraz testy integracyjne HTTP/PostgreSQL: nagłówki, severity, akcje, korelacja, daty, Unicode, znaki specjalne, długie ID, limity długości, filtrowanie oraz kompletność JSON. Nie deklarujemy certyfikacji ani testu importu do konkretnej instalacji Splunka, Elastic Security czy Microsoft Sentinel.

Źródła kontraktu:

- [ArcSight CEF — struktura, kodowanie i format plikowy](https://www.microfocus.com/documentation/arcsight/arcsight-smartconnectors-8.3/cef-implementation-standard/Content/CEF/Chapter%201%20What%20is%20CEF.htm).
- [ArcSight — słownik pól CEF](https://www.microfocus.com/documentation/arcsight/arcsight-smartconnectors-8.3/cef-implementation-standard/Content/CEF/Chapter%202%20ArcSight%20Extension.htm).
- [Microsoft Sentinel — mapowanie pól CEF](https://learn.microsoft.com/en-us/azure/sentinel/cef-name-mapping).
- [Microsoft Sentinel — wymagania transportu i walidacji CEF](https://learn.microsoft.com/en-us/azure/sentinel/cef-syslog-ama-troubleshooting).
