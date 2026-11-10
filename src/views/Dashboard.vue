<template>
  <div class="page">
    <header class="page-header">
      <div>
        <div class="eyebrow">今日概览</div>
        <h1 class="page-title">本喵的辉煌战绩</h1>
        <p class="page-subtitle">你每天陪优墨聊了多少，本喵都替你记着呢</p>
      </div>
      <div class="header-actions">
        <span class="update-time" v-if="lastUpdated">
          <AppIcon name="clock" :size="12" />
          更新于 {{ lastUpdated }}
        </span>
        <button class="btn-refresh" :disabled="loading" @click="manualRefresh">
          <AppIcon name="refresh" :size="14" :class="{ spinning: loading }" />
          {{ loading ? '加载中' : '刷新' }}
        </button>
      </div>
    </header>

    <!-- 错误空态（Python 服务未运行 / 仍在冷启动等） -->
    <section v-if="error" class="card error-card">
      <div class="error-icon"><AppIcon name="alert" :size="22" /></div>
      <div class="error-title">账本一时翻不开</div>
      <div class="error-text">{{ error }}</div>
      <p v-if="retrying" class="error-hint">
        <span class="ui-spinner"></span>
        本喵正在自动重试（第 {{ retryCount }} / {{ RETRY_MAX }} 次）
      </p>
      <button class="btn-retry" @click="manualRefresh">立即重试</button>
    </section>

    <template v-else>
      <!-- KPI 指标卡片 -->
      <div class="kpi-grid">
        <section
          v-for="k in kpiCards"
          :key="k.label"
          class="card kpi-card"
          :class="`kpi--${k.accent}`"
        >
          <div class="kpi-top">
            <span class="kpi-icon"><AppIcon :name="k.icon" :size="15" /></span>
            <span class="kpi-label">{{ k.label }}</span>
          </div>
          <div class="kpi-value tabular">{{ k.value }}</div>
          <div class="kpi-sub" v-html="k.sub"></div>
        </section>
      </div>

      <!-- 知识库家底：三项指标合并成一条横向摘要，避免 KPI 网格出现孤行 -->
      <section class="card kb-summary">
        <div class="kb-summary-head">
          <span class="kb-summary-icon"><AppIcon name="book" :size="15" /></span>
          <div>
            <div class="kb-summary-title">藏书阁家底</div>
            <div class="kb-summary-sub">知识库、文档、分片都堆在这了</div>
          </div>
        </div>
        <div class="kb-stats">
          <div v-for="s in kbStats" :key="s.label" class="kb-stat">
            <span class="kb-stat-value tabular">{{ s.value }}</span>
            <span class="kb-stat-label">{{ s.label }}</span>
          </div>
        </div>
      </section>

      <!-- 近 7 天趋势 -->
      <section class="card chart-card">
        <div class="card-header">
          <div class="card-head-main">
            <span class="card-title">近 7 天你找本喵的次数</span>
            <span class="card-sub">柱形 = 对话次数 · 折线 = Token 用量</span>
          </div>
        </div>
        <div ref="trendRef" class="chart-box" style="height: 292px"></div>
      </section>

      <!-- 用量与成本：按模型 / 会话 -->
      <section class="card usage-card">
        <div class="card-header">
          <div class="card-head-main">
            <span class="card-title">用量与成本</span>
            <span class="card-sub">按模型与会话统计 Token、平均耗时和失败率；模型与耗时从本版本开始记录</span>
          </div>
          <span v-if="usageLoading" class="usage-loading"><span class="ui-spinner"></span></span>
        </div>

        <div v-if="usage?.summary" class="usage-summary">
          <div v-for="s in usageSummary" :key="s.label" class="usage-summary-item">
            <span class="usage-summary-value tabular">{{ s.value }}</span>
            <span class="usage-summary-label">{{ s.label }}</span>
          </div>
        </div>

        <div class="usage-grid">
          <div class="usage-block">
            <div class="usage-block-head">
              <span>按模型</span>
              <span class="usage-block-sub">仅统计有 Token 记录的轮次</span>
            </div>
            <div class="usage-table-wrap">
              <table class="usage-table">
                <thead>
                  <tr>
                    <th>模型</th>
                    <th class="num">轮次</th>
                    <th class="num">输入 / 输出</th>
                    <th class="num">平均耗时</th>
                    <th class="num">失败率</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in usage?.models || []" :key="row.model">
                    <td class="usage-name" :title="row.model">{{ row.model }}</td>
                    <td class="num tabular">{{ fmtInt(row.turns) }}</td>
                    <td class="num tabular">{{ fmtInt(row.inputTokens) }} / {{ fmtInt(row.outputTokens) }}</td>
                    <td class="num tabular">{{ fmtDuration(row.avgDurationMs) }}</td>
                    <td class="num tabular" :class="{ 'usage-bad': row.failureRate > 0 }">{{ fmtRate(row.failureRate) }}</td>
                  </tr>
                  <tr v-if="!usage?.models?.length">
                    <td colspan="5" class="usage-empty">还没有模型用量记录</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div class="usage-block">
            <div class="usage-block-head">
              <span>按会话（Token 前 8）</span>
              <span class="usage-block-sub">点击会话可继续对话</span>
            </div>
            <div class="usage-table-wrap">
              <table class="usage-table">
                <thead>
                  <tr>
                    <th>会话</th>
                    <th class="num">轮次</th>
                    <th class="num">Token</th>
                    <th class="num">平均耗时</th>
                    <th class="num">失败率</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in usage?.sessions || []" :key="row.sessionId">
                    <td class="usage-name">
                      <button class="usage-session" type="button" :title="row.title" @click="openSession(row.sessionId)">
                        {{ row.title }}
                      </button>
                    </td>
                    <td class="num tabular">{{ fmtInt(row.turns) }}</td>
                    <td class="num tabular">{{ fmtInt(row.totalTokens) }}</td>
                    <td class="num tabular">{{ fmtDuration(row.avgDurationMs) }}</td>
                    <td class="num tabular" :class="{ 'usage-bad': row.failureRate > 0 }">{{ fmtRate(row.failureRate) }}</td>
                  </tr>
                  <tr v-if="!usage?.sessions?.length">
                    <td colspan="5" class="usage-empty">还没有会话用量记录</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </section>

      <div class="chart-row">
        <!-- Token 构成环图 -->
        <section class="card chart-card">
          <div class="card-header">
            <div class="card-head-main">
              <span class="card-title">本喵烧掉的脑细胞</span>
              <span class="card-sub">输入 = 你说的话 · 输出 = 本喵的回话</span>
            </div>
          </div>
          <div class="donut-wrap">
            <div ref="tokenTodayRef" class="chart-box donut-box"></div>
            <div ref="tokenTotalRef" class="chart-box donut-box"></div>
          </div>
        </section>

        <!-- 知识库分布 -->
        <section class="card chart-card">
          <div class="card-header">
            <div class="card-head-main">
              <span class="card-title">本喵的藏书阁分布</span>
              <span class="card-sub">按库统计文档数与分片数</span>
            </div>
          </div>
          <div ref="kbRef" class="chart-box" style="height: 292px"></div>
        </section>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue'
