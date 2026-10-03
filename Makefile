.PHONY: help up dev-infra down restart logs status build test bench demo clean postgres-up postgres-test-up controlplane-run controlplane-test controlplane-build smoke bench-flood bench-budget offline-check report

help: ## Pokazuje dostępne komendy
	@echo "🛡️ NoorPointer Hackathon Commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

dev-infra: ## Uruchamia TYLKO bazy i telemetrię (Postgres, Redis, mock LLM, Threat Feed, Prometheus, Grafana) dla pracy lokalnej
	docker compose up -d postgres redis mock-llm signatures-feed prometheus grafana

up: ## Uruchamia WSZYSTKIE serwisy w kontenerach (pełny stos demonstracyjny dla Jury)
	docker compose up -d --build

down: ## Zatrzymuje całe środowisko
	docker compose down

build: ## Buduje obrazy dla wszystkich serwisów
	docker compose build

restart: down up ## Restartuje całe środowisko

logs: ## Wyświetla zagregowane logi ze wszystkich kontenerów
	docker compose logs -f

status: ## Pokazuje stan kontenerów i ich porty
	docker compose ps

test: ## Uruchamia automatyczny pakiet testów e2e (z generowaniem raportu HTML)
	docker compose run --rm tests

bench: ## Uruchamia benchmarki wydajnościowe k6 (narzut p95)
	docker compose run --rm benchmarks run /benchmarks/benchmark_baseline.js

demo: ## Uruchamia scenariusze demonstracyjne agenta
	./agent-demo/run.sh all

clean: ## Czyści wolumeny i nieużywane obrazy Dockera
	docker compose down -v --remove-orphans

postgres-up: ## Uruchamia PostgreSQL dla aplikacji i czeka na gotowość
	docker compose up -d --wait postgres

postgres-test-up: postgres-up ## Przygotowuje osobną bazę PostgreSQL dla testów Javy
	docker compose exec -T postgres psql -U noor -d postgres -v ON_ERROR_STOP=1 < config/init-test-db.sql

controlplane-run: postgres-up ## Uruchamia PostgreSQL, a następnie Javę i dashboard lokalnie na :8082
	cd controlplane && ./mvnw spring-boot:run

controlplane-test: postgres-test-up ## Uruchamia testy modułu Java na osobnej bazie PostgreSQL
	cd controlplane && ./mvnw test

controlplane-build: postgres-test-up ## Sprawdza Javę na PostgreSQL i buduje JAR z frontendem z dashboard/
	cd controlplane && ./mvnw verify

smoke: ## Sprawdza spięcie całego stosu (health + proxy + auth controlplane)
	./scripts/smoke.sh

bench-flood: ## k6: zalew złośliwych promptów (fast-block)
	docker compose run --rm benchmarks run /benchmarks/benchmark_malicious_flood.js

bench-budget: ## k6: równoległe zapytania jednego agenta (atomowość budżetu)
	docker compose run --rm benchmarks run /benchmarks/benchmark_budget_concurrency.js

offline-check: ## Lint: brak instalacji/pobierania w runtime (finalny stage obrazów)
	./scripts/offline-check.sh

report: ## Zbiera dowody dla jury do reports/INDEX.md
	./scripts/report.sh
