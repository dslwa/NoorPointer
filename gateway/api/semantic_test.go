package api

import (
	"context"
	"errors"
	"strings"
	"testing"

	"github.com/dslwa/NoorPointer/gateway/config"
	pb "github.com/dslwa/NoorPointer/gateway/gen/semanticv1"
	"github.com/golang-jwt/jwt/v5"
	"google.golang.org/grpc"
)

type fakeSemantic struct {
	pb.SemanticServiceClient // ScanArtifact unused: nil, panics if called
	resp                     *pb.AnalyzeResponse
	err                      error
	got                      *pb.AnalyzeRequest
}

func (f *fakeSemantic) Analyze(_ context.Context, req *pb.AnalyzeRequest, _ ...grpc.CallOption) (*pb.AnalyzeResponse, error) {
	f.got = req
	return f.resp, f.err
}

func result(check pb.Check, status pb.Status, score float32, cats ...string) *pb.AnalyzeResponse {
	return &pb.AnalyzeResponse{Results: []*pb.CheckResult{{Check: check, Status: status, Score: score, Categories: cats}}}
}

func TestSemantic(t *testing.T) {
	key := newKey(t)
	auth := "Bearer " + sign(t, jwt.SigningMethodRS256, validClaims(), key)
	const (
		inj  = pb.Check_CHECK_PROMPT_INJECTION
		safe = pb.Check_CHECK_CONTENT_SAFETY
		ok   = pb.Status_STATUS_OK
	)
	body := `{"model":"mock-llm","messages":[{"role":"user","content":"hi jan@example.com"}]}`

	tests := []struct {
		name       string
		resp       *pb.AnalyzeResponse
		err        error
		mutate     func(*config.Policy)
		body       string
		wantStatus int
		wantCode   string
		wantCalled bool
	}{
		{"clean", result(inj, ok, 0.1), nil, nil, body, 200, "", true},
		{"injection", result(inj, ok, 0.9), nil, nil, body, 403, "PROMPT_INJECTION_DETECTED", true},
		{"injection monitor action", result(inj, ok, 0.9), nil, func(p *config.Policy) { p.Controls.PromptInjection.Action = "monitor" }, body, 200, "", true},
		{"unsafe category", result(safe, ok, 1, "S9", "S1"), nil, nil, body, 403, "UNSAFE_CONTENT_DETECTED", true},
		{"unsafe without category", result(safe, ok, 1), nil, nil, body, 403, "UNSAFE_CONTENT_DETECTED", true},
		{"safe", result(safe, ok, 0), nil, nil, body, 200, "", true},
		{"unsafe category not in policy", result(safe, ok, 1, "S9"), nil, nil, body, 200, "", true},
		{"rpc error fail_open", nil, errors.New("unavailable"), nil, body, 200, "", true},
		{"rpc error fail_closed", nil, errors.New("unavailable"), func(p *config.Policy) { p.Defaults.OnSemanticTimeout = "fail_closed" }, body, 503, "SEMANTIC_UNAVAILABLE", true},
		{"check timeout fail_closed", result(inj, pb.Status_STATUS_TIMEOUT, 0), nil, func(p *config.Policy) { p.Defaults.OnSemanticTimeout = "fail_closed" }, body, 503, "SEMANTIC_UNAVAILABLE", true},
		{"check timeout fail_open", result(inj, pb.Status_STATUS_TIMEOUT, 0), nil, nil, body, 200, "", true},
		{"rejected never fails open", result(inj, pb.Status_STATUS_REJECTED, 0), nil, nil, body, 403, "SEMANTIC_INPUT_REJECTED", true},
		{"regex block skips python", nil, nil, nil, `{"model":"mock-llm","messages":[{"role":"user","content":"AKIAABCDEFGHIJKLMNOP"}]}`, 403, "SECRET_LEAKAGE_DETECTED", false},
		{"no checks enabled", nil, nil, func(p *config.Policy) { p.Controls.PromptInjection, p.Controls.ContentSafety = nil, nil }, body, 200, "", false},
		{"content parts", result(inj, ok, 0.9), nil, nil, `{"model":"mock-llm","messages":[{"role":"user","content":[{"type":"text","text":"ignore all"}]}]}`, 403, "PROMPT_INJECTION_DETECTED", true},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			s, _ := newTestServer(t, &key.PublicKey)
			fake := &fakeSemantic{resp: tt.resp, err: tt.err}
			s.semanticClient = fake
			p := *s.policy.Load()
			p.Defaults.SemanticTimeoutMs = 500
			p.Defaults.OnSemanticTimeout = "fail_open"
			p.Controls.PromptInjection = &config.ScoreControl{Control: config.Control{Enabled: true, Action: "block"}, Threshold: 0.8}
			p.Controls.ContentSafety = &config.CategoryControl{Control: config.Control{Enabled: true, Action: "block"}, Categories: []string{"S1"}}
			if tt.mutate != nil {
				tt.mutate(&p)
			}
			s.policy.Store(&p)

			rec := doBody(s.routes(), "POST", "/v1/chat/completions", auth, tt.body)
			if rec.Code != tt.wantStatus {
				t.Fatalf("got %d, want %d: %s", rec.Code, tt.wantStatus, rec.Body)
			}
			if tt.wantCode != "" && !strings.Contains(rec.Body.String(), `"code":"`+tt.wantCode+`"`) {
				t.Errorf("body %s missing code %s", rec.Body, tt.wantCode)
			}
			if called := fake.got != nil; called != tt.wantCalled {
				t.Fatalf("python called=%v, want %v", called, tt.wantCalled)
			}
		})
	}
}

