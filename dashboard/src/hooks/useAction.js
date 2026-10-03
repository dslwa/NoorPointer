import { useRef, useState } from 'react';

export function useAction(notify) {
  const [pending, setPending] = useState(null);
  const running = useRef(false);
  async function run(name, action) {
    if (running.current) return;
    running.current = true;
    setPending(name);
    try {
      await action();
    } catch (error) {
      if (error.name !== 'AbortError') notify(error.message, true);
    } finally {
      running.current = false;
      setPending(null);
    }
  }
  return { pending, run };
}
