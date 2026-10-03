package api

import (
	"context"
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/dslwa/NoorPointer/gateway/types"
	"github.com/golang-jwt/jwt/v5"
)

type ctxKey struct{}

func claimsFor(r *http.Request) *types.Claims {
	claims, _ := r.Context().Value(ctxKey{}).(*types.Claims)
	return claims
}

func (s *Server) withPolicy(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		claims := claimsFor(r)
		// ponytail: logs identity only, policy checks land here next
		log.Printf("request sub=%s team=%s %s %s", claims.Subject, claims.Team, r.Method, r.URL.Path)
		next.ServeHTTP(w, r)
	})
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
