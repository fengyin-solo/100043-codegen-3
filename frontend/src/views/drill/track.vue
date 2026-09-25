<template>
  <section class="page" data-module="drill-track">
    <header class="page-head">
      <div>
        <RouterLink class="link back-link" to="/drill">← 返回演练计划列表</RouterLink>
        <h2>整改跟踪 · {{ plan['演练主题'] ?? '全部演练' }}</h2>
        <p class="page-desc">
          {{ plan['计划编号'] ? `${plan['计划编号']} · ` : '' }}{{ plan['演练季度'] ?? '' }}
          演练结束后逐条登记的问题在这里跟踪到闭环，进度按实际条目实时汇总。
        </p>
      </div>
    </header>

    <div class="stat-row">
      <article class="stat-card">
        <span class="stat-label">问题总数</span>
        <strong class="stat-value">{{ stats.total }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">待整改</span>
        <strong class="stat-value">{{ stats.todo }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">整改中/待验收</span>
        <strong class="stat-value">{{ stats.doing }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">已闭环</span>
        <strong class="stat-value">{{ stats.done }}（{{ stats.percent }}%）</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>整改状态</span>
        <select v-model="statusFilter">
          <option value="">全部</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="statusFilter = ''; void reload()">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in issues" :key="String(row.id)">
          <td>{{ row['问题编号'] }}</td>
          <td>{{ row['演练编号'] }}</td>
          <td>{{ row['问题描述'] }}</td>
          <td>{{ row['责任人'] }}</td>
          <td>{{ row['整改措施'] || '待填报' }}</td>
          <td>{{ row['整改期限'] || '—' }}</td>
          <td>{{ row['验收人'] || '—' }}</td>
          <td><span class="tag" :class="statusClass(row.status)">{{ row.status }}</span></td>
          <td class="row-actions">
            <button v-if="row.status === '待整改'" class="link" type="button" @click="fillMeasure(row)">填报整改</button>
            <button v-if="row.status === '整改中'" class="link" type="button" @click="issueAction('提交验收', row)">提交验收</button>
            <button v-if="row.status === '待验收'" class="link" type="button" @click="verifyClose(row)">确认闭环</button>
            <span v-if="row.status === '已闭环'" class="muted-text">闭环于 {{ row['闭环时间'] }}</span>
          </td>
        </tr>
        <tr v-if="!issues.length">
          <td :colspan="columns.length + 1" class="empty-state">当前条件下暂无整改问题</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ stats.total }} 条问题，已闭环 {{ stats.done }} 条</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

const props = defineProps<{ id?: string }>()
const planId = props.id && props.id !== 'all' ? Number(props.id) : null
const ENDPOINT = '/api/drill'
const columns = ['问题编号', '演练编号', '问题描述', '责任人', '整改措施', '整改期限', '验收人', '整改状态']
const statuses = ['待整改', '整改中', '待验收', '已闭环']

type Row = Record<string, string | number | null>

const issues = ref<Row[]>([])
const plan = ref<Record<string, string | number | null>>({})
const statusFilter = ref('')
const errorMessage = ref('')

const stats = computed(() => {
  const total = issues.value.length
  const done = issues.value.filter((r) => r.status === '已闭环').length
  const todo = issues.value.filter((r) => r.status === '待整改').length
  const doing = issues.value.filter((r) => r.status === '整改中' || r.status === '待验收').length
  return { total, done, todo, doing, percent: total ? Math.round((done / total) * 100) : 0 }
})

function statusClass(status: unknown): string {
  if (status === '已闭环') return 'ok'
  if (status === '待整改') return 'warn'
  return 'doing'
}

async function fillMeasure(row: Row) {
  const measure = window.prompt(`请填写「${row['问题编号']}」的整改措施：`)
  if (measure === null) return
  if (!measure.trim()) {
    errorMessage.value = '整改措施不能为空，问题仍停留在待整改'
    return
  }
  await issueAction('填报整改', row, { 整改措施: measure.trim() })
}

async function verifyClose(row: Row) {
  const verifier = window.prompt(`请输入「${row['问题编号']}」的验收人：`)
  if (verifier === null) return
  await issueAction('确认闭环', row, { 验收人: verifier.trim() })
}

async function issueAction(action: string, row: Row, extra: Record<string, string> = {}) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/issues/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action, ...extra } }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      errorMessage.value = payload.message
      return
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '整改动作未生效'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (planId !== null) query.set('plan_id', String(planId))
  if (statusFilter.value) query.set('status', statusFilter.value)
  try {
    const issueRes = await request(`${ENDPOINT}/issues?${query.toString()}`)
    if (!issueRes.ok) throw new Error('整改清单读取失败')
    const payload = await issueRes.json()
    issues.value = payload.items ?? []
    if (planId !== null) {
      const planRes = await request(`${ENDPOINT}/plans/${planId}`)
      if (planRes.ok) plan.value = await planRes.json()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '整改跟踪读取失败'
  }
}

onMounted(reload)
</script>
