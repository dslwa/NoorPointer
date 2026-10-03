export default function Toast({ toast }) {
  return (
    <div
      id="toast"
      role="status"
      aria-live="polite"
      hidden={!toast}
      className={toast?.error ? 'error-toast' : ''}
    >
      {toast?.message}
    </div>
  );
}
