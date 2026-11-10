<template>
  <div class="page chat-page">
    <header class="page-header">
      <div class="page-head-left">
        <h1 class="page-title">唠嗑</h1>
        <p class="page-subtitle">与本喵说说话，什么都可以聊</p>
      </div>
      <div class="page-head-right">
        <label v-if="llmOptions.length" class="model-picker" title="切换模型：下一条消息生效">
          <AppIcon name="cpu" :size="13" />
          <select
            :value="activeLlmProfile"
            :disabled="switchingModel"
            @change="onSwitchModel($event.target.value)"
          >
            <option v-for="p in llmOptions" :key="p.name" :value="p.name">{{ p.optionLabel }}</option>
          </select>
          <span v-if="modelNotice" class="model-notice" :class="{ bad: modelNotice.error }">{{ modelNotice.text }}</span>
        </label>
        <span class="conn" :class="connClass">
          <span class="conn-dot"></span>{{ connText }}
        </span>
      </div>
    </header>

    <section class="card chat-card">
      <!-- 会话内搜索（Ctrl/Cmd+F） -->
      <div v-if="convSearchOpen" class="conv-search">
        <AppIcon name="search" :size="14" />
        <input
          ref="convSearchInput"
          v-model="convSearchQuery"
          type="text"
          aria-label="在当前对话中搜索"
          placeholder="在当前对话中搜索…"
          @keydown.enter.prevent="nextConvMatch($event.shiftKey)"
          @keydown.esc.prevent="closeConvSearch"
        />
        <span class="conv-search-count">{{ convSearchCount }}</span>
        <button class="conv-search-nav" type="button" title="上一处" :disabled="!convMatches.length" @click="prevConvMatch">↑</button>
        <button class="conv-search-nav" type="button" title="下一处" :disabled="!convMatches.length" @click="nextConvMatch(false)">↓</button>
        <button class="conv-search-close" type="button" title="关闭" @click="closeConvSearch">
          <AppIcon name="x" :size="13" />
        </button>
      </div>

      <!-- 上半区：会话侧栏 + 消息流并排 -->
      <div class="chat-body">
      <!-- 会话侧栏：历史对话列表 + 新建 -->
      <aside class="conv-panel">
        <button class="btn conv-new" @click="onNewConv">
          <AppIcon name="plus" :size="14" />
          <span>新建对话</span>
        </button>
        <!-- 置顶分组：与历史列表分区展示。置顶项数量有限，独立于滚动容器，
             自身超出高度时可单独滚动，不挤占历史列表 -->
        <div v-if="pinnedConvs.length" class="conv-pinned-group">
          <div class="conv-group-title">
            <AppIcon name="pin" :size="11" />
            <span>置顶</span>
          </div>
          <div class="conv-pinned-list">
            <ConversationItem
              v-for="c in pinnedConvs"
              :key="c.id"
              :item="c"
              :active="c.id === chat.convId"
              :editing="editingId === c.id"
              v-model:editingTitle="editingTitle"
              @select="onSwitchConv(c)"
              @rename-start="startRename(c)"
              @rename-commit="commitRename(c)"
              @rename-cancel="cancelRename"
              @delete="onDeleteConv(c)"
              @pin-toggle="onTogglePin(c)"
            />
          </div>
        </div>
        <div v-if="pinnedConvs.length" class="conv-group-title">历史对话</div>
        <div class="conv-list" ref="convListRef" @scroll="onConvListScroll">
          <ConversationItem
            v-for="c in historyConvs"
            :key="c.id"
            :item="c"
            :active="c.id === chat.convId"
            :editing="editingId === c.id"
            v-model:editingTitle="editingTitle"
            @select="onSwitchConv(c)"
            @rename-start="startRename(c)"
            @rename-commit="commitRename(c)"
            @rename-cancel="cancelRename"
            @delete="onDeleteConv(c)"
            @pin-toggle="onTogglePin(c)"
          />
          <!-- 无限滚动加载更多：滚动到底部自动加载，加载中显示转圈 -->
          <div v-if="conv.loadingMore" class="conv-more-hint">
            <span class="conv-spinner"></span> 加载中…
          </div>
          <div v-else-if="conv.hasMore && historyConvs.length" class="conv-more-hint clickable" @click="onLoadMoreConvs">
            加载更多
          </div>
          <div v-if="!conv.list.length && !conv.loading" class="conv-empty">还没有对话</div>
        </div>
      </aside>

      <!-- 消息流 -->
      <div class="msg-list" ref="listRef" @scroll="onMsgListScroll">
        <!-- 加载更多提示 -->
        <div v-if="chat.loadingMore" class="load-more-hint">
          <span class="spinner"></span> 加载中...
        </div>
        <div v-else-if="chat.hasMore && messages.length > 0" class="load-more-hint clickable" @click="onLoadMore">
          加载更多历史消息
        </div>
        <div v-if="messages.length === 0" class="empty-state">
          <div class="empty-mark"><AppIcon name="chat" :size="22" /></div>
          <p class="empty-title">喵？有什么事就说吧</p>
          <p class="empty-sub">本喵听着呢 · 可以粘贴或拖入图片、文档</p>
        </div>
        <div v-for="m in messages" :key="m.id" class="msg" :class="[m.role, { 'search-hit': m.id === convSearchActiveId }]" :data-msg-id="m.id">
          <div class="msg-avatar" :class="m.role">
            <img v-if="isAssistant(m)" :src="logoUrl" alt="" />
            <span v-else>你</span>
          </div>
          <div class="msg-body">
            <!-- 深度思考区域：可折叠，仅在有助手消息且存在 reasoning 内容时显示 -->
            <!-- 有新的思考输出时由状态自动展开（open 单向绑定，需靠 toggle 回收用户的折叠动作） -->
            <details
              v-if="m.reasoning"
              class="reasoning-block"
              :open="m.reasoningOpen"
              @toggle="onReasoningToggle(m, $event)"
            >
              <summary class="reasoning-summary">
                <AppIcon name="brain" :size="14" class="sum-icon" />
                <span>深度思考</span>
                <span v-if="m.thinking" class="thinking-dot">…</span>
                <span class="sum-chevron"><AppIcon name="chevron-right" :size="12" /></span>
              </summary>
              <!-- 深度思考内容限高并支持滚轮滚动；流式期间自动跟随到底部（用户手动上翻后暂停） -->
              <div
                class="reasoning-content"
                :ref="(el) => setReasoningEl(m.id, el)"
                @scroll="onReasoningScroll(m, $event)"
              >{{ m.reasoning }}</div>
            </details>
            <div v-if="m.content || m.images?.length || docAttachments(m).length" class="msg-content" :class="{ 'md-mode': isAssistant(m) }" @click="onContentClick(m, $event)">
              <!-- 用户消息的图片附件 -->
              <div v-if="m.images && m.images.length" class="msg-images">
                <img v-for="(img, i) in m.images" :key="i" :src="img" class="msg-image" @click="openImagePreview(img)" />
              </div>
              <!-- 用户消息的文档附件 -->
              <div v-if="docAttachments(m).length" class="msg-doc-attachments">
                <DocumentAttachment
                  v-for="att in docAttachments(m)"
                  :key="att.id"
                  :attachment="att"
                />
              </div>
              <template v-if="isAssistant(m)">
                <!-- 按来源分段渲染：带 agent 的段落来自子 agent（如 DeepSeek Harness），
                     单独成块并标注来源，与主 agent 的正文区分开 -->
                <template v-if="m.segments && m.segments.length">
                  <div
                    v-for="(seg, i) in m.segments"
                    :key="i"
                    class="msg-segment"
                    :class="{ 'sub-agent': seg.agent }"
                  >
                    <!-- 子 agent 段落：独立嵌套面板 + 头部来源标签，与主 agent 正文明显区分 -->
                    <template v-if="seg.agent">
                      <div class="sub-agent-head">
                        <span class="sub-agent-avatar">🤖</span>
                        <span class="sub-agent-badge">子 Agent</span>
                        <span class="sub-agent-name">{{ agentLabel(seg.agent) }}</span>
                      </div>
                      <div class="sub-agent-body">
                        <MarkdownRenderer :content="seg.text" :done="!m.streaming" @rendered="onMDRendered(m)" />
                      </div>
                    </template>
                    <MarkdownRenderer v-else :content="seg.text" :done="!m.streaming" @rendered="onMDRendered(m)" />
                  </div>
                </template>
                <MarkdownRenderer v-else :content="m.content" :done="!m.streaming" @rendered="onMDRendered(m)" />
              </template>
              <template v-else>{{ m.content }}</template>
            </div>
            <!-- 知识库参考来源：正文 [n] 与这里的 chip 都可点开分块内容 -->
            <div v-if="m.citations?.length" class="kb-cites">
              <span class="kb-cites-title">参考来源</span>
              <button
                v-for="c in m.citations"
                :key="c.index + c.source"
                type="button"
                class="kb-cite-chip"
                :title="c.content.slice(0, 160)"
                @click.stop="openCitation(c)"
              >
                <span class="kb-cite-index">[{{ c.index }}]</span>
                {{ c.source }}
              </button>
            </div>
            <!-- present 工具产出的文件卡片：正文下方、工具步骤上方 -->
            <PresentedFiles v-if="m.presentation" :data="m.presentation" />
            <!-- 操作条：朗读 + 复制按钮（豆包风格图标按钮），助手消息流式期间隐藏 -->
            <div v-if="isAssistant(m) ? (!m.streaming && (m.content || m.reasoning)) : !!m.content" class="msg-actions">
              <button
                v-if="isAssistant(m) && m.content"
                class="action-btn"
                type="button"
                :class="{ speaking: isSpeaking(m) }"
                :title="isSpeaking(m) ? '停止朗读' : '朗读'"
                @click="onSpeak(m)"
              >
                <svg v-if="isSpeaking(m)" class="action-icon speaking" viewBox="0 0 24 24" width="16" height="16" fill="currentColor" stroke="none"><rect x="6" y="6" width="12" height="12" rx="2"></rect></svg>
                <svg v-else class="action-icon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path><path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path></svg>
              </button>
              <button
                class="action-btn"
                type="button"
                :title="m.copied === false ? '复制失败' : '复制'"
                @click="copyMessage(m)"
              >
                <svg v-if="m.copied" class="action-icon copied" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
                <svg v-else class="action-icon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="11" height="11" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
              </button>
            </div>
            <!-- 工具步骤条：放在气泡下方，避免新消息把正文顶走（默认折叠） -->
            <details
              v-if="m.tools && m.tools.length"
              class="tool-steps-wrapper"
              @toggle="onToolStepsToggle(m, $event)"
            >
              <summary class="tool-steps-summary">
                <AppIcon name="wrench" :size="13" class="sum-icon" />
                <span>工具调用</span>
                <span class="sum-count">{{ m.tools.length }}</span>
                <span class="sum-chevron"><AppIcon name="chevron-right" :size="12" /></span>
              </summary>
              <!-- 工具步骤容器限高滚动：尾部有新工具追加时自动跟随到底部（用户手动上翻后暂停） -->
              <div
                class="tool-steps"
                :ref="(el) => setToolStepsEl(m.id, el)"
                @scroll="onToolStepsScroll(m, $event)"
              >
                <div v-for="(t, i) in m.tools" :key="i" class="tool-step">
                  🐟 本喵正在叼小鱼干：<b>{{ t.name }}</b>
                  <span v-if="t.done" class="tool-done" :class="{ failed: t.status === 'error' }">{{ t.status === 'error' ? '✕' : '✓' }}</span>
                  <!-- 参数流式写入期间：限高区域内自动跟随到最新一行（用户手动上翻后暂停，折叠时不滚动） -->
                  <pre
                    v-if="t.args"
                    class="tool-args"
                    :ref="(el) => setToolArgsEl(toolArgKey(m, i), el)"
                    @scroll="onToolArgsScroll(toolArgKey(m, i), $event)"
                  >{{ t.args }}</pre>
                  <!-- 历史回填的工具结果（实时流无 result 字段，自然不显示） -->
                  <details v-if="t.result" class="tool-result">
                    <summary class="tool-result-summary">执行结果</summary>
                    <pre class="tool-result-body">{{ t.result }}</pre>
                  </details>
                </div>
              </div>
            </details>
            <!-- Token 用量统计：来自 agent.usage 事件（仅助手消息，可折叠） -->
            <details v-if="isAssistant(m) && hasUsage(m.usage)" class="usage-block">
              <summary class="usage-summary">
                <AppIcon name="zap" :size="13" class="sum-icon" />
                <span class="usage-title">Token 统计</span>
                <span class="usage-inline">{{ usageSummary(m.usage) }}</span>
                <span class="sum-chevron"><AppIcon name="chevron-right" :size="12" /></span>
              </summary>
              <div class="usage-body">
                <div class="usage-row">
                  <span class="usage-label">输入 tokens</span>
                  <span class="usage-value">{{ fmtTokens(m.usage.input_tokens) }}</span>
                  <span v-if="m.usage.input_token_details" class="usage-detail">
                    <span v-if="m.usage.input_token_details.cache_read != null">缓存读 {{ fmtTokens(m.usage.input_token_details.cache_read) }}</span>
                    <span v-if="m.usage.input_token_details.cache_creation != null">缓存写 {{ fmtTokens(m.usage.input_token_details.cache_creation) }}</span>
                    <span v-if="usageCacheRate(m.usage) != null" class="usage-cache-rate">命中 {{ usageCacheRate(m.usage).toFixed(1) }}%</span>
                  </span>
                </div>
                <div class="usage-row">
                  <span class="usage-label">输出 tokens</span>
                  <span class="usage-value">{{ fmtTokens(m.usage.output_tokens) }}</span>
                  <span v-if="m.usage.output_token_details" class="usage-detail">
                    <span v-if="m.usage.output_token_details.reasoning != null">推理 {{ fmtTokens(m.usage.output_token_details.reasoning) }}</span>
                    <span v-if="m.usage.output_token_details.reasoning_tokens != null">推理 {{ fmtTokens(m.usage.output_token_details.reasoning_tokens) }}</span>
                  </span>
                </div>
                <div class="usage-row usage-total">
                  <span class="usage-label">总计 tokens</span>
                  <span class="usage-value">{{ fmtTokens(m.usage.total_tokens) }}</span>
                </div>
              </div>
            </details>
            <!-- interrupt 确认（存在待确认项时自动展开；全部处理完则折叠并切换为已完成文案）
                 展示层只渲染待确认项：已决策过的项直接隐藏，不再重复出现；
                 但 interruptDecisions 仍是与 actions 等长的全量数组，
                 发送 tool.confirm 时依旧带上所有结果（含历史轮次），避免服务端错位 -->
            <details v-if="m.interruptActions?.length" class="interrupt-bar-wrapper" :open="hasPendingDecisions(m)">
              <summary class="interrupt-bar-summary">
                {{ hasPendingDecisions(m) ? '⚠️ 需要高危操作确认，请核对参数：' : `📋 高危操作确认（共 ${m.interruptActions.length} 项已全部处理）` }}
                <span class="interrupt-bar-arrow">▶</span>
              </summary>
              <div class="interrupt-bar">
                <div class="interrupt-global-btns" v-if="hasPendingDecisions(m)">
                  <button class="btn approve-all" @click="onApproveAll(m.id)">✅ 全部允许</button>
                </div>
                <!-- pendingActions 只返回未决策项，并携带原始索引 i：决策写回的位置必须与 actions 对齐 -->
                <div v-for="{ a, i } in pendingActions(m)" :key="i" class="interrupt-action">
                  <div class="interrupt-action-header">
                    <span class="interrupt-action-index">#{{ i + 1 }}</span>
                    <span class="interrupt-action-name">{{ a.name }}</span>
                  </div>
                  <pre class="interrupt-action-args">{{ a.argsText }}</pre>
                  <div class="interrupt-action-btns">
                    <button class="btn-sm approve" @click="onDecision(m.id, i, 'approve')">允许</button>
                    <button class="btn-sm reject" @click="onDecision(m.id, i, 'reject')">拒绝</button>
                  </div>
                </div>
                <div v-if="!hasPendingDecisions(m)" class="interrupt-hint">✅ 共 {{ m.interruptActions.length }} 项高危操作已全部处理。</div>
                <div v-else-if="decidedCount(m)" class="interrupt-hint">已处理的 {{ decidedCount(m) }} 项已隐藏，仅展示待确认项。</div>
                <div v-if="!m.interruptActions?.length" class="interrupt-fallback">{{ summarizeInterrupt(m.interrupt) }}</div>
              </div>
            </details>
            <!-- 确认卡失效提示：用户在确认前发送了新消息，服务端以 respond 决策跳过挂起操作并续跑新消息 -->
            <div v-if="m.interruptExpired" class="interrupt-expired">⏹ 新消息已发送，未确认的操作已跳过</div>
            <div v-if="m.error" class="msg-error">
              <span class="msg-error-text">{{ m.error }}</span>
              <button class="msg-retry-btn" type="button" :disabled="m.streaming" @click="onRetry(m)">重试</button>
            </div>
            <!-- 光标：放在 msg-body 末尾，确保出现在所有内容（包括工具步骤和中断确认）之后 -->
            <span v-if="m.streaming" class="cursor cursor-at-end">▌</span>
          </div>
        </div>
      </div>

      <!-- 回到底部浮动按钮：用户手动上翻时出现，点击/自行滚回底部即消失 -->
      <button v-if="!stickToBottom" class="back-to-bottom" @click="onBackToBottom" title="回到底部">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>
      </button>
      </div>

      <!-- 输入区：永远固定在卡片最底部，横跨整宽 -->
      <div 
        class="input-area"
        :class="{ 'drag-over': isDragOver }"
        @dragover.prevent="onDragOver"
        @dragleave="onDragLeave"
        @drop.prevent="onDrop"
      >
        <!-- 文件预览区 -->
        <FilePreview v-if="hasAttachments" />
        
        <div class="input-bar">
          <input 
            ref="fileInputRef"
            type="file" 
            multiple 
            style="display: none"
            @change="onFileSelect"
          />
          <div class="composer-stack">
            <!-- 生成中收到的消息默认排队；可直接插队或移除 -->
            <div v-if="chat.queued.length" class="queue-panel">
              <div class="queue-head">
                <span class="queue-title">
                  <AppIcon name="clock" :size="12" />
                  排队中 · {{ chat.queued.length }}
                </span>
                <span class="queue-sub">本轮结束后自动发送</span>
              </div>
              <div v-for="(q, i) in chat.queued" :key="q.id" class="queue-item">
                <span class="queue-index">{{ i + 1 }}</span>
                <div class="queue-main">
                  <div class="queue-text" :title="q.text">{{ q.text || '（附件）' }}</div>
                  <div v-if="q.attachments?.length" class="queue-meta">
                    <AppIcon name="paperclip" :size="11" />
                    {{ q.attachments.length }} 个附件
                  </div>
                </div>
                <button
                  class="queue-act send-now"
                  type="button"
                  title="插队发送：中断当前回复，立刻发送这条"
                  @click="sendQueuedNow(q.id)"
                >
                  <AppIcon name="zap" :size="12" />
                  <span>插队</span>
                </button>
                <button class="queue-act remove" type="button" title="移除" @click="removeQueuedMessage(q.id)">
                  <AppIcon name="x" :size="12" />
                </button>
              </div>
            </div>

            <!-- 一体化书写区：正文在上、工具条在下，视觉上是一个整体 -->
            <div class="composer" :class="{ focused: composerFocused }">
              <textarea
                v-model="draft"
                class="chat-input"
                rows="2"
                :placeholder="generating ? '输入将加入队列…' : '说点什么…'"
                @focus="composerFocused = true"
                @blur="composerFocused = false"
                @keydown.enter.exact.prevent="submit"
                @paste="onPaste"
              ></textarea>
              <div class="composer-tools">
                <button class="attach-btn" @click="triggerFileInput" title="上传图片或文件">
                  <AppIcon name="paperclip" :size="15" />
                  <span>附件</span>
                </button>
                <span class="composer-hint">
                  {{ generating ? '本轮输出中 · 发送会排队，可用插队立即发送' : 'Enter 发送 · Shift + Enter 换行' }}
                </span>
                <button
                  class="btn send"
                  :class="{ queue: generating }"
                  :disabled="(!draft.trim() && !hasAttachments) || isProcessing"
                  @click="submit"
                >
                  <AppIcon :name="generating ? 'clock' : 'arrow-up'" :size="14" />
                  <span>{{ generating ? '排队' : '发送' }}</span>
                </button>
                <button v-if="generating" class="btn stop" @click="stopGen">
                  <AppIcon name="stop" :size="12" />
                  <span>停止</span>
                </button>
              </div>
            </div>
          </div>
        </div>
        
        <!-- 拖拽提示遮罩 -->
        <div v-if="isDragOver" class="drag-overlay">
          <div class="drag-hint"> 松开以上传文件</div>
        </div>
      </div>

      <!-- 消息图片放大预览弹窗 -->
      <div v-if="previewImageUrl" class="image-modal" @click="closeImagePreview">
        <img :src="previewImageUrl" class="image-modal-img" />
      </div>

      <!-- 知识库引用分块预览 -->
      <div v-if="citationView" class="citation-modal" @click.self="citationView = null">
        <div class="citation-panel">
          <div class="citation-head">
            <span class="citation-index">[{{ citationView.index }}]</span>
            <span class="citation-source" :title="citationView.source">{{ citationView.source }}</span>
            <button class="citation-close" type="button" title="关闭" @click="citationView = null">
              <AppIcon name="x" :size="14" />
            </button>
          </div>
          <pre class="citation-body">{{ citationView.content }}</pre>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useChatStore } from '../composables/useChatStore'
