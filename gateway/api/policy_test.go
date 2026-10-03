package api

import (
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync/atomic"
	"testing"

	"github.com/golang-jwt/jwt/v5"
)

func TestRefreshPolicyETag(t *testing.T) {
	doc, err := os.ReadFile("../../controlplane/src/main/resources/profiles/balanced.json")
	if err != nil {
		t.Fatal(err)
	}
	var full, notModified atomic.Int32
	cp := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer test-token" {
			w.WriteHeader(http.StatusUnauthorized)
			return
		}
		if r.Header.Get("If-None-Match") == `"v1"` {
			notModified.Add(1)
			w.WriteHeader(http.StatusNotModified)
			return
		}
		full.Add(1)
		w.Header().Set("ETag", `"v1"`)
		w.Write(doc)
	}))
	defer cp.Close()

	s, err := NewServer(":0", "http://upstream", nil, cp.URL, "test-token")
	if err != nil {
		t.Fatal(err)
	}
	for range 3 {
		if err := s.refreshPolicy(t.Context()); err != nil {
			t.Fatal(err)
		}
	}
	if full.Load() != 1 || notModified.Load() != 2 {
		t.Fatalf("full=%d notModified=%d, want 1 and 2", full.Load(), notModified.Load())
	}
	if s.policy.Load() == nil {
		t.Fatal("policy not stored")
	}
}

func TestPolicyReloadEndpoint(t *testing.T) {
	cp := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte(`{"version":7,"defaults":{"mode":"enforce","semantic_timeout_ms":300,"on_semantic_timeout":"fail_closed"},"models":{"allowed":["mock-llm"]},"controls":{}}`))
	}))
	defer cp.Close()
	s, _ := NewServer(":0", "http://upstream", nil, cp.URL, "test-token")
	h := s.routes()

	if rec := do(h, http.MethodPost, "/admin/policy/reload", ""); rec.Code != http.StatusUnauthorized {
		t.Fatalf("no token: got %d, want 401", rec.Code)
	}
	rec := do(h, http.MethodPost, "/admin/policy/reload", "Bearer test-token")
	if rec.Code != http.StatusOK || !strings.Contains(rec.Body.String(), `"reloaded"`) {
		t.Fatalf("got %d %s", rec.Code, rec.Body)
	}
	if s.policyVersion() != 7 {
		t.Fatalf("version %d, want 7", s.policyVersion())
	}
}

func TestNoPolicyIs503(t *testing.T) {
	key := newKey(t)
	s, _ := NewServer(":0", "http://upstream", &key.PublicKey, "http://unused", "test-token")
	rec := do(s.routes(), http.MethodPost, "/v1/chat/completions", "Bearer "+sign(t, jwt.SigningMethodRS256, validClaims(), key))
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("got %d, want 503", rec.Code)
	}
}
