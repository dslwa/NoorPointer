package main

import (
	"log"
	"os"

	"github.com/dslwa/NoorPointer/gateway/api"
	"github.com/golang-jwt/jwt/v5"
)

func main() {
	pem, err := os.ReadFile(env("JWT_PUBLIC_KEY", "keys/jwt.pub"))
	if err != nil {
		// env lets docker-compose configure the gateway, flags still win when passed.
		log.Fatal(err)
	}
	pubKey, err := jwt.ParseRSAPublicKeyFromPEM(pem)
	if err != nil {
		log.Fatal(err)
	}

	server, err := api.NewServer(":"+env("PORT", "8080"), env("UPSTREAM_LLM_URL", "http://localhost:11434"), pubKey)
	if err != nil {
		log.Fatal(err)
	}
	log.Fatal(server.Start())
}

func env(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
