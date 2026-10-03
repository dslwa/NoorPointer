package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/dslwa/NoorPointer/gateway/config"
	pb "github.com/dslwa/NoorPointer/gateway/gen/semanticv1"
)

func checkServer(t *testing.T, auditStatus int) (*Server, <-chan map[string]any, *http.Request) {
	t.Helper()
	events := make(chan map[string]any, 10)
	cp := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/gateway/events" || r.Method != "POST" {
			t.Errorf("unexpected request %s %s", r.Method, r.URL.Path)
		}
		if r.Header.Get("Authorization") != "Bearer test-token" {
			t.Error("audit token missing")
		}
		var event map[string]any
		if err := json.NewDecoder(r.Body).Decode(&event); err != nil {
			t.Error(err)
		}
		events <- event
		w.WriteHeader(auditStatus)
	}))
	t.Cleanup(cp.Close)
	s, upstream := newTestServer(t, nil)
	s.controlPlaneURL = cp.URL
	s.policy.Load().Defaults.SemanticTimeoutMs = 500
	s.policy.Load().Defaults.OnSemanticTimeout = "fail_closed"
	return s, events, upstream
}

func promptReport(t *testing.T, s *Server, body string) checkReport {
	t.Helper()
	rec := doBody(s.routes(), "POST", "/admin/check", "Bearer admin-token", body)
	if rec.Code != 200 {
		t.Fatalf("HTTP %d: %s", rec.Code, rec.Body)
	}
	var report checkReport
	if err := json.Unmarshal(rec.Body.Bytes(), &report); err != nil {
		t.Fatal(err)
	}
	return report
}

func TestCheckAuthorizationAndValidation(t *testing.T) {
	s, _, _ := checkServer(t, 201)
	tests := []struct {
		name, auth, body string
		status           int
	}{
		{"no token", "", `{"direction":"input","messages":[{"role":"user","content":"hi"}]}`, 401},
		{"wrong token", "Bearer other", `{}`, 401},
		{"invalid direction", "Bearer admin-token", `{"direction":"sideways","messages":[{"role":"user","content":"hi"}]}`, 400},
		{"empty messages", "Bearer admin-token", `{"direction":"input","messages":[]}`, 400},
		{"blank content", "Bearer admin-token", `{"direction":"input","messages":[{"role":"user","content":" "}]}`, 400},
		{"unknown role", "Bearer admin-token", `{"direction":"input","messages":[{"role":"invalid","content":"hi"}]}`, 400},
		{"output context only", "Bearer admin-token", `{"direction":"output","messages":[{"role":"user","content":"hi"}]}`, 400},
		{"unknown field", "Bearer admin-token", `{"direction":"input","threshold":0.1,"messages":[]}`, 400},
		{"trailing JSON", "Bearer admin-token", `{"direction":"input","messages":[{"role":"user","content":"hi"}]} {}`, 400},
		{"too large", "Bearer admin-token", `{"direction":"input","messages":[{"role":"user","content":"` + strings.Repeat("a", maxBodyBytes) + `"}]}`, 413},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			rec := doBody(s.routes(), "POST", "/admin/check", tt.auth, tt.body)
			if rec.Code != tt.status {
				t.Fatalf("HTTP %d, want %d: %s", rec.Code, tt.status, rec.Body)
			}
		})
	}
	s.policy.Store(nil)
	if rec := doBody(s.routes(), "POST", "/admin/check", "Bearer admin-token", `{}`); rec.Code != 503 {
		t.Fatalf("missing policy: %d", rec.Code)
	}
}

func TestCheckBlocksSecretsWithoutCallingModelsAndAuditsMetadata(t *testing.T) {
	s, events, upstream := checkServer(t, 201)
	s.policy.Load().Controls.PromptInjection = &config.ScoreControl{Control: config.Control{Enabled: true, Action: "block"}, Threshold: 0.8}
	fake := &fakeSemantic{}
	s.semanticClient = fake
	report := promptReport(t, s, `{"direction":"input","messages":[{"role":"user","content":"AKIAABCDEFGHIJKLMNOP"}]}`)
	if report.Decision != "block" || report.Code != "SECRET_LEAKAGE_DETECTED" || !report.AuditSaved {
		t.Fatalf("report: %+v", report)
	}
	if fake.got != nil || upstream.URL != nil {
		t.Fatal("a deterministic block called a model")
	}
	if len(report.Findings) != 1 || report.Findings[0].Control != "secrets" {
		t.Fatalf("findings: %+v", report.Findings)
	}
	event := <-events
	data, _ := json.Marshal(event)
	if strings.Contains(string(data), "AKIAABCDEFGHIJKLMNOP") {
		t.Fatal("submitted secret leaked to audit")
	}
	if event["action"] != "block" || event["id"] != report.AuditEventID || event["policy_version"] != float64(report.PolicyVersion) {
		t.Fatalf("audit: %v", event)
	}
	if event["context"].(map[string]any)["source"] != "prompt_check" {
		t.Fatal("not recognizable in Events")
	}
}

