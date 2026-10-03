import { useEffect, useState } from 'react';
import { eventQuery, formatDate, labels } from '../api.js';
import { useAction, useResource } from '../hooks.js';
import Modal from './Modal.jsx';

const emptyFilters = { action: '', agent: '', category: '' };
export default function Events({ active, authenticated, request, refreshKey, notify }) {
  const [filters, setFilters] = useState(emptyFilters);
  const [applied, setApplied] = useState(emptyFilters);
  const [page, setPage] = useState(0);
  const [detail, setDetail] = useState(null);
  const { pending, run } = useAction(notify);
  const query = eventQuery(applied); query.set('page', page); query.set('size', 20);
  const { data, loading } = useResource(request, '/events?' + query, active && authenticated, refreshKey, notify);
  const total = data?.total || 0;
  useEffect(() => {
    if (data && page > 0 && page * 20 >= total) setPage(Math.max(0, Math.ceil(total / 20) - 1));
  }, [data, page, total]);

  function updateFilter(key, value) { setFilters(previous => ({ ...previous, [key]: value })); }
  function showDetail(event) {
    run('detail', async () => setDetail(await request('/events/' + encodeURIComponent(event.id))));
  }
  async function download(format) {
    const query = eventQuery(applied); query.set('format', format);
    const blob = await request('/events/export?' + query, { download: true });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url; link.download = 'noorpointer-events.' + format; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <>
    <article className="card"><div className="card-header"><div><h2>Event log</h2><p>Select an event to view its details. Sample data is marked DEMO.</p></div>
      <div className="export-actions">{['json', 'csv', 'cef'].map(format => <button key={format} className="button secondary small" data-export={format} disabled={!!pending || !authenticated} onClick={() => run('export', () => download(format))}>{format.toUpperCase()} ↓</button>)}</div>
    </div>
      <form id="event-filters" className="filters" onSubmit={event => { event.preventDefault(); setPage(0); setApplied({ ...filters }); }} onReset={() => { setFilters(emptyFilters); setApplied(emptyFilters); setPage(0); }}>
        <select id="filter-action" aria-label="Action" value={filters.action} onChange={event => updateFilter('action', event.target.value)}><option value="">All actions</option>{['block', 'allow', 'redact', 'monitor', 'timeout'].map(action => <option key={action} value={action}>{action[0].toUpperCase() + action.slice(1)}</option>)}</select>
        <input id="filter-agent" placeholder="Agent ID" aria-label="Agent ID" value={filters.agent} onChange={event => updateFilter('agent', event.target.value)} />
        <input id="filter-category" placeholder="Category" aria-label="Category" value={filters.category} onChange={event => updateFilter('category', event.target.value)} />
        <button className="button primary small" type="submit">Filter</button><button className="button ghost small" type="reset">Clear</button>
      </form>
      <div className="table-wrap" aria-busy={loading}><table><thead><tr><th>Time</th><th>Agent / model</th><th>Control</th><th>Category</th><th>Action</th><th /></tr></thead><tbody id="event-rows">
        {data?.items.length ? data.items.map(event => <tr key={event.id} className="event-row" data-event={event.id} onClick={() => showDetail(event)}>
          <td>{formatDate(event.occurred_at)}{event.context.demo && <span className="demo-label">DEMO</span>}<small>{event.kind}</small></td>
          <td><strong>{event.agent_id}</strong><small>{event.model}</small></td><td>{labels[event.control] || event.control}</td><td>{event.category}</td>
          <td><span className={`badge ${event.action}`}>{event.action}</span></td><td><button className="button ghost small" disabled={!!pending} aria-label={`Event details ${event.id}`}>↗</button></td>
        </tr>) : <tr><td colSpan={6} className="empty">{loading ? 'Loading events…' : 'No events match these filters. Load demo events or connect the gateway.'}</td></tr>}
      </tbody></table></div>
      <div className="card-footer pagination"><span id="event-count">{total ? `${page * 20 + 1}–${Math.min((page + 1) * 20, total)} of ${total} events` : 'No events'}</span><div>
        <button className="button secondary small" id="previous-page" disabled={page === 0 || loading} onClick={() => setPage(value => value - 1)}>← Previous</button>
        <button className="button secondary small" id="next-page" disabled={(page + 1) * 20 >= total || loading} onClick={() => setPage(value => value + 1)}>Next →</button>
      </div></div>
    </article>
    <Modal id="detail-dialog" open={!!detail} onDismiss={() => setDetail(null)}><div className="detail-header"><h2>Event details</h2><button className="button secondary small" id="close-detail" onClick={() => setDetail(null)}>Close ×</button></div><pre id="event-detail">{detail ? JSON.stringify(detail, null, 2) : ''}</pre></Modal>
  </>;
}
