<template>
  <section class="tab-content active">
    <!-- 子 Tab 切换器 -->
    <div class="radio-group-inline" style="margin-bottom:20px">
      <label class="radio-pill" :class="{ active: subMode === 'single' }" @click="subMode = 'single'">
        <span>单次测试</span>
      </label>
      <label class="radio-pill" :class="{ active: subMode === 'schedule' }" @click="subMode = 'schedule'">
        <span>定时任务</span>
      </label>
    </div>

    <!-- ========== 单次测试模式 ========== -->
    <template v-if="subMode === 'single'">
      <div class="card">
        <div class="card-header">
          <div class="card-title">测试配置</div>
        </div>

        <!-- Profile 选择 -->
        <div class="profile-section">
          <div class="profile-bar">
            <div class="profile-chips">
              <template v-for="p in profiles" :key="p.name">
                <div class="profile-chip" :class="{ active: multiMode ? multiSelectedProfiles.includes(p.name) : (selectedProfileName === p.name), 'multi-check': multiMode }" @click="multiMode ? toggleMultiProfile(p.name) : selectProfile(p.name)">
                  <span class="profile-chip-check" v-show="multiMode && multiSelectedProfiles.includes(p.name)">&#10003;</span>
                  <span class="profile-chip-name">{{ p.name }}</span>
                  <span class="profile-chip-meta">{{ profileHost(p.base_url) }}</span>
                </div>
              </template>
              <router-link to="/config" class="profile-chip profile-chip-add" title="管理配置">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
                <span>管理</span>
              </router-link>
            </div>
            <button class="btn btn-ghost btn-sm" @click="toggleMultiMode()" v-show="!running && profiles.length >= 2" style="flex-shrink:0">{{ multiMode ? '切回单配置' : '多配置对比' }}</button>
          </div>
          <div class="profile-multi-hint" v-show="multiMode">
            <span>已选 <strong>{{ multiSelectedProfiles.length }}</strong> 个配置，至少需要 2 个</span>
          </div>
        </div>

        <!-- 当前选中的 Profile 信息 -->
        <div v-if="currentProfile && !multiMode" class="selected-profile-info">
          <div class="profile-info-row">
            <span class="profile-info-label">目标地址</span>
            <span class="profile-info-value">{{ currentProfile.base_url }}</span>
          </div>
          <div class="profile-info-row">
            <span class="profile-info-label">模型</span>
            <span class="profile-info-value">{{ (currentProfile.models || []).join(', ') || currentProfile.model || '未设置' }}</span>
          </div>
          <div class="profile-info-row" v-if="currentProfile.provider">
            <span class="profile-info-label">厂商</span>
            <span class="profile-info-value">{{ providerLabel(currentProfile.provider) }}</span>
          </div>
        </div>

        <!-- 测试参数表单 -->
        <div class="form-grid">
          <div class="form-group full">
            <label class="form-label">并发级别 <span class="info-tip" data-tip="选择并发连接数">?</span></label>
            <div class="chip-group">
              <template v-for="val in concurrencyPresets" :key="val">
                <div class="chip" :class="{ selected: selectedConcurrency === val }" @click="selectedConcurrency = val">
                  <span>{{ val }}</span>
                </div>
              </template>
              <div class="chip-custom">
                <input class="form-input" type="number" v-model.number="customConcurrency" placeholder="自定义" min="1" style="width:90px;padding:6px 10px;font-size:13px" @keydown.enter.prevent="addCustomConcurrency()">
                <button class="btn btn-ghost btn-sm" @click="addCustomConcurrency()" style="padding:6px 10px">+</button>
              </div>
            </div>
          </div>
          <div class="form-group">
            <label class="form-label">每级请求数 <span class="info-tip" data-tip="每个并发级别发送的总请求数，默认等于并发数">?</span></label>
            <input class="form-input" type="number" v-model.number="requestsPerLevel" placeholder="默认等于并发数" min="1">
          </div>
          <div class="form-group">
            <label class="form-label">最大输出 Tokens</label>
            <input class="form-input" type="number" v-model.number="form.max_tokens">
          </div>
          <div class="form-group">
            <label class="form-label">测试模式</label>
            <div class="radio-group-inline">
              <label class="radio-pill" :class="{ active: form.mode === 'burst' }" @click="form.mode = 'burst'">
                <span>Burst <small>瞬时并发</small></span>
              </label>
              <label class="radio-pill" :class="{ active: form.mode === 'sustained' }" @click="form.mode = 'sustained'">
                <span>Sustained <small>持续压力</small></span>
              </label>
            </div>
          </div>
          <div class="form-group" v-show="form.mode === 'sustained'">
            <label class="form-label">持续时长 (秒) <span class="info-tip" data-tip="持续模式下每个并发级别的运行时长（秒）">?</span></label>
            <input class="form-input" type="number" v-model.number="form.duration">
          </div>
          <div class="form-group">
            <label class="form-label">超时时间 (秒)</label>
            <input class="form-input" type="number" v-model.number="form.timeout">
          </div>
          <div class="form-group full">
            <label class="form-label">系统提示词</label>
            <input class="form-input" v-model="form.system_prompt">
          </div>
          <div class="form-group full">
            <label class="form-label">用户提示词</label>
            <textarea class="form-textarea" v-model="form.user_prompt" rows="2"></textarea>
          </div>
        </div>

        <div class="btn-group" style="margin-top:20px">
          <button class="btn btn-primary" v-show="!running && !multiMode" @click="startBench()" :disabled="!selectedProfileName">开始测试</button>
          <button class="btn btn-primary" v-show="!running && multiMode" @click="startMultiBench()" :disabled="multiSelectedProfiles.length < 2">开始多配置对比测试</button>
          <button class="btn btn-danger" v-show="running" @click="stopBench()">停止</button>
          <button class="btn btn-ghost" v-show="!running && !multiMode" @click="dryRun()" :disabled="!selectedProfileName">连通性验证 <span style="font-weight:400;color:var(--text-tertiary)">(单请求)</span></button>
        </div>

        <!-- Progress Panel -->
        <div class="progress-panel" :class="{ active: running }" v-show="running && !multiMode">
          <div class="card">
            <div class="card-header">
              <div class="card-title">运行中...</div>
            </div>
            <div class="progress-bar-wrap">
              <div class="progress-bar" :style="'width:' + (progress.total > 0 ? (progress.done / progress.total * 100).toFixed(1) : 0) + '%'"></div>
            </div>
            <div class="progress-stats">
              <div class="progress-stat">
                <div class="progress-stat-value">{{ progress.done }}</div>
                <div class="progress-stat-label">已完成</div>
              </div>
              <div class="progress-stat">
                <div class="progress-stat-value" style="color:var(--success)">{{ progress.success }}</div>
                <div class="progress-stat-label">成功</div>
              </div>
              <div class="progress-stat">
                <div class="progress-stat-value" style="color:var(--danger)">{{ progress.failed }}</div>
                <div class="progress-stat-label">失败</div>
              </div>
              <div class="progress-stat">
                <div class="progress-stat-value">{{ progress.elapsed + 's' }}</div>
                <div class="progress-stat-label">耗时</div>
              </div>
              <div class="progress-stat">
                <div class="progress-stat-value">{{ progress.rate }}</div>
                <div class="progress-stat-label">请求/秒</div>
              </div>
            </div>
            <div class="progress-log" ref="progressLogRef">
              <template v-for="(log, i) in logs" :key="i">
                <div v-html="log"></div>
              </template>
            </div>
          </div>
        </div>

        <!-- Multi-Server Progress Panel -->
        <div class="progress-panel" :class="{ active: running && multiMode }" v-show="running && multiMode">
          <div class="card">
            <div class="card-header">
              <div class="card-title">多配置并行测试</div>
            </div>
            <template v-for="tid in Object.keys(multiTasks)" :key="tid">
              <div class="multi-task-progress" style="margin-bottom:16px">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
                  <span style="font-weight:600;font-size:13px">{{ multiTasks[tid]?.model_name || multiTasks[tid]?.profile_name || tid }}</span>
                  <span class="status-badge" :class="multiTasks[tid]?.status" style="font-size:11px">{{ multiTasks[tid]?.status === 'running' ? '运行中' : multiTasks[tid]?.status === 'completed' ? '已完成' : multiTasks[tid]?.status }}</span>
                </div>
                <div class="progress-bar-wrap">
                  <div class="progress-bar" :style="'width:' + (multiTasks[tid]?.progress.total > 0 ? (multiTasks[tid]?.progress.done / multiTasks[tid]?.progress.total * 100).toFixed(1) : 0) + '%'"></div>
                </div>
                <div class="progress-stats" style="padding:8px 0">
                  <div class="progress-stat">
                    <div class="progress-stat-value" style="font-size:16px">{{ multiTasks[tid]?.progress.done || 0 }}</div>
                    <div class="progress-stat-label">已完成</div>
                  </div>
                  <div class="progress-stat">
                    <div class="progress-stat-value" style="color:var(--success);font-size:16px">{{ multiTasks[tid]?.progress.success || 0 }}</div>
                    <div class="progress-stat-label">成功</div>
                  </div>
                  <div class="progress-stat">
                    <div class="progress-stat-value" style="color:var(--danger);font-size:16px">{{ multiTasks[tid]?.progress.failed || 0 }}</div>
                    <div class="progress-stat-label">失败</div>
                  </div>
                  <div class="progress-stat">
                    <div class="progress-stat-value" style="font-size:16px">{{ (multiTasks[tid]?.progress.elapsed || 0) + 's' }}</div>
                    <div class="progress-stat-label">耗时</div>
                  </div>
                </div>
              </div>
            </template>
          </div>
        </div>

        <!-- Live Results -->
        <div class="live-results" ref="liveResultsRef">
          <template v-for="(lr, i) in liveResults" :key="i">
            <div class="card" style="margin-bottom:16px">
              <div class="live-result-content"></div>
            </div>
          </template>
        </div>
      </div>
    </template>

    <!-- ========== 定时任务模式 ========== -->
    <template v-if="subMode === 'schedule'">
      <!-- 创建卡片 -->
      <div class="card" style="margin-bottom:20px">
        <div class="card-header">
          <div class="card-title">定时任务</div>
          <button class="btn btn-primary btn-sm" @click="showCreateForm = !showCreateForm">
            {{ showCreateForm ? '取消' : '新建定时任务' }}
          </button>
        </div>

        <!-- 创建表单 -->
        <div v-show="showCreateForm" style="margin-top:16px">
          <div class="form-grid" style="max-width:600px">
            <div class="form-group full">
              <label class="form-label">任务名称</label>
              <input class="form-input" v-model="createForm.name" @input="nameAutoGenerated = false" placeholder="自动或手动填写">
            </div>
            <div class="form-group full">
              <label class="form-label">选择配置</label>
              <div style="display:flex;align-items:flex-start;gap:8px;flex-wrap:wrap">
                <ProfileChips :profiles="profileNames" :selected="createForm.profile_ids" @update:selected="createForm.profile_ids = $event" />
                <button class="profile-chip profile-chip-add" style="width:auto;min-width:auto;padding:8px 14px" @click="showNewProfile = !showNewProfile" title="新建配置">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                </button>
              </div>
              <!-- 新建配置 inline 表单 -->
              <div v-show="showNewProfile" class="new-profile-inline">
                <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">
                  <input class="form-input" v-model="newProfile.name" placeholder="配置名称" style="width:130px;padding:6px 10px;font-size:12px">
                  <input class="form-input" v-model="newProfile.base_url" placeholder="目标地址" style="flex:1;min-width:180px;padding:6px 10px;font-size:12px">
                  <input class="form-input" v-model="newProfile.api_key" placeholder="API Key" style="width:160px;padding:6px 10px;font-size:12px" type="password">
                  <input class="form-input" v-model="newProfile.model" placeholder="模型" style="width:140px;padding:6px 10px;font-size:12px">
                  <button class="btn btn-primary btn-sm" @click="saveNewProfile()" :disabled="!newProfile.name.trim() || !newProfile.base_url.trim() || !newProfile.model.trim()">保存</button>
                  <button class="btn btn-ghost btn-sm" @click="showNewProfile = false">取消</button>
                </div>
              </div>
            </div>
            <div class="form-group">
              <label class="form-label">并发数</label>
              <input class="form-input" type="number" v-model.number="createForm.concurrency" min="1">
            </div>
            <div class="form-group">
              <label class="form-label">执行间隔（秒）</label>
              <input class="form-input" type="number" v-model.number="createForm.schedule_value" min="60">
              <span style="font-size:11px;color:var(--text-tertiary)">每 {{ formatInterval(createForm.schedule_value) }} 执行一次</span>
            </div>
            <div class="form-group">
              <label class="form-label">测试模式</label>
              <div class="radio-group-inline">
                <label class="radio-pill" :class="{ active: createForm.mode === 'burst' }" @click="createForm.mode = 'burst'"><span>Burst</span></label>
                <label class="radio-pill" :class="{ active: createForm.mode === 'sustained' }" @click="createForm.mode = 'sustained'"><span>Sustained</span></label>
              </div>
            </div>
            <div class="form-group" v-show="createForm.mode === 'sustained'">
              <label class="form-label">持续时长 (秒)</label>
              <input class="form-input" type="number" v-model.number="createForm.duration">
            </div>
          </div>
          <div class="btn-group" style="margin-top:16px">
            <button class="btn btn-primary" @click="createSchedule" :disabled="createLoading">
              <span v-show="!createLoading">创建</span>
              <span v-show="createLoading">创建中...</span>
            </button>
          </div>
        </div>
      </div>

      <!-- 任务列表 -->
      <div class="card" style="padding:0;overflow-x:auto">
        <div v-if="loading" style="text-align:center;color:var(--text-tertiary);padding:32px">加载中...</div>
        <div v-else class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>名称</th>
                <th>配置</th>
                <th>间隔</th>
                <th>状态</th>
                <th>上次运行</th>
                <th>运行次数</th>
                <th style="width:140px"></th>
              </tr>
            </thead>
            <tbody>
              <template v-for="s in schedules" :key="s.id">
                <tr style="cursor:pointer" @click="onRowClick($event, s.id)">
                  <td style="font-weight:600">
                    <span>{{ s.name }}</span>
                    <span style="font-size:11px;color:var(--text-tertiary);font-weight:400;margin-left:4px">#{{ s.id }}</span>
                    <span style="font-size:11px;color:var(--text-tertiary);margin-left:4px">
                      <i class="ph" :class="expandedScheduleId === s.id ? 'ph-caret-up' : 'ph-caret-down'"></i>
                    </span>
                  </td>
                  <td><span style="font-size:12px">{{ (s.profile_ids || []).join(', ') }}</span></td>
                  <td>{{ formatInterval(s.schedule_value) }}</td>
                  <td>
                    <span class="status-badge" :class="s.status">
                      <span v-if="s.status === 'active'" class="status-dot"></span>
                      <i v-if="s.status === 'paused'" class="ph ph-pause" style="font-size:10px"></i>
                      {{ s.status === 'active' ? '运行中' : s.status === 'paused' ? '已暂停' : s.status }}
                    </span>
                  </td>
                  <td style="font-size:12px;color:var(--text-tertiary)">{{ formatTime(s.last_run_at) }}</td>
                  <td>{{ s.run_count || 0 }}</td>
                  <td style="white-space:nowrap">
                    <button class="btn btn-ghost btn-sm" v-show="s.status === 'active'" @click.stop="pauseSchedule(s.id)" title="暂停"><i class="ph ph-pause"></i></button>
                    <button class="btn btn-ghost btn-sm" v-show="s.status !== 'active'" @click.stop="resumeSchedule(s.id)" title="恢复"><i class="ph ph-play"></i></button>
                    <button class="btn btn-ghost btn-sm" @click.stop="runNow(s.id)" title="立即执行"><i class="ph ph-lightning"></i></button>
                    <button class="btn btn-ghost btn-sm" @click.stop="startEdit(s)" title="编辑" style="color:var(--accent)"><i class="ph ph-pencil-simple"></i></button>
                    <InlineConfirmDelete
                      :active="deleteCandidate === s.id"
                      title="删除"
                      icon-style="color:var(--danger)"
                      @request.stop="requestDelete(s.id)"
                      @cancel.stop="deleteCandidate = null"
                      @confirm.stop="confirmDelete(s.id)"
                    >
                      <i class="ph ph-trash-simple"></i>
                    </InlineConfirmDelete>
                  </td>
                </tr>
                <!-- 展开行 -->
                <tr v-if="expandedScheduleId === s.id">
                  <td colspan="7" style="padding:16px 20px;background:var(--bg-secondary)">
                    <div v-if="historyLoading" style="text-align:center;color:var(--text-tertiary);padding:20px">加载中...</div>
                    <div v-else-if="scheduleHistory.length === 0" style="text-align:center;color:var(--text-tertiary);padding:20px">暂无执行记录</div>
                    <div v-else>
                      <div style="font-size:13px;font-weight:600;margin-bottom:12px;display:flex;align-items:center;gap:12px">
                        <span>执行趋势 (共 {{ scheduleHistoryTotal }} 次执行)</span>
                        <div class="radio-group-inline" style="margin:0">
                          <label v-for="opt in timeRangeOptions" :key="opt.label" class="radio-pill" :class="{ active: selectedTimeRange === opt.hours }" @click="changeTimeRange(opt.hours)" style="cursor:pointer">
                            <span>{{ opt.label }}</span>
                          </label>
                        </div>
                      </div>
                      <div v-if="trendSummary.length > 0" class="trend-summary-cards" style="margin-bottom:16px">
                        <div v-for="card in trendSummary" :key="card.label" class="trend-card">
                          <div class="trend-card-label">{{ card.label }}</div>
                          <div class="trend-card-value" :style="card.valueStyle">{{ card.value }}</div>
                          <div class="trend-card-delta" :style="card.deltaStyle">{{ card.delta }}</div>
                        </div>
                      </div>
                      <div style="margin-bottom:12px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:16px;overflow:hidden">
                        <div style="font-size:11px;font-weight:600;color:var(--text-tertiary);margin-bottom:8px">延迟趋势 ↓ 越低越好</div>
                        <canvas v-show="scheduleTrend.length >= 1" ref="trendLatencyCanvas" style="width:100%;height:180px;max-height:180px"></canvas>
                        <div v-show="scheduleTrend.length < 1" style="height:180px;display:flex;align-items:center;justify-content:center;color:var(--text-tertiary);font-size:12px">暂无趋势数据，至少需要 1 次执行</div>
                      </div>
                      <div style="margin-bottom:16px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:16px;overflow:hidden">
                        <div style="font-size:11px;font-weight:600;color:var(--text-tertiary);margin-bottom:8px">质量趋势 ↑ 越高越好</div>
                        <canvas v-show="scheduleTrend.length >= 1" ref="trendQualityCanvas" style="width:100%;height:180px;max-height:180px"></canvas>
                        <div v-show="scheduleTrend.length < 1" style="height:180px;display:flex;align-items:center;justify-content:center;color:var(--text-tertiary);font-size:12px">暂无趋势数据，至少需要 1 次执行</div>
                      </div>
                      <div style="font-size:13px;font-weight:600;margin-bottom:8px">最近执行记录 ({{ scheduleHistory.length }} / {{ scheduleHistoryTotal }})</div>
                      <table class="pct-table" style="width:100%">
                        <thead><tr><th>测试 ID</th><th>时间</th><th>模型</th><th>并发</th><th>成功率</th><th>TTFT P50</th><th>E2E P50</th><th>吞吐量</th><th></th></tr></thead>
                        <tbody>
                          <tr v-for="(r, ri) in scheduleHistory" :key="ri">
                            <td style="font-family:var(--font-mono);font-size:11px;color:var(--text-tertiary)">{{ r.test_id || '-' }}</td>
                            <td style="font-size:12px">{{ fmtTimestamp(r.timestamp) }}</td>
                            <td style="font-size:12px">{{ r.config?.model || '-' }}</td>
                            <td style="font-size:12px">{{ r.config?.concurrency || '-' }}</td>
                            <td style="font-size:12px;font-weight:600" :style="(r.summary?.success_rate || 0) >= 95 ? 'color:var(--success)' : (r.summary?.success_rate || 0) >= 80 ? 'color:var(--warning)' : 'color:var(--danger)'">{{ fmtPct(r.summary?.success_rate) }}</td>
                            <td style="font-size:12px;font-weight:600" :style="latencyColorStyle(r.percentiles?.TTFT?.P50, 0.5, 2)">{{ fmtTime(r.percentiles?.TTFT?.P50) }}</td>
                            <td style="font-size:12px;font-weight:600" :style="latencyColorStyle(r.percentiles?.E2E?.P50, 2, 10)">{{ fmtTime(r.percentiles?.E2E?.P50) }}</td>
                            <td style="font-size:12px;font-weight:600" :style="qualityColorStyle(r.summary?.throughput_rps, 20, 5)">{{ (fmtNum(r.summary?.throughput_rps) || '-') + ' /s' }}</td>
                            <td><button class="btn btn-ghost btn-sm" @click.stop="viewResultInHistory(r)" title="查看详情" style="font-size:12px;color:var(--accent)">详情 &#8594;</button></td>
                          </tr>
                        </tbody>
                      </table>
                      <div v-if="scheduleHistory.length < scheduleHistoryTotal" style="text-align:center;margin-top:12px">
                        <button class="btn btn-ghost btn-sm" @click.stop="loadMoreHistory" :disabled="historyLoadingMore" style="font-size:12px">{{ historyLoadingMore ? '加载中...' : '加载更多' }}</button>
                      </div>
                    </div>
                  </td>
                </tr>
              </template>
              <tr v-if="!loading && schedules.length === 0">
                <td colspan="7" style="text-align:center;color:var(--text-tertiary);padding:32px">暂无定时任务</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 编辑任务弹窗 -->
      <ModalOverlay :show="showEditForm" title="编辑定时任务" max-width="620px" @close="showEditForm = false">
        <div class="form-grid">
          <div class="form-group full"><label class="form-label">任务名称</label><input class="form-input" v-model="editForm.name"></div>
          <div class="form-group full"><label class="form-label">选择配置</label><ProfileChips :profiles="profileNames" :selected="editForm.profile_ids" @update:selected="editForm.profile_ids = $event" /></div>
          <div class="form-group"><label class="form-label">并发数</label><input class="form-input" type="number" v-model.number="editForm.concurrency" min="1"></div>
          <div class="form-group"><label class="form-label">执行间隔（秒）</label><input class="form-input" type="number" v-model.number="editForm.schedule_value" min="10"><span style="font-size:11px;color:var(--text-tertiary)">每 {{ formatInterval(editForm.schedule_value) }} 执行一次</span></div>
          <div class="form-group"><label class="form-label">测试模式</label><div class="radio-group-inline"><label class="radio-pill" :class="{ active: editForm.mode === 'burst' }" @click="editForm.mode = 'burst'"><span>Burst</span></label><label class="radio-pill" :class="{ active: editForm.mode === 'sustained' }" @click="editForm.mode = 'sustained'"><span>Sustained</span></label></div></div>
          <div class="form-group" v-show="editForm.mode === 'sustained'"><label class="form-label">持续时长 (秒)</label><input class="form-input" type="number" v-model.number="editForm.duration"></div>
          <div class="form-group"><label class="form-label">Max Tokens</label><input class="form-input" type="number" v-model.number="editForm.max_tokens" min="1"></div>
          <div class="form-group"><label class="form-label">超时 (秒)</label><input class="form-input" type="number" v-model.number="editForm.timeout" min="1"></div>
          <div class="form-group full"><label class="form-label">System Prompt</label><textarea class="form-input" v-model="editForm.system_prompt" rows="2" style="resize:vertical"></textarea></div>
          <div class="form-group full"><label class="form-label">User Prompt</label><textarea class="form-input" v-model="editForm.user_prompt" rows="2" style="resize:vertical"></textarea></div>
        </div>
        <div class="btn-group" style="margin-top:20px">
          <button class="btn btn-primary" @click="saveEdit" :disabled="editLoading"><span v-show="!editLoading">保存</span><span v-show="editLoading">保存中...</span></button>
          <button class="btn btn-ghost" @click="showEditForm = false">取消</button>
        </div>
      </ModalOverlay>
    </template>
  </section>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue';
