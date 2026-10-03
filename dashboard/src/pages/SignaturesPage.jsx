import { useEffect, useRef, useState } from 'react';
import { exampleFeed } from '../constants/signatureExample.js';
import { useAction } from '../hooks/useAction.js';
import { useResource } from '../hooks/useResource.js';
import { paths } from '../api/paths.js';

export default function SignaturesPage({ active, authenticated, request, refreshKey, notify }) {
  const [text, setText] = useState('');
  const [revision, setRevision] = useState(0);
  const initialized = useRef(false);
  const { pending, run } = useAction(notify);
  const { data, loading } = useResource(
    request,
    paths.signatureFeed,
    active && authenticated,
    `${refreshKey}-${revision}`,
    notify,
  );
  useEffect(() => {
    if (data && !initialized.current) {
      setText(JSON.stringify(data.signatures.length ? data : exampleFeed, null, 2));
      initialized.current = true;
    }
  }, [data]);
  return (
    <article className="card">
      <div className="card-header">
        <div>
          <h2>Signature feed</h2>
          <p>Import JSON / YAML to replace the entire current feed.</p>
        </div>
        <span id="signature-count" className="label">
          {data?.signatures.length || 0} RULES
        </span>
      </div>
      <div className="editor-content">
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
                : 'The feed is empty. An example document is ready to import below.'}
            </p>
          )}
        </div>
        <label>
          Feed document
          <textarea
            id="signature-document"
            className="code-editor"
            spellCheck={false}
            value={text}
            disabled={!!pending}
            onChange={(event) => setText(event.target.value)}
          />
        </label>
      </div>
      <div className="card-footer action-footer">
        <small>Rules match literal text and are enforced by the gateway.</small>
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
              setRevision((value) => value + 1);
              notify(`Feed replaced. Imported ${result.signatures.length} rules.`);
            })
          }
        >
          Replace feed
        </button>
      </div>
    </article>
  );
}
