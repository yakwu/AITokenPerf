document.addEventListener('alpine:init', () => {
  Alpine.data('configTab', () => ({
    configText: '',

    init() {
      this.load();
    },

    async load() {
      const config = await api('/api/config');
      const yamlLines = [];
      const order = ['base_url','api_key','model','api_version','system_prompt','user_prompt','max_tokens','concurrency_levels','mode','duration','timeout','connector_limit','output_dir'];
      const seen = new Set();
      for (const k of order) {
        if (k in config) {
          seen.add(k);
          yamlLines.push(this.formatYamlLine(k, config[k]));
        }
      }
      for (const [k, v] of Object.entries(config)) {
        if (!seen.has(k) && !k.startsWith('_')) {
          yamlLines.push(this.formatYamlLine(k, v));
        }
      }
      this.configText = yamlLines.join('\n');
    },

    async save() {
      const config = {};
      for (const line of this.configText.split('\n')) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith('#')) continue;
        const idx = trimmed.indexOf(':');
        if (idx < 0) continue;
        const key = trimmed.slice(0, idx).trim();
        let val = trimmed.slice(idx + 1).trim();
        if (val.startsWith('[') && val.endsWith(']')) {
          val = val.slice(1, -1).split(',').map(s => {
            const n = Number(s.trim());
            return isNaN(n) ? s.trim().replace(/^"|"$/g, '') : n;
          });
        } else if (val.startsWith('"') && val.endsWith('"')) {
          val = val.slice(1, -1);
        } else if (val === 'true') val = true;
        else if (val === 'false') val = false;
        else { const n = Number(val); if (!isNaN(n) && val !== '') val = n; }
        config[key] = val;
      }
      try {
        await api('/api/config', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(config),
        });
        toast('\u914d\u7f6e\u5df2\u4fdd\u5b58', 'success');
      } catch (e) { toast('\u4fdd\u5b58\u5931\u8d25: ' + e.message, 'error'); }
    },

    formatYamlLine(k, v) {
      if (Array.isArray(v)) return `${k}: [${v.join(', ')}]`;
      if (typeof v === 'string') return `${k}: "${v}"`;
      return `${k}: ${v}`;
    },
  }));
});
