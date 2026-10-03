import { useState } from 'react';
import { useAction } from '../hooks/useAction.js';
import PromptCheckResults from '../features/prompts/PromptCheckResults.jsx';

export default function PromptCheckPage({ authenticated, gateway, notify, refresh, onEvents }) {
  const [text, setText] = useState('');
  const [report, setReport] = useState(null);
  const { pending, run } = useAction(notify);

  function check() {
    run('check', async () => {
      setReport(null);
      const result = await gateway('/check', {
        method: 'POST',
        body: JSON.stringify({
          direction: 'input',
          messages: [{ role: 'user', content: text }],
        }),
      });
      if (!['allow', 'block', 'redact', 'monitor'].includes(result?.decision))
        throw new Error('Invalid gateway check response.');
      setReport(result);
      if (result.audit_saved) await refresh().catch((error) => notify(error.message, true));
    });
  }

  return (
    <article className="card">
      <div className="card-header">
        <div>
          <h2>Check text with the gateway</h2>
          <p>Go applies its active policy. Thresholds and actions come from Policies.</p>
        </div>
      </div>
      <div className="editor-content">
        <label>
          Text to check
          <textarea
            className="prompt-input"
            aria-label="Text to check"
            maxLength={200000}
            value={text}
            disabled={!!pending}
            placeholder="Paste a prompt…"
            onChange={(event) => {
              setText(event.target.value);
              setReport(null);
            }}
            onKeyDown={(event) => {
              if (
                event.key === 'Enter' &&
                (event.ctrlKey || event.metaKey) &&
                authenticated &&
                text.trim()
              ) {
                event.preventDefault();
                check();
              }
            }}
          />
        </label>
        <p className="help">
          This checks text only. No request is sent to the upstream model. Agent budgets, tool
          permissions and loop limits require a real agent session.
        </p>
      </div>
      <div className="card-footer action-footer">
        <span className={report && !report.audit_saved ? 'prompt-warning' : 'help'} role="status">
          {pending
            ? 'Waiting for the Go gateway…'
            : report
              ? report.audit_saved
                ? 'Saved to Events.'
                : 'Audit was not saved. Check the gateway connection to the control plane.'
              : 'The gateway records each completed check in Events.'}
        </span>
        <div>
          {report?.audit_saved && (
            <button className="button secondary" onClick={onEvents}>
              View in Events
            </button>
          )}
          <button
            className="button primary"
            disabled={!!pending || !authenticated || !text.trim()}
            onClick={check}
          >
            {pending ? 'Checking…' : 'Check text'}
          </button>
        </div>
      </div>
      {report && <PromptCheckResults report={report} showMessages />}
    </article>
  );
}
