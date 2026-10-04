export const labels = {
  prompt_check: 'Prompt check',
  pii_regex: 'Personal data (PII)',
  pii_ner: 'Personal data (NER)',
  leakage: 'System prompt leakage',
  secrets: 'Secrets and API keys',
  prompt_injection: 'Prompt injection',
  content_safety: 'Content safety',
  attack_signatures: 'Attack signatures',
  agent_loops: 'Agent loops',
  mcp_tools: 'MCP tools',
};

// Keep this in sync with policy.schema.json: verdict-only controls cannot redact spans.
export function actionsFor(control) {
  return ['pii_regex', 'pii_ner', 'secrets'].includes(control)
    ? ['block', 'redact', 'monitor']
    : ['block', 'monitor'];
}

export const piiTypes = {
  email: 'Email',
  pesel: 'PESEL',
  iban: 'IBAN',
  card: 'Payment card',
  phone: 'Phone',
  first_name: 'First name',
  last_name: 'Last name',
  full_name: 'Full name',
  date_of_birth: 'Date of birth',
  postal_code: 'Polish postal code',
};
