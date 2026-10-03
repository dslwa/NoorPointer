package main

import (
	"bytes"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/pem"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/dslwa/NoorPointer/gateway/types"
	"github.com/golang-jwt/jwt/v5"
)

func writeKey(t *testing.T) (string, *rsa.PrivateKey) {
	t.Helper()
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	der, err := x509.MarshalPKCS8PrivateKey(key)
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(t.TempDir(), "jwt.key")
	if err := os.WriteFile(path, pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: der}), 0o600); err != nil {
		t.Fatal(err)
	}
	return path, key
}

func TestRunMintsValidToken(t *testing.T) {
	path, key := writeKey(t)
	t.Setenv("JWT_PRIVATE_KEY", path)
	t.Setenv("AGENT", "agent-x")
	t.Setenv("TEAM", "finance")
	t.Setenv("TTL", "1h")

	var out bytes.Buffer
	if err := run(&out); err != nil {
		t.Fatal(err)
	}

	claims := &types.Claims{}
	_, err := jwt.ParseWithClaims(strings.TrimSpace(out.String()), claims,
		func(*jwt.Token) (any, error) { return &key.PublicKey, nil },
		jwt.WithValidMethods([]string{"RS256"}),
		jwt.WithIssuer("noorpointer-cp"),
		jwt.WithAudience("noorpointer-gateway"),
	)
	if err != nil {
		t.Fatal(err)
	}
	if claims.Subject != "agent-x" || claims.Team != "finance" {
		t.Errorf("claims sub=%q team=%q", claims.Subject, claims.Team)
	}
	if ttl := claims.ExpiresAt.Sub(claims.IssuedAt.Time); ttl != time.Hour {
		t.Errorf("ttl %v, want 1h", ttl)
	}
}

func TestRunErrors(t *testing.T) {
	path, _ := writeKey(t)
	notPEM := filepath.Join(t.TempDir(), "bad.key")
	if err := os.WriteFile(notPEM, []byte("not a key"), 0o600); err != nil {
		t.Fatal(err)
	}

	tests := []struct {
		name, ttl, keyPath string
	}{
		{"bad ttl", "forever", path},
		{"missing key", "1h", filepath.Join(t.TempDir(), "missing.key")},
		{"not pem", "1h", notPEM},
		{"key too weak to sign", "1h", "testdata/weak512.pem"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Setenv("TTL", tt.ttl)
			t.Setenv("JWT_PRIVATE_KEY", tt.keyPath)
			if err := run(&bytes.Buffer{}); err == nil {
				t.Fatal("expected error")
			}
		})
	}
}

func TestEnvFallback(t *testing.T) {
	t.Setenv("MINT_TEST_UNSET", "")
	if got := env("MINT_TEST_UNSET", "fallback"); got != "fallback" {
		t.Errorf("got %q", got)
	}
}
