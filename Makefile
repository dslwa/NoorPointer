.PHONY: help up dev-infra down restart logs status build test bench demo clean

help: ## Pokazuje dostępne komendy
	@echo "🛡️ NoorPointer Hackathon Commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

dev-infra: ## Uruchamia TYLKO bazy i telemetrię (Postgres, Redis, Ollama, Threat Feed, Prometheus, Grafana) dla pracy lokalnej
	docker compose up -d postgres redis ollama signatures-feed prometheus grafana

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
