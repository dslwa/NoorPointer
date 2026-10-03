package api

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"log"
	"net/http"
	"slices"
	"strings"
	"time"

	"github.com/dslwa/NoorPointer/gateway/config"
	pb "github.com/dslwa/NoorPointer/gateway/gen/semanticv1"
	"github.com/dslwa/NoorPointer/gateway/scan"
)

type checkMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type checkRequest struct {
	Direction string         `json:"direction"`
	Messages  []checkMessage `json:"messages"`
}

type checkFinding struct {
	Control string `json:"control"`
	Kind    string `json:"kind"`
	Action  string `json:"action"`
}

type checkOutcome struct {
	Control string `json:"control"`
	Status  string `json:"status"`
	Action  string `json:"action"`
	Message string `json:"message"`
}

type semanticOutcome struct {
	Check      string   `json:"check"`
	Status     string   `json:"status"`
	MessageID  string   `json:"message_id"`
	Score      float32  `json:"score"`
	Categories []string `json:"categories"`
	Error      string   `json:"error,omitempty"`
	Passed     *bool    `json:"passed,omitempty"`
}

type checkReport struct {
	Decision      string            `json:"decision"`
	Code          string            `json:"code"`
	Message       string            `json:"message"`
	PolicyVersion int64             `json:"policy_version"`
	Mode          string            `json:"mode"`
	RequestID     string            `json:"request_id"`
	Findings      []checkFinding    `json:"findings"`
	Semantic      []semanticOutcome `json:"semantic"`
	Messages      []checkMessage    `json:"messages"`
	Checks        []checkOutcome    `json:"checks"`
	LatencyMS     float64           `json:"latency_ms"`
	AuditSaved    bool              `json:"audit_saved"`
	AuditEventID  string            `json:"audit_event_id,omitempty"`
}

// A text-only inspection: no request is sent to the upstream LLM. The active
// gateway policy, regex scanner and semantic verdict logic are shared with chat.
func (s *Server) handleCheck(w http.ResponseWriter, r *http.Request) error {
	if !bearer(r, s.adminToken) {
		return WriteJSON(w, http.StatusUnauthorized, APIError{Error: "unauthorized"})
	}
	p := s.policy.Load()
	if p == nil {
		return WriteJSON(w, http.StatusServiceUnavailable, APIError{Error: "policy not loaded"})
	}
	dec := json.NewDecoder(http.MaxBytesReader(w, r.Body, maxBodyBytes))
	dec.DisallowUnknownFields()
	var input checkRequest
	if err := dec.Decode(&input); err != nil {
		if _, large := errors.AsType[*http.MaxBytesError](err); large {
			return WriteJSON(w, 413, APIError{Error: "request body too large"})
		}
		return WriteJSON(w, 400, APIError{Error: "invalid check request"})
	}
	if err := dec.Decode(new(any)); err != io.EOF {
		return WriteJSON(w, 400, APIError{Error: "expected one JSON object"})
	}
	if input.Direction == "" {
		input.Direction = "input"
	}
	if input.Direction != "input" {
		return WriteJSON(w, 400, APIError{Error: "only input checks are supported"})
	}
	if len(input.Messages) == 0 || len(input.Messages) > 50 {
		return WriteJSON(w, 400, APIError{Error: "send between 1 and 50 messages"})
	}
	for _, m := range input.Messages {
		if !slices.Contains([]string{"user", "assistant", "system", "tool"}, m.Role) || strings.TrimSpace(m.Content) == "" {
			return WriteJSON(w, 400, APIError{Error: "messages need a valid role and non-empty content"})
		}
	}

	started := time.Now()
	id := make([]byte, 16)
	if _, err := rand.Read(id); err != nil {
		return err
	}
	requestID := hex.EncodeToString(id)
	r.Header.Set("X-Request-Id", requestID)
	report := checkReport{Decision: "allow", Code: "CHECKS_PASSED", Message: "No blocking findings.",
		PolicyVersion: p.Version, Mode: p.Defaults.Mode, RequestID: requestID,
		Findings: []checkFinding{}, Semantic: []semanticOutcome{}, Messages: input.Messages, Checks: []checkOutcome{}}

	raw, _ := json.Marshal(map[string]any{"messages": input.Messages})
	doc := map[string]any{}
	json.Unmarshal(raw, &doc)
	blocked, found, results := s.check(r, "dashboard-prompt-check", p, doc)
	raw, _ = json.Marshal(doc["messages"])
	json.Unmarshal(raw, &report.Messages)
	for _, f := range found {
		report.Findings = append(report.Findings, checkFinding{f.Control, f.Kind, f.Action})
	}
	for _, item := range []struct {
		name    string
		control *config.Control
	}{
		{"secrets", p.Controls.Secrets}, {"pii_regex", piiControl(p)},
	} {
		status, action, message := "passed", "allow", "No findings."
		if item.control == nil || !item.control.Enabled {
			status, action, message = "disabled", "", "Disabled by policy."
		}
		for _, f := range found {
			if f.Control == item.name {
				status, action, message = "failed", f.Action, "Detected "+f.Kind+"."
			}
		}
		report.Checks = append(report.Checks, checkOutcome{item.name, status, action, message})
	}
	// These controls require a real agent/tool session or are not implemented in
	// the current gateway. Never label them as passed in a text-only inspection.
	if c := p.Controls.AttackSignatures; c != nil && c.Enabled {
		report.Checks = append(report.Checks, checkOutcome{"attack_signatures", "not_run", "", "Signature matching is not implemented by the gateway yet."})
	}

	specs := []struct {
		name    string
		check   pb.Check
		control *config.Control
	}{}
	if c := p.Controls.PromptInjection; c != nil {
		specs = append(specs, struct {
			name    string
			check   pb.Check
			control *config.Control
		}{"prompt_injection", pb.Check_CHECK_PROMPT_INJECTION, &c.Control})
	}
	if c := p.Controls.ContentSafety; c != nil {
		specs = append(specs, struct {
			name    string
			check   pb.Check
			control *config.Control
		}{"content_safety", pb.Check_CHECK_CONTENT_SAFETY, &c.Control})
	}
	if slices.ContainsFunc(found, func(f scan.Finding) bool { return f.Action == "block" }) {
		for _, spec := range specs {
			status := "not_run"
			if !spec.control.Enabled {
				status = "disabled"
			}
			report.Checks = append(report.Checks, checkOutcome{spec.name, status, "", "Not run after a deterministic block."})
		}
	} else {
		for _, spec := range specs {
			if !spec.control.Enabled {
				report.Checks = append(report.Checks, checkOutcome{spec.name, "disabled", "", "Disabled by policy."})
				continue
			}
			state, action, message := "passed", "allow", "No findings."
			for _, res := range results {
				if res.Check != spec.check {
					continue
				}
				if res.Status != pb.Status_STATUS_OK {
					if res.Status == pb.Status_STATUS_REJECTED {
						state, action, message = "failed", "block", res.Error
					} else if state != "failed" {
						state, message = "error", res.Error
					}
					continue
				}
				hit := semanticHit(p, res)
				if hit && (state != "failed" || action != "block") {
					state, action, message = "failed", spec.control.Action, "Gateway policy threshold exceeded."
				}
			}
			if state == "error" {
				action = "monitor"
				if p.Defaults.OnSemanticTimeout == "fail_closed" {
					action = "block"
				}
			}
			if p.Defaults.Mode == "monitor" && action == "block" {
				action = "monitor"
			}
			report.Checks = append(report.Checks, checkOutcome{spec.name, state, action, message})
		}
		for _, res := range results {
			categories := res.Categories
			if categories == nil {
				categories = []string{}
			}
			out := semanticOutcome{Check: res.Check.String(), Status: res.Status.String(), MessageID: res.MessageId, Score: res.Score, Categories: categories, Error: res.Error}
			if res.Status == pb.Status_STATUS_OK {
				passed := !semanticHit(p, res)
				out.Passed = &passed
			}
			report.Semantic = append(report.Semantic, out)
		}
	}
	if blocked.code != "" {
		report.Code, report.Message = blocked.code, blocked.msg
		report.Decision = "block"
		if p.Defaults.Mode == "monitor" {
			report.Decision = "monitor"
		}
	} else if slices.ContainsFunc(report.Findings, func(f checkFinding) bool { return f.Action == "redact" }) {
		report.Decision = "redact"
		report.Code = "PII_ANONYMIZED"
		report.Message = "Personal data was redacted."
	}
	if report.Decision == "allow" && (len(report.Findings) > 0 || slices.ContainsFunc(report.Checks, func(c checkOutcome) bool { return c.Status == "failed" || c.Status == "error" })) {
		report.Decision = "monitor"
		report.Code = "CHECK_FINDINGS_MONITORED"
		report.Message = "Findings or unavailable checks were allowed by policy."
	}
	report.LatencyMS = float64(time.Since(started).Microseconds()) / 1000
	eventID := "prompt-check-" + requestID
	report.AuditSaved = s.saveCheckEvent(r.Context(), report, eventID, input.Direction)
	if report.AuditSaved {
		report.AuditEventID = eventID
	}
	return WriteJSON(w, http.StatusOK, report)
}