import { useRouter } from 'vue-router'
import { fetchDashboardStats, fetchUsageStats } from '../api/stats'
import { useAgentSocket } from '../composables/useAgentSocket'
import { switchConversation } from '../composables/useChatStore'
import AppIcon from '../components/AppIcon.vue'

// ---------- ECharts 按需引入（控制打包体积） ----------
import * as echarts from 'echarts/core'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, TitleComponent, GraphicComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  BarChart, LineChart, PieChart,
  GridComponent, TooltipComponent, LegendComponent, TitleComponent, GraphicComponent,
  CanvasRenderer,
])

// ---------- 主题色：与 tokens.css 的「墨夜 · 琥珀」保持一致 ----------
const COLOR = {
  text: '#7B8392',
  textStrong: '#EBE9E4',
  axis: 'rgba(255,255,255,0.10)',
  split: 'rgba(255,255,255,0.055)',
  tooltipBg: 'rgba(14,17,24,0.96)',
  tooltipBorder: 'rgba(255,255,255,0.12)',
  amber: '#EFA84C',
  amberDeep: '#B4691C',
  azure: '#8FB6E8',
  jade: '#7ECBA1',
  coral: '#E9776E',
  lilac: '#C0A6E8',
  track: 'rgba(255,255,255,0.055)',
}

