import { useEffect, useRef, useState } from 'react';
import { useAction } from '../hooks/useAction.js';
import { useResource } from '../hooks/useResource.js';
import { paths } from '../api/paths.js';
import AddSignatureDialog from '../features/signatures/AddSignatureDialog.jsx';

export default function SignaturesPage({ active, authenticated, request, refreshKey, notify }) {
  const [text, setText] = useState('');
  const [revision, setRevision] = useState(0);
  const [adding, setAdding] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const lastFeed = useRef(null);
  const { pending, run } = useAction(notify);
  const { data, loading } = useResource(
    request,
    paths.signatureFeed,
    active && authenticated,
    `${refreshKey}-${revision}`,
    notify,
  );
  useEffect(() => {
    if (!data || data === lastFeed.current) return;
    lastFeed.current = data;
    if (data && !dirty) {
      setText(JSON.stringify(data, null, 2));
    }
  }, [data, dirty]);

  async function addSignature(signature) {
    await request(paths.signatures, { method: 'POST', body: JSON.stringify(signature) });
    signatureSaved();
  }

  async function pasteSignature(document) {
    await request(paths.signatures, {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain' },
      body: document,
    });
    signatureSaved();
  }

  function signatureSaved() {
    setRevision((value) => value + 1);
    setAdding(false);
    notify(
      dirty
        ? 'Signature saved. Your unsaved feed document was kept; replacing it will overwrite the saved feed.'
        : 'Signature saved. Existing rules were preserved.',
    );
  }

  return (
    <>
      <article className="card">
        <div className="card-header">
          <div>
            <h2>Signature feed</h2>
            <p>Add individual rules or import a complete detection feed.</p>
          </div>
          <div className="signature-dialog-actions">
            <span id="signature-count" className="label">
              {data?.signatures.length || 0} RULES
            </span>
            <button
              className="button primary small"
              id="add-signature"
              disabled={!!pending || !data}
              onClick={() => setAdding(true)}
            >
              ＋ Add signature
            </button>
          </div>
        </div>
        <div className="editor-content">
          <div className="starter-signatures">
            <div>
              <strong>Basic signatures</strong>
              <p className="help">
                Seven basic rules are included by default, with monitoring enabled. Add your own by
                pasting a JSON / YAML signature or using the form. These are NoorPointer examples
                inspired by OWASP, with no automatic OWASP sync.
              </p>
            </div>
          </div>
          <div id="signature-list" aria-busy={loading}>
            {data?.signatures.length ? (
              data.signatures.map((signature) => (
                <div key={signature.id} className="signature-row">
                  <div>
                    <strong>{signature.name}</strong>
                    <p>
                      {signature.id} · {signature.category} · {signature.target}
                    </p>
                    <a href={signature.source} target="_blank" rel="noopener noreferrer">
                      Source ↗
                    </a>
                  </div>
                  <span className={`badge ${signature.action}`}>{signature.action}</span>
                </div>
              ))
            ) : (
              <p className="help">
                {loading
                  ? 'Loading signatures…'
                  : 'The feed is empty. Click Add signature to create a rule.'}
              </p>
            )}
          </div>
          <details open={importOpen} onToggle={(event) => setImportOpen(event.currentTarget.open)}>
            <summary>Replace entire feed (JSON / YAML)</summary>
            <p className="help">
              Replacement removes rules absent from this document. Include every rule you want to
              keep.
            </p>
            <label>
              Feed document
              <textarea
                id="signature-document"
                className="code-editor"
                spellCheck={false}
                value={text}
                disabled={!!pending}
                onChange={(event) => {
                  setText(event.target.value);
                  setDirty(true);
                }}
              />
            </label>
            <div className="card-footer action-footer">
              <small>
                {dirty ? 'Unsaved replacement document.' : 'This replaces the entire saved feed.'}
              </small>
              <button
                className="button primary"
                id="import-signatures"
                disabled={!!pending || !data}
                onClick={() =>
                  run('import', async () => {
                    const result = await request(paths.signatureFeed, {
                      method: 'PUT',
                      body: JSON.stringify({ document: text }),
                    });
                    setText(JSON.stringify(result, null, 2));
                    setDirty(false);
                    setRevision((value) => value + 1);
                    notify(`Feed replaced. Imported ${result.signatures.length} rules.`);
                  })
                }
              >
                Replace feed
              </button>
            </div>
          </details>
          <p className="help">
            Signatures detect literal text. Saving rules makes them available to the gateway.
          </p>
        </div>
      </article>
      {adding && (
        <AddSignatureDialog
          onCreate={addSignature}
          onPaste={pasteSignature}
          onDismiss={() => setAdding(false)}
        />
      )}
    </>
  );
}
