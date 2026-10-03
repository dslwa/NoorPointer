import { useState } from 'react';
import Modal from '../../components/common/Modal.jsx';
import { exampleFeed } from '../../constants/signatureExample.js';

export default function AddSignatureDialog({ onCreate, onPaste, onDismiss }) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [mode, setMode] = useState('paste');
  const [documentText, setDocumentText] = useState('');

  async function submit(event) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    setSaving(true);
    setError('');
    try {
      if (mode === 'paste') await onPaste(documentText);
      else
        await onCreate({
          id: fields.get('id').trim(),
          name: fields.get('name').trim(),
          source: fields.get('source').trim(),
          category: fields.get('category').trim(),
          action: fields.get('action'),
          target: fields.get('target'),
          match: { type: 'literal', value: fields.get('match') },
          description: fields.get('description').trim(),
          enabled: true,
        });
    } catch (failure) {
      setError(failure.message);
      setSaving(false);
    }
  }

  return (
    <Modal id="add-signature-dialog" open required={saving} onDismiss={onDismiss}>
      <form onSubmit={submit}>
        <div className="dialog-heading">
          <h2>Add signature</h2>
          <p>Save a detection rule alongside the existing signatures.</p>
        </div>
        <div className="signature-dialog-actions">
          <button
            type="button"
            className={`button ${mode === 'paste' ? 'primary' : 'secondary'} small`}
            disabled={saving}
            aria-pressed={mode === 'paste'}
            onClick={() => {
              setMode('paste');
              setError('');
            }}
          >
            Paste JSON / YAML
          </button>
          <button
            type="button"
            className={`button ${mode === 'form' ? 'primary' : 'secondary'} small`}
            disabled={saving}
            aria-pressed={mode === 'form'}
            onClick={() => {
              setMode('form');
              setError('');
            }}
          >
            Use form
          </button>
        </div>
        {mode === 'paste' ? (
          <div className="signature-fields">
            <label>
              Signature document
              <textarea
                id="pasted-signature"
                className="code-editor"
                value={documentText}
                onChange={(event) => setDocumentText(event.target.value)}
                required
                maxLength={1_000_000}
                disabled={saving}
                placeholder="Paste one signature object in JSON or YAML…"
                spellCheck={false}
              />
            </label>
            <p className="help">
              Paste one rule with id, name, source, category, action, target and match. Saving adds
              it to the existing feed.
            </p>
            <button
              type="button"
              className="button secondary small"
              disabled={saving}
              onClick={() => {
                setDocumentText(
                  JSON.stringify(
                    {
                      ...exampleFeed.signatures[0],
                      id: 'CUSTOM-INJECTION-001',
                      name: 'My injection rule',
                      action: 'monitor',
                    },
                    null,
                    2,
                  ),
                );
                setError('');
              }}
            >
              Load example
            </button>
          </div>
        ) : (
          <fieldset className="signature-fields" disabled={saving}>
            <label>
              Unique rule ID
              <input
                name="id"
                required
                maxLength={120}
                pattern="[A-Za-z0-9._\-]+"
                placeholder="INJECTION-002"
              />
            </label>
            <label>
              Name
              <input
                name="name"
                required
                maxLength={200}
                placeholder="Attempt to reveal system instructions"
              />
            </label>
            <label>
              Category
              <input name="category" required maxLength={80} defaultValue="LLM01:2025" />
            </label>
            <label>
              Source URL
              <input
                name="source"
                type="url"
                required
                pattern="https://.*"
                maxLength={1000}
                placeholder="https://example.org/security-reference"
              />
            </label>
            <label>
              Inspect
              <select name="target" defaultValue="prompt">
                <option value="prompt">Prompt</option>
                <option value="tool_name">Tool name</option>
                <option value="tool_arguments">Tool arguments</option>
                <option value="model_artifact">Model artifact</option>
                <option value="upstream_path">Upstream path</option>
              </select>
            </label>
            <label>
              When matched
              <select name="action" defaultValue="block">
                <option value="block">Block</option>
                <option value="monitor">Monitor</option>
              </select>
            </label>
            <label>
              Text to match literally
              <textarea
                name="match"
                required
                maxLength={2000}
                rows={3}
                placeholder="reveal your system instructions"
              />
            </label>
            <label>
              Description (optional)
              <textarea name="description" maxLength={2000} rows={2} />
            </label>
          </fieldset>
        )}
        <p className="error" role="alert">
          {error}
        </p>
        <div className="signature-dialog-actions">
          <button className="button secondary" type="button" disabled={saving} onClick={onDismiss}>
            Cancel
          </button>
          <button className="button primary" type="submit" disabled={saving}>
            {saving ? 'Saving…' : 'Save signature'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