import { api, getSchedules, createScheduleApi, updateScheduleApi, deleteScheduleApi,
  pauseScheduleApi, resumeScheduleApi, runNowApi, getScheduleResults, getScheduleTrend, getProfiles,
} from '../api/index.js';
import { useAppStore } from '../stores/app.js';
import { toast } from '../composables/useToast.js';
import { useBenchSSE } from '../composables/useBenchSSE.js';
import { renderResultDetail } from '../utils/resultDetail.js';
import { escHtml, fmtTime, fmtTimestamp, fmtPct, fmtNum, qualityColorStyle, latencyColorStyle } from '../utils/formatters.js';
import { aggregateToFixedPoints } from '../utils/trendAggregator.js';
import { Chart, registerables } from 'chart.js';
Chart.register(...registerables);
import InlineConfirmDelete from '../components/InlineConfirmDelete.vue';
import ModalOverlay from '../components/ModalOverlay.vue';
import ProfileChips from '../components/ProfileChips.vue';
import { useRoute, useRouter } from 'vue-router';

const store = useAppStore();
const route = useRoute();
const router = useRouter();

// ---- Sub mode ----
const subMode = ref('single');

// ========== Shared Profile state ==========
const profiles = ref([]);
const selectedProfileName = ref('');
const multiMode = ref(false);
const multiSelectedProfiles = ref([]);

