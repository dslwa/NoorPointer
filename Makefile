# NoorPointer - wejscie do infrastruktury (DevOps). Pelna lista komend: make help
# Na start: sudo make up (uruchamia system), potem sudo make checkpoint (testy + dowody).
#
# Komendy, ktore uzywaja Dockera, uruchamiaj przez `sudo make ...` (Docker nalezy do roota).
# Skrypty, ktore tylko pytaja dzialajace uslugi (curl), dzialaja bez sudo.

COMPOSE         ?= docker compose
SEMANTIC_REPLICAS ?= 1  # ile kopii uslugi AI stawia make up (zmien: make scale REPLIKI=3)
COMPOSE_ALL      = $(COMPOSE) --profile tests --profile bench
OLLAMA_COMPOSE   = $(COMPOSE) -f docker-compose.yaml -f docker-compose.ollama.yaml
PROM_TOKEN_FILE  = telemetry/.prometheus-admin-token

# Pusty token = kazde pytanie do bramy odbite (401), wiec od razu przerywamy komende.
JWT_GUARD = jwt="$$(./scripts/token.sh)"; [ -n "$$jwt" ] || { echo "BLAD: pusty JWT - uruchom: make keys && make mint-build"; exit 1; }
K6        = $(COMPOSE) run --rm -e GATEWAY_JWT="$$jwt" benchmarks run

.PHONY: help \
        up dev-infra down restart build clean logs status wait \
        seed test test-unit test-local test-rebuild test-semantic bench bench-stress bench-flood bench-budget bench-semantic traffic \
        smoke verify verify-strict offline-check report deck checkpoint \
        demo demo-ready demo-full demo-strict \
        keys mint-build prometheus-token token token-file reload-policy new-signature db-tidy db-dump db-restore doctor urls \
        jury scan policy-edit policy-apply signature evidence pack stop scale scale-check \
        ollama-up ollama-down up-real \
        lint \
        postgres-up postgres-test-up controlplane-run controlplane-test controlplane-build dashboard-dev dashboard-test

help: ## Lista komend pogrupowana w sekcje
	@awk 'BEGIN {FS = ":.*## "} /^##@/ {printf "\n\033[1m%s\033[0m\n", substr($$0, 5)} /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

##@ Zacznij tutaj (dla osob oceniajacych)

jury: ## JEDNO polecenie: srodowisko, start stosu, wszystkie testy, ruch na panele i dowody
	./scripts/jury.sh

scan: ## Sprawdz dowolny tekst kontrolami AI: make scan TEXT="twoj tekst" [CHECKS=...]
	./scripts/scan.sh

policy-edit: ## Zapisz aktualne zasady bezpieczenstwa do policy.local.json (do edycji)
	./scripts/policy-edit.sh

policy-apply: ## Opublikuj edytowane zasady i przeladuj gateway bez restartu
	./scripts/policy-apply.sh

signature: ## Dodaj wlasna regule ataku: make signature PATTERN='...' NAME='...'
	@$(MAKE) --no-print-directory new-signature PATTERN="$(PATTERN)" NAME="$(NAME)" ACTION="$(ACTION)"

evidence: ## Zbiera dowody do katalogu dowody/ (widoczne na GitHubie bez uruchamiania)
	./scripts/evidence.sh

pack: ## Eksport do przekazania dalej: tylko pliki z gita (bez .env, kluczy i smieci) - PACK_OUT=sciezka
	@out="$(or $(PACK_OUT),/tmp/noorpointer-src.tar.gz)"; \
	git archive --format=tar.gz --prefix=noorpointer/ -o "$$out" HEAD; \
	echo "  zapisano $$out"; \
	echo "  plikow: $$(tar -tzf "$$out" | wc -l), rozmiar: $$(du -h "$$out" | cut -f1)"; \
	echo "  w archiwum NIE MA: .env, gateway/keys (klucz prywatny), gateway/bin, reports/, policy.local.json, node_modules"

stop: ## Zatrzymuje stos (dane i wolumeny zostaja, wracasz przez: make up)
	@$(MAKE) --no-print-directory down