import { useAgentSocket } from '../composables/useAgentSocket'
import { useFileUpload } from '../composables/useFileUpload'
import { useTTS } from '../composables/useTTS'
import MarkdownRenderer from '../components/MarkdownRenderer.vue'
import PresentedFiles from '../components/PresentedFiles.vue'
import FilePreview from '../components/FilePreview.vue'
import DocumentAttachment from '../components/DocumentAttachment.vue'
import ConversationItem from '../components/ConversationItem.vue'
import AppIcon from '../components/AppIcon.vue'
// 助手头像用真实品牌图标（黑猫），比 emoji 更统一、更像「一个产品」
import logoUrl from '../../assets/icon.png'

// 会话状态与 WS 事件订阅已提升到模块级单例（useChatStore）：
// 切换 tab 导致本组件卸载时，流式数据仍在后台接收与累积；
// 重新挂载直接恢复现场继续渲染，不再出现"切走就停止渲染"的问题。
const { chat, conv, pinnedConvs, historyConvs, socketState, submitMessage, stopGeneration, retryLastTurn, decideInterrupt, approveAllInterrupt, sendQueuedNow, removeQueuedMessage, newConversation, switchConversation, renameConversation, deleteConversation, setConversationPinned, loadMoreConversations, loadMoreMessages } = useChatStore()
const { hasAttachments, isProcessing, handleFiles, buildAttachments, clearAllAttachments } = useFileUpload()
// 语音朗读（TTS）：播放状态（模块级，跨 tab 存活）+ 播放/停止/切换
const { speaking, playMessage, loadConfig: loadTtsConfig } = useTTS()

