package types

import "github.com/golang-jwt/jwt/v5"

type Claims struct {
	Team string `json:"team"`
	jwt.RegisteredClaims
}
