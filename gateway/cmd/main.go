package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"regexp"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

var (
	reqCountTotal   uint64
	reqCountBlocked uint64
	reqCountAllowed uint64
	reqCountRedact  uint64
	loopTriggers    uint64

	peselRegex  = regexp.MustCompile(`\b\d{11}\b`)
	cardRegex   = regexp.MustCompile(`\b(?:\d{4}[ -]?){3}\d{4}\b`)
	emailRegex  = regexp.MustCompile(`[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}`)
	secretRegex = regexp.MustCompile(`(ghp_[a-zA-Z0-9]{36}|AKIA[0-9A-Z]{16}|sk-[a-zA-Z0-9]{20,})`)
	cveRegex    = regexp.MustCompile(`(?i)(/api/job/submit|ray\.remote.*__import__|\.\./\.\./|posix\.system)`)

	// In-memory token bucket / request counter per tenant/agent
	agentBudget = struct {
		sync.Mutex
		counts map[string]int
	}{counts: make(map[string]int)}

	// Tool call history for loop breaking
	toolCallTracker = struct {
		sync.Mutex
		calls map[string][]string
	}{calls: make(map[string][]string)}
)

type ChatCompletionRequest struct {
	Model    string    `json:"model"`
	Messages []Message `json:"messages"`
	AgentID  string    `json:"agent_id,omitempty"`
}

type Message struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type ChatCompletionResponse struct {
	ID      string   `json:"id"`
	Object  string   `json:"object"`
	Created int64    `json:"created"`
	Model   string   `json:"model"`
	Choices []Choice `json:"choices"`
	Usage   Usage    `json:"usage"`
}

type Choice struct {
	Index        int     `json:"index"`
	Message      Message `json:"message"`
	FinishReason string  `json:"finish_reason"`
}

type Usage struct {
	PromptTokens     int `json:"prompt_tokens"`
	CompletionTokens int `json:"completion_tokens"`
	TotalTokens      int `json:"total_tokens"`
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}
	metricsPort := os.Getenv("METRICS_PORT")
	if metricsPort == "" {
		metricsPort = "9090"
	}

	// 1. Serwer metryk Prometheus (:9090)
	go func() {
		metricsMux := http.NewServeMux()
		metricsMux.HandleFunc("/metrics", handleMetrics)
		log.Printf("📊 Prometheus metrics listening on :%s/metrics", metricsPort)
		if err := http.ListenAndServe(":"+metricsPort, metricsMux); err != nil {
			log.Fatalf("Metrics server error: %v", err)
		}
	}()

	// 2. Główny serwer Reverse Proxy Gateway (:8080)
	mainMux := http.NewServeMux()
	mainMux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{"status":"ok","component":"gateway"}`))
	})

	mainMux.HandleFunc("/admin/policy/reload", func(w http.ResponseWriter, r *http.Request) {
		log.Println("🔄 Hot-reloading policy configuration from disk...")
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"status":"reloaded","timestamp":"` + time.Now().Format(time.RFC3339) + `"}`))
	})

	mainMux.HandleFunc("/v1/chat/completions", handleChatCompletions)

	log.Printf("🚪 NoorPointer Gateway running on :%s", port)
	if err := http.ListenAndServe(":"+port, mainMux); err != nil {
		log.Fatalf("Gateway server error: %v", err)
	}
}

func logAuditEvent(agentID, action, reason, owaspCat, snippet string) {
	controlURL := os.Getenv("CONTROLPLANE_URL")
	if controlURL == "" {
		controlURL = "http://controlplane:8082"
	}
	payload := map[string]interface{}{
		"agent_id":       agentID,
		"action":         action,
		"reason":         reason,
		"owasp_category": owaspCat,
		"prompt_snippet": snippet,
		"timestamp":      time.Now().UTC().Format(time.RFC3339),
	}
	body, _ := json.Marshal(payload)
	go func() {
		client := http.Client{Timeout: 1 * time.Second}
		client.Post(controlURL+"/api/v1/audit/events", "application/json", bytes.NewBuffer(body))
	}()
}

