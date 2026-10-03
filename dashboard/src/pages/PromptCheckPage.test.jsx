import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import PromptCheckPage from './PromptCheckPage.jsx';

const report = {
  decision: 'block',
  code: 'PROMPT_INJECTION_DETECTED',
  message: 'prompt injection score 0.97',
  policy_version: 12,
  mode: 'enforce',
  findings: [{ control: 'pii_regex', kind: 'pesel', action: 'redact' }],
  semantic: [
    {
      check: 'CHECK_PROMPT_INJECTION',
      status: 'STATUS_OK',
      score: 0.97,
      categories: [],
      passed: false,
    },
  ],
  checks: [
    { control: 'secrets', status: 'passed', action: 'allow', message: 'No findings.' },
    {
      control: 'prompt_injection',
      status: 'failed',
      action: 'block',
      message: 'Gateway policy threshold exceeded.',
    },
  ],
  messages: [{ role: 'user', content: '[REDACTED:pesel]' }],
  audit_saved: true,
  audit_event_id: 'check-1',
};

function setup(overrides = {}) {
  const props = {
    authenticated: true,
    gateway: vi.fn().mockResolvedValue(report),
    notify: vi.fn(),
    refresh: vi.fn().mockResolvedValue(),
    onEvents: vi.fn(),
    ...overrides,
  };
  return { props, user: userEvent.setup(), ...render(<PromptCheckPage {...props} />) };
}

async function submit(user) {
  await user.type(screen.getByRole('textbox', { name: 'Text to check' }), 'A prompt');
  await user.click(screen.getByRole('button', { name: 'Check text' }));
}

describe('Prompt check through the Go gateway', () => {
  it('sends chat messages to the gateway without local thresholds or selected checks', async () => {
    const { user, props } = setup();
    await submit(user);
    await screen.findByText('Saved to Events.');
    expect(props.gateway).toHaveBeenCalledWith('/check', {
      method: 'POST',
      body: JSON.stringify({
        direction: 'input',
        messages: [{ role: 'user', content: 'A prompt' }],
      }),
    });
    expect(screen.queryByRole('spinbutton')).toBeNull();
    expect(screen.getByText('Blocked')).toBeTruthy();
    expect(screen.getByText('Policy version 12 · enforce mode')).toBeTruthy();
    expect(screen.getByRole('progressbar', { name: 'Prompt injection score' }).value).toBe(0.97);
    const controls = screen.getByRole('table', { name: 'Gateway controls' });
    expect(within(controls).getByText('Passed')).toBeTruthy();
    expect(within(controls).getByText('Finding detected')).toBeTruthy();
    expect(screen.getByText('[REDACTED:pesel]')).toBeTruthy();
    expect(props.refresh).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole('button', { name: 'View in Events' }));
    expect(props.onEvents).toHaveBeenCalledTimes(1);
  });

  it('shows timeouts and the actual fail-open decision without calling them passed', async () => {
    const { user } = setup({
      gateway: vi.fn().mockResolvedValue({
        ...report,
        decision: 'monitor',
        code: 'SEMANTIC_UNAVAILABLE',
        message: 'Allowed by fail-open policy',
        findings: [],
        checks: [
          {
            control: 'prompt_injection',
            status: 'error',
            action: 'monitor',
            message: 'Timed out',
          },
        ],
        semantic: [
          { check: 'CHECK_PROMPT_INJECTION', status: 'STATUS_TIMEOUT', score: 0, categories: [] },
        ],
      }),
    });
    await submit(user);
    await screen.findByText('Monitoring');
    expect(screen.queryByText('Passed')).toBeNull();
    expect(
      screen.getByText(
        'Some controls were unavailable or not run. The decision follows the gateway policy.',
      ),
    ).toBeTruthy();
    expect(screen.queryByRole('progressbar')).toBeNull();
  });

  it('warns when the gateway could not persist its audit event', async () => {
    const { user, props } = setup({
      gateway: vi.fn().mockResolvedValue({ ...report, audit_saved: false }),
    });
    await submit(user);
    await screen.findByText(
      'Audit was not saved. Check the gateway connection to the control plane.',
    );
    expect(screen.queryByRole('button', { name: 'View in Events' })).toBeNull();
    expect(props.refresh).not.toHaveBeenCalled();
  });

  it('clears the previous verdict if the next gateway request fails', async () => {
    const { user, props } = setup();
    await submit(user);
    await screen.findByText('Blocked');
    props.gateway.mockRejectedValueOnce(new Error('Cannot reach the Go gateway'));
    await user.click(screen.getByRole('button', { name: 'Check text' }));
    await waitFor(() =>
      expect(props.notify).toHaveBeenCalledWith('Cannot reach the Go gateway', true),
    );
    expect(screen.queryByText('Blocked')).toBeNull();
    expect(screen.queryByText('Saved to Events.')).toBeNull();
    expect(screen.getByRole('button', { name: 'Check text' }).disabled).toBe(false);
  });

  it('prevents duplicate submissions until Go responds', async () => {
    let finish;
    const gateway = vi.fn().mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const { user } = setup({ gateway });
    await submit(user);
    const button = screen.getByRole('button', { name: 'Checking…' });
    await user.click(button);
    expect(gateway).toHaveBeenCalledTimes(1);
    expect(button.disabled).toBe(true);
    await act(async () => finish(report));
    expect(screen.getByRole('button', { name: 'Check text' }).disabled).toBe(false);
  });

  it('does not submit blank text or check without a panel connection', async () => {
    const { user, props } = setup({ authenticated: false });
    await user.type(screen.getByRole('textbox', { name: 'Text to check' }), 'Hello');
    expect(screen.getByRole('button', { name: 'Check text' }).disabled).toBe(true);
    expect(props.gateway).not.toHaveBeenCalled();
  });
});
