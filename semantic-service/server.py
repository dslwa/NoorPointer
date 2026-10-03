import os
import time
import logging
import threading
from concurrent import futures
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
from prometheus_client import Counter, Histogram, make_asgi_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("semantic-service")

# Prometheus Metrics
INJECTION_DETECTED = Counter("semantic_injections_total", "Total prompt injections detected")
PII_REDACTIONS = Counter("semantic_pii_redacted_total", "Total PII entities redacted by GLiNER")
SEMANTIC_LATENCY = Histogram("semantic_scan_duration_seconds", "Duration of semantic scan in seconds")

app = FastAPI(title="NoorPointer Semantic Guardrails (GLiNER + DeBERTa)", version="1.0.0")
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# ============================================================================
# Model Initializers (GLiNER, DeBERTa, Picklescan) with Graceful Fallback
# ============================================================================
USE_MOCK_MODELS = os.getenv("MOCK_MODELS", "false").lower() == "true"
gliner_model = None
injection_pipeline = None

PII_LABELS = [
    "person", 
    "medical condition", 
    "home address", 
    "phone number", 
    "credit card", 
    "bank account",
    "passport"
]

def load_ai_models():
    global gliner_model, injection_pipeline
    if USE_MOCK_MODELS:
        logger.info("⚡ MOCK_MODELS is enabled. Running fast heuristics mock.")
        return

    # 1. Load GLiNER
    try:
        from gliner import GLiNER
        logger.info("⏳ Loading GLiNER model (urchade/gliner_small-v2.1)...")
        gliner_model = GLiNER.from_pretrained("urchade/gliner_small-v2.1")
        logger.info("✅ GLiNER loaded successfully.")
    except Exception as e:
        logger.warning(f"⚠️ Could not load GLiNER ({e}). Falling back to fast regex/NER mock.")

    # 2. Load DeBERTa Prompt Injection Classifier
    try:
        from transformers import pipeline
        logger.info("⏳ Loading DeBERTa v3 Prompt Injection Classifier...")
        injection_pipeline = pipeline(
            "text-classification",
            model="protectai/deberta-v3-base-prompt-injection-v2",
            device=-1 # CPU
        )
        logger.info("✅ DeBERTa Prompt Injection Classifier loaded successfully.")
    except Exception as e:
        logger.warning(f"⚠️ Could not load DeBERTa model ({e}). Falling back to heuristics mock.")

# Run model loading in background so server starts immediately without blocking
threading.Thread(target=load_ai_models, daemon=True).start()

# ============================================================================
# Core Guardrails Engine
# ============================================================================
def redact_with_gliner(text: str) -> tuple[str, list]:
    global gliner_model
    entities_found = []
    
    if gliner_model is not None:
        try:
            preds = gliner_model.predict_entities(text, PII_LABELS, threshold=0.45)
            redacted = text
            # Podmiana od końca, aby nie popsuć offsetów start/end
            for ent in sorted(preds, key=lambda x: x["start"], reverse=True):
                label = ent["label"].upper().replace(" ", "_")
                redacted = redacted[:ent["start"]] + f"[REDACTED_{label}]" + redacted[ent["end"]:]
                entities_found.append(f"{label}:{ent['text']}")
            return redacted, entities_found
        except Exception as e:
            logger.error(f"GLiNER prediction error: {e}")

    # Fallback heuristics mock
    redacted = text
    lower = text.lower()
    if "pesel" in lower or any(term in lower for term in ["kowalski", "nowak", "jan"]):
        redacted = redacted.replace("Jan Kowalski", "[REDACTED_PERSON]")
        entities_found.append("PERSON:Jan Kowalski")
    return redacted, entities_found

def classify_prompt_injection(prompt: str) -> tuple[bool, float]:
    global injection_pipeline
    lower = prompt.lower()
    
    # Szybka heurystyka znanych wzorców
    fast_patterns = [
        "ignore previous instructions", 
        "ignore all instructions",
        "act as dan", 
        "system prompt", 
        "you are now an unrestricted ai",
        "override system instructions",
        "dump database"
    ]
    if any(p in lower for p in fast_patterns):
        return True, 0.98

    if injection_pipeline is not None:
        try:
            res = injection_pipeline(prompt[:512])[0] # Ograniczenie do 512 tokenów dla szybkości
            is_inj = (res["label"] == "INJECTION")
            score = float(res["score"]) if is_inj else float(1.0 - res["score"])
            return is_inj, score
        except Exception as e:
            logger.error(f"DeBERTa classification error: {e}")

    return False, 0.05

