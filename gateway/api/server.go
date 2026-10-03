package api

import (
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
	controlPlane    *http.Client

	semanticClient pb.SemanticServiceClient

	policy     atomic.Pointer[config.Policy]
	policyMu   sync.Mutex
	policyETag string
}

func NewServer(listenAddr, upstream string, pubKey *rsa.PublicKey, controlPlaneURL, gatewayToken string, semanticClient pb.SemanticServiceClient) (*Server, error) {
	u, err := url.Parse(upstream)
	if err != nil || u.Scheme == "" || u.Host == "" {
		return nil, fmt.Errorf("invalid upstream %q", upstream)
	}
	if gatewayToken == "" {
		return nil, errors.New("gateway token is empty")
	}

	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.MaxIdleConnsPerHost = 100

	// -1 disable response buffering and flush data
	proxy := httputil.NewSingleHostReverseProxy(u)
	proxy.FlushInterval = -1
	proxy.Transport = transport

	return &Server{
		listenAddr:      listenAddr,
		proxy:           proxy,
		pubKey:          pubKey,
		controlPlaneURL: controlPlaneURL,
		gatewayToken:    gatewayToken,
		controlPlane:    &http.Client{Timeout: 3 * time.Second},
		semanticClient:  semanticClient,
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

	log.Printf("gateway running on %s", s.listenAddr)
	return srv.ListenAndServe()
}

func (s *Server) routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", makeHTTPHandleFunc(s.handleHealth))
	mux.HandleFunc("POST /admin/policy/reload", makeHTTPHandleFunc(s.handlePolicyReload))
	mux.Handle("/v1/", s.withJWTAuth(s.withPolicy(s.proxy)))
	return mux
}

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) error {
	return WriteJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}
