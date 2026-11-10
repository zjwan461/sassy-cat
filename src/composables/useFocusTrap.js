import { nextTick, onBeforeUnmount, watch } from 'vue'

const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'textarea:not([disabled])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

/**
 * 模态焦点陷阱：打开时聚焦容器内第一个可聚焦元素，Tab/Shift+Tab 在容器内循环，
 * 关闭时把焦点还给打开前的元素。用于命令面板 / 快捷键帮助等浮层。
 */
export function useFocusTrap(rootRef, activeRef) {
  let previous = null
  let bound = false

  function focusables() {
    const root = rootRef.value
    if (!root) return []
    return [...root.querySelectorAll(FOCUSABLE)].filter((el) => el.getClientRects().length > 0)
  }

  function onKeydown(e) {
    if (e.key !== 'Tab') return
    const list = focusables()
    if (!list.length) {
      e.preventDefault()
      return
    }
    const first = list[0]
    const last = list[list.length - 1]
    const active = document.activeElement
    if (e.shiftKey && (active === first || active === rootRef.value || !rootRef.value?.contains(active))) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && active === last) {
      e.preventDefault()
      first.focus()
    }
  }

  function activate() {
    if (bound) return
    previous = document.activeElement
    document.addEventListener('keydown', onKeydown, true)
    bound = true
    nextTick(() => {
      const list = focusables()
      ;(list[0] || rootRef.value)?.focus?.()
    })
  }

  function deactivate() {
    if (!bound) return
    document.removeEventListener('keydown', onKeydown, true)
    bound = false
    if (previous && typeof previous.focus === 'function' && document.contains(previous)) {
      previous.focus()
    }
    previous = null
  }

  watch(
    activeRef,
    (active) => {
      if (active) activate()
      else deactivate()
    },
    { immediate: true }
  )

  onBeforeUnmount(deactivate)
}
