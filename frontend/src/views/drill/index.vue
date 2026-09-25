<template>
  <section class="page" data-module="drill">
    <header class="page-head">
      <div>
        <h2>应急演练管理</h2>
        <p class="page-desc">按季度编排演练计划，一次把多条演练记录批量下发给参演班组，演练结束后逐条登记问题并跟踪到整改闭环。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">编排季度计划</button>
        <button class="btn" type="button" @click="exportRows">导出演练数据</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>计划编号 / 主题</span>
        <input v-model="keyword" placeholder="按计划编号或演练主题检索" />
      </label>
      <label class="filter-item">
        <span>演练季度</span>
        <input v-model="quarter" placeholder="如 2026-Q3" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>整改跟踪</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td>{{ row['计划编号'] }}</td>
          <td>{{ row['演练季度'] }}</td>
          <td>{{ row['演练主题'] }}</td>
          <td>{{ row['计划日期'] }}</td>
          <td>{{ row['编制人'] ?? '—' }}</td>
          <td>
            <span class="tag" :class="statusClass(row.status)">{{ row.status }}</span>
          </td>
          <td>{{ row['已确认数'] }}/{{ row['记录数'] }} 确认 · {{ row['已下发数'] }}/{{ row['记录数'] }} 下发</td>
          <td>
            演练 {{ row['演练进度'] }}
            <div class="progress-bar"><i :style="{ width: `${drillPercent(row)}%` }" /></div>
          </td>
          <td>
            闭环 {{ row['闭环进度'] }}（{{ row['整改进度'] }}%）
            <div class="progress-bar"><i :class="{ done: row['整改进度'] === 100 }" :style="{ width: `${row['整改进度']}%` }" /></div>
          </td>
          <td>
            <RouterLink class="link" :to="`/drill/${row.id}/track`">整改跟踪</RouterLink>
          </td>
          <td>
            <RouterLink class="link" :to="`/drill/${row.id}/detail`">编排与下发</RouterLink>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无演练计划，先编排一份季度演练计划</td>
        </tr>
      </tbody>
    </table>

    <section v-if="orphans.length" class="orphan-panel">
      <h3>未编入计划的演练记录（{{ orphans.length }}）</h3>
      <p class="page-desc">下列记录缺少演练计划，直接下发会被整批拦下并逐条说明；请先编入对应季度计划。</p>
      <table class="data-table">
        <thead>
          <tr><th>演练编号</th><th>演练名称</th><th>参演班组</th><th>参演人员</th><th>确认状态</th><th>状态</th></tr>
      </thead>
        <tbody>
          <tr v-for="row in orphans" :key="String(row.id)">
            <td>{{ row['演练编号'] }}</td>
            <td>{{ row['演练名称'] }}</td>
            <td>{{ row['参演班组'] }}</td>
            <td>{{ row['参演人员'] || '—' }}</td>
            <td>{{ row['确认状态'] }}</td>
            <td><span class="tag warn">缺少计划</span></td>
          </tr>
        </tbody>
      </table>
    </section>

    <footer class="page-foot">
      <span>共 {{ total }} 份季度演练计划</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="creating" class="modal-mask" @click.self="creating = false">
      <form class="modal-card" @submit.prevent="submitCreate">
        <h3>编排季度演练计划</h3>
        <label class="filter-item">
          <span>演练季度（必填，格式 YYYY-Qn）</span>
          <input v-model="form.演练季度" placeholder="如 2026-Q4" />
        </label>
        <label class="filter-item">
          <span>演练主题（必填）</span>
          <input v-model="form.演练主题" placeholder="如 冬季加药管线冻堵处置演练" />
        </label>
        <label class="filter-item">
          <span>演练场景</span>
          <input v-model="form.演练场景" placeholder="触发场景与联动范围" />
        </label>
        <label class="filter-item">
          <span>计划日期</span>
          <input v-model="form.计划日期" type="date" />
        </label>
        <label class="filter-item">
          <span>编制人</span>
          <input v-model="form.编制人" />
        </label>
        <p v-if="formError" class="error-text">{{ formError }}</p>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="creating = false">取消</button>
          <button class="btn primary" type="submit">保存计划</button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

const ENDPOINT = '/api/drill'
const columns = ['计划编号', '演练季度', '演练主题', '计划日期', '编制人', '计划状态', '参演/下发', '演练进度', '闭环进度']

const rows = ref<Row[]>([])
const orphans = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const keyword = ref('')
const quarter = ref('')

const creating = ref(false)
const formError = ref('')
const form = reactive<Record<string, string>>({ 演练季度: '', 演练主题: '', 演练场景: '', 计划日期: '', 编制人: '' })

const stats = computed(() => [
  { label: '季度计划', value: total.value },
  { label: '进行中计划', value: rows.value.filter((r) => r.status === '进行中').length },
  { label: '待整改问题', value: rows.value.reduce((sum, r) => Number(r['问题数'] ?? 0) - Number(r['闭环数'] ?? 0) + sum, 0) },
  { label: '缺计划记录', value: orphans.value.length },
])

function drillPercent(row: Row): number {
  const [done, all] = String(row['演练进度'] ?? '0/0').split('/').map(Number)
  return all ? Math.round((done / all) * 100) : 0
}

function statusClass(status: unknown): string {
  if (status === '已闭环') return 'ok'
  if (status === '进行中') return 'doing'
  if (status === '待下发') return 'warn'
  return ''
}

function resetFilters() {
  keyword.value = ''
  quarter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  formError.value = ''
  Object.keys(form).forEach((key) => { form[key] = '' })
  creating.value = true
}

async function submitCreate() {
  formError.value = ''
  try {
    const response = await request(`${ENDPOINT}/plans`, {
      method: 'POST',
      body: JSON.stringify({ values: { ...form } }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      formError.value = payload.message
      return
    }
    creating.value = false
    await reload()
  } catch (error) {
    formError.value = error instanceof Error ? error.message : '计划编排失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (keyword.value.trim()) query.set('keyword', keyword.value.trim())
  if (quarter.value.trim()) query.set('quarter', quarter.value.trim())
  try {
    const [planRes, orphanRes] = await Promise.all([
      request(`${ENDPOINT}/plans?${query.toString()}`),
      request(`${ENDPOINT}/records?plan_id=none`),
    ])
    if (!planRes.ok) throw new Error('演练计划列表读取失败')
    const payload = await planRes.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    if (orphanRes.ok) {
      const orphanPayload = await orphanRes.json()
      orphans.value = orphanPayload.items ?? []
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '应急演练列表读取失败'
  }
}

onMounted(reload)
</script>
