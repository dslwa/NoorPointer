package main

import (
	"flag"
	"log"
	"os"

	"github.com/dslwa/NoorPointer/gateway/api"
)

func main() {
	var (
		listenAddr = flag.String("listenaddr", ":"+env("PORT", "8080"), "gateway listen address")
		upstream   = flag.String("upstream", env("UPSTREAM_LLM_URL", "http://localhost:11434"), "LLM upstream URL")
	)
	flag.Parse()

	server, err := api.NewServer(*listenAddr, *upstream)
	if err != nil {
		log.Fatal(err)
	}
	log.Fatal(server.Start())
}

func env(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
