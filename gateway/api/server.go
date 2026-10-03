package api

import (
	"context"
	"crypto/rsa"
	"errors"
	"fmt"
	"log"
	"net/http"
	"net/http/httputil"
	"net/url"
	"sync"
	"sync/atomic"
	"time"

	"github.com/dslwa/NoorPointer/gateway/config"
	pb "github.com/dslwa/NoorPointer/gateway/gen/semanticv1"
)

type Server struct {
	listenAddr string
	proxy      *httputil.ReverseProxy
	pubKey     *rsa.PublicKey

	controlPlaneURL string
	gatewayToken    string
	adminToken      string
	controlPlane    *http.Client

	semanticClient pb.SemanticServiceClient

	policy     atomic.Pointer[config.Policy]
	policyMu   sync.Mutex
	policyETag string

	signatures atomic.Pointer[[]signature]
	sigMu      sync.Mutex
	sigETag    string

	quitch chan struct{}
}

func NewServer(listenAddr, upstream string, pubKey *rsa.PublicKey, controlPlaneURL, gatewayToken, adminToken string, semanticClient pb.SemanticServiceClient) (*Server, error) {
	u, err := url.Parse(upstream)
	if err != nil || u.Scheme == "" || u.Host == "" {
		return nil, fmt.Errorf("invalid upstream %q", upstream)
	}
	if gatewayToken == "" || adminToken == "" {
		return nil, errors.New("gateway or admin token is empty")
	}

	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.MaxIdleConnsPerHost = 100

	// -1 flushes every write, so streamed tokens reach the agent as they come.
	proxy := httputil.NewSingleHostReverseProxy(u)
	proxy.FlushInterval = -1
	proxy.Transport = transport

	return &Server{
		listenAddr:      listenAddr,
		proxy:           proxy,
		pubKey:          pubKey,
		controlPlaneURL: controlPlaneURL,
		gatewayToken:    gatewayToken,
		adminToken:      adminToken,
		controlPlane:    &http.Client{Timeout: 3 * time.Second},
		semanticClient:  semanticClient,
		quitch:          make(chan struct{}),
	}, nil
}

func (s *Server) Start() error {
	go s.watchPolicy(time.Second)

	srv := &http.Server{
		Addr:              s.listenAddr,
		Handler:           s.routes(),
		ReadHeaderTimeout: 5 * time.Second,
		IdleTimeout:       120 * time.Second,
	}

	drained := make(chan error, 1)
	go func() {
		<-s.quitch
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		drained <- srv.Shutdown(ctx)
	}()

	log.Printf("gateway running on %s", s.listenAddr)
	if err := srv.ListenAndServe(); !errors.Is(err, http.ErrServerClosed) {
		return err
	}
	// ListenAndServe returns as soon as Shutdown starts; wait for in-flight requests.
	return <-drained
}

// Stop stops polling and drains the server; call it once.
func (s *Server) Stop() {
	close(s.quitch)
}

func (s *Server) routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", makeHTTPHandleFunc(s.handleHealth))
	mux.HandleFunc("GET /readyz", makeHTTPHandleFunc(s.handleReady))
	mux.HandleFunc("POST /admin/policy/reload", makeHTTPHandleFunc(s.handlePolicyReload))
	mux.HandleFunc("POST /admin/check", makeHTTPHandleFunc(s.handleCheck))
	proxy := s.withJWTAuth(s.withPolicy(s.proxy))
	mux.Handle("POST /v1/chat/completions", proxy)
	mux.Handle("GET /v1/models", proxy)
	return mux
}

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) error {
	return WriteJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (s *Server) handleReady(w http.ResponseWriter, r *http.Request) error {
	if s.policy.Load() == nil {
		return WriteJSON(w, http.StatusServiceUnavailable, APIError{Error: "policy not loaded"})
	}
	return WriteJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}
