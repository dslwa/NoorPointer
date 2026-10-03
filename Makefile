.PHONY: help up dev-infra down restart logs status build test test-rebuild bench demo clean postgres-up postgres-test-up controlplane-run controlplane-test controlplane-build dashboard-dev smoke bench-flood bench-budget offline-check report demo-full demo-strict verify verify-strict keys token doctor seed urls checkpoint ollama-up ollama-down mint-build

help: ## Pokazuje dostępne komendy
	@echo "🛡️ NoorPointer Hackathon Commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

dev-infra: ## Uruchamia TYLKO bazy i telemetrię (Postgres, Redis, mock LLM, Threat Feed, Prometheus, Grafana) dla pracy lokalnej
	docker compose up -d postgres redis mock-llm signatures-feed prometheus grafana

up: ## Uruchamia WSZYSTKIE serwisy w kontenerach (pełny stos demonstracyjny dla Jury)
	@test -f gateway/keys/jwt.pub || $(MAKE) keys
	docker compose up -d --build
	-@./scripts/seed.sh

down: ## Zatrzymuje całe środowisko
	docker compose down

build: ## Buduje obrazy dla wszystkich serwisów
	docker compose build

restart: down up ## Restartuje całe środowisko

logs: ## Wyświetla zagregowane logi ze wszystkich kontenerów
	docker compose logs -f

status: ## Pokazuje stan kontenerów i ich porty
	docker compose ps

seed: ## Wypełnia bazę audytu danymi demo (wymagane dla eksportu CEF)
	./scripts/seed.sh

test: seed ## Uruchamia e2e (seed + raport HTML); --build, bo obraz testow wpieka kod testow
	@jwt="$$(./scripts/token.sh)"; [ -n "$$jwt" ] || { echo "BLAD: pusty JWT - uruchom: make keys && make mint-build"; exit 1; }; \
	docker compose run --rm --build -e GATEWAY_JWT="$$jwt" tests

test-rebuild: ## Przebudowuje obraz testow (po zmianie requirements.txt)
	docker compose build --no-cache tests

bench: ## Uruchamia benchmarki wydajnościowe k6 (narzut p95)
	@jwt="$$(./scripts/token.sh)"; [ -n "$$jwt" ] || { echo "BLAD: pusty JWT - uruchom: make keys && make mint-build"; exit 1; }; \
	docker compose run --rm -e GATEWAY_JWT="$$jwt" benchmarks run /benchmarks/benchmark_baseline.js

demo: ## Uruchamia scenariusze demonstracyjne agenta (z seedem danych demo)
	-@./scripts/seed.sh
	./scripts/run-with-jwt.sh ./agent-demo/run.sh all

clean: ## Czyści wolumeny i nieużywane obrazy Dockera
	docker compose down -v --remove-orphans

postgres-up: ## Uruchamia PostgreSQL dla aplikacji i czeka na gotowość
	docker compose up -d --wait postgres

postgres-test-up: postgres-up ## Przygotowuje osobną bazę PostgreSQL dla testów Javy
	docker compose exec -T postgres psql -U noor -d postgres -v ON_ERROR_STOP=1 < config/init-test-db.sql

controlplane-run: postgres-up ## Uruchamia PostgreSQL, buduje React i uruchamia Javę z panelem na :8082
	cd controlplane && ./mvnw spring-boot:run

controlplane-test: postgres-test-up ## Uruchamia testy modułu Java na osobnej bazie PostgreSQL
	cd controlplane && ./mvnw test

controlplane-build: postgres-test-up ## Sprawdza Javę na PostgreSQL i buduje JAR z panelem React
	cd controlplane && ./mvnw verify

dashboard-dev: ## Uruchamia React z hot reload na :5173 (API Javy musi działać na :8082)
	cd dashboard && npm ci --no-audit --no-fund && npm run dev

smoke: ## Sprawdza spięcie całego stosu (health + proxy + auth controlplane), zapisuje reports/smoke.txt
	@mkdir -p reports
	./scripts/smoke.sh | tee reports/smoke.txt

bench-flood: ## k6: zalew złośliwych promptów (fast-block)
	@jwt="$$(./scripts/token.sh)"; [ -n "$$jwt" ] || { echo "BLAD: pusty JWT - uruchom: make keys && make mint-build"; exit 1; }; \
	docker compose run --rm -e GATEWAY_JWT="$$jwt" benchmarks run /benchmarks/benchmark_malicious_flood.js

