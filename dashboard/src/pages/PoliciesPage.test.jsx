import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import PoliciesPage from './PoliciesPage.jsx';

const document = { controls: { secrets: { enabled: true, action: 'block' } } };
const revisions = [
  { version: 2, name: 'Active policy', created_at: '2026-10-03T10:00:00Z', document },
  { version: 1, name: 'Previous policy', created_at: '2026-10-02T10:00:00Z', document },
];

function setup({ rejectDelete = false } = {}) {
  let current = [...revisions];
  const request = vi.fn(async (path, options = {}) => {
    if (options.method === 'DELETE') {
      if (rejectDelete) throw new Error('Cannot delete the active policy');
      current = current.filter((revision) => path !== `/policy-revisions/${revision.version}`);
      return null;
    }
    if (path === '/policy-revisions') return current;
    throw new Error(`Unexpected request: ${path}`);
  });
  const props = {
    active: true,
    request,
    dashboard: { active_policy: { revision: revisions[0] } },
    refreshKey: 0,
    refresh: vi.fn(),
    notify: vi.fn(),
  };
  const view = render(<PoliciesPage {...props} />);
  return { ...view, props, request, user: userEvent.setup() };
}

async function card(name) {
  return within((await screen.findByRole('heading', { name })).closest('article'));
}

describe('Policies', () => {
  it('protects the active revision from deletion and publication', async () => {
    const { user, request } = setup();
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    const active = await card('Active policy');
    const button = active.getByRole('button', { name: 'Delete' });
    expect(button.disabled).toBe(true);
    expect(active.getByRole('button', { name: 'Publish' }).disabled).toBe(true);
    await user.click(button);
    expect(confirm).not.toHaveBeenCalled();
    expect(request.mock.calls.some(([, options]) => options?.method === 'DELETE')).toBe(false);
  });

  it('does not delete a revision when confirmation is cancelled', async () => {
    const { user, request } = setup();
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    await user.click((await card('Previous policy')).getByRole('button', { name: 'Delete' }));
    expect(confirm).toHaveBeenCalledWith(
      'Delete version 1 (Previous policy)? This cannot be undone.',
    );
    expect(request.mock.calls.some(([, options]) => options?.method === 'DELETE')).toBe(false);
    expect(screen.getByRole('heading', { name: 'Previous policy' })).toBeTruthy();
  });

  it('deletes a confirmed revision and refreshes the list', async () => {
    const { user, request, props } = setup();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    await user.click((await card('Previous policy')).getByRole('button', { name: 'Delete' }));
    await waitFor(() =>
      expect(screen.queryByRole('heading', { name: 'Previous policy' })).toBeNull(),
    );
    expect(request).toHaveBeenCalledWith('/policy-revisions/1', { method: 'DELETE' });
    expect(props.notify).toHaveBeenCalledWith('Deleted version 1.');
    expect(screen.getByRole('heading', { name: 'Active policy' })).toBeTruthy();
  });

  it('preserves the revision and displays a conflict if it became active on the server', async () => {
    const { user, props } = setup({ rejectDelete: true });
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    await user.click((await card('Previous policy')).getByRole('button', { name: 'Delete' }));
    await waitFor(() =>
      expect(props.notify).toHaveBeenCalledWith('Cannot delete the active policy', true),
    );
    const previous = await card('Previous policy');
    expect(previous.getByRole('button', { name: 'Delete' }).disabled).toBe(false);
    expect(props.notify).not.toHaveBeenCalledWith('Deleted version 1.');
  });

  it('preserves an unsaved draft when dashboard data refreshes', async () => {
    const { user, rerender, props } = setup();
    await screen.findByRole('heading', { name: 'Active policy' });
    await user.clear(screen.getByLabelText('Version name'));
    await user.type(screen.getByLabelText('Version name'), 'unsaved-draft');
    await user.click(screen.getByText('Full JSON / YAML configuration'));
    const editor = screen.getByRole('textbox', { name: 'Policy document' });
    await user.clear(editor);
    await user.type(editor, 'controls:\n  secrets:\n    enabled: false');
    rerender(
      <PoliciesPage
        {...props}
        refreshKey={1}
        dashboard={{ active_policy: { revision: revisions[1] } }}
      />,
    );
    expect(screen.getByLabelText('Version name').value).toBe('unsaved-draft');
    expect(editor.value).toBe('controls:\n  secrets:\n    enabled: false');
    await waitFor(() => expect(props.request).toHaveBeenCalledTimes(2));
  });
});
