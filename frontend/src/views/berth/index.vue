<template>
  <section class="page" data-module="berth">
    <header class="page-head">
      <div>
        <h2>泊位计划管理</h2>
        <p class="page-desc">维护泊位计划，围绕计划编号、泊位编号、靠泊船舶、计划靠泊时间做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记泊位计划</button>
        <button class="btn" type="button" @click="exportRows">导出泊位计划清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="submitSearch">
      <label class="filter-item">
        <span>泊位编号</span>
        <input v-model="form.berth_no" placeholder="如 A-01，支持模糊匹配" />
      </label>
      <label class="filter-item">
        <span>靠泊船舶</span>
        <input v-model="form.vessel" placeholder="如 中远海运，支持模糊匹配" />
      </label>
      <label class="filter-item">
        <span>计划状态</span>
        <select v-model="form.status">
          <option value="">全部状态</option>
          <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <button class="btn primary" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <div v-if="hasActiveFilter" class="filter-summary">
      当前条件：
      <template v-if="query.berth_no">泊位编号含“{{ query.berth_no }}”</template>
      <template v-if="query.vessel">靠泊船舶含“{{ query.vessel }}”</template>
      <template v-if="query.status">计划状态为“{{ query.status }}”</template>
      <span v-if="!loading">，命中 {{ total }} 条</span>
      <button class="link" type="button" @click="resetFilters">清空条件</button>
    </div>

    <p v-if="errorMessage" class="inline-error" role="alert">{{ errorMessage }}</p>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">
            <button class="sort-header" type="button" @click="toggleSort(column)">
              {{ column }}
              <span class="sort-arrow">{{ sortArrow(column) }}</span>
            </button>
          </th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)" :ref="setRowRef(row.id)" :class="{ 'row-locate': row.id === locateId }">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!loading && !errorMessage && !rows.length">
          <td :colspan="columns.length + 1" class="empty-state">
            <template v-if="hasActiveFilter">
              没有符合条件的泊位计划：
              <span v-if="query.berth_no">泊位编号含“{{ query.berth_no }}”</span>
              <span v-if="query.vessel">靠泊船舶含“{{ query.vessel }}”</span>
              <span v-if="query.status">计划状态为“{{ query.status }}”</span>
              ，请放宽关键字或更换状态后重试。
              <button class="link" type="button" @click="resetFilters">清空条件查看全部计划</button>
            </template>
            <template v-else>暂无泊位计划数据，可先登记泊位计划</template>
          </td>
        </tr>
        <tr v-if="loading">
          <td :colspan="columns.length + 1" class="empty-state">正在读取泊位计划…</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条泊位计划记录，第 {{ page }} / {{ pages }} 页</span>
      <div class="pagination">
        <button class="btn" type="button" :disabled="page <= 1 || loading" @click="goPage(1)">首页</button>
        <button class="btn" type="button" :disabled="page <= 1 || loading" @click="goPage(page - 1)">上一页</button>
        <button
          v-for="item in pageNumbers"
          :key="item"
          class="btn"
          type="button"
          :class="{ primary: item === page }"
          :disabled="item === page || loading"
          @click="goPage(item)"
        >
          {{ item }}
        </button>
        <button class="btn" type="button" :disabled="page >= pages || loading" @click="goPage(page + 1)">下一页</button>
        <label class="page-size">
          每页
          <select :value="size" :disabled="loading" @change="changeSize(($event.target as HTMLSelectElement).value)">
            <option v-for="item in sizeOptions" :key="item" :value="item">{{ item }}</option>
          </select>
          条
        </label>
      </div>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch, type ComponentPublicInstance } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
interface ListPayload {
  items: Row[]
  total: number
  page: number
  size: number
  pages: number
  locate_id: number | null
}
interface QueryState {
  berth_no: string
  vessel: string
  status: string
  sort_field: string
  sort_order: string
  page: number
  size: number
}

const ENDPOINT = '/api/berth'
const columns = ["计划编号", "泊位编号", "靠泊船舶", "计划靠泊时间", "计划离泊时间", "船长", "吃水深度", "计划状态"]
const actions = ["确认编排", "确认靠泊", "确认离泊"]
const statuses = ["待编排", "已编排", "已靠泊", "已离泊"]
const stats = [{"label": "今日靠泊计划", "value": 0}, {"label": "待编排计划", "value": 0}, {"label": "在泊船舶数", "value": 0}]
const sizeOptions = [10, 20, 50]

const route = useRoute()
const router = useRouter()

const rows = ref<Row[]>([])
const total = ref(0)
const page = ref(1)
const pages = ref(1)
const size = ref(10)
const locateId = ref<number | null>(null)
const loading = ref(false)
const errorMessage = ref('')

// 检索框里的草稿；以路由 query 为单一事实来源，刷新/前进后退/离开再回来都能还原
const form = reactive({ berth_no: '', vessel: '', status: '' })
const query = ref<QueryState>({
  berth_no: '',
  vessel: '',
  status: '',
  sort_field: '计划靠泊时间',
  sort_order: 'asc',
  page: 1,
  size: 10,
})

const hasActiveFilter = computed(() => Boolean(query.value.berth_no || query.value.vessel || query.value.status))
const pageNumbers = computed(() => {
  const start = Math.max(1, Math.min(page.value - 2, pages.value - 4))
  const end = Math.min(pages.value, start + 4)
  const list: number[] = []
  for (let item = start; item <= end; item += 1) {
    list.push(item)
  }
  return list
})

let loadedSignature = ''
let pendingLocate: number | null = null
const rowRefs = new Map<number, HTMLTableRowElement>()

