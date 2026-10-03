import { views } from '../../app/navigation.js';

export default function AppShell({ view, onNavigate, connected, onCredentials, children }) {
  return (
    <>
      <aside className="sidebar">
        <a className="brand" href="/">
          <span className="brand-mark" aria-hidden="true">
            N
          </span>
          <span>
            NoorPointer<small>Control plane</small>
          </span>
        </a>
        <nav aria-label="Main menu">
          {Object.entries(views).map(([key, item]) => (
            <button
              key={key}
              className={`nav-item ${view === key ? 'active' : ''}`}
              data-view={key}
              aria-current={view === key ? 'page' : undefined}
              onClick={() => onNavigate(key)}
            >
              {item.name}
            </button>
          ))}
        </nav>
      </aside>
      <main>
        <header className="topbar">
          <div className="topbar-actions">
            <span className={`connection ${connected ? 'online' : ''}`} id="connection">
              {connected ? 'API connected' : 'Disconnected'}
            </span>
            <button className="button ghost small" id="credentials" onClick={onCredentials}>
              API token
            </button>
          </div>
        </header>
        <div className="content">{children}</div>
      </main>
    </>
  );
}
