package api

import (
	"context"
	"encoding/json"
	"log"
	"net/http"
	"strings"

	"github.com/dslwa/NoorPointer/gateway/config"
	"github.com/dslwa/NoorPointer/gateway/scan"
)

// The feed only has "literal" matches (signatures.schema.json), compared case-insensitively.
type signature struct {
	ID     string `json:"id"`
	Action string `json:"action"`
	Target string `json:"target"`
	Match  struct {
		Value string `json:"value"`
	} `json:"match"`
	Enabled *bool `json:"enabled"`
}

func (s *Server) refreshSignatures(ctx context.Context) error {
	s.sigMu.Lock()
	defer s.sigMu.Unlock()

	body, etag, err := s.fetch(ctx, "/api/gateway/signatures", s.sigETag)
	if err != nil || body == nil {
		return err
	}
	var feed struct {
		Signatures []signature `json:"signatures"`
	}
	if err := json.Unmarshal(body, &feed); err != nil {
		return err
	}
	sigs := feed.Signatures[:0]
	for _, sig := range feed.Signatures {
		if (sig.Enabled == nil || *sig.Enabled) && sig.Match.Value != "" {
			sig.Match.Value = strings.ToLower(sig.Match.Value)
			sigs = append(sigs, sig)
		}
	}

	s.signatures.Store(&sigs)
	s.sigETag = etag
	log.Printf("signatures loaded count=%d", len(sigs))
	return nil
}

func (s *Server) signatureCount() int {
	if sigs := s.signatures.Load(); sigs != nil {
		return len(*sigs)
	}
	return 0
}

// matchSignatures runs before the regex scan, so redaction cannot break up a literal.
// A hit blocks only when both the control and the signature say block.
func (s *Server) matchSignatures(r *http.Request, p *config.Policy, doc map[string]any, found *[]scan.Finding) {
	c, sigs := p.Controls.AttackSignatures, s.signatures.Load()
	if c == nil || !c.Enabled || sigs == nil {
		return
	}
	model, _ := doc["model"].(string)
	names, args := toolCalls(doc)
	targets := map[string][]string{
		"prompt":         collectStrings(doc), // every string, like the regex scan
		"tool_name":      names,
		"tool_arguments": args,
		"model_artifact": {model},
		"upstream_path":  {r.URL.Path},
	}
	for k, texts := range targets {
		for i := range texts {
			texts[i] = strings.ToLower(texts[i])
		}
		targets[k] = texts
	}

	for _, sig := range *sigs {
		for _, text := range targets[sig.Target] {
			if strings.Contains(text, sig.Match.Value) {
				action := "monitor"
				if c.Action == "block" && sig.Action == "block" {
					action = "block"
				}
				*found = append(*found, scan.Finding{Control: "attack_signatures", Kind: sig.ID, Action: action})
				break
			}
		}
	}
}

func collectStrings(v any) []string {
	var out []string
	walkStrings(v, func(t string) string { out = append(out, t); return t })
	return out
}

// toolCalls reads names and arguments from assistant tool_calls and names from the tools list.
func toolCalls(doc map[string]any) (names, args []string) {
	fn := func(x any) map[string]any {
		m, _ := x.(map[string]any)
		f, _ := m["function"].(map[string]any)
		return f
	}
	tools, _ := doc["tools"].([]any)
	for _, t := range tools {
		if name, ok := fn(t)["name"].(string); ok {
			names = append(names, name)
		}
	}
	msgs, _ := doc["messages"].([]any)
	for _, m := range msgs {
		m, _ := m.(map[string]any)
		calls, _ := m["tool_calls"].([]any)
		for _, c := range calls {
			f := fn(c)
			if name, ok := f["name"].(string); ok {
				names = append(names, name)
			}
			if a, ok := f["arguments"].(string); ok {
				args = append(args, a)
			}
		}
	}
	return names, args
}