bench-budget: ## k6: równoległe zapytania jednego agenta (atomowość budżetu)
	@jwt="$$(./scripts/token.sh)"; [ -n "$$jwt" ] || { echo "BLAD: pusty JWT - uruchom: make keys && make mint-build"; exit 1; }; \
	docker compose run --rm -e GATEWAY_JWT="$$jwt" benchmarks run /benchmarks/benchmark_budget_concurrency.js

offline-check: ## Lint: brak instalacji/pobierania w runtime (finalny stage obrazów)
	./scripts/offline-check.sh

report: ## Zbiera dowody dla jury do reports/INDEX.md
	./scripts/report.sh

demo-full: ## Pełne demo: seed + run.sh (5 scenariuszy) + scenariusze zaawansowane (PENDING dozwolone)
	-@./scripts/seed.sh
	./scripts/run-with-jwt.sh ./agent-demo/run.sh all
	./agent-demo/scenarios.sh

demo-strict: ## Jak demo-full, ale PENDING (gateway bez guardraili) liczy się jako FAIL
	-@./scripts/seed.sh
	./scripts/run-with-jwt.sh ./agent-demo/run.sh all
	./agent-demo/scenarios.sh --strict

verify: ## Zero-prep: smoke + offline-check + scenariusze demo (PENDING dozwolone)
	./scripts/smoke.sh
	./scripts/offline-check.sh
	./agent-demo/scenarios.sh

verify-strict: ## Jak verify, ale PENDING liczy się jako FAIL (po guardrailach gatewaya)
	./scripts/smoke.sh
	./scripts/offline-check.sh
	./agent-demo/scenarios.sh --strict

keys: ## Generuje lokalną parę kluczy JWT gatewaya (gateway/keys, gitignored)
	cd gateway && make keys
	@echo "UWAGA: gateway czyta jwt.pub tylko przy starcie. Po regeneracji kluczy zrob:"
	@echo "  sudo docker compose up -d --force-recreate gateway"

mint-build: ## Buduje gateway/bin/mint raz, zeby token nie wymagal 'go run' (dziala tez pod sudo)
	cd gateway && go build -o bin/mint ./cmd/mint
	@echo "zbudowano gateway/bin/mint"

token: ## Wypisuje świeży JWT dla gatewaya (AGENT=... TEAM=... TTL=...)
	./scripts/token.sh

doctor: ## Pre-flight: klucze JWT, compose, token, wymuszanie auth (bez zmian w stacku)
	./scripts/doctor.sh

urls: ## Wypisuje adresy usług i dane logowania
	@echo "  dashboard     http://localhost:3000   (login: ADMIN_TOKEN = local-dev-admin)"
	@echo "  grafana       http://localhost:3001   (admin/admin, anonimowo wlaczony)"
	@echo "  prometheus    http://localhost:9091/targets  oraz /alerts"
	@echo "  controlplane  http://localhost:8082/actuator/health"
	@echo "  semantic      http://localhost:8001/healthz , /readyz"
	@echo "  gateway       http://localhost:8080/healthz (reszta tras wymaga JWT: make token)"
	@echo "  feed sygnatur http://localhost:8085/signatures.json"
	@echo "  mock LLM      http://localhost:11434/healthz"

checkpoint: ## Zero-prep dowód na checkpoint: doctor -> up -> seed -> test -> raport + URL-e
	-@./scripts/doctor.sh
	$(MAKE) up
	-$(MAKE) test
	./scripts/report.sh
	@echo ""
	@echo "== checklista =="
	@$(MAKE) --no-print-directory urls

OLLAMA_COMPOSE = docker compose -f docker-compose.yaml -f docker-compose.ollama.yaml

ollama-up: ## Opcjonalnie: prawdziwa Llama przez Ollame (overlay), potem przelaczenie gatewaya
	$(OLLAMA_COMPOSE) up -d --wait ollama
	$(OLLAMA_COMPOSE) exec ollama ollama pull llama3.2:1b
	$(OLLAMA_COMPOSE) up -d gateway
	@echo "gateway -> realna Ollama. Testy/bench wymagajace echo: make ollama-down"

ollama-down: ## Powrot gatewaya na mock-llm (deterministyczne testy/bench)
	docker compose up -d --no-deps gateway
	@echo "gateway -> mock-llm"
