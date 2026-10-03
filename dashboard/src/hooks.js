import { useEffect, useRef, useState } from 'react';

export function useAction(notify) {
  const [pending, setPending] = useState(null);
  const running = useRef(false);
  async function run(name, action) {
    if (running.current) return;
    running.current = true;
    setPending(name);
    try { await action(); }
    catch (error) { if (error.name !== 'AbortError') notify(error.message, true); }
    finally { running.current = false; setPending(null); }
  }
  return { pending, run };
}

export function useResource(request, path, enabled, revision, notify) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    setLoading(true);
    request(path, { signal: controller.signal }).then(setData).catch(error => {
      if (error.name !== 'AbortError') notify(error.message, true);
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [request, path, enabled, revision, notify]);
  return { data, loading };
}