// ---------- 聊天页模型切换 ----------
// 模型配置存在 config.user.json 的 llm.profiles 里，切换只改 activeProfile：
// 1) 经 Electron IPC 落盘；2) 通过 WS 通知 Python 热重建 agent；3) 下一条消息生效。
const { send: sendSocket } = useAgentSocket()
const llmOptions = ref([])
const activeLlmProfile = ref('')
const switchingModel = ref(false)
const modelNotice = ref(null)
let modelNoticeTimer = null
let offConfigChanged = null

function optionLabel(name, profile) {
  const label = profile?.label || name
  return profile?.model ? `${label} · ${profile.model}` : label
}

async function loadLlmProfiles() {
  const api = window.electronAPI
  if (!api?.getConfig) return
  try {
    const res = await api.getConfig()
    if (!res.success) return
    const llm = res.config?.llm || {}
    const profiles = llm.profiles || {}
    llmOptions.value = Object.entries(profiles).map(([name, p]) => ({
      name,
      model: p?.model || '',
      optionLabel: optionLabel(name, p),
    }))
    activeLlmProfile.value = llm.activeProfile || 'default'
  } catch {
    // 配置读取失败不影响聊天，隐藏选择器即可
    llmOptions.value = []
  }
}

function flashModelNotice(text, error = false) {
  modelNotice.value = { text, error }
  clearTimeout(modelNoticeTimer)
  modelNoticeTimer = setTimeout(() => { modelNotice.value = null }, 2800)
}

async function onSwitchModel(name) {
  if (!name || name === activeLlmProfile.value || switchingModel.value) return
  const api = window.electronAPI
  if (!api?.setConfig) return
  switchingModel.value = true
  try {
    const res = await api.setConfig('llm.activeProfile', name)
    if (!res.success) {
      flashModelNotice('切换失败：' + (res.message || '未知错误'), true)
      return
    }
    activeLlmProfile.value = name
    // Python 侧 reload_config + holder.invalidate：下一轮用新模型重建 agent
    sendSocket('config.invalidate', { paths: ['llm'] })
    flashModelNotice('已切换，下一条消息生效')
  } finally {
    switchingModel.value = false
  }
}

// 当前激活会话的消息列表（chat 为多会话视图代理，切换会话时底层数组引用会变化，
// 故用 computed 让模板/监听始终读取最新引用）
const messages = computed(() => chat.messages)
const draft = ref('')
const generating = computed(() => chat.generating)
const listRef = ref(null)
const convListRef = ref(null)
const fileInputRef = ref(null)
const isDragOver = ref(false)
const composerFocused = ref(false)
const previewImageUrl = ref(null)
const citationView = ref(null)

// ---------- 会话内搜索（Ctrl/Cmd + F） ----------
const convSearchOpen = ref(false)
const convSearchQuery = ref('')
const convSearchInput = ref(null)
const convSearchIndex = ref(0)

function messageSearchText(m) {
  const parts = [m.content || '']
  for (const t of m.tools || []) {
    if (t.args) parts.push(t.args)
    if (t.result) parts.push(t.result)
  }
  return parts.join('\n')
}

const convMatches = computed(() => {
  const q = convSearchQuery.value.trim().toLowerCase()
  if (!q) return []
  return messages.value
    .filter((m) => messageSearchText(m).toLowerCase().includes(q))
    .map((m) => m.id)
})

const convSearchActiveId = computed(() => convMatches.value[convSearchIndex.value] || null)
const convSearchCount = computed(() =>
  convMatches.value.length ? `${convSearchIndex.value + 1} / ${convMatches.value.length}` : '0 / 0'
)

async function scrollToConvMatch() {
  await nextTick()
  const id = convSearchActiveId.value
  const list = listRef.value
  if (!id || !list) return
  const el = list.querySelector(`[data-msg-id="${CSS.escape(String(id))}"]`)
  if (el) el.scrollIntoView({ block: 'center', behavior: 'smooth' })
  stickToBottom.value = false
}

function nextConvMatch(reverse = false) {
  const total = convMatches.value.length
  if (!total) return
  convSearchIndex.value = reverse
    ? (convSearchIndex.value - 1 + total) % total
    : (convSearchIndex.value + 1) % total
  scrollToConvMatch()
}

function prevConvMatch() {
  nextConvMatch(true)
}

function openConvSearch() {
  convSearchOpen.value = true
  convSearchIndex.value = 0
  nextTick(() => convSearchInput.value?.focus())
}

function closeConvSearch() {
  convSearchOpen.value = false
  convSearchQuery.value = ''
  convSearchIndex.value = 0
}

function onConvSearchHotkey(e) {
  if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === 'f') {
    e.preventDefault()
    if (convSearchOpen.value) closeConvSearch()
    else openConvSearch()
  }
}

watch(convSearchQuery, () => {
  convSearchIndex.value = 0
  scrollToConvMatch()
})

watch(convMatches, (list) => {
  if (convSearchIndex.value >= list.length) {
    convSearchIndex.value = Math.max(0, list.length - 1)
  }
})

// 是否紧贴底部：用户手动上翻看历史时置 false（暂停自动滚动并显示浮动按钮），重新到达底部或点击按钮后恢复 true
const stickToBottom = ref(true)

// 是否已滚动到接近底部（80px 阈值内视为贴底）
function isNearBottom() {
  const el = listRef.value
  if (!el) return true
  return el.scrollHeight - el.scrollTop - el.clientHeight < 80
}

// 强制滚动到底部并恢复自动跟随（用户主动操作：发消息/切会话/确认/点击浮动按钮）
function forceScrollBottom() {
  stickToBottom.value = true
  reasoningUnpinned.clear()
  nextTick(scrollListToBottom)
}

function openImagePreview(url) {
  previewImageUrl.value = url
}

function closeImagePreview() {
  previewImageUrl.value = null
}

// ---------- 会话侧栏 ----------
// 重命名态：同一时刻只允许一条会话处于编辑态，故标题草稿由父组件统一持有，
// 通过 v-model:editingTitle 透传给对应的 ConversationItem
const editingId = ref(null)
const editingTitle = ref('')

function onNewConv() {
  newConversation()
}

function onSwitchConv(c) {
  if (c.id === chat.convId) return
  switchConversation(c.id)
  forceScrollBottom()
}

function startRename(c) {
  editingId.value = c.id
  editingTitle.value = c.title || ''
}

function cancelRename() {
  editingId.value = null
  editingTitle.value = ''
}

function commitRename(c) {
  if (editingId.value !== c.id) return
  const title = editingTitle.value.trim()
  editingId.value = null
  if (title && title !== c.title) renameConversation(c.id, title)
}

function onDeleteConv(c) {
  if (!window.confirm(`删除对话「${c.title || '新对话'}」？消息记录仍会保留在本地。`)) return
  deleteConversation(c.id)
}

// 置顶 / 取消置顶：服务端持久化并广播列表刷新（置顶分组随后自动重排）
function onTogglePin(c) {
  setConversationPinned(c.id, !c.pinned)
}

