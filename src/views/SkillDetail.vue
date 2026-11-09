<template>
  <div class="sd-page">
    <!-- 顶部信息栏 -->
    <header class="sd-header">
      <button class="btn-back" @click="goBack">
        <AppIcon name="arrow-left" :size="14" />
        返回
      </button>
      <div class="sd-title-block">
        <div class="eyebrow">SKILL · 技能详情</div>
        <h2 class="sd-title">{{ skill?.displayName || routeName }}</h2>
        <p class="sd-subtitle" :title="skill?.description">{{ skill?.description || '暂无描述' }}</p>
      </div>
      <div class="sd-stats" v-if="skill">
        <div class="sd-stat">
          <span class="stat-value">{{ skill.fileCount }}</span>
          <span class="stat-label">文件</span>
        </div>
        <div class="sd-stat">
          <span class="stat-value">{{ skill.referenceCount }}</span>
          <span class="stat-label">参考</span>
        </div>
        <div class="sd-stat">
          <span class="stat-value">{{ skill.scriptCount }}</span>
          <span class="stat-label">脚本</span>
        </div>
      </div>
    </header>

    <div v-if="loading" class="state-block">
      <span class="ui-spinner"></span>
      <span>加载中…</span>
    </div>
    <div v-else-if="error" class="sd-error">
      <AppIcon name="alert" :size="15" />
      <span>{{ error }}</span>
      <button class="btn-retry" @click="load">重试</button>
    </div>

    <div v-else class="sd-body">
      <!-- 左侧目录树 -->
      <aside class="sd-tree">
        <div class="tree-head">
          <span class="tree-title">目录结构</span>
          <button class="btn-newfile" title="在技能内新增文件" @click="openCreate">
            <AppIcon name="plus" :size="12" />
            新增文件
          </button>
        </div>
        <div class="tree-scroll">
          <div class="tree-node root" :class="{ active: !currentPath }" @click="openSkillMd">
            <span class="tree-caret"></span>
            <span class="tree-icon"><AppIcon name="package" :size="14" /></span>
            <span class="tree-name">{{ routeName }}/</span>
          </div>
          <div
            v-for="node in visibleNodes"
            :key="node.path"
            class="tree-node"
            :class="{ active: currentPath === node.path }"
            :style="{ paddingLeft: 10 + node.depth * 16 + 'px' }"
            @click="onNodeClick(node)"
          >
            <span v-if="node.type === 'dir'" class="tree-caret">
              <AppIcon :name="expanded.has(node.path) ? 'chevron-down' : 'chevron-right'" :size="12" />
            </span>
            <span v-else class="tree-caret"></span>
            <span class="tree-icon"><AppIcon :name="nodeIcon(node)" :size="13" /></span>
            <span class="tree-name" :title="node.path">{{ node.name }}</span>
            <span class="tree-size" v-if="node.type === 'file'">{{ fmtSize(node.size) }}</span>
          </div>
        </div>
      </aside>

      <!-- 右侧文件查看 / 编辑区 -->
      <section class="sd-viewer">
        <template v-if="currentPath">
          <div class="viewer-head">
            <span class="viewer-path" :title="currentPath">{{ routeName }}/{{ currentPath }}</span>
            <div class="viewer-actions">
              <div class="mode-toggle">
                <button
                  class="mode-btn"
                  :class="{ on: previewMode }"
                  @click="previewMode = true"
                >预览</button>
                <button
                  class="mode-btn"
                  :class="{ on: !previewMode }"
                  @click="previewMode = false"
                >编辑</button>
              </div>
              <button
                class="btn-save"
                :disabled="!dirty || saving"
                @click="saveFile"
              >
                <AppIcon name="check" :size="13" />
                {{ saving ? '保存中…' : '保存' }}
              </button>
              <button class="btn-del" title="删除该文件" @click="confirmDelete">
                <AppIcon name="trash" :size="13" />
                删除
              </button>
            </div>
          </div>
          <div v-if="fileLoading" class="state-block">
            <span class="ui-spinner"></span>
            <span>文件加载中…</span>
          </div>
          <div v-else-if="fileUnsupported" class="state-block warn">
            <AppIcon name="alert" :size="15" />
            <span>{{ fileUnsupported }}</span>
          </div>
          <div v-else class="viewer-body">
            <div v-if="isMarkdown && previewMode" class="md-wrap">
              <MarkdownRenderer :content="fileContent" />
            </div>
            <div
              v-else-if="!isMarkdown && previewMode"
              class="code-wrap"
            >
              <pre class="code-pre"><code class="hljs" v-html="highlightedHtml"></code></pre>
            </div>
            <textarea
              v-else
              v-model="editContent"
              class="code-editor"
              spellcheck="false"
              @keydown.ctrl.s.prevent="saveFile"
              @keydown.meta.s.prevent="saveFile"
            ></textarea>
          </div>
          <div class="viewer-foot" v-if="dirty && !previewMode">
            <span class="foot-dot"></span>
            有未保存的修改（保存前自动备份为 {{ currentPath }}.bak，Ctrl+S 快捷保存）
          </div>
        </template>
        <div v-else class="ui-empty viewer-placeholder">
          <div class="ui-empty-icon"><AppIcon name="folder" :size="24" /></div>
          <div class="ui-empty-title">从左侧目录树选择一个文件查看 / 编辑</div>
          <p class="ui-empty-text">技能下所有文本文件（含脚本）均可在线修改，保存后即刻生效</p>
        </div>
      </section>
    </div>

    <!-- 新增文件弹窗 -->
    <div v-if="showCreate" class="modal-mask" @click.self="showCreate = false">
      <div class="modal">
        <div class="modal-title">
          <AppIcon name="plus" :size="16" />
          新增文件
        </div>
        <input
          v-model="newPath"
          class="modal-input"
          placeholder="相对路径，如 scripts/helper.py 或 notes.md"
          maxlength="200"
          @keyup.enter="submitCreate"
        />
        <div class="modal-hint">支持子目录（自动创建）；同名文件已存在时会提示冲突</div>
        <div v-if="createError" class="modal-error">{{ createError }}</div>
        <div class="modal-actions">
          <button class="btn-ghost" @click="showCreate = false">取消</button>
          <button class="btn-primary" :disabled="creating || !newPath.trim()" @click="submitCreate">
            {{ creating ? '创建中…' : '创建并编辑' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { createSkillFile, deleteSkillFile, getSkill, readSkillFile, writeSkillFile } from '../api/skills'
import MarkdownRenderer from '../components/MarkdownRenderer.vue'
import AppIcon from '../components/AppIcon.vue'
import hljs from 'highlight.js/lib/common'
import 'highlight.js/styles/atom-one-dark.css'

// 扩展名 -> highlight.js 语言（未命中则自动探测）
const HL_LANG = {
  py: 'python', js: 'javascript', mjs: 'javascript', cjs: 'javascript', ts: 'typescript',
  json: 'json', md: 'markdown', markdown: 'markdown', sh: 'bash', bash: 'bash',
  bat: 'dos', cmd: 'dos', ps1: 'powershell', yml: 'yaml', yaml: 'yaml', toml: 'ini',
  ini: 'ini', cfg: 'ini', html: 'xml', xml: 'xml', css: 'css', lua: 'lua', go: 'go',
  rs: 'rust', java: 'java', rb: 'ruby', php: 'php', sql: 'sql', txt: 'plaintext',
}

const route = useRoute()
const router = useRouter()
const routeName = computed(() => route.params.name)

const skill = ref(null)
const tree = ref([])
const loading = ref(true)
const error = ref('')

// ---------- 目录树扁平化（展开状态驱动） ----------
const expanded = ref(new Set())

const visibleNodes = computed(() => {
  const out = []
  const walk = (nodes, depth) => {
    for (const n of nodes) {
      out.push({ ...n, depth })
      if (n.type === 'dir' && expanded.value.has(n.path)) {
        walk(n.children || [], depth + 1)
      }
    }
  }
  walk(tree.value, 0)
  return out
})

// 图标名（交给 AppIcon 渲染，避免各系统 emoji 字形不一致）
function nodeIcon(node) {
  if (node.type === 'dir') return 'folder'
  const ext = node.name.slice(node.name.lastIndexOf('.')).toLowerCase()
  if (ext === '.md') return 'file'
  if (ext === '.py') return 'terminal'
  if (['.js', '.ts', '.json'].includes(ext)) return 'file'
  if (['.sh', '.bat', '.ps1'].includes(ext)) return 'terminal'
  return 'file'
}

function fmtSize(n) {
  if (n == null) return ''
  if (n < 1024) return n + ' B'
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB'
  return (n / 1024 / 1024).toFixed(1) + ' MB'
}

function onNodeClick(node) {
  if (node.type === 'dir') {
    const s = new Set(expanded.value)
    s.has(node.path) ? s.delete(node.path) : s.add(node.path)
    expanded.value = s
  } else {
    openFile(node.path)
  }
}

// ---------- 文件查看 / 编辑 ----------
const currentPath = ref('')
const fileContent = ref('')
const editContent = ref('')
const fileLoading = ref(false)
const fileUnsupported = ref('')
const saving = ref(false)
const previewMode = ref(true)

const isMarkdown = computed(() => /\.(md|markdown)$/i.test(currentPath.value))
const dirty = computed(() => currentPath.value && editContent.value !== fileContent.value)

// 脚本/代码预览：highlight.js 语法高亮（按扩展名选语言，未命中自动探测）
const highlightedHtml = computed(() => {
  const code = editContent.value
  if (!code) return ''
  const ext = currentPath.value.slice(currentPath.value.lastIndexOf('.') + 1).toLowerCase()
  const lang = HL_LANG[ext]
  try {
    if (lang && hljs.getLanguage(lang)) {
      return hljs.highlight(code, { language: lang, ignoreIllegals: true }).value
    }
    return hljs.highlightAuto(code).value
  } catch {
    return code.replace(/&/g, '&').replace(/</g, '<').replace(/>/g, '>')
  }
})

function findNode(nodes, path) {
  for (const n of nodes) {
    if (n.path === path) return n
    if (n.type === 'dir') {
      const hit = findNode(n.children || [], path)
      if (hit) return hit
    }
  }
  return null
}

async function openFile(path) {
  if (dirty.value && !window.confirm('当前文件有未保存的修改，切换将丢弃，确定吗？')) return
  currentPath.value = path
  fileContent.value = ''
  editContent.value = ''
  fileUnsupported.value = ''
  fileLoading.value = true
  previewMode.value = true
  try {
    const node = findNode(tree.value, path)
    if (node && node.text === false) {
      fileUnsupported.value = '该文件类型不支持在线查看 / 编辑'
    } else {
      const res = await readSkillFile(routeName.value, path)
      fileContent.value = res.content
      editContent.value = res.content
    }
  } catch (e) {
    fileUnsupported.value = e.message
  } finally {
    fileLoading.value = false
  }
}

async function openSkillMd() {
  // 点击根节点：默认展示 SKILL.md（存在时）
  if (skill.value && tree.value.some((n) => n.name === 'SKILL.md')) {
    await openFile('SKILL.md')
  }
}

async function saveFile() {
  if (!dirty.value || saving.value) return
  saving.value = true
  try {
    await writeSkillFile(routeName.value, currentPath.value, editContent.value)
    fileContent.value = editContent.value
    error.value = ''
  } catch (e) {
    window.alert(`保存失败：${e.message}`)
  } finally {
    saving.value = false
  }
}

// ---------- 删除文件 ----------
const deleting = ref(false)

async function confirmDelete() {
  if (!currentPath.value || deleting.value) return
  if (dirty.value && !window.confirm(`「${currentPath.value}」有未保存的修改，仍要删除吗？`)) return
  if (!window.confirm(`确定删除「${currentPath.value}」吗？该操作不可撤销（.bak 备份将一并删除）。`)) return
  deleting.value = true
  try {
    await deleteSkillFile(routeName.value, currentPath.value)
    currentPath.value = ''
    fileContent.value = ''
    editContent.value = ''
    fileUnsupported.value = ''
    // 重新拉目录树，刷新文件计数与树节点
    await reloadTree()
  } catch (e) {
    window.alert(`删除失败：${e.message}`)
  } finally {
    deleting.value = false
  }
}

// 仅刷新目录树与元信息，不清空当前打开的文件
async function reloadTree() {
  try {
    const res = await getSkill(routeName.value)
    skill.value = res.skill
    tree.value = res.tree || []
  } catch (e) {
    error.value = `刷新目录失败：${e.message}`
  }
}

// ---------- 新增文件 ----------
const showCreate = ref(false)
const newPath = ref('')
const createError = ref('')
const creating = ref(false)

function openCreate() {
  newPath.value = ''
  createError.value = ''
  showCreate.value = true
}

async function submitCreate() {
  const path = newPath.value.trim().replace(/^\/+/, '')
  if (!path) return
  creating.value = true
  createError.value = ''
  try {
    await createSkillFile(routeName.value, path, '')
    showCreate.value = false
    // 重新拉目录树（可能引入了新子目录），并展开新文件所在目录
    await load({ keepFile: false })
    // 展开新文件的各级父目录
    const s = new Set(expanded.value)
    const parts = path.split('/')
    for (let i = 1; i < parts.length; i++) {
      s.add(parts.slice(0, i).join('/'))
    }
    expanded.value = s
    await openFile(path)
  } catch (e) {
    createError.value = e.message
  } finally {
    creating.value = false
  }
}

// ---------- 详情加载 ----------
async function load(opts = {}) {
  loading.value = true
  error.value = ''
  currentPath.value = ''
  fileContent.value = ''
  editContent.value = ''
  try {
    const res = await getSkill(routeName.value)
    skill.value = res.skill
    tree.value = res.tree || []
    // 默认展开 references 与 scripts 之外的顶层目录，方便一眼看到文件
    const top = new Set()
    for (const n of tree.value) {
      if (n.type === 'dir' && !['references', 'scripts'].includes(n.name.toLowerCase())) {
        top.add(n.path)
      }
    }
    expanded.value = top
    // 默认打开 SKILL.md
    if (res.skill && res.tree?.some((n) => n.name === 'SKILL.md')) {
      await openFile('SKILL.md')
    }
  } catch (e) {
    error.value = `加载技能详情失败：${e.message}`
  } finally {
    loading.value = false
  }
}

function goBack() {
  router.push('/skills')
}

watch(routeName, () => load())
onMounted(load)
</script>

<style scoped>
.sd-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 104px);
  min-height: 420px;
  color: var(--text-2);
  animation: fadeIn var(--dur-slow) var(--ease-out) both;
}

