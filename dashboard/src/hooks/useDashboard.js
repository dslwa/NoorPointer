import { useCallback, useEffect, useState } from 'react';
import { paths } from '../api/paths.js';

export function useDashboard({ request, token, view, loginOpen, notify, onUnauthorized }) {
  const [dashboard, setDashboard] = useState(null);
  const [connected, setConnected] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const acceptConnection = useCallback((data) => {
    setDashboard(data);
    setConnected(true);
    setRefreshKey((value) => value + 1);
  }, []);

  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    request(paths.dashboard, { signal: controller.signal })
      .then((data) => {
        setDashboard(data);
        setConnected(true);
      })
      .catch((error) => {
        if (error.name === 'AbortError') return;
        setConnected(false);
        if (error.status === 401 || error.status === 403) onUnauthorized(error.message);
        else notify(error.message, true);
      });
    return () => controller.abort();
  }, [request, token, notify, onUnauthorized]);

  const refresh = useCallback(async () => {
    try {
      acceptConnection(await request(paths.dashboard));
    } catch (error) {
      setConnected(false);
      if (error.status === 401 || error.status === 403) onUnauthorized(error.message);
      throw error;
    }
  }, [request, acceptConnection, onUnauthorized]);

  useEffect(() => {
    if (!token || loginOpen || !['overview', 'events'].includes(view)) return;
    const interval = setInterval(() => {
      if (!document.hidden) refresh().catch(() => setConnected(false));
    }, 15000);
    return () => clearInterval(interval);
  }, [token, loginOpen, view, refresh]);

  return { dashboard, connected, refreshKey, refresh, acceptConnection };
}
