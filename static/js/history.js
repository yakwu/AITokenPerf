document.addEventListener('alpine:init', () => {
  Alpine.data('historyTab', () => ({
    results: [],
    search: '',
    modeFilter: '',
    sortKey: 'timestamp',
    sortDir: 'desc',
    compareSet: new Set(),
    expandedRows: new Set(),

    get filtered() {
      let filtered = this.results.filter(r => {
        const c = r.config || {};
        if (this.modeFilter && c.mode !== this.modeFilter) return false;
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
      this.refresh();
    },

    async refresh() {
      this.results = await api('/api/results');
      this.$nextTick(() => {
        this.renderTable();
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
      this.$el.querySelectorAll('th.sortable').forEach(t => {
        t.classList.remove('active-sort', 'asc', 'desc');
        const arrow = t.querySelector('.sort-arrow');
        if (arrow) arrow.innerHTML = '';
      });
      const activeTh = this.$el.querySelector(`th.sortable[data-sort="${this.sortKey}"]`);
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
          <td style="white-space:nowrap"><button class="del-btn expand-btn" onclick="event.stopPropagation();window._historyComponent && window._historyComponent.rerunResult(window._historyComponent.filtered[${idx}])" title="\u91cd\u65b0\u8fd0\u884c" style="color:var(--accent)">&#8635;</button><button class="del-btn expand-btn" onclick="event.stopPropagation();window._historyComponent && window._historyComponent.deleteResult('${fn}')" title="\u5220\u9664" style="color:var(--danger)">&#10005;</button></td>`;
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
      if (isOpen) {
        this.expandedRows.add(idx);
        const r = this.filtered[idx];
        const el = document.getElementById(`detail-content-${idx}`);
        if (el) el.innerHTML = renderResultDetail(r);
      } else {
        this.expandedRows.delete(idx);
      }
    },

    toggleCompare(idx) {
      if (this.compareSet.has(idx)) this.compareSet.delete(idx); else this.compareSet.add(idx);
      this.compareSet = new Set(this.compareSet);
      const wrap = this.$refs.compareBtnWrap;
      if (wrap) wrap.classList.toggle('visible', this.compareSet.size >= 2);
      // Update checkbox
      const cb = this.$el.querySelector(`.compare-check[data-idx="${idx}"]`);
      if (cb) cb.checked = this.compareSet.has(idx);
    },

    clearCompare() {
      this.compareSet = new Set();
      this.$el.querySelectorAll('.compare-check').forEach(c => c.checked = false);
      const wrap = this.$refs.compareBtnWrap;
      if (wrap) wrap.classList.remove('visible');
    },

    rerunResult(r) {
      const c = r.config || {};
      window._rerunConfig = {
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

    async deleteResult(filename) {
      if (!confirm('\u786e\u5b9a\u5220\u9664\u8be5\u8bb0\u5f55\uff1f')) return;
      await api('/api/results/' + filename, { method: 'DELETE' });
      toast('\u5df2\u5220\u9664', 'info');
      this.refresh();
    },

    openCompare() {
      const filtered = this.filtered;
      const selected = [...this.compareSet].map(i => filtered[i]).filter(Boolean);
      if (selected.length < 2) { toast('\u8bf7\u81f3\u5c11\u9009\u62e9 2 \u6761\u8bb0\u5f55', 'info'); return; }

      const el = document.getElementById('compareContent');
      let html = '<div class="table-wrap"><table class="pct-table"><thead><tr><th>Metric</th>';
      selected.forEach(r => {
        const c = r.config || {};
        html += `<th>${c.model || '?'}<br><small style="font-weight:400">${c.concurrency || '?'}c \u00b7 ${fmtTimestamp(r.timestamp).slice(5)}</small></th>`;
      });
      html += '</tr></thead><tbody>';

      const rows = [
        ['Success Rate', r => fmtPct(r.summary?.success_rate)],
        ['Throughput', r => fmtNum(r.summary?.throughput_rps) + ' /s'],
        ['Token Rate', r => fmtNum(r.summary?.token_throughput_tps, 0) + ' t/s'],
        ['TTFT P50', r => fmtTime(r.percentiles?.TTFT?.P50)],
        ['TTFT P95', r => fmtTime(r.percentiles?.TTFT?.P95)],
        ['TTFT P99', r => fmtTime(r.percentiles?.TTFT?.P99)],
        ['TPOT P50', r => fmtTime(r.percentiles?.TPOT?.P50)],
        ['TPOT P95', r => fmtTime(r.percentiles?.TPOT?.P95)],
        ['E2E P50', r => fmtTime(r.percentiles?.E2E?.P50)],
        ['E2E P95', r => fmtTime(r.percentiles?.E2E?.P95)],
        ['E2E P99', r => fmtTime(r.percentiles?.E2E?.P99)],
        ['Avg Tokens', r => fmtNum(r.summary?.avg_output_tokens)],
      ];

      rows.forEach(([label, fn]) => {
        html += `<tr><td>${label}</td>`;
        selected.forEach(r => {
          html += `<td>${fn(r)}</td>`;
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
