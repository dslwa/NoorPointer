package config

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const validPolicy = `{
  "version": 3,
  "defaults": {"mode": "enforce", "semantic_timeout_ms": 300, "on_semantic_timeout": "fail_closed"},
  "models": {"allowed": ["mock-llm"]},
  "controls": {"prompt_injection": {"enabled": true, "action": "block", "threshold": 0.85}},
  "budgets": [{"subject": "agent:x", "daily_tokens": 0, "on_exceed": "block"}]
}`

func TestParsePolicyJavaProfiles(t *testing.T) {
	files, err := filepath.Glob("../../controlplane/src/main/resources/profiles/*.json")
	if err != nil || len(files) == 0 {
		t.Fatalf("no profiles found: %v", err)
	}
	for _, f := range files {
		data, err := os.ReadFile(f)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := ParsePolicy(data); err != nil {
			t.Errorf("%s: %v", filepath.Base(f), err)
		}
	}
}

func TestParsePolicyValid(t *testing.T) {
	p, err := ParsePolicy([]byte(validPolicy))
	if err != nil {
		t.Fatal(err)
	}
	if p.Version != 3 || p.Models.Allowed[0] != "mock-llm" || p.Controls.PromptInjection.Threshold != 0.85 {
		t.Errorf("unexpected policy: %+v", p)
	}
	if p.Budgets[0].DailyTokens == nil || *p.Budgets[0].DailyTokens != 0 {
		t.Error("daily_tokens 0 must be set, not nil")
	}
	if p.Controls.Secrets != nil {
		t.Error("absent control must be nil")
	}
}

func TestParsePolicyRejects(t *testing.T) {
	tests := []struct{ name, from, to string }{
		{"not json", `{`, `{"`},
		{"unknown field", `"version": 3`, `"versoin": 3`},
		{"bad mode", `"mode": "enforce"`, `"mode": "off"`},
		{"bad on_timeout", `"fail_closed"`, `"ignore"`},
		{"zero timeout", `"semantic_timeout_ms": 300`, `"semantic_timeout_ms": 0`},
		{"no models", `["mock-llm"]`, `[]`},
		{"threshold above 1", `"threshold": 0.85`, `"threshold": 1.5`},
		{"threshold below 0", `"threshold": 0.85`, `"threshold": -0.1`},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			doc := strings.Replace(validPolicy, tt.from, tt.to, 1)
			if doc == validPolicy {
				t.Fatalf("replacement %q not applied", tt.from)
			}
			if _, err := ParsePolicy([]byte(doc)); err == nil {
				t.Fatal("expected error")
			}
		})
	}
}
