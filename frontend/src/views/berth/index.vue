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

    <form class="filter-bar" @submit.prevent="applyFilters">
      <label class="filter-item">
        <span>计划编号</span>
        <input v-model="filters.keyword" placeholder="按计划编号检索" />
      </label>
      <label class="filter-item">
        <span>泊位编号</span>
        <input v-model="filters.berth" placeholder="按泊位编号检索" />
      </label>
      <label class="filter-item">
        <span>靠泊船舶</span>
        <input v-model="filters.vessel" placeholder="按靠泊船舶检索" />
      </label>
      <label class="filter-item">
        <span>计划状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th
            v-for="column in columns"
            :key="column"
            :class="{ sortable: isSortable(column) }"
            @click="toggleSort(column)"
          >
            {{ column }}
            <span v-if="sortMark(column)" class="sort-mark">{{ sortMark(column) }}</span>
          </th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody ref="tableBody">
        <tr
          v-for="row in rows"
          :key="String(row.id)"
          :data-row-id="row.id"
          :class="{ 'row-focus': focusId === Number(row.id) }"
        >
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
        <tr v-if="!rows.length && !errorMessage">
          <td :colspan="columns.length + 1" class="empty-state">{{ emptyMessage }}</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>
        共 {{ total }} 条泊位计划记录，第 {{ page }} / {{ pageCount }} 页
        <button
          v-if="focusId !== null && !focusOnPage"
          class="link"
          type="button"
          @click="locateFocused"
        >
          定位到命中记录
        </button>
      </span>
      <div v-if="pageCount > 1" class="pager">
        <button class="btn ghost" type="button" :disabled="page <= 1" @click="goPage(page - 1)">上一页</button>
        <button
          v-for="p in pageCount"
          :key="p"
          class="btn ghost pager-page"
          :class="{ active: p === page }"
          type="button"
          @click="goPage(p)"
        >
          {{ p }}
        </button>
        <button class="btn ghost" type="button" :disabled="page >= pageCount" @click="goPage(page + 1)">下一页</button>
      </div>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { LocationQuery } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

interface ListState {
  keyword: string
  berth: string
  vessel: string
  status: string
  sort: string
  order: 'asc' | 'desc'
  page: number
  focus: number | null
}

const ENDPOINT = '/api/berth'
const PAGE_SIZE = 10
const STORAGE_KEY = 'berth:list-state'
const columns = ["计划编号", "泊位编号", "靠泊船舶", "计划靠泊时间", "计划离泊时间", "船长", "吃水深度", "计划状态"]
const SORTABLE_COLUMNS = ["计划编号", "泊位编号", "靠泊船舶", "计划靠泊时间", "计划离泊时间"]
const QUERY_KEYS = ['keyword', 'berth', 'vessel', 'status', 'sort', 'order', 'page', 'focus']
const actions = ["确认编排", "确认靠泊", "确认离泊"]
const statuses = ["待编排", "已编排", "已靠泊", "已离泊"]
const stats = [{"label": "今日靠泊计划", "value": 0}, {"label": "待编排计划", "value": 0}, {"label": "在泊船舶数", "value": 0}]

const route = useRoute()
const router = useRouter()

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref({ keyword: '', berth: '', vessel: '', status: '' })
const sortField = ref('')
const sortOrder = ref<'asc' | 'desc'>('asc')
const page = ref(1)
const focusId = ref<number | null>(null)
const tableBody = ref<HTMLElement | null>(null)

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))
const focusOnPage = computed(() => rows.value.some((row) => Number(row.id) === focusId.value))

const conditionText = computed(() => {
  const parts: string[] = []
  if (filters.value.keyword.trim()) parts.push(`计划编号含「${filters.value.keyword.trim()}」`)
  if (filters.value.berth.trim()) parts.push(`泊位编号含「${filters.value.berth.trim()}」`)
  if (filters.value.vessel.trim()) parts.push(`靠泊船舶含「${filters.value.vessel.trim()}」`)
  if (filters.value.status) parts.push(`计划状态为「${filters.value.status}」`)
  return parts.join('、')
})
const hasConditions = computed(() => conditionText.value.length > 0)
const emptyMessage = computed(() => (hasConditions.value
  ? `未找到符合「${conditionText.value}」的泊位计划，可调整条件或点击「重置条件」后重试`
  : '暂无泊位计划数据，可先登记泊位计划'))