const profileNames = computed(() => profiles.value.map(p => p.name));

const currentProfile = computed(() => {
  return profiles.value.find(p => p.name === selectedProfileName.value) || null;
});

const providerOptions = [
  { value: 'anthropic', label: 'Anthropic (Claude)' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'qwen', label: 'Qwen (通义千问)' },
  { value: 'google', label: 'Google (Gemini)' },
  { value: 'mistral', label: 'Mistral' },
  { value: 'cohere', label: 'Cohere' },
  { value: 'bytedance', label: '字节 (豆包)' },
  { value: 'zhipu', label: '智谱 (GLM)' },
  { value: 'moonshot', label: 'Moonshot (Kimi)' },
  { value: 'other', label: '其他' },
];

function providerLabel(val) {
  const p = providerOptions.find(o => o.value === val);
  return p ? p.label : val;
}

function profileHost(baseUrl) {
  if (!baseUrl) return '未设置';
  try { return new URL(baseUrl).host; } catch { return baseUrl; }
}

async function loadProfiles() {
  try {
    const data = await api('/api/profiles');
    profiles.value = Array.isArray(data.profiles) ? data.profiles : [];
    const active = data.active_profile || '';
    if (active && profiles.value.some(p => p.name === active)) {
      selectedProfileName.value = active;
    }
  } catch { profiles.value = []; }
}

