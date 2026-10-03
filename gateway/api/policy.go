package api

import (
	"context"
	"crypto/subtle"
	"fmt"
	"io"
	"log"
	"net/http"
	"time"

	"github.com/dslwa/NoorPointer/gateway/config"
)

func (s *Server) refreshPolicy(ctx context.Context) error {
	s.policyMu.Lock()
	defer s.policyMu.Unlock()

	body, etag, err := s.fetch(ctx, "/api/gateway/policy", s.policyETag)
	if err != nil || body == nil {
		return err
	}
	p, err := config.ParsePolicy(body)
	if err != nil {
		return err
	}

	s.policy.Store(p)
	s.policyETag = etag
	log.Printf("policy loaded version=%d", p.Version)
	return nil
}

// fetch GETs a control plane path; a nil body with no error means 304 Not Modified.
func (s *Server) fetch(ctx context.Context, path, etag string) ([]byte, string, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, s.controlPlaneURL+path, nil)
	if err != nil {
		return nil, "", err
	}
	req.Header.Set("Authorization", "Bearer "+s.gatewayToken)
	if etag != "" {
		req.Header.Set("If-None-Match", etag)
	}

	resp, err := s.controlPlane.Do(req)
	if err != nil {
		return nil, "", err
	}
	defer resp.Body.Close()

	switch resp.StatusCode {
	case http.StatusNotModified:
		return nil, etag, nil
	case http.StatusOK:
	default:
		return nil, "", fmt.Errorf("control plane %s returned %s", path, resp.Status)
	}

	// 4 MB: the feed allows 1000 signatures of up to ~4 KB each.
	body, err := io.ReadAll(io.LimitReader(resp.Body, 4<<20))
	if err != nil {
		return nil, "", err
	}
	return body, resp.Header.Get("ETag"), nil
}

func (s *Server) watchPolicy(every time.Duration) {
	for {
		if err := s.refreshPolicy(context.Background()); err != nil {
			log.Printf("policy refresh failed, keeping version=%d: %v", s.policyVersion(), err)
		}
		// ponytail: polled with the policy every second, refresh_s ignored; a 304 costs nothing.
		if err := s.refreshSignatures(context.Background()); err != nil {
			log.Printf("signature refresh failed, keeping %d: %v", s.signatureCount(), err)
		}
		select {
		case <-s.quitch:
			return
		case <-time.After(every):
		}
	}
}

func (s *Server) policyVersion() int64 {
	if p := s.policy.Load(); p != nil {
		return p.Version
	}
	return 0
}

func (s *Server) handlePolicyReload(w http.ResponseWriter, r *http.Request) error {
	if !bearer(r, s.gatewayToken) {
		return WriteJSON(w, http.StatusUnauthorized, APIError{Error: "unauthorized"})
	}
	if err := s.refreshPolicy(r.Context()); err != nil {
		log.Printf("policy reload failed: %v", err)
		return WriteJSON(w, http.StatusBadGateway, APIError{Error: "policy reload failed"})
	}
	if err := s.refreshSignatures(r.Context()); err != nil {
		log.Printf("signature reload failed: %v", err)
		return WriteJSON(w, http.StatusBadGateway, APIError{Error: "signature reload failed"})
	}
	return WriteJSON(w, http.StatusOK, map[string]any{"status": "reloaded", "version": s.policyVersion(), "signatures": s.signatureCount()})
}

func bearer(r *http.Request, token string) bool {
	return subtle.ConstantTimeCompare([]byte(r.Header.Get("Authorization")), []byte("Bearer "+token)) == 1
}
