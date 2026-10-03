export const exampleFeed = {
  signatures: [
    {
      id: 'DEMO-INJECTION-001',
      name: 'Example prompt injection rule',
      source: 'https://owasp.org/www-project-top-10-for-large-language-model-applications/',
      category: 'LLM01:2025',
      action: 'block',
      target: 'prompt',
      match: { type: 'literal', value: 'ignore all previous instructions' },
      description: 'Demonstration rule; does not provide comprehensive prompt injection detection.',
      enabled: true,
    },
  ],
};
