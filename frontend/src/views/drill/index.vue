<template>
  <section class="page" data-module="drill">
    <header class="page-head">
      <div>
        <h2>应急演练管理</h2>
        <p class="page-desc">按季度编排演练计划，把演练记录批量下发给参演班组，演练结束后逐条登记问题并跟踪到整改闭环。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">编排季度演练计划</button>
        <button class="btn" type="button" @click="exportRows">导出演练计划清单</button>
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
        <span>计划编号 / 演练名称</span>
        <input v-model="keyword" placeholder="按计划编号或演练名称检索" />
      </label>
      <label class="filter-item">
        <span>演练季度</span>
        <select v-model="quarter">
          <option value="">全部季度</option>
          <option v-for="q in quarterOptions" :key="q" :value="q">{{ q }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th>计划编号</th>
          <th>演练季度</th>
          <th>演练名称</th>
          <th>演练类型</th>
          <th>计划演练日</th>
          <th>编排人员</th>
          <th>演练记录（已下发/已完成）</th>
          <th>问题整改（已闭环/总数）</th>
          <th>闭环率</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td>{{ row['计划编号'] ?? '—' }}</td>
          <td>{{ row['演练季度'] ?? '—' }}</td>
          <td>{{ row['演练名称'] ?? '—' }}</td>
          <td>{{ row['演练类型'] ?? '—' }}</td>
          <td>{{ row['计划演练日'] ?? '—' }}</td>
          <td>{{ row['编排人员'] ?? '—' }}</td>
          <td>{{ row['演练记录数'] }}（{{ row['已下发数'] }}/{{ row['已完成数'] }}）</td>
          <td>{{ row['整组进度'] }}</td>
          <td>{{ row['整改闭环率'] }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openTracking(row)">整改跟踪</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td colspan="10" class="empty-state">暂无演练计划，可先按季度编排一条计划</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条演练计划 · 整组进度按演练记录与问题实际状态实时统计</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 编排季度演练计划 -->
    <div v-if="createVisible" class="modal-mask" @click.self="closeCreate">
      <div class="modal">
        <h3>编排季度演练计划</h3>
        <div v-for="field in createFields" :key="field.key" class="form-item">
          <label>{{ field.label }}</label>
          <input v-model="createForm[field.key]" :placeholder="field.placeholder" />
        </div>
        <p v-if="createError" class="error-text">{{ createError }}</p>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="closeCreate">取消</button>
          <button class="btn primary" type="button" :disabled="submitting" @click="submitCreate">
            {{ submitting ? '提交中…' : '保存计划' }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { request } from '@/api/client'

type PlanRow = Record<string, string | number | null>

const ENDPOINT = '/api/drill'
const router = useRouter()

const rows = ref<PlanRow[]>([])
const total = ref(0)
const errorMessage = ref('')
const keyword = ref('')
const quarter = ref('')
const quarterOptions = [
  '2026年第一季度', '2026年第二季度', '2026年第三季度', '2026年第四季度',
]

// 统计卡也直接取自列表接口汇总，不写死初始进度，避免刷新后回到初始值。
const stats = ref<{ label: string; value: string | number }[]>([
  { label: '季度计划数', value: 0 },
  { label: '演练记录总数', value: 0 },
  { label: '待整改问题', value: 0 },
  { label: '已闭环问题', value: 0 },
])

const createVisible = ref(false)
const submitting = ref(false)
const createError = ref('')
const createFields = [
  { key: '计划编号', label: '计划编号', placeholder: '如 DRIL-P2026Q4-02' },
  { key: '演练季度', label: '演练季度', placeholder: '如 2026年第四季度' },
  { key: '演练名称', label: '演练名称', placeholder: '如 停电应急演练' },
  { key: '演练类型', label: '演练类型（可空，默认综合演练）', placeholder: '如 设备故障' },
  { key: '计划演练日', label: '计划演练日', placeholder: 'YYYY-MM-DD' },
  { key: '编排人员', label: '编排人员', placeholder: '安全科·姓名' },
] as const
const createForm = reactive<Record<string, string>>({})

function resetFilters() {
  keyword.value = ''
  quarter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  for (const field of createFields) createForm[field.key] = ''
  createError.value = ''
  createVisible.value = true
}

function closeCreate() {
  createVisible.value = false
}

async function submitCreate() {
  submitting.value = true
  createError.value = ''
  try {
    const response = await request(`${ENDPOINT}/plans`, {
      method: 'POST',
      body: JSON.stringify({ values: { ...createForm } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      // 缺字段、编号重复等说明完整展示，不吞掉后端原因。
      throw new Error(payload.message || '计划编排失败')
    }
    createVisible.value = false
    await reload()
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '计划编排失败'
  } finally {
    submitting.value = false
  }
}

function openTracking(row: PlanRow) {
  void router.push({
    name: 'drill-tracking',
    params: { planId: String(row.id) },
    query: { planNo: String(row['计划编号'] ?? '') },
  })
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (keyword.value) query.set('keyword', keyword.value)
  if (quarter.value) query.set('quarter', quarter.value)
  try {
    const response = await request(`${ENDPOINT}/plans?${query.toString()}`)
    if (!response.ok) throw new Error('演练计划列表读取失败')
    const payload = await response.json()
    const items: PlanRow[] = payload.items ?? []
    rows.value = items
    total.value = payload.total ?? items.length
    // 每张卡片都由后端返回的实际条目汇总而来，整组进度不使用前端初值。
    stats.value = [
      { label: '季度计划数', value: items.length },
      {
        label: '演练记录总数',
        value: items.reduce((sum: number, item) => sum + Number(item['演练记录数'] ?? 0), 0),
      },
      {
        label: '待整改问题',
        value: items.reduce(
          (sum: number, item) => sum + Number(item['问题总数'] ?? 0) - Number(item['已闭环数'] ?? 0),
          0,
        ),
      },
      {
        label: '已闭环问题',
        value: items.reduce((sum: number, item) => sum + Number(item['已闭环数'] ?? 0), 0),
      },
    ]
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '演练计划列表读取失败'
  }
}

// onMounted 在每次从整改跟踪页返回时都会重新触发（无 keep-alive），
// 因此整组进度一定与服务端实际条目一致，刷新页面也不会回到初始值。
onMounted(reload)
</script>

<style scoped>
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}
.modal {
  width: 460px;
  background: #fff;
  border-radius: 10px;
  padding: 18px 20px;
}
.modal h3 { margin: 0 0 12px; }
.form-item { margin-bottom: 10px; }
.form-item label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
.form-item input { width: 100%; padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; }
</style>
