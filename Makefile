# NoorPointer - infrastructure / DevOps entrypoint.
#
# Najkrotsza droga do dzialajacego stosu i dowodow:
#   sudo make up          pelny stos + seed danych demo (upstream: mock LLM, runtime offline)
#   make doctor           pre-flight: narzedzia, klucze, compose, token, wymuszanie auth
#   sudo make test        e2e (seed + raport HTML)
#   make verify           zero-prep: smoke + offline-check + scenariusze demo
#   sudo make checkpoint  wszystko powyzsze + reports/INDEX.md + lista adresow
#
# Konwencja: komendy Makefile, ktore wolaja docker, uruchamiaj przez `sudo make ...`
# (docker.sock jest root:docker). Skrypty czyste (curl) dzialaja bez sudo.
# Grupy widac w `make help` (sekcje ##@).

# --- narzedzia i zmienne wspolne -------------------------------------------------------------------
COMPOSE         ?= docker compose
COMPOSE_ALL      = $(COMPOSE) --profile tests --profile bench
OLLAMA_COMPOSE   = $(COMPOSE) -f docker-compose.yaml -f docker-compose.ollama.yaml

# Mintujemy JWT raz na recipe. Pusty token zamienia kazde wywolanie gatewaya w 401, a $(...)
# w Makefile cicho zwraca pusty string - dlatego twardo przerywamy.
JWT_GUARD = jwt="$$(./scripts/token.sh)"; [ -n "$$jwt" ] || { echo "BLAD: pusty JWT - uruchom: make keys && make mint-build"; exit 1; }
K6        = $(COMPOSE) run --rm -e GATEWAY_JWT="$$jwt" benchmarks run

.PHONY: help \
        up dev-infra down restart build clean logs status wait \
        seed test test-unit test-local test-rebuild bench bench-flood bench-budget traffic \
        smoke verify verify-strict offline-check report deck checkpoint \
        demo demo-full demo-strict \
        keys mint-build token token-file reload-policy new-signature db-tidy doctor urls \
        jury scan policy-edit policy-apply signature evidence stop \
        ollama-up ollama-down \
        postgres-up postgres-test-up controlplane-run controlplane-test controlplane-build dashboard-dev

# --- pomoc -----------------------------------------------------------------------------------------
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

stop: ## Zatrzymuje stos (dane i wolumeny zostaja, wracasz przez: make up)
	@$(MAKE) --no-print-directory down

##@ Stos

up: ## Pelny stos + seed danych demo; czeka na gotowosc (semantic laduje modele ~2 min)
	@test -f gateway/keys/jwt.pub || $(MAKE) --no-print-directory keys
	$(COMPOSE) up -d --build --remove-orphans
	@./scripts/wait-ready.sh
	-@./scripts/seed.sh

wait: ## Czeka, az wszystkie uslugi odpowiedza (WAIT_TIMEOUT=sekundy, domyslnie 180)
	./scripts/wait-ready.sh

dev-infra: ## Tylko bazy i telemetria (Postgres, Redis, mock LLM, feed, Prometheus, Grafana)
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

test: seed ## e2e (seed + raport HTML); --build, bo obraz testow wpieka kod testow
	@$(JWT_GUARD); $(COMPOSE) run --rm --build -e GATEWAY_JWT="$$jwt" tests; rc=$$?; \
	chown -R "$$(stat -c '%u:%g' .)" reports 2>/dev/null || true; exit $$rc

test-unit: ## Testy jednostkowe modulow (Go teraz; nie wymagaja dzialajacego stosu)
	cd gateway && go test ./...

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

bench: ## k6: baseline (narzut p95)
	@$(JWT_GUARD); $(K6) /benchmarks/benchmark_baseline.js

bench-flood: ## k6: zalew zlosliwych promptow
	@$(JWT_GUARD); $(K6) /benchmarks/benchmark_malicious_flood.js

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

ollama-up: ## Prawdziwa Llama przez Ollame + przelaczenie gatewaya na nia
	$(OLLAMA_COMPOSE) up -d --wait ollama
	$(OLLAMA_COMPOSE) exec ollama ollama pull llama3.2:1b
	$(OLLAMA_COMPOSE) up -d gateway
	@echo "gateway -> realna Ollama. Testy/bench wymagajace echo: make ollama-down"

ollama-down: ## Powrot gatewaya na mock-llm (deterministyczne testy i bench)
	$(COMPOSE) up -d --no-deps gateway
	@echo "gateway -> mock-llm"

##@ Praca nad modulami (dev, bez kontenera dla danego modulu)

postgres-up: ## Postgres dla aplikacji i czeka na gotowosc
	$(COMPOSE) up -d --wait postgres

postgres-test-up: postgres-up ## Osobna baza PostgreSQL dla testow Javy
	$(COMPOSE) exec -T postgres psql -U noor -d postgres -v ON_ERROR_STOP=1 < config/init-test-db.sql

controlplane-run: postgres-up ## Uruchamia Jave (REST/panel) na :8082
	cd controlplane && ./mvnw spring-boot:run

controlplane-test: postgres-test-up ## Testy modulu Java w kontenerze (bez Javy na hoscie)
	$(COMPOSE) --profile java run --rm --build controlplane-tests

controlplane-build: postgres-test-up ## Weryfikacja Javy + budowa JAR (w kontenerze)
	$(COMPOSE) --profile java run --rm --build controlplane-tests mvn -B -ntp -f controlplane/pom.xml verify -Dfrontend.skip=true

dashboard-dev: ## React z hot reload na :5173 (API Javy musi dzialac na :8082)
	cd dashboard && npm ci --no-audit --no-fund && npm run dev
