const API_BASE = 'http://localhost:8000/api';

const api = {
  async listDatasets() {
    const r = await fetch(`${API_BASE}/datasets`);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async uploadDataset(file, dataId) {
    const fd = new FormData();
    fd.append('file', file);
    const url = dataId ? `${API_BASE}/datasets/upload?data_id=${encodeURIComponent(dataId)}` : `${API_BASE}/datasets/upload`;
    const r = await fetch(url, { method: 'POST', body: fd });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async deleteDataset(dataId) {
    const r = await fetch(`${API_BASE}/datasets/${encodeURIComponent(dataId)}`, { method: 'DELETE' });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async getDataset(dataId) {
    const r = await fetch(`${API_BASE}/datasets/${encodeURIComponent(dataId)}`);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async getPlot(dataId, plotType, params = {}) {
    const q = new URLSearchParams();
    if (params.normalize) q.set('normalize', 'true');
    if (params.cycles) q.set('cycles', params.cycles);
    if (params.y_range) q.set('y_range', params.y_range);
    const qs = q.toString() ? `?${q}` : '';
    const r = await fetch(`${API_BASE}/plots/${encodeURIComponent(dataId)}/${plotType}${qs}`);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async generateReport(datasetId, format, analysisNotes) {
    const r = await fetch(`${API_BASE}/reports`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dataset_id: datasetId, format, analysis_notes: analysisNotes || null }),
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  getReportDownloadUrl(dataId, format) {
    return `${API_BASE}/reports/download/${encodeURIComponent(dataId)}/${format}`;
  },

  chatStream(message, datasetId, model) {
    const q = new URLSearchParams({ message });
    if (datasetId) q.set('dataset_id', datasetId);
    if (model) q.set('model', model);
    return new EventSource(`${API_BASE}/chat/stream?${q}`);
  },

  async getSettings() {
    const r = await fetch(`${API_BASE}/settings`);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async fetchReportContent(dataId, format) {
    const r = await fetch(this.getReportDownloadUrl(dataId, format));
    if (!r.ok) throw new Error(await r.text());
    return r.text();
  },

  async updateSettings(body) {
    const r = await fetch(`${API_BASE}/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
};
