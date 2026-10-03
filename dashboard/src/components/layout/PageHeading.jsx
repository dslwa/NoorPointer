import { views } from '../../app/navigation.js';

export default function PageHeading({
  view,
  pending,
  authenticated,
  dashboard,
  onRefresh,
  onDemo,
}) {
  const current = views[view];
  return (
    <div className="page-heading">
      <div>
        <h1 id="page-title">{current.title}</h1>
        <p className="subtitle" id="page-description">
          {current.description}
        </p>
      </div>
      <div className="heading-actions" hidden={view === 'prompt'}>
        <button
          className="button secondary"
          id="refresh"
          disabled={!!pending || !authenticated}
          onClick={onRefresh}
        >
          Refresh
        </button>
        <button
          className="button primary"
          id="demo"
          hidden={dashboard?.demo_enabled === false}
          disabled={!!pending || !dashboard}
          onClick={onDemo}
        >
          Load demo events
        </button>
      </div>
    </div>
  );
}
