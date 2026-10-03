import { formatNumber, money } from '../utils/formatters.js';

export default function OverviewPage({ dashboard, onPolicies }) {
  const summary = dashboard?.summary;
  const revision = dashboard?.active_policy.revision;
  const categories = Object.entries(summary?.categories || {}).sort((a, b) => b[1] - a[1]);
  const maximum = Math.max(...(summary?.trend || []).map((day) => day.requests), 1);
  const metrics = {
    monthly_usd: 'Monthly cost, USD',
    daily_tokens: 'Daily tokens',
    gpu_seconds_per_hour: 'GPU seconds in the last hour',
  };
  return (
    <>
      <div className="notice">
        <div>
          <strong id="policy-name">
            {revision
              ? `Active policy: ${revision.name}, version ${revision.version}`
              : 'Waiting for connection'}
          </strong>
          <p id="policy-status">
            {revision
              ? `${dashboard.controls_enabled} of ${dashboard.controls_total} controls on, ${revision.document.defaults.mode} mode. The gateway can fetch this configuration.`
              : 'Connect with your token to load the configuration.'}
          </p>
        </div>
        <button className="button ghost small" id="open-policies" onClick={onPolicies}>
          Manage policy
        </button>
      </div>
      <div className="metrics">
        <article className="metric">
          <span>Gateway decisions</span>
          <strong id="stat-requests">{summary ? formatNumber(summary.requests) : '—'}</strong>
          <small>Last 7 days, UTC</small>
        </article>
        <article className="metric">
          <span>Blocked</span>
          <strong id="stat-blocked">{summary ? formatNumber(summary.blocked) : '—'}</strong>
          <small id="block-rate">
            {summary?.requests
              ? `${formatNumber((summary.blocked / summary.requests) * 100)}% of decisions blocked`
              : 'No decisions reported'}
          </small>
        </article>
        <article className="metric">
          <span>Tokens used</span>
          <strong id="stat-tokens">{summary ? formatNumber(summary.tokens) : '—'}</strong>
          <small>From gateway usage reports</small>
        </article>
        <article className="metric">
          <span>API cost</span>
          <strong id="stat-cost">{summary ? money(summary.cost_usd) : '—'}</strong>
          <small>Last 7 days, USD</small>
        </article>
      </div>
      <div className="overview-grid">
        <article className="card">
          <div className="card-header">
            <div>
              <h2>Agent activity</h2>
              <p>Decisions and blocks over the last 7 days</p>
            </div>
            <div className="legend">
              <span>
                <i /> All
              </span>
              <span>
                <i className="blocked" /> Blocked
              </span>
            </div>
          </div>
          <div
            id="trend"
            className="chart"
            role="img"
            aria-label="Agent activity over the last 7 days"
          >
            {(summary?.trend || []).map((day) => (
              <div
                key={day.date}
                className="chart-day"
                title={`${day.date}: ${day.requests} decisions, ${day.blocked} blocked`}
              >
                <span className="chart-count">{day.requests}</span>
                <div className="chart-bars">
                  <i
                    className="chart-bar"
                    style={{ height: `${(day.requests / maximum) * 100}%` }}
                  />
                  <i
                    className="chart-bar blocked"
                    style={{ height: `${(day.blocked / maximum) * 100}%` }}
                  />
                </div>
                <small>
                  {day.date.slice(5, 7)}/{day.date.slice(8)}
                </small>
              </div>
            ))}
          </div>
        </article>
        <article className="card">
          <div className="card-header">
            <div>
              <h2>Block categories</h2>
              <p>As reported by the gateway</p>
            </div>
            <span className="label">OWASP categories</span>
          </div>
          <div id="categories" className={`categories${categories.length ? '' : ' empty'}`}>
            {categories.length
              ? categories.map(([category, count]) => (
                  <div key={category} className="category-row">
                    <div>
                      <span>{category}</span>
                      <strong>{count}</strong>
                    </div>
                    <div className="progress">
                      <i style={{ width: `${(count / summary.blocked) * 100}%` }} />
                    </div>
                  </div>
                ))
              : 'No blocks yet. Connect the gateway or load demo events.'}
          </div>
          <div className="card-footer">
            <span id="control-coverage">
              {dashboard
                ? `${dashboard.controls_enabled} / ${dashboard.controls_total} controls enabled in the policy`
                : '—'}
            </span>
            <small>
              Enabled controls reflect the policy configuration; gateway enforcement is tracked
              separately.
            </small>
          </div>
        </article>
      </div>
      <article className="card">
        <div className="card-header">
          <div>
            <h2>Budgets</h2>
            <p>Usage reported by the gateway, in UTC periods</p>
          </div>
        </div>
        <div id="budgets" className="budget-grid">
          {dashboard?.budgets.length ? (
            dashboard.budgets.map((budget) => {
              const percent =
                budget.limit > 0
                  ? Math.min((budget.used / budget.limit) * 100, 100)
                  : budget.used > 0
                    ? 100
                    : 0;
              return (
                <div key={`${budget.subject}-${budget.metric}`} className="budget-row">
                  <strong>{budget.subject}</strong>
                  <div className="budget-numbers">
                    <span>{metrics[budget.metric]}</span>
                    <span>
                      {formatNumber(budget.used)} / {formatNumber(budget.limit)}
                    </span>
                  </div>
                  <div className={`progress ${budget.used >= budget.limit ? 'over' : ''}`}>
                    <i style={{ width: `${percent}%` }} />
                  </div>
                  <small>When exceeded: {budget.on_exceed}</small>
                </div>
              );
            })
          ) : (
            <div className="empty">No budgets are configured in the active policy.</div>
          )}
        </div>
        <div className="card-footer">
          <small>The gateway enforces limits. This dashboard displays reported usage.</small>
        </div>
      </article>
    </>
  );
}