function selectProfile(name) { selectedProfileName.value = name; }

function toggleMultiMode() {
  multiMode.value = !multiMode.value;
  if (multiMode.value) {
    multiSelectedProfiles.value = selectedProfileName.value ? [selectedProfileName.value] : [];
  } else { multiSelectedProfiles.value = []; }
}

function toggleMultiProfile(name) {
  const idx = multiSelectedProfiles.value.indexOf(name);
  if (idx >= 0) multiSelectedProfiles.value = multiSelectedProfiles.value.filter(n => n !== name);
  else multiSelectedProfiles.value = [...multiSelectedProfiles.value, name];
}

// ========== Single Test state ==========
const progressLogRef = ref(null);
const liveResultsRef = ref(null);
const form = ref({
  max_tokens: 512, mode: 'burst', duration: 120, timeout: 120,
  system_prompt: 'You are a helpful assistant.',
  user_prompt: 'Write a short essay about the future of artificial intelligence in exactly 200 words.',
});
const concurrencyPresets = ref([1, 10, 50, 100, 200, 500, 1000]);
const selectedConcurrency = ref(100);
const customConcurrency = ref('');
const requestsPerLevel = ref('');
const running = ref(false);
const progress = ref({ done: 0, total: 0, success: 0, failed: 0, elapsed: 0, rate: '-' });
const logs = ref([]);
const liveResults = ref([]);
const pollTimer = ref(null);
const taskId = ref(null);
const lastCompletedFilename = ref(null);
const benchSSE = useBenchSSE();
const elapsedTimer = ref(null);
let benchStartTime = 0;
const groupId = ref(null);
const multiTasks = ref({});
const multiLogs = ref({});
const multiResults = ref({});
const multiResultFiles = ref([]);