scale: ## Ustaw liczbe replik: sudo make scale REPLIKI=3 (FORCE=1 odtwarza, TORCH_THREADS=N zmienia watki)
	@$(COMPOSE) run --rm --no-deps --entrypoint nginx semantic-lb -t >/dev/null 2>&1 || { echo "scale: blad w konfiguracji load balancera - uruchom: $(COMPOSE) run --rm --no-deps --entrypoint nginx semantic-lb -t"; exit 1; }
	@echo "  konfiguracja load balancera poprawna"
	@$(COMPOSE) up -d --scale semantic-app=$(or $(REPLIKI),3) $(if $(FORCE),--force-recreate semantic-app,--no-recreate) --remove-orphans 2>&1 | tail -4
	@./scripts/wait-ready.sh
	@$(COMPOSE) ps --format '  {{.Name}}  {{.Status}}' | grep semantic || true

scale-check: ## Sprawdza, czy ruch rozklada sie na repliki (mierzy licznik w kazdym kontenerze)
	./scripts/check-balance.sh

##@ Stos

up: ## Pelny stos + seed danych demo; czeka na gotowosc (VERBOSE=1 pokazuje budowanie, NOSEED=1 pomija seed)
	@test -f gateway/keys/jwt.pub || $(MAKE) --no-print-directory keys
	@$(MAKE) --no-print-directory prometheus-token
	@mkdir -p reports
	@if [ -n "$(VERBOSE)" ]; then \
	  $(COMPOSE) up -d --build --remove-orphans --scale semantic-app=$(SEMANTIC_REPLICAS); \
	else \
	  if ! $(COMPOSE) up -d --build --remove-orphans --scale semantic-app=$(SEMANTIC_REPLICAS) > reports/log-up.txt 2>&1; then \
	    echo "BLAD: nie udalo sie zbudowac lub uruchomic stosu. Ostatnie linie:"; tail -25 reports/log-up.txt; exit 1; \
	  fi; \
	  echo "  zbudowano i uruchomiono stos (pelny log: reports/log-up.txt)"; \
	fi
	@./scripts/wait-ready.sh
	@printf '  uslugi dzialajace: %s\n' "$$($(COMPOSE) ps --services --filter status=running 2>/dev/null | wc -l)"
	-@if [ -z "$(NOSEED)" ]; then ./scripts/seed.sh; fi

wait: ## Czeka, az wszystkie uslugi odpowiedza (WAIT_TIMEOUT=sekundy, domyslnie 180)
	./scripts/wait-ready.sh

dev-infra: ## Tylko bazy i telemetria (Postgres, Redis, mock LLM, feed, Prometheus, Grafana)
	@$(MAKE) --no-print-directory prometheus-token
	$(COMPOSE) up -d postgres redis mock-llm signatures-feed prometheus grafana

down: ## Zatrzymuje srodowisko
	$(COMPOSE) down

restart: down up ## Restart calego srodowiska

build: ## Buduje obrazy wszystkich serwisow
	$(COMPOSE) build

clean: ## Zatrzymuje i usuwa wolumeny (kasuje dane Postgresa - potem seed wroci z `make up`)
	$(COMPOSE) down -v --remove-orphans

logs: ## Logi wszystkich kontenerow (follow)
	$(COMPOSE) logs -f

status: ## Stan kontenerow i porty
	$(COMPOSE) ps

seed: ## Wypelnia baze audytu danymi demo (potrzebne dla eksportu CEF)
	./scripts/seed.sh

##@ Testy i dowody

test: seed ## e2e (seed + raport HTML); --tb=no ukrywa tracebacki, pelne sa w raporcie
	@$(JWT_GUARD); $(COMPOSE) run --rm --build -e GATEWAY_JWT="$$jwt" -e PYTEST_ADDOPTS="$${PYTEST_ADDOPTS:---tb=no}" tests; rc=$$?; \
	chown -R "$$(stat -c '%u:%g' .)" reports 2>/dev/null || true; exit $$rc

test-unit: ## Testy jednostkowe modulow (Go teraz; nie wymagaja dzialajacego stosu)
	cd gateway && go test ./...