// ---------- 数据状态 ----------
const stats = ref(null)
const usage = ref(null)
const usageLoading = ref(false)
const loading = ref(false)
const error = ref('')
const lastUpdated = ref('')

const baseEmpty = {
  chat: { today: 0, total: 0 },
  token: {
    today: { inputTokens: 0, outputTokens: 0, totalTokens: 0 },
    total: { inputTokens: 0, outputTokens: 0, totalTokens: 0 },
  },
  kb: { kbCount: 0, docCount: 0, chunkCount: 0, perKb: [] },
  trend: [],
}

// ---------- 数字格式化 ----------
const fmtInt = (n) => (n ?? 0).toLocaleString('zh-CN')
const fmtDuration = (ms) => {
  if (ms == null) return '—'
  if (ms < 1000) return `${Math.round(ms)}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60000)}m${Math.round((ms % 60000) / 1000)}s`
}
const fmtRate = (rate) => (rate == null ? '—' : `${(Number(rate) * 100).toFixed(1)}%`)

const router = useRouter()
const usageSummary = computed(() => {
  const s = usage.value?.summary
  if (!s) return []
  return [
    { label: '总轮次', value: fmtInt(s.turns) },
    { label: '总 Token', value: fmtInt(s.totalTokens) },
    { label: '平均耗时', value: fmtDuration(s.avgDurationMs) },
    { label: '失败率', value: fmtRate(s.failureRate) },
  ]
})

function openSession(id) {
  if (!id) return
  switchConversation(id)
  router.push('/chat')
}
const fmtCompact = (n) => {
  n = n ?? 0
  if (n >= 100000000) return (n / 100000000).toFixed(2) + ' 亿'
  if (n >= 10000) return (n / 10000).toFixed(n >= 1000000 ? 1 : 2) + ' 万'
  return String(n)
}

// ---------- KPI 卡片 ----------
const kpiCards = computed(() => {
  const d = stats.value || baseEmpty
  const tTok = d.token.today
  const hTok = d.token.total
  return [
    {
      label: '今日对话次数', icon: 'chat', accent: 'amber',
      value: fmtInt(d.chat.today), sub: todayChatQuip.value,
    },
    {
      label: '今日 Token 用量', icon: 'zap', accent: 'amber',
      value: fmtCompact(tTok.totalTokens),
      sub: `输入 ${fmtCompact(tTok.inputTokens)} · 输出 ${fmtCompact(tTok.outputTokens)}`,
    },
    {
      label: '历史对话次数', icon: 'list', accent: 'azure',
      value: fmtInt(d.chat.total), sub: `日均 ${avgChats.value} 次，本喵都记着呢`,
    },
    {
      label: '历史 Token 用量', icon: 'bar-chart', accent: 'azure',
      value: fmtCompact(hTok.totalTokens),
      sub: `输入 ${fmtCompact(hTok.inputTokens)} · 输出 ${fmtCompact(hTok.outputTokens)}`,
    },
  ]
})

const kbStats = computed(() => {
  const d = (stats.value || baseEmpty).kb
  return [
    { label: '个知识库', value: fmtInt(d.kbCount) },
    { label: '份文档', value: fmtInt(d.docCount) },
    { label: '个分片', value: fmtInt(d.chunkCount) },
  ]
})

const avgChats = computed(() => {
  const t = stats.value?.trend || []
  if (!t.length) return 0
  return Math.round(t.reduce((s, x) => s + x.chats, 0) / t.length)
})

// 今日对话卡片小字：按次数分级吐槽，拽一点
const todayChatQuip = computed(() => {
  const n = stats.value?.chat.today ?? 0
  if (n === 0) return '今天一句都不跟本喵说？'
  if (n <= 3) return '就这？本喵还没热身呢'
  if (n <= 10) return '还行，勉强算你惦记本喵'
  if (n <= 30) return '话这么多，本喵耳朵起茧了'
  return '疯狂粘人，本喵勉强受宠若惊吧'
})

