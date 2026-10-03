export function createApi(token) {
  return async (path, { download = false, ...options } = {}) => {
    const response = await fetch('/api' + path, {
      ...options,
      headers: {
        Authorization: 'Bearer ' + token,
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...options.headers,
      },
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      const error = new Error(body.message || (response.status === 401 ? 'Invalid API token.' : 'API error: ' + response.status));
      error.status = response.status;
      throw error;
    }
    return download ? response.blob() : response.json();
  };
}

export function eventQuery(filters) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) if (value.trim()) query.set(key, value.trim());
  return query;
}

export const labels = {
  pii_regex: 'Personal data (PII)', secrets: 'Secrets and API keys',
  prompt_injection: 'Prompt injection', content_safety: 'Content safety',
  attack_signatures: 'Attack signatures', agent_loops: 'Agent loops', mcp_tools: 'MCP tools',
};
export const formatNumber = value => new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(value);
export const money = value => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 4 }).format(value);
export const formatDate = value => new Date(value).toLocaleString('en-US');
export const exampleFeed = { signatures: [{
  id: 'DEMO-INJECTION-001', name: 'Example prompt injection rule',
  source: 'https://owasp.org/www-project-top-10-for-large-language-model-applications/',
  category: 'LLM01:2025', action: 'block', target: 'prompt',
  match: { type: 'literal', value: 'ignore all previous instructions' },
  description: 'Demonstration rule; does not provide comprehensive prompt injection detection.', enabled: true,
}] };