// ---------- 会话列表无限滚动 ----------
// 滚动到底部附近时自动加载下一页（阈值 40px）
function onConvListScroll() {
  const el = convListRef.value
  if (!el) return
  const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40
  if (nearBottom) loadMoreConversations()
}

// 底部"加载更多"点击兜底：容器内容不足无法滚动时仍能手动触发
function onLoadMoreConvs() {
  loadMoreConversations()
}

// 历史列表长度变化后，若容器内容不足以产生滚动条（无法触发 scroll 事件），主动补拉下一页
// （监听 historyConvs 而非 conv.list：滚动容器只渲染历史分组，置顶项不计入其内容高度）
watch(
  () => historyConvs.value.length,
  () => {
    nextTick(() => {
      const el = convListRef.value
      if (!el || !conv.hasMore || conv.loadingMore) return
      if (el.scrollHeight <= el.clientHeight) loadMoreConversations()
    })
  }
)

const connText = computed(() => ({ open: '已连接', connecting: '连接中…', reconnecting: '重连中…', closed: '未连接' }[socketState.status] || '未连接'))
const connClass = computed(() => socketState.status === 'open' ? 'online' : 'offline')

// 上一次程序化滚动后的 scrollTop：onMsgListScroll 据此识别"自己触发的滚动"，
// 避免把自动贴底误判为用户上翻而错误地暂停自动跟随
let expectedScrollTop = -1

// 立即贴底（同步执行，必须在 DOM 更新之后调用）
function scrollListToBottom() {
  const el = listRef.value
  if (!el) return
  el.scrollTop = el.scrollHeight
  expectedScrollTop = el.scrollTop
}

// 由 MarkdownRenderer 的 rendered 事件驱动：此刻本帧 DOM 已更新、浏览器尚未绘制，
// 在同一帧内贴底，不会出现"先滚到底、内容随后长高"的抖动
function onMDRendered(m) {
  if (stickToBottom.value) scrollListToBottom()
  if (m) enhanceCitations(m)
}

// 把正文里对应参考来源的 [n] 包成可点击的 <a.cite-ref>
function enhanceCitations(m) {
  if (!m?.citations?.length || !m.id) return
  const root = document.querySelector(`[data-msg-id="${CSS.escape(String(m.id))}"]`)
  if (!root) return
  const known = new Set(m.citations.map((c) => c.index))
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      if (!node.nodeValue || !node.nodeValue.includes('[')) return NodeFilter.FILTER_REJECT
      const parent = node.parentElement
      if (!parent || parent.closest('pre, code, a')) return NodeFilter.FILTER_REJECT
      return NodeFilter.FILTER_ACCEPT
    },
  })
  const nodes = []
  while (walker.nextNode()) nodes.push(walker.currentNode)

  for (const node of nodes) {
    const text = node.nodeValue
    const re = /\[(\d+)\]/g
    let match
    let last = 0
    let fragment = null
    while ((match = re.exec(text)) !== null) {
      const index = Number(match[1])
      if (!known.has(index)) continue
      if (!fragment) fragment = document.createDocumentFragment()
      if (match.index > last) fragment.appendChild(document.createTextNode(text.slice(last, match.index)))
      const link = document.createElement('a')
      link.href = '#'
      link.className = 'cite-ref'
      link.dataset.cite = String(index)
      link.textContent = match[0]
      fragment.appendChild(link)
      last = match.index + match[0].length
    }
    if (fragment) {
      if (last < text.length) fragment.appendChild(document.createTextNode(text.slice(last)))
      node.parentNode.replaceChild(fragment, node)
    }
  }
}

function openCitation(citation) {
  if (!citation) return
  citationView.value = {
    index: citation.index,
    source: citation.source,
    content: citation.content,
  }
}

function onContentClick(m, event) {
  const link = event.target.closest?.('.cite-ref')
  if (!link) return
  event.preventDefault()
  const index = Number(link.dataset.cite)
  const citation = (m.citations || []).find((c) => c.index === index)
  if (citation) openCitation(citation)
}

function scrollBottom() {
  nextTick(() => {
    // 仅在用户未上翻时自动跟随到底部；用户手动上翻后不再强制滚动
    if (stickToBottom.value) scrollListToBottom()
  })
}

// ---------- 深度思考区域：内部滚轮滚动状态 ----------
// 每条消息的深度思考内容 DOM（限高后可滚动），用于流式期间自动跟随到底部
const reasoningEls = new Map()
// 用户手动上翻过的消息 id：暂停自动跟随，回到底部后恢复
const reasoningUnpinned = new Set()

function setReasoningEl(id, el) {
  if (el) reasoningEls.set(id, el)
  else reasoningEls.delete(id)
}

function isReasoningNearBottom(el) {
  return el.scrollHeight - el.scrollTop - el.clientHeight < 40
}

function onReasoningScroll(m, e) {
  if (isReasoningNearBottom(e.target)) reasoningUnpinned.delete(m.id)
  else reasoningUnpinned.add(m.id)
}

// 让某条消息的深度思考内容滚到最新处（用户手动上翻过的消息默认不强制，除非 force）
function scrollReasoningToBottom(id, force = false) {
  if (!force && reasoningUnpinned.has(id)) return
  const el = reasoningEls.get(id)
  if (el) el.scrollTop = el.scrollHeight
}

// <details> 的 open 只是单向绑定：用户手动折叠的 DOM 状态必须写回 m.reasoningOpen，
// 否则状态恒为 true 时再次置 true 不产生变更，"有新思考就自动展开"会失效
function onReasoningToggle(m, e) {
  const open = e.target.open
  if (m.reasoningOpen !== open) m.reasoningOpen = open
  // 展开瞬间直接定位到最新内容（此时元素刚变为可见，需等 DOM 更新完成）
  if (open) {
    reasoningUnpinned.delete(m.id)
    nextTick(() => scrollReasoningToBottom(m.id, true))
  }
}

// 流式思考中：让限高的深度思考区域自动滚到最新内容
function followReasoning() {
  for (const m of messages.value) {
    if (!m.thinking) continue
    scrollReasoningToBottom(m.id)
  }
}

// ---------- 工具参数区域：内部滚轮滚动状态 ----------
// 各工具步骤的参数块 DOM（限高后可滚动），key = `${msgId}:${步骤下标}`
const toolArgsEls = new Map()
// 用户手动上翻过的参数块：暂停自动跟随，回到底部后恢复
const toolArgsUnpinned = new Set()

function toolArgKey(m, i) {
  return `${m.id}:${i}`
}

function setToolArgsEl(key, el) {
  if (el) toolArgsEls.set(key, el)
  else toolArgsEls.delete(key)
}

function onToolArgsScroll(key, e) {
  const el = e.target
  if (el.scrollHeight - el.scrollTop - el.clientHeight < 40) toolArgsUnpinned.delete(key)
  else toolArgsUnpinned.add(key)
}

// 让某个工具参数块滚到最新一行：用户手动上翻过的默认不强制（force 时强制），
// 折叠状态（未渲染，clientHeight 为 0）时不滚动
function scrollToolArgsToBottom(key, force = false) {
  if (!force && toolArgsUnpinned.has(key)) return
  const el = toolArgsEls.get(key)
  if (!el || el.clientHeight === 0) return
  el.scrollTop = el.scrollHeight
}

// 参数仍在流式写入：把该步骤的参数块自动滚到最新，能实时看到正在写入的内容
// （只跟随最后一个未完成步骤，已完成步骤保留用户自己的阅读位置）
function followToolArgs() {
  for (const m of messages.value) {
    if (!m.tools || !m.tools.length) continue
    for (let i = m.tools.length - 1; i >= 0; i--) {
      if (m.tools[i].done) continue
      scrollToolArgsToBottom(toolArgKey(m, i))
      break
    }
  }
}

// ---------- 工具步骤条容器：整体限高后的内部滚动状态 ----------
// 各消息的工具步骤条滚动容器 DOM（限高后步骤多时可整条滚动），key = 消息 id
const toolStepsEls = new Map()
// 用户手动上翻过的步骤条：暂停自动跟随，回到底部后恢复
const toolStepsUnpinned = new Set()

function setToolStepsEl(id, el) {
  if (el) toolStepsEls.set(id, el)
  else toolStepsEls.delete(id)
}

function onToolStepsScroll(m, e) {
  const el = e.target
  if (el.scrollHeight - el.scrollTop - el.clientHeight < 40) toolStepsUnpinned.delete(m.id)
  else toolStepsUnpinned.add(m.id)
}

// 让步骤条滚到最新追加的步骤处：用户手动上翻过的默认不强制（force 时强制），
// 折叠状态（未渲染，clientHeight 为 0）时不滚动
function scrollToolStepsToBottom(id, force = false) {
  if (!force && toolStepsUnpinned.has(id)) return
  const el = toolStepsEls.get(id)
  if (!el || el.clientHeight === 0) return
  el.scrollTop = el.scrollHeight
}

// 新工具调用持续追加：把步骤条自动滚到最新一条，避免被限高区域挡在视野之外
// （只跟随最后一个未完成步骤所在的消息，已完成消息保留用户的阅读位置）
function followToolSteps() {
  for (const m of messages.value) {
    if (!m.tools || !m.tools.length) continue
    if (m.tools[m.tools.length - 1].done) continue
    scrollToolStepsToBottom(m.id)
  }
}

// 展开工具步骤条时，直接把参数块与步骤条定位到最新写入位置
function onToolStepsToggle(m, e) {
  if (!e.target.open || !m.tools) return
  nextTick(() => {
    toolStepsUnpinned.delete(m.id)
    scrollToolStepsToBottom(m.id, true)
    m.tools.forEach((t, i) => {
      const key = toolArgKey(m, i)
      toolArgsUnpinned.delete(key)
      scrollToolArgsToBottom(key, true)
    })
  })
}

// 浮动按钮点击：回到底部并恢复自动滚动
function onBackToBottom() {
  forceScrollBottom()
}

