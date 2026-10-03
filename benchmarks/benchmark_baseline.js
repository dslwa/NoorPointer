import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '5s', target: 20 },  // Ramp-up
    { duration: '10s', target: 50 }, // Sustained load
    { duration: '5s', target: 0 },   // Ramp-down
  ],
  thresholds: {
    // Sprawdzenie wymogu SLA z kryteriów oceny jury
    http_req_duration: ['p(95)<10'], // p95 poniżej 10ms dla ścieżki deterministycznej
    http_req_failed: ['rate<0.01'],   // mniej niż 1% błędów
  },
};

const BASE_URL = __ENV.TARGET_URL || 'http://gateway:8080';

// setup() runs once before the first VU: sequential requests warm the gateway + upstream so the
// measured run is not skewed by the cold-start outlier. Return value is passed to default(data).
export function setup() {
  const params = { headers: { 'Content-Type': 'application/json' } };
  const codes = [];
  for (let i = 0; i < 5; i++) {
    codes.push(http.post(`${BASE_URL}/v1/chat/completions`, JSON.stringify({
      model: 'mock-llm',
      agent_id: 'k6-warmup',
      messages: [{ role: 'user', content: 'warm up' }],
    }), params).status);
  }
  console.log(`warm-up responses: ${codes.join(', ')}`);
}

export default function () {
  const payload = JSON.stringify({
    model: 'mock-llm',
    agent_id: 'agent-benchmark',
    messages: [
      { role: 'user', content: 'What is the corporate compliance policy for data classification?' }
    ]
  });

  const params = {
    headers: {
      'Content-Type': 'application/json',
    },
  };

  const res = http.post(`${BASE_URL}/v1/chat/completions`, payload, params);

  check(res, {
    'status is 200': (r) => r.status === 200,
    'latency is below 15ms': (r) => r.timings.duration < 15,
  });

  sleep(0.05);
}