// ---------- 图表 refs 与实例 ----------
const trendRef = ref(null)
const tokenTodayRef = ref(null)
const tokenTotalRef = ref(null)
const kbRef = ref(null)
const charts = shallowRef([])

const tooltipStyle = {
  backgroundColor: COLOR.tooltipBg,
  borderColor: COLOR.tooltipBorder,
  borderWidth: 1,
  padding: [9, 12],
  textStyle: { color: COLOR.textStrong, fontSize: 12 },
  extraCssText: 'border-radius:10px;box-shadow:0 16px 40px -16px rgba(0,0,0,0.85);backdrop-filter:blur(8px);',
}

// 统一的轴样式：去掉轴线，只留极淡的虚线网格
const axisLabel = { color: COLOR.text, fontSize: 11 }
const axisLine = { show: false }
const splitLine = { lineStyle: { color: COLOR.split, type: [3, 4] } }

const legendStyle = {
  icon: 'roundRect',
  itemWidth: 8,
  itemHeight: 8,
  itemGap: 18,
  top: 2,
  textStyle: { color: COLOR.text, fontSize: 11 },
}

function disposeCharts() {
  charts.value.forEach((c) => c.dispose())
  charts.value = []
}

function emptyGraphic(text) {
  return [
    {
      type: 'text',
      left: 'center',
      top: '46%',
      style: {
        text,
        fill: COLOR.text,
        fontSize: 13,
        fontWeight: 400,
        letterSpacing: 0.4,
      },
    },
  ]
}

