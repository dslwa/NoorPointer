import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createApi } from './api.js';
import { useAction } from './hooks.js';
import Modal from './components/Modal.jsx';
import Overview from './components/Overview.jsx';
import Policies from './components/Policies.jsx';
import Events from './components/Events.jsx';
import Signatures from './components/Signatures.jsx';

const views = {
  overview: ['Overview', 'Security in one place.', 'Policies, events and usage across your AI agents.', '◫'],
  policies: ['Policies', 'Your policies, under control.', 'Edit configurations and publish new versions for the gateway.', '◇'],
  events: ['Events', 'See what happened.', 'Browse decisions and usage reports received from the gateway.', '≡'],
  signatures: ['Signatures', 'Simple rules. One shared feed.', 'Import signatures and make them available to the gateway.', '⌁'],
};

export default function App() {
  const [token, setToken] = useState(() => sessionStorage.getItem('noorpointer-token'));
  const [tokenInput, setTokenInput] = useState(token || 'local-dev-admin');
  const [loginOpen, setLoginOpen] = useState(!token);
  const [loginError, setLoginError] = useState('');
  const [loggingIn, setLoggingIn] = useState(false);
  const [view, setView] = useState('overview');
  const [dashboard, setDashboard] = useState(null);
  const [connected, setConnected] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [toast, setToast] = useState(null);
  const toastTimer = useRef(null);
  const request = useMemo(() => createApi(token), [token]);
  const notify = useCallback((message, error = false) => {
    setToast({ message, error });
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), error ? 8500 : 4500);
  }, []);
  const { pending, run } = useAction(notify);
  useEffect(() => () => clearTimeout(toastTimer.current), []);

  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    request('/dashboard', { signal: controller.signal }).then(data => {
      setDashboard(data); setConnected(true);
    }).catch(error => {
      if (error.name === 'AbortError') return;
      setConnected(false);
      if (error.status === 401 || error.status === 403) { setLoginError(error.message); setLoginOpen(true); }
      else notify(error.message, true);
    });
    return () => controller.abort();
  }, [request, token, notify]);

  const refresh = useCallback(async () => {
    try {
      setDashboard(await request('/dashboard'));
      setConnected(true); setRefreshKey(value => value + 1);
    } catch (error) { setConnected(false); throw error; }
  }, [request]);
  useEffect(() => {
    if (!token || loginOpen || !['overview', 'events'].includes(view)) return;
    const interval = setInterval(() => {
      if (!document.hidden) refresh().catch(() => setConnected(false));
    }, 15000);
    return () => clearInterval(interval);
  }, [token, loginOpen, view, refresh]);

  async function connect(event) {
    event.preventDefault(); setLoggingIn(true); setLoginError('');
    try {
      const nextToken = tokenInput.trim();
      const data = await createApi(nextToken)('/dashboard');
      sessionStorage.setItem('noorpointer-token', nextToken);
      setToken(nextToken); setDashboard(data); setConnected(true); setLoginOpen(false);
      setRefreshKey(value => value + 1);
    } catch (error) { setLoginError(error.message); }
    finally { setLoggingIn(false); }
  }

  return <>
    <aside className="sidebar">
      <a className="brand" href="/"><span className="brand-mark">N<span>↗</span></span><span>NoorPointer<small>AI SECURITY CONTROL PLANE</small></span></a>
      <div className="nav-label">WORKSPACE</div><nav aria-label="Main menu">{Object.entries(views).map(([key, [name, , , icon]]) =>
        <button key={key} className={`nav-item ${view === key ? 'active' : ''}`} data-view={key} aria-current={view === key ? 'page' : undefined} onClick={() => setView(key)}><span>{icon}</span> {name}</button>)}</nav>
      <div className="sidebar-bottom"><span className="status-dot" /> Control plane<small>Configure. Monitor. Control.</small></div>
    </aside>
    <main><header className="topbar"><span>Workspace <span className="breadcrumb">/</span> <strong id="breadcrumb">{views[view][0]}</strong></span><div className="topbar-actions"><span className={`connection ${connected ? 'online' : ''}`} id="connection">{connected ? 'API connected' : 'Disconnected'}</span><button className="button ghost small" id="credentials" onClick={() => { setLoginError(''); setLoginOpen(true); }}>API token</button></div></header>
      <div className="content"><div className="page-heading"><div><p className="eyebrow">NOORPOINTER / CONTROL CENTER</p><h1 id="page-title">{views[view][1]}</h1><p className="subtitle" id="page-description">{views[view][2]}</p></div>
        <div className="heading-actions"><button className="button secondary" id="refresh" disabled={!!pending || !token} onClick={() => run('refresh', async () => { await refresh(); notify('Data refreshed.'); })}>↻ Refresh</button>
          <button className="button primary" id="demo" hidden={dashboard?.demo_enabled === false} disabled={!!pending || !dashboard} onClick={() => run('demo', async () => {
            const result = await request('/demo/events', { method: 'POST' }); await refresh(); notify(`Added ${result.created} sample events, marked DEMO.`);
          })}>＋ Load demo</button>
        </div>
      </div>
        <section id="overview" className="view" hidden={view !== 'overview'}><Overview dashboard={dashboard} onPolicies={() => setView('policies')} /></section>
        <section id="policies" className="view" hidden={view !== 'policies'}><Policies active={view === 'policies'} request={request} dashboard={dashboard} refreshKey={refreshKey} refresh={refresh} notify={notify} /></section>
        <section id="events" className="view" hidden={view !== 'events'}><Events active={view === 'events'} authenticated={!!dashboard} request={request} refreshKey={refreshKey} notify={notify} /></section>
        <section id="signatures" className="view" hidden={view !== 'signatures'}><Signatures active={view === 'signatures'} authenticated={!!dashboard} request={request} refreshKey={refreshKey} notify={notify} /></section>
        <footer className="page-footer">NoorPointer <span>Policies · Events · Budgets</span></footer>
      </div>
    </main>
    <Modal id="login-dialog" open={loginOpen} required={!dashboard} onDismiss={() => setLoginOpen(false)}>
      <form id="login-form" onSubmit={connect}><div className="dialog-heading"><span className="brand-mark">N<span>↗</span></span><h2>Connect to the control plane</h2><p>Enter your administrator token to access the API.</p></div>
        <label>Administrator token<input id="api-token" type="password" autoComplete="off" value={tokenInput} onChange={event => setTokenInput(event.target.value)} required /></label>
        <p className="help">Default local token: <code>local-dev-admin</code>. You can change it using <code>ADMIN_TOKEN</code>.</p><p id="login-error" className="error" role="alert">{loginError}</p><button className="button primary full" type="submit" disabled={loggingIn}>Connect</button>
      </form>
    </Modal>
    <div id="toast" role="status" aria-live="polite" hidden={!toast} className={toast?.error ? 'error-toast' : ''}>{toast?.message}</div>
  </>;
}
