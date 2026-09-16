<template>
  <div class="page">
    <header class="page-header">
      <div>
        <h1 class="page-title">本喵的辉煌战绩 😼</h1>
        <p class="page-subtitle">你每天陪优墨聊了多少，本喵都替你记着呢</p>
      </div>
      <div class="header-actions">
        <span class="update-time" v-if="lastUpdated">更新于 {{ lastUpdated }}</span>
        <button class="btn-refresh" :disabled="loading" @click="loadData">
          <span :class="{ spinning: loading }">⟳</span>
          {{ loading ? '加载中…' : '刷新' }}
        </button>
      </div>
    </header>

    <!-- 错误空态（Python 服务未运行等） -->
    <section v-if="error" class="card empty-card">
      <div class="empty-icon">⚠️</div>
      <div class="empty-text">{{ error }}</div>
      <button class="btn-retry" @click="loadData">重试</button>
    </section>

    <template v-else>
      <!-- KPI 指标卡片 -->
      <div class="kpi-grid">
        <section v-for="k in kpiCards" :key="k.label" class="card kpi-card">
          <div class="kpi-icon" :style="{ background: k.color + '22', color: k.color }">{{ k.icon }}</div>
          <div class="kpi-body">
            <div class="kpi-label">{{ k.label }}</div>
            <div class="kpi-value">{{ k.value }}</div>
            <div class="kpi-sub" v-html="k.sub"></div>
          </div>
        </section>
      </div>

      <!-- 近 7 天趋势 -->
      <section class="card chart-card">
        <div class="card-header">
          <span>近 7 天你找本喵的次数 📈</span>
          <span class="card-sub">柱形 = 对话次数 · 折线 = Token 用量</span>
        </div>
        <div ref="trendRef" class="chart-box" style="height: 300px"></div>
      </section>

      <div class="chart-row">
        <!-- Token 构成环图 -->
        <section class="card chart-card">
          <div class="card-header">
            <span>本喵烧掉的脑细胞 🧠（输入 / 输出）</span>
            <span class="card-sub">输入 = 你说的话 · 输出 = 本喵的回话</span>
          </div>
          <div class="donut-wrap">
            <div ref="tokenTodayRef" class="chart-box donut-box"></div>
            <div ref="tokenTotalRef" class="chart-box donut-box"></div>
          </div>
        </section>

        <!-- 知识库分布 -->
        <section class="card chart-card">
          <div class="card-header">
            <span>本喵的藏书阁家底 📚</span>
            <span class="card-sub">按库统计文档数与分片数</span>
          </div>
          <div ref="kbRef" class="chart-box" style="height: 300px"></div>
        </section>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, shallowRef } from 'vue'
import { fetchDashboardStats } from '../api/stats'

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

// ---------- 主题色（与全局深色风格一致） ----------
const COLOR = {
  text: '#94a3b8',
  textStrong: '#e2e8f0',
  axis: '#334155',
  tooltipBg: '#1e293b',
  tooltipBorder: '#334155',
  blue: '#38bdf8',
  violet: '#a78bfa',
  green: '#34d399',
  amber: '#fbbf24',
  rose: '#fb7185',
  cyan: '#22d3ee',
  slate: '#475569',
}

// ---------- 数据状态 ----------
const stats = ref(null)
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
      label: '今日对话次数', icon: '💬', color: COLOR.blue,
      value: fmtInt(d.chat.today), sub: todayChatQuip.value,
    },
    {
      label: '今日 Token 用量', icon: '⚡', color: COLOR.amber,
      value: fmtCompact(tTok.totalTokens),
      sub: `输入 ${fmtCompact(tTok.inputTokens)} · 输出 ${fmtCompact(tTok.outputTokens)}`,
    },
    {
      label: '历史对话次数', icon: '🗂️', color: COLOR.violet,
      value: fmtInt(d.chat.total), sub: `日均 ${avgChats.value} 次，本喵都记着呢`,
    },
    {
      label: '历史 Token 用量', icon: '🔋', color: COLOR.rose,
      value: fmtCompact(hTok.totalTokens),
      sub: `输入 ${fmtCompact(hTok.inputTokens)} · 输出 ${fmtCompact(hTok.outputTokens)}`,
    },
    {
      label: '知识库个数', icon: '📚', color: COLOR.green,
      value: fmtInt(d.kb.kbCount), sub: '本喵的藏书阁',
    },
    {
      label: '知识库文档个数', icon: '📄', color: COLOR.cyan,
      value: fmtInt(d.kb.docCount), sub: '本喵已读的书',
    },
    {
      label: '知识库分片个数', icon: '🧩', color: '#818cf8',
      value: fmtInt(d.kb.chunkCount), sub: '嚼碎了记脑子里',
    },
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
  textStyle: { color: COLOR.textStrong, fontSize: 12 },
}

