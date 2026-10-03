// @vitest-environment node
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { semantic } from './semantic.js';

beforeEach(() => vi.stubGlobal('fetch', vi.fn()));

describe('semantic API', () => {
  it('reads a 503 readiness response while models are loading', async () => {
    const body = { ready: false, models: { prompt_injection: 'loading' } };
    fetch.mockResolvedValue(new Response(JSON.stringify(body), { status: 503 }));
    const signal = new AbortController().signal;
    await expect(semantic.ready(signal)).resolves.toEqual(body);
    expect(fetch).toHaveBeenCalledWith('/semantic/readyz', { signal, headers: {} });
  });

  it('sends the selected scan configuration through the semantic proxy', async () => {
    fetch.mockResolvedValue(new Response(JSON.stringify({ results: [] })));
    const payload = { text: 'Hello', direction: 'input', checks: ['pii_ner'] };
    await semantic.scan(payload);
    expect(fetch).toHaveBeenCalledWith('/semantic/v1/scan', {
      method: 'POST',
      body: JSON.stringify(payload),
      headers: { 'Content-Type': 'application/json' },
    });
  });

  it('shows field-level validation failures instead of a generic API error', async () => {
    fetch.mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: [
            { loc: ['body', 'timeout_ms'], msg: 'Must be at least 10' },
            { loc: ['body', 'checks'], msg: 'Unknown check' },
          ],
        }),
        { status: 422 },
      ),
    );
    await expect(semantic.scan({})).rejects.toThrow(
      'timeout_ms: Must be at least 10; checks: Unknown check',
    );
  });

  it('handles a non-JSON response from an unavailable proxy', async () => {
    fetch.mockResolvedValue(new Response('Bad gateway', { status: 502 }));
    await expect(semantic.scan({})).rejects.toThrow('Semantic service error: 502');
  });
});
