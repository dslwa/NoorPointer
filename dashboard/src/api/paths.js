export const paths = {
  dashboard: '/dashboard',
  policyRevisions: '/policy-revisions',
  policyRevision: (version) => `/policy-revisions/${encodeURIComponent(version)}`,
  activePolicy: '/active-policy',
  policyValidations: '/policy-validations',
  policyProfile: (name) => `/policy-profiles/${encodeURIComponent(name)}`,
  auditEvents: '/audit-events',
  auditEvent: (id) => `/audit-events/${encodeURIComponent(id)}`,
  auditExport: '/audit-events/export',
  signatureFeed: '/signature-feed',
  demoBatches: '/demo-batches',
};
