package main

import (
	"log"
	"os"

	"github.com/dslwa/NoorPointer/gateway/api"
	"github.com/golang-jwt/jwt/v5"
)

func main() {
	log.Fatal(run())
}

func run() error {
	pem, err := os.ReadFile(env("JWT_PUBLIC_KEY", "keys/jwt.pub"))
	if err != nil {
		return err
	}
	pubKey, err := jwt.ParseRSAPublicKeyFromPEM(pem)
	if err != nil {
		return err
	}

	server, err := api.NewServer(":"+env("PORT", "8080"), env("UPSTREAM_LLM_URL", "http://localhost:11434"), pubKey,
		env("CONTROLPLANE_URL", "http://localhost:8082"), env("GATEWAY_TOKEN", "local-dev-gateway"))
	if err != nil {
		return err
	}
	return server.Start()
}

func env(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