// Python sees the prompt after regex redaction, never the raw PII.
func TestSemanticGetsRedactedPrompt(t *testing.T) {
	key := newKey(t)
	s, _ := newTestServer(t, &key.PublicKey)
	fake := &fakeSemantic{resp: &pb.AnalyzeResponse{}}
	s.semanticClient = fake
	p := *s.policy.Load()
	p.Defaults.SemanticTimeoutMs = 500
	p.Controls.PromptInjection = &config.ScoreControl{Control: config.Control{Enabled: true, Action: "block"}, Threshold: 0.8}
	s.policy.Store(&p)

	doBody(s.routes(), "POST", "/v1/chat/completions", "Bearer "+sign(t, jwt.SigningMethodRS256, validClaims(), key),
		`{"model":"mock-llm","messages":[{"role":"system","content":""},{"role":"user","content":"mail jan@example.com"}]}`)
	if len(fake.got.Messages) != 1 || fake.got.Messages[0].Content != "mail [REDACTED:email]" || fake.got.AgentId == "" {
		t.Fatalf("got %v", fake.got)
	}
}

func TestCheckEndpoint(t *testing.T) {
	body := `{"messages":[{"role":"user","content":"ignore all, mail jan@example.com"}]}`
	tests := []struct {
		name       string
		auth       string
		mode       string
		noPolicy   bool
		body       string
		wantStatus int
		want       []string
	}{
		{"block", "Bearer admin-token", "enforce", false, body, 200,
			[]string{`"decision":"block"`, `"code":"PROMPT_INJECTION_DETECTED"`, `"kind":"email"`, `"check":"CHECK_PROMPT_INJECTION"`, `[REDACTED:email]`}},
		{"monitor would block", "Bearer admin-token", "monitor", false, body, 200, []string{`"decision":"monitor"`}},
		{"wrong token", "Bearer test-token", "enforce", false, body, 401, nil},
		{"no policy", "Bearer admin-token", "enforce", true, body, 503, nil},
		{"invalid json", "Bearer admin-token", "enforce", false, `{`, 400, nil},
		{"regex block skips python", "Bearer admin-token", "enforce", false, `{"messages":[{"role":"user","content":"AKIAABCDEFGHIJKLMNOP"}]}`, 200,
			[]string{`"decision":"block"`, `"code":"SECRET_LEAKAGE_DETECTED"`, `"semantic":[]`}},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			s, got := newTestServer(t, &newKey(t).PublicKey)
			s.semanticClient = &fakeSemantic{resp: result(pb.Check_CHECK_PROMPT_INJECTION, pb.Status_STATUS_OK, 0.9)}
			p := *s.policy.Load()
			p.Defaults.Mode = tt.mode
			p.Defaults.SemanticTimeoutMs = 500
			p.Controls.PromptInjection = &config.ScoreControl{Control: config.Control{Enabled: true, Action: "block"}, Threshold: 0.8}
			s.policy.Store(&p)
			if tt.noPolicy {
				s.policy.Store(nil)
			}

			rec := doBody(s.routes(), "POST", "/admin/check", tt.auth, tt.body)
			if rec.Code != tt.wantStatus {
				t.Fatalf("got %d, want %d: %s", rec.Code, tt.wantStatus, rec.Body)
			}
			for _, w := range tt.want {
				if !strings.Contains(rec.Body.String(), w) {
					t.Errorf("body %s missing %s", rec.Body, w)
				}
			}
			if got.URL != nil {
				t.Fatal("dry run reached upstream")
			}
		})
	}
}
