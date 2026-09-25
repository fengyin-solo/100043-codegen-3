<template>
  <section class="page" data-module="drill-tracking">
    <header class="page-head">
      <div>
        <h2>
          <button class="btn ghost" type="button" @click="goBack">← 返回演练计划</button>
          整改跟踪：{{ plan['演练名称'] ?? '加载中…' }}
        </h2>
        <p class="page-desc">
          计划 {{ plan['计划编号'] ?? '—' }} · {{ plan['演练季度'] ?? '—' }} ·
          演练记录 {{ plan['演练记录数'] ?? 0 }} 条（已下发 {{ plan['已下发数'] ?? 0 }} /
          已完成 {{ plan['已完成数'] ?? 0 }}），问题 {{ plan['问题总数'] ?? 0 }} 项、
          已闭环 {{ plan['已闭环数'] ?? 0 }} 项，闭环率 {{ plan['整改闭环率'] ?? '—' }}
        </p>
      </div>
    </header>

    <div class="stat-row">
      <article class="stat-card">
        <span class="stat-label">整组整改进度</span>
        <strong class="stat-value">{{ plan['整组进度'] ?? '0/0' }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">待整改 / 整改中</span>
        <strong class="stat-value">{{ pendingIssueCount }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">已闭环</span>
        <strong class="stat-value">{{ Number(plan['已闭环数'] ?? 0) }}</strong>
      </article>
    </div>

    <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>
    <p v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</p>

    <!-- 演练记录：勾选后批量下发 / 结束演练 -->
    <section class="panel">
      <header class="panel-head">
        <h3>演练记录（批量下发给参演班组）</h3>
        <div class="page-actions">
          <button class="btn primary" type="button" :disabled="busy" @click="dispatchSelected">
            批量下发（{{ selectedIds.length }}）
          </button>
          <button class="btn" type="button" :disabled="busy" @click="finishSelected">
            演练结束（{{ selectedIds.length }}）
          </button>
        </div>
      </header>
      <table class="data-table">
        <thead>
          <tr>
            <th style="width: 36px">
              <input
                type="checkbox"
                :checked="allChecked"
                :indeterminate.prop="someChecked"
                @change="toggleAll"
              />
            </th>
            <th>演练编号</th>
            <th>演练科目</th>
            <th>参演班组</th>
            <th>参演人数</th>
            <th>参演人员</th>
            <th>人员确认</th>
            <th>下发时间</th>
            <th>完成时间</th>
            <th>演练状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in records" :key="String(row.id)">
            <td><input v-model="selectedIds" type="checkbox" :value="Number(row.id)" /></td>
            <td>{{ row['演练编号'] ?? '—' }}</td>
            <td>{{ row['演练科目'] ?? '—' }}</td>
            <td>{{ row['参演班组'] ?? '—' }}</td>
            <td>{{ row['参演人数'] ?? '—' }}</td>
            <td class="cell-people">{{ row['参演人员'] ?? '—' }}</td>
            <td>
              <span :class="row['人员已确认'] ? 'tag ok' : 'tag warn'">
                {{ row['人员已确认'] ? '已确认' : '未确认' }}
              </span>
            </td>
            <td>{{ row['下发时间'] || '—' }}</td>
            <td>{{ row['完成时间'] || '—' }}</td>
            <td>
              <span :class="recordTagClass(row)">{{ row.status }}</span>
            </td>
            <td class="row-actions">
              <button
                v-if="!row['人员已确认']"
                class="link"
                type="button"
                @click="confirmParticipants(Number(row.id))"
              >
                参演人确认
              </button>
              <span v-else class="muted-text">—</span>
            </td>
          </tr>
          <tr v-if="!records.length">
            <td colspan="11" class="empty-state">该计划下暂无演练记录</td>
          </tr>
        </tbody>
      </table>
      <p class="panel-tip">
        下发前会逐条校验：缺演练计划、重复下发、参演人未确认都会整体拦下并逐条说明，不会只发出第一条。
      </p>
    </section>

    <!-- 问题登记与整改闭环 -->
    <section class="panel">
      <header class="panel-head">
        <h3>问题登记与整改闭环</h3>
        <button class="btn primary" type="button" @click="openIssueForm">逐条登记问题</button>
      </header>
      <table class="data-table">
        <thead>
          <tr>
            <th>演练编号</th>
            <th>参演班组</th>
            <th>问题描述</th>
            <th>问题分类</th>
            <th>责任人</th>
            <th>整改要求</th>
            <th>整改措施</th>
            <th>闭环时间</th>
            <th>整改状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in issues" :key="String(row.id)">
            <td>{{ row['演练编号'] ?? '—' }}</td>
            <td>{{ row['参演班组'] ?? '—' }}</td>
            <td>{{ row['问题描述'] ?? '—' }}</td>
            <td>{{ row['问题分类'] ?? '—' }}</td>
            <td>{{ row['责任人'] ?? '—' }}</td>
            <td>{{ row['整改要求'] || '—' }}</td>
            <td>{{ row['整改措施'] || '—' }}</td>
            <td>{{ row['闭环时间'] || '—' }}</td>
            <td>
              <span :class="row.status === '已闭环' ? 'tag ok' : row.status === '整改中' ? 'tag doing' : 'tag warn'">
                {{ row.status }}
              </span>
            </td>
            <td class="row-actions">
              <button
                v-if="row.status === '待整改'"
                class="link"
                type="button"
                @click="startIssue(Number(row.id))"
              >
                开始整改
              </button>
              <button
                v-if="row.status !== '已闭环'"
                class="link"
                type="button"
                @click="openCloseForm(Number(row.id))"
              >
                闭环验收
              </button>
              <span v-else class="muted-text">已闭环</span>
            </td>
          </tr>
          <tr v-if="!issues.length">
            <td colspan="10" class="empty-state">演练结束后逐条登记问题，整改闭环后整组进度会同步更新</td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- 登记问题 -->
    <div v-if="issueFormVisible" class="modal-mask" @click.self="issueFormVisible = false">
      <div class="modal">
        <h3>登记演练问题</h3>
        <div class="form-item">
          <label>演练编号（仅演练已结束的记录可登记）</label>
          <select v-model="issueForm['演练编号']">
            <option value="">请选择演练记录</option>
            <option v-for="r in finishedRecords" :key="String(r.id)" :value="String(r['演练编号'])">
              {{ r['演练编号'] }} · {{ r['参演班组'] }}
            </option>
          </select>
        </div>
        <div class="form-item">
          <label>问题描述</label>
          <textarea v-model="issueForm['问题描述']" rows="2" placeholder="发现的具体问题"></textarea>
        </div>
        <div class="form-item">
          <label>问题分类（可空，默认一般问题）</label>
          <input v-model="issueForm['问题分类']" placeholder="如 物资、响应时效、流程" />
        </div>
        <div class="form-item">
          <label>责任人</label>
          <input v-model="issueForm['责任人']" placeholder="整改责任人" />
        </div>
        <div class="form-item">
          <label>整改要求（可空）</label>
          <textarea v-model="issueForm['整改要求']" rows="2" placeholder="对整改时限与效果的要求"></textarea>
        </div>
        <p v-if="issueFormError" class="error-text">{{ issueFormError }}</p>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="issueFormVisible = false">取消</button>
          <button class="btn primary" type="button" :disabled="busy" @click="submitIssue">保存问题</button>
        </div>
      </div>
    </div>

    <!-- 闭环验收：必须填整改措施 -->
    <div v-if="closeFormVisible" class="modal-mask" @click.self="closeFormVisible = false">
      <div class="modal">
        <h3>闭环验收（问题 #{{ closeIssueId }}）</h3>
        <div class="form-item">
          <label>整改措施与验收说明</label>
          <textarea v-model="closeMeasure" rows="3" placeholder="闭环必须填写整改措施，不允许空口闭环"></textarea>
        </div>
        <p v-if="closeFormError" class="error-text">{{ closeFormError }}</p>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="closeFormVisible = false">取消</button>
          <button class="btn primary" type="button" :disabled="busy" @click="submitClose">确认闭环</button>
        </div>
      </div>
    </div>

    <!-- 批量校验未通过：逐条列出全部原因，不只显示第一条 -->
    <div v-if="failuresVisible" class="modal-mask" @click.self="failuresVisible = false">
      <div class="modal modal-wide">
        <h3>{{ batchTitle }}未执行</h3>
        <p class="error-text">{{ batchMessage }}</p>
        <table class="data-table">
          <thead>
            <tr><th>演练编号</th><th>参演班组</th><th>未通过原因</th></tr>
          </thead>
          <tbody>
            <tr v-for="(item, index) in failures" :key="index">
              <td>{{ item['演练编号'] }}</td>
              <td>{{ item['参演班组'] ?? '—' }}</td>
              <td>{{ item['原因'] }}</td>
            </tr>
          </tbody>
        </table>
        <div class="modal-actions">
          <button class="btn primary" type="button" @click="failuresVisible = false">知道了，逐项处理</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>
type Failure = { '演练编号': string; '参演班组'?: string; '原因': string }

const ENDPOINT = '/api/drill'
const route = useRoute()
const router = useRouter()

const planId = String(route.params.planId ?? '')
const planNo = String(route.query.planNo ?? '')

const plan = ref<Row>({})
const records = ref<Row[]>([])
const issues = ref<Row[]>([])
const selectedIds = ref<number[]>([])
const errorMessage = ref('')
const noticeMessage = ref('')
const busy = ref(false)

const finishedRecords = computed(() => records.value.filter((row) => row.status === '已完成'))
const pendingIssueCount = computed(
  () => issues.value.filter((row) => row.status !== '已闭环').length,
)

const allChecked = computed(
  () => records.value.length > 0 && selectedIds.value.length === records.value.length,
)
const someChecked = computed(() => selectedIds.value.length > 0 && !allChecked.value)

function toggleAll(event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  selectedIds.value = checked ? records.value.map((row) => Number(row.id)) : []
}

function recordTagClass(row: Row) {
  if (row.status === '已完成') return 'tag ok'
  if (row.status === '已下发') return 'tag doing'
  return 'tag warn'
}

function goBack() {
  // 返回列表；列表页 onMounted 会重新拉取，整组进度不会停在旧值。
  void router.push({ name: 'drill' })
}

function flash(message: string, ok = true) {
  noticeMessage.value = message
  if (ok) window.setTimeout(() => (noticeMessage.value = ''), 3000)
}

async function loadAll() {
  errorMessage.value = ''
  try {
    const [planRes, recordRes, issueRes] = await Promise.all([
      request(`${ENDPOINT}/plans/${planId}`),
      request(`${ENDPOINT}/records?plan_no=${encodeURIComponent(planNo)}`),
      request(`${ENDPOINT}/issues?plan_no=${encodeURIComponent(planNo)}`),
    ])
    if (planRes.ok) plan.value = await planRes.json()
    if (recordRes.ok) records.value = (await recordRes.json()).items ?? []
    if (issueRes.ok) issues.value = (await issueRes.json()).items ?? []
    if (!planRes.ok) throw new Error(`演练计划 ${planId} 不存在或已归档，请返回列表重新进入`)
    // 已失效的勾选（记录状态变化后）剔掉，避免带着旧选择批量提交。
    const liveIds = records.value.map((row) => Number(row.id))
    selectedIds.value = selectedIds.value.filter((id) => liveIds.includes(id))
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '整改跟踪数据读取失败'
  }
}

async function confirmParticipants(recordId: number) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/records/${recordId}/confirm`, { method: 'POST' })
    const payload = await response.json()
    if (!response.ok || !payload.ok) throw new Error(payload.message || '参演人确认失败')
    flash(payload.message)
    await loadAll()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '参演人确认失败'
  }
}

// ---- 批量下发 / 结束演练 ------------------------------------------------
const failures = ref<Failure[]>([])
const failuresVisible = ref(false)
const batchTitle = ref('批量下发')
const batchMessage = ref('')

async function runBatch(path: string, title: string) {
  if (!selectedIds.value.length) {
    errorMessage.value = `未勾选任何演练记录，无法${title}`
    return
  }
  busy.value = true
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/records/${path}`, {
      method: 'POST',
      body: JSON.stringify({ record_ids: selectedIds.value }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      // 关键：把后端逐条给出的失败原因全部摊开，不只提示第一条。
      batchTitle.value = title
      batchMessage.value = payload.message
      failures.value = payload.failures ?? []
      failuresVisible.value = true
      return
    }
    flash(payload.message)
    await loadAll()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : `${title}请求失败`
  } finally {
    busy.value = false
  }
}

function dispatchSelected() {
  return runBatch('dispatch', '批量下发')
}

function finishSelected() {
  return runBatch('finish', '结束演练')
}

// ---- 登记问题 -----------------------------------------------------------
const issueFormVisible = ref(false)
const issueFormError = ref('')
const issueForm = reactive<Record<string, string>>({})

function openIssueForm() {
  for (const key of ['演练编号', '问题描述', '问题分类', '责任人', '整改要求']) issueForm[key] = ''
  issueFormError.value = ''
  if (!finishedRecords.value.length) {
    issueFormError.value = '还没有「已完成」的演练记录，需先勾选记录执行「演练结束」后才能登记问题'
  }
  issueFormVisible.value = true
}

async function submitIssue() {
  busy.value = true
  issueFormError.value = ''
  try {
    const response = await request(`${ENDPOINT}/issues`, {
      method: 'POST',
      body: JSON.stringify({ values: { ...issueForm } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) throw new Error(payload.message || '问题登记失败')
    issueFormVisible.value = false
    flash(payload.message)
    // 登记后立刻重拉计划与问题，整组进度马上与实际条目一致。
    await loadAll()
  } catch (error) {
    issueFormError.value = error instanceof Error ? error.message : '问题登记失败'
  } finally {
    busy.value = false
  }
}

// ---- 整改动作 -----------------------------------------------------------
async function startIssue(issueId: number) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/issues/${issueId}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action: '开始整改' }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) throw new Error(payload.message || '开始整改失败')
    flash(payload.message)
    await loadAll()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '开始整改失败'
  }
}