// 本消息工具参数已写入的字符数：参数流式增量不改变 content/reasoning，
// 需单独计入才能触发下方的跟随滚动
function toolArgsLength(m) {
  return (m.tools || []).reduce((n, t) => n + (t.args?.length || 0), 0)
}

// 流式内容（正文/思考/工具参数/工具步骤条数量）变化时自动滚动到底部（仅在本组件挂载期间生效）
watch(
  () => messages.value.reduce(
    (n, m) => n + (m.content?.length || 0) + (m.reasoning?.length || 0) + toolArgsLength(m) + (m.tools?.length || 0),
    0
  ),
  () => {
    scrollBottom()
    nextTick(() => {
      followReasoning()
      followToolArgs()
      followToolSteps()
    })
  }
)

function isAssistant(m) {
  return m.role === 'assistant'
}

// 子 agent 来源标识：来自后端 chat.delta 帧的 agent 字段（dsh 工具经 runner 的
// custom 分支带出），仅用于展示文案，未知来源回退为原样显示 id
const SUB_AGENT_LABELS = { dsh: 'DeepSeek Harness' }

function agentLabel(id) {
  return SUB_AGENT_LABELS[id] || id
}

// ---------- 语音朗读（TTS） ----------
// 当前消息是否正在朗读（播放中按钮高亮为停止图标）
function isSpeaking(m) {
  return speaking.value === m.id
}

// 点击朗读按钮：播放/停止/切换（由 useTTS.playMessage 裁决）
function onSpeak(m) {
  if (!m.content) return
  playMessage(m.id, m.content)
}

// 复制助手消息：包含深度思考内容 + 正文
let copyTimer = null
async function copyMessage(m) {
  const parts = []
  if (m.reasoning) parts.push('【深度思考】\n' + m.reasoning)
  if (m.content) parts.push(m.content)
  const text = parts.join('\n\n')
  if (!text) return
  let ok = false
  try {
    await navigator.clipboard.writeText(text)
    ok = true
  } catch {
    // clipboard API 不可用时回退
    try {
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      ok = document.execCommand('copy')
      document.body.removeChild(ta)
    } catch { ok = false }
  }
  if (ok) {
    m.copied = true
    clearTimeout(copyTimer)
    copyTimer = setTimeout(() => { m.copied = false }, 1500)
  } else {
    m.copied = false
    setTimeout(() => { m.copied = undefined }, 1500)
  }
}

function summarizeInterrupt(payload) {
  try {
    const actions = payload?.actions || []
    const names = actions.flatMap(a => (a?.action_requests || []).map(r => r.name))
    return names.length ? names.join(', ') : JSON.stringify(actions).slice(0, 120)
  } catch { return '未知操作' }
}

// ---------- Token 用量统计（agent.usage） ----------
// usage_metadata 缺失部分字段（如纯缓存读、无推理 token）时只显示已有的，兼容多种模型返回
function hasUsage(u) {
  return !!u && (u.total_tokens != null || u.input_tokens != null || u.output_tokens != null)
}
function fmtTokens(n) {
  return n == null ? '0' : Number(n).toLocaleString()
}
function usageSummary(u) {
  if (!u) return ''
  const parts = []
  if (u.total_tokens != null) parts.push(`总计 ${fmtTokens(u.total_tokens)}`)
  if (u.input_tokens != null) parts.push(`输入 ${fmtTokens(u.input_tokens)}`)
  if (u.output_tokens != null) parts.push(`输出 ${fmtTokens(u.output_tokens)}`)
  return parts.join(' · ')
}

// 缓存命中率：命中读取（cache_read）的 token 占输入 token 的比例
function usageCacheRate(u) {
  if (!u) return null
  const inp = u.input_tokens
  const read = u.input_token_details?.cache_read
  if (inp == null || read == null || inp <= 0) return null
  return Math.min(100, (read / inp) * 100)
}

// 统一决策记录的形态差异：
// - 本地实时点击存的是字符串（'approve' | 'reject'）
// - 数据库历史回填的是对象（{ type: 'approve' }），且 JSON 序列化后
//   未决策项可能为 null；decisions 数组还可能短于 actions（服务端把
//   多轮 interrupt 的 actions 累积到同一条消息，decisions 只含已确认部分）
function decisionType(m, i) {
  const d = m.interruptDecisions?.[i]
  if (!d) return null
  return (typeof d === 'string' ? d : d.type) || null
}

// 判断消息是否还有未确认的操作（以 actions 长度为基准逐项检查，
// 避免 decisions 数组偏短时漏判新增的待确认项）
function hasPendingDecisions(m) {
  if (!m.interruptActions || !m.interruptActions.length) return false
  return m.interruptActions.some((_, i) => !decisionType(m, i))
}

// 待确认（尚未决策）的操作列表：模板只渲染这些项，已决策项隐藏不再展示。
// 注意保留原始索引 i —— onDecision 按 actions 的下标写回 interruptDecisions，
// 而 interruptDecisions 全量保留（发送 tool.confirm 时带全部结果），两者必须对齐。
function pendingActions(m) {
  if (!m.interruptActions?.length) return []
  return m.interruptActions
    .map((a, i) => ({ a, i }))
    .filter(({ i }) => !decisionType(m, i))
}

// 已决策项数量：用于提示"已隐藏 N 项"，让用户知道列表为何变短
function decidedCount(m) {
  if (!m.interruptActions?.length) return 0
  return m.interruptActions.filter((_, i) => decisionType(m, i)).length
}

// 单个操作的确认/拒绝
function onDecision(msgId, index, decision) {
  decideInterrupt(msgId, index, decision)
  forceScrollBottom()
}

// 全部允许
function onApproveAll(msgId) {
  approveAllInterrupt(msgId)
  forceScrollBottom()
}

// ---------- 文件上传相关 ----------
function triggerFileInput() {
  fileInputRef.value?.click()
}

function onFileSelect(e) {
  const files = e.target.files
  if (files && files.length) {
    handleFiles(Array.from(files))
  }
  // 清空 input 值，允许重复选择同一文件
  e.target.value = ''
}

function onDragOver(e) {
  isDragOver.value = true
}

function onDragLeave(e) {
  // 只有当离开目标元素时才隐藏（避免子元素触发）
  if (e.currentTarget === e.target) {
    isDragOver.value = false
  }
}

function onDrop(e) {
  isDragOver.value = false
  const files = e.dataTransfer?.files
  if (files && files.length) {
    handleFiles(Array.from(files))
  }
}

function onPaste(e) {
  const items = e.clipboardData?.items
  if (!items) return
  
  const files = []
  for (const item of items) {
    if (item.kind === 'file') {
      const file = item.getAsFile()
      if (file) files.push(file)
    }
  }
  
  if (files.length) {
    e.preventDefault()
    handleFiles(files)
  }
}

function submit() {
  const text = draft.value.trim()
  const attachments = buildAttachments()
  
  // 没有文本也没有附件时不发送
  if (!text && !attachments.length) return
  
  draft.value = ''
  submitMessage(text, attachments)
  clearAllAttachments()
  forceScrollBottom()
}

function stopGen() {
  stopGeneration()
}

// 重试上一轮失败的生成（是否重试由用户决定）；重试后滚到底部跟随新内容
function onRetry(m) {
  retryLastTurn(m.id)
  forceScrollBottom()
}

// ---------- 文档附件提取 ----------
function docAttachments(m) {
  if (!m.attachments) return []
  return m.attachments.filter(a => a.type === 'document')
}

// ---------- 滚动加载更多历史消息 ----------
function onMsgListScroll() {
  if (!listRef.value) return
  const { scrollTop } = listRef.value
  // 当滚动到顶部附近（50px 以内）时触发加载；空会话/首屏加载中不触发，
  // 否则会跳过第一页直接请求 page+1
  if (scrollTop < 50 && chat.hasMore && !chat.loadingMore && chat.messages.length > 0) {
    onLoadMore()
  }
  // 程序化贴底产生的 scroll 事件不代表用户意图，直接忽略；
  // 否则流式期间每帧的自动贴底都会把状态改写成"贴底"，用户上翻的意图会被吞掉
  if (Math.abs(scrollTop - expectedScrollTop) < 1) return
  // 同步"是否贴底"状态：用户手动上翻 → 暂停自动跟随并显示浮动按钮；滚回底部 → 恢复自动跟随
  stickToBottom.value = isNearBottom()
}

async function onLoadMore() {
  if (chat.loadingMore || !chat.hasMore || chat.messages.length === 0) return
  const oldScrollHeight = listRef.value?.scrollHeight || 0
  await loadMoreMessages()
  // 保持滚动位置：新消息插入头部后，调整 scrollTop 使当前内容不跳动
  await nextTick()
  if (listRef.value) {
    const newScrollHeight = listRef.value.scrollHeight
    const diff = newScrollHeight - oldScrollHeight
    if (diff > 0) {
      listRef.value.scrollTop += diff
    }
  }
}

onMounted(() => {
  // 回到页面时若仍处于流式轮次，恢复滚动位置（进入页面默认贴底并恢复自动跟随）
  forceScrollBottom()
  // 刷新语音配置（用户在设置页可能改过自动朗读/语音等，回到聊天页即时生效）
  loadTtsConfig()
  // 模型列表：设置页改配置后同步刷新（onConfigChanged 返回取消订阅函数）
  loadLlmProfiles()
  if (window.electronAPI?.onConfigChanged) {
    offConfigChanged = window.electronAPI.onConfigChanged(() => { loadLlmProfiles() })
  }
  window.addEventListener('keydown', onConvSearchHotkey)
})

onUnmounted(() => {
  clearTimeout(modelNoticeTimer)
  if (typeof offConfigChanged === 'function') offConfigChanged()
  offConfigChanged = null
  window.removeEventListener('keydown', onConvSearchHotkey)
})
</script>

<style scoped>
/* =========================================================
   唠嗑页 · 视觉层
   设计要点：
   1) 页头压扁成单行，把纵向空间还给消息流
   2) 助手消息去掉「气泡框」——正文直接落在画布上，更像和一个人说话
   3) 用户消息用极淡的暖色底 + 异形圆角，与助手形成"对话方向"
   4) 折叠面板（思考/工具/用量）统一为同一套「摘要行 + 旋转箭头」语言
   ========================================================= */

