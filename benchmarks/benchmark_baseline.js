import http from 'k6/http';
import { check, sleep } from 'k6';

// Sciezka zadania obejmuje teraz rowniez kontrole AI (klasyfikator prob oszustwa i dane osobowe).
// Zmierzona przepustowosc tej warstwy na tej maszynie to okolo 13 zadan/s (make bench-semantic),
// dlatego domyslne obciazenie zostaje ponizej tej granicy. Przy wiekszym ruchu usluga nie odpowiada
// w budzecie z polityki (semantic_timeout_ms) i brama - zgodnie z projektem - blokuje zadania,
// bo woli zablokowac niz przepuscic niesprawdzony ruch. Ten drugi przypadek pokazuje make bench-stress.
//
// Parametry (zmienne srodowiskowe):
//   VUS=3            ile rownoleglych klientow
//   DURATION=20s     jak dlugo trwa obciazenie
//   LATENCY_MS=1500  budzet czasu na zadanie (zgodny z semantic_timeout_ms w polityce)

const BASE_URL = __ENV.TARGET_URL || 'http://gateway:8080';
const VUS = Number(__ENV.VUS || 3);
const DURATION = __ENV.DURATION || '20s';
const LATENCY_MS = Number(__ENV.LATENCY_MS || 1500);

export const options = {
  stages: [
    { duration: '5s', target: VUS },   // rozbieg
    { duration: DURATION, target: VUS }, // stale obciazenie
    { duration: '5s', target: 0 },     // wygaszanie
  ],
  thresholds: {
    http_req_duration: [`p(95)<${LATENCY_MS}`],
    http_req_failed: ['rate<0.05'],
  },
};

// The gateway requires an RS256 JWT on every route except /healthz; the Makefile targets mint one
// and pass it as GATEWAY_JWT.
const AUTH = __ENV.GATEWAY_JWT ? { Authorization: `Bearer ${__ENV.GATEWAY_JWT}` } : {};

// setup() runs once before the first VU: sequential requests warm the gateway and the model caches
// so the measured run is not skewed by the cold start. Return value is passed to default(data).
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
      ...AUTH,
    },
  };

  const res = http.post(`${BASE_URL}/v1/chat/completions`, payload, params);

  check(res, {
    'status is 200': (r) => r.status === 200,
    [`latency is below ${LATENCY_MS}ms`]: (r) => r.timings.duration < LATENCY_MS,
  });

  sleep(0.05);
}
