package api

import (
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"testing/iotest"

	"github.com/dslwa/NoorPointer/gateway/config"
	"github.com/golang-jwt/jwt/v5"
)

func TestWithPolicy(t *testing.T) {
	key := newKey(t)
	auth := "Bearer " + sign(t, jwt.SigningMethodRS256, validClaims(), key)

	tests := []struct {
		name       string
		mode       string
		method     string
		path       string
		body       string
		wantStatus int
		wantCode   string
		wantProxy  bool
	}{
		{"allowed model", "enforce", http.MethodPost, "/v1/chat/completions", `{"model":"mock-llm"}`, 200, "", true},
		{"model not allowed", "enforce", http.MethodPost, "/v1/chat/completions", `{"model":"gpt-4o"}`, 403, "MODEL_NOT_ALLOWED", false},
		{"missing model", "enforce", http.MethodPost, "/v1/chat/completions", `{}`, 403, "MODEL_NOT_ALLOWED", false},
		{"monitor mode only logs", "monitor", http.MethodPost, "/v1/chat/completions", `{"model":"gpt-4o"}`, 200, "", true},
		{"invalid json", "enforce", http.MethodPost, "/v1/chat/completions", `{"model":`, 400, "", false},
		{"body too large", "enforce", http.MethodPost, "/v1/chat/completions", `{"model":"` + strings.Repeat("a", maxBodyBytes) + `"}`, 413, "", false},
		{"get without body", "enforce", http.MethodGet, "/v1/models", "", 200, "", true},
		{"native ollama api", "enforce", http.MethodPost, "/api/chat", `{"model":"mock-llm"}`, 404, "", false},
		{"legacy completions skip semantic checks", "enforce", http.MethodPost, "/v1/completions", `{"model":"mock-llm","prompt":"x"}`, 404, "", false},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			s, got := newTestServer(t, &key.PublicKey)
			p := *s.policy.Load()
			p.Defaults.Mode = tt.mode
			s.policy.Store(&p)

			rec := doBody(s.routes(), tt.method, tt.path, auth, tt.body)
			if rec.Code != tt.wantStatus {
				t.Fatalf("got %d, want %d: %s", rec.Code, tt.wantStatus, rec.Body)
			}
			if tt.wantCode != "" && !strings.Contains(rec.Body.String(), `"code":"`+tt.wantCode+`"`) {
				t.Errorf("body %s missing code %s", rec.Body, tt.wantCode)
			}
			if reached := got.URL != nil; reached != tt.wantProxy {
				t.Fatalf("upstream reached=%v, want %v", reached, tt.wantProxy)
			}
			if tt.wantProxy && tt.body != "" {
				if b, _ := io.ReadAll(got.Body); string(b) != tt.body {
					t.Errorf("upstream body %q, want %q", b, tt.body)
				}
			}
		})
	}
}