const closeFormVisible = ref(false)
const closeFormError = ref('')
const closeIssueId = ref(0)
const closeMeasure = ref('')

function openCloseForm(issueId: number) {
  closeIssueId.value = issueId
  closeMeasure.value = ''
  closeFormError.value = ''
  closeFormVisible.value = true
}

async function submitClose() {
  busy.value = true
  closeFormError.value = ''
  try {
    const response = await request(`${ENDPOINT}/issues/${closeIssueId.value}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action: '闭环验收', 整改措施: closeMeasure.value }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) throw new Error(payload.message || '闭环验收失败')
    closeFormVisible.value = false
    flash(payload.message)
    // 闭环后重拉：本页整组进度更新，返回列表时 onMounted 再取一次，仍是实际值。
    await loadAll()
  } catch (error) {
    closeFormError.value = error instanceof Error ? error.message : '闭环验收失败'
  } finally {
    busy.value = false
  }
}

// 每次进入（含从列表进入、浏览器刷新）都重新拉取，进度不使用任何本地初值。
onMounted(loadAll)
</script>

<style scoped>
.panel { background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 12px; margin-bottom: 16px; }
.panel-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.panel-head h3 { margin: 0; font-size: 15px; }
.panel-tip { color: var(--muted); font-size: 12px; margin: 8px 0 0; }
.cell-people { max-width: 220px; }
.notice-text { color: #067647; background: #ecfdf3; border: 1px solid #abefc6; padding: 6px 10px; border-radius: 6px; font-size: 13px; }
.muted-text { color: var(--muted); }
.tag { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 12px; }
.tag.ok { background: #ecfdf3; color: #067647; }
.tag.doing { background: #eff8ff; color: #175cd3; }
.tag.warn { background: #fffaeb; color: #b54708; }
.modal-mask { position: fixed; inset: 0; background: rgba(15, 23, 42, 0.45); display: flex; align-items: center; justify-content: center; z-index: 20; }
.modal { width: 480px; max-height: 86vh; overflow: auto; background: #fff; border-radius: 10px; padding: 18px 20px; }
.modal-wide { width: 720px; }
.modal h3 { margin: 0 0 12px; }
.form-item { margin-bottom: 10px; }
.form-item label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
.form-item input, .form-item select, .form-item textarea {
  width: 100%; padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; font-family: inherit;
}
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; }
</style>
