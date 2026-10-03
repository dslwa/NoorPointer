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
        up dev-infra down restart build clean logs status \
        seed test test-unit test-rebuild bench bench-flood bench-budget \
        smoke verify verify-strict offline-check report checkpoint \
        demo demo-full demo-strict \
        keys mint-build token reload-policy doctor urls \
        ollama-up ollama-down \
        postgres-up postgres-test-up controlplane-run controlplane-test controlplane-build dashboard-dev

# --- pomoc -----------------------------------------------------------------------------------------
help: ## Lista komend pogrupowana w sekcje
	@awk 'BEGIN {FS = ":.*## "} /^##@/ {printf "\n\033[1m%s\033[0m\n", substr($$0, 5)} /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

##@ Stos

up: ## Pelny stos + seed danych demo; --remove-orphans sprzata kontenery po usunietych serwisach
	@test -f gateway/keys/jwt.pub || $(MAKE) --no-print-directory keys
	$(COMPOSE) up -d --build --remove-orphans
	-@./scripts/seed.sh

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
	@$(JWT_GUARD); $(COMPOSE) run --rm --build -e GATEWAY_JWT="$$jwt" tests

test-unit: ## Testy jednostkowe modulow (Go teraz; nie wymagaja dzialajacego stosu)
	cd gateway && go test ./...

test-rebuild: ## Przebudowuje obraz testow (po zmianie requirements.txt)
	$(COMPOSE) build --no-cache tests

bench: ## k6: baseline (narzut p95)
	@$(JWT_GUARD); $(K6) /benchmarks/benchmark_baseline.js

bench-flood: ## k6: zalew zlosliwych promptow
	@$(JWT_GUARD); $(K6) /benchmarks/benchmark_malicious_flood.js

bench-budget: ## k6: rownolegle zapytania jednego agenta (atomowosc budzetu)
	@$(JWT_GUARD); $(K6) /benchmarks/benchmark_budget_concurrency.js

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

checkpoint: ## Zero-prep dowod: doctor -> up -> test -> raport + adresy
	-@./scripts/doctor.sh
	$(MAKE) --no-print-directory up
	-$(MAKE) --no-print-directory test-unit
	-$(MAKE) --no-print-directory test
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

token: ## Wypisuje swiezy JWT dla gatewaya (AGENT=... TEAM=... TTL=...)
	./scripts/token.sh

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

controlplane-test: postgres-test-up ## Testy modulu Java na osobnej bazie
	cd controlplane && ./mvnw test

controlplane-build: postgres-test-up ## Weryfikacja Javy + budowa JAR
	cd controlplane && ./mvnw verify

dashboard-dev: ## React z hot reload na :5173 (API Javy musi dzialac na :8082)
	cd dashboard && npm ci --no-audit --no-fund && npm run dev
