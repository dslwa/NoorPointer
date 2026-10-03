package main

import (
	"fmt"
	"io"
	"log"
	"os"
	"time"

	"github.com/dslwa/NoorPointer/gateway/types"
	"github.com/golang-jwt/jwt/v5"
)

func main() {
	if err := run(os.Stdout); err != nil {
		log.Fatal(err)
	}
}

func run(w io.Writer) error {
	ttl, err := time.ParseDuration(env("TTL", "24h"))
	if err != nil {
		return err
	}
	pem, err := os.ReadFile(env("JWT_PRIVATE_KEY", "keys/jwt.key"))
	if err != nil {
		return err
	}
	key, err := jwt.ParseRSAPrivateKeyFromPEM(pem)
	if err != nil {
		return err
	}

	now := time.Now()
	claims := types.Claims{
		Team: env("TEAM", "sales"),
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   env("AGENT", "support-bot"),
			Issuer:    "noorpointer-cp",
			Audience:  jwt.ClaimStrings{"noorpointer-gateway"},
			IssuedAt:  jwt.NewNumericDate(now),
			ExpiresAt: jwt.NewNumericDate(now.Add(ttl)),
		},
	}

	token, err := jwt.NewWithClaims(jwt.SigningMethodRS256, claims).SignedString(key)
	if err != nil {
		return err
	}
	_, err = fmt.Fprintln(w, token)
	return err
}

func env(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
