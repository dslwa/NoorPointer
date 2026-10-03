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

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, s.controlPlaneURL+"/api/gateway/policy", nil)
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+s.gatewayToken)
	if s.policyETag != "" {
		req.Header.Set("If-None-Match", s.policyETag)
	}

	resp, err := s.controlPlane.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	switch resp.StatusCode {
	case http.StatusNotModified:
		return nil
	case http.StatusOK:
	default:
		return fmt.Errorf("control plane returned %s", resp.Status)
	}

	body, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if err != nil {
		return err
	}
	p, err := config.ParsePolicy(body)
	if err != nil {
		return err
	}

	s.policy.Store(p)
	s.policyETag = resp.Header.Get("ETag")
	log.Printf("policy loaded version=%d", p.Version)
	return nil
}

func (s *Server) watchPolicy(every time.Duration) {
	for {
		if err := s.refreshPolicy(context.Background()); err != nil {
			log.Printf("policy refresh failed, keeping version=%d: %v", s.policyVersion(), err)
		}
		time.Sleep(every)
	}
}

func (s *Server) policyVersion() int64 {
	if p := s.policy.Load(); p != nil {
		return p.Version
	}
	return 0
}

func (s *Server) handlePolicyReload(w http.ResponseWriter, r *http.Request) error {
	want := []byte("Bearer " + s.gatewayToken)
	if subtle.ConstantTimeCompare([]byte(r.Header.Get("Authorization")), want) != 1 {
		return WriteJSON(w, http.StatusUnauthorized, APIError{Error: "unauthorized"})
	}
	if err := s.refreshPolicy(r.Context()); err != nil {
		log.Printf("policy reload failed: %v", err)
		return WriteJSON(w, http.StatusBadGateway, APIError{Error: "policy reload failed"})
	}
	return WriteJSON(w, http.StatusOK, map[string]any{"status": "reloaded", "version": s.policyVersion()})
}