/* ===== 头部 ===== */
.sd-header {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  flex-shrink: 0;
  margin-bottom: 20px;
}

.btn-back {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 12px;
  flex-shrink: 0;
  font-size: 12.5px;
  color: var(--text-2);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  cursor: pointer;
  transition: color var(--dur-fast), background var(--dur-fast), border-color var(--dur-fast);
}

.btn-back:hover {
  color: var(--text-1);
  background: rgba(255, 255, 255, 0.06);
  border-color: var(--line-3);
}

.sd-title-block {
  flex: 1;
  min-width: 0;
}

.eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.18em;
  color: var(--amber-500);
  margin-bottom: 5px;
}

.sd-title {
  margin: 0;
  font-size: 23px;
  font-weight: 700;
  line-height: 1.25;
  letter-spacing: -0.02em;
  color: var(--text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sd-subtitle {
  margin: 4px 0 0;
  font-size: 12.5px;
  color: var(--text-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 元信息：横向统计组（值强、标签弱，靠左发丝线分隔） */
.sd-stats {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 18px;
  flex-shrink: 0;
  margin: 0 0 0 auto;
  padding-left: 18px;
  border-left: 1px solid var(--line-1);
}

.sd-stat {
  display: flex;
  align-items: baseline;
  gap: 5px;
}

.stat-value {
  font-size: 15px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--text-1);
  font-variant-numeric: tabular-nums;
}

.stat-label {
  font-size: 11px;
  color: var(--text-4);
}

/* ===== 状态 ===== */
.state-block {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  padding: 48px 16px;
  font-size: 13px;
  color: var(--text-3);
}

.state-block.warn {
  color: var(--warn-400);
}

.sd-error {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 12px 14px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--coral-400);
  background: var(--coral-a12);
  border: 1px solid rgba(233, 119, 110, 0.3);
  border-radius: var(--r-md);
}

.btn-retry {
  margin-left: auto;
  height: 26px;
  padding: 0 10px;
  font-size: 12px;
  color: var(--coral-400);
  background: transparent;
  border: 1px solid rgba(233, 119, 110, 0.4);
  border-radius: var(--r-xs);
  cursor: pointer;
  transition: background var(--dur-fast), border-color var(--dur-fast);
}

.btn-retry:hover {
  background: rgba(233, 119, 110, 0.18);
  border-color: rgba(233, 119, 110, 0.6);
}

/* ===== 主体两栏 ===== */
.sd-body {
  flex: 1;
  display: flex;
  gap: 14px;
  min-height: 0;
}

/* 左：目录树 */
.sd-tree {
  display: flex;
  flex-direction: column;
  width: 262px;
  min-width: 200px;
  min-height: 0;
  background: linear-gradient(180deg, var(--ink-850), var(--ink-800));
  border: 1px solid var(--line-1);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-1), var(--hairline);
  overflow: hidden;
}

.tree-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-shrink: 0;
  padding: 10px 10px 10px 14px;
  border-bottom: 1px solid var(--line-1);
}

