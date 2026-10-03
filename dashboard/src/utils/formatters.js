export const formatNumber = (value) =>
  new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(value);
export const money = (value) =>
  new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 4,
  }).format(value);
export const formatDate = (value) => new Date(value).toLocaleString('en-US');