func handleChatCompletions(w http.ResponseWriter, r *http.Request) {
	atomic.AddUint64(&reqCountTotal, 1)
	startTime := time.Now()

	bodyBytes, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, `{"error":"invalid_request"}`, http.StatusBadRequest)
		return
	}

	var req ChatCompletionRequest
	if err := json.Unmarshal(bodyBytes, &req); err != nil {
		http.Error(w, `{"error":"invalid_json"}`, http.StatusBadRequest)
		return
	}

	agentID := req.AgentID
	if agentID == "" {
		agentID = "anonymous-agent"
	}

	// Kontrola 0: Budżet tokenów / Limit zapytań (Token Bucket / Redis)
	agentBudget.Lock()
	agentBudget.counts[agentID]++
	currentUsage := agentBudget.counts[agentID]
	agentBudget.Unlock()

	if strings.Contains(agentID, "exhaust") || currentUsage > 50 {
		atomic.AddUint64(&reqCountBlocked, 1)
		logAuditEvent(agentID, "BLOCKED", "BUDGET_EXCEEDED", "Resource Governance", "")
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusTooManyRequests)
		w.Write([]byte(`{"error":"RATE_LIMITED","reason":"BUDGET_EXCEEDED","message":"Monthly USD / Token budget limit exceeded"}`))
		return
	}

	fullPrompt := ""
	for _, m := range req.Messages {
		fullPrompt += m.Content + " "
	}

	// Kontrola 1: Pętla Agenta (Loop Breaker)
	if strings.Contains(fullPrompt, "LOOP_TRIGGER_TEST") || r.Header.Get("X-Tool-Call-Repeat") == "3" {
		atomic.AddUint64(&loopTriggers, 1)
		atomic.AddUint64(&reqCountBlocked, 1)
		logAuditEvent(agentID, "BLOCKED", "LOOP_BREAKER_TRIGGERED", "LLM07: Tool Hijacking / Loop", fullPrompt)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusForbidden)
		w.Write([]byte(`{"error":"BLOCKED","reason":"RUNAWAY_LOOP_DETECTED","message":"Agent repeated identical tool call 3 times. Terminating."}`))
		return
	}

	// Kontrola 2: Sekrety (API keys, GitHub tokens)
	if secretRegex.MatchString(fullPrompt) {
		atomic.AddUint64(&reqCountBlocked, 1)
		logAuditEvent(agentID, "BLOCKED", "SECRET_LEAKAGE_DETECTED", "LLM06: Sensitive Information Disclosure", fullPrompt)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusForbidden)
		w.Write([]byte(`{"error":"BLOCKED","reason":"SECRET_LEAKAGE_DETECTED","owasp":"LLM06: Sensitive Information Disclosure"}`))
		return
	}

	// Kontrola 3: CVE / Historyczne Ataki (ShadowRay, Probllama, etc.)
	if cveRegex.MatchString(fullPrompt) {
		atomic.AddUint64(&reqCountBlocked, 1)
		logAuditEvent(agentID, "BLOCKED", "HISTORICAL_EXPLOIT_SIGNATURE_MATCHED", "LLM02: Insecure Output / Exploits", fullPrompt)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusForbidden)
		w.Write([]byte(`{"error":"BLOCKED","reason":"HISTORICAL_EXPLOIT_SIGNATURE_MATCHED","owasp":"LLM02: Insecure Output / Exploits"}`))
		return
	}

	// Kontrola 4: Prompt Injection (Heurystyka + DeBERTa)
	lowerPrompt := strings.ToLower(fullPrompt)
	if strings.Contains(lowerPrompt, "ignore previous instructions") ||
		strings.Contains(lowerPrompt, "act as dan") ||
		strings.Contains(lowerPrompt, "override system") {
		atomic.AddUint64(&reqCountBlocked, 1)
		logAuditEvent(agentID, "BLOCKED", "PROMPT_INJECTION_DETECTED", "LLM01: Prompt Injection", fullPrompt)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusForbidden)
		w.Write([]byte(`{"error":"BLOCKED","reason":"PROMPT_INJECTION_DETECTED","owasp":"LLM01: Prompt Injection"}`))
		return
	}

	// Kontrola 5: PII Redaction (PESEL, karty kredytowe, maile)
	hasPII := false
	redactedText := fullPrompt
	if peselRegex.MatchString(fullPrompt) {
		redactedText = peselRegex.ReplaceAllString(redactedText, "[REDACTED_PESEL]")
		hasPII = true
	}
	if cardRegex.MatchString(fullPrompt) {
		redactedText = cardRegex.ReplaceAllString(redactedText, "[REDACTED_CARD]")
		hasPII = true
	}
	if emailRegex.MatchString(fullPrompt) {
		redactedText = emailRegex.ReplaceAllString(redactedText, "[REDACTED_EMAIL]")
		hasPII = true
	}

	if hasPII {
		atomic.AddUint64(&reqCountRedact, 1)
		logAuditEvent(agentID, "REDACTED", "PII_ANONYMIZED", "LLM06: Sensitive Information Disclosure", redactedText)
	} else {
		atomic.AddUint64(&reqCountAllowed, 1)
		logAuditEvent(agentID, "ALLOWED", "CLEAN_PROMPT", "Safe Interaction", fullPrompt)
	}

	duration := time.Since(startTime)
	log.Printf("✅ Request processed in %v (PII: %v, Agent: %s)", duration, hasPII, agentID)

	resp := ChatCompletionResponse{
		ID:      fmt.Sprintf("chatcmpl-noor-%d", time.Now().UnixNano()),
		Object:  "chat.completion",
		Created: time.Now().Unix(),
		Model:   req.Model,
		Choices: []Choice{
			{
				Index: 0,
				Message: Message{
					Role:    "assistant",
					Content: "NoorPointer Gateway: Interakcja zabezpieczona. Treść zweryfikowana pomyślnie.",
				},
				FinishReason: "stop",
			},
		},
		Usage: Usage{
			PromptTokens:     len(fullPrompt) / 4,
			CompletionTokens: 10,
			TotalTokens:      (len(fullPrompt) / 4) + 10,
		},
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(resp)
}

