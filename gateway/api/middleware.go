package api

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"slices"
	"strings"
	"time"

	"github.com/dslwa/NoorPointer/gateway/config"
	pb "github.com/dslwa/NoorPointer/gateway/gen/semanticv1"
	"github.com/dslwa/NoorPointer/gateway/scan"
	"github.com/dslwa/NoorPointer/gateway/types"
	"github.com/golang-jwt/jwt/v5"
)

const maxBodyBytes = 1 << 20

var blockCodes = map[string]string{
	"secrets":   "SECRET_LEAKAGE_DETECTED",
	"pii_regex": "PII_DETECTED",
}

type ctxKey struct{}

func claimsFor(r *http.Request) *types.Claims {
	claims, _ := r.Context().Value(ctxKey{}).(*types.Claims)
	return claims
}

func (s *Server) withPolicy(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		p := s.policy.Load()
		if p == nil {
			WriteJSON(w, http.StatusServiceUnavailable, APIError{Error: "policy not loaded"})
			return
		}
		claims := claimsFor(r)
		log.Printf("request sub=%s team=%s policy=%d %s %s", claims.Subject, claims.Team, p.Version, r.Method, r.URL.Path)

		if r.Method == http.MethodPost {
			doc, ok := decodeBody(w, r)
			if !ok {
				return
			}
			model, _ := doc["model"].(string)
			if !slices.Contains(p.Models.Allowed, model) &&
				s.deny(w, p, http.StatusForbidden, "MODEL_NOT_ALLOWED", fmt.Sprintf("model %q is not allowed", model)) {
				return
			}
			if v, _, _ := s.check(r, claims.Subject, p, doc); v.code != "" && s.deny(w, p, v.status, v.code, v.msg) {
				return
			}

			// Always forward the document we checked, never the raw bytes:
			// duplicate keys or trailing data could read differently upstream.
			var buf bytes.Buffer
			buf.Grow(int(min(max(r.ContentLength, 0), maxBodyBytes)) + 512) // one alloc instead of doubling
			enc := json.NewEncoder(&buf)
			enc.SetEscapeHTML(false)
			enc.Encode(doc) // re-encoding a document we just decoded cannot fail
			body := bytes.TrimSuffix(buf.Bytes(), []byte("\n"))
			r.Body = io.NopCloser(bytes.NewReader(body))
			r.ContentLength = int64(len(body))
		}

		next.ServeHTTP(w, r)
	})
}

// Decode straight from the capped stream: no raw copy of the body, and a
// 30 MB upload stops being read at maxBodyBytes.
func decodeBody(w http.ResponseWriter, r *http.Request) (map[string]any, bool) {
	dec := json.NewDecoder(http.MaxBytesReader(w, r.Body, maxBodyBytes))
	dec.UseNumber()
	var doc map[string]any
	if err := dec.Decode(&doc); err != nil {
		if _, tooBig := errors.AsType[*http.MaxBytesError](err); tooBig {
			WriteJSON(w, http.StatusRequestEntityTooLarge, APIError{Error: "request body too large"})
		} else {
			WriteJSON(w, http.StatusBadRequest, APIError{Error: "invalid JSON body"})
		}
		return nil, false
	}
	return doc, true
}

// Shared by the proxy and the dashboard's dry run, so both decide alike.
// doc is redacted in place: Python and the upstream see the masked text.
func (s *Server) check(r *http.Request, agent string, p *config.Policy, doc map[string]any) (verdict, []scan.Finding, []*pb.CheckResult) {
	var found []scan.Finding
	walkStrings(doc, func(text string) string { return scan.Text(p, text, &found) })
	for _, f := range found {
		log.Printf("%s: %s %s detected", f.Action, f.Control, f.Kind)
	}
	if i := slices.IndexFunc(found, func(f scan.Finding) bool { return f.Action == "block" }); i >= 0 {
		return verdict{http.StatusForbidden, blockCodes[found[i].Control], fmt.Sprintf("%s detected: %s", found[i].Control, found[i].Kind)}, found, nil
	}
	v, results := s.semantic(r, agent, p, doc)
	return v, found, results
}

func (s *Server) deny(w http.ResponseWriter, p *config.Policy, status int, code, msg string) bool {
	if p.Defaults.Mode == "monitor" {
		log.Printf("monitor: would block %s: %s", code, msg)
		return false
	}
	WriteJSON(w, status, APIError{Error: msg, Code: code})
	return true
}

func (s *Server) withJWTAuth(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		const prefix = "Bearer "
		authHeader := r.Header.Get("Authorization")
		if !strings.HasPrefix(authHeader, prefix) {
			WriteJSON(w, http.StatusUnauthorized, APIError{Error: "missing or invalid authorization header"})
			return
		}

		claims := &types.Claims{}
		_, err := jwt.ParseWithClaims(strings.TrimPrefix(authHeader, prefix), claims,
			func(*jwt.Token) (any, error) { return s.pubKey, nil },
			jwt.WithValidMethods([]string{"RS256"}),
			jwt.WithIssuer("noorpointer-cp"),
			jwt.WithAudience("noorpointer-gateway"),
			jwt.WithExpirationRequired(),
			jwt.WithLeeway(30*time.Second),
		)
		if err != nil {
			log.Printf("jwt rejected: %v", err)
			WriteJSON(w, http.StatusUnauthorized, APIError{Error: "invalid token"})
			return
		}

		r.Header.Del("Authorization")
		ctx := context.WithValue(r.Context(), ctxKey{}, claims)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}
