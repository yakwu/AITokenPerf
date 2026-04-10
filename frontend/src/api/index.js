import { toast } from '../composables/useToast';

export async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  const token = localStorage.getItem('token');
  if (token) headers['Authorization'] = 'Bearer ' + token;
  const apiBase = window.__API_BASE__ || (import.meta.env.DEV ? 'http://localhost:8080' : '');
  const res = await fetch(apiBase + path, { ...opts, headers });
  if (res.status === 401) {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    import('../router').then(m => m.default.push('/auth'));
    throw new Error('Unauthorized');
  }
  return res.json();
}

// Auth
export const loginApi = (email, password) =>
  api('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password }) });

export const registerApi = (email, password, display_name) =>
  api('/api/auth/register', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password, display_name }) });

// Profiles
export const getProfiles = () => api('/api/profiles');
export const createProfile = (data) => api('/api/profiles', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
export const updateProfile = (name, data) => api(`/api/profiles/${encodeURIComponent(name)}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
export const deleteProfileApi = (name) => api(`/api/profiles/${encodeURIComponent(name)}`, { method: 'DELETE' });

// Benchmark
export const startBenchApi = (data) => api('/api/bench/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
export const stopBenchApi = () => api('/api/bench/stop', { method: 'POST' });
export const getBenchStatus = () => api('/api/bench/status');
export const dryRunApi = (data) => api('/api/bench/dry-run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
export const startMultiBenchApi = (data) => api('/api/bench/start-multi', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
export const getMultiBenchStatus = (groupId) => api(`/api/bench/status-multi/${encodeURIComponent(groupId)}`);

// Results
export const getResults = (params = {}) => {
  const qs = new URLSearchParams(params).toString();
  return api('/api/results' + (qs ? '?' + qs : ''));
};
export const getResult = (filename) => api(`/api/results/${encodeURIComponent(filename)}`);
export const deleteResultApi = (filename) => api(`/api/results/${encodeURIComponent(filename)}`, { method: 'DELETE' });
export const getCompare = (filenames) => api('/api/results/compare?filenames=' + filenames.map(f => encodeURIComponent(f)).join(','));

// Schedules
export const getSchedules = () => api('/api/schedules');
export const createScheduleApi = (data) => api('/api/schedules', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
export const updateScheduleApi = (id, data) => api(`/api/schedules/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
export const deleteScheduleApi = (id) => api(`/api/schedules/${id}`, { method: 'DELETE' });
export const pauseScheduleApi = (id) => api(`/api/schedules/${id}/pause`, { method: 'POST' });
export const resumeScheduleApi = (id) => api(`/api/schedules/${id}/resume`, { method: 'POST' });
export const runNowApi = (id) => api(`/api/schedules/${id}/run-now`, { method: 'POST' });
export const getScheduleResults = (id, { limit = 100, offset = 0, hours } = {}) => {
  const params = new URLSearchParams({ limit, offset });
  if (hours) params.set('hours', hours);
  return api(`/api/schedules/${id}/results?${params}`);
};
export const getScheduleTrend = (id, { hours } = {}) => api(`/api/schedules/${id}/trend` + (hours ? `?hours=${hours}` : ''));

// Settings
export const updateProfileApi = (data) => api('/api/user/profile', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
export const changePasswordApi = (data) => api('/api/user/password', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });

// Admin
export const getUsers = () => api('/api/admin/users');
export const updateUserRoleApi = (id, role) => api(`/api/admin/users/${id}/role`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ role }) });
export const deleteUserApi = (id) => api(`/api/admin/users/${id}`, { method: 'DELETE' });

// Models
export const getModels = (baseUrl, apiKey) =>
  api('/api/models', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ base_url: baseUrl, api_key: apiKey }) });

// Pricing / Model Config
export const getModelsConfig = () => api('/api/pricing/models-config');
export const putModelsConfig = (enabledModels) =>
  api('/api/pricing/models-config', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled_models: enabledModels }) });
export const getPricingModels = (provider = '') =>
  api(`/api/pricing/models?provider=${encodeURIComponent(provider)}`);