function isSortable(column: string): boolean {
  return SORTABLE_COLUMNS.includes(column)
}

function sortMark(column: string): string {
  if (sortField.value !== column) return ''
  return sortOrder.value === 'asc' ? '▲' : '▼'
}

// ---- 状态 <-> 地址栏 / 会话缓存：翻页、返回、刷新都靠这份状态还原 ----

function currentState(): ListState {
  return {
    keyword: filters.value.keyword.trim(),
    berth: filters.value.berth.trim(),
    vessel: filters.value.vessel.trim(),
    status: filters.value.status,
    sort: sortField.value,
    order: sortOrder.value,
    page: page.value,
    focus: focusId.value,
  }
}

function stateToQuery(state: ListState): Record<string, string> {
  const query: Record<string, string> = {}
  if (state.keyword) query.keyword = state.keyword
  if (state.berth) query.berth = state.berth
  if (state.vessel) query.vessel = state.vessel
  if (state.status) query.status = state.status
  if (state.sort) {
    query.sort = state.sort
    query.order = state.order
  }
  if (state.page > 1) query.page = String(state.page)
  if (state.focus !== null) query.focus = String(state.focus)
  return query
}

function queryText(value: unknown): string {
  if (typeof value === 'string') return value
  if (Array.isArray(value)) return String(value[0] ?? '')
  return ''
}

function parseQuery(query: LocationQuery): ListState | null {
  if (!QUERY_KEYS.some((key) => key in query)) return null
  const pageNum = Number.parseInt(queryText(query.page), 10)
  const focusNum = Number.parseInt(queryText(query.focus), 10)
  return {
    keyword: queryText(query.keyword),
    berth: queryText(query.berth),
    vessel: queryText(query.vessel),
    status: queryText(query.status),
    sort: queryText(query.sort),
    order: queryText(query.order) === 'desc' ? 'desc' : 'asc',
    page: Number.isFinite(pageNum) && pageNum > 0 ? pageNum : 1,
    focus: Number.isFinite(focusNum) ? focusNum : null,
  }
}

function applyState(state: ListState) {
  filters.value = {
    keyword: state.keyword,
    berth: state.berth,
    vessel: state.vessel,
    status: state.status,
  }
  sortField.value = state.sort
  sortOrder.value = state.order
  page.value = state.page
  focusId.value = state.focus
}

function saveCache() {
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(currentState()))
  } catch {
    // 私密模式等场景下写不进去就静默跳过，地址栏里仍有状态
  }
}

function readCache(): ListState | null {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const cached = JSON.parse(raw) as Partial<ListState>
    const pageNum = Number(cached.page)
    const focusNum = Number(cached.focus)
    return {
      keyword: String(cached.keyword ?? ''),
      berth: String(cached.berth ?? ''),
      vessel: String(cached.vessel ?? ''),
      status: String(cached.status ?? ''),
      sort: String(cached.sort ?? ''),
      order: cached.order === 'desc' ? 'desc' : 'asc',
      page: Number.isFinite(pageNum) && pageNum > 0 ? Math.floor(pageNum) : 1,
      focus: cached.focus !== null && cached.focus !== undefined && Number.isFinite(focusNum) ? focusNum : null,
    }
  } catch {
    return null
  }
}

function syncUrl() {
  saveCache()
  void router.replace({ query: stateToQuery(currentState()) })
}

// 浏览器前进/后退时地址栏先变，这里把状态拉齐再重新取数；
// 自己 syncUrl 触发的变化与当前状态一致，直接跳过
watch(
  () => route.query,
  (query) => {
    const incoming = parseQuery(query)
    if (!incoming) return
    if (JSON.stringify(stateToQuery(incoming)) === JSON.stringify(stateToQuery(currentState()))) return
    applyState(incoming)
    saveCache()
    void reload()
  },
)

