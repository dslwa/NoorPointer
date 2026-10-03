import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import EventsPage from './EventsPage.jsx';

vi.mock('../components/common/Modal.jsx', () => ({
  default: ({ open, children }) => (open ? <div role="dialog">{children}</div> : null),
}));

it('shows the gateway prompt check in Events and displays its persisted results in details', async () => {
  const event = {
    id: 'prompt-check-1',
    occurred_at: '2026-10-03T12:00:00Z',
    kind: 'decision',
    agent_id: 'dashboard-prompt-check',
    control: 'prompt_check',
    action: 'block',
    category: 'LLM01:2025',
    policy_version: 12,
    message: 'prompt injection score 0.97',
    context: {
      source: 'prompt_check',
      mode: 'enforce',
      checks: [
        {
          control: 'prompt_injection',
          status: 'failed',
          action: 'block',
          message: 'Gateway policy threshold exceeded.',
        },
      ],
      findings: [],
      semantic: [
        {
          check: 'CHECK_PROMPT_INJECTION',
          status: 'STATUS_OK',
          score: 0.97,
          passed: false,
          categories: [],
        },
      ],
    },
  };
  const request = vi.fn(async (path) =>
    path.includes('?') ? { items: [event], total: 1 } : event,
  );
  render(<EventsPage active authenticated request={request} refreshKey={1} notify={vi.fn()} />);
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Event details prompt-check-1' }));
  const dialog = await screen.findByRole('dialog');
  expect(within(dialog).getByText('Blocked')).toBeTruthy();
  expect(within(dialog).getByText('Policy version 12 · enforce mode')).toBeTruthy();
  expect(within(dialog).getAllByText('Finding detected')).toHaveLength(2);
  expect(request).toHaveBeenCalledWith('/audit-events/prompt-check-1');
});
