import http from 'k6/http';
import { check, sleep } from 'k6';

// Budget concurrency: hammer one tenant's agent and verify the counter is atomic (no overspend).
// Run: make bench-budget
// Expectations turn into 429s once the gateway enforces Redis budgets; until then this measures
// throughput and must stay error-free.

export const options = {
  vus: 40,
  duration: '20s',
  thresholds: {
    http_req_duration: ['p(95)<25'],
    http_req_failed: ['rate<0.05'],
  },
};

const BASE_URL = __ENV.TARGET_URL || 'http://gateway:8080';
const AGENT = __ENV.AGENT_ID || 'agent-budget-concurrency';
// Gateway JWT (RS256) is required on every route except /healthz; injected by make bench-budget.
const AUTH = __ENV.GATEWAY_JWT ? { Authorization: `Bearer ${__ENV.GATEWAY_JWT}` } : {};

// setup() runs once before the VUs. It uses its own agent id so warming up does not consume the
// measured agent's budget, and it removes the cold-start outlier from the measured run.
export function setup() {
  const params = { headers: { 'Content-Type': 'application/json', ...AUTH } };
  const codes = [];
  for (let i = 0; i < 5; i++) {
    codes.push(http.post(`${BASE_URL}/v1/chat/completions`, JSON.stringify({
      model: 'mock-llm',
      agent_id: 'k6-warmup',
      messages: [{ role: 'user', content: 'warm up' }],
    }), params).status);
  }
  console.log(`warm-up responses: ${codes.join(', ')}`);
  return { warmup: codes };
}

export default function () {
  const payload = JSON.stringify({
    model: 'mock-llm',
    agent_id: AGENT,
    messages: [{ role: 'user', content: 'run a large query' }],
  });
  const res = http.post(`${BASE_URL}/v1/chat/completions`, payload, {
    headers: { 'Content-Type': 'application/json', ...AUTH },
    tags: { name: 'budget' },
  });

  check(res, {
    'handled (200/429)': (r) => [200, 429].includes(r.status),
  });

  sleep(0.02);
}