lint: ## Szybki lint: skladnia skryptow bash + go vet (shellcheck, jesli jest zainstalowany)
	@for f in scripts/*.sh agent-demo/*.sh signatures-feed/*.sh deck/*.sh; do bash -n "$$f" || exit 1; done
	@echo "  skladnia skryptow bash: OK"
	@cd gateway && go vet ./...
	@echo "  go vet: OK"
	@if command -v shellcheck >/dev/null 2>&1; then shellcheck -S warning scripts/*.sh agent-demo/*.sh signatures-feed/*.sh && echo "  shellcheck: OK"; else echo "  (shellcheck nie zainstalowany - pomijam)"; fi

test-local: ## e2e bez Dockera na opublikowanych portach (szybka petla: kilka sekund, nie minut)
	@mkdir -p reports 2>/dev/null || true
	@test -d .venv-tests || python3 -m venv .venv-tests
	@.venv-tests/bin/pip -q install -r tests/requirements.txt
	@$(JWT_GUARD); \
	report=reports/test_report_local.html; \
	if [ ! -w reports ]; then report="$${TMPDIR:-/tmp}/noorpointer-test_report_local.html"; \
	  echo "uwaga: katalog reports/ nie jest zapisywalny - raport trafi do $$report"; \
	fi; \
	echo "raport: $$report"; \
	GATEWAY_JWT="$$jwt" .venv-tests/bin/python -m pytest tests/test_guardrails.py -v \
	  --html="$$report" --self-contained-html

test-rebuild: ## Przebudowuje obraz testow (po zmianie requirements.txt)
	$(COMPOSE) build --no-cache tests

bench: ## k6: pelna sciezka kontroli przy obciazeniu, ktore warstwa AI wyrabia (VUS=3)
	@$(JWT_GUARD); $(K6) /benchmarks/benchmark_baseline.js

bench-stress: ## k6: przeciazenie (VUS=50) - pokazuje, ze brama blokuje, gdy AI nie wyrabia
	@$(JWT_GUARD); $(COMPOSE) run --rm -e GATEWAY_JWT="$$jwt" -e VUS=50 benchmarks run /benchmarks/benchmark_baseline.js

bench-flood: ## k6: zalew zlosliwych promptow
	@$(JWT_GUARD); $(K6) /benchmarks/benchmark_malicious_flood.js

bench-semantic: ## Przepustowosc kontroli semantycznych (RUNDY=10 ROZMIAR=10, sam Python)
	python3 benchmarks/semantic_throughput.py --rounds $(or $(RUNDY),10) --concurrency $(or $(ROZMIAR),10)

bench-budget: ## k6: rownolegle zapytania jednego agenta (atomowosc budzetu)
	@$(JWT_GUARD); $(K6) /benchmarks/benchmark_budget_concurrency.js

traffic: ## Realny ruch na panele Grafany: zadania przez gateway + skany semantyczne (LICZNIK=3)
	./scripts/traffic.sh

smoke: ## Spiecie calego stosu (health + proxy + auth), zapis do reports/smoke.txt
	@mkdir -p reports
	./scripts/smoke.sh | tee reports/smoke.txt

verify: ## Zero-prep: smoke + offline-check + scenariusze demo (PENDING dozwolone)
	./scripts/verify.sh

verify-strict: ## Jak verify, ale PENDING liczy sie jako FAIL (po guardrailach gatewaya)
	./scripts/verify.sh --strict

offline-check: ## Lint: brak pobierania/instalacji w runtime (finalny stage obrazow)
	./scripts/offline-check.sh

report: ## Zbiera dowody dla jury do reports/INDEX.md
	./scripts/report.sh

deck: ## Buduje prezentacje: deck/slajdy.md -> reports/deck (HTML + PDF, 10 slajdow)
	./deck/build.sh

demo-ready: ## Przygotowanie pokazu: start stosu (z danymi demo) i ruch na panele (wymaga sudo)
	$(MAKE) --no-print-directory up
	./scripts/traffic.sh

checkpoint: ## Zero-prep dowod: doctor -> up -> testy (Go, e2e, Java) -> raport + adresy
	-@./scripts/doctor.sh
	$(MAKE) --no-print-directory up
	-$(MAKE) --no-print-directory test-unit
	-$(MAKE) --no-print-directory test
	-$(MAKE) --no-print-directory controlplane-test
	./scripts/report.sh
	@echo ""
	@echo "== adresy =="
	@$(MAKE) --no-print-directory urls

##@ Demo agenta

demo: ## Scenariusze demonstracyjne agenta (z seedem danych demo)
	-@./scripts/seed.sh
	@$(JWT_GUARD); GATEWAY_JWT="$$jwt" ./agent-demo/run.sh all

demo-full: ## Demo + scenariusze zaawansowane (PENDING dozwolone)
	-@./scripts/seed.sh
	@$(JWT_GUARD); GATEWAY_JWT="$$jwt" ./agent-demo/run.sh all
	./agent-demo/scenarios.sh

demo-strict: ## Jak demo-full, ale PENDING liczy sie jako FAIL
	-@./scripts/seed.sh
	@$(JWT_GUARD); GATEWAY_JWT="$$jwt" ./agent-demo/run.sh all
	./agent-demo/scenarios.sh --strict

##@ JWT i polityka

keys: ## Generuje lokalna pare kluczy JWT gatewaya (gateway/keys, gitignored)
	cd gateway && make keys
	@echo "UWAGA: gateway czyta jwt.pub tylko przy starcie. Po regeneracji kluczy zrob:"
	@echo "  sudo docker compose up -d --force-recreate gateway"

mint-build: ## Buduje gateway/bin/mint raz (token bez 'go run', dziala tez pod sudo)
	cd gateway && go build -o bin/mint ./cmd/mint
	@echo "zbudowano gateway/bin/mint"

prometheus-token: ## Zapisuje ADMIN_TOKEN do pliku dla Prometheusa (zgodny z .env; wola to make up)
	@tok=$$(sed -nE 's/^[[:space:]]*ADMIN_TOKEN=[[:space:]]*//p' .env 2>/dev/null | tail -1 | tr -d '"'); \
	tok="$${tok:-$${ADMIN_TOKEN:-local-dev-admin}}"; \
	printf '%s' "$$tok" > $(PROM_TOKEN_FILE); \
	chmod 644 $(PROM_TOKEN_FILE); \
	echo "  $(PROM_TOKEN_FILE) gotowy (zgodny z ADMIN_TOKEN)"

