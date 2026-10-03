import { useState } from 'react';
import { createApi } from '../../api/client.js';
import { paths } from '../../api/paths.js';
import Modal from '../../components/common/Modal.jsx';

export default function LoginDialog({
  token,
  open,
  required,
  error,
  onError,
  onConnect,
  onDismiss,
}) {
  const [tokenInput, setTokenInput] = useState(token || 'local-dev-admin');
  const [loggingIn, setLoggingIn] = useState(false);
  async function connect(event) {
    event.preventDefault();
    setLoggingIn(true);
    onError('');
    try {
      const nextToken = tokenInput.trim();
      const data = await createApi(nextToken)(paths.dashboard);
      onConnect(nextToken, data);
    } catch (failure) {
      onError(failure.message);
    } finally {
      setLoggingIn(false);
    }
  }
  return (
    <Modal id="login-dialog" open={open} required={required} onDismiss={onDismiss}>
      <form id="login-form" onSubmit={connect}>
        <div className="dialog-heading">
          <span className="brand-mark">
            N<span>↗</span>
          </span>
          <h2>Connect to the control plane</h2>
          <p>Enter your administrator token to access the API.</p>
        </div>
        <label>
          Administrator token
          <input
            id="api-token"
            type="password"
            autoComplete="off"
            value={tokenInput}
            onChange={(event) => setTokenInput(event.target.value)}
            required
          />
        </label>
        <p className="help">
          Default local token: <code>local-dev-admin</code>. You can change it using{' '}
          <code>ADMIN_TOKEN</code>.
        </p>
        <p id="login-error" className="error" role="alert">
          {error}
        </p>
        <button className="button primary full" type="submit" disabled={loggingIn}>
          Connect
        </button>
      </form>
    </Modal>
  );
}
