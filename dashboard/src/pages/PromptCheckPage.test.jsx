import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { semantic } from '../api/semantic.js';
import PromptCheckPage from './PromptCheckPage.jsx';

vi.mock('../api/semantic.js', () => ({ semantic: { ready: vi.fn(), scan: vi.fn() } }));

function result(check, overrides = {}) {
  return { check, status: 'ok', flagged: false, score: 0.1, details: {}, ...overrides };
}

function response(results) {
  return { results, latency_ms: 25, redacted_text: null };
}

function setup() {
  const notify = vi.fn();
  const user = userEvent.setup();
  const view = render(<PromptCheckPage active notify={notify} />);
  return { notify, user, ...view };
}

async function scanText(user, text = 'What is the capital of France?') {
  await user.type(screen.getByRole('textbox', { name: 'Text to check' }), text);
  await user.click(screen.getByRole('button', { name: 'Check text' }));
  await screen.findByRole('button', { name: 'Check again' });
}

beforeEach(() => {
  semantic.ready.mockResolvedValue({ ready: true });
  semantic.scan.mockResolvedValue(
    response(['prompt_injection', 'content_safety', 'pii_ner'].map((check) => result(check))),
  );
});

describe('Prompt check', () => {
  it('sends only enabled input checks with the configured threshold and timeout', async () => {
    const { user } = setup();
    await user.click(screen.getByRole('checkbox', { name: 'Harmful content' }));
    expect(screen.getByRole('checkbox', { name: 'System prompt leak' }).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('Flag at a score of'), { target: { value: '0.9' } });
    await user.click(screen.getByText('Time limit'));
    fireEvent.change(screen.getByLabelText('Milliseconds each check may take'), {
      target: { value: '1500' },
    });
    await scanText(user, 'Hello');
    expect(semantic.scan).toHaveBeenCalledWith({
      request_id: expect.stringMatching(/^dashboard-\d+$/),
      direction: 'input',
      text: 'Hello',
      checks: ['prompt_injection', 'pii_ner'],
      timeout_ms: 1500,
      config: { prompt_injection: { threshold: 0.9 } },
      context: {},
    });
  });

  it('sends the reference system prompt when checking a model response for leakage', async () => {
    const { user } = setup();
    await user.click(screen.getByRole('button', { name: 'Model response' }));
    await user.click(screen.getByRole('checkbox', { name: 'System prompt leak' }));
    await user.type(
      screen.getByLabelText('System prompt the response must not reveal'),
      'Internal instructions',
    );
    await scanText(user, 'A model response');
    expect(semantic.scan.mock.calls[0][0]).toMatchObject({
      direction: 'output',
      checks: ['prompt_injection', 'content_safety', 'pii_ner', 'leakage'],
      context: { system_prompt: 'Internal instructions' },
    });
  });

  it('shows a clean verdict when every check completes without findings', async () => {
    const { user, container } = setup();
    await scanText(user);
    expect(container.querySelector('#verdict').textContent).toBe('Nothing found by 3 checks');
    expect(container.querySelector('#verdict').classList.contains('clear')).toBe(true);
  });

  it.each(['timeout', 'error', 'rejected', 'skipped'])(
    'does not show a clean verdict when a check is %s',
    async (status) => {
      semantic.scan.mockResolvedValue(
        response([
          result('prompt_injection'),
          result('content_safety', { status, error: 'Check unavailable' }),
        ]),
      );
      const { user, container } = setup();
      await scanText(user);
      const verdict = container.querySelector('#verdict');
      expect(verdict.classList.contains('clear')).toBe(false);
      expect(verdict.textContent).not.toContain('Nothing found');
      expect(screen.getByText('Check unavailable')).toBeTruthy();
    },
  );

  it('does not treat an empty list of results as a successful scan', async () => {
    semantic.scan.mockResolvedValue(response([]));
    const { user, container } = setup();
    await scanText(user);
    expect(container.querySelector('#verdict').classList.contains('clear')).toBe(false);
    expect(container.querySelector('#verdict').textContent).not.toContain('Nothing found');
  });

  it('does not show a clean verdict when a selected check is missing from the response', async () => {
    semantic.scan.mockResolvedValue(response([result('prompt_injection')]));
    const { user, container } = setup();
    await scanText(user);
    expect(container.querySelector('#verdict').classList.contains('clear')).toBe(false);
    expect(container.querySelector('#verdict').textContent).toContain(
      'Some checks did not complete',
    );
  });

  it('keeps a finding visible when another check times out', async () => {
    semantic.scan.mockResolvedValue(
      response([
        result('prompt_injection', { flagged: true, score: 0.98 }),
        result('content_safety', { status: 'timeout' }),
      ]),
    );
    const { user, container } = setup();
    await scanText(user);
    expect(container.querySelector('#verdict').classList.contains('stopped')).toBe(true);
    expect(container.querySelector('#verdict').textContent).toContain(
      '1 of 2 checks found something',
    );
    expect(screen.getByText('Ran out of time')).toBeTruthy();
  });

  it('uses Unicode code-point offsets to highlight PII and displays the redacted copy', async () => {
    semantic.scan.mockResolvedValue({
      ...response([
        result('pii_ner', {
          flagged: true,
          details: { entities: [{ start: 2, end: 5, type: 'PERSON' }] },
        }),
      ]),
      redacted_text: '😀 [PERSON]',
    });
    const { user, container } = setup();
    await scanText(user, '😀 Jan');
    expect(container.querySelector('#scan-result').textContent).toBe('😀 Jan');
    expect(container.querySelector('mark').textContent).toBe('Jan');
    expect(container.querySelector('mark').dataset.type).toBe('name');
    expect(screen.getByText('😀 [PERSON]')).toBeTruthy();
  });

  it('reports a service error and allows a retry', async () => {
    semantic.scan.mockRejectedValueOnce(new Error('Semantic service error: 502'));
    const { user, notify } = setup();
    await user.type(screen.getByRole('textbox', { name: 'Text to check' }), 'Hello');
    await user.click(screen.getByRole('button', { name: 'Check text' }));
    await waitFor(() => expect(notify).toHaveBeenCalledWith('Semantic service error: 502', true));
    await user.click(screen.getByRole('button', { name: 'Check text' }));
    await screen.findByRole('button', { name: 'Check again' });
    expect(semantic.scan).toHaveBeenCalledTimes(2);
  });

  it('prevents duplicate submissions while the service is responding', async () => {
    let finish;
    semantic.scan.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const { user } = setup();
    await user.type(screen.getByRole('textbox', { name: 'Text to check' }), 'Hello');
    await user.click(screen.getByRole('button', { name: 'Check text' }));
    const button = screen.getByRole('button', { name: 'Checking…' });
    expect(button.disabled).toBe(true);
    await user.click(button);
    expect(semantic.scan).toHaveBeenCalledTimes(1);
    await act(async () => finish(response([result('prompt_injection')])));
    expect(screen.getByRole('button', { name: 'Check again' }).disabled).toBe(false);
  });

  it('disables submission for blank text or when no checks are enabled', async () => {
    const { user } = setup();
    const button = screen.getByRole('button', { name: 'Check text' });
    expect(button.disabled).toBe(true);
    await user.type(screen.getByRole('textbox', { name: 'Text to check' }), '   ');
    expect(button.disabled).toBe(true);
    await user.type(screen.getByRole('textbox', { name: 'Text to check' }), 'Hello');
    expect(button.disabled).toBe(false);
    for (const name of ['Prompt injection', 'Harmful content', 'Personal data']) {
      await user.click(screen.getByRole('checkbox', { name }));
    }
    expect(button.disabled).toBe(true);
    expect(semantic.scan).not.toHaveBeenCalled();
  });
});