// ========== Schedule state ==========
const loading = ref(false);
const showCreateForm = ref(false);
const schedules = ref([]);
const defaultForm = () => ({
  name: '', profile_ids: [], concurrency: 100, mode: 'burst',
  max_tokens: 512, timeout: 120, duration: 120,
  system_prompt: 'You are a helpful assistant.',
  user_prompt: 'Write a short essay about the future of artificial intelligence in exactly 200 words.',
  schedule_value: 300,
});
const createForm = ref(defaultForm());
const createLoading = ref(false);
const nameAutoGenerated = ref(true);
const showNewProfile = ref(false);
const newProfile = ref({ name: '', base_url: '', api_key: '', model: '' });
const deleteCandidate = ref(null);
const expandedScheduleId = ref(null);
const scheduleHistory = ref([]);
const scheduleHistoryTotal = ref(0);
const scheduleTrend = ref([]);
const trendSummary = ref([]);
const historyLoading = ref(false);
const historyLoadingMore = ref(false);
const selectedTimeRange = ref(6);
const timeRangeOptions = [
  { label: '6h', hours: 6 },
  { label: '24h', hours: 24 },
  { label: '7d', hours: 168 },
];
const showEditForm = ref(false);
const editLoading = ref(false);
const editForm = ref({ id: null, ...defaultForm() });
const trendLatencyCanvas = ref(null);
const trendQualityCanvas = ref(null);
let trendLatencyChart = null;
let trendQualityChart = null;
const lastKnownResultIds = ref({});
const schedulePollTimer = ref(null);

// ---- Rerun config ----
watch(() => route.path, (val) => {
  if (val === '/bench' && store.rerunConfig) loadProfiles().then(() => applyRerunConfig());
});
watch(() => store.rerunConfig, (val) => {
  if (val && route.path === '/bench') loadProfiles().then(() => applyRerunConfig());
});

// ========== Single Test methods ==========
function getProfileConfig() {
  const p = currentProfile.value;
  if (!p) return null;
  return { base_url: p.base_url, api_key: p.api_key_display || '', model: p.model, provider: p.provider || '' };
}

function getFormConfig() {
  const pc = getProfileConfig();
  if (!pc) return null;
  const conc = selectedConcurrency.value || 100;
  const requests = parseInt(requestsPerLevel.value);
  const config = {
    ...pc, concurrency_levels: [conc], mode: form.value.mode,
    max_tokens: parseInt(form.value.max_tokens) || 512,
    timeout: parseInt(form.value.timeout) || 120,
    duration: parseInt(form.value.duration) || 120,
    system_prompt: form.value.system_prompt, user_prompt: form.value.user_prompt,
  };
  if (!isNaN(requests) && requests > 0) config.requests_per_level = requests;
  return config;
}

async function startBench() {
  const config = getFormConfig();
  if (!config) { toast('请先选择一个配置', 'info'); return; }
  try {
    const res = await api('/api/bench/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(config) });
    if (res.error) { toast(res.error, 'error'); return; }
    taskId.value = res.task_id; setRunningState(true); startSSE(); toast('测试已启动', 'success');
  } catch (e) { toast('启动失败: ' + e.message, 'error'); }
}

async function stopBench() { await api('/api/bench/stop', { method: 'POST' }); toast('正在停止...', 'info'); }

async function dryRun() {
  const config = getFormConfig();
  if (!config) { toast('请先选择一个配置', 'info'); return; }
  config.concurrency_levels = [1]; config.requests_per_level = 1; config.mode = 'burst';
  try {
    const res = await api('/api/bench/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(config) });
    if (res.error) { toast(res.error, 'error'); return; }
    taskId.value = res.task_id; setRunningState(true); startSSE(); toast('连通性验证已启动（1 个请求）', 'info');
  } catch (e) { toast('失败: ' + e.message, 'error'); }
}

function setRunningState(val) {
  running.value = val;
  if (val) { logs.value = []; liveResults.value = []; lastCompletedFilename.value = null; progress.value = { done: 0, total: 0, success: 0, failed: 0, elapsed: 0, rate: '-' }; }
  store.status = val ? 'running' : 'idle';
}

function startSSE() {
  stopSSE(); benchStartTime = Date.now(); benchSSE.connect(handleEvent);
  elapsedTimer.value = setInterval(() => {
    if (running.value) {
      progress.value.elapsed = ((Date.now() - benchStartTime) / 1000).toFixed(1);
      if (progress.value.elapsed > 0 && progress.value.done > 0) progress.value.rate = (progress.value.done / progress.value.elapsed).toFixed(1);
    }
  }, 1000);
}

function stopSSE() { benchSSE.disconnect(); if (elapsedTimer.value) { clearInterval(elapsedTimer.value); elapsedTimer.value = null; } }

function startMultiPolling() { stopMultiPolling(); pollTimer.value = setInterval(() => pollMultiStatus(), 1500); pollMultiStatus(); }
function stopMultiPolling() { if (pollTimer.value) { clearInterval(pollTimer.value); pollTimer.value = null; } }

function handleEvent(type, d) {
  switch (type) {
    case 'bench:start': logLine(`<span class="info">[第 ${escHtml(d.current_level)}/${escHtml(d.total_levels)} 级] 启动 并发=${escHtml(d.concurrency)} 模式=${escHtml(d.mode)}</span>`); break;
    case 'bench:progress': progress.value = { ...progress.value, done: d.done, success: d.success, failed: d.failed, total: d.total, elapsed: d.elapsed }; if (d.elapsed > 0) progress.value.rate = (d.done / d.elapsed).toFixed(1); break;
    case 'bench:level_complete': logLine(`<span class="ok">[完成] 并发=${escHtml(d.concurrency)} ✓</span>`); liveResults.value = [...liveResults.value, { concurrency: d.concurrency, result: d.result }]; if (d.filename) lastCompletedFilename.value = d.filename; break;
    case 'bench:complete': stopSSE(); setRunningState(false); toast('测试完成！', 'success'); logLine('<span class="ok">测试完成！</span>'); if (lastCompletedFilename.value) store.pendingFilename = lastCompletedFilename.value; if (liveResults.value.length > 0) store.switchTab('history'); break;
    case 'bench:stopped': stopSSE(); setRunningState(false); toast('测试已停止', 'info'); logLine('<span class="fail">测试已被用户停止</span>'); break;
    case 'bench:error': stopSSE(); setRunningState(false); toast('错误: ' + d.error, 'error'); logLine(`<span class="fail">错误: ${escHtml(d.error)}</span>`); break;
  }
}

function logLine(html) { const time = new Date().toLocaleTimeString(); logs.value = [...logs.value, `[${time}] ${html}`]; }
function addCustomConcurrency() { const val = parseInt(customConcurrency.value); if (!val || val <= 0) return; selectedConcurrency.value = val; if (!concurrencyPresets.value.includes(val)) concurrencyPresets.value = [...concurrencyPresets.value, val].sort((a, b) => a - b); customConcurrency.value = ''; }

async function startMultiBench() {
  if (multiSelectedProfiles.value.length < 2) { toast('请至少选择 2 个配置', 'info'); return; }
  const conc = selectedConcurrency.value || 100; const requests = parseInt(requestsPerLevel.value);
  const config = { concurrency_levels: [conc], mode: form.value.mode, max_tokens: parseInt(form.value.max_tokens) || 512, timeout: parseInt(form.value.timeout) || 120, duration: parseInt(form.value.duration) || 120, system_prompt: form.value.system_prompt, user_prompt: form.value.user_prompt };
  if (!isNaN(requests) && requests > 0) config.requests_per_level = requests;
  try {
    const res = await api('/api/bench/start-multi', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tasks: multiSelectedProfiles.value.map(name => ({ profile_name: name, config })) }) });
    if (res.error) { toast(res.error, 'error'); return; }
    groupId.value = res.group_id; multiTasks.value = {}; multiLogs.value = {}; multiResults.value = {}; multiResultFiles.value = [];
    for (const tid of res.task_ids) { multiTasks.value[tid] = { profile_name: '', status: 'running', progress: { done: 0, total: 0, success: 0, failed: 0, elapsed: 0, rate: '-' }, event_seq: 0 }; multiLogs.value[tid] = []; multiResults.value[tid] = []; }
    setRunningState(true); startMultiPolling(); toast('多服务器测试已启动', 'success');
  } catch (e) { toast('启动失败: ' + e.message, 'error'); }
}

