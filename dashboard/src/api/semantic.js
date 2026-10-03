// The semantic service has no auth of its own; nginx (and the vite dev proxy) expose only these two routes.
async function call(path, options = {}) {
  const response = await fetch('/semantic' + path, {
    ...options,
    headers: options.body ? { 'Content-Type': 'application/json' } : {},
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok && path !== '/readyz') {
    const detail = Array.isArray(body.detail)
      ? body.detail.map((item) => `${item.loc?.slice(1).join('.')}: ${item.msg}`).join('; ')
      : body.detail;
    throw new Error(detail || 'Semantic service error: ' + response.status);
  }
  return body;
}

export const semantic = {
  ready: (signal) => call('/readyz', { signal }),
  scan: (request) => call('/v1/scan', { method: 'POST', body: JSON.stringify(request) }),
};