function initCharts() {
  disposeCharts()
  const d = stats.value || baseEmpty
  const list = []

  // === 近 7 天趋势：柱（对话次数）+ 折线（Token 用量），双轴 ===
  if (trendRef.value) {
    const c = echarts.init(trendRef.value)
    const dates = d.trend.map((x) => x.date)
    const hasTrend = dates.length > 0
    c.setOption({
      graphic: hasTrend ? [] : emptyGraphic('近 7 天还没有对话记录，快去和本喵唠两句'),
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(255,255,255,0.035)' } },
        ...tooltipStyle,
        valueFormatter: (v) => fmtInt(v),
      },
      legend: { ...legendStyle, data: ['你找本喵', '烧掉的 Token'] },
      grid: { left: 46, right: 54, top: 44, bottom: 26 },
      xAxis: {
        type: 'category',
        data: dates,
        axisLine,
        axisTick: { show: false },
        axisLabel: { ...axisLabel, margin: 12 },
      },
      yAxis: [
        {
          type: 'value',
          name: '次数',
          nameTextStyle: { color: COLOR.text, fontSize: 11, padding: [0, 0, 4, -24] },
          minInterval: 1,
          splitLine,
          axisLine,
          axisTick: { show: false },
          axisLabel,
        },
        {
          type: 'value',
          name: 'Token',
          nameTextStyle: { color: COLOR.text, fontSize: 11, padding: [0, -18, 4, 0] },
          splitLine: { show: false },
          axisLine,
          axisTick: { show: false },
          axisLabel: { ...axisLabel, formatter: (v) => fmtCompact(v) },
        },
      ],
      series: [
        {
          name: '你找本喵',
          type: 'bar',
          data: d.trend.map((x) => x.chats),
          barMaxWidth: 24,
          itemStyle: {
            borderRadius: [4, 4, 0, 0],
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: COLOR.amber },
              { offset: 1, color: COLOR.amberDeep },
            ]),
          },
          emphasis: { itemStyle: { color: '#F7C173' } },
        },
        {
          name: '烧掉的 Token',
          type: 'line',
          yAxisIndex: 1,
          smooth: 0.35,
          symbolSize: 6,
          symbol: 'circle',
          data: d.trend.map((x) => x.tokens),
          itemStyle: { color: COLOR.azure, borderColor: '#0E1118', borderWidth: 2 },
          lineStyle: { width: 2, color: COLOR.azure, shadowBlur: 10, shadowColor: 'rgba(143,182,232,0.35)' },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(143,182,232,0.22)' },
              { offset: 1, color: 'rgba(143,182,232,0)' },
            ]),
          },
        },
      ],
    })
    list.push(c)
  }

  // === Token 构成环图（今日 / 历史） ===
  const makeDonut = (el, title, tok) => {
    if (!el) return
    const c = echarts.init(el)
    const has = tok.totalTokens > 0
    c.setOption({
      title: {
        text: title,
        subtext: has ? fmtCompact(tok.totalTokens) : '暂无',
        left: 'center',
        top: '37%',
        textStyle: { color: COLOR.text, fontSize: 11, fontWeight: 500, letterSpacing: 1 },
        subtextStyle: { color: COLOR.textStrong, fontSize: 20, fontWeight: 700 },
      },
      tooltip: {
        trigger: 'item',
        ...tooltipStyle,
        formatter: (p) => has ? `${p.name}：${fmtInt(p.value)}（${p.percent}%）` : '暂无数据',
      },
      series: [
        {
          type: 'pie',
          radius: ['62%', '82%'],
          center: ['50%', '52%'],
          avoidLabelOverlap: false,
          label: { show: false },
          labelLine: { show: false },
          itemStyle: { borderColor: '#12161F', borderWidth: 3 },
          data: has
            ? [
                { name: '听你唠叨（输入）', value: tok.inputTokens, itemStyle: { color: COLOR.amber } },
                { name: '本喵高见（输出）', value: tok.outputTokens, itemStyle: { color: COLOR.azure } },
              ]
            : [{ name: '无数据', value: 1, itemStyle: { color: COLOR.track, borderWidth: 0 } }],
        },
      ],
    })
    list.push(c)
  }
  makeDonut(tokenTodayRef.value, '今日', d.token.today)
  makeDonut(tokenTotalRef.value, '历史累计', d.token.total)

  // === 知识库分布：按库堆叠柱（文档数 / 分片数） ===
  if (kbRef.value) {
    const c = echarts.init(kbRef.value)
    const per = d.kb.perKb || []
    const names = per.map((x) => x.name)
    const hasKb = per.length > 0
    c.setOption({
      graphic: hasKb ? [] : emptyGraphic('还没有知识库，去「藏书阁」建一个吧'),
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(255,255,255,0.035)' } },
        ...tooltipStyle,
        valueFormatter: (v) => fmtInt(v),
      },
      legend: { ...legendStyle, data: ['藏书（文档）', '笔记（分片）'] },
      grid: { left: 46, right: 18, top: 44, bottom: per.length > 4 ? 54 : 26 },
      xAxis: {
        type: 'category',
        data: names.length ? names : ['暂无知识库'],
        axisLine,
        axisTick: { show: false },
        axisLabel: {
          ...axisLabel,
          margin: 12,
          interval: 0,
          rotate: names.length > 4 ? 24 : 0,
          formatter: (v) => (v.length > 8 ? v.slice(0, 7) + '…' : v),
        },
      },
      yAxis: {
        type: 'value',
        minInterval: 1,
        splitLine,
        axisLine,
        axisTick: { show: false },
        axisLabel,
      },
      series: [
        {
          name: '藏书（文档）',
          type: 'bar',
          stack: 'kb',
          data: per.map((x) => x.docCount),
          barMaxWidth: 30,
          itemStyle: { color: COLOR.jade },
        },
        {
          name: '笔记（分片）',
          type: 'bar',
          stack: 'kb',
          data: per.map((x) => x.chunkCount),
          barMaxWidth: 30,
          itemStyle: { color: COLOR.amber, borderRadius: [4, 4, 0, 0] },
        },
      ],
    })
    list.push(c)
  }

  charts.value = list
}

const handleResize = () => charts.value.forEach((c) => c.resize())

// ---------- 数据加载 ----------
// 后端就绪前不发请求：Python 端口由 Electron 的 agent-ready 上报（8790 被占用时会回退到随机
// 端口），而本页挂载时（子组件 onMounted 先于 App.vue）往往还没拿到端口，此时请求会打到默认
// 端口并被直接拒绝，浏览器只抛 "Failed to fetch"。
// 生产构建（electron:preview / 打包版）页面自本地文件加载、挂载极快，比 dev（Vite 现编译
// 2800+ 模块、天然慢几秒）更容易撞上 Python 冷启动窗口，所以这里用"等就绪 + 失败退避重试"
// 双保险，任一侧生效都不会再把错误卡片挂在界面上。
const { state: socketState } = useAgentSocket()