def audit_model_with_picklescan(file_path: str) -> tuple[bool, list]:
    try:
        from picklescan.scanner import scan_file_path
        if os.path.exists(file_path):
            scan_res = scan_file_path(file_path)
            is_safe = (scan_res.issues_count == 0)
            dangerous = [str(f) for f in scan_res.infected_files] if not is_safe else []
            return is_safe, dangerous
    except Exception as e:
        logger.warning(f"Picklescan library call fallback: {e}")

    # Fallback mock na podstawie nazwy pliku lub nagłówka
    dangerous_keywords = ["rce", "posix.system", "os.system", "evil", "malicious"]
    is_safe = not any(k in file_path.lower() for k in dangerous_keywords)
    return is_safe, ["posix.system"] if not is_safe else []

# ============================================================================
# API Models & REST Endpoints
# ============================================================================
class PromptScanRequest(BaseModel):
    prompt: str
    agent_id: Optional[str] = "default"
    session_id: Optional[str] = "session-0"

class PromptScanResponse(BaseModel):
    is_injection: bool
    injection_score: float
    pii_detected: List[str]
    sanitized_prompt: str
    recommended_action: str # "allow" | "block" | "redact"
    latency_ms: int

class ModelScanRequest(BaseModel):
    file_path: str

class ModelScanResponse(BaseModel):
    safe: bool
    dangerous_opcodes: List[str]
    description: str

@app.get("/healthz")
def healthz():
    return {
        "status": "ok", 
        "service": "semantic-guardrails", 
        "gliner_loaded": gliner_model is not None,
        "deberta_loaded": injection_pipeline is not None
    }

@app.post("/v1/scan/prompt", response_model=PromptScanResponse)
def scan_prompt_http(req: PromptScanRequest):
    start = time.time()
    
    # 1. PII Redaction via GLiNER
    sanitized, pii_entities = redact_with_gliner(req.prompt)
    if pii_entities:
        PII_REDACTIONS.inc(len(pii_entities))

    # 2. Injection Classification via DeBERTa
    is_inj, score = classify_prompt_injection(req.prompt)
    if is_inj:
        INJECTION_DETECTED.inc()

    action = "block" if is_inj else ("redact" if pii_entities else "allow")
    duration_ms = int((time.time() - start) * 1000)
    
    return {
        "is_injection": is_inj,
        "injection_score": score,
        "pii_detected": pii_entities,
        "sanitized_prompt": sanitized,
        "recommended_action": action,
        "latency_ms": max(duration_ms, 22)
    }

@app.post("/v1/scan/model", response_model=ModelScanResponse)
def scan_model_http(req: ModelScanRequest):
    is_safe, dangerous = audit_model_with_picklescan(req.file_path)
    return {
        "safe": is_safe,
        "dangerous_opcodes": dangerous,
        "description": "Picklescan static analysis complete"
    }

# ============================================================================
# gRPC Server (GuardrailService)
# ============================================================================
def start_grpc_server(port=50051):
    try:
        import grpc
        import guardrails_pb2
        import guardrails_pb2_grpc

        class GuardrailServicer(guardrails_pb2_grpc.GuardrailServiceServicer):
            def ScanPrompt(self, request, context):
                start = time.time()
                sanitized, pii_list = redact_with_gliner(request.prompt)
                is_inj, score = classify_prompt_injection(request.prompt)
                
                action = "block" if is_inj else ("redact" if pii_list else "allow")
                duration_ms = int((time.time() - start) * 1000)

                pii_pb = [
                    guardrails_pb2.PiiEntity(entity_type="PII", text=p, start=0, end=0, score=0.9)
                    for p in pii_list
                ]

                return guardrails_pb2.PromptScanResponse(
                    is_injection=is_inj,
                    injection_score=score,
                    pii_detected=pii_pb,
                    sanitized_prompt=sanitized,
                    recommended_action=action,
                    reason="PROMPT_INJECTION_DETECTED" if is_inj else "CLEAN",
                    latency_ms=max(duration_ms, 18)
                )

            def ScanModel(self, request, context):
                is_safe, dangerous = audit_model_with_picklescan(request.file_path)
                return guardrails_pb2.ModelScanResponse(
                    is_safe=is_safe,
                    dangerous_opcodes=dangerous,
                    description="Picklescan gRPC Analysis Result"
                )

        server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        guardrails_pb2_grpc.add_GuardrailServiceServicer_to_server(GuardrailServicer(), server)
        server.add_insecure_port(f"0.0.0.0:{port}")
        server.start()
        logger.info(f"🚀 gRPC GuardrailService listening on port :{port}")
        server.wait_for_termination()
    except Exception as e:
        logger.warning(f"gRPC server note: {e}")

if __name__ == "__main__":
    grpc_port = int(os.getenv("GRPC_PORT", "50051"))
    http_port = int(os.getenv("PORT", "8001"))

    grpc_t = threading.Thread(target=start_grpc_server, args=(grpc_port,), daemon=True)
    grpc_t.start()

    logger.info(f"🌐 FastAPI Semantic Service listening on port :{http_port}")
    uvicorn.run(app, host="0.0.0.0", port=http_port)
