import { toast } from '../composables/useToast';

export async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  const token = localStorage.getItem('token');
  if (token) headers['Authorization'] = 'Bearer ' + token;
  const apiBase = window.__API_BASE__ || '';
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

// Runs
export const createRunApi = (data) => api('/api/runs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
export const getRunApi = (runId) => api(`/api/runs/${encodeURIComponent(runId)}`);
export const stopRunApi = (runId) => api(`/api/runs/${encodeURIComponent(runId)}/stop`, { method: 'POST' });
export const retryRunApi = (runId) => api(`/api/runs/${encodeURIComponent(runId)}/retry`, { method: 'POST' });
export const getRunningTasks = () => api('/api/runs/running');

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

// Sites
export const getSiteTrend = (profileName, { hours } = {}) => {
  const params = new URLSearchParams({ profile_name: profileName });
  if (hours) params.set('hours', hours);
  return api(`/api/sites/trend?${params}`);
};

// Channel Diagnostics
export const createChannelDiagnostic = (data) =>
  api('/api/channel-diagnostics', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });

export const getChannelDiagnostic = (id) =>
  api(`/api/channel-diagnostics/${id}`);

export const listChannelDiagnostics = (params = {}) => {
  const qs = new URLSearchParams(params).toString();
  return api('/api/channel-diagnostics' + (qs ? '?' + qs : ''));
};

export const getDiagnosticFilterOptions = (params = {}) => {
  const qs = new URLSearchParams(params).toString();
  return api('/api/channel-diagnostics/filter-options' + (qs ? '?' + qs : ''));
};

// Settings
export const updateProfileApi = (data) => api('/api/user/profile', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
export const changePasswordApi = (data) => api('/api/user/password', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });

// Admin
export const getUsers = () => api('/api/admin/users');
export const updateUserRoleApi = (id, role) => api(`/api/admin/users/${id}/role`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ role }) });
export const deleteUserApi = (id) => api(`/api/admin/users/${id}`, { method: 'DELETE' });
export const getAdminRuns = () => api('/api/admin/runs');
export const adminStopRunApi = (id) => api(`/api/admin/runs/${encodeURIComponent(id)}/stop`, { method: 'POST' });

// Sites
export const getSitesSummary = ({ hours } = {}) => {
  const params = new URLSearchParams();
  if (hours != null) params.set('hours', hours);
  const qs = params.toString();
  return api('/api/sites/summary' + (qs ? '?' + qs : ''));
};

// Models
export const getModels = (baseUrl, apiKey) =>
  api('/api/models', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ base_url: baseUrl, api_key: apiKey }) });

// Pricing / Model Config
export const getVendors = () => api('/api/pricing/vendors');
export const getProviders = () => api('/api/pricing/providers');
export const getModelsConfig = () => api('/api/pricing/models-config');
export const putModelsConfig = (data) =>
  api('/api/pricing/models-config', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
export const getPricingModels = (vendor = '', enabledOnly = false) =>
  api(`/api/pricing/models?vendor=${encodeURIComponent(vendor)}${enabledOnly ? '&enabled_only=true' : ''}`);
export const getLibrary = ({ search = '', vendor = '', page = 1, pageSize = 50 } = {}) => {
  const params = new URLSearchParams({ search, vendor, page, page_size: pageSize });
  return api(`/api/pricing/library?${params}`);
};
