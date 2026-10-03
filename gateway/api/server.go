package api

import (
	"crypto/rsa"
	"fmt"
	"log"
	"net/http"
	"net/http/httputil"
	"net/url"
	"time"
)

type Server struct {
	listenAddr string
	proxy      *httputil.ReverseProxy
	pubKey     *rsa.PublicKey
}

func NewServer(listenAddr, upstream string, pubKey *rsa.PublicKey) (*Server, error) {
	u, err := url.Parse(upstream)
	if err != nil || u.Scheme == "" || u.Host == "" {
		return nil, fmt.Errorf("invalid upstream %q", upstream)
	}

	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.MaxIdleConnsPerHost = 100

	// -1 disable response buffering and flush data
	proxy := httputil.NewSingleHostReverseProxy(u)
	proxy.FlushInterval = -1
	proxy.Transport = transport

	return &Server{
		listenAddr: listenAddr,
		proxy:      proxy,
		pubKey:     pubKey,
	}, nil
}

func (s *Server) Start() error {
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
	mux.Handle("/", s.withJWTAuth(s.withPolicy(s.proxy)))
	return mux
}

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) error {
	return WriteJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}