token: ## Wypisuje swiezy JWT i tylko jego (bez tego nie nadaje sie do TOK=$(make token))
	@./scripts/token.sh

new-signature: ## Demo dla jury: dodaje sygnature do feedu (PATTERN=, NAME=, ACTION=) i sprawdza, ze jest serwowana
	@PATTERN="$(PATTERN)" NAME="$(NAME)" ACTION="$(ACTION)" ./signatures-feed/push_new_signature.sh
	@echo "--- kontrola feedu ---"
	@curl -s -m 5 http://localhost:8085/signatures.json | python3 -c "import sys,json;d=json.load(sys.stdin);s=d['signatures'][-1];print('  sygnatur w feedzie:',len(d['signatures']),'| ostatnia:',s['id'],'/',s['pattern'])"
	@$(JWT_GUARD); \
	 literal="$$(python3 -c 'import sys; p=sys.argv[1].strip(); p=p[1:-1] if p.startswith("(") and p.endswith(")") else p; print(p.split("|")[0].replace(chr(92),"").strip())' "$(PATTERN)")"; \
	 echo "--- proba uzycia wzorca: $(PATTERN) ---"; \
	 code=$$(curl -s -o /dev/null -w '%{http_code}' -m 6 -X POST http://localhost:8080/v1/chat/completions \
	   -H 'Content-Type: application/json' -H "Authorization: Bearer $$jwt" \
	   -d "{\"model\":\"llama3.2:1b\",\"agent_id\":\"agent-zero-day\",\"messages\":[{\"role\":\"user\",\"content\":\"$$literal\"}]}"); \
	 echo "  HTTP $$code - gateway nie konsumuje jeszcze feedu, wiec 200 jest oczekiwane (403 po podlaczeniu sygnatur)"

db-tidy: ## Porzadkuje dane demo: czysci audyt i usuwa zdublowane rewizje polityki (wymaga sudo)
	./scripts/db-tidy.sh