func piiControl(p *config.Policy) *config.Control {
	if p.Controls.PIIRegex == nil {
		return nil
	}
	return &p.Controls.PIIRegex.Control
}

func semanticHit(p *config.Policy, res *pb.CheckResult) bool {
	switch res.Check {
	case pb.Check_CHECK_PROMPT_INJECTION:
		return p.Controls.PromptInjection != nil && float64(res.Score) >= p.Controls.PromptInjection.Threshold
	case pb.Check_CHECK_CONTENT_SAFETY:
		c := p.Controls.ContentSafety
		return c != nil && res.Score >= 0.5 && (len(res.Categories) == 0 || slices.ContainsFunc(res.Categories, func(cat string) bool { return slices.Contains(c.Categories, cat) }))
	}
	return false
}

func (s *Server) saveCheckEvent(ctx context.Context, report checkReport, id, direction string) bool {
	severity := "info"
	if report.Decision == "block" {
		severity = "high"
	}
	// Store gateway results, never the submitted text or returned messages.
	event := map[string]any{"id": id, "occurred_at": time.Now().UTC().Format(time.RFC3339Nano), "kind": "decision",
		"agent_id": "dashboard-prompt-check", "request_id": report.RequestID, "action": report.Decision, "severity": severity,
		"control": "prompt_check", "policy_version": report.PolicyVersion, "message": report.Message, "latency_ms": report.LatencyMS,
		"context": map[string]any{"source": "prompt_check", "direction": direction, "code": report.Code, "mode": report.Mode,
			"findings": report.Findings, "semantic": report.Semantic, "checks": report.Checks}}
	data, _ := json.Marshal(event)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, s.controlPlaneURL+"/api/gateway/events", bytes.NewReader(data))
	if err != nil {
		return false
	}
	req.Header.Set("Authorization", "Bearer "+s.gatewayToken)
	req.Header.Set("Content-Type", "application/json")
	resp, err := s.controlPlane.Do(req)
	if err != nil {
		log.Printf("prompt check audit: %v", err)
		return false
	}
	defer resp.Body.Close()
	io.Copy(io.Discard, io.LimitReader(resp.Body, 4096))
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		log.Printf("prompt check audit returned %s", resp.Status)
		return false
	}
	return true
}
