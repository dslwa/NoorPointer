package api

import (
	"bytes"
	"crypto/rand"
	"crypto/rsa"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/dslwa/NoorPointer/gateway/config"
	"github.com/dslwa/NoorPointer/gateway/types"
	"github.com/golang-jwt/jwt/v5"
)

func newKey(t *testing.T) *rsa.PrivateKey {
	t.Helper()
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	return key
}

func validClaims() types.Claims {
	now := time.Now()
	return types.Claims{
		Team: "sales",
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   "support-bot",
			Issuer:    "noorpointer-cp",
			Audience:  jwt.ClaimStrings{"noorpointer-gateway"},
			IssuedAt:  jwt.NewNumericDate(now),
			ExpiresAt: jwt.NewNumericDate(now.Add(time.Hour)),
		},
	}
}

func sign(t *testing.T, method jwt.SigningMethod, claims types.Claims, key any) string {
	t.Helper()
	tok, err := jwt.NewWithClaims(method, claims).SignedString(key)
	if err != nil {
		t.Fatal(err)
	}
	return tok
}

// newTestServer returns a gateway with a balanced-like enforce policy
// (mock-llm allowed, secrets blocked, PII redacted),
// in front of a fake upstream that records the last request and its body.
func newTestServer(t *testing.T, pub *rsa.PublicKey) (*Server, *http.Request) {
	t.Helper()
	got := &http.Request{}
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		*got = *r.Clone(r.Context())
		got.Body = io.NopCloser(bytes.NewReader(body))
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(upstream.Close)

	s, err := NewServer(":0", upstream.URL, pub, "http://unused", "test-token")
	if err != nil {
		t.Fatal(err)
	}
	s.policy.Store(&config.Policy{
		Version:  1,
		Defaults: config.Defaults{Mode: "enforce"},
		Models:   config.Models{Allowed: []string{"mock-llm"}},
		Controls: config.Controls{
			Secrets: &config.Control{Enabled: true, Action: "block"},
			PIIRegex: &config.PatternControl{
				Control: config.Control{Enabled: true, Action: "redact"},
				Types:   []string{"email", "pesel", "iban", "card", "phone"},
			},
		},
	})
	return s, got
}

func do(h http.Handler, method, path, auth string) *httptest.ResponseRecorder {
	return doBody(h, method, path, auth, "")
}

func doBody(h http.Handler, method, path, auth, body string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(method, path, strings.NewReader(body))
	if auth != "" {
		req.Header.Set("Authorization", auth)
	}
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	return rec
}

func TestNewServerInvalidUpstream(t *testing.T) {
	for _, u := range []string{"", "localhost:11434", "://bad", "http://"} {
		if _, err := NewServer(":0", u, nil, "", "t"); err == nil {
			t.Errorf("upstream %q: expected error", u)
		}
	}
}

func TestHealthzNoAuth(t *testing.T) {
	s, _ := newTestServer(t, &newKey(t).PublicKey)
	if rec := do(s.routes(), http.MethodGet, "/healthz", ""); rec.Code != http.StatusOK {
		t.Fatalf("got %d, want 200", rec.Code)
	}
}

func TestValidTokenIsProxied(t *testing.T) {
	key := newKey(t)
	s, got := newTestServer(t, &key.PublicKey)

	rec := doBody(s.routes(), http.MethodPost, "/v1/chat/completions", "Bearer "+sign(t, jwt.SigningMethodRS256, validClaims(), key), `{"model":"mock-llm"}`)
	if rec.Code != http.StatusOK {
		t.Fatalf("got %d, want 200: %s", rec.Code, rec.Body)
	}
	if got.URL.Path != "/v1/chat/completions" {
		t.Errorf("upstream path %q, want /v1/chat/completions", got.URL.Path)
	}
	if a := got.Header.Get("Authorization"); a != "" {
		t.Errorf("Authorization leaked to upstream: %q", a)
	}
}

func TestRejectedTokens(t *testing.T) {
	key := newKey(t)
	otherKey := newKey(t)
	s, got := newTestServer(t, &key.PublicKey)
	h := s.routes()

	expired := validClaims()
	expired.ExpiresAt = jwt.NewNumericDate(time.Now().Add(-time.Hour))
	noExp := validClaims()
	noExp.ExpiresAt = nil
	wrongIss := validClaims()
	wrongIss.Issuer = "evil"
	wrongAud := validClaims()
	wrongAud.Audience = jwt.ClaimStrings{"other-service"}

	tests := []struct {
		name string
		auth string
	}{
		{"missing header", ""},
		{"wrong scheme", "Basic dXNlcjpwYXNz"},
		{"colon prefix", "Bearer: " + sign(t, jwt.SigningMethodRS256, validClaims(), key)},
		{"garbage", "Bearer garbage"},
		{"expired", "Bearer " + sign(t, jwt.SigningMethodRS256, expired, key)},
		{"no exp", "Bearer " + sign(t, jwt.SigningMethodRS256, noExp, key)},
		{"wrong issuer", "Bearer " + sign(t, jwt.SigningMethodRS256, wrongIss, key)},
		{"wrong audience", "Bearer " + sign(t, jwt.SigningMethodRS256, wrongAud, key)},
		{"signed by other key", "Bearer " + sign(t, jwt.SigningMethodRS256, validClaims(), otherKey)},
		{"alg none", "Bearer " + sign(t, jwt.SigningMethodNone, validClaims(), jwt.UnsafeAllowNoneSignatureType)},
		{"alg HS256", "Bearer " + sign(t, jwt.SigningMethodHS256, validClaims(), []byte("secret"))},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			*got = http.Request{}
			rec := do(h, http.MethodPost, "/v1/chat/completions", tt.auth)
			if rec.Code != http.StatusUnauthorized {
				t.Fatalf("got %d, want 401", rec.Code)
			}
			if got.URL != nil {
				t.Fatal("request reached upstream")
			}
		})
	}
}

func TestNewServerEmptyGatewayToken(t *testing.T) {
	if _, err := NewServer(":0", "http://upstream", nil, "http://cp", ""); err == nil {
		t.Fatal("expected error")
	}
}

func TestStartListenError(t *testing.T) {
	s, err := NewServer(":-1", "http://upstream", nil, "http://127.0.0.1:1", "test-token")
	if err != nil {
		t.Fatal(err)
	}
	if err := s.Start(); err == nil {
		t.Fatal("expected listen error")
	}
}

func TestMakeHTTPHandleFuncError(t *testing.T) {
	h := makeHTTPHandleFunc(func(http.ResponseWriter, *http.Request) error {
		return errors.New("boom")
	})
	rec := do(h, http.MethodGet, "/", "")
	if rec.Code != http.StatusBadRequest || !strings.Contains(rec.Body.String(), "boom") {
		t.Fatalf("got %d %s", rec.Code, rec.Body)
	}
}