.tree-title {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--text-2);
}

.btn-newfile {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 24px;
  padding: 0 8px;
  font-size: 11px;
  color: var(--amber-300);
  background: var(--amber-a12);
  border: 1px solid var(--amber-a20);
  border-radius: var(--r-xs);
  white-space: nowrap;
  cursor: pointer;
  transition: background var(--dur-fast), border-color var(--dur-fast), color var(--dur-fast);
}

.btn-newfile:hover {
  color: var(--amber-200);
  background: var(--amber-a20);
  border-color: var(--amber-a35);
}

.tree-scroll {
  flex: 1;
  min-height: 0;
  padding: 6px 0;
  overflow-y: auto;
}

.tree-node {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 28px;
  padding: 4px 10px;
  font-size: 12.5px;
  color: var(--text-2);
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
  transition: background var(--dur-fast), color var(--dur-fast);
}

.tree-node:hover {
  color: var(--text-1);
  background: rgba(255, 255, 255, 0.04);
}

.tree-node.active {
  color: var(--amber-200);
  background: linear-gradient(90deg, rgba(239, 168, 76, 0.14), rgba(239, 168, 76, 0.02));
  box-shadow: inset 2px 0 0 var(--amber-400);
}

.tree-node.root {
  font-weight: 600;
  padding-left: 10px;
}