.chat-page {
  width: 100%;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  /* 只做透明度淡入：transform 会让图片预览弹窗的 fixed 定位相对页面而非视口 */
  animation: fadeIn var(--dur-slow) var(--ease-out) both;
}

/* ===== 页头 ===== */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  flex-shrink: 0;
}

.page-head-left {
  display: flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}

.page-head-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
  min-width: 0;
}

/* 模型切换：聊天页头部的紧凑胶囊选择器 */
.model-picker {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 26px;
  padding: 0 9px;
  border: 1px solid var(--line-2);
  border-radius: var(--r-full);
  background: rgba(255, 255, 255, 0.025);
  color: var(--text-3);
  font-size: 11.5px;
  transition: border-color var(--dur-fast), color var(--dur-fast);
}

.model-picker:hover {
  border-color: var(--line-3);
  color: var(--text-2);
}

.model-picker select {
  appearance: none;
  -webkit-appearance: none;
  max-width: 200px;
  padding: 0;
  border: none;
  outline: none;
  background: transparent;
  color: var(--text-2);
  font-size: 11.5px;
  cursor: pointer;
}

.model-picker select:disabled {
  opacity: 0.55;
  cursor: default;
}

.model-picker select option {
  background: var(--ink-800);
  color: var(--text-1);
}

.model-notice {
  position: absolute;
  top: 30px;
  right: 0;
  z-index: 20;
  padding: 3px 8px;
  border: 1px solid var(--line-2);
  border-radius: var(--r-xs);
  background: rgba(9, 12, 17, 0.94);
  box-shadow: var(--shadow-2);
  color: var(--jade-400);
  font-size: 10.5px;
  white-space: nowrap;
}

.model-notice.bad {
  color: var(--coral-400);
}

@media (max-width: 760px) {
  .model-picker select {
    max-width: 120px;
  }
}

.page-title {
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.015em;
  color: var(--text-1);
  margin: 0;
  white-space: nowrap;
}

.page-subtitle {
  font-size: 12px;
  color: var(--text-4);
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.conn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  height: 22px;
  padding: 0 9px;
  border-radius: var(--r-full);
  font-size: 11px;
  font-weight: 500;
  border: 1px solid var(--line-1);
  background: rgba(255, 255, 255, 0.02);
}

.conn-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: currentColor;
  flex-shrink: 0;
}

.conn.online {
  color: var(--jade-400);
  border-color: rgba(126, 203, 161, 0.22);
  background: var(--jade-a12);
}

.conn.offline {
  color: var(--amber-400);
  border-color: var(--amber-a20);
  background: var(--amber-a08);
}

.conn.offline .conn-dot {
  animation: breathe 1.6s ease-in-out infinite;
}

/* ===== 聊天卡片骨架 ===== */
.chat-card {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: linear-gradient(180deg, var(--ink-850), var(--ink-800));
  border: 1px solid var(--line-1);
  border-radius: var(--r-lg);
  overflow: hidden;
  box-shadow: var(--hairline), 0 1px 2px rgba(0, 0, 0, 0.3);
}

/* ===== 会话内搜索 ===== */
.conv-search {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 12px;
  color: var(--text-4);
  background: rgba(255, 255, 255, 0.025);
  border-bottom: 1px solid var(--line-1);
}

.conv-search input {
  flex: 1;
  min-width: 0;
  height: 26px;
  padding: 0;
  color: var(--text-1);
  font-size: 12.5px;
  font-family: inherit;
  background: transparent;
  border: none;
  outline: none;
}

.conv-search input::placeholder { color: var(--text-4); }

.conv-search-count {
  flex-shrink: 0;
  min-width: 46px;
  color: var(--text-3);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.conv-search-nav,
.conv-search-close {
  width: 24px;
  height: 24px;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  color: var(--text-3);
  background: transparent;
  border: 1px solid var(--line-2);
  border-radius: var(--r-xs);
  cursor: pointer;
}

.conv-search-nav:hover:not(:disabled),
.conv-search-close:hover {
  color: var(--text-1);
  background: rgba(255, 255, 255, 0.05);
}

.conv-search-nav:disabled {
  opacity: 0.35;
  cursor: default;
}

/* 命中消息：整条消息描边 + 淡琥珀底色，不破坏原排版 */
.msg.search-hit {
  border-radius: 12px;
  background: rgba(239, 168, 76, 0.055);
  box-shadow: 0 0 0 1px var(--amber-a35), 0 0 0 4px rgba(239, 168, 76, 0.06);
  transition: background 0.2s ease, box-shadow 0.2s ease;
}

.chat-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: row;
  position: relative;
}

/* ===== 会话侧栏 ===== */
.conv-panel {
  width: 196px;
  min-width: 196px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 8px;
  background: rgba(0, 0, 0, 0.16);
  border-right: 1px solid var(--line-1);
}

.conv-new {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  height: 32px;
  flex-shrink: 0;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--amber-ink);
  background: var(--amber-grad);
  border: none;
  border-radius: var(--r-sm);
  cursor: pointer;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.28);
  transition: filter var(--dur-fast), box-shadow var(--dur-fast);
}

.conv-new:hover {
  filter: brightness(1.07);
  box-shadow: var(--shadow-amber), inset 0 1px 0 rgba(255, 255, 255, 0.3);
}

.conv-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.conv-pinned-group {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
  max-height: 45%;
  padding-bottom: 6px;
  margin-bottom: 2px;
  border-bottom: 1px solid var(--line-1);
}

.conv-pinned-list {
  display: flex;
  flex-direction: column;
  gap: 1px;
  overflow-y: auto;
}

.conv-group-title {
  display: flex;
  align-items: center;
  gap: 5px;
  flex-shrink: 0;
  padding: 10px 7px 4px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.12em;
  color: var(--text-4);
  user-select: none;
}

.conv-empty {
  text-align: center;
  color: var(--text-4);
  font-size: 12px;
  margin-top: 26px;
}

.conv-more-hint {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px 0;
  color: var(--text-4);
  font-size: 11.5px;
}

.conv-more-hint.clickable {
  cursor: pointer;
  transition: color var(--dur-fast);
}

.conv-more-hint.clickable:hover {
  color: var(--text-2);
}

.conv-spinner {
  display: inline-block;
  width: 11px;
  height: 11px;
  border: 1.5px solid var(--line-3);
  border-top-color: var(--amber-400);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

/* 窄屏：侧栏折叠成图标轨道 */
@media (max-width: 900px) {
  .conv-panel {
    width: 50px;
    min-width: 50px;
    padding: 8px 4px;
  }
  .conv-panel .conv-new span {
    display: none;
  }
  .conv-panel .conv-new {
    padding: 0;
  }
  .conv-group-title {
    display: none;
  }
  .conv-pinned-group {
    max-height: 50%;
    padding-bottom: 0;
    border-bottom: none;
  }
}

/* ===== 消息流 ===== */
/* overflow-anchor: none —— 关闭浏览器滚动锚定：
   流式尾部由脚本原地更新，若浏览器再自行"锚定补偿"，会与自动贴底相互打架产生位移抖动 */
.msg-list {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  padding: 20px 24px 56px;
  overflow-anchor: none;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding-top: 16%;
  text-align: center;
}

.empty-mark {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  margin-bottom: 8px;
  border-radius: 16px;
  color: var(--amber-400);
  background:
    radial-gradient(circle at 50% 20%, var(--amber-a20), transparent 70%),
    var(--ink-850);
  border: 1px solid var(--line-2);
  box-shadow: var(--hairline);
}

.empty-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-1);
}

.empty-sub {
  font-size: 12px;
  color: var(--text-4);
}

.load-more-hint {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 8px 0 16px;
  color: var(--text-4);
  font-size: 12px;
}

.load-more-hint.clickable {
  cursor: pointer;
  transition: color var(--dur-fast);
}

.load-more-hint.clickable:hover {
  color: var(--amber-300);
}

.load-more-hint .spinner {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 1.5px solid var(--line-3);
  border-top-color: var(--amber-400);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

/* ===== 单条消息 ===== */
.msg {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 18px;
  animation: fadeUp var(--dur) var(--ease-out) both;
}

.msg.user {
  flex-direction: row-reverse;
}

.msg-avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  border-radius: 9px;
  font-size: 11px;
  font-weight: 600;
  user-select: none;
}

.msg-avatar img {
  width: 20px;
  height: 20px;
  object-fit: contain;
}

/* 助手头像沿用品牌「月光瓦片 + 黑猫」，让对话里也认得出是本喵 */
.msg-avatar.assistant {
  background: linear-gradient(150deg, #FBF0DA 0%, #E9D2A6 100%);
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.12),
    0 4px 12px -6px rgba(239, 168, 76, 0.55);
}

.msg-avatar.user {
  background: var(--ink-700);
  border: 1px solid var(--line-2);
  color: var(--text-3);
}

.msg-body {
  max-width: min(80%, 820px);
  min-width: 0;
}

.msg-content {
  padding: 11px 15px;
  font-size: 14px;
  line-height: 1.72;
  color: var(--text-1);
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--ink-900);
  border: 1px solid var(--line-1);
  border-radius: 4px var(--r-md) var(--r-md) var(--r-md);
  box-shadow: var(--shadow-1);
}

/* 助手正文：不套气泡，直接落在画布上 */
.msg-content.md-mode {
  padding: 2px 2px 0;
  white-space: normal;
  background: transparent;
  border-color: transparent;
  box-shadow: none;
  border-radius: 0;
}

/* 用户消息：极淡暖色 + 反向圆角，形成对话方向感 */
.msg.user .msg-content {
  color: var(--text-1);
  background: linear-gradient(155deg, rgba(239, 168, 76, 0.13), rgba(239, 168, 76, 0.04)),
    var(--ink-800);
  border-color: rgba(239, 168, 76, 0.18);
  border-radius: var(--r-md) 4px var(--r-md) var(--r-md);
}

