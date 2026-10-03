package main

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/pem"
	"os"
	"path/filepath"
	"testing"
)

func writePubKey(t *testing.T) string {
	t.Helper()
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	der, err := x509.MarshalPKIXPublicKey(&key.PublicKey)
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(t.TempDir(), "jwt.pub")
	if err := os.WriteFile(path, pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: der}), 0o600); err != nil {
		t.Fatal(err)
	}
	return path
}

func TestRunErrors(t *testing.T) {
	pub := writePubKey(t)
	notPEM := filepath.Join(t.TempDir(), "bad.pub")
	if err := os.WriteFile(notPEM, []byte("not a key"), 0o600); err != nil {
		t.Fatal(err)
	}

	tests := []struct {
		name, keyPath, upstream, port string
	}{
		{"missing key", filepath.Join(t.TempDir(), "missing.pub"), "http://localhost:11434", "0"},
		{"not pem", notPEM, "http://localhost:11434", "0"},
		{"bad upstream", pub, "localhost:11434", "0"},
		{"listen fails", pub, "http://localhost:11434", "-1"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Setenv("JWT_PUBLIC_KEY", tt.keyPath)
			t.Setenv("UPSTREAM_LLM_URL", tt.upstream)
			t.Setenv("PORT", tt.port)
			t.Setenv("CONTROLPLANE_URL", "http://127.0.0.1:1")
			if err := run(); err == nil {
				t.Fatal("expected error")
			}
		})
	}
}