// The upstream always receives the re-encoded document the gateway
// checked (sorted keys), never the raw client bytes.
func TestWithPolicyContentScan(t *testing.T) {
	key := newKey(t)
	auth := "Bearer " + sign(t, jwt.SigningMethodRS256, validClaims(), key)
	// chat builds a body in canonical form (sorted keys), which is also
	// exactly what the gateway forwards upstream.
	chat := func(content string) string {
		return `{"messages":[{"content":"` + content + `","role":"user"}],"model":"mock-llm"}`
	}

	tests := []struct {
		name         string
		mutate       func(*config.Policy)
		body         string
		wantStatus   int
		wantCode     string
		wantUpstream string
	}{
		{
			name: "clean prompt untouched", body: chat("What is the capital of Poland?"),
			wantStatus: 200, wantUpstream: chat("What is the capital of Poland?"),
		},
		{
			name: "secret blocked", body: chat("my token ghp_123456789012345678901234567890123456"),
			wantStatus: 403, wantCode: "SECRET_LEAKAGE_DETECTED",
		},
		{
			name: "pesel redacted", body: chat("My PESEL is 95081212345."),
			wantStatus:   200,
			wantUpstream: `{"messages":[{"content":"My PESEL is [REDACTED:pesel].","role":"user"}],"model":"mock-llm"}`,
		},
		{
			name:         "content parts redacted",
			body:         `{"model":"mock-llm","messages":[{"role":"user","content":[{"type":"text","text":"mail jan@example.com"}]}]}`,
			wantStatus:   200,
			wantUpstream: `{"messages":[{"content":[{"text":"mail [REDACTED:email]","type":"text"}],"role":"user"}],"model":"mock-llm"}`,
		},
		{
			name:   "pii block action",
			mutate: func(p *config.Policy) { p.Controls.PIIRegex.Action = "block" },
			body:   chat("My PESEL is 95081212345."), wantStatus: 403, wantCode: "PII_DETECTED",
		},
		{
			name:   "secrets disabled",
			mutate: func(p *config.Policy) { p.Controls.Secrets.Enabled = false },
			body:   chat("ghp_123456789012345678901234567890123456"), wantStatus: 200,
			wantUpstream: chat("ghp_123456789012345678901234567890123456"),
		},
		{
			name:   "global monitor neither blocks nor redacts",
			mutate: func(p *config.Policy) { p.Defaults.Mode = "monitor" },
			body:   chat("ghp_123456789012345678901234567890123456 and 95081212345"), wantStatus: 200,
			wantUpstream: chat("ghp_123456789012345678901234567890123456 and 95081212345"),
		},
		{
			name:   "monitor action only logs",
			mutate: func(p *config.Policy) { p.Controls.PIIRegex.Action = "monitor" },
			body:   chat("95081212345"), wantStatus: 200, wantUpstream: chat("95081212345"),
		},
		{
			name: "non-object json", body: `["model"]`, wantStatus: 400,
		},
		{
			name:       "duplicate keys forward what was checked",
			body:       `{"model":"mock-llm","messages":[{"role":"user","content":"95081212345"}],"messages":[{"role":"user","content":"hi"}]}`,
			wantStatus: 200, wantUpstream: chat("hi"),
		},
		{
			name: "html characters kept as is", body: chat("a < b && c > d"),
			wantStatus: 200, wantUpstream: chat("a < b && c > d"),
		},
		{
			name: "secret behind zero-width space", body: chat("ghp_1234567890123456​78901234567890123456"),
			wantStatus: 403, wantCode: "SECRET_LEAKAGE_DETECTED",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			s, got := newTestServer(t, &key.PublicKey)
			if tt.mutate != nil {
				p := *s.policy.Load()
				pii, sec := *p.Controls.PIIRegex, *p.Controls.Secrets
				p.Controls.PIIRegex, p.Controls.Secrets = &pii, &sec
				tt.mutate(&p)
				s.policy.Store(&p)
			}

			rec := doBody(s.routes(), http.MethodPost, "/v1/chat/completions", auth, tt.body)
			if rec.Code != tt.wantStatus {
				t.Fatalf("got %d, want %d: %s", rec.Code, tt.wantStatus, rec.Body)
			}
			if tt.wantCode != "" && !strings.Contains(rec.Body.String(), `"code":"`+tt.wantCode+`"`) {
				t.Errorf("body %s missing code %s", rec.Body, tt.wantCode)
			}
			if strings.Contains(rec.Body.String(), "ghp_") {
				t.Error("secret echoed back to the client")
			}
			if tt.wantUpstream == "" {
				if tt.wantStatus != 200 && got.URL != nil {
					t.Fatal("blocked request reached upstream")
				}
				return
			}
			b, _ := io.ReadAll(got.Body)
			if string(b) != tt.wantUpstream {
				t.Errorf("upstream body\n got %s\nwant %s", b, tt.wantUpstream)
			}
			if got.ContentLength != int64(len(b)) {
				t.Errorf("upstream content-length %d, body %d", got.ContentLength, len(b))
			}
		})
	}
}

func TestWithPolicyUnreadableBody(t *testing.T) {
	key := newKey(t)
	s, got := newTestServer(t, &key.PublicKey)

	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", iotest.ErrReader(errors.New("broken")))
	req.Header.Set("Authorization", "Bearer "+sign(t, jwt.SigningMethodRS256, validClaims(), key))
	rec := httptest.NewRecorder()
	s.routes().ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("got %d, want 400", rec.Code)
	}
	if got.URL != nil {
		t.Fatal("request reached upstream")
	}
}