db-dump: ## Kopia bazy audytu do backups/ (pg_dump, wymaga sudo; OUT=sciezka)
	./scripts/db-dump.sh $(OUT)

db-restore: ## Odtworzenie bazy z kopii: make db-restore FILE=backups/noorpointer-....dump (wymaga sudo)
	./scripts/db-restore.sh $(FILE)

token-file: ## Zapisuje swiezy JWT do pliku 0600 (domyslnie /tmp/noorpointer-e2e.jwt); env GATEWAY_JWT jest preferowany
	@f="$${TOKEN_FILE:-/tmp/noorpointer-e2e.jwt}"; umask 077; ./scripts/token.sh > "$$f"; \
	  echo "zapisano token do $$f (uprawnienia 0600)"; \
	  echo "preferowany sposob przekazania tokenu to zmienna srodowiskowa: TOK=\$$(make token)"; \
	  echo "uzycie:"; \
	  echo "  curl -s localhost:8080/v1/chat/completions -H \"Authorization: Bearer \$$(cat $$f)\" -H \"Content-Type: application/json\" -d '{\"model\":\"llama3.2:1b\",\"messages\":[{\"role\":\"user\",\"content\":\"test\"}]}'"

reload-policy: ## Wymusza natychmiastowy reload polityki w gatewayu (Bearer GATEWAY_TOKEN)
	@body=$$(mktemp); code=$$(curl -s -o "$$body" -w '%{http_code}' -X POST http://localhost:8080/admin/policy/reload \
	  -H "Authorization: Bearer $${GATEWAY_TOKEN:-local-dev-gateway}"); \
	echo "  HTTP $$code $$(cat "$$body")"; rm -f "$$body"; [ "$$code" = "200" ]

doctor: ## Pre-flight: narzedzia, klucze JWT, compose, token, wymuszanie auth (bez zmian w stacku)
	./scripts/doctor.sh

urls: ## Adresy uslug i dane logowania
	@echo "  dashboard     http://localhost:3000   (login: ADMIN_TOKEN = local-dev-admin)"
	@echo "  grafana       http://localhost:3001   (admin/admin)"
	@echo "  prometheus    http://localhost:9091/targets  oraz /alerts"
	@echo "  controlplane  http://localhost:8082/actuator/health"
	@echo "  semantic      http://localhost:8001/healthz , /readyz"
	@echo "  gateway       http://localhost:8080/healthz (reszta tras wymaga JWT: make token)"
	@echo "  feed sygnatur http://localhost:8085/signatures.json"
	@echo "  mock LLM      http://localhost:11434/healthz"

##@ Opcjonalny prawdziwy model (Ollama)

ollama-up: ## Prawdziwa Llama + Llama Guard przez Ollame, gateway i serwis semantyczny przelaczone na nia
	$(OLLAMA_COMPOSE) up -d --wait ollama
	$(OLLAMA_COMPOSE) exec ollama ollama pull llama3.2:1b
	$(OLLAMA_COMPOSE) exec ollama ollama pull llama-guard3:1b
	$(OLLAMA_COMPOSE) up -d gateway semantic-app
	@echo "gateway i content_safety -> realna Ollama. Testy/bench wymagajace echo: make ollama-down"

ollama-down: ## Powrot gatewaya i content_safety na mock-llm (deterministyczne testy i bench)
	$(COMPOSE) up -d --no-deps gateway semantic-app
	@echo "gateway i content_safety -> mock-llm"

up-real: ## Demo dla jury: pelny stos + prawdziwe modele (pyta przed pobraniem ~2,9 GB)
	@$(MAKE) --no-print-directory up
	@$(OLLAMA_COMPOSE) up -d --wait ollama
	@have="$$($(OLLAMA_COMPOSE) exec -T ollama ollama list 2>/dev/null | awk 'NR>1{print $$1}')"; \
	missing=""; \
	for m in llama3.2:1b llama-guard3:1b; do \
	  printf '%s\n' "$$have" | grep -qxF "$$m" || missing="$$missing $$m"; \
	done; \
	if [ -n "$$missing" ]; then \
	  echo "up-real: brak modeli:$$missing"; \
	  echo "  do pobrania ok. 2,9 GB (przy 0,7 MB/s to ponad godzina)."; \
	  if [ -z "$(ALLOW_DOWNLOAD)" ]; then \
	    echo "  swiadomie pobierz: make up-real ALLOW_DOWNLOAD=1"; \
	    echo "  (albo zostan na mocku: make up)"; \
	    exit 1; \
	  fi; \
	  echo "  ALLOW_DOWNLOAD=1 - pobieram brakujace modele."; \
	fi
	@$(MAKE) --no-print-directory ollama-up
	@echo ""
	@echo "up-real: stos na prawdziwych modelach (tryb demo)."
	@echo "  Testy e2e i bench zakladaja echo z mocka - przed nimi: make ollama-down"

