// @vitest-environment node
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createApi } from './client.js';

const request = createApi('test-token');

beforeEach(() => vi.stubGlobal('fetch', vi.fn()));

describe('control plane API', () => {
  it('authenticates gateway checks using the panel session without exposing a gateway secret', async () => {
    fetch.mockResolvedValue(new Response(JSON.stringify({ decision: 'allow' })));
    await createApi('panel-token', '/gateway')('/check', { method: 'POST', body: '{}' });
    expect(fetch).toHaveBeenCalledWith('/gateway/check', {
      method: 'POST',
      body: '{}',
      headers: { Authorization: 'Bearer panel-token', 'Content-Type': 'application/json' },
    });
  });
  it('sends authenticated JSON and forwards the cancellation signal', async () => {
    fetch.mockResolvedValue(new Response(JSON.stringify({ version: 4 }), { status: 201 }));
    const signal = new AbortController().signal;
    const body = JSON.stringify({ name: 'strict' });
    await expect(request('/policy-revisions', { method: 'POST', body, signal })).resolves.toEqual({
      version: 4,
    });
    expect(fetch).toHaveBeenCalledWith('/api/v1/policy-revisions', {
      method: 'POST',
      body,
      signal,
      headers: { Authorization: 'Bearer test-token', 'Content-Type': 'application/json' },
    });
  });

  it('accepts an empty 204 response when a policy is deleted', async () => {
    fetch.mockResolvedValue(new Response(null, { status: 204 }));
    await expect(request('/policy-revisions/4', { method: 'DELETE' })).resolves.toBeNull();
  });

  it.each([401, 403, 409])('preserves the message and status of a %s error', async (status) => {
    fetch.mockResolvedValue(
      new Response(JSON.stringify({ message: 'Request denied' }), { status }),
    );
    await expect(request('/policy-revisions/4', { method: 'DELETE' })).rejects.toMatchObject({
      message: 'Request denied',
      status,
    });
  });

  it.each([
    [401, 'Invalid API token.'],
    [502, 'API error: 502'],
  ])('handles non-JSON error responses (%s)', async (status, message) => {
    fetch.mockResolvedValue(new Response('<html>Unavailable</html>', { status }));
    await expect(request('/dashboard')).rejects.toMatchObject({ message, status });
  });

  it('downloads CEF as a blob without attempting to parse it as JSON', async () => {
    const cef = 'CEF:0|NoorPointer|Gateway|1.0|PROMPT_INJECTION|LLM01|8|act=BLOCKED';
    fetch.mockResolvedValue(new Response(cef, { headers: { 'Content-Type': 'text/plain' } }));
    const blob = await request('/audit-events/export?format=cef', { download: true });
    expect(await blob.text()).toBe(cef);
    expect(blob.type).toBe('text/plain');
  });
});
