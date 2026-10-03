import { labels } from '../../constants/controls.js';

const names = {
  CHECK_PROMPT_INJECTION: 'Prompt injection',
  CHECK_CONTENT_SAFETY: 'Content safety',
  CHECK_PII_NER: 'Personal data (NER)',
  CHECK_SYSTEM_PROMPT_LEAK: 'System prompt leak',
};

const statuses = {
  passed: 'Passed',
  failed: 'Finding detected',
  error: 'Unavailable',
  disabled: 'Disabled',
  not_run: 'Not run',
};

function semanticStatus(result) {
  if (result.status === 'STATUS_OK') {
    if (result.passed === true) return 'Passed';
    if (result.passed === false) return 'Finding detected';
    return 'Completed';
  }
  return (
    {
      STATUS_TIMEOUT: 'Timed out',
      STATUS_ERROR: 'Unavailable',
      STATUS_REJECTED: 'Rejected',
    }[result.status] || 'Unknown result'
  );
}

export default function PromptCheckResults({ report, showMessages = false }) {
  const checks = report.checks || [];
  const semantic = report.semantic || [];
  const findings = report.findings || [];
  const incomplete =
    checks.some((check) => ['error', 'not_run'].includes(check.status)) ||
    semantic.some((result) => result.status !== 'STATUS_OK');
  return (
    <div className="prompt-results">
      <div className="prompt-verdict" role="status">
        <span className={`badge ${report.decision}`}>
          {{ allow: 'Allowed', block: 'Blocked', redact: 'Redacted', monitor: 'Monitoring' }[
            report.decision
          ] || 'Unknown decision'}
        </span>
        <strong>{report.message}</strong>
        <p className="help">
          Policy version {report.policy_version} · {report.mode} mode
        </p>
        {report.code && <code>{report.code}</code>}
      </div>
      {incomplete && (
        <p className="prompt-warning">
          Some controls were unavailable or not run. The decision follows the gateway policy.
        </p>
      )}
      {checks.length > 0 && (
        <div className="table-wrap">
          <table>
            <caption>Gateway controls</caption>
            <thead>
              <tr>
                <th>Control</th>
                <th>Result</th>
                <th>Action</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {checks.map((check) => (
                <tr key={check.control}>
                  <td>{labels[check.control] || check.control}</td>
                  <td>{statuses[check.status] || check.status}</td>
                  <td>{check.action || '—'}</td>
                  <td>{check.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {findings.length > 0 && (
        <div className="prompt-section">
          <h3>Findings</h3>
          <ul>
            {findings.map((finding, index) => (
              <li key={index}>
                {labels[finding.control] || finding.control}: {finding.kind} — {finding.action}
              </li>
            ))}
          </ul>
        </div>
      )}
      {semantic.length > 0 && (
        <div className="table-wrap">
          <table>
            <caption>Semantic results returned by Go</caption>
            <thead>
              <tr>
                <th>Check</th>
                <th>Result</th>
                <th>Score</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {semantic.map((result, index) => (
                <tr key={index}>
                  <td>{names[result.check] || result.check}</td>
                  <td>{semanticStatus(result)}</td>
                  <td>
                    {result.status === 'STATUS_OK' && Number.isFinite(result.score) ? (
                      <div className="prompt-score">
                        <progress
                          aria-label={`${names[result.check] || result.check} score`}
                          max="1"
                          value={Math.max(0, Math.min(1, result.score))}
                        />
                        {result.score.toFixed(2)}
                      </div>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td>{result.error || result.categories?.join(', ') || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {showMessages && report.messages?.length > 0 && (
        <div className="prompt-section">
          <h3>Messages after gateway checks</h3>
          {report.messages.map((message, index) => (
            <div key={index}>
              <span className="label">{message.role}</span>
              <pre>{message.content}</pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
