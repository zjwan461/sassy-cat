<template>
  <div v-if="hasAttachments" class="file-preview">
    <!-- 图片预览区 -->
    <div v-if="pendingImages.length" class="preview-section">
      <div class="preview-label">图片 ({{ pendingImages.length }})</div>
      <div class="image-grid">
        <div v-for="img in pendingImages" :key="img.id" class="image-item">
          <img :src="img.preview" :alt="img.name" @click="showImagePreview(img)" />
          <button class="remove-btn" @click="removeImage(img.id)" title="移除">×</button>
        </div>
      </div>
    </div>

    <!-- 文档预览区 -->
    <div v-if="pendingDocs.length" class="preview-section">
      <div class="preview-label">文档 ({{ pendingDocs.length }})</div>
      <div class="doc-list">
        <div v-for="doc in pendingDocs" :key="doc.id" class="doc-item" :class="doc.status">
          <div class="doc-info">
            <div class="doc-name">{{ doc.name }}</div>
            <div class="doc-status">
              <span v-if="doc.status === 'loading'" class="status-loading">
                <span class="spinner"></span>识别中...
              </span>
              <span v-else-if="doc.status === 'done'" class="status-done">✓ 已识别</span>
              <span v-else-if="doc.status === 'error'" class="status-error">✗ {{ doc.error }}</span>
            </div>
          </div>
          <button class="remove-btn" @click="removeDoc(doc.id)" title="移除">×</button>
        </div>
      </div>
    </div>

    <!-- 图片放大预览弹窗 -->
    <div v-if="previewImage" class="image-modal" @click="closeImagePreview">
      <img :src="previewImage.preview" :alt="previewImage.name" />
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useFileUpload } from '../composables/useFileUpload'

const {
  pendingImages,
  pendingDocs,
  hasAttachments,
  removeImage,
  removeDoc,
} = useFileUpload()

const previewImage = ref(null)

function showImagePreview(img) {
  previewImage.value = img
}

function closeImagePreview() {
  previewImage.value = null
}
</script>

<style scoped>
.file-preview {
  padding: 8px 12px;
  border-bottom: 1px solid #334155;
  background: #172033;
  max-height: 200px;
  overflow-y: auto;
}

.preview-section {
  margin-bottom: 8px;
}

.preview-section:last-child {
  margin-bottom: 0;
}

.preview-label {
  font-size: 11px;
  color: #94a3b8;
  margin-bottom: 6px;
  font-weight: 500;
}

/* 图片网格 */
.image-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.image-item {
  position: relative;
  width: 64px;
  height: 64px;
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid #334155;
  cursor: pointer;
  transition: border-color 0.15s;
}

.image-item:hover {
  border-color: #6366f1;
}

.image-item img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.image-item .remove-btn {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.6);
  color: #fff;
  border: none;
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.15s;
}

.image-item:hover .remove-btn {
  opacity: 1;
}

/* 文档列表 */
.doc-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.doc-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 6px;
}

.doc-item.loading {
  border-color: #6366f1;
}

.doc-item.done {
  border-color: #059669;
}

.doc-item.error {
  border-color: #dc2626;
}

.doc-info {
  flex: 1;
  min-width: 0;
}

.doc-name {
  font-size: 12px;
  color: #e2e8f0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.doc-status {
  font-size: 11px;
  margin-top: 2px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.status-loading {
  color: #6366f1;
}

.status-loading .spinner {
  display: inline-block;
  width: 10px;
  height: 10px;
  border: 2px solid #6366f1;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.status-done {
  color: #34d399;
}

.status-error {
  color: #f87171;
}

.doc-item .remove-btn {
  width: 20px;
  height: 20px;
  border-radius: 4px;
  background: transparent;
  color: #64748b;
  border: none;
  font-size: 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s, color 0.15s;
}

.doc-item .remove-btn:hover {
  background: #334155;
  color: #e2e8f0;
}

/* 图片放大预览弹窗 */
.image-modal {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  cursor: pointer;
}

.image-modal img {
  max-width: 90%;
  max-height: 90%;
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
}
</style>
