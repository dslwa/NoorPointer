package main

import (
	"log"
	"os"
	"os/signal"
	"syscall"

	"github.com/dslwa/NoorPointer/gateway/api"
	pb "github.com/dslwa/NoorPointer/gateway/gen/semanticv1"
	"github.com/golang-jwt/jwt/v5"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

func main() {
	if err := run(); err != nil {
		log.Fatal(err)
	}
}

func run() error {
	pem, err := os.ReadFile(env("JWT_PUBLIC_KEY", "keys/jwt.pub"))
	if err != nil {
		return err
	}
	pubKey, err := jwt.ParseRSAPublicKeyFromPEM(pem)
	if err != nil {
		return err
	}

	// NewClient dials lazily: the gateway starts while Python still loads its models.
	conn, err := grpc.NewClient(env("SEMANTIC_GRPC_URL", "localhost:50051"),
		grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return err
	}
	defer conn.Close()

	server, err := api.NewServer(":"+env("PORT", "8080"), env("UPSTREAM_LLM_URL", "http://localhost:11434"), pubKey,
		env("CONTROLPLANE_URL", "http://localhost:8082"), env("GATEWAY_TOKEN", "local-dev-gateway"),
		env("ADMIN_TOKEN", "local-dev-admin"),
		pb.NewSemanticServiceClient(conn))
	if err != nil {
		return err
	}

	go func() {
		sigch := make(chan os.Signal, 1)
		signal.Notify(sigch, syscall.SIGINT, syscall.SIGTERM)
		<-sigch
		server.Stop()
	}()
	return server.Start()
}

func env(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