.tree-caret {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 12px;
  flex-shrink: 0;
  color: var(--text-4);
}

.tree-icon {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  color: var(--text-4);
}

.tree-node.active .tree-icon {
  color: var(--amber-300);
}

.tree-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tree-size {
  margin-left: auto;
  flex-shrink: 0;
  padding-right: 4px;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-4);
}

/* 右：查看器 */
.sd-viewer {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
  background: linear-gradient(180deg, var(--ink-850), var(--ink-800));
  border: 1px solid var(--line-1);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-1), var(--hairline);
  overflow: hidden;
}

.viewer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-shrink: 0;
  padding: 8px 12px 8px 16px;
  background: rgba(255, 255, 255, 0.015);
  border-bottom: 1px solid var(--line-1);
}

.viewer-path {
  min-width: 0;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.viewer-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.mode-toggle {
  display: inline-flex;
  gap: 2px;
  padding: 2px;
  background: var(--ink-1000);
  border: 1px solid var(--line-1);
  border-radius: var(--r-sm);
}

.mode-btn {
  height: 24px;
  padding: 0 10px;
  font-size: 11.5px;
  color: var(--text-3);
  background: transparent;
  border: none;
  border-radius: var(--r-xs);
  cursor: pointer;
  transition: color var(--dur-fast), background var(--dur-fast), box-shadow var(--dur-fast);
}

.mode-btn:hover {
  color: var(--text-1);
}

.mode-btn.on {
  color: var(--amber-200);
  background: var(--amber-a12);
  box-shadow: inset 0 0 0 1px var(--amber-a20);
}

.btn-save {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 28px;
  padding: 0 12px;
  font-size: 12px;
  font-weight: 650;
  color: var(--amber-ink);
  background: var(--amber-grad);
  border: none;
  border-radius: var(--r-xs);
  cursor: pointer;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.28);
  transition: filter var(--dur-fast), box-shadow var(--dur-fast);
}