function disposeCharts() {
  charts.value.forEach((c) => c.dispose())
  charts.value = []
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
      graphic: hasTrend
        ? []
        : [
            {
              type: 'text',
              left: 'center',
              top: '45%',
              style: {
                text: '近 7 天还没有对话记录，快去和本喵唠两句 😼',
                fill: COLOR.text,
                fontSize: 14,
                fontWeight: 500,
              },
            },
          ],
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        ...tooltipStyle,
        valueFormatter: (v) => fmtInt(v),
      },
      legend: {
        data: ['你找本喵', '烧掉的 Token'],
        textStyle: { color: COLOR.text },
        top: 4,
      },
      grid: { left: 50, right: 60, top: 40, bottom: 28 },
      xAxis: {
        type: 'category',
        data: dates,
        axisLine: { lineStyle: { color: COLOR.axis } },
        axisLabel: { color: COLOR.text },
      },
      yAxis: [
        {
          type: 'value',
          name: '次数',
          nameTextStyle: { color: COLOR.text },
          minInterval: 1,
          splitLine: { lineStyle: { color: COLOR.axis, type: 'dashed' } },
          axisLabel: { color: COLOR.text },
        },
        {
          type: 'value',
          name: 'Token',
          nameTextStyle: { color: COLOR.text },
          splitLine: { show: false },
          axisLabel: {
            color: COLOR.text,
            formatter: (v) => fmtCompact(v),
          },
        },
      ],
      series: [
        {
          name: '你找本喵',
          type: 'bar',
          data: d.trend.map((x) => x.chats),
          barMaxWidth: 28,
          itemStyle: {
            borderRadius: [5, 5, 0, 0],
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: COLOR.blue },
              { offset: 1, color: '#0369a1' },
            ]),
          },
        },
        {
          name: '烧掉的 Token',
          type: 'line',
          yAxisIndex: 1,
          smooth: true,
          symbolSize: 7,
          data: d.trend.map((x) => x.tokens),
          itemStyle: { color: COLOR.amber },
          lineStyle: { width: 2.5, color: COLOR.amber },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(251,191,36,0.25)' },
              { offset: 1, color: 'rgba(251,191,36,0)' },
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
        subtext: has ? fmtCompact(tok.totalTokens) : '暂无数据',
        left: 'center',
        top: '38%',
        textStyle: { color: COLOR.text, fontSize: 13, fontWeight: 400 },
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
          radius: ['58%', '78%'],
          center: ['50%', '50%'],
          avoidLabelOverlap: false,
          label: { show: false },
          labelLine: { show: false },
          data: has
            ? [
                { name: '听你唠叨（输入）', value: tok.inputTokens, itemStyle: { color: COLOR.violet } },
                { name: '本喵高见（输出）', value: tok.outputTokens, itemStyle: { color: COLOR.cyan } },
              ]
            : [{ name: '无数据', value: 1, itemStyle: { color: COLOR.slate } }],
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
      graphic: hasKb
        ? []
        : [
            {
              type: 'text',
              left: 'center',
              top: '45%',
              style: {
                text: '还没有知识库，去「知识库」页面建一个吧 📚',
                fill: COLOR.text,
                fontSize: 14,
                fontWeight: 500,
              },
            },
          ],
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        ...tooltipStyle,
        valueFormatter: (v) => fmtInt(v),
      },
      legend: {
        data: ['藏书（文档）', '笔记（分片）'],
        textStyle: { color: COLOR.text },
        top: 4,
      },
      grid: { left: 50, right: 20, top: 40, bottom: per.length > 4 ? 56 : 28 },
      xAxis: {
        type: 'category',
        data: names.length ? names : ['暂无知识库'],
        axisLine: { lineStyle: { color: COLOR.axis } },
        axisLabel: {
          color: COLOR.text,
          interval: 0,
          rotate: names.length > 4 ? 24 : 0,
          formatter: (v) => (v.length > 8 ? v.slice(0, 7) + '…' : v),
        },
      },
      yAxis: {
        type: 'value',
        minInterval: 1,
        splitLine: { lineStyle: { color: COLOR.axis, type: 'dashed' } },
        axisLabel: { color: COLOR.text },
      },
      series: [
        {
          name: '藏书（文档）',
          type: 'bar',
          stack: 'kb',
          data: per.map((x) => x.docCount),
          barMaxWidth: 34,
          itemStyle: { color: COLOR.green, borderRadius: [0, 0, 0, 0] },
        },
        {
          name: '笔记（分片）',
          type: 'bar',
          stack: 'kb',
          data: per.map((x) => x.chunkCount),
          barMaxWidth: 34,
          itemStyle: { color: '#0d9488', borderRadius: [5, 5, 0, 0] },
        },
      ],
    })
    list.push(c)
  }

  charts.value = list
}

