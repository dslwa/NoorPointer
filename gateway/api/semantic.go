package api

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"slices"
	"strconv"
	"time"

	"github.com/dslwa/NoorPointer/gateway/config"
	pb "github.com/dslwa/NoorPointer/gateway/gen/semanticv1"
)

type verdict struct {
	status    int
	code, msg string
}

// Python only scores; the thresholds live in the policy, so the gateway decides.
func (s *Server) semantic(r *http.Request, agent string, p *config.Policy, doc map[string]any) (verdict, []*pb.CheckResult) {
	pi, cs := p.Controls.PromptInjection, p.Controls.ContentSafety
	var checks []*pb.CheckSpec
	timeout := uint32(p.Defaults.SemanticTimeoutMs)
	if pi != nil && pi.Enabled {
		checks = append(checks, &pb.CheckSpec{Check: pb.Check_CHECK_PROMPT_INJECTION, TimeoutMs: timeout})
	}
	if cs != nil && cs.Enabled {
		checks = append(checks, &pb.CheckSpec{Check: pb.Check_CHECK_CONTENT_SAFETY, TimeoutMs: timeout})
	}
	msgs := chatMessages(doc)
	// ponytail: nil client only in tests that don't exercise semantic checks
	if s.semanticClient == nil || len(checks) == 0 || len(msgs) == 0 {
		return verdict{}, nil
	}

	ctx, cancel := context.WithTimeout(r.Context(), time.Duration(p.Defaults.SemanticTimeoutMs)*time.Millisecond)
	defer cancel()
	resp, err := s.semanticClient.Analyze(ctx, &pb.AnalyzeRequest{
		RequestId: r.Header.Get("X-Request-Id"),
		AgentId:   agent,
		Direction: pb.Direction_DIRECTION_INPUT,
		Messages:  msgs,
		Checks:    checks,
	})
	if err != nil {
		log.Printf("semantic: %v", err)
		return unavailable(p, err.Error()), nil
	}

	for _, res := range resp.Results {
		var v verdict
		switch {
		case res.Status == pb.Status_STATUS_REJECTED:
			// The caller can trigger a hard limit at will, so this never fails open.
			return verdict{http.StatusForbidden, "SEMANTIC_INPUT_REJECTED", res.Error}, resp.Results
		case res.Status != pb.Status_STATUS_OK:
			log.Printf("semantic: %s %s: %s", res.Check, res.Status, res.Error)
			v = unavailable(p, res.Error)
		case res.Check == pb.Check_CHECK_PROMPT_INJECTION && float64(res.Score) >= pi.Threshold:
			v = act(pi.Control, "PROMPT_INJECTION_DETECTED", fmt.Sprintf("prompt injection score %.2f", res.Score))
		// Llama Guard can say unsafe without a category; Python flags that too.
		case res.Check == pb.Check_CHECK_CONTENT_SAFETY && res.Score >= 0.5 &&
			(len(res.Categories) == 0 || slices.ContainsFunc(res.Categories, func(c string) bool { return slices.Contains(cs.Categories, c) })):
			v = act(cs.Control, "UNSAFE_CONTENT_DETECTED", fmt.Sprintf("unsafe content %v", res.Categories))
		}
		if v.code != "" {
			return v, resp.Results
		}
	}
	return verdict{}, resp.Results
}

func act(c config.Control, code, msg string) verdict {
	if c.Action != "block" {
		log.Printf("%s: %s", c.Action, msg)
		return verdict{}
	}
	return verdict{http.StatusForbidden, code, msg}
}

func unavailable(p *config.Policy, msg string) verdict {
	if p.Defaults.OnSemanticTimeout == "fail_closed" {
		return verdict{http.StatusServiceUnavailable, "SEMANTIC_UNAVAILABLE", "semantic checks unavailable: " + msg}
	}
	return verdict{}
}

func chatMessages(doc map[string]any) []*pb.Message {
	var out []*pb.Message
	add := func(role, text string) {
		if text == "" {
			return
		}
		out = append(out, &pb.Message{Id: strconv.Itoa(len(out)), Role: role, Content: text})
	}
	list, _ := doc["messages"].([]any)
	for _, m := range list {
		m, _ := m.(map[string]any)
		role, _ := m["role"].(string)
		switch c := m["content"].(type) {
		case string:
			add(role, c)
		case []any:
			for _, part := range c {
				part, _ := part.(map[string]any)
				if text, ok := part["text"].(string); ok {
					add(role, text)
				}
			}
		}
	}
	return out
}