async function pollMultiStatus() {
  if (!groupId.value) return;
  try {
    const data = await api(`/api/bench/status-multi?group_id=${groupId.value}`); let allDone = true;
    for (const t of (data.tasks || [])) { const mt = multiTasks.value[t.task_id]; if (!mt) continue; mt.profile_name = t.profile_name; mt.model_name = t.model_name || ''; mt.status = t.status; mt.progress = { done: t.done, total: t.total, success: t.success, failed: t.failed, elapsed: t.elapsed, rate: t.elapsed > 0 ? (t.done / t.elapsed).toFixed(1) : '-' }; if (t.status === 'running') allDone = false; if (t.result_filenames) for (const fn of t.result_filenames) if (!multiResultFiles.value.includes(fn)) multiResultFiles.value.push(fn); }
    if (allDone && data.status === 'completed') { stopMultiPolling(); setRunningState(false); toast('所有测试完成！', 'success'); if (multiResultFiles.value.length >= 2) { store.pendingCompareFilenames = [...multiResultFiles.value]; store.switchTab('history'); } }
  } catch (e) {}
}

async function applyRerunConfig() {
  const rc = store.rerunConfig; if (!rc) return; store.rerunConfig = null;
  subMode.value = 'single';
  let matched = null;
  if (rc.profile_name) matched = profiles.value.find(p => p.name === rc.profile_name);
  if (!matched && rc.base_url) matched = profiles.value.find(p => p.base_url === rc.base_url);
  if (matched) selectedProfileName.value = matched.name;
  form.value = { ...form.value, max_tokens: rc.max_tokens, mode: rc.mode, duration: rc.duration, timeout: rc.timeout, system_prompt: rc.system_prompt, user_prompt: rc.user_prompt };
  selectedConcurrency.value = rc.concurrency;
}

watch(logs, () => { nextTick(() => { const el = progressLogRef.value; if (el) el.scrollTop = el.scrollHeight; }); }, { deep: true });
watch(liveResults, () => {
  nextTick(() => {
    const container = liveResultsRef.value; if (!container) return;
    const cards = container.querySelectorAll('.live-result-content');
    liveResults.value.forEach((lr, i) => { if (cards[i]) cards[i].innerHTML = '<div class=\'card-title\' style=\'margin-bottom:12px\'>结果 — 并发 ' + escHtml(lr.concurrency) + '</div>' + renderResultDetail(lr.result); });
  });
}, { deep: true });

// ========== Schedule methods ==========
function formatInterval(seconds) { const s = parseInt(seconds) || 0; if (s < 60) return s + ' 秒'; if (s < 3600) return (s / 60) + ' 分钟'; return (s / 3600) + ' 小时'; }
function formatTime(iso) { if (!iso) return '-'; try { const d = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z'); return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }); } catch { return iso; } }
function intervalSuffix(seconds) { const s = parseInt(seconds) || 300; if (s % 86400 === 0) return (s / 86400) + 'd'; if (s % 3600 === 0) return (s / 3600) + 'h'; if (s % 60 === 0) return (s / 60) + 'm'; return s + 's'; }

function autoGenerateName() {
  if (!nameAutoGenerated.value) return; const f = createForm.value; const profileName = f.profile_ids[0] || '';
  if (!profileName) { f.name = ''; return; }
  const suffix = intervalSuffix(f.schedule_value); let base = `${profileName}-${suffix}`;
  const existingNames = schedules.value.map(s => s.name);
  if (!existingNames.includes(base)) { f.name = base; return; }
  let i = 2; while (existingNames.includes(`${base}-${i}`)) i++; f.name = `${base}-${i}`;
}

watch([() => createForm.value.profile_ids, () => createForm.value.schedule_value], () => autoGenerateName(), { deep: true });
function destroyCharts() { if (trendLatencyChart) { trendLatencyChart.destroy(); trendLatencyChart = null; } if (trendQualityChart) { trendQualityChart.destroy(); trendQualityChart = null; } }

async function refreshSchedules() { loading.value = true; try { const data = await getSchedules(); schedules.value = data.schedules || []; } catch (e) { toast('加载失败: ' + e.message, 'error'); } loading.value = false; }

async function createSchedule() {
  const f = createForm.value; if (!f.name.trim()) { toast('请输入任务名称', 'info'); return; } if (f.profile_ids.length === 0) { toast('请至少选择一个配置', 'info'); return; }
  createLoading.value = true;
  try {
    const res = await createScheduleApi({ name: f.name.trim(), profile_ids: f.profile_ids, configs_json: { concurrency_levels: [Number(f.concurrency)], mode: f.mode, max_tokens: Number(f.max_tokens), timeout: Number(f.timeout), duration: Number(f.duration), system_prompt: f.system_prompt, user_prompt: f.user_prompt }, schedule_type: 'interval', schedule_value: String(f.schedule_value) });
    if (res.error) { toast(res.error, 'error'); return; }
    toast('定时任务已创建', 'success'); showCreateForm.value = false; createForm.value = defaultForm(); nameAutoGenerated.value = true; await refreshSchedules();
  } catch (e) { toast('创建失败: ' + e.message, 'error'); }
  createLoading.value = false;
}

async function saveNewProfile() {
  const np = newProfile.value; if (!np.name.trim() || !np.base_url.trim() || !np.model.trim()) return;
  try {
    await api('/api/profiles/save', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: np.name.trim(), base_url: np.base_url.trim(), api_key: np.api_key.trim(), model: np.model.trim(), api_version: '2023-06-01' }) });
    toast('配置已保存', 'success'); showNewProfile.value = false; newProfile.value = { name: '', base_url: '', api_key: '', model: '' };
    await loadProfiles(); const savedName = np.name.trim(); if (!createForm.value.profile_ids.includes(savedName)) createForm.value.profile_ids = [...createForm.value.profile_ids, savedName];
  } catch (e) { toast('保存失败: ' + e.message, 'error'); }
}

async function pauseSchedule(id) { try { await pauseScheduleApi(id); toast('已暂停', 'info'); await refreshSchedules(); } catch (e) { toast('操作失败: ' + e.message, 'error'); } }
async function resumeSchedule(id) { try { await resumeScheduleApi(id); toast('已恢复', 'success'); await refreshSchedules(); } catch (e) { toast('操作失败: ' + e.message, 'error'); } }
async function runNow(id) { try { await runNowApi(id); toast('已触发执行', 'info'); } catch (e) { toast('触发失败: ' + e.message, 'error'); } }
function requestDelete(id) { deleteCandidate.value = id; }
async function confirmDelete(id) { try { await deleteScheduleApi(id); toast('已删除', 'info'); deleteCandidate.value = null; await refreshSchedules(); } catch (e) { toast('删除失败: ' + e.message, 'error'); } }

