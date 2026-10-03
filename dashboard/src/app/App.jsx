import { useCallback, useMemo, useState } from 'react';
import { createApi } from '../api/client.js';
import { paths } from '../api/paths.js';
import { useAction } from '../hooks/useAction.js';
import { useDashboard } from '../hooks/useDashboard.js';
import { useToast } from '../hooks/useToast.js';
import AppShell from '../components/layout/AppShell.jsx';
import PageHeading from '../components/layout/PageHeading.jsx';
import Toast from '../components/common/Toast.jsx';
import LoginDialog from '../features/auth/LoginDialog.jsx';
import OverviewPage from '../pages/OverviewPage.jsx';
import PoliciesPage from '../pages/PoliciesPage.jsx';
import EventsPage from '../pages/EventsPage.jsx';
import SignaturesPage from '../pages/SignaturesPage.jsx';
import PromptCheckPage from '../pages/PromptCheckPage.jsx';

export default function App() {
  const [token, setToken] = useState(() => sessionStorage.getItem('noorpointer-token'));
  const [loginOpen, setLoginOpen] = useState(!token);
  const [loginError, setLoginError] = useState('');
  const [view, setView] = useState('overview');
  const { toast, notify } = useToast();
  const { pending, run } = useAction(notify);
  const request = useMemo(() => createApi(token), [token]);
  const gateway = useMemo(() => createApi(token, '/gateway'), [token]);
  const onUnauthorized = useCallback((message) => {
    setLoginError(message);
    setLoginOpen(true);
  }, []);
  const { dashboard, connected, refreshKey, refresh, acceptConnection } = useDashboard({
    request,
    token,
    view,
    loginOpen,
    notify,
    onUnauthorized,
  });

  function connect(nextToken, data) {
    sessionStorage.setItem('noorpointer-token', nextToken);
    setToken(nextToken);
    acceptConnection(data);
    setLoginOpen(false);
  }
  function loadDemo() {
    run('demo', async () => {
      const result = await request(paths.demoBatches, { method: 'POST' });
      await refresh();
      notify(`Added ${result.created} sample events, marked DEMO.`);
    });
  }

  return (
    <>
      <AppShell
        view={view}
        onNavigate={setView}
        connected={connected}
        onCredentials={() => {
          setLoginError('');
          setLoginOpen(true);
        }}
      >
        <PageHeading
          view={view}
          pending={pending}
          authenticated={!!token}
          dashboard={dashboard}
          onRefresh={() =>
            run('refresh', async () => {
              await refresh();
              notify('Data refreshed.');
            })
          }
          onDemo={loadDemo}
        />
        <section id="overview" className="view" hidden={view !== 'overview'}>
          <OverviewPage dashboard={dashboard} onPolicies={() => setView('policies')} />
        </section>
        <section id="policies" className="view" hidden={view !== 'policies'}>
          <PoliciesPage
            active={view === 'policies'}
            request={request}
            dashboard={dashboard}
            refreshKey={refreshKey}
            refresh={refresh}
            notify={notify}
          />
        </section>
        <section id="events" className="view" hidden={view !== 'events'}>
          <EventsPage
            active={view === 'events'}
            authenticated={!!dashboard}
            request={request}
            refreshKey={refreshKey}
            notify={notify}
          />
        </section>
        <section id="signatures" className="view" hidden={view !== 'signatures'}>
          <SignaturesPage
            active={view === 'signatures'}
            authenticated={!!dashboard}
            request={request}
            refreshKey={refreshKey}
            notify={notify}
          />
        </section>
        <section id="prompt" className="view" hidden={view !== 'prompt'}>
          <PromptCheckPage
            authenticated={!!dashboard}
            gateway={gateway}
            notify={notify}
            refresh={refresh}
            onEvents={() => setView('events')}
          />
        </section>
      </AppShell>
      <LoginDialog
        token={token}
        open={loginOpen}
        required={!dashboard}
        error={loginError}
        onError={setLoginError}
        onConnect={connect}
        onDismiss={() => setLoginOpen(false)}
      />
      <Toast toast={toast} />
    </>
  );
}
