.PHONY: build run test

build:
	@go build -o bin/gateway ./cmd

run: build
	@./bin/gateway

test:
	@go test -v ./...