// ---- 列表读取与定位 ----

function buildParams(): URLSearchParams {
  const state = currentState()
  const params = new URLSearchParams()
  if (state.keyword) params.set('keyword', state.keyword)
  if (state.berth) params.set('berth', state.berth)
  if (state.vessel) params.set('vessel', state.vessel)
  if (state.status) params.set('status', state.status)
  if (state.sort) {
    params.set('sort', state.sort)
    params.set('order', state.order)
  }
  return params
}

async function readDetail(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json()
    if (body && typeof body.detail === 'string') return body.detail
  } catch {
    // 返回体不是 JSON 时走兜底文案
  }
  return `${fallback}（接口返回 ${response.status}）`
}

async function reload() {
  errorMessage.value = ''
  const params = buildParams()
  params.set('page', String(page.value))
  params.set('size', String(PAGE_SIZE))
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) {
      throw new Error(await readDetail(response, '泊位计划列表读取失败'))
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? 0
    // 条件或数据变化后当前页可能超出范围，收回到最后一页再取一次
    if (page.value > pageCount.value) {
      page.value = pageCount.value
      syncUrl()
      await reload()
      return
    }
    // 有检索条件且还没定位过时，自动定位到第一条命中记录
    if (focusId.value === null && hasConditions.value && rows.value.length > 0) {
      focusId.value = Number(rows.value[0].id)
      syncUrl()
    }
    await scrollToFocus()
  } catch (error) {
    rows.value = []
    total.value = 0
    errorMessage.value = error instanceof Error ? error.message : '泊位计划列表读取失败'
  }
}

async function scrollToFocus() {
  if (focusId.value === null) return
  await nextTick()
  const target = tableBody.value?.querySelector(`tr[data-row-id="${focusId.value}"]`)
  target?.scrollIntoView({ block: 'center' })
}

async function locateFocused() {
  if (focusId.value === null) return
  errorMessage.value = ''
  const params = buildParams()
  params.set('size', String(PAGE_SIZE))
  try {
    const response = await request(`${ENDPOINT}/locate?id=${focusId.value}&${params.toString()}`)
    if (!response.ok) {
      throw new Error(await readDetail(response, '定位失败，请稍后重试'))
    }
    const payload = await response.json()
    page.value = Math.max(1, Number(payload.page) || 1)
    syncUrl()
    await reload()
  } catch (error) {
    // 定位不到（记录已归档或不满足当前条件）时清掉定位，把原因摆出来
    focusId.value = null
    syncUrl()
    errorMessage.value = error instanceof Error ? error.message : '定位失败，请稍后重试'
  }
}

// ---- 用户操作 ----

function applyFilters() {
  page.value = 1
  focusId.value = null
  syncUrl()
  void reload()
}

function resetFilters() {
  filters.value = { keyword: '', berth: '', vessel: '', status: '' }
  page.value = 1
  focusId.value = null
  syncUrl()
  void reload()
}

function toggleSort(column: string) {
  if (!isSortable(column)) return
  if (sortField.value === column) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortField.value = column
    sortOrder.value = 'asc'
  }
  page.value = 1
  focusId.value = null
  syncUrl()
  void reload()
}

function goPage(target: number) {
  if (target < 1 || target > pageCount.value || target === page.value) return
  page.value = target
  syncUrl()
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
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
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message ?? '泊位计划动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '泊位计划操作失败'
  }
}

onMounted(() => {
  // 地址栏里的状态优先（刷新、分享链接）；否则取会话缓存（切走再回来）
  const fromUrl = parseQuery(route.query)
  if (fromUrl) {
    applyState(fromUrl)
    saveCache()
  } else {
    const cached = readCache()
    if (cached) {
      applyState(cached)
      syncUrl()
    }
  }
  void reload()
})
</script>
