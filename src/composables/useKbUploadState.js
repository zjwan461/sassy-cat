/**
 * 知识库文档上传队列（模块级单例）
 * 上传任务独立于组件生命周期：切换 tab 组件卸载后，后台上传继续推进，
 * 悬浮进度条（App.vue 全局渲染）不丢失；处理中的批次再次上传会排队并累计总数。
 */
import { ref, computed } from 'vue'
import { uploadDocument } from '../api/kb'

const uploading = ref(false)
const uploadTotal = ref(0)
const uploadDone = ref(0)
const uploadCurrent = ref('')
// 进度遮罩可见性：点「后台处理」仅隐藏遮罩（遮罩在详情页渲染）
const maskVisible = ref(true)
// 当前批次所属知识库（悬浮条点击时导航回详情页用）
const uploadKbId = ref('')

// 待处理文件队列与失败记录（非响应式：仅循环内部消费）
const queue = []
let running = false
let failed = []

const uploadPercent = computed(() =>
  uploadTotal.value ? Math.round((uploadDone.value / uploadTotal.value) * 100) : 0
)

async function pump() {
  if (running) return
  running = true
  uploading.value = true
  while (queue.length) {
    const { kbId, file } = queue.shift()
    uploadCurrent.value = file.name
    try {
      await uploadDocument(kbId, file)
    } catch (e) {
      failed.push(`${file.name}: ${e.message}`)
    }
    uploadDone.value += 1
  }
  uploadCurrent.value = ''
  uploading.value = false
  running = false
}

/**
 * 把一批文件加入上传队列。
 * 队列空闲时重置计数并重新弹出进度遮罩；处理中则排队、总数累计增加。
 */
function enqueueFiles(kbId, files) {
  if (!files.length) return
  if (!running) {
    uploadTotal.value = 0
    uploadDone.value = 0
    failed = []
    maskVisible.value = true
  }
  uploadKbId.value = kbId
  uploadTotal.value += files.length
  for (const file of files) queue.push({ kbId, file })
  pump()
}

/** 取出并清空失败记录（组件在批次结束后弹窗告警） */
function takeFailed() {
  const list = failed
  failed = []
  return list
}

export function useKbUploadState() {
  return {
    uploading, uploadTotal, uploadDone, uploadCurrent,
    maskVisible, uploadPercent, uploadKbId,
    enqueueFiles, takeFailed,
  }
}
