import { useEffect, useRef, useState } from 'react';
import { formatDate } from '../utils/formatters.js';
import { labels } from '../constants/controls.js';
import { useAction } from '../hooks/useAction.js';
import { useResource } from '../hooks/useResource.js';
import { paths } from '../api/paths.js';

const initialMessage = 'Each save creates a separate, immutable version.';

export default function PoliciesPage({ active, request, dashboard, refreshKey, refresh, notify }) {
  const [documentText, setDocumentText] = useState('');
  const [name, setName] = useState('my-policy');
  const [profile, setProfile] = useState('');
  const [validation, setValidation] = useState(initialMessage);
  const [listRevision, setListRevision] = useState(0);
  const initialized = useRef(false);
  const nameInput = useRef(null);
  const { pending, run } = useAction(notify);
  const { data: revisions, loading } = useResource(
    request,
    paths.policyRevisions,
    active && !!dashboard,
    `${refreshKey}-${listRevision}`,
    notify,
  );
  const activeVersion = dashboard?.active_policy.revision.version;

  useEffect(() => {
    if (dashboard && !initialized.current) {
      setDocumentText(JSON.stringify(dashboard.active_policy.revision.document, null, 2));
      initialized.current = true;
    }
  }, [dashboard]);

  let parsed;
  try {
    parsed = JSON.parse(documentText);
  } catch {
    /* YAML is edited in the full editor. */
  }
  const controls = parsed?.controls;
  const hasQuickControls =
    controls &&
    typeof controls === 'object' &&
    !Array.isArray(controls) &&
    Object.values(controls).every(
      (control) => control && typeof control === 'object' && !Array.isArray(control),
    );
  function setEditor(document) {
    setDocumentText(JSON.stringify(document, null, 2));
    setValidation(initialMessage);
  }
  function updateControl(key, field, value) {
    const document = JSON.parse(documentText);
    document.controls[key][field] = value;
    setDocumentText(JSON.stringify(document, null, 2));
    setValidation('Configuration changed — save a new version.');
  }

  return (
    <>
      <div id="revision-list" className="revision-grid" aria-busy={loading}>
        {(revisions || []).slice(0, 9).map((revision) => (
          <article
            key={revision.version}
            className={`revision ${revision.version === activeVersion ? 'current' : ''}`}
          >
            <div>
              <span className="label">VERSION {revision.version}</span>
              {revision.version === activeVersion && <span className="badge allow">ACTIVE</span>}
            </div>
            <h3>{revision.name}</h3>
            <p>{formatDate(revision.created_at)}</p>
            <div className="revision-actions">
              <button
                className="button ghost small"
                data-edit={revision.version}
                disabled={!!pending}
                onClick={() =>
                  run('copy', async () => {
                    const copy = await request(paths.policyRevision(revision.version));
                    setEditor(copy.document);
                    setName(copy.name + '-copy');
                    setProfile('');
                    nameInput.current?.focus();
                  })
                }
              >
                Create copy
              </button>
              <button
                className={`button ${revision.version === activeVersion ? 'secondary' : 'primary'} small`}
                data-publish={revision.version}
                disabled={!!pending || revision.version === activeVersion}
                onClick={() =>
                  run('publish', async () => {
                    await request(paths.activePolicy, {
                      method: 'PUT',
                      body: JSON.stringify({ version: revision.version }),
                    });
                    await refresh();
                    notify(
                      `Published version ${revision.version}. The gateway can fetch the updated configuration.`,
                    );
                  })
                }
              >
                Publish
              </button>
              <button
                className="button danger small"
                data-delete={revision.version}
                disabled={!!pending || revision.version === activeVersion}
                title={
                  revision.version === activeVersion
                    ? 'Publish another version before deleting this policy.'
                    : `Delete version ${revision.version}`
                }
                onClick={() => {
                  if (
                    !window.confirm(
                      `Delete version ${revision.version} (${revision.name})? This cannot be undone.`,
                    )
                  )
                    return;
                  run('delete', async () => {
                    await request(paths.policyRevision(revision.version), { method: 'DELETE' });
                    setListRevision((value) => value + 1);
                    notify(`Deleted version ${revision.version}.`);
                  });
                }}
              >
                Delete
              </button>
            </div>
          </article>
        ))}
        {loading && !revisions && <p className="help">Loading policy versions…</p>}
      </div>
      <article className="card">
        <div className="card-header">
          <div>
            <h2>New policy version</h2>
            <p>Save a version, then publish it for the gateway.</p>
          </div>
          <select
            id="profile"
            aria-label="Load a preset profile"
            value={profile}
            disabled={!!pending || !dashboard}
            onChange={(event) => {
              const value = event.target.value;
              setProfile(value);
              if (value)
                run('profile', async () => {
                  setEditor(await request(paths.policyProfile(value)));
                  setName(value + '-custom');
                });
            }}
          >
            <option value="">Load a profile…</option>
            <option value="permissive">Permissive</option>
            <option value="balanced">Balanced</option>
            <option value="strict">Strict</option>
          </select>
        </div>
        <div className="editor-content">
          <label>
            Version name
            <input
              ref={nameInput}
              id="draft-name"
              maxLength={120}
              placeholder="e.g. balanced-v2"
              value={name}
              disabled={!!pending}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <div id="quick-controls" className="quick-controls">
            {hasQuickControls ? (
              Object.entries(controls).map(([key, control]) => (
                <div key={key} className="quick-row">
                  <input
                    type="checkbox"
                    data-control={key}
                    aria-label={`Enable ${labels[key] || key}`}
                    checked={!!control.enabled}
                    disabled={!!pending}
                    onChange={(event) => updateControl(key, 'enabled', event.target.checked)}
                  />
                  <strong>{labels[key] || key}</strong>
                  {key === 'prompt_injection' && (
                    <label>
                      Threshold{' '}
                      <input
                        type="number"
                        id="injection-threshold"
                        min="0"
                        max="1"
                        step="0.05"
                        value={control.threshold ?? ''}
                        disabled={!!pending}
                        onChange={(event) =>
                          updateControl(key, 'threshold', Number(event.target.value))
                        }
                      />
                    </label>
                  )}
                  <select
                    data-action={key}
                    aria-label={`Action ${labels[key] || key}`}
                    value={control.action || 'block'}
                    disabled={!!pending}
                    onChange={(event) => updateControl(key, 'action', event.target.value)}
                  >
                    {['block', 'redact', 'monitor'].map((action) => (
                      <option key={action}>{action}</option>
                    ))}
                  </select>
                </div>
              ))
            ) : (
              <p className="help">
                Use the full editor below for YAML or incomplete JSON. Quick settings require a JSON
                policy with valid controls.
              </p>
            )}
          </div>
          <details>
            <summary>Full JSON / YAML configuration</summary>
            <textarea
              id="policy-document"
              className="code-editor"
              spellCheck={false}
              aria-label="Policy document"
              value={documentText}
              disabled={!!pending}
              onChange={(event) => {
                setDocumentText(event.target.value);
                setValidation('Configuration changed — save a new version.');
              }}
            />
          </details>
        </div>
        <div className="card-footer action-footer">
          <span id="validation-result" role="status">
            {validation}
          </span>
          <div>
            <button
              className="button secondary"
              id="validate-policy"
              disabled={!!pending || !dashboard}
              onClick={() =>
                run('validate', async () => {
                  await request(paths.policyValidations, {
                    method: 'POST',
                    body: JSON.stringify({ document: documentText }),
                  });
                  setValidation('Configuration is valid.');
                  notify('Configuration passed validation.');
                })
              }
            >
              Validate configuration
            </button>
            <button
              className="button primary"
              id="save-policy"
              disabled={!!pending || !dashboard}
              onClick={() =>
                run('save', async () => {
                  if (!name.trim()) throw new Error('Enter a version name.');
                  const revision = await request(paths.policyRevisions, {
                    method: 'POST',
                    body: JSON.stringify({
                      name: name.trim(),
                      description: 'Created from dashboard',
                      document: documentText,
                    }),
                  });
                  setListRevision((value) => value + 1);
                  notify(`Saved version ${revision.version}. Click Publish to activate it.`);
                })
              }
            >
              Save new version
            </button>
          </div>
        </div>
      </article>
    </>
  );
}