func TestCheckUsesPolicyThresholdAndReportsAllSemanticResults(t *testing.T) {
	for _, tt := range []struct {
		name, mode       string
		score, threshold float32
		want             string
	}{
		{"blocked", "enforce", 0.97, 0.85, "block"},
		{"higher threshold", "enforce", 0.97, 0.99, "allow"},
		{"monitor", "monitor", 0.97, 0.85, "monitor"},
	} {
		t.Run(tt.name, func(t *testing.T) {
			s, _, upstream := checkServer(t, 201)
			p := s.policy.Load()
			p.Version = 12
			p.Defaults.Mode = tt.mode
			p.Controls.PromptInjection = &config.ScoreControl{Control: config.Control{Enabled: true, Action: "block"}, Threshold: float64(tt.threshold)}
			p.Controls.ContentSafety = &config.CategoryControl{Control: config.Control{Enabled: true, Action: "block"}, Categories: []string{"S1"}}
			s.semanticClient = &fakeSemantic{resp: &pb.AnalyzeResponse{Results: []*pb.CheckResult{
				{Check: pb.Check_CHECK_PROMPT_INJECTION, Status: pb.Status_STATUS_OK, Score: tt.score},
				{Check: pb.Check_CHECK_CONTENT_SAFETY, Status: pb.Status_STATUS_OK, Score: 0},
			}}}
			report := promptReport(t, s, `{"direction":"input","messages":[{"role":"user","content":"hello"}]}`)
			if report.Decision != tt.want || report.PolicyVersion != 12 || len(report.Semantic) != 2 {
				t.Fatalf("report: %+v", report)
			}
			if report.Semantic[0].Check != "CHECK_PROMPT_INJECTION" || report.Semantic[0].Passed == nil || *report.Semantic[0].Passed != (tt.score < tt.threshold) {
				t.Fatalf("semantic: %+v", report.Semantic)
			}
			if upstream.URL != nil {
				t.Fatal("check endpoint called upstream")
			}
		})
	}
}

func TestCheckRedactsBeforeSemanticAnalysisAndPreservesDirection(t *testing.T) {
	s, _, _ := checkServer(t, 201)
	p := s.policy.Load()
	p.Controls.PromptInjection = &config.ScoreControl{Control: config.Control{Enabled: true, Action: "block"}, Threshold: 0.8}
	fake := &fakeSemantic{resp: result(pb.Check_CHECK_PROMPT_INJECTION, pb.Status_STATUS_OK, 0.1)}
	s.semanticClient = fake
	report := promptReport(t, s, `{"direction":"input","messages":[{"role":"user","content":"email jan@example.com"}]}`)
	if report.Decision != "redact" || strings.Contains(report.Messages[0].Content, "jan@example.com") {
		t.Fatalf("report: %+v", report)
	}
	if fake.got.Direction != pb.Direction_DIRECTION_INPUT || fake.got.Messages[0].Content != report.Messages[0].Content {
		t.Fatalf("analyze: %+v", fake.got)
	}
}

func TestCheckUnavailableAndMissingResultsNeverPass(t *testing.T) {
	for _, mode := range []string{"fail_closed", "fail_open"} {
		t.Run(mode, func(t *testing.T) {
			s, _, _ := checkServer(t, 201)
			p := s.policy.Load()
			p.Defaults.OnSemanticTimeout = mode
			p.Controls.PromptInjection = &config.ScoreControl{Control: config.Control{Enabled: true, Action: "block"}, Threshold: 0.8}
			// Empty successful RPC response: every requested result is missing.
			s.semanticClient = &fakeSemantic{resp: &pb.AnalyzeResponse{}}
			report := promptReport(t, s, `{"direction":"input","messages":[{"role":"user","content":"hello"}]}`)
			want := "block"
			if mode == "fail_open" {
				want = "monitor"
			}
			if report.Decision != want || len(report.Semantic) != 1 || report.Semantic[0].Status != "STATUS_ERROR" || report.Semantic[0].Passed != nil {
				t.Fatalf("report: %+v", report)
			}
		})
	}
	s, _, _ := checkServer(t, 201)
	s.policy.Load().Controls.PromptInjection = &config.ScoreControl{Control: config.Control{Enabled: true, Action: "block"}, Threshold: 0.8}
	report := promptReport(t, s, `{"direction":"input","messages":[{"role":"user","content":"hello"}]}`)
	if report.Decision != "block" || report.Semantic[0].Status != "STATUS_ERROR" {
		t.Fatalf("missing client: %+v", report)
	}
}

func TestCheckReportsAuditFailure(t *testing.T) {
	s, _, _ := checkServer(t, 503)
	report := promptReport(t, s, `{"direction":"input","messages":[{"role":"user","content":"hello"}]}`)
	if report.AuditSaved || report.AuditEventID != "" || report.Decision != "allow" {
		t.Fatalf("report: %+v", report)
	}
}

func TestCheckRejectionAlwaysBlocksAndMixedResultsPreserveFindings(t *testing.T) {
	for _, results := range [][]*pb.CheckResult{
		{{Check: pb.Check_CHECK_PROMPT_INJECTION, Status: pb.Status_STATUS_REJECTED, Error: "message too long"}},
		{{Check: pb.Check_CHECK_PROMPT_INJECTION, Status: pb.Status_STATUS_OK, Score: 0.97, MessageId: "0"},
			{Check: pb.Check_CHECK_PROMPT_INJECTION, Status: pb.Status_STATUS_TIMEOUT, MessageId: "1", Error: "timeout"}},
	} {
		s, _, _ := checkServer(t, 201)
		p := s.policy.Load()
		p.Defaults.OnSemanticTimeout = "fail_open"
		p.Controls.PromptInjection = &config.ScoreControl{Control: config.Control{Enabled: true, Action: "block"}, Threshold: 0.8}
		s.semanticClient = &fakeSemantic{resp: &pb.AnalyzeResponse{Results: results}}
		report := promptReport(t, s, `{"direction":"input","messages":[{"role":"user","content":"one"},{"role":"user","content":"two"}]}`)
		if report.Decision != "block" {
			t.Fatalf("report: %+v", report)
		}
		for _, check := range report.Checks {
			if check.Control == "prompt_injection" && (check.Status != "failed" || check.Action != "block") {
				t.Fatalf("result hid the rejection or finding: %+v", check)
			}
		}
	}
}
