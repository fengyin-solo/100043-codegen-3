<template>
  <section class="page" data-module="drill-detail">
    <header class="page-head">
      <div>
        <RouterLink class="link back-link" to="/drill">← 返回演练计划列表</RouterLink>
        <h2>{{ plan['计划编号'] ?? '—' }} · {{ plan['演练主题'] ?? '' }}</h2>
        <p class="page-desc">
          {{ plan['演练季度'] }} · 计划日期 {{ plan['计划日期'] ?? '—' }} · 编制人 {{ plan['编制人'] || '—' }}
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" :disabled="!selected.length" @click="dispatchSelected">
          批量下发（{{ selected.length }}）
        </button>
        <button class="btn" type="button" @click="openCreateRecord">编排演练记录</button>
      </div>
    </header>

    <div class="stat-row">
      <article class="stat-card">
        <span class="stat-label">计划状态</span>
        <strong class="stat-value"><span class="tag" :class="statusClass(plan.status)">{{ plan.status ?? '—' }}</span></strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">参演确认</span>
        <strong class="stat-value">{{ plan['已确认数'] ?? 0 }}/{{ plan['记录数'] ?? 0 }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">演练进度</span>
        <strong class="stat-value">{{ plan['演练进度'] ?? '0/0' }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">问题闭环</span>
        <strong class="stat-value">{{ plan['闭环进度'] ?? '0/0' }}（{{ plan['整改进度'] ?? 0 }}%）</strong>
      </article>
    </div>

    <table class="data-table">
      <thead>
        <tr>
          <th class="check-col"><input type="checkbox" :checked="allChecked" :indeterminate.prop="someChecked" @change="toggleAll" /></th>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in records" :key="String(row.id)" :class="{ disabled: row.status === '已下发' || row.status === '已演练' }">
          <td class="check-col">
            <input v-model="selected" type="checkbox" :value="Number(row.id)" :disabled="!dispatchable(row)" />
          </td>
          <td>{{ row['演练编号'] }}</td>
          <td>{{ row['演练名称'] }}</td>
          <td>{{ row['参演班组'] }}</td>
          <td>{{ row['参演人员'] || '—' }}</td>
          <td>{{ row['演练时间'] || '—' }}</td>
          <td>
            <span class="tag" :class="row['确认状态'] === '已确认' ? 'ok' : 'warn'">{{ row['确认状态'] }}</span>
          </td>
          <td><span class="tag" :class="statusClass(row.status)">{{ row.status }}</span></td>
          <td>
            <template v-if="row['问题数']">
              {{ row['闭环数'] }}/{{ row['问题数'] }} 闭环
            </template>
            <span v-else>无问题</span>
          </td>
          <td class="row-actions">
            <button v-if="row.status === '待确认'" class="link" type="button" @click="recordAction('参演确认', row)">参演确认</button>
            <button v-if="row.status === '已下发'" class="link" type="button" @click="recordAction('登记结束', row)">演练结束</button>
            <button v-if="row.status === '已演练'" class="link" type="button" @click="openCreateIssue(row)">登记问题</button>
            <RouterLink class="link" :to="`/drill/${planId}/track`">整改跟踪</RouterLink>
          </td>
        </tr>
        <tr v-if="!records.length">
          <td :colspan="columns.length + 2" class="empty-state">本计划还没有演练记录，先编排一条</td>
        </tr>
      </tbody>
    </table>

    <section v-if="dispatchResults.length" class="dispatch-panel">
      <h3>批量下发结果：成功 {{ dispatchSummary.success }} 条，未成功 {{ dispatchSummary.failed }} 条</h3>
      <ul class="dispatch-list">
        <li v-for="item in dispatchResults" :key="String(item.id)" :class="item.ok ? 'line-ok' : 'line-fail'">
          <strong>{{ item['演练编号'] ?? item.id }}</strong>
          <span>{{ item['演练名称'] ?? '' }}</span>
          <span v-if="item.ok" class="tag ok">已下发给{{ item['参演班组'] }}</span>
          <span v-else class="error-text">{{ item.reasons.join('；') }}</span>
        </li>
      </ul>
    </section>

    <footer class="page-foot">
      <RouterLink class="link" to="/drill">返回计划列表</RouterLink>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="creatingRecord" class="modal-mask" @click.self="creatingRecord = false">
      <form class="modal-card" @submit.prevent="submitRecord">
        <h3>编排演练记录</h3>
        <label class="filter-item">
          <span>演练名称（必填）</span>
          <input v-model="recordForm.演练名称" placeholder="如 生化池冲击负荷投运演练" />
        </label>
        <label class="filter-item">
          <span>参演班组（必填）</span>
          <input v-model="recordForm.参演班组" placeholder="如 运行一班" />
        </label>
        <label class="filter-item">
          <span>参演人员</span>
          <input v-model="recordForm.参演人员" placeholder="多人用顿号分隔，参演人确认前可补充" />
        </label>
        <label class="filter-item">
          <span>演练时间</span>
          <input v-model="recordForm.演练时间" placeholder="如 2026-10-12 09:00" />
        </label>
        <p v-if="formError" class="error-text">{{ formError }}</p>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="creatingRecord = false">取消</button>
          <button class="btn primary" type="submit">保存记录</button>
        </div>
      </form>
    </div>

    <div v-if="issueTarget" class="modal-mask" @click.self="issueTarget = null">
      <form class="modal-card" @submit.prevent="submitIssue">
        <h3>登记演练问题 · {{ issueTarget['演练名称'] }}</h3>
        <p class="page-desc">演练结束后逐条登记，每条问题独立跟踪到闭环。</p>
        <label class="filter-item">
          <span>问题描述（必填）</span>
          <textarea v-model="issueForm.问题描述" rows="3" placeholder="演练中暴露的具体问题" />
        </label>
        <label class="filter-item">
          <span>责任人（必填）</span>
          <input v-model="issueForm.责任人" />
        </label>
        <label class="filter-item">
          <span>整改期限</span>
          <input v-model="issueForm.整改期限" type="date" />
        </label>
        <p v-if="formError" class="error-text">{{ formError }}</p>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="issueTarget = null">取消</button>
          <button class="btn primary" type="submit">登记并进入整改</button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

const props = defineProps<{ id: string }>()
const planId = Number(props.id)
const ENDPOINT = '/api/drill'
const columns = ['演练编号', '演练名称', '参演班组', '参演人员', '演练时间', '确认状态', '记录状态', '问题闭环']

type Row = Record<string, string | number | boolean | null>
type DispatchItem = {
  id: number
  ok: boolean
  reasons: string[]
  演练编号?: string
  演练名称?: string
  参演班组?: string
}

const plan = ref<Row>({})
const records = ref<Row[]>([])
const selected = ref<number[]>([])
const dispatchResults = ref<DispatchItem[]>([])
const errorMessage = ref('')

const creatingRecord = ref(false)
const issueTarget = ref<Row | null>(null)
const formError = ref('')
const recordForm = reactive<Record<string, string>>({ 演练名称: '', 参演班组: '', 参演人员: '', 演练时间: '' })
const issueForm = reactive<Record<string, string>>({ 问题描述: '', 责任人: '', 整改期限: '' })

const dispatchableRows = computed(() => records.value.filter(dispatchable))
const allChecked = computed(() => dispatchableRows.value.length > 0 && dispatchableRows.value.every((r) => selected.value.includes(Number(r.id))))
const someChecked = computed(() => selected.value.length > 0 && !allChecked.value)
const dispatchSummary = computed(() => ({
  success: dispatchResults.value.filter((i) => i.ok).length,
  failed: dispatchResults.value.filter((i) => !i.ok).length,
}))

function dispatchable(row: Row): boolean {
  return row.status === '待下发' || row.status === '待确认'
}

function statusClass(status: unknown): string {
  if (status === '已闭环' || status === '已演练') return 'ok'
  if (status === '进行中' || status === '已下发' || status === '整改中' || status === '待验收') return 'doing'
  if (status === '待下发') return 'warn'
  return ''
}

function toggleAll(event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  selected.value = checked ? dispatchableRows.value.map((r) => Number(r.id)) : []
}

function openCreateRecord() {
  formError.value = ''
  Object.keys(recordForm).forEach((key) => { recordForm[key] = '' })
  creatingRecord.value = true
}

function openCreateIssue(row: Row) {
  formError.value = ''
  Object.keys(issueForm).forEach((key) => { issueForm[key] = '' })
  issueTarget.value = row
}

async function submitRecord() {
  formError.value = ''
  try {
    const response = await request(`${ENDPOINT}/records`, {
      method: 'POST',
      body: JSON.stringify({ values: { ...recordForm, plan_id: planId } }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      formError.value = payload.message
      return
    }
    creatingRecord.value = false
    await reload()
  } catch (error) {
    formError.value = error instanceof Error ? error.message : '演练记录编排失败'
  }
}

async function submitIssue() {
  formError.value = ''
  try {
    const response = await request(`${ENDPOINT}/issues`, {
      method: 'POST',
      body: JSON.stringify({ values: { ...issueForm, record_id: issueTarget.value?.id } }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      formError.value = payload.message
      return
    }
    issueTarget.value = null
    await reload()
  } catch (error) {
    formError.value = error instanceof Error ? error.message : '问题登记失败'
  }
}

async function recordAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/records/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      errorMessage.value = payload.message
      return
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '演练操作失败'
  }
}

async function dispatchSelected() {
  errorMessage.value = ''
  dispatchResults.value = []
  const ids = [...selected.value]
  try {
    const response = await request(`${ENDPOINT}/records/dispatch`, {
      method: 'POST',
      body: JSON.stringify({ ids }),
    })
    const payload = await response.json()
    dispatchResults.value = payload.items ?? []
    selected.value = []
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '批量下发失败'
  }
}

async function reload() {
  errorMessage.value = ''
  try {
    const [planRes, recordRes] = await Promise.all([
      request(`${ENDPOINT}/plans/${planId}`),
      request(`${ENDPOINT}/plans/${planId}/records`),
    ])
    if (!planRes.ok) throw new Error('演练计划读取失败')
    plan.value = await planRes.json()
    if (!recordRes.ok) throw new Error('演练记录读取失败')
    const payload = await recordRes.json()
    records.value = payload.items ?? []
    selected.value = selected.value.filter((id) =>
      records.value.some((r) => Number(r.id) === id && dispatchable(r)),
    )
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '演练明细读取失败'
  }
}

onMounted(reload)
</script>