const RETRY_MAX = 5 // 自动重试次数上限
const RETRY_BASE_MS = 1500 // 首次重试间隔，之后指数退避：1.5s / 3s / 6s / 12s / 24s

const retrying = ref(false)
const retryCount = ref(0)

let retryTimer = null
let autoTimer = null
let bootTimer = null
let stopStatusWatch = null

async function loadData() {
  loading.value = true
  usageLoading.value = true
  fetchUsageStats(8)
    .then((data) => { usage.value = data })
    .catch((e) => console.warn('[dashboard] 用量统计加载失败:', e))
    .finally(() => { usageLoading.value = false })
  try {
    const data = await fetchDashboardStats(7)
    stats.value = data
    error.value = ''
    retryCount.value = 0
    retrying.value = false
    lastUpdated.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    await nextTick()
    initCharts()
  } catch (e) {
    error.value = `本喵翻遍了账本也没找到数据：${e.message}`
    scheduleRetry()
  } finally {
    loading.value = false
  }
}

/** 失败后退避重试：覆盖"端口已就绪但 Python 仍在冷启动"的时间窗 */
function scheduleRetry() {
  if (retryCount.value >= RETRY_MAX) {
    retrying.value = false
    return
  }
  const delay = RETRY_BASE_MS * 2 ** retryCount.value
  retryCount.value += 1
  retrying.value = true
  clearTimeout(retryTimer)
  retryTimer = setTimeout(() => { retryTimer = null; loadData() }, delay)
}

/** 手动刷新/重试：清掉待重试计时器并重置计数，避免与自动重试叠加 */
function manualRefresh() {
  clearTimeout(retryTimer)
  retryTimer = null
  retryCount.value = 0
  retrying.value = false
  loadData()
}

/** 后端就绪（端口可用）后启动：先拉一次数据，再开启定时刷新 */
function startLoad() {
  if (bootTimer) { clearTimeout(bootTimer); bootTimer = null }
  if (stopStatusWatch) { stopStatusWatch(); stopStatusWatch = null }
  loadData()
  if (!autoTimer) autoTimer = setInterval(loadData, 60000) // 60s 自动刷新
}

onMounted(() => {
  if (socketState.status === 'open') {
    // 已连通（例如从其它页面切回本页）：直接拉
    startLoad()
  } else if (!window.electronAPI) {
    // 非 Electron（浏览器直连调试）：没有 agent-ready 可等，按默认端口直接试
    startLoad()
  } else {
    // Electron 环境：等 setPort 触发的重连把状态推进到 open
    stopStatusWatch = watch(() => socketState.status, (s) => { if (s === 'open') startLoad() })
    // 兜底：WS 久未连通也先试一次；失败会自动退避重试，不会再一直挂着错误卡片
    bootTimer = setTimeout(startLoad, 8000)
  }
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  if (autoTimer) clearInterval(autoTimer)
  if (bootTimer) clearTimeout(bootTimer)
  if (retryTimer) clearTimeout(retryTimer)
  if (stopStatusWatch) stopStatusWatch()
  window.removeEventListener('resize', handleResize)
  disposeCharts()
})
</script>

<style scoped>
.page {
  max-width: 1180px;
  margin: 0 auto;
  animation: fadeUp var(--dur-slow) var(--ease-out) backwards;
}

/* ===== 页头 ===== */
.page-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  flex-wrap: wrap;
  margin-bottom: 22px;
}

.eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.2em;
  color: var(--amber-500);
  margin-bottom: 8px;
}

.page-title {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--text-1);
  line-height: 1.25;
}

