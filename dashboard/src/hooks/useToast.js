import { useCallback, useEffect, useRef, useState } from 'react';

export function useToast() {
  const [toast, setToast] = useState(null);
  const timer = useRef(null);
  const notify = useCallback((message, error = false) => {
    setToast({ message, error });
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setToast(null), error ? 8500 : 4500);
  }, []);
  useEffect(() => () => clearTimeout(timer.current), []);
  return { toast, notify };
}