/* ===== 子 Agent 段落：嵌套引用面板 ===== */
.msg-segment.sub-agent {
  position: relative;
  margin: 12px 0;
  border: 1px solid rgba(192, 166, 232, 0.22);
  border-left: 2px solid var(--lilac-400);
  border-radius: var(--r-md);
  overflow: hidden;
  background:
    radial-gradient(circle at 0 0, rgba(192, 166, 232, 0.1), transparent 62%),
    rgba(192, 166, 232, 0.03);
}

.sub-agent-head {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 7px 12px;
  font-size: 11.5px;
  color: var(--lilac-400);
  background: rgba(192, 166, 232, 0.07);
  border-bottom: 1px solid rgba(192, 166, 232, 0.16);
}

.sub-agent-avatar {
  display: flex;
  color: var(--lilac-400);
}

.sub-agent-badge {
  display: inline-flex;
  align-items: center;
  padding: 1px 7px;
  border-radius: var(--r-full);
  background: var(--lilac-a12);
  border: 1px solid rgba(192, 166, 232, 0.24);
  color: var(--lilac-400);
  font-size: 10.5px;
  font-weight: 600;
}

.sub-agent-name {
  color: var(--text-2);
  font-weight: 600;
}

.sub-agent-body {
  padding: 10px 13px;
}

.sub-agent-body > .markdown-body > :first-child {
  margin-top: 0;
}

.sub-agent-body > .markdown-body > :last-child {
  margin-bottom: 0;
}

.cursor {
  animation: blink 0.8s infinite;
  color: var(--amber-400);
}

.cursor-at-end {
  display: inline-block;
  margin-left: 4px;
  vertical-align: middle;
}

@keyframes blink {
  50% { opacity: 0; }
}

/* ===== 图片 / 附件 ===== */
.msg-images {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}

.msg-image {
  max-width: 200px;
  max-height: 200px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  cursor: pointer;
  transition: border-color var(--dur-fast), transform var(--dur-fast);
}

.msg-image:hover {
  border-color: var(--amber-a55);
  transform: translateY(-1px);
}

.msg-doc-attachments {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
}

/* ===== 折叠面板：统一摘要行语言 ===== */
.reasoning-block,
.tool-steps-wrapper,
.usage-block {
  margin-top: 8px;
  background: rgba(255, 255, 255, 0.015);
  border: 1px solid var(--line-1);
  border-radius: var(--r-md);
  overflow: hidden;
}

.reasoning-block {
  margin: 0 0 10px;
}

.reasoning-summary,
.tool-steps-summary,
.usage-summary {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 8px 12px;
  font-size: 12px;
  color: var(--text-3);
  cursor: pointer;
  list-style: none;
  user-select: none;
  transition: background var(--dur-fast), color var(--dur-fast);
}

.reasoning-summary {
  padding: 9px 12px;
}

.reasoning-summary::-webkit-details-marker,
.tool-steps-summary::-webkit-details-marker,
.usage-summary::-webkit-details-marker {
  display: none;
}

.reasoning-summary:hover,
.tool-steps-summary:hover,
.usage-summary:hover {
  background: rgba(255, 255, 255, 0.035);
  color: var(--text-2);
}

.sum-icon {
  flex-shrink: 0;
  color: var(--text-4);
}

.sum-chevron {
  display: flex;
  margin-left: auto;
  color: var(--text-4);
  transition: transform var(--dur) var(--ease-out);
}

.reasoning-block[open] .sum-chevron,
.tool-steps-wrapper[open] .sum-chevron,
.usage-block[open] .sum-chevron,
.interrupt-bar-wrapper[open] .interrupt-bar-arrow {
  transform: rotate(90deg);
}

.sum-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 16px;
  padding: 0 5px;
  border-radius: var(--r-full);
  background: var(--amber-a12);
  border: 1px solid var(--amber-a20);
  color: var(--amber-300);
  font-size: 10.5px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

/* 深度思考 */
.reasoning-content {
  padding: 9px 13px 12px;
  border-top: 1px dashed var(--line-1);
  color: var(--text-3);
  font-size: 12.5px;
  font-style: italic;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 240px;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.thinking-dot {
  color: var(--amber-400);
  animation: blink 1s infinite;
}

/* ===== 消息操作条 ===== */
.msg-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 2px;
  margin-top: 6px;
  opacity: 0.45;
  transition: opacity var(--dur);
}

.msg:hover .msg-actions,
.msg-actions:focus-within {
  opacity: 1;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: var(--text-4);
  cursor: pointer;
  transition: background var(--dur-fast), color var(--dur-fast);
}

.action-btn:hover {
  background: rgba(255, 255, 255, 0.06);
  color: var(--text-1);
}

.action-btn .action-icon {
  display: block;
}

.action-btn .action-icon.copied {
  color: var(--jade-400);
}

.action-btn.speaking {
  color: var(--amber-400);
}

/* ===== 工具调用 ===== */
.tool-steps {
  padding: 0 8px 8px;
  max-height: min(42vh, 320px);
  overflow-y: auto;
  overscroll-behavior: contain;
}

.tool-step {
  padding: 5px 10px;
  margin-bottom: 4px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-3);
  background: rgba(255, 255, 255, 0.02);
  border-left: 2px solid var(--line-2);
  border-radius: 6px;
}

.tool-step b {
  color: var(--text-1);
  font-weight: 600;
}

.tool-done {
  color: var(--jade-400);
  margin-left: 6px;
}

.tool-done.failed {
  color: var(--coral-400);
}

.tool-result {
  margin-top: 4px;
}

.tool-result-summary {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--text-4);
  font-size: 11px;
  cursor: pointer;
  list-style: none;
  user-select: none;
}

.tool-result-summary::-webkit-details-marker {
  display: none;
}

.tool-result-summary::before {
  content: '';
  width: 0;
  height: 0;
  border-left: 4px solid currentColor;
  border-top: 3.5px solid transparent;
  border-bottom: 3.5px solid transparent;
  transition: transform var(--dur);
}

.tool-result[open] > .tool-result-summary::before {
  transform: rotate(90deg);
}

.tool-args,
.tool-result-body {
  margin: 6px 0 0;
  padding: 7px 9px;
  background: var(--ink-1000);
  border: 1px solid var(--line-1);
  border-radius: 6px;
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 160px;
  overflow-y: auto;
}

.tool-args {
  color: var(--azure-400);
}

.tool-result-body {
  color: var(--text-3);
}

/* ===== Token 用量 ===== */
.usage-inline {
  margin-left: auto;
  color: var(--jade-400);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.usage-body {
  padding: 2px 12px 11px;
  display: flex;
  flex-direction: column;
  gap: 5px;
  border-top: 1px dashed var(--line-1);
  padding-top: 9px;
}

.usage-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 12px;
  color: var(--text-3);
}

.usage-label {
  min-width: 82px;
  color: var(--text-4);
}

.usage-value {
  color: var(--text-1);
  font-family: var(--font-mono);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.usage-detail {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  color: var(--text-4);
  font-size: 11px;
}

.usage-cache-rate {
  color: var(--jade-400);
  font-weight: 600;
}

.usage-total {
  margin-top: 2px;
  padding-top: 7px;
  border-top: 1px dashed var(--line-1);
}

.usage-total .usage-value {
  color: var(--amber-300);
}

/* ===== 高危操作确认 ===== */
.interrupt-bar-wrapper {
  margin-top: 8px;
  background: rgba(232, 192, 106, 0.04);
  border: 1px solid rgba(232, 192, 106, 0.24);
  border-radius: var(--r-md);
  overflow: hidden;
}

.interrupt-bar-summary {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 9px 12px;
  color: var(--warn-400);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  list-style: none;
  user-select: none;
  transition: background var(--dur-fast);
}

.interrupt-bar-summary::-webkit-details-marker {
  display: none;
}

.interrupt-bar-summary:hover {
  background: rgba(232, 192, 106, 0.06);
}

.interrupt-bar-arrow {
  display: flex;
  margin-left: auto;
  font-size: 10px;
  transition: transform var(--dur) var(--ease-out);
}

.interrupt-bar {
  padding: 10px 12px;
  background: rgba(0, 0, 0, 0.22);
  border-top: 1px solid rgba(232, 192, 106, 0.16);
}

.interrupt-global-btns {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}

.btn.approve-all {
  display: inline-flex;
  align-items: center;
  height: 30px;
  padding: 0 14px;
  font-size: 12px;
  font-weight: 600;
  color: var(--jade-400);
  background: var(--jade-a12);
  border: 1px solid rgba(126, 203, 161, 0.3);
  border-radius: var(--r-sm);
  cursor: pointer;
  transition: background var(--dur-fast), border-color var(--dur-fast);
}

.btn.approve-all:hover {
  background: rgba(126, 203, 161, 0.2);
  border-color: rgba(126, 203, 161, 0.5);
}

.interrupt-action {
  margin-top: 6px;
  padding: 8px 10px;
  background: var(--ink-900);
  border: 1px solid var(--line-1);
  border-radius: var(--r-sm);
}

.interrupt-action-header {
  display: flex;
  align-items: center;
  gap: 6px;
}

.interrupt-action-index {
  color: var(--text-4);
  font-size: 10.5px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.interrupt-action-name {
  color: var(--warn-400);
  font-size: 12px;
  font-weight: 600;
}

.interrupt-action-args {
  margin: 5px 0 0;
  color: var(--azure-400);
  font-family: var(--font-mono);
  font-size: 11.5px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
}

.interrupt-action-btns {
  display: flex;
  gap: 6px;
  margin-top: 8px;
}

.interrupt-hint {
  margin-top: 7px;
  color: var(--text-3);
  font-size: 11.5px;
}

.interrupt-fallback {
  margin-top: 4px;
  color: var(--warn-400);
  font-size: 12px;
}

.interrupt-expired {
  margin-top: 8px;
  padding: 7px 12px;
  border: 1px dashed var(--line-3);
  border-radius: var(--r-sm);
  color: var(--text-4);
  font-size: 11.5px;
}

.btn-sm {
  height: 26px;
  padding: 0 12px;
  font-size: 11.5px;
  font-weight: 600;
  border-radius: var(--r-xs);
  border: 1px solid transparent;
  cursor: pointer;
  transition: background var(--dur-fast), border-color var(--dur-fast);
}

.btn-sm.approve {
  color: var(--jade-400);
  background: var(--jade-a12);
  border-color: rgba(126, 203, 161, 0.28);
}

.btn-sm.approve:hover {
  background: rgba(126, 203, 161, 0.2);
}

.btn-sm.reject {
  color: var(--coral-400);
  background: var(--coral-a12);
  border-color: rgba(233, 119, 110, 0.28);
}

.btn-sm.reject:hover {
  background: rgba(233, 119, 110, 0.2);
}

/* ===== 错误 ===== */
.msg-error {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 8px;
  color: var(--coral-400);
  font-size: 12.5px;
}

.msg-error-text {
  flex: 1;
  min-width: 0;
}

.msg-retry-btn {
  flex-shrink: 0;
  height: 26px;
  padding: 0 12px;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--coral-400);
  background: var(--coral-a12);
  border: 1px solid rgba(233, 119, 110, 0.3);
  border-radius: var(--r-xs);
  cursor: pointer;
  transition: background var(--dur-fast), border-color var(--dur-fast);
}

.msg-retry-btn:hover:not(:disabled) {
  background: rgba(233, 119, 110, 0.2);
  border-color: rgba(233, 119, 110, 0.55);
}

.msg-retry-btn:disabled {
  opacity: 0.5;
  cursor: default;
}

/* ===== 输入区 ===== */
.input-area {
  position: relative;
  flex-shrink: 0;
  border-top: 1px solid var(--line-1);
  background: rgba(0, 0, 0, 0.14);
  transition: border-color var(--dur), background var(--dur);
}

.input-area.drag-over {
  border-color: var(--amber-a55);
  background: var(--amber-a08);
}

.input-bar {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 12px 14px 14px;
}

.composer-stack {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* ===== 生成中的消息队列（参考 DSH：默认排队，可插队） ===== */
.queue-panel {
  padding: 6px;
  background: linear-gradient(180deg, rgba(239, 168, 76, 0.055), rgba(239, 168, 76, 0.02));
  border: 1px solid var(--amber-a20);
  border-radius: var(--r-md);
}

.queue-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 2px 6px 6px;
  user-select: none;
}

.queue-title {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--amber-200);
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.queue-sub {
  color: var(--text-4);
  font-size: 10px;
  white-space: nowrap;
}

.queue-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 7px;
  background: rgba(10, 14, 20, 0.55);
  border: 1px solid var(--line-1);
  border-radius: var(--r-sm);
}

