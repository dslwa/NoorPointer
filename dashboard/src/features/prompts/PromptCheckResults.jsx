import { labels } from '../../constants/controls.js';

const names = {
  CHECK_PROMPT_INJECTION: 'Prompt injection',
  CHECK_CONTENT_SAFETY: 'Content safety',
  CHECK_PII_NER: 'Personal data (NER)',
  CHECK_SYSTEM_PROMPT_LEAK: 'System prompt leak',
};

// Gateway controls whose verdict comes from a semantic check: the score is shown in the control's row.
const semanticFor = {
  prompt_injection: 'CHECK_PROMPT_INJECTION',
  content_safety: 'CHECK_CONTENT_SAFETY',
};

const decisions = {
  allow: 'Allowed',
  block: 'Blocked',
  redact: 'Redacted',
  monitor: 'Monitoring',
};

// [label, tone]: tone picks the pill colour.
const statuses = {
  passed: ['Passed', 'pass'],
  failed: ['Finding detected', 'found'],
  error: ['Unavailable', 'trouble'],
  disabled: ['Disabled', 'off'],
  not_run: ['Not run', 'off'],
};

function semanticStatus(result) {
  if (result.status === 'STATUS_OK') {
    if (result.passed === true) return ['Passed', 'pass'];
    if (result.passed === false) return ['Finding detected', 'found'];
    return ['Completed', 'off'];
  }
  return (
    {
      STATUS_TIMEOUT: ['Timed out', 'trouble'],
      STATUS_ERROR: ['Unavailable', 'trouble'],
      STATUS_REJECTED: ['Rejected', 'found'],
    }[result.status] || ['Unknown result', 'trouble']
  );
}

function Score({ name, result }) {
  if (result?.status !== 'STATUS_OK' || !Number.isFinite(result.score)) return null;
  const value = Math.max(0, Math.min(1, result.score));
  return (
    <div className={`prompt-score ${result.passed === false ? 'found' : ''}`}>
      <progress aria-label={`${name} score`} max="1" value={value} />
      <span>{result.score.toFixed(2)}</span>
    </div>
  );
}

function Details({ text, result }) {
  const categories = result?.categories || [];
  return (
    <div className="prompt-details">
      {text && <span>{text}</span>}
      {categories.length > 0 && (
        <span className="prompt-categories">
          {categories.map((code) => (
            <code key={code}>{code}</code>
          ))}
        </span>
      )}
      {result?.error && result.error !== text && <span>{result.error}</span>}
    </div>
  );
}

export default function PromptCheckResults({ report, showMessages = false }) {
  const checks = report.checks || [];
  const semantic = report.semantic || [];
  const findings = report.findings || [];
  const incomplete =
    checks.some((check) => ['error', 'not_run'].includes(check.status)) ||
    semantic.some((result) => result.status !== 'STATUS_OK');
  const shown = new Set(checks.map((check) => semanticFor[check.control]).filter(Boolean));
  const extraSemantic = semantic.filter((result) => !shown.has(result.check));
  const semanticOf = (control) => semantic.find((result) => result.check === semanticFor[control]);

  return (
    <section className="prompt-results" aria-label="Gateway decision">
      <div className={`prompt-verdict ${report.decision}`} role="status">
        <div className="prompt-verdict-head">
          <span className={`badge ${report.decision}`}>
            {decisions[report.decision] || 'Unknown decision'}
          </span>
          {report.code && <code>{report.code}</code>}
        </div>
        <strong>{report.message}</strong>
        <p className="help">
          Policy version {report.policy_version} · {report.mode} mode
        </p>
        {findings.length > 0 && (
          <ul className="prompt-findings" aria-label="Findings">
            {findings.map((finding, index) => (
              <li key={index}>
                {labels[finding.control] || finding.control}: <strong>{finding.kind}</strong>,{' '}
                {finding.action}
              </li>
            ))}
          </ul>
        )}
      </div>

      {incomplete && (
        <p className="prompt-warning">
          Some controls were unavailable or not run. The decision follows the gateway policy.
        </p>
      )}

      {checks.length > 0 && (
        <div className="table-wrap">
          <table className="prompt-table">
            <caption>Gateway controls</caption>
            <thead>
              <tr>
                <th>Control</th>
                <th>Result</th>
                <th>Score</th>
                <th>Action</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {checks.map((check) => {
                const [label, tone] = statuses[check.status] || [check.status, 'off'];
                const name = labels[check.control] || check.control;
                const result = semanticOf(check.control);
                return (
                  <tr key={check.control}>
                    <td className="prompt-control">{name}</td>
                    <td>
                      <span className={`status-pill ${tone}`}>{label}</span>
                    </td>
                    <td>
                      <Score name={name} result={result} />
                    </td>
                    <td className="prompt-action">{check.action || '—'}</td>
                    <td>
                      <Details text={check.message} result={result} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {extraSemantic.length > 0 && (
        <div className="table-wrap">
          <table className="prompt-table">
            <caption>Other semantic results</caption>
            <thead>
              <tr>
                <th>Check</th>
                <th>Result</th>
                <th>Score</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {extraSemantic.map((result, index) => {
                const [label, tone] = semanticStatus(result);
                const name = names[result.check] || result.check;
                return (
                  <tr key={index}>
                    <td className="prompt-control">{name}</td>
                    <td>
                      <span className={`status-pill ${tone}`}>{label}</span>
                    </td>
                    <td>
                      <Score name={name} result={result} />
                    </td>
                    <td>
                      <Details result={result} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {showMessages && report.messages?.length > 0 && (
        <div className="prompt-section">
          <h3>What the model would receive</h3>
          {report.messages.map((message, index) => (
            <div key={index} className="prompt-message">
              <span className="label">{message.role}</span>
              <pre>{message.content}</pre>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
