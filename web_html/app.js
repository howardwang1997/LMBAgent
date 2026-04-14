const app = {
  selectedDataset: null,
  activePlotTypes: new Set(['capacity_fade', 'coulombic_efficiency', 'voltage_curves', 'impedance']),
  chatModel: 'grok-4-1-fast-reasoning',

  // ===== INIT =====
  async init() {
    this.bindUpload();
    this.bindPlotTabs();
    await this.loadDatasets();
    await this.loadSettings();
  },

  // ===== TOAST =====
  toast(msg, type = 'success') {
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 2500);
  },

  // ===== UPLOAD =====
  bindUpload() {
    const zone = document.getElementById('uploadZone');
    const input = document.getElementById('fileInput');
    zone.addEventListener('click', () => input.click());
    zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', e => {
      e.preventDefault();
      zone.classList.remove('drag-over');
      if (e.dataTransfer.files.length) this.uploadFile(e.dataTransfer.files[0]);
    });
    input.addEventListener('change', () => {
      if (input.files.length) this.uploadFile(input.files[0]);
      input.value = '';
    });
  },

  async uploadFile(file) {
    try {
      const res = await api.uploadDataset(file);
      this.toast(`上传成功: ${res.data_id}`);
      await this.loadDatasets();
      this.selectDataset(res.data_id);
    } catch (e) {
      this.toast(`上传失败: ${e.message}`, 'error');
    }
  },

  // ===== DATASETS =====
  async loadDatasets() {
    try {
      const list = await api.listDatasets();
      const el = document.getElementById('datasetList');
      if (!list.length) {
        el.innerHTML = '<div class="plot-placeholder" style="padding:20px;">暂无数据集</div>';
        return;
      }
      el.innerHTML = list.map(d => `
        <div class="dataset-item ${this.selectedDataset === d.data_id ? 'active' : ''}"
             onclick="app.selectDataset('${d.data_id}')">
          <div>
            <div class="dataset-item-name">${d.data_id}</div>
            <div class="dataset-item-info">${d.num_cycles} 循环 · ${d.num_data_points} 点</div>
          </div>
          <button class="dataset-item-delete"
                  onclick="event.stopPropagation(); app.deleteDataset('${d.data_id}')"
                  title="删除">✕</button>
        </div>
      `).join('');
    } catch (e) {
      console.error('loadDatasets', e);
    }
  },

  selectDataset(dataId) {
    this.selectedDataset = dataId;
    document.getElementById('plotDatasetBadge').textContent = dataId;
    this.loadDatasets();
  },

  async deleteDataset(dataId) {
    if (!confirm(`确认删除 ${dataId}？`)) return;
    try {
      await api.deleteDataset(dataId);
      if (this.selectedDataset === dataId) {
        this.selectedDataset = null;
        document.getElementById('plotDatasetBadge').textContent = '未选择数据集';
        document.getElementById('plotContainer').innerHTML = '<div class="plot-placeholder">请先选择数据集，再生成图表</div>';
      }
      this.toast(`已删除 ${dataId}`);
      await this.loadDatasets();
    } catch (e) {
      this.toast(`删除失败: ${e.message}`, 'error');
    }
  },

  // ===== PLOTS =====
  bindPlotTabs() {
    document.querySelectorAll('.plot-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        tab.classList.toggle('active');
        const type = tab.dataset.type;
        if (this.activePlotTypes.has(type)) {
          this.activePlotTypes.delete(type);
        } else {
          this.activePlotTypes.add(type);
        }
        this.updatePlotGrid();
      });
    });
    this.updatePlotGrid();
  },

  updatePlotGrid() {
    const allTypes = ['capacity_fade', 'coulombic_efficiency', 'voltage_curves', 'impedance'];
    const active = [...this.activePlotTypes];
    allTypes.forEach(t => {
      const cell = document.getElementById(`plot-${t}`);
      cell.classList.toggle('hidden', !this.activePlotTypes.has(t));
    });
    const grid = document.getElementById('plotGrid');
    grid.style.gridTemplateColumns = `repeat(${active.length || 1}, 1fr)`;
    grid.style.gridTemplateRows = '1fr';
  },

  async generatePlots() {
    if (!this.selectedDataset) { this.toast('请先选择数据集', 'error'); return; }
    if (!this.activePlotTypes.size) { this.toast('请至少选择一种图表', 'error'); return; }

    const baseParams = {};
    if (document.getElementById('paramNormalize').checked) baseParams.normalize = true;
    const cyclesVal = document.getElementById('paramCycles').value.trim();
    if (cyclesVal) baseParams.cycles = cyclesVal;

    const tasks = [...this.activePlotTypes].map(async (type) => {
      const cell = document.getElementById(`plot-${type}`);
      cell.innerHTML = '<div class="loading-spinner"></div>';
      try {
        const res = await api.getPlot(this.selectedDataset, type, baseParams);
        cell.innerHTML = `<img src="data:image/png;base64,${res.image}" alt="${type}">`;
      } catch (e) {
        cell.innerHTML = `<div class="plot-placeholder" style="color:var(--danger);">${e.message}</div>`;
      }
    });
    await Promise.all(tasks);
  },

  // ===== CHAT =====
  toggleSettings() {
    document.getElementById('settingsPanel').classList.toggle('open');
  },

  async loadSettings() {
    try {
      const s = await api.getSettings();
      document.getElementById('settModel').value = s.default_model || '';
      this.chatModel = s.default_model || 'grok-4-1-fast-reasoning';
      for (const [prov, info] of Object.entries(s.providers)) {
        if (info.api_key_set) {
          document.getElementById('settProvider').value = prov;
          document.getElementById('settBaseUrl').value = info.base_url || '';
          break;
        }
      }
    } catch (_) {}
  },

  async saveSettings() {
    const body = {
      model: document.getElementById('settModel').value || null,
      provider: document.getElementById('settProvider').value || null,
      api_key: document.getElementById('settApiKey').value || null,
      base_url: document.getElementById('settBaseUrl').value || null,
    };
    try {
      await api.updateSettings(body);
      this.chatModel = body.model || this.chatModel;
      document.getElementById('settApiKey').value = '';
      this.toast('配置已保存');
    } catch (e) {
      this.toast(`保存失败: ${e.message}`, 'error');
    }
  },

  sendChat() {
    const input = document.getElementById('chatInput');
    const msg = input.value.trim();
    if (!msg) return;
    input.value = '';

    const msgsEl = document.getElementById('chatMessages');
    msgsEl.innerHTML += `<div class="chat-msg user">${this.escapeHtml(msg)}</div>`;
    msgsEl.innerHTML += `<div class="chat-msg assistant" id="streamingMsg"><div class="typing-dots"><span></span><span></span><span></span></div></div>`;
    msgsEl.scrollTop = msgsEl.scrollHeight;

    const es = api.chatStream(msg, this.selectedDataset, this.chatModel);
    let fullText = '';
    const streamEl = document.getElementById('streamingMsg');

    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type === 'content' && data.content) {
          fullText += data.content;
          streamEl.textContent = fullText;
          msgsEl.scrollTop = msgsEl.scrollHeight;
        } else if (data.type === 'tool') {
          const toolEl = document.createElement('div');
          toolEl.className = 'chat-msg tool';
          toolEl.textContent = `🔧 调用工具: ${data.tool_name}`;
          msgsEl.insertBefore(toolEl, streamEl);
        } else if (data.type === 'done') {
          es.close();
          streamEl.removeAttribute('id');
        } else if (data.type === 'error') {
          streamEl.className = 'chat-msg error';
          streamEl.textContent = `错误: ${data.error}`;
          streamEl.removeAttribute('id');
          es.close();
        }
      } catch (_) {}
    };

    es.onerror = () => {
      es.close();
      if (streamEl && streamEl.id === 'streamingMsg') {
        if (!fullText) {
          streamEl.className = 'chat-msg error';
          streamEl.textContent = '连接失败，请检查后端是否运行';
        } else {
          streamEl.removeAttribute('id');
        }
      }
    };
  },

  // ===== REPORT =====
  async generateReport() {
    if (!this.selectedDataset) { this.toast('请先选择数据集', 'error'); return; }
    const notes = document.getElementById('reportNotes').value.trim();
    const statusEl = document.getElementById('reportStatus');
    const previewEl = document.getElementById('reportPreview');
    const btnsEl = document.getElementById('downloadBtns');

    statusEl.textContent = '正在生成报告...';
    statusEl.style.display = '';
    previewEl.style.display = 'none';
    btnsEl.style.display = 'none';

    try {
      await api.generateReport(this.selectedDataset, 'html', notes);
      const html = await api.fetchReportContent(this.selectedDataset, 'html');
      previewEl.srcdoc = html;
      previewEl.style.display = '';
      statusEl.style.display = 'none';
      btnsEl.style.display = 'flex';
    } catch (e) {
      statusEl.textContent = `生成失败: ${e.message}`;
      statusEl.style.color = 'var(--danger)';
    }
  },

  async downloadReport(format) {
    if (!this.selectedDataset) return;
    try {
      const notes = document.getElementById('reportNotes').value.trim();
      await api.generateReport(this.selectedDataset, format, notes);
      window.open(api.getReportDownloadUrl(this.selectedDataset, format), '_blank');
    } catch (e) {
      this.toast(`下载失败: ${e.message}`, 'error');
    }
  },

  // ===== UTIL =====
  escapeHtml(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  },
};

document.addEventListener('DOMContentLoaded', () => app.init());