.btn-save:hover:not(:disabled) {
  filter: brightness(1.06);
  box-shadow: var(--shadow-amber), inset 0 1px 0 rgba(255, 255, 255, 0.3);
}

.btn-save:disabled {
  opacity: 0.4;
  cursor: default;
}

.btn-del {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 28px;
  padding: 0 10px;
  font-size: 12px;
  color: var(--coral-400);
  background: transparent;
  border: 1px solid rgba(233, 119, 110, 0.3);
  border-radius: var(--r-xs);
  cursor: pointer;
  transition: background var(--dur-fast), border-color var(--dur-fast);
}

.btn-del:hover {
  background: var(--coral-a12);
  border-color: rgba(233, 119, 110, 0.55);
}

.viewer-body {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: auto;
}

/* 长文阅读：正文 14px/1.75，代码块已是 ink-1000 + 发丝线 */
.md-wrap {
  flex: 1;
  min-width: 0;
  padding: 28px 40px 40px;
  box-sizing: border-box;
}

.md-wrap :deep(.markdown-body) {
  max-width: 820px;
  margin: 0 auto;
  font-size: 14px;
  line-height: 1.75;
  color: var(--text-2);
}

/* 脚本/代码高亮预览 */
.code-wrap {
  flex: 1;
  min-width: 0;
  padding: 16px;
  overflow: auto;
  background: transparent;
}