.page-subtitle {
  margin-top: 7px;
  font-size: 13px;
  color: var(--text-3);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.update-time {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11.5px;
  color: var(--text-4);
  font-variant-numeric: tabular-nums;
}

.btn-refresh {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 32px;
  padding: 0 13px;
  font-size: 12.5px;
  font-weight: 500;
  color: var(--text-2);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  cursor: pointer;
  transition: color var(--dur-fast), background var(--dur-fast), border-color var(--dur-fast);
}

.btn-refresh:hover:not(:disabled) {
  color: var(--text-1);
  background: rgba(255, 255, 255, 0.06);
  border-color: var(--line-3);
}

.btn-refresh:disabled {
  opacity: 0.55;
  cursor: default;
}

.spinning {
  animation: spin 1s linear infinite;
}

/* ===== 卡片通用 ===== */
.card {
  position: relative;
  background: linear-gradient(180deg, var(--ink-850), var(--ink-800));
  border: 1px solid var(--line-1);
  border-radius: var(--r-lg);
  box-shadow: var(--hairline), 0 1px 2px rgba(0, 0, 0, 0.3);
  overflow: hidden;
}

/* ===== 错误空态 ===== */
.error-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 56px 24px;
  text-align: center;
}

.error-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  margin-bottom: 4px;
  border-radius: var(--r-md);
  color: var(--amber-400);
  background: var(--amber-a12);
  border: 1px solid var(--amber-a20);
}

.error-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-1);
}

.error-text {
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-3);
  max-width: 60ch;
}

.error-hint {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  color: var(--text-4);
}

.btn-retry {
  margin-top: 8px;
  height: 34px;
  padding: 0 22px;
  font-size: 13px;
  font-weight: 600;
  color: var(--amber-ink);
  background: var(--amber-grad);
  border: none;
  border-radius: var(--r-sm);
  cursor: pointer;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.3);
  transition: filter var(--dur-fast), box-shadow var(--dur-fast);
}

.btn-retry:hover {
  filter: brightness(1.07);
  box-shadow: var(--shadow-amber), inset 0 1px 0 rgba(255, 255, 255, 0.3);
}

/* ===== KPI 卡片 ===== */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 14px;
}

.kpi-card {
  padding: 16px 18px 18px;
  transition: border-color var(--dur), transform var(--dur) var(--ease-out), box-shadow var(--dur);
  animation: fadeUp 420ms var(--ease-out) both;
}

/* 四张卡片依次入场的 30ms 错峰：比整块同时出现更有节奏 */
.kpi-card:nth-child(1) { animation-delay: 20ms; }
.kpi-card:nth-child(2) { animation-delay: 50ms; }
.kpi-card:nth-child(3) { animation-delay: 80ms; }
.kpi-card:nth-child(4) { animation-delay: 110ms; }

.kpi-card:hover {
  border-color: var(--line-2);
  transform: translateY(-2px);
  box-shadow: var(--shadow-2), var(--hairline);
}

/* 顶部一道极淡的色相条，给同类指标一点身份区分 */
.kpi-card::before {
  content: '';
  position: absolute;
  inset: 0 0 auto;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--k), transparent);
  opacity: 0.55;
}

.kpi--amber { --k: var(--amber-400); --k-soft: var(--amber-a12); }
.kpi--azure { --k: var(--azure-400); --k-soft: var(--azure-a12); }
.kpi--jade { --k: var(--jade-400); --k-soft: var(--jade-a12); }

.kpi-top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
}

.kpi-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  flex-shrink: 0;
  border-radius: 8px;
  color: var(--k);
  background: var(--k-soft);
  border: 1px solid color-mix(in srgb, var(--k) 22%, transparent);
}

.kpi-label {
  font-size: 12px;
  color: var(--text-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.kpi-value {
  font-size: 27px;
  font-weight: 700;
  line-height: 1.1;
  letter-spacing: -0.02em;
  color: var(--text-1);
}

.kpi-sub {
  margin-top: 7px;
  font-size: 11.5px;
  color: var(--text-4);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ===== 知识库摘要条 ===== */
.kb-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  flex-wrap: wrap;
  padding: 14px 20px;
  margin-bottom: 16px;
  animation: fadeUp 420ms var(--ease-out) both;
  animation-delay: 140ms;
}

.kb-summary-head {
  display: flex;
  align-items: center;
  gap: 11px;
  min-width: 0;
}

.kb-summary-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  border-radius: 9px;
  color: var(--jade-400);
  background: var(--jade-a12);
  border: 1px solid rgba(126, 203, 161, 0.22);
}

.kb-summary-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-1);
}