.queue-item + .queue-item {
  margin-top: 4px;
}

.queue-index {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--text-4);
  font-size: 10px;
  font-variant-numeric: tabular-nums;
  background: rgba(255, 255, 255, 0.045);
  border-radius: 5px;
}

.queue-main {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.queue-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-2);
  font-size: 12px;
}

.queue-meta {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  color: var(--text-4);
  font-size: 10px;
}

.queue-act {
  height: 24px;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 0 8px;
  font-family: inherit;
  font-size: 10.5px;
  border-radius: 6px;
  cursor: pointer;
}

.queue-act.send-now {
  color: var(--amber-200);
  background: var(--amber-a12);
  border: 1px solid var(--amber-a20);
}

.queue-act.send-now:hover {
  color: var(--amber-100);
  border-color: var(--amber-a55);
  background: var(--amber-a20);
}

.queue-act.remove {
  width: 24px;
  padding: 0;
  color: var(--text-4);
  background: transparent;
  border: 1px solid transparent;
}

.queue-act.remove:hover {
  color: var(--text-1);
  background: rgba(255, 255, 255, 0.05);
  border-color: var(--line-2);
}

@media (max-width: 720px) {
  .queue-sub { display: none; }
  .queue-act.send-now span { display: none; }
  .queue-act.send-now { width: 24px; padding: 0; }
}

/* 生成中：发送按钮变为“排队”，仍保持主按钮可点 */
.btn.send.queue {
  color: var(--amber-200);
  background: var(--amber-a12);
  border: 1px solid var(--amber-a35);
  box-shadow: none;
}

.btn.send.queue:hover:not(:disabled) {
  background: var(--amber-a20);
  border-color: var(--amber-a55);
}

/* 一体化书写区：外框承担焦点态，内部所有控件去边框，视觉更"整" */
.composer {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: var(--ink-1000);
  border: 1px solid var(--line-2);
  border-radius: var(--r-md);
  transition: border-color var(--dur-fast), box-shadow var(--dur-fast), background var(--dur-fast);
}

.composer:hover {
  border-color: var(--line-3);
}

.composer.focused {
  border-color: var(--amber-a55);
  box-shadow: 0 0 0 3px var(--amber-a12);
}

.composer-tools {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px 8px 8px;
}

.composer-hint {
  margin-left: auto;
  font-size: 10.5px;
  color: var(--text-4);
  user-select: none;
  white-space: nowrap;
}

.attach-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 26px;
  padding: 0 8px;
  flex-shrink: 0;
  font-size: 11.5px;
  color: var(--text-3);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--r-xs);
  cursor: pointer;
  transition: color var(--dur-fast), background var(--dur-fast), border-color var(--dur-fast);
}

.attach-btn:hover {
  color: var(--text-1);
  background: rgba(255, 255, 255, 0.05);
  border-color: var(--line-2);
}

.chat-input {
  width: 100%;
  min-width: 0;
  resize: none;
  padding: 11px 13px 4px;
  font-size: 13.5px;
  line-height: 1.65;
  color: var(--text-1);
  background: transparent;
  border: none;
  max-height: 180px;
}

.chat-input::placeholder {
  color: var(--text-4);
}

.chat-input:focus {
  outline: none;
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  height: 30px;
  padding: 0 13px;
  font-size: 12px;
  font-weight: 600;
  border: none;
  border-radius: var(--r-sm);
  cursor: pointer;
  white-space: nowrap;
  transition: filter var(--dur-fast), box-shadow var(--dur-fast), opacity var(--dur-fast);
}

.btn.send {
  color: var(--amber-ink);
  background: var(--amber-grad);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.28);
}

.btn.send:hover:not(:disabled) {
  filter: brightness(1.07);
  box-shadow: var(--shadow-amber), inset 0 1px 0 rgba(255, 255, 255, 0.3);
}

.btn.send:disabled {
  opacity: 0.35;
  cursor: not-allowed;
  box-shadow: none;
}

.btn.stop {
  color: var(--coral-400);
  background: var(--coral-a12);
  border: 1px solid rgba(233, 119, 110, 0.3);
}

.btn.stop:hover {
  background: rgba(233, 119, 110, 0.2);
}

/* ===== 拖拽遮罩 ===== */
.drag-overlay {
  position: absolute;
  inset: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
  background: rgba(9, 12, 17, 0.72);
  backdrop-filter: blur(4px);
  border: 1px dashed var(--amber-a55);
  border-radius: var(--r-sm);
}

.drag-hint {
  padding: 11px 22px;
  border-radius: var(--r-full);
  font-size: 13px;
  font-weight: 600;
  color: var(--amber-ink);
  background: var(--amber-grad);
  box-shadow: var(--shadow-amber);
}

/* ===== 图片放大预览 ===== */
/* ===== 知识库引用 ===== */
.kb-cites {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin: 2px 0 8px;
}

.kb-cites-title {
  color: var(--text-4);
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  margin-right: 2px;
}

.kb-cite-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 220px;
  padding: 2px 8px;
  color: var(--text-3);
  font-family: inherit;
  font-size: 10.5px;
  background: rgba(239, 168, 76, 0.06);
  border: 1px solid var(--amber-a20);
  border-radius: 999px;
  cursor: pointer;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kb-cite-chip:hover {
  color: var(--amber-200);
  border-color: var(--amber-a55);
  background: var(--amber-a12);
}

.kb-cite-index {
  color: var(--amber-300);
  flex-shrink: 0;
}

.cite-ref {
  color: var(--amber-300);
  text-decoration: none;
  border-bottom: 1px dotted var(--amber-a55);
  cursor: pointer;
  font-size: 0.92em;
}

.cite-ref:hover {
  color: var(--amber-200);
  border-bottom-style: solid;
}

.citation-modal {
  position: fixed;
  inset: 0;
  z-index: 1200;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(3, 5, 8, 0.72);
  backdrop-filter: blur(8px);
}

.citation-panel {
  width: min(640px, calc(100vw - 48px));
  max-height: min(72vh, 620px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: linear-gradient(180deg, #121721 0%, #0D1118 100%);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  box-shadow: 0 30px 80px -20px rgba(0, 0, 0, 0.85);
}

.citation-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 11px 13px;
  border-bottom: 1px solid var(--line-1);
}

.citation-index {
  flex-shrink: 0;
  color: var(--amber-300);
  font-size: 11px;
  font-weight: 700;
}

.citation-source {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-1);
  font-size: 12px;
  font-weight: 600;
}

.citation-close {
  width: 26px;
  height: 26px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  color: var(--text-3);
  background: transparent;
  border: 1px solid var(--line-2);
  border-radius: 6px;
  cursor: pointer;
}

.citation-close:hover { color: var(--text-1); background: rgba(255, 255, 255, 0.05); }

.citation-body {
  margin: 0;
  padding: 13px;
  overflow-y: auto;
  color: var(--text-2);
  font-family: inherit;
  font-size: 12.5px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

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

.image-modal-img {
  max-width: 90%;
  max-height: 90%;
  border-radius: var(--r-md);
  box-shadow: var(--shadow-3);
  cursor: default;
}

/* ===== 回到底部 ===== */
.back-to-bottom {
  position: absolute;
  right: 24px;
  bottom: 18px;
  z-index: 5;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  color: var(--text-2);
  background: rgba(22, 27, 37, 0.92);
  backdrop-filter: blur(8px);
  border: 1px solid var(--line-2);
  border-radius: 50%;
  box-shadow: var(--shadow-2);
  cursor: pointer;
  transition: transform var(--dur-fast) var(--ease-out), border-color var(--dur-fast), color var(--dur-fast);
}

.back-to-bottom:hover {
  color: var(--amber-300);
  border-color: var(--amber-a35);
  transform: translateY(-2px);
}

.back-to-bottom:active {
  transform: translateY(0);
}
</style>
