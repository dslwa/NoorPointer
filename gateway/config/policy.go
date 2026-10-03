package config

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
)

type Policy struct {
	Version  int64    `json:"version"`
	Defaults Defaults `json:"defaults"`
	Models   Models   `json:"models"`
	Controls Controls `json:"controls"`
	Budgets  []Budget `json:"budgets"`
}

type Defaults struct {
	Mode              string `json:"mode"`
	SemanticTimeoutMs int    `json:"semantic_timeout_ms"`
	OnSemanticTimeout string `json:"on_semantic_timeout"`
}

type Models struct {
	Allowed []string `json:"allowed"`
}

type Controls struct {
	PIIRegex         *PatternControl   `json:"pii_regex"`
	Secrets          *Control          `json:"secrets"`
	PromptInjection  *ScoreControl     `json:"prompt_injection"`
	ContentSafety    *CategoryControl  `json:"content_safety"`
	AttackSignatures *SignatureControl `json:"attack_signatures"`
	AgentLoops       *LoopControl      `json:"agent_loops"`
	MCPTools         *ToolControl      `json:"mcp_tools"`
}

type Control struct {
	Enabled bool   `json:"enabled"`
	Action  string `json:"action"`
}

type PatternControl struct {
	Control
	Types []string `json:"types"`
}

type ScoreControl struct {
	Control
	Threshold float64 `json:"threshold"`
}

type CategoryControl struct {
	Control
	Categories []string `json:"categories"`
}

type SignatureControl struct {
	Control
	RefreshS int `json:"refresh_s"`
}

type LoopControl struct {
	Control
	MaxSteps              int `json:"max_steps"`
	MaxIdenticalToolCalls int `json:"max_identical_tool_calls"`
}

type ToolControl struct {
	Control
	Allowed      map[string][]string `json:"allowed"`
	PinnedHashes map[string]string   `json:"pinned_hashes"`
}

type Budget struct {
	Subject           string   `json:"subject"`
	MonthlyUSD        *float64 `json:"monthly_usd"`
	DailyTokens       *int64   `json:"daily_tokens"`
	GPUSecondsPerHour *float64 `json:"gpu_seconds_per_hour"`
	OnExceed          string   `json:"on_exceed"`
}

func ParsePolicy(data []byte) (*Policy, error) {
	dec := json.NewDecoder(bytes.NewReader(data))
	dec.DisallowUnknownFields()
	var p Policy
	if err := dec.Decode(&p); err != nil {
		return nil, fmt.Errorf("decode policy: %w", err)
	}
	if err := p.validate(); err != nil {
		return nil, fmt.Errorf("validate policy: %w", err)
	}
	return &p, nil
}

func (p *Policy) validate() error {
	if p.Defaults.Mode != "enforce" && p.Defaults.Mode != "monitor" {
		return fmt.Errorf("mode %q: want enforce or monitor", p.Defaults.Mode)
	}
	if p.Defaults.OnSemanticTimeout != "fail_open" && p.Defaults.OnSemanticTimeout != "fail_closed" {
		return fmt.Errorf("on_semantic_timeout %q: want fail_open or fail_closed", p.Defaults.OnSemanticTimeout)
	}
	if p.Defaults.SemanticTimeoutMs <= 0 {
		return errors.New("semantic_timeout_ms must be > 0")
	}
	if len(p.Models.Allowed) == 0 {
		return errors.New("models.allowed is empty")
	}
	if pi := p.Controls.PromptInjection; pi != nil && (pi.Threshold < 0 || pi.Threshold > 1) {
		return fmt.Errorf("prompt_injection threshold %v: want 0..1", pi.Threshold)
	}
	return nil
}