.code-pre {
  margin: 0;
  padding: 16px 18px;
  min-height: 100%;
  background: var(--ink-1000);
  border: 1px solid var(--line-1);
  border-radius: var(--r-md);
}

.code-pre code {
  display: block;
  font-family: var(--font-mono);
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--text-2);
  background: transparent;
  white-space: pre;
}

.code-editor {
  flex: 1;
  width: 100%;
  min-width: 0;
  padding: 16px 18px;
  font-family: var(--font-mono);
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--text-1);
  background: var(--ink-1000);
  border: none;
  outline: none;
  resize: none;
  caret-color: var(--amber-400);
  tab-size: 4;
  white-space: pre;
}

.viewer-foot {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-shrink: 0;
  padding: 7px 16px;
  font-size: 11.5px;
  color: var(--amber-300);
  background: var(--amber-a08);
  border-top: 1px solid var(--line-1);
}

.foot-dot {
  width: 5px;
  height: 5px;
  flex-shrink: 0;
  border-radius: 50%;
  background: var(--amber-400);
  box-shadow: 0 0 0 3px var(--amber-a12);
}

.viewer-placeholder {
  flex: 1;
  min-width: 0;
}

/* ===== 新增文件弹窗 ===== */
.modal-mask {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(6, 8, 11, 0.68);
  backdrop-filter: blur(8px);
  animation: fadeIn var(--dur) var(--ease-out);
}

