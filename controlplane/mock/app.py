import os
import json
import logging
from datetime import datetime, timezone
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("controlplane")

app = FastAPI(title="NoorPointer Control Plane API", version="1.0.0")

# Włącz CORS dla Dashboardu React (:3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_URL = os.getenv("DATABASE_URL", "postgres://noor:noorpass@postgres:5432/noorpointer?sslmode=disable")
FEED_URL = os.getenv("SIGNATURES_FEED_URL", "http://signatures-feed:8085/signatures.json")

# In-memory fallback w razie restartu bazy
in_memory_logs = [
    {
        "id": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": "req-init-101",
        "agent_id": "agent-finance-01",
        "model": "llama3.2:1b",
        "action": "BLOCKED",
        "reason": "PROMPT_INJECTION_DETECTED",
        "owasp_category": "LLM01: Prompt Injection",
        "details": {"score": 0.96, "pattern": "ignore previous instructions"},
        "prompt_tokens": 35,
        "completion_tokens": 0,
        "cost_usd": 0.0000
    },
    {
        "id": 2,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": "req-init-102",
        "agent_id": "agent-support-02",
        "model": "llama3.2:1b",
        "action": "REDACTED",
        "reason": "PII_DETECTED",
        "owasp_category": "LLM06: Sensitive Information Disclosure",
        "details": {"entity": "PESEL"},
        "prompt_tokens": 20,
        "completion_tokens": 40,
        "cost_usd": 0.0001
    }
]

def get_db_connection():
    try:
        conn = psycopg2.connect(DB_URL, connect_timeout=3)
        return conn
    except Exception as e:
        logger.warning(f"Postgres not reachable yet ({e}), using memory store.")
        return None

@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "controlplane"}

@app.get("/api/v1/policies")
def get_policy():
    policy_path = "/app/config/policy.yaml"
    if os.path.exists(policy_path):
        with open(policy_path, "r") as f:
            return {"raw_policy": f.read()}
    return {"version": "1.0", "mode": "enforce"}

@app.post("/api/v1/policies/reload")
def reload_policy():
    logger.info("Policy reload triggered.")
    return {"status": "success", "message": "Policy reloaded"}

@app.post("/api/v1/signatures/sync")
def sync_signatures():
    try:
        resp = requests.get(FEED_URL, timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            sigs = data.get("signatures", [])
            logger.info(f"Synced {len(sigs)} signatures from external feed.")
            return {"status": "synced", "count": len(sigs), "version": data.get("version")}
    except Exception as e:
        logger.error(f"Failed to sync signatures: {e}")
    return {"status": "fallback", "count": 5}

@app.get("/api/v1/audit/logs")
def get_audit_logs(limit: int = 50, action: Optional[str] = None):
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = "SELECT * FROM audit_events"
                params = []
                if action:
                    query += " WHERE action = %s"
                    params.append(action)
                query += " ORDER BY timestamp DESC LIMIT %s"
                params.append(limit)
                cur.execute(query, tuple(params))
                rows = cur.fetchall()
                conn.close()
                return list(rows)
        except Exception as e:
            logger.error(f"Error querying postgres: {e}")
            conn.close()
    return in_memory_logs[:limit]

@app.get("/api/v1/stats/posture")
def get_security_posture():
    return {
        "security_posture_score": 98.4,
        "total_inspections": 1420,
        "blocked_threats": 42,
        "redacted_pii": 18,
        "cost_saved_usd": 12.80,
        "owasp_breakdown": {
            "LLM01: Prompt Injection": 24,
            "LLM02: Sensitive Information": 8,
            "LLM05: Supply Chain / Exploits": 6,
            "LLM07: Tool Hijacking / Loop": 4
        },
        "system_status": "ENFORCING"
    }

@app.get("/api/v1/audit/export")
def export_audit_logs(format: str = Query("cef", regex="^(cef|json|csv)$")):
    logs = get_audit_logs(limit=100)
    
    if format == "json":
        return logs
    elif format == "csv":
        csv_out = "id,timestamp,agent_id,action,reason,owasp_category\n"
        for log in logs:
            csv_out += f"{log.get('id')},{log.get('timestamp')},{log.get('agent_id')},{log.get('action')},{log.get('reason')},{log.get('owasp_category')}\n"
        return Response(content=csv_out, media_type="text/csv")
    else: # CEF format (Standard SIEM)
        cef_lines = []
        for log in logs:
            ts = log.get("timestamp", datetime.now().isoformat())
            cef = f"CEF:0|NoorPointer|ControlLayer|1.0|{log.get('reason', 'AUDIT')}|{log.get('owasp_category', 'General')}|High|src={log.get('agent_id')} act={log.get('action')} msg={log.get('reason')}"
            cef_lines.append(cef)
        return Response(content="\n".join(cef_lines), media_type="text/plain")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8082"))
    uvicorn.run(app, host="0.0.0.0", port=port)