function setRowRef(id: unknown) {
  return (el: Element | ComponentPublicInstance | null) => {
    const rowId = Number(id)
    if (el instanceof HTMLTableRowElement) {
      rowRefs.set(rowId, el)
    } else {
      rowRefs.delete(rowId)
    }
  }
}

function readRoute(): QueryState {
  const parsedSize = Number(route.query.size)
  const parsedPage = Number(route.query.page)
  return {
    berth_no: String(route.query.berth_no ?? '').trim(),
    vessel: String(route.query.vessel ?? '').trim(),
    status: String(route.query.status ?? ''),
    sort_field: String(route.query.sort_field ?? '计划靠泊时间'),
    sort_order: route.query.sort_order === 'desc' ? 'desc' : 'asc',
    page: Number.isFinite(parsedPage) && parsedPage >= 1 ? Math.floor(parsedPage) : 1,
    size: sizeOptions.includes(parsedSize) ? parsedSize : 10,
  }
}

function syncQuery(state: QueryState, options: { replace?: boolean } = {}) {
  const params = new URLSearchParams()
  if (state.berth_no) params.set('berth_no', state.berth_no)
  if (state.vessel) params.set('vessel', state.vessel)
  if (state.status) params.set('status', state.status)
  if (state.sort_field !== '计划靠泊时间') params.set('sort_field', state.sort_field)
  if (state.sort_order !== 'asc') params.set('sort_order', state.sort_order)
  if (state.page !== 1) params.set('page', String(state.page))
  if (state.size !== 10) params.set('size', String(state.size))
  const search = params.toString()
  const target = `${route.path}${search ? `?${search}` : ''}`
  if (target === route.fullPath) {
    void reload()
    return
  }
  void router[options.replace ? 'replace' : 'push'](target)
}

function sortArrow(column: string): string {
  if (query.value.sort_field !== column) return ''
  return query.value.sort_order === 'asc' ? '▲' : '▼'
}

function toggleSort(column: string) {
  const state = { ...query.value }
  if (state.sort_field === column) {
    state.sort_order = state.sort_order === 'asc' ? 'desc' : 'asc'
  } else {
    state.sort_field = column
    state.sort_order = 'asc'
  }
  state.page = 1
  syncQuery(state)
}

function submitSearch() {
  syncQuery({
    ...query.value,
    berth_no: form.berth_no.trim(),
    vessel: form.vessel.trim(),
    status: form.status,
    page: 1,
  })
}

function resetFilters() {
  form.berth_no = ''
  form.vessel = ''
  form.status = ''
  syncQuery({ ...query.value, berth_no: '', vessel: '', status: '', page: 1 })
}

function goPage(target: number) {
  if (target < 1 || target > pages.value || target === page.value) return
  syncQuery({ ...query.value, page: target })
}

function changeSize(value: string) {
  syncQuery({ ...query.value, size: Number(value), page: 1 })
}

function exportRows() {
  const params = new URLSearchParams()
  if (query.value.berth_no) params.set('berth_no', query.value.berth_no)
  if (query.value.vessel) params.set('vessel', query.value.vessel)
  if (query.value.status) params.set('status', query.value.status)
  params.set('sort_field', query.value.sort_field)
  params.set('sort_order', query.value.sort_order)
  window.open(`${ENDPOINT}/export?${params.toString()}`, '_blank')
}

function openCreate() {
  errorMessage.value = '泊位计划登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok) {
      throw new Error(payload?.detail ?? '泊位计划动作未生效，请稍后重试')
    }
    if (payload?.ok === false) {
      throw new Error(payload?.message ?? '泊位计划动作未生效，请稍后重试')
    }
    // 动作完成后仍在当前条件与排序下，并定位到刚操作的那条
    pendingLocate = Number(row.id)
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '泊位计划操作失败'
  }
}

async function reload() {
  const state = readRoute()
  loadedSignature = route.fullPath
  query.value = state
  form.berth_no = state.berth_no
  form.vessel = state.vessel
  form.status = state.status

  loading.value = true
  errorMessage.value = ''
  const params = new URLSearchParams()
  if (state.berth_no) params.set('berth_no', state.berth_no)
  if (state.vessel) params.set('vessel', state.vessel)
  if (state.status) params.set('status', state.status)
  params.set('sort_field', state.sort_field)
  params.set('sort_order', state.sort_order)
  params.set('page', String(state.page))
  params.set('size', String(state.size))
  if (pendingLocate != null) params.set('locate_id', String(pendingLocate))

  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    const payload = await response.json().catch(() => null)
    if (!response.ok) {
      throw new Error(payload?.detail ?? '泊位计划列表读取失败')
    }
    const data = payload as ListPayload
    rows.value = data.items ?? []
    total.value = data.total ?? 0
    page.value = data.page ?? state.page
    pages.value = data.pages ?? 1
    size.value = data.size ?? state.size
    locateId.value = data.locate_id ?? pendingLocate
    pendingLocate = null

    // 服务端可能因定位而调整了页码，把真实页码写回地址栏，刷新后仍停在同页
    if (page.value !== state.page || size.value !== state.size) {
      syncQuery({ ...state, page: page.value, size: size.value }, { replace: true })
    }
    if (locateId.value != null) {
      await nextTick()
      rowRefs.get(locateId.value)?.scrollIntoView({ block: 'center', behavior: 'smooth' })
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '泊位计划列表读取失败'
    locateId.value = null
    pendingLocate = null
  } finally {
    loading.value = false
  }
}

watch(
  () => route.fullPath,
  () => {
    if (route.fullPath === loadedSignature) return
    void reload()
  },
)

onMounted(reload)
</script>