##@ Praca nad modulami (dev, bez kontenera dla danego modulu)

postgres-up: ## Postgres dla aplikacji i czeka na gotowosc
	$(COMPOSE) up -d --wait postgres

postgres-test-up: postgres-up ## Osobna baza PostgreSQL dla testow Javy
	$(COMPOSE) exec -T postgres psql -U noor -d postgres -v ON_ERROR_STOP=1 < config/init-test-db.sql

controlplane-run: postgres-up ## Uruchamia Jave (REST/panel) na :8082
	cd controlplane && ./mvnw spring-boot:run

test-semantic: ## Testy modulu semantycznego w kontenerze z pytest (sudo; --build bierze kod z repo)
	@mkdir -p reports 2>/dev/null || true
	@log=reports/log-semantic-test.txt; \
	: > "$$log" 2>/dev/null || { log="$${TMPDIR:-/tmp}/noorpointer-log-semantic-test.txt"; echo "uwaga: nie moge pisac do reports/ - log: $$log"; }; \
	$(COMPOSE) --profile semantic run --rm --build semantic-tests > "$$log" 2>&1; rc=$$?; \
	grep -E "[0-9]+ (passed|failed)|^(FAILED|ERROR)|error" "$$log" | tail -18; \
	if grep -qiE 'permission denied.*docker|docker.*permission denied' "$$log"; then echo "  BLAD: brak dostepu do Dockera (docker.sock jest root:docker, a Ty nie jestes w grupie docker) - uruchom: sudo make test-semantic"; fi; \
	chown -R "$$(stat -c '%u:%g' .)" reports 2>/dev/null || true; \
	[ $$rc -eq 0 ] || echo "  szczegoly: $$log"; exit $$rc

controlplane-test: postgres-test-up ## Testy modulu Java w kontenerze (sudo; pelny log: reports/log-java-test.txt)
	@mkdir -p reports 2>/dev/null || true
	@log=reports/log-java-test.txt; \
	: > "$$log" 2>/dev/null || { log="$${TMPDIR:-/tmp}/noorpointer-log-java-test.txt"; echo "uwaga: nie moge pisac do reports/ - log: $$log"; }; \
	$(COMPOSE) --profile java run --rm --build controlplane-tests > "$$log" 2>&1; rc=$$?; \
	grep -E "Tests run:|BUILD (SUCCESS|FAILURE)|^\[ERROR\]" "$$log" || true; \
	if grep -qiE 'permission denied.*docker|docker.*permission denied' "$$log"; then echo "  BLAD: brak dostepu do Dockera (docker.sock jest root:docker) - uruchom: sudo make controlplane-test"; fi; \
	chown -R "$$(stat -c '%u:%g' .)" reports 2>/dev/null || true; \
	[ $$rc -eq 0 ] || echo "  szczegoly bledu: $$log"; exit $$rc

controlplane-build: postgres-test-up ## Weryfikacja Javy + budowa JAR (w kontenerze)
	$(COMPOSE) --profile java run --rm --build controlplane-tests mvn -B -ntp -f controlplane/pom.xml verify -Dfrontend.skip=true

dashboard-dev: ## React z hot reload na :5173 (API Javy musi dzialac na :8082)
	cd dashboard && npm ci --no-audit --no-fund && npm run dev

dashboard-test: ## Testy React i klientow API (bez uruchamiania backendow, Node.js 22.12+)
	cd dashboard && npm ci --no-audit --no-fund && npm test
