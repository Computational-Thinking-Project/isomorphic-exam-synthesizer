import { api } from './api.js';

export async function getMyStatistics({ signal } = {}) {
  const { data } = await api.get('/users/me/statistics', { signal });
  return data;
}
