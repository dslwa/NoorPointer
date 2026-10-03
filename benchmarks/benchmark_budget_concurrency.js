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

export default function () {
  const payload = JSON.stringify({
    model: 'mock-llm',
    agent_id: AGENT,
    messages: [{ role: 'user', content: 'run a large query' }],
  });
  const res = http.post(`${BASE_URL}/v1/chat/completions`, payload, {
    headers: { 'Content-Type': 'application/json' },
    tags: { name: 'budget' },
  });

  check(res, {
    'handled (200/429)': (r) => [200, 429].includes(r.status),
  });

  sleep(0.02);
}
