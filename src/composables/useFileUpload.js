/**
 * 文件上传 composable
 * 支持图片（base64）和文档（OCR）两种类型
 */
import { ref, computed } from 'vue'
import { useAgentSocket } from './useAgentSocket'

const { state: socketState } = useAgentSocket()

// 支持的图片类型
const IMAGE_TYPES = new Set(['image/png', 'image/jpeg', 'image/gif', 'image/webp'])
// 图片大小限制 5MB
const MAX_IMAGE_SIZE = 5 * 1024 * 1024
// 文档大小限制 20MB
const MAX_DOC_SIZE = 20 * 1024 * 1024

// 全局状态（模块级单例，与组件生命周期解耦）
const pendingImages = ref([]) // { id, name, data (base64), mimeType, preview }
const pendingDocs = ref([])   // { id, name, markdown, status: 'loading'|'done'|'error', error? }

let idCounter = 0
function genId() { return 'att-' + Date.now() + '-' + (++idCounter) }

/**
 * 读取图片文件为 base64
 */
function readImageAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      // reader.result 格式: data:image/png;base64,xxxxx
      const dataUrl = reader.result
      const commaIndex = dataUrl.indexOf(',')
      const base64Data = dataUrl.slice(commaIndex + 1)
      resolve({
        data: base64Data,
        preview: dataUrl, // 预览用完整 dataUrl
      })
    }
    reader.onerror = () => reject(new Error('读取图片失败'))
    reader.readAsDataURL(file)
  })
}

/**
 * 调用后端 OCR 接口
 */
async function callOcrApi(file) {
  const port = socketState.port
  const formData = new FormData()
  formData.append('file', file)
  
  const response = await fetch(`http://127.0.0.1:${port}/api/ocr`, {
    method: 'POST',
    body: formData,
  })
  
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'OCR 请求失败' }))
    throw new Error(err.detail || `HTTP ${response.status}`)
  }
  
  const result = await response.json()
  return result.markdown || ''
}

/**
 * 处理文件列表
 * @param {FileList|File[]} files 
 */
export async function handleFiles(files) {
  if (!files || !files.length) return
  
  for (const file of files) {
    if (IMAGE_TYPES.has(file.type)) {
      // 图片处理
      if (file.size > MAX_IMAGE_SIZE) {
        console.warn(`图片 ${file.name} 超过 5MB 限制，已跳过`)
        continue
      }
      try {
        const { data, preview } = await readImageAsBase64(file)
        pendingImages.value.push({
          id: genId(),
          name: file.name,
          data,
          mimeType: file.type,
          preview,
        })
      } catch (e) {
        console.error(`处理图片 ${file.name} 失败:`, e)
      }
    } else {
      // 文档处理：调用 OCR
      if (file.size > MAX_DOC_SIZE) {
        console.warn(`文件 ${file.name} 超过 20MB 限制，已跳过`)
        continue
      }
      const docId = genId()
      const docEntry = {
        id: docId,
        name: file.name,
        markdown: '',
        status: 'loading',
      }
      pendingDocs.value.push(docEntry)
      
      try {
        const markdown = await callOcrApi(file)
        docEntry.markdown = markdown
        docEntry.status = 'done'
      } catch (e) {
        docEntry.status = 'error'
        docEntry.error = e.message
        console.error(`OCR 处理 ${file.name} 失败:`, e)
      }
    }
  }
}

/**
 * 移除图片
 */
export function removeImage(id) {
  const idx = pendingImages.value.findIndex(img => img.id === id)
  if (idx !== -1) pendingImages.value.splice(idx, 1)
}

/**
 * 移除文档
 */
export function removeDoc(id) {
  const idx = pendingDocs.value.findIndex(doc => doc.id === id)
  if (idx !== -1) pendingDocs.value.splice(idx, 1)
}

/**
 * 清空所有待发送附件
 */
export function clearAllAttachments() {
  pendingImages.value = []
  pendingDocs.value = []
}

/**
 * 构造 attachments 数组（用于 chat.send）
 * 仅包含已就绪的内容（图片 + 已完成的 OCR 文档）
 */
export function buildAttachments() {
  const attachments = []
  
  // 图片
  for (const img of pendingImages.value) {
    attachments.push({
      type: 'image',
      data: img.data,
      mimeType: img.mimeType,
      name: img.name,
    })
  }
  
  // 文档（仅已完成的）
  for (const doc of pendingDocs.value) {
    if (doc.status === 'done' && doc.markdown) {
      attachments.push({
        type: 'text',
        content: `【文件: ${doc.name}】\n\n${doc.markdown}`,
        name: doc.name,
      })
    }
  }
  
  return attachments
}

/**
 * 是否有待发送的附件
 */
export const hasAttachments = computed(() => 
  pendingImages.value.length > 0 || pendingDocs.value.length > 0
)

/**
 * 是否有正在处理中的文档
 */
export const isProcessing = computed(() =>
  pendingDocs.value.some(doc => doc.status === 'loading')
)

export function useFileUpload() {
  return {
    pendingImages,
    pendingDocs,
    hasAttachments,
    isProcessing,
    handleFiles,
    removeImage,
    removeDoc,
    clearAllAttachments,
    buildAttachments,
  }
}
