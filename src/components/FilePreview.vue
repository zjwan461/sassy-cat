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
  padding: 10px 14px;
  border-bottom: 1px solid var(--line-1);
  background: rgba(0, 0, 0, 0.18);
  max-height: 200px;
  overflow-y: auto;
}

.preview-section {
  margin-bottom: 10px;
}

.preview-section:last-child {
  margin-bottom: 0;
}

.preview-label {
  margin-bottom: 7px;
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--text-4);
}

/* ---------- 图片网格 ---------- */
.image-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.image-item {
  position: relative;
  width: 62px;
  height: 62px;
  border-radius: var(--r-sm);
  overflow: hidden;
  border: 1px solid var(--line-2);
  cursor: zoom-in;
  transition: border-color var(--dur-fast);
}

.image-item:hover {
  border-color: var(--amber-a55);
}

.image-item img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.image-item .remove-btn {
  position: absolute;
  top: 3px;
  right: 3px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 17px;
  height: 17px;
  font-size: 13px;
  line-height: 1;
  color: #fff;
  background: rgba(0, 0, 0, 0.66);
  backdrop-filter: blur(4px);
  border: none;
  border-radius: 50%;
  cursor: pointer;
  opacity: 0;
  transition: opacity var(--dur-fast);
}

.image-item:hover .remove-btn {
  opacity: 1;
}

/* ---------- 文档列表 ---------- */
.doc-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.doc-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  transition: border-color var(--dur-fast);
}

.doc-item.loading {
  border-color: var(--amber-a35);
}

.doc-item.done {
  border-color: rgba(126, 203, 161, 0.35);
}

.doc-item.error {
  border-color: rgba(233, 119, 110, 0.4);
}

.doc-info {
  flex: 1;
  min-width: 0;
}

.doc-name {
  font-size: 12px;
  color: var(--text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.doc-status {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 2px;
  font-size: 10.5px;
}

.status-loading {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--amber-300);
}

.status-loading .spinner {
  display: inline-block;
  width: 9px;
  height: 9px;
  border: 1.5px solid var(--amber-a35);
  border-top-color: var(--amber-400);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.status-done {
  color: var(--jade-400);
}

.status-error {
  color: var(--coral-400);
}

.doc-item .remove-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  font-size: 15px;
  color: var(--text-4);
  background: transparent;
  border: none;
  border-radius: var(--r-xs);
  cursor: pointer;
  transition: background var(--dur-fast), color var(--dur-fast);
}

.doc-item .remove-btn:hover {
  background: rgba(255, 255, 255, 0.07);
  color: var(--text-1);
}

/* ---------- 图片放大预览 ---------- */
.image-modal {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(3, 5, 8, 0.86);
  backdrop-filter: blur(6px);
  cursor: zoom-out;
  animation: fadeIn var(--dur) var(--ease-out);
}

.image-modal img {
  max-width: 90%;
  max-height: 90%;
  border-radius: var(--r-md);
  box-shadow: var(--shadow-3);
}
</style>
