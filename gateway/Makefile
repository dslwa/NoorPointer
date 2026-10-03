.PHONY: build run test keys token

build:
	@go build -o bin/gateway ./cmd

run: build
	@./bin/gateway

test:
	@go test -race -v ./...

keys:
	@mkdir -p keys
	@openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out keys/jwt.key
	@openssl rsa -in keys/jwt.key -pubout -out keys/jwt.pub

token:
	@go run ./cmd/mint