const handleResize = () => charts.value.forEach((c) => c.resize())

// ---------- 数据加载 ----------
async function loadData() {
  loading.value = true
  try {
    const data = await fetchDashboardStats(7)
    stats.value = data
    error.value = ''
    lastUpdated.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    await nextTick()
    initCharts()
  } catch (e) {
    error.value = `本喵翻遍了账本也没找到数据：${e.message}（确认一下本地服务是否已启动）`
  } finally {
    loading.value = false
  }
}

let autoTimer = null
onMounted(() => {
  loadData()
  autoTimer = setInterval(loadData, 60000) // 60s 自动刷新
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  if (autoTimer) clearInterval(autoTimer)
  window.removeEventListener('resize', handleResize)
  disposeCharts()
})
</script>

<style scoped>
.page {
  max-width: 1200px;
}

.page-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  margin-bottom: 24px;
}

.page-title {
  font-size: 30px;
  font-weight: 700;
  color: #f1f5f9;
  margin-bottom: 6px;
}

.page-subtitle {
  font-size: 14px;
  color: #64748b;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 14px;
}

.update-time {
  font-size: 12px;
  color: #64748b;
}

.btn-refresh {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  font-size: 13px;
  color: #e2e8f0;
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 9px;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-refresh:hover:not(:disabled) {
  background: #273449;
}

.btn-refresh:disabled {
  opacity: 0.6;
  cursor: default;
}

.spinning {
  display: inline-block;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ===== 卡片通用 ===== */
.card {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 14px;
  overflow: hidden;
}

.card-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 4px 12px;
  padding: 16px 22px;
  font-size: 15px;
  font-weight: 600;
  color: #e2e8f0;
  border-bottom: 1px solid #334155;
}

.card-sub {
  font-size: 12px;
  font-weight: 400;
  color: #64748b;
}

/* ===== 错误空态 ===== */
.empty-card {
  padding: 64px 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
}

.empty-icon {
  font-size: 36px;
}

.empty-text {
  font-size: 14px;
  color: #94a3b8;
}

.btn-retry {
  padding: 8px 24px;
  font-size: 13px;
  color: #f1f5f9;
  background: #0ea5e9;
  border: none;
  border-radius: 9px;
  cursor: pointer;
}

.btn-retry:hover {
  background: #38bdf8;
}

/* ===== KPI 卡片 ===== */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.kpi-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px 20px;
}

.kpi-icon {
  width: 44px;
  height: 44px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  border-radius: 12px;
}

.kpi-body {
  min-width: 0;
}

.kpi-label {
  font-size: 13px;
  color: #94a3b8;
  margin-bottom: 4px;
  white-space: nowrap;
}

.kpi-value {
  font-size: 24px;
  font-weight: 700;
  color: #f1f5f9;
  font-family: 'Consolas', 'Monaco', monospace;
  line-height: 1.2;
}

.kpi-sub {
  font-size: 12px;
  color: #64748b;
  margin-top: 3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ===== 图表 ===== */
.chart-card {
  margin-bottom: 20px;
}

.chart-box {
  width: 100%;
}

.chart-row {
  display: grid;
  grid-template-columns: 1fr 1.2fr;
  gap: 20px;
}

.chart-row .chart-card {
  margin-bottom: 0;
}

@media (max-width: 900px) {
  .chart-row {
    grid-template-columns: 1fr;
  }
}

.donut-wrap {
  display: flex;
}

.donut-box {
  flex: 1;
  height: 260px;
}

@media (max-width: 560px) {
  .donut-wrap {
    flex-direction: column;
  }
}
</style>
