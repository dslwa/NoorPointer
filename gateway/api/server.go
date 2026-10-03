package api

import (
	"fmt"
	"log"
	"net/http"
	"net/http/httputil"
	"net/url"
)

type Server struct {
	listenAddr string
	proxy      *httputil.ReverseProxy
}

func NewServer(listenAddr, upstream string) (*Server, error) {
	u, err := url.Parse(upstream)
	if err != nil || u.Scheme == "" || u.Host == "" {
		return nil, fmt.Errorf("invalid upstream %q", upstream)
	}

	// -1 disable response buffering and flush data
	proxy := httputil.NewSingleHostReverseProxy(u)
	proxy.FlushInterval = -1

	return &Server{
		listenAddr: listenAddr,
		proxy:      proxy,
	}, nil
}

func (s *Server) Start() error {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", makeHTTPHandleFunc(s.handleHealth))
	mux.Handle("/", s.proxy)

	log.Printf("gateway running on %s", s.listenAddr)
	return http.ListenAndServe(s.listenAddr, mux)
}

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) error {
	return WriteJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}