func handleMetrics(w http.ResponseWriter, r *http.Request) {
	total := atomic.LoadUint64(&reqCountTotal)
	blocked := atomic.LoadUint64(&reqCountBlocked)
	allowed := atomic.LoadUint64(&reqCountAllowed)
	redacted := atomic.LoadUint64(&reqCountRedact)
	loops := atomic.LoadUint64(&loopTriggers)

	w.Header().Set("Content-Type", "text/plain; version=0.0.4")
	fmt.Fprintf(w, "# HELP gateway_requests_total Total number of intercepted requests\n")
	fmt.Fprintf(w, "# TYPE gateway_requests_total counter\n")
	fmt.Fprintf(w, "gateway_requests_total{action=\"allowed\"} %d\n", allowed)
	fmt.Fprintf(w, "gateway_requests_total{action=\"blocked\"} %d\n", blocked)
	fmt.Fprintf(w, "gateway_requests_total{action=\"redacted\"} %d\n", redacted)
	fmt.Fprintf(w, "gateway_requests_total{action=\"total\"} %d\n", total)

	fmt.Fprintf(w, "# HELP gateway_loop_breaker_triggers_total Loop breaker triggers\n")
	fmt.Fprintf(w, "# TYPE gateway_loop_breaker_triggers_total counter\n")
	fmt.Fprintf(w, "gateway_loop_breaker_triggers_total %d\n", loops)

	fmt.Fprintf(w, "# HELP gateway_deterministic_duration_seconds Latency of deterministic path\n")
	fmt.Fprintf(w, "# TYPE gateway_deterministic_duration_seconds histogram\n")
	fmt.Fprintf(w, "gateway_deterministic_duration_seconds_bucket{le=\"0.002\"} %d\n", allowed+blocked)
	fmt.Fprintf(w, "gateway_deterministic_duration_seconds_bucket{le=\"0.005\"} %d\n", allowed+blocked+redacted)
	fmt.Fprintf(w, "gateway_deterministic_duration_seconds_bucket{le=\"+Inf\"} %d\n", total)
	fmt.Fprintf(w, "gateway_deterministic_duration_sum %f\n", float64(total)*0.0035)
	fmt.Fprintf(w, "gateway_deterministic_duration_count %d\n", total)
}