.kb-summary-sub {
  font-size: 11.5px;
  color: var(--text-4);
  margin-top: 1px;
}

.kb-stats {
  display: flex;
  align-items: center;
  gap: 28px;
}

.kb-stat {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.kb-stat-value {
  font-size: 19px;
  font-weight: 700;
  color: var(--text-1);
  letter-spacing: -0.01em;
}

.kb-stat-label {
  font-size: 11.5px;
  color: var(--text-4);
}

/* ===== 图表 ===== */
.chart-card {
  margin-bottom: 16px;
  animation: fadeUp 460ms var(--ease-out) both;
  animation-delay: 170ms;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding: 15px 20px 9px;
}

.card-head-main {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}

.card-title {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--text-1);
  letter-spacing: -0.01em;
}

.card-sub {
  font-size: 11.5px;
  color: var(--text-4);
}

.chart-box {
  width: 100%;
}

.chart-row {
  display: grid;
  grid-template-columns: 1fr 1.15fr;
  gap: 16px;
}

.chart-row .chart-card {
  margin-bottom: 0;
}

.donut-wrap {
  display: flex;
  padding: 0 6px 10px;
}

.donut-box {
  flex: 1;
  height: 258px;
}

@media (max-width: 1180px) {
  .kpi-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 980px) {
  .chart-row {
    grid-template-columns: 1fr;
  }
  .page-title {
    font-size: 23px;
  }
}

/* ===== 用量与成本 ===== */
.usage-card {
  padding-bottom: 6px;
}

.usage-loading {
  display: inline-flex;
  align-items: center;
}

.usage-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  margin: 0 14px 12px;
  overflow: hidden;
  background: var(--line-1);
  border: 1px solid var(--line-1);
  border-radius: var(--r-sm);
}

.usage-summary-item {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 10px 12px;
  background: var(--bg-input);
}

.usage-summary-value {
  color: var(--text-1);
  font-size: 16px;
  font-weight: 650;
}

.usage-summary-label {
  color: var(--text-4);
  font-size: 10px;
}

.usage-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 14px;
  padding: 0 14px 12px;
}

.usage-block {
  min-width: 0;
}

.usage-block-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
  color: var(--text-2);
  font-size: 11.5px;
  font-weight: 600;
}

.usage-block-sub {
  color: var(--text-4);
  font-size: 9.5px;
  font-weight: 400;
}

.usage-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--line-1);
  border-radius: var(--r-sm);
}

.usage-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}

.usage-table th,
.usage-table td {
  padding: 7px 8px;
  text-align: left;
  border-bottom: 1px solid var(--line-1);
  white-space: nowrap;
}

.usage-table th {
  color: var(--text-4);
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: 0.04em;
  background: rgba(255, 255, 255, 0.02);
}

.usage-table tbody tr:last-child td {
  border-bottom: none;
}

.usage-table tbody tr:hover td {
  background: rgba(239, 168, 76, 0.035);
}

.usage-table .num {
  text-align: right;
  color: var(--text-2);
}

.usage-name {
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text-2);
}

.usage-session {
  max-width: 170px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding: 0;
  color: var(--text-2);
  font-family: inherit;
  font-size: inherit;
  background: none;
  border: none;
  cursor: pointer;
}

.usage-session:hover {
  color: var(--amber-200);
  text-decoration: underline;
  text-underline-offset: 2px;
}

.usage-bad {
  color: var(--coral-400) !important;
}

.usage-empty {
  padding: 18px 8px !important;
  text-align: center !important;
  color: var(--text-4);
}

@media (max-width: 900px) {
  .usage-grid {
    grid-template-columns: 1fr;
  }
  .usage-summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 620px) {
  .kpi-grid {
    grid-template-columns: 1fr;
  }
  .kb-stats {
    gap: 18px;
  }
  .donut-wrap {
    flex-direction: column;
  }
}
</style>
