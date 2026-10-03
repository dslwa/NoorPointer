package api

import (
	"net/http"

	"github.com/dslwa/NoorPointer/gateway/scan"
)

type checkResponse struct {
	Decision      string           `json:"decision"` // allow | block | monitor (would block)
	Code          string           `json:"code,omitempty"`
	Message       string           `json:"message,omitempty"`
	PolicyVersion int64            `json:"policy_version"`
	Findings      []scan.Finding   `json:"findings"`
	Semantic      []semanticResult `json:"semantic"`
	Messages      any              `json:"messages"` // after redaction: what the model would get
}

type semanticResult struct {
	Check      string   `json:"check"`
	Status     string   `json:"status"`
	Score      float32  `json:"score"`
	Categories []string `json:"categories"`
	Error      string   `json:"error,omitempty"`
}

// handleCheck is the dashboard's dry run: the same controls as the proxy,
// but the verdict is returned instead of forwarding to the model.
// ponytail: input direction only, output checks arrive with step 10
func (s *Server) handleCheck(w http.ResponseWriter, r *http.Request) error {
	if !bearer(r, s.adminToken) {
		return WriteJSON(w, http.StatusUnauthorized, APIError{Error: "unauthorized"})
	}
	p := s.policy.Load()
	if p == nil {
		return WriteJSON(w, http.StatusServiceUnavailable, APIError{Error: "policy not loaded"})
	}
	doc, ok := decodeBody(w, r)
	if !ok {
		return nil
	}

	v, found, results := s.check(r, "dashboard", p, doc)
	resp := checkResponse{Decision: "allow", Code: v.code, Message: v.msg, PolicyVersion: p.Version,
		Findings: append([]scan.Finding{}, found...), Semantic: []semanticResult{}, Messages: doc["messages"]}
	if v.code != "" {
		resp.Decision = "block"
		if p.Defaults.Mode == "monitor" {
			resp.Decision = "monitor"
		}
	}
	for _, r := range results {
		resp.Semantic = append(resp.Semantic, semanticResult{r.Check.String(), r.Status.String(), r.Score, r.Categories, r.Error})
	}
	return WriteJSON(w, http.StatusOK, resp)
}
