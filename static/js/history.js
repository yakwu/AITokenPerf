document.addEventListener('alpine:init', () => {
  Alpine.data('historyTab', () => ({
    results: [],
    search: '',
    modeFilter: '',
    modelFilter: '',
    urlFilter: '',
    concurrencyFilter: '',
    sortKey: 'timestamp',
    sortDir: 'desc',
    compareSet: new Set(),
    expandedRows: new Set(),
    ddOpen: '',

    get uniqueModels() {
      return [...new Set(this.results.map(r => r.config?.model).filter(Boolean))].sort();
    },
    get uniqueUrls() {
      const norm = u => u.replace(/\/+$/, '');
      return [...new Set(this.results.map(r => r.config?.base_url).filter(Boolean).map(norm))].sort();
    },
    get uniqueConcurrencies() {
      return [...new Set(this.results.map(r => r.config?.concurrency).filter(Boolean))].sort((a, b) => a - b);
    },

    get filtered() {
      let filtered = this.results.filter(r => {
        const c = r.config || {};
        if (this.modeFilter && c.mode !== this.modeFilter) return false;
        if (this.modelFilter && c.model !== this.modelFilter) return false;
        if (this.urlFilter && (c.base_url || '').replace(/\/+$/, '') !== this.urlFilter) return false;
        if (this.concurrencyFilter && String(c.concurrency) !== this.concurrencyFilter) return false;
        if (this.search) {
          const hay = `${c.model} ${c.base_url} ${r.timestamp} ${r.test_id || ''}`.toLowerCase();
          if (!hay.includes(this.search.toLowerCase())) return false;
        }
        return true;
      });

      filtered.sort((a, b) => {
        let va, vb;
        switch (this.sortKey) {
          case 'timestamp': va = a.timestamp || ''; vb = b.timestamp || ''; break;
          case 'test_id': va = a.test_id || ''; vb = b.test_id || ''; break;
          case 'concurrency': va = a.config?.concurrency || 0; vb = b.config?.concurrency || 0; break;
          case 'success_rate': va = a.summary?.success_rate || 0; vb = b.summary?.success_rate || 0; break;
          case 'ttft': va = a.percentiles?.TTFT?.P50 || 999; vb = b.percentiles?.TTFT?.P50 || 999; break;
          case 'e2e': va = a.percentiles?.E2E?.P50 || 999; vb = b.percentiles?.E2E?.P50 || 999; break;
          case 'throughput': va = a.summary?.throughput_rps || 0; vb = b.summary?.throughput_rps || 0; break;
          default: va = a.timestamp || ''; vb = b.timestamp || '';
        }
        const cmp = typeof va === 'string' ? va.localeCompare(vb) : va - vb;
        return this.sortDir === 'asc' ? cmp : -cmp;
      });

      return filtered;
    },

    init() {
      // Expose component reference for inline onclick handlers in innerHTML
      window._historyComponent = this;
      if (!localStorage.getItem('token')) return;
      this.refresh();
    },

    tryAutoCompare() {
      if (!window._autoCompareFilenames) return;
      const filenames = window._autoCompareFilenames;
      window._autoCompareFilenames = null;
      this.$nextTick(() => {
        const indices = [];
        for (const fn of filenames) {
          const idx = this.filtered.findIndex(r => (r._filename || r.filename) === fn);
          if (idx >= 0) indices.push(idx);
        }
        if (indices.length >= 2) {
          this.compareSet = new Set(indices);
          this.compareSet = new Set(this.compareSet);
          this.renderTable();
          setTimeout(() => this.openCompare(), 200);
        }
      });
    },

    async refresh() {
      this.results = await api('/api/results');
      this.$nextTick(() => {
        this.renderTable();
        this.tryAutoCompare();
        // Auto-expand a specific test if navigated from dashboard
        if (window._autoExpandTestId) {
          const tid = window._autoExpandTestId;
          window._autoExpandTestId = null;
          const idx = this.filtered.findIndex(r => r.test_id === tid);
          if (idx >= 0) {
            this.toggleDetail(idx);
            const row = document.getElementById(`detail-${idx}`);
            if (row) row.previousElementSibling.scrollIntoView({ behavior: 'smooth', block: 'center' });
          }
        }
      });
    },

    toggleSort(key) {
      if (this.sortKey === key) {
        this.sortDir = this.sortDir === 'desc' ? 'asc' : 'desc';
      } else {
        this.sortKey = key;
        this.sortDir = 'desc';
      }
      this.renderTable();
    },

    renderTable() {
      const filtered = this.filtered;
      const tbody = this.$refs.historyBody;
      if (!tbody) return;
      tbody.innerHTML = '';

      // Update sort header display
      document.querySelectorAll('th.sortable').forEach(t => {
        t.classList.remove('active-sort', 'asc', 'desc');
        const arrow = t.querySelector('.sort-arrow');
        if (arrow) arrow.innerHTML = '';
      });
      const activeTh = document.querySelector(`th.sortable[data-sort="${this.sortKey}"]`);
      if (activeTh) {
        activeTh.classList.add('active-sort', this.sortDir);
        const arrow = activeTh.querySelector('.sort-arrow');
        if (arrow) arrow.innerHTML = this.sortDir === 'desc' ? '&#9660;' : '&#9650;';
      }

      if (!filtered.length) {
        tbody.innerHTML = '<tr><td colspan="12" style="text-align:center;padding:40px;color:var(--text-tertiary)">\u6682\u65e0\u8bb0\u5f55</td></tr>';
        return;
      }

      filtered.forEach((r, idx) => {
        const c = r.config || {};
        const s = r.summary || {};
        const p = r.percentiles || {};
        const fn = r._filename || '';
        const successClass = (s.success_rate || 0) >= 95 ? 'color:var(--success)' : (s.success_rate || 0) >= 80 ? 'color:var(--warning)' : 'color:var(--danger)';

        const tr = document.createElement('tr');
        tr.className = 'history-row';
        tr.style.cursor = 'pointer';
        tr.onclick = (e) => {
          if (e.target.tagName === 'INPUT' || e.target.closest('.del-btn')) return;
          this.toggleDetail(idx);
        };
        tr.innerHTML = `
          <td><input type="checkbox" class="compare-check" data-idx="${idx}" ${this.compareSet.has(idx) ? 'checked' : ''} onchange="window._historyComponent && window._historyComponent.toggleCompare(${idx})"></td>
          <td style="font-family:var(--font-mono);font-size:11px;color:var(--text-tertiary)">${r.test_id || '-'}</td>
          <td>${fmtTimestamp(r.timestamp)}</td>
          <td>${c.model || '-'}</td>
          <td style="max-width:160px;overflow:hidden;text-overflow:ellipsis" title="${c.base_url || ''}">${c.base_url || '-'}</td>
          <td>${c.concurrency || '-'}</td>
          <td>${c.mode || '-'}</td>
          <td style="${successClass};font-weight:600">${fmtPct(s.success_rate)}</td>
          <td>${fmtTime(p.TTFT?.P50)}</td>
          <td>${fmtTime(p.E2E?.P50)}</td>
          <td>${fmtNum(s.throughput_rps)} /s</td>
          <td style="white-space:nowrap"><button class="del-btn expand-btn" onclick="event.stopPropagation();window._historyComponent && window._historyComponent.rerunResult(window._historyComponent.filtered[${idx}])" title="\u91cd\u65b0\u8fd0\u884c" style="color:var(--accent)">&#8635;</button><button class="del-btn expand-btn" onclick="event.stopPropagation();window._historyComponent && window._historyComponent.deleteResult('${fn}')" title="\u5220\u9664" style="color:var(--danger)">${window._historyComponent?.pendingDelete === fn ? '<span class="delete-undo">\u786e\u8ba4\u5220\u9664</span>' : '&#10005;'}</button></td>`;
        tbody.appendChild(tr);

        const detailTr = document.createElement('tr');
        detailTr.className = 'detail-row' + (this.expandedRows.has(idx) ? ' open' : '');
        detailTr.id = `detail-${idx}`;
        detailTr.innerHTML = `<td colspan="12"><div id="detail-content-${idx}"></div></td>`;
        tbody.appendChild(detailTr);

        if (this.expandedRows.has(idx)) {
          document.getElementById(`detail-content-${idx}`)
          // Render in next tick after DOM is ready
          requestAnimationFrame(() => {
            const el = document.getElementById(`detail-content-${idx}`);
            if (el && !el.innerHTML) el.innerHTML = renderResultDetail(r);
          });
        }
      });

      // Update compare button visibility
      const wrap = this.$refs.compareBtnWrap;
      if (wrap) wrap.classList.toggle('visible', this.compareSet.size >= 2);
    },

    toggleDetail(idx) {
      const row = document.getElementById(`detail-${idx}`);
      if (!row) return;
      const isOpen = row.classList.toggle('open');
      const historyRow = row.previousElementSibling;
      if (isOpen) {
        this.expandedRows.add(idx);
        if (historyRow) historyRow.classList.add('expanded');
        const r = this.filtered[idx];
        const el = document.getElementById(`detail-content-${idx}`);
        if (el) el.innerHTML = renderResultDetail(r);
      } else {
        this.expandedRows.delete(idx);
        if (historyRow) historyRow.classList.remove('expanded');
      }
    },

    toggleCompare(idx) {
      if (this.compareSet.has(idx)) this.compareSet.delete(idx); else this.compareSet.add(idx);
      this.compareSet = new Set(this.compareSet);
      const wrap = this.$refs.compareBtnWrap;
      if (wrap) wrap.classList.toggle('visible', this.compareSet.size >= 2);
      // Update checkbox
      const cb = document.querySelector(`.compare-check[data-idx="${idx}"]`);
      if (cb) cb.checked = this.compareSet.has(idx);
    },

    clearCompare() {
      this.compareSet = new Set();
      document.querySelectorAll('.compare-check').forEach(c => c.checked = false);
      const wrap = this.$refs.compareBtnWrap;
      if (wrap) wrap.classList.remove('visible');
    },

    rerunResult(r) {
      const c = r.config || {};
      window._rerunConfig = {
        profile_name: c.profile_name || '',
        base_url: c.base_url || '',
        model: c.model || '',
        max_tokens: c.max_tokens || 512,
        concurrency: c.concurrency || 100,
        mode: c.mode || 'burst',
        duration: c.duration || 120,
        timeout: c.timeout || 120,
        system_prompt: c.system_prompt || '',
        user_prompt: c.user_prompt || '',
      };
      Alpine.store('app').switchTab('benchmark');
    },

    pendingDelete: null,
    deleteTimer: null,

    deleteResult(filename) {
      if (this.pendingDelete === filename) {
        // 第二次点击：确认删除
        clearTimeout(this.deleteTimer);
        this.pendingDelete = null;
        this.confirmDelete(filename);
        return;
      }
      this.pendingDelete = filename;
      this.renderTable();
      this.deleteTimer = setTimeout(() => {
        if (this.pendingDelete === filename) {
          this.pendingDelete = null;
          this.renderTable();
        }
      }, 3000);
    },

    async confirmDelete(filename) {
      await api('/api/results/' + filename, { method: 'DELETE' });
      toast('\u5df2\u5220\u9664', 'info');
      this.refresh();
    },

    openCompare() {
      const filtered = this.filtered;
      const selected = [...this.compareSet].map(i => filtered[i]).filter(Boolean);
      if (selected.length < 2) { toast('\u8bf7\u81f3\u5c11\u9009\u62e9 2 \u6761\u8bb0\u5f55', 'info'); return; }

      const el = document.getElementById('compareContent');
      let html = '<div class="table-wrap"><table class="pct-table"><thead><tr><th>\u6307\u6807</th>';
      selected.forEach(r => {
        const c = r.config || {};
        html += `<th>${c.model || '?'}<br><small style="font-weight:400">${c.concurrency || '?'}c \u00b7 ${fmtTimestamp(r.timestamp).slice(5)}</small></th>`;
      });
      html += '</tr></thead><tbody>';

      // higherIsBetter: true = 越大越好, false = 越小越好, null = 不比较
      const rows = [
        ['成功率', r => fmtPct(r.summary?.success_rate), r => r.summary?.success_rate, true],
        ['吞吐量', r => fmtNum(r.summary?.throughput_rps) + ' /s', r => r.summary?.throughput_rps, true],
        ['Token 速率', r => fmtNum(r.summary?.token_throughput_tps, 0) + ' t/s', r => r.summary?.token_throughput_tps, true],
        ['TTFT P50', r => fmtTime(r.percentiles?.TTFT?.P50), r => r.percentiles?.TTFT?.P50, false],
        ['TTFT P95', r => fmtTime(r.percentiles?.TTFT?.P95), r => r.percentiles?.TTFT?.P95, false],
        ['TTFT P99', r => fmtTime(r.percentiles?.TTFT?.P99), r => r.percentiles?.TTFT?.P99, false],
        ['TPOT P50', r => fmtTime(r.percentiles?.TPOT?.P50), r => r.percentiles?.TPOT?.P50, false],
        ['TPOT P95', r => fmtTime(r.percentiles?.TPOT?.P95), r => r.percentiles?.TPOT?.P95, false],
        ['E2E P50', r => fmtTime(r.percentiles?.E2E?.P50), r => r.percentiles?.E2E?.P50, false],
        ['E2E P95', r => fmtTime(r.percentiles?.E2E?.P95), r => r.percentiles?.E2E?.P95, false],
        ['E2E P99', r => fmtTime(r.percentiles?.E2E?.P99), r => r.percentiles?.E2E?.P99, false],
        ['平均输出 Tokens', r => fmtNum(r.summary?.avg_output_tokens), r => r.summary?.avg_output_tokens, null],
        ['输入 Tokens', r => fmtNum(r.summary?.input_tokens?.Avg, 0), r => r.summary?.input_tokens?.Avg, null],
        ['输出 Tokens', r => fmtNum(r.summary?.output_tokens?.Avg, 0), r => r.summary?.output_tokens?.Avg, null],
        ['总输入 Tokens', r => fmtBigNum(r.summary?.total_input_tokens), r => r.summary?.total_input_tokens, null],
        ['总输出 Tokens', r => fmtBigNum(r.summary?.total_output_tokens), r => r.summary?.total_output_tokens, null],
      ];

      rows.forEach(([label, fmtFn, valFn, higherIsBetter]) => {
        html += `<tr><td>${label}</td>`;
        // 计算 best/worst
        let bestIdx = -1, worstIdx = -1;
        if (higherIsBetter !== null && selected.length >= 2) {
          const vals = selected.map(r => valFn(r) ?? null);
          const hasAny = vals.some(v => v != null);
          if (hasAny) {
            const nonNull = vals.map((v, i) => [v, i]).filter(([v]) => v != null);
            if (nonNull.length >= 2) {
              nonNull.sort((a, b) => higherIsBetter ? b[0] - a[0] : a[0] - b[0]);
              bestIdx = nonNull[0][1];
              worstIdx = nonNull[nonNull.length - 1][1];
              // 只有 best 和 worst 不同时才标记
              if (bestIdx === worstIdx) { bestIdx = -1; worstIdx = -1; }
            }
          }
        }
        selected.forEach((r, i) => {
          let cls = '';
          if (i === bestIdx) cls = ' class="compare-best"';
          else if (i === worstIdx) cls = ' class="compare-worst"';
          html += `<td${cls}>${fmtFn(r)}</td>`;
        });
        html += '</tr>';
      });

      html += '</tbody></table></div>';

      // Comparison chart
      html += `<div style="margin-top:20px"><div class="card-title" style="margin-bottom:4px">TTFT & E2E \u5bf9\u6bd4</div><div class="chart-container"><canvas id="compareChart"></canvas></div></div>`;

      el.innerHTML = html;
      document.getElementById('compareOverlay').classList.add('open');

      setTimeout(() => {
        const canvas = document.getElementById('compareChart');
        if (!canvas) return;
        const labels = selected.map(r => `${(r.config?.model||'?').slice(-12)} ${r.config?.concurrency||'?'}c`);
        new Chart(canvas, {
          type: 'bar',
          data: {
            labels,
            datasets: [
              { label: 'TTFT P50', data: selected.map(r => r.percentiles?.TTFT?.P50 || 0), backgroundColor: '#3B7DD644', borderColor: '#3B7DD6', borderWidth: 2, borderRadius: 4 },
              { label: 'TTFT P95', data: selected.map(r => r.percentiles?.TTFT?.P95 || 0), backgroundColor: '#F59E3B44', borderColor: '#F59E3B', borderWidth: 2, borderRadius: 4 },
              { label: 'E2E P50', data: selected.map(r => r.percentiles?.E2E?.P50 || 0), backgroundColor: '#E85D2644', borderColor: '#E85D26', borderWidth: 2, borderRadius: 4 },
              { label: 'E2E P95', data: selected.map(r => r.percentiles?.E2E?.P95 || 0), backgroundColor: '#D63B3B44', borderColor: '#D63B3B', borderWidth: 2, borderRadius: 4 },
            ]
          },
          options: {
            responsive: true, maintainAspectRatio: false,
            plugins: {
              legend: { position: 'top', labels: { font: { family: "'DM Sans'" }, usePointStyle: true, pointStyle: 'rectRounded' } },
              tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${fmtTime(ctx.parsed.y)}` } }
            },
            scales: {
              y: { title: { display: true, text: 'Seconds' }, grid: { color: '#F0EEE9' }, ticks: { callback: v => fmtTime(v) } },
              x: { grid: { display: false } }
            }
          }
        });
      }, 50);
    },

    closeCompare() {
      document.getElementById('compareOverlay').classList.remove('open');
    },
  }));
});
