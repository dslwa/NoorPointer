export function createApi(token) {
  return async (path, { download = false, ...options } = {}) => {
    const response = await fetch('/api/v1' + path, {
      ...options,
      headers: {
        Authorization: 'Bearer ' + token,
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...options.headers,
      },
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      const error = new Error(
        body.message ||
          (response.status === 401 ? 'Invalid API token.' : 'API error: ' + response.status),
      );
      error.status = response.status;
      throw error;
    }
    if (response.status === 204) return null;
    return download ? response.blob() : response.json();
  };
}