function startEdit(s) {
  const configs = s.configs || {};
  editForm.value = { id: s.id, name: s.name || '', profile_ids: [...(s.profile_ids || [])], concurrency: (configs.concurrency_levels || [100])[0], mode: configs.mode || 'burst', max_tokens: configs.max_tokens || 512, timeout: configs.timeout || 120, duration: configs.duration || 120, system_prompt: configs.system_prompt || 'You are a helpful assistant.', user_prompt: configs.user_prompt || 'Write a short essay about the future of artificial intelligence in exactly 200 words.', schedule_value: parseInt(s.schedule_value) || 300 };
  showEditForm.value = true;
}

async function saveEdit() {
  const f = editForm.value; if (!f.name.trim()) { toast('请输入任务名称', 'info'); return; } if (f.profile_ids.length === 0) { toast('请至少选择一个配置', 'info'); return; }
  editLoading.value = true;
  try {
    const res = await updateScheduleApi(f.id, { name: f.name.trim(), profile_ids: f.profile_ids, configs_json: { concurrency_levels: [Number(f.concurrency)], mode: f.mode, max_tokens: Number(f.max_tokens), timeout: Number(f.timeout), duration: Number(f.duration), system_prompt: f.system_prompt, user_prompt: f.user_prompt }, schedule_type: 'interval', schedule_value: String(f.schedule_value) });
    if (res.error) { toast(res.error, 'error'); return; } toast('已更新', 'success'); showEditForm.value = false; await refreshSchedules();
  } catch (e) { toast('更新失败: ' + e.message, 'error'); }
  editLoading.value = false;
}

function onRowClick(event, id) { if (event.target.closest('button')) return; toggleHistory(id); }
async function toggleHistory(id) { if (expandedScheduleId.value === id) { expandedScheduleId.value = null; destroyCharts(); return; } expandedScheduleId.value = id; await loadHistory(id); }

async function loadHistory(id) {
  historyLoading.value = true; trendSummary.value = []; scheduleHistory.value = []; scheduleHistoryTotal.value = 0; selectedTimeRange.value = 6;
  const hours = selectedTimeRange.value;
  try { const [listData, trendData] = await Promise.all([getScheduleResults(id, { limit: 100, offset: 0, hours }), getScheduleTrend(id, { hours })]); scheduleHistory.value = listData.results || []; scheduleHistoryTotal.value = listData.total || 0; scheduleTrend.value = trendData.trend || []; }
  catch (e) { toast('加载执行记录失败: ' + e.message, 'error'); scheduleHistory.value = []; scheduleTrend.value = []; }
  historyLoading.value = false; destroyCharts(); await nextTick(); renderTrendSummary(); renderLatencyChart(); renderQualityChart();
}

async function changeTimeRange(hours) {
  selectedTimeRange.value = hours;
  if (expandedScheduleId.value == null) return;
  try {
    const [listData, trendData] = await Promise.all([
      getScheduleResults(expandedScheduleId.value, { limit: 100, offset: 0, hours }),
      getScheduleTrend(expandedScheduleId.value, { hours }),
    ]);
    scheduleHistory.value = listData.results || [];
    scheduleHistoryTotal.value = listData.total || 0;
    scheduleTrend.value = trendData.trend || [];
  } catch (e) { toast('加载失败: ' + e.message, 'error'); scheduleHistory.value = []; scheduleTrend.value = []; }
  destroyCharts(); await nextTick(); renderTrendSummary(); renderLatencyChart(); renderQualityChart();
}

async function loadMoreHistory() { if (expandedScheduleId.value == null) return; historyLoadingMore.value = true; try { const data = await getScheduleResults(expandedScheduleId.value, { limit: 100, offset: scheduleHistory.value.length, hours: selectedTimeRange.value }); scheduleHistory.value = [...scheduleHistory.value, ...(data.results || [])]; } catch (e) { toast('加载更多失败: ' + e.message, 'error'); } historyLoadingMore.value = false; }

function renderTrendSummary() {
  const results = scheduleHistory.value; if (!results || results.length === 0) { trendSummary.value = []; return; }
  function avgField(fn) { const vals = results.map(r => fn(r)).filter(v => v != null); return vals.length > 0 ? vals.reduce((a, b) => a + b, 0) / vals.length : null; }
  const aSucc = avgField(r => r.summary?.success_rate); const aThr = avgField(r => r.summary?.throughput_rps); const aTtft = avgField(r => r.percentiles?.TTFT?.P50 != null ? r.percentiles.TTFT.P50 : null); const aE2e = avgField(r => r.percentiles?.E2E?.P50 != null ? r.percentiles.E2E.P50 : null);
  const sorted = [...results].sort((a, b) => (a.timestamp || '').localeCompare(b.timestamp || '')); const mid = Math.floor(sorted.length / 2); const recentHalf = sorted.slice(mid); const prevHalf = sorted.slice(0, mid);
  function avgHalf(arr, fn) { const vals = arr.map(r => fn(r)).filter(v => v != null); return vals.length > 0 ? vals.reduce((a, b) => a + b, 0) / vals.length : null; }
  const pSucc = prevHalf.length > 0 ? avgHalf(prevHalf, r => r.summary?.success_rate) : null; const pThr = prevHalf.length > 0 ? avgHalf(prevHalf, r => r.summary?.throughput_rps) : null; const pTtft = prevHalf.length > 0 ? avgHalf(prevHalf, r => r.percentiles?.TTFT?.P50 != null ? r.percentiles.TTFT.P50 : null) : null; const pE2e = prevHalf.length > 0 ? avgHalf(prevHalf, r => r.percentiles?.E2E?.P50 != null ? r.percentiles.E2E.P50 : null) : null;
  function deltaStr(curr, prevVal, unit, higherIsBetter) { if (curr == null || prevVal == null) return { delta: '-', deltaStyle: '' }; const diff = curr - prevVal; const absDiff = Math.abs(diff); const arrow = diff > 0 ? '↑' : diff < 0 ? '↓' : '→'; const isGood = higherIsBetter ? diff >= 0 : diff <= 0; const color = diff === 0 ? 'color:var(--text-tertiary)' : isGood ? 'color:var(--success)' : 'color:var(--danger)'; return { delta: `${arrow} ${absDiff.toFixed(1)}${unit}`, deltaStyle: color }; }
  trendSummary.value = [
    { label: '成功率', value: aSucc != null ? aSucc.toFixed(1) + '%' : '-', valueStyle: aSucc >= 95 ? 'color:var(--success)' : aSucc >= 80 ? 'color:var(--warning)' : 'color:var(--danger)', ...deltaStr(aSucc, pSucc, '%', true) },
    { label: '吞吐量', value: aThr != null ? aThr.toFixed(1) + '/s' : '-', valueStyle: '', ...deltaStr(aThr, pThr, '/s', true) },
    { label: 'TTFT P50', value: aTtft != null ? aTtft.toFixed(1) + 's' : '-', valueStyle: aTtft <= 0.5 ? 'color:var(--success)' : aTtft <= 2 ? 'color:var(--warning)' : 'color:var(--danger)', ...(aTtft != null ? deltaStr(aTtft, pTtft, 's', false) : { delta: '-', deltaStyle: '' }) },
    { label: 'E2E P50', value: aE2e != null ? aE2e.toFixed(1) + 's' : '-', valueStyle: aE2e <= 2 ? 'color:var(--success)' : aE2e <= 10 ? 'color:var(--warning)' : 'color:var(--danger)', ...(aE2e != null ? deltaStr(aE2e, pE2e, 's', false) : { delta: '-', deltaStyle: '' }) },
  ];
}