.modal {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 440px;
  max-width: 100%;
  max-height: 86vh;
  padding: 22px;
  overflow-y: auto;
  background: rgba(16, 19, 26, 0.96);
  border: 1px solid var(--line-2);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-3);
  backdrop-filter: blur(18px);
  animation: fadeUp var(--dur) var(--ease-out);
}

.modal-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 650;
  letter-spacing: -0.01em;
  color: var(--text-1);
}

.modal-input {
  width: 100%;
  padding: 9px 11px;
  font-family: var(--font-mono);
  font-size: 12.5px;
  color: var(--text-1);
  background: var(--bg-input);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  outline: none;
  transition: border-color var(--dur-fast), background var(--dur-fast), box-shadow var(--dur-fast);
}

.modal-input::placeholder {
  color: var(--text-4);
}

.modal-input:hover {
  border-color: var(--line-3);
}

.modal-input:focus {
  border-color: var(--amber-a55);
  background: var(--ink-900);
  box-shadow: 0 0 0 3px var(--amber-a12);
}

.modal-hint {
  font-size: 11.5px;
  line-height: 1.65;
  color: var(--text-4);
}

.modal-error {
  font-size: 12px;
  line-height: 1.6;
  color: var(--coral-400);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 4px;
}

.btn-ghost,
.btn-primary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 34px;
  padding: 0 14px;
  font-size: 13px;
  font-weight: 500;
  border-radius: var(--r-sm);
  white-space: nowrap;
  cursor: pointer;
  transition: background var(--dur-fast), border-color var(--dur-fast), color var(--dur-fast),
    filter var(--dur-fast), box-shadow var(--dur-fast);
}

.btn-ghost {
  color: var(--text-2);
  background: transparent;
  border: 1px solid transparent;
}

.btn-ghost:hover {
  color: var(--text-1);
  background: rgba(255, 255, 255, 0.05);
}

.btn-primary {
  color: var(--amber-ink);
  background: var(--amber-grad);
  border: 1px solid transparent;
  font-weight: 650;
  box-shadow: var(--shadow-1), inset 0 1px 0 rgba(255, 255, 255, 0.28);
}

.btn-primary:hover:not(:disabled) {
  filter: brightness(1.06);
  box-shadow: var(--shadow-amber), inset 0 1px 0 rgba(255, 255, 255, 0.3);
}

.btn-primary:disabled {
  opacity: 0.45;
  cursor: default;
}

/* ===== 响应式 ===== */
@media (max-width: 1180px) {
  .sd-tree {
    width: 232px;
    min-width: 188px;
  }

  .md-wrap {
    padding: 24px 28px 32px;
  }
}

@media (max-width: 980px) {
  .sd-page {
    height: calc(100vh - 92px);
  }

  .sd-title {
    font-size: 20px;
  }

  .sd-tree {
    width: 204px;
    min-width: 168px;
  }

  .md-wrap {
    padding: 20px 20px 28px;
  }

  .viewer-path {
    max-width: 44%;
  }
}

@media (max-width: 760px) {
  .sd-page {
    height: auto;
    min-height: calc(100vh - 92px);
  }

  .sd-stats {
    margin-left: 0;
    padding-left: 0;
    border-left: none;
  }

  .sd-body {
    flex-direction: column;
    min-height: 0;
  }

  .sd-tree {
    width: 100%;
    min-width: 0;
    max-height: 220px;
  }

  .sd-viewer {
    min-height: 380px;
  }

  .viewer-head {
    flex-wrap: wrap;
  }

  .viewer-path {
    max-width: 100%;
  }

  .md-wrap {
    padding: 18px 16px 24px;
  }
}
</style>
