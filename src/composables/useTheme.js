import { computed, ref } from 'vue'

const STORAGE_KEY = 'sassy.theme'
const media = typeof window !== 'undefined' && window.matchMedia
  ? window.matchMedia('(prefers-color-scheme: dark)')
  : null

function readMode() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved === 'dark' || saved === 'light' || saved === 'system') return saved
  } catch { /* localStorage 不可用时回退 */ }
  return 'dark'
}

const mode = ref(readMode())
const systemDark = ref(media ? media.matches : true)
const resolved = computed(() => (mode.value === 'system' ? (systemDark.value ? 'dark' : 'light') : mode.value))

function apply() {
  document.documentElement.dataset.theme = resolved.value
  document.documentElement.style.colorScheme = resolved.value
}

function setTheme(next) {
  if (next !== 'dark' && next !== 'light' && next !== 'system') return
  mode.value = next
  try { localStorage.setItem(STORAGE_KEY, next) } catch { /* ignore */ }
  apply()
}

function toggleTheme() {
  setTheme(resolved.value === 'light' ? 'dark' : 'light')
}

if (media && media.addEventListener) {
  media.addEventListener('change', (e) => {
    systemDark.value = e.matches
    if (mode.value === 'system') apply()
  })
}

/** 在挂载前调用，避免首帧闪出错误主题 */
export function initTheme() {
  apply()
  return { mode, resolved, setTheme, toggleTheme }
}

export function useTheme() {
  return { mode, resolved, setTheme, toggleTheme }
}