function renderLatencyChart() {
  const trend = scheduleTrend.value; if (!trend || trend.length < 1) return; const canvas = trendLatencyCanvas.value; if (!canvas) return;
  const { labels, items } = aggregateToFixedPoints(trend, 144);
  trendLatencyChart = new Chart(canvas, { type: 'line', data: { labels, datasets: [{ label: 'TTFT P50', data: items.map(r => r?.avg_ttft_p50 ?? null), borderColor: '#3B7DD6', backgroundColor: '#3B7DD618', borderWidth: 2, pointRadius: trend.length <= 50 ? 3 : 0, tension: 0.3, fill: true, spanGaps: false }, { label: 'E2E P50', data: items.map(r => r?.avg_e2e_p50 ?? null), borderColor: '#E85D26', backgroundColor: '#E85D2618', borderWidth: 2, pointRadius: trend.length <= 50 ? 3 : 0, tension: 0.3, fill: true, spanGaps: false }] }, options: { responsive: true, maintainAspectRatio: false, animation: false, interaction: { mode: 'index', intersect: false }, plugins: { legend: { position: 'top', labels: { font: { family: "'DM Sans'", size: 11 }, usePointStyle: true, pointStyle: 'circle', padding: 12 } }, tooltip: { callbacks: { label: ctx => ctx.parsed.y != null ? `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)}s` : '' } } }, scales: { y: { title: { display: true, text: 'Latency (s)', font: { size: 11 } }, grid: { color: '#F0EEE9' }, ticks: { font: { family: "'JetBrains Mono'", size: 10 }, callback: v => v.toFixed(1) + 's' }, beginAtZero: true }, x: { grid: { display: false }, ticks: { font: { family: "'JetBrains Mono'", size: 10 }, maxRotation: 45, autoSkip: true, maxTicksLimit: 20 } } } } });
}

function renderQualityChart() {
  const trend = scheduleTrend.value; if (!trend || trend.length < 1) return; const canvas = trendQualityCanvas.value; if (!canvas) return;
  const { labels, items } = aggregateToFixedPoints(trend, 144);
  // 用失败率展示：失败率越高值越大，fill 自然越红，100% 成功时线在底部无填充
  const failureData = items.map(r => r?.avg_success_rate != null ? (100 - r.avg_success_rate) : null);
  trendQualityChart = new Chart(canvas, { type: 'line', data: { labels, datasets: [{ label: '吞吐量 (req/s)', data: items.map(r => r?.avg_throughput ?? null), borderColor: '#2D8B55', backgroundColor: '#2D8B5518', borderWidth: 2, pointRadius: trend.length <= 50 ? 3 : 0, tension: 0.3, fill: true, yAxisID: 'y', spanGaps: false }, { label: '失败率 (%)', data: failureData, borderColor: '#E85D26', backgroundColor: '#E85D2618', borderWidth: 2, pointRadius: trend.length <= 50 ? 3 : 0, tension: 0.3, fill: true, yAxisID: 'y1', borderDash: [5, 3], spanGaps: false }] }, options: { responsive: true, maintainAspectRatio: false, animation: false, interaction: { mode: 'index', intersect: false }, plugins: { legend: { position: 'top', labels: { font: { family: "'DM Sans'", size: 11 }, usePointStyle: true, pointStyle: 'circle', padding: 12 } }, tooltip: { callbacks: { label: ctx => { if (ctx.parsed.y == null) return ''; if (ctx.dataset.yAxisID === 'y1') return `失败率: ${ctx.parsed.y.toFixed(1)}%`; return `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)} /s`; } } } }, scales: { y: { position: 'left', title: { display: true, text: 'Throughput (req/s)', font: { size: 11 } }, grid: { color: '#F0EEE9' }, ticks: { font: { family: "'JetBrains Mono'", size: 10 } }, beginAtZero: true }, y1: { position: 'right', title: { display: true, text: '失败率 (%)', font: { size: 11 } }, grid: { drawOnChartArea: false }, ticks: { font: { family: "'JetBrains Mono'", size: 10 } }, min: 0, max: 100 }, x: { grid: { display: false }, ticks: { font: { family: "'JetBrains Mono'", size: 10 }, maxRotation: 45, autoSkip: true, maxTicksLimit: 20 } } } } });
}

function viewResultInHistory(r) { window.showDetailOverlay(renderResultDetail(r)); }

// ========== Schedule Polling ==========
async function pollScheduleUpdates() {
  if (subMode.value !== 'schedule') return;
  for (const s of schedules.value) {
    try {
      const res = await getScheduleResults(s.id, { limit: 1 });
      const results = res.results || [];
      if (results.length > 0) {
        const latestId = results[0].test_id || results[0].filename;
        if (lastKnownResultIds.value[s.id] !== undefined && lastKnownResultIds.value[s.id] !== latestId) {
          toast(`定时任务「${s.name}」有新执行结果`, 'info');
        }
        lastKnownResultIds.value[s.id] = latestId;
      }
    } catch (e) { /* 静默忽略 */ }
  }
}

function startSchedulePolling() {
  stopSchedulePolling();
  pollScheduleUpdates();
  schedulePollTimer.value = setInterval(() => pollScheduleUpdates(), 30000);
}

function stopSchedulePolling() {
  if (schedulePollTimer.value) {
    clearInterval(schedulePollTimer.value);
    schedulePollTimer.value = null;
  }
}

// ========== Lifecycle ==========
onMounted(() => {
  if (!localStorage.getItem('token')) return;
  loadProfiles(); refreshSchedules();
  startSchedulePolling();
  if (store.rerunConfig) loadProfiles().then(() => applyRerunConfig());
  checkRunningStatus();
});

onUnmounted(() => { stopSSE(); stopMultiPolling(); stopSchedulePolling(); destroyCharts(); });

async function checkRunningStatus() {
  const data = await api('/api/bench/status');
  if (data.status === 'running') { taskId.value = data.task_id; running.value = true; store.status = 'running'; subMode.value = 'single'; if (!data.scheduled_task_id) startSSE(); }
}
</script>

<style scoped>
.selected-profile-info { margin-top: 16px; padding: 12px 16px; background: var(--bg-secondary); border-radius: var(--radius); border: 1px solid var(--border); }
.profile-info-row { display: flex; align-items: center; padding: 4px 0; font-size: 13px; }
.profile-info-label { width: 80px; font-weight: 600; color: var(--text-tertiary); font-size: 12px; flex-shrink: 0; }
.profile-info-value { color: var(--text-secondary); word-break: break-all; font-size: 12px; }
.new-profile-inline { margin-top: 8px; padding: 10px 12px; background: var(--bg); border: 1px dashed var(--border); border-radius: var(--radius); }
</style>
