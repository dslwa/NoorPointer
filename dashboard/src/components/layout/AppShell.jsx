import { views } from '../../app/navigation.js';

export default function AppShell({ view, onNavigate, connected, onCredentials, children }) {
  return (
    <>
      <aside className="sidebar">
        <a className="brand" href="/">
          <span className="brand-mark">
            N<span>↗</span>
          </span>
          <span>
            NoorPointer<small>AI SECURITY CONTROL PLANE</small>
          </span>
        </a>
        <div className="nav-label">WORKSPACE</div>
        <nav aria-label="Main menu">
          {Object.entries(views).map(([key, item]) => (
            <button
              key={key}
              className={`nav-item ${view === key ? 'active' : ''}`}
              data-view={key}
              aria-current={view === key ? 'page' : undefined}
              onClick={() => onNavigate(key)}
            >
              <span>{item.icon}</span> {item.name}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <span className="status-dot" /> Control plane<small>Configure. Monitor. Control.</small>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <span>
            Workspace <span className="breadcrumb">/</span>{' '}
            <strong id="breadcrumb">{views[view].name}</strong>
          </span>
          <div className="topbar-actions">
            <span className={`connection ${connected ? 'online' : ''}`} id="connection">
              {connected ? 'API connected' : 'Disconnected'}
            </span>
            <button className="button ghost small" id="credentials" onClick={onCredentials}>
              API token
            </button>
          </div>
        </header>
        <div className="content">
          {children}
          <footer className="page-footer">
            NoorPointer <span>Policies · Events · Budgets</span>
          </footer>
        </div>
      </main>
    </>
  );
}
