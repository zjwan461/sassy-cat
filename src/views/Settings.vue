<template>
  <div ref="pageEl" class="page settings-page">
    <header class="settings-topbar">
      <div class="topbar-head">
        <div class="eyebrow">
          <AppIcon name="settings" :size="12" />
          偏好设置
        </div>
        <div class="topbar-line">
          <h1 class="page-title">设置</h1>
          <span class="topbar-note">改动保存后生效</span>
        </div>
      </div>

      <div class="global-actions">
        <button class="btn primary" type="button" @click="saveAll">
          <AppIcon name="check" :size="14" />
          保存设置
        </button>
        <button class="btn warn" type="button" :class="{ 'is-done': restartDone }" @click="restartAgent" :disabled="restarting">
          <span v-if="restarting" class="btn-spinner"></span>
          <AppIcon v-else-if="restartDone" name="check" :size="14" class="btn-check" />
          <AppIcon v-else name="refresh" :size="14" />
          <span v-if="!restarting && !restartDone">重启服务进程</span>
        </button>
      </div>
    </header>

    <div class="settings-shell">
      <nav class="settings-nav" aria-label="设置分类">
        <div v-for="group in navGroups" :key="group.title" class="nav-group">
          <div class="nav-group-title">{{ group.title }}</div>
          <button
            v-for="item in group.items"
            :key="item.id"
            type="button"
            class="nav-item"
            :class="{ active: activeSection === item.id }"
            :aria-current="activeSection === item.id ? 'page' : undefined"
            @click="selectSection(item.id)"
          >
            <AppIcon :name="item.icon" :size="15" class="nav-icon" />
            <span class="nav-label">{{ item.label }}</span>
          </button>
        </div>
        <p class="nav-note">设置仅保存在本机</p>
      </nav>

      <div class="settings-main">
        <!-- 外观主题 -->
        <section v-show="activeSection === 'theme'" class="panel" aria-labelledby="sec-theme">
          <header class="panel-head">
            <span class="panel-icon"><AppIcon name="sun" :size="16" /></span>
            <div class="panel-head-text">
              <h2 id="sec-theme" class="panel-title">外观主题</h2>
              <p class="panel-sub">墨夜琥珀 / 霜白墨青，切换立即生效</p>
            </div>
          </header>
          <div class="panel-body">
            <div class="theme-picker">
              <button
                v-for="opt in themeOptions"
                :key="opt.value"
                type="button"
                class="theme-option"
                :class="[`theme-${opt.value}`, { active: themeMode === opt.value }]"
                @click="setTheme(opt.value)"
              >
                <span class="theme-swatch">
                  <span class="swatch-sample">Aa</span>
                  <span class="swatch-dot"></span>
                </span>
                <span class="theme-meta">
                  <span class="theme-name">
                    <AppIcon :name="opt.icon" :size="14" />
                    {{ opt.label }}
                  </span>
                  <span v-if="themeMode === opt.value" class="theme-badge">
                    <AppIcon name="check" :size="11" />
                    当前
                  </span>
                </span>
              </button>
            </div>
            <p class="field-hint">「跟随系统」会随操作系统的浅色 / 深色外观自动切换；选择保存在本机。</p>
          </div>
        </section>

        <!-- 桌宠 -->
        <section v-show="activeSection === 'pet'" class="panel" aria-labelledby="sec-pet">
          <header class="panel-head">
            <span class="panel-icon"><AppIcon name="bot" :size="16" /></span>
            <div class="panel-head-text">
              <h2 id="sec-pet" class="panel-title">桌宠</h2>
              <p class="panel-sub">显示开关、大小与快速提问快捷键</p>
            </div>
          </header>
          <div class="panel-body">
            <div class="sgroup">
              <div class="switch-row">
                <div class="switch-text">
                  <div class="switch-title">启用桌宠</div>
                  <p class="switch-desc">桌宠不可见时（关闭或右键临时隐藏），提醒事项与闲置提醒将以系统通知呈现，不再使用桌宠气泡。</p>
                </div>
                <label class="toggle">
                  <input type="checkbox" v-model="form.petEnabled" aria-label="启用桌宠" />
                  <span class="toggle-track"><span class="toggle-thumb"></span></span>
                </label>
              </div>
            </div>

            <div class="sgroup">
              <div class="sgroup-head">
                <h3 class="sgroup-title">外观</h3>
              </div>
              <div class="field">
                <div class="range-grid" role="group" aria-label="桌宠大小与透明度">
                  <label class="range-field">
                    <span class="range-label">大小</span>
                    <input type="range" v-model.number="form.petSize" min="0.75" max="1.3" step="0.05" />
                    <span class="range-value">{{ Number(form.petSize).toFixed(2) }}×</span>
                  </label>
                  <label class="range-field">
                    <span class="range-label">透明度</span>
                    <input type="range" v-model.number="form.petOpacity" min="0.35" max="1" step="0.05" />
                    <span class="range-value">{{ Math.round(Number(form.petOpacity) * 100) }}%</span>
                  </label>
                </div>
                <p class="field-hint">保存后桌宠即时缩放 / 变透明，不影响气泡与主窗口。</p>
              </div>
            </div>

            <div class="sgroup">
              <div class="sgroup-head">
                <h3 class="sgroup-title">快速提问</h3>
              </div>
              <div class="field">
                <label class="field-label">全局快捷键</label>
                <div class="hotkey-row">
                  <div
                    class="hotkey-box"
                    :class="{ recording: recordingKey, bad: hotkeyError }"
                    tabindex="0"
                    title="点击后按下组合键进行录制"
                    @click="startRecord"
                    @blur="stopRecord"
                    @keydown.prevent="onRecordKeydown"
                  >{{ hotkeyDisplay }}</div>
                  <button v-if="form.quickAskShortcut" class="mini" type="button" @click="form.quickAskShortcut = ''">禁用</button>
                </div>
                <p class="field-hint" :class="{ bad: hotkeyError }">
                  {{ hotkeyError || (recordingKey ? '请按下组合键（需包含 Ctrl / Alt / Shift / Win），Esc 取消' : '例如 Alt+Shift+Q；留空表示禁用') }}
                </p>
                <p v-if="hotkeyStatus" :class="hotkeyStatus.ok ? 'ok' : 'bad-text'" class="field-hint">{{ hotkeyStatus.text }}</p>
              </div>
            </div>

            <div class="sgroup">
              <div class="switch-row">
                <div class="switch-text">
                  <div class="switch-title">勿扰时段</div>
                  <p class="switch-desc">勿扰时段内不弹提醒气泡与系统通知；支持跨午夜（如 22:00 → 08:00）。</p>
                </div>
                <label class="toggle">
                  <input type="checkbox" v-model="form.dndEnabled" aria-label="勿扰时段" />
                  <span class="toggle-track"><span class="toggle-thumb"></span></span>
                </label>
              </div>
              <div v-if="form.dndEnabled" class="field-grid">
                <label class="field">
                  <span class="field-label">开始时间</span>
                  <input type="time" v-model="form.dndStart" />
                </label>
                <label class="field">
                  <span class="field-label">结束时间</span>
                  <input type="time" v-model="form.dndEnd" />
                </label>
              </div>
            </div>
          </div>
        </section>

        <!-- 语音朗读 -->
        <section v-show="activeSection === 'voice'" class="panel" aria-labelledby="sec-voice">
          <header class="panel-head">
            <span class="panel-icon"><AppIcon name="volume" :size="16" /></span>
            <div class="panel-head-text">
              <h2 id="sec-voice" class="panel-title">语音朗读（TTS）</h2>
              <p class="panel-sub">系统语音、语速与音调</p>
            </div>
          </header>
          <div class="panel-body">
            <div class="sgroup">
              <div class="field">
                <label class="field-label" for="tts-engine">语音方案</label>
                <select id="tts-engine" v-model="form.voiceEngine">
                  <option value="web-speech">Web Speech API（系统语音 · 无需 GPU）</option>
                  <option value="local" disabled>本地 TTS（N 卡 ≥8GB，Phase 2 敬请期待）</option>
                </select>
                <p class="field-hint">当前方案使用系统自带语音，无需显卡、零依赖；本地 TTS 将随 GPU 推理支持逐步开放。</p>
              </div>
            </div>

            <div class="sgroup">
              <div class="switch-row">
                <div class="switch-text">
                  <div class="switch-title">启用语音朗读</div>
                  <p class="switch-desc">开启后，每条 AI 回复气泡下都会出现朗读按钮。</p>
                </div>
                <label class="toggle">
                  <input type="checkbox" v-model="form.voiceEnabled" aria-label="启用语音朗读" />
                  <span class="toggle-track"><span class="toggle-thumb"></span></span>
                </label>
              </div>
              <div class="switch-row">
                <div class="switch-text">
                  <div class="switch-title">AI 自动朗读</div>
                  <p class="switch-desc">AI 回复生成时自动朗读；内置播放缓冲抗网络波动，回复结束会补全剩余内容。</p>
                </div>
                <label class="toggle">
                  <input type="checkbox" v-model="form.voiceAutoRead" :disabled="!form.voiceEnabled" aria-label="AI 自动朗读" />
                  <span class="toggle-track"><span class="toggle-thumb"></span></span>
                </label>
              </div>
            </div>

            <div class="sgroup">
              <div class="field">
                <label class="field-label" for="tts-voice">中文语音</label>
                <div class="inline-row">
                  <select id="tts-voice" v-model="form.voiceVoiceName" class="voice-select" :disabled="!form.voiceEnabled">
                    <option v-for="v in voiceOptions" :key="v.name" :value="v.name">{{ voiceLabel(v) }}</option>
                  </select>
                  <button class="btn" type="button" :disabled="!form.voiceEnabled" @click="voicePreview" :title="testingVoice ? '正在试听…' : '试听当前语音'">
                    <template v-if="testingVoice"><span class="eq"><i></i><i></i><i></i></span>试听中</template>
                    <template v-else><AppIcon name="play" :size="13" />试听</template>
                  </button>
                </div>
                <p v-if="!voiceOptions.length" class="field-hint">{{ voiceNoVoicesHint }}</p>
                <p v-else class="field-hint">选择朗读时使用的语音；留空则自动挑选中文语音。</p>
              </div>
            </div>

            <div class="sgroup">
              <div class="field-grid">
                <div class="field">
                  <div class="field-label-row">
                    <label class="field-label" for="tts-rate">语速</label>
                    <span class="inline-val">{{ form.voiceRate.toFixed(1) }}</span>
                  </div>
                  <input id="tts-rate" type="range" min="0.5" max="2" step="0.1" v-model.number="form.voiceRate" :disabled="!form.voiceEnabled" />
                </div>
                <div class="field">
                  <div class="field-label-row">
                    <label class="field-label" for="tts-pitch">音调</label>
                    <span class="inline-val">{{ form.voicePitch.toFixed(1) }}</span>
                  </div>
                  <input id="tts-pitch" type="range" min="0.5" max="2" step="0.1" v-model.number="form.voicePitch" :disabled="!form.voiceEnabled" />
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- 模型连接 -->
        <section v-show="activeSection === 'llm'" class="panel" aria-labelledby="sec-llm">
          <header class="panel-head">
            <span class="panel-icon"><AppIcon name="plug" :size="16" /></span>
            <div class="panel-head-text">
              <h2 id="sec-llm" class="panel-title">模型连接</h2>
              <p class="panel-sub">主 Agent 的 LLM 连接、采样与上下文策略</p>
            </div>
          </header>
          <div class="panel-body">
            <div class="sgroup">
              <div class="sgroup-head">
                <h3 class="sgroup-title">配置档</h3>
                <p class="sgroup-desc">一套连接参数存为一个配置档，可随时切换</p>
              </div>
              <div class="profile-row">
                <select :value="activeProfile" @change="switchProfile($event.target.value)" aria-label="当前配置档">
                  <option v-for="(p, name) in profiles" :key="name" :value="name">{{ p.label || name }}</option>
                </select>
                <button class="btn" type="button" @click="showAddProfile = true" title="新增配置档"><AppIcon name="plus" :size="14" />新增</button>
                <button class="btn warn" type="button" @click="deleteProfile" :disabled="activeProfile === 'default'" title="删除当前配置档（default 不可删除）"><AppIcon name="trash" :size="14" />删除</button>
              </div>
            </div>

            <div class="sgroup">
              <div class="sgroup-head">
                <h3 class="sgroup-title">连接</h3>
              </div>
              <div class="field-grid">
                <div class="field">
                  <label class="field-label" for="llm-provider">Provider</label>
                  <select id="llm-provider" v-model="form.provider">
                    <option value="openai">OpenAI‑Compatible</option>
                    <option value="deepseek">DeepSeek-Compatible</option>
                  </select>
                  <p class="field-hint">OpenAI: reasoning 放在 content 中；DeepSeek: 放在 reasoning_content 中</p>
                </div>
                <div class="field">
                  <label class="field-label" for="llm-model">模型名称</label>
                  <input id="llm-model" v-model="form.model" placeholder="Qwen3.6-35B" />
                </div>
                <div class="field span-2">
                  <label class="field-label" for="llm-base-url">Base URL</label>
                  <input id="llm-base-url" v-model="form.baseUrl" placeholder="http://localhost:8080/v1" />
                </div>
                <div class="field span-2">
                  <label class="field-label" for="llm-api-key">API Key</label>
                  <div class="key-row">
                    <input id="llm-api-key" v-model="form.apiKey" :type="showKey ? 'text' : 'password'" placeholder="sk-..." @focus="revealKey" />
                    <button class="mini" type="button" @click="showKey = !showKey">{{ showKey ? '隐藏' : '显示' }}</button>
                  </div>
                </div>
              </div>
            </div>

            <div class="sgroup">
              <div class="sgroup-head">
                <h3 class="sgroup-title">生成参数</h3>
              </div>
              <div class="field">
                <div class="field-label-row">
                  <label class="field-label" for="llm-temp">采样温度（Temperature）</label>
                  <span class="inline-val">{{ Number(form.temperature).toFixed(2) }}</span>
                </div>
                <input id="llm-temp" type="range" min="0" max="2" step="0.05" v-model.number="form.temperature" />
                <p class="field-hint">范围 0~2，越低回答越稳定、越高越发散（默认 0.7）；仅作用于当前配置档。</p>
              </div>
              <div class="field-grid">
                <div class="field">
                  <label class="field-label">最大输出 token（maxTokens）</label>
                  <div class="stepper">
                    <button type="button" class="step-btn" @click="step('maxTokens', -1024, MAX_TOKENS_MIN, MAX_TOKENS_MAX)" :disabled="form.maxTokens <= MAX_TOKENS_MIN"><AppIcon name="minus" :size="14" /></button>
                    <input type="number" v-model.number="form.maxTokens" :min="MAX_TOKENS_MIN" :max="MAX_TOKENS_MAX" class="step-input"
                      @blur="clamp('maxTokens', MAX_TOKENS_MIN, MAX_TOKENS_MAX, DEFAULT_MAX_TOKENS)" />
                    <button type="button" class="step-btn" @click="step('maxTokens', 1024, MAX_TOKENS_MIN, MAX_TOKENS_MAX)" :disabled="form.maxTokens >= MAX_TOKENS_MAX"><AppIcon name="plus" :size="14" /></button>
                  </div>
                  <p class="field-hint">单次回复上限，范围 256~1048576，默认 8192；实际请求会按上下文窗口自动收缩。</p>
                </div>
                <div class="field">
                  <label class="field-label">上下文窗口（contextWindow）</label>
                  <div class="stepper">
                    <button type="button" class="step-btn" @click="step('contextWindow', -8192, CONTEXT_WINDOW_MIN, CONTEXT_WINDOW_MAX)" :disabled="form.contextWindow <= CONTEXT_WINDOW_MIN"><AppIcon name="minus" :size="14" /></button>
                    <input type="number" v-model.number="form.contextWindow" :min="CONTEXT_WINDOW_MIN" :max="CONTEXT_WINDOW_MAX" class="step-input"
                      @blur="clamp('contextWindow', CONTEXT_WINDOW_MIN, CONTEXT_WINDOW_MAX, DEFAULT_CONTEXT_WINDOW)" />
                    <button type="button" class="step-btn" @click="step('contextWindow', 8192, CONTEXT_WINDOW_MIN, CONTEXT_WINDOW_MAX)" :disabled="form.contextWindow >= CONTEXT_WINDOW_MAX"><AppIcon name="plus" :size="14" /></button>
                  </div>
                  <p class="field-hint">单次可处理的最大 token 数（输入 + 输出），范围 8192~1048576，默认 262144。</p>
                </div>
              </div>
            </div>

            <div class="sgroup">
              <div class="sgroup-head">
                <h3 class="sgroup-title">上下文</h3>
                <p class="sgroup-desc">接近模型窗口上限时，自动把久远历史总结成一条摘要</p>
              </div>
              <div class="switch-row">
                <div class="switch-text">
                  <div class="switch-title">启用上下文自动压缩</div>
                  <p class="switch-desc">保留近期原文、摘要替换旧历史，避免请求溢出；关闭后不再自动裁剪，请自行控制会话长度。</p>
                </div>
                <label class="toggle">
                  <input type="checkbox" v-model="form.contextCompressionEnabled" aria-label="启用上下文自动压缩" />
                  <span class="toggle-track"><span class="toggle-thumb"></span></span>
                </label>
              </div>
              <div v-if="form.contextCompressionEnabled" class="sub-panel">
                <div class="field-grid">
                  <div class="field span-2">
                    <label class="field-label" for="cc-model">压缩使用的模型</label>
                    <select id="cc-model" v-model="form.contextCompressionModel">
                      <option value="">跟随当前配置档（{{ profiles[activeProfile]?.label || activeProfile }}）</option>
                      <option v-for="(p, name) in profiles" :key="name" :value="name">{{ p.label || name }}</option>
                    </select>
                    <p class="field-hint">生成摘要所用的 LLM；留空则复用当前激活的模型。</p>
                  </div>
                  <div class="field span-2">
                    <div class="field-label-row">
                      <label class="field-label" for="cc-threshold">触发压缩的上下文占用</label>
                      <span class="inline-val">{{ form.contextCompressionThreshold }}%</span>
                    </div>
                    <input id="cc-threshold" type="range" :min="CC_THRESHOLD_MIN" :max="CC_THRESHOLD_MAX" step="5" v-model.number="form.contextCompressionThreshold" />
                    <p class="field-hint">估算 token 达到窗口的该比例时触发，范围 10~95%（默认 80%）。</p>
                  </div>
                  <div class="field">
                    <label class="field-label" for="cc-retain">压缩后保留最近原文（tokens）</label>
                    <input id="cc-retain" type="number" v-model.number="form.contextCompressionRetainTokens" min="0" :max="CC_RETAIN_TOKENS_MAX" step="1024" />
                    <p class="field-hint">默认 0 = 按窗口的 16% 自动计算（上限 64k）。</p>
                  </div>
                  <div class="field">
                    <label class="field-label" for="cc-summary-input">摘要输入上限（tokens）</label>
                    <input id="cc-summary-input" type="number" v-model.number="form.contextCompressionSummaryInput" min="0" :max="CC_SUMMARY_INPUT_MAX" step="8192" />
                    <p class="field-hint">默认 65536；0 = 不截断，交给摘要模型自身窗口兜底。</p>
                  </div>
                  <div class="field span-2">
                    <label class="field-label" for="cc-headroom">触发预留 headroom（tokens）</label>
                    <input id="cc-headroom" type="number" v-model.number="form.contextCompressionHeadroom" min="0" :max="CC_HEADROOM_MAX" step="4096" />
                    <p class="field-hint">阈值同时受 maxTokens 与 headroom 约束：min(窗口 × 比例, 窗口 − maxTokens − headroom)，默认 8192。</p>
                  </div>
                </div>
              </div>

              <!-- 媒体守卫与自动压缩相互独立：关掉压缩只是不做摘要，历史图片的压缩 / 预算照常生效 -->
              <details class="fold">
                <summary>
                  <AppIcon name="play" :size="10" class="fold-chevron" />
                  <span class="fold-title">媒体守卫</span>
                  <span class="fold-meta">5 项 · 历史图片压缩与预算</span>
                </summary>
                <div class="fold-body">
                  <p class="field-hint fold-tip">与上面的自动压缩相互独立：关闭压缩只是不做摘要，历史图片的体积 / 张数预算照常生效。</p>
                  <div class="field-grid">
                    <div class="field">
                      <label class="field-label" for="media-kb">单张图片压缩目标（KB）</label>
                      <input id="media-kb" type="number" v-model.number="form.contextMediaMaxKB" :min="MEDIA_MAX_KB_MIN" :max="MEDIA_MAX_KB_MAX" step="128" />
                      <p class="field-hint">默认 1024KB；压不到目标也保留最小产物，不因体积丢图；0 = 不设目标。</p>
                    </div>
                    <div class="field">
                      <label class="field-label" for="media-px">压缩后图片最长边（px）</label>
                      <input id="media-px" type="number" v-model.number="form.contextMediaMaxPx" :min="MEDIA_MAX_PX_MIN" :max="MEDIA_MAX_PX_MAX" step="128" />
                      <p class="field-hint">按最长边等比缩放，默认 1568px；越小越省视觉 token，截图文字越糊。</p>
                    </div>
                    <div class="field">
                      <label class="field-label" for="media-budget">历史媒体总预算（KB）</label>
                      <input id="media-budget" type="number" v-model.number="form.contextMediaBudgetKB" min="0" :max="MEDIA_BUDGET_KB_MAX" step="1024" />
                      <p class="field-hint">默认 8192KB；0 = 不限制，永远只压缩不 offload。</p>
                    </div>
                    <div class="field">
                      <label class="field-label" for="media-images">历史图片张数预算</label>
                      <input id="media-images" type="number" v-model.number="form.contextMediaMaxImages" min="0" :max="MEDIA_MAX_IMAGES_MAX" step="1" />
                      <p class="field-hint">默认 24 张；0 = 不限制。</p>
                    </div>
                    <div class="field span-2">
                      <label class="field-label" for="media-offload">offload 阶梯（KB）</label>
                      <input id="media-offload" type="number" v-model.number="form.contextMediaOffloadKB" min="0" :max="MEDIA_OFFLOAD_KB_MAX" step="512" />
                      <p class="field-hint">总预算超限时一次释放的额度，默认 1024KB；阶梯式高水位可避免每来一张图就改写旧前缀。</p>
                    </div>
                  </div>
                </div>
              </details>
            </div>

            <div class="sgroup">
              <div class="sgroup-head">
                <h3 class="sgroup-title">高级</h3>
              </div>
              <div class="field">
                <label class="field-label" for="llm-extra">额外参数（JSON）</label>
                <textarea id="llm-extra" v-model="form.extraParamsText" rows="3" class="mono" @input="validateExtra"></textarea>
                <p class="field-hint" :class="{ bad: extraError }">{{ extraError || '个性化模型参数，例如 {"enable_thinking": true}、{"reasoning_effort": "high"}' }}</p>
              </div>
              <div class="actions">
                <button class="btn" type="button" @click="testConnection" :disabled="testing">{{ testing ? '测试中…' : '测试连接' }}</button>
                <span v-if="testResult" :class="testResult.ok ? 'ok' : 'bad-text'" class="field-hint">{{ testResult.text }}</span>
              </div>
            </div>
          </div>
        </section>

        <!-- Agent 配置 -->
        <section v-show="activeSection === 'agent'" class="panel" aria-labelledby="sec-agent">
          <header class="panel-head">
            <span class="panel-icon"><AppIcon name="brain" :size="16" /></span>
            <div class="panel-head-text">
              <h2 id="sec-agent" class="panel-title">Agent 配置</h2>
              <p class="panel-sub">人设提示词、运行限制与高危操作确认</p>
            </div>
          </header>
          <div class="panel-body">
            <div class="sgroup">
              <div class="sgroup-head">
                <h3 class="sgroup-title">配置档</h3>
              </div>
              <div class="profile-row">
                <select :value="activeAgentProfile" @change="switchAgentProfile($event.target.value)" aria-label="当前 Agent 配置档">
                  <option v-for="(p, name) in agentProfiles" :key="name" :value="name">{{ p.label || name }}</option>
                </select>
                <button class="btn" type="button" @click="showAddAgentProfile = true" title="新增 Agent 配置档"><AppIcon name="plus" :size="14" />新增</button>
                <button class="btn warn" type="button" @click="deleteAgentProfile" :disabled="activeAgentProfile === 'default'" title="删除当前 Agent 配置档（default 不可删除）"><AppIcon name="trash" :size="14" />删除</button>
              </div>
            </div>

            <div class="sgroup">
              <div class="field">
                <div class="field-label-row">
                  <label class="field-label" for="agent-persona">人设提示词</label>
                  <span class="inline-val">{{ form.persona.length }} 字</span>
                </div>
                <textarea id="agent-persona" v-model="form.persona" rows="8" class="mono persona"
                  placeholder="你是「优墨」……（支持 {app_name} {time} {os_user} 变量）"></textarea>
                <p class="field-hint">留空使用默认傲娇猫咪人设；支持 {app_name} / {time} / {os_user} 变量。</p>
              </div>
            </div>

            <div class="sgroup">
              <div class="sgroup-head">
                <h3 class="sgroup-title">运行限制</h3>
              </div>
              <div class="field-grid">
                <div class="field">
                  <label class="field-label">递归上限（步）</label>
                  <div class="stepper">
                    <button type="button" class="step-btn" @click="step('recursionLimit', -1, 1, 9999)" :disabled="form.recursionLimit <= 1"><AppIcon name="minus" :size="14" /></button>
                    <input type="number" v-model.number="form.recursionLimit" min="1" max="9999" class="step-input"
                      @blur="clamp('recursionLimit', 1, 9999, 100)" />
                    <button type="button" class="step-btn" @click="step('recursionLimit', 1, 1, 9999)" :disabled="form.recursionLimit >= 9999"><AppIcon name="plus" :size="14" /></button>
                  </div>
                  <p class="field-hint">单轮对话可执行的最大步数（含工具调用），范围 1~9999，默认 100。</p>
                </div>
                <div class="field">
                  <label class="field-label" for="agent-ocr-engine">对话文档解析引擎</label>
                  <select id="agent-ocr-engine" v-model="form.agentOcrEngine" :disabled="!form.agentEnableOcr">
                    <option value="markitdown">MarkItDown（快速）</option>
                    <option value="docling">Docling（更精细，支持图片识别）</option>
                  </select>
                  <p class="field-hint">需先开启下方的「对话文档解析」。</p>
                </div>
              </div>
              <div class="switch-row">
                <div class="switch-text">
                  <div class="switch-title">启用对话文档解析（OCR）</div>
                  <p class="switch-desc">开启后对话中上传的文档会 OCR 解析并入库；关闭则只保存文件，不做解析。</p>
                </div>
                <label class="toggle">
                  <input type="checkbox" v-model="form.agentEnableOcr" aria-label="启用对话文档解析（OCR）" />
                  <span class="toggle-track"><span class="toggle-thumb"></span></span>
                </label>
              </div>
            </div>

            <div class="sgroup">
              <div class="sgroup-head">
                <h3 class="sgroup-title">检索与工具</h3>
              </div>
              <div class="field">
                <label class="field-label" for="agent-tavily">Tavily API Key（网络搜索）</label>
                <div class="key-row">
                  <input id="agent-tavily" v-model="form.tavilyApiKey" :type="showTavilyKey ? 'text' : 'password'" placeholder="tvly-..." />
                  <button class="mini" type="button" @click="showTavilyKey = !showTavilyKey">{{ showTavilyKey ? '隐藏' : '显示' }}</button>
                </div>
                <p class="field-hint">用于 internet_search 工具，留空则无法使用网络搜索。</p>
              </div>
              <div class="field">
                <label class="field-label" for="agent-ds">DeepSeek API Key（搜索 / 网页抓取）</label>
                <div class="key-row">
                  <input id="agent-ds" v-model="form.dsApiKey" :type="showDsKey ? 'text' : 'password'" placeholder="sk-..." />
                  <button class="mini" type="button" @click="showDsKey = !showDsKey">{{ showDsKey ? '隐藏' : '显示' }}</button>
                </div>
                <p class="field-hint">用于 deepseek_web_search / deepseek_web_fetch，留空则这两个工具不可用。</p>
              </div>
            </div>

            <div class="sgroup">
              <div class="sgroup-head">
                <h3 class="sgroup-title">高危操作确认</h3>
                <p class="sgroup-desc">勾选的工具在执行前会中断并等待你确认</p>
              </div>
              <div class="interrupt-grid">
                <label v-for="t in interruptTools" :key="t.name" class="check">
                  <input type="checkbox" v-model="form.interruptOn[t.name]" /> {{ t.label }}
                </label>
              </div>
              <div class="actions">
                <button class="mini" type="button" @click="setAllInterrupt(true)">全部打断</button>
                <button class="mini" type="button" @click="setAllInterrupt(false)">全部放行</button>
              </div>
              <div class="switch-row">
                <div class="switch-text">
                  <div class="switch-title">技能脚本免确认</div>
                  <p class="switch-desc">运行技能自带脚本（skills/技能名/scripts/脚本.py）不再弹确认；含管道 / 重定向 / 变量等拼接写法的命令仍会打断。仅在勾选「执行命令（execute）」时生效。</p>
                </div>
                <label class="toggle">
                  <input type="checkbox" v-model="form.autoApproveSkillScripts" aria-label="技能脚本免确认" />
                  <span class="toggle-track"><span class="toggle-thumb"></span></span>
                </label>
              </div>
            </div>

            <div class="sgroup">
              <div class="sgroup-head">
                <h3 class="sgroup-title">提示词</h3>
              </div>
              <div class="actions">
                <button class="btn" type="button" @click="togglePreview">{{ preview ? '隐藏完整提示词' : '预览完整提示词' }}</button>
                <button class="btn" type="button" @click="resetPersona">恢复默认人设</button>
              </div>
              <pre v-if="preview" class="preview-box">{{ preview }}</pre>
            </div>
          </div>
        </section>

        <!-- dsh 子代理 -->
        <section v-show="activeSection === 'dsh'" class="panel" aria-labelledby="sec-dsh">
          <header class="panel-head">
            <span class="panel-icon"><AppIcon name="layers" :size="16" /></span>
            <div class="panel-head-text">
              <h2 id="sec-dsh" class="panel-title">dsh 子代理</h2>
              <p class="panel-sub">DeepSeek Harness 的连接方式、输出上限与系统提示词</p>
            </div>
          </header>
          <div class="panel-body">
            <div class="sgroup">
              <p class="notice">
                <AppIcon name="info" :size="14" />
                <span>dsh 会自动带上主 Agent 的技能：委托执行时挂载「技能管理」里的同一套技能，按需加载，无需重复配置。</span>
              </p>
              <div class="switch-row no-line">
                <div class="switch-text">
                  <div class="switch-title">复用主 Agent 的 LLM</div>
                  <p class="switch-desc">勾选时 dsh 直接使用「模型连接」中当前激活的配置档（{{ mainLlmSummary }}）；取消勾选则使用下方独立连接参数。</p>
                </div>
                <label class="toggle">
                  <input type="checkbox" v-model="form.dshUseMainLlm" aria-label="复用主 Agent 的 LLM" />
                  <span class="toggle-track"><span class="toggle-thumb"></span></span>
                </label>
              </div>
              <!-- 复用主 Agent LLM 时，独立连接参数整组隐藏（值仍随保存一起落盘，不丢失） -->
              <div v-if="!form.dshUseMainLlm" class="sub-panel">
                <div class="field-grid">
                  <div class="field">
                    <label class="field-label" for="dsh-base">Base URL</label>
                    <input id="dsh-base" v-model="form.dshBaseUrl" placeholder="http://localhost:8080/v1" />
                  </div>
                  <div class="field">
                    <label class="field-label" for="dsh-model">模型名称</label>
                    <input id="dsh-model" v-model="form.dshModel" placeholder="Qwen3.6-35B" />
                  </div>
                  <div class="field span-2">
                    <label class="field-label" for="dsh-key">API Key</label>
                    <div class="key-row">
                      <input id="dsh-key" v-model="form.dshApiKey" :type="showDshKey ? 'text' : 'password'" placeholder="sk-..." @focus="revealDshKey" />
                      <button class="mini" type="button" @click="showDshKey = !showDshKey">{{ showDshKey ? '隐藏' : '显示' }}</button>
                    </div>
                  </div>
                </div>
                <p class="field-hint">dsh 路由名固定为 deepseek-official，模型 id 原样透传给网关，填服务商 / 自建服务实际使用的模型名。</p>
              </div>
            </div>

            <div class="sgroup">
              <div class="field">
                <div class="field-label-row">
                  <label class="field-label" for="dsh-prompt">系统提示词</label>
                  <span class="inline-val">{{ form.dshSystemPrompt.length }} 字</span>
                </div>
                <textarea id="dsh-prompt" v-model="form.dshSystemPrompt" rows="10" class="mono persona"
                  placeholder="留空则使用内置默认 dsh 提示词"></textarea>
                <p class="field-hint">支持 {shell_guidance} 变量，会在运行平台展开为 pwsh / bash 指引。</p>
              </div>
            </div>

            <div class="sgroup">
              <div class="sgroup-head">
                <h3 class="sgroup-title">输出</h3>
              </div>
              <div class="field-grid">
                <div class="field">
                  <label class="field-label">最大输出 tokens</label>
                  <div class="stepper">
                    <button type="button" class="step-btn" @click="step('dshMaxTokens', -1024, 1, DSH_MAX_TOKENS_LIMIT)" :disabled="form.dshMaxTokens <= 1"><AppIcon name="minus" :size="14" /></button>
                    <input type="number" v-model.number="form.dshMaxTokens" min="1" :max="DSH_MAX_TOKENS_LIMIT" class="step-input"
                      @blur="clamp('dshMaxTokens', 1, DSH_MAX_TOKENS_LIMIT, DSH_MAX_TOKENS_LIMIT)" />
                    <button type="button" class="step-btn" @click="step('dshMaxTokens', 1024, 1, DSH_MAX_TOKENS_LIMIT)" :disabled="form.dshMaxTokens >= DSH_MAX_TOKENS_LIMIT"><AppIcon name="plus" :size="14" /></button>
                  </div>
                  <p class="field-hint">范围 1~131072，默认 131072（DashScope qwen 系只接受该区间）。</p>
                </div>
                <div class="field">
                  <label class="field-label" for="dsh-reasoning">推理强度（reasoningEffort）</label>
                  <select id="dsh-reasoning" v-model="form.dshReasoningEffort">
                    <option v-for="o in dshReasoningEffortOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
                  </select>
                  <p class="field-hint">仅 dsh 适配器识别（deepseek-official），与主 Agent 的「额外参数」互不影响。</p>
                </div>
              </div>
              <div class="actions">
                <button class="btn" type="button" @click="resetDshPrompt">恢复默认提示词</button>
              </div>
            </div>
          </div>
        </section>

        <!-- 知识库（RAG） -->
        <section v-show="activeSection === 'rag'" class="panel" aria-labelledby="sec-rag">
          <header class="panel-head">
            <span class="panel-icon"><AppIcon name="database" :size="16" /></span>
            <div class="panel-head-text">
              <h2 id="sec-rag" class="panel-title">知识库（RAG）</h2>
              <p class="panel-sub">入库行为、检索参数与向量模型</p>
            </div>
          </header>
          <div class="panel-body">
            <div class="sgroup">
              <div class="switch-row">
                <div class="switch-text">
                  <div class="switch-title">聊天上传文件自动入库</div>
                  <p class="switch-desc">开启后，普通对话中上传的文件将异步自动 Embedding 到默认知识库。</p>
                </div>
                <label class="toggle">
                  <input type="checkbox" v-model="form.ragAutoEmbedding" aria-label="聊天上传文件自动入库" />
                  <span class="toggle-track"><span class="toggle-thumb"></span></span>
                </label>
              </div>
              <div class="switch-row">
                <div class="switch-text">
                  <div class="switch-title">混合检索（向量 + 关键词）</div>
                  <p class="switch-desc">向量语义召回 + BM25 关键词召回，再用 RRF 融合；对编号、专有名词、代码标识符更稳。关闭后回到纯向量 top-k。</p>
                </div>
                <label class="toggle">
                  <input type="checkbox" v-model="form.ragHybrid" aria-label="混合检索" />
                  <span class="toggle-track"><span class="toggle-thumb"></span></span>
                </label>
              </div>
            </div>

            <div class="sgroup">
              <div class="sgroup-head">
                <h3 class="sgroup-title">分块与召回</h3>
              </div>
              <div class="rag-retrieval-row">
                <label class="rag-num">
                  分块大小
                  <input type="number" v-model.number="form.ragChunkSize" min="100" max="8000" step="100" />
                </label>
                <label class="rag-num">
                  重叠
                  <input type="number" v-model.number="form.ragChunkOverlap" min="0" max="4000" step="50" />
                </label>
                <label class="rag-num">
                  候选倍数
                  <input type="number" v-model.number="form.ragCandidateMultiplier" min="1" max="10" step="1" />
                </label>
              </div>
              <p class="field-hint">分块大小 / 重叠单位为字符；候选倍数用于混合检索（实际召回数 = k × 倍数）。修改分块参数后需重建索引才会应用到已有文档。</p>
            </div>

            <div class="sgroup">
              <div class="sgroup-head">
                <h3 class="sgroup-title">索引健康</h3>
                <p class="sgroup-desc">向量维度、分块数与失败原因</p>
              </div>
              <div class="rag-health" :class="{ bad: ragHealth && !ragHealth.dimensionMatch && !ragHealth.empty }">
                <div class="rag-health-grid">
                  <span class="rh-item"><span class="rh-label">模型</span>{{ ragHealth?.embeddingModel?.model || '—' }}</span>
                  <span class="rh-item">
                    <span class="rh-label">维度</span>
                    {{ ragHealth ? `${ragHealth.embeddingDim ?? '—'} / 集合 ${ragHealth.collectionDim ?? '—'}` : '检测中…' }}
                  </span>
                  <span class="rh-item">
                    <span class="rh-label">分块 / 文档</span>
                    {{ ragHealth ? `${ragHealth.count ?? '—'} / ${ragHealth.documentCount ?? '—'}` : '—' }}
                  </span>
                </div>
                <div v-if="ragHealth && ragHealth.embeddingDim && ragHealth.collectionDim && !ragHealth.dimensionMatch && !ragHealth.empty" class="rag-warn">
                  <AppIcon name="alert" :size="13" />
                  <span>当前模型输出 {{ ragHealth.embeddingDim }} 维，索引是 {{ ragHealth.collectionDim }} 维；向量召回会降级为关键词。请重建索引，或切回建库时的模型。</span>
                </div>
                <div v-if="ragHealth?.embeddingError" class="rag-warn">
                  <AppIcon name="alert" :size="13" />
                  <span :title="ragHealth.embeddingError">Embedding 模型调用失败：{{ shortError(ragHealth.embeddingError, 140) }}。请检查模型地址 / API Key，或先修复模型再重建索引。</span>
                </div>
                <div v-if="ragHealth?.missingFileCount" class="rag-warn">
                  <AppIcon name="alert" :size="13" />
                  <span>{{ ragHealth.missingFileCount }} 篇文档的原始文件已缺失，重建后这些文档会标记为失败。</span>
                </div>
                <div class="rag-health-actions">
                  <button class="mini" type="button" @click="loadRagHealth" :disabled="ragHealthLoading">刷新状态</button>
                  <button class="mini danger" type="button" @click="startRagRebuild" :disabled="ragRebuild.running || ragHealthLoading || !!ragHealth?.embeddingError" :title="ragHealth?.embeddingError ? '请先修复 Embedding 模型' : ''">
                    {{ ragRebuild.running ? '重建中…' : '重建全部索引' }}
                  </button>
                  <span class="rag-health-tip">重建会清空现有向量，并按原始文件重新 OCR / 分块 / embedding</span>
                </div>
                <div v-if="ragRebuild.running" class="rag-progress">
                  <div class="rag-progress-bar"><span :style="{ width: ragRebuildPercent + '%' }"></span></div>
                  <div class="rag-progress-text">
                    {{ ragRebuild.done }} / {{ ragRebuild.total }} · {{ ragRebuild.current || '准备中' }}
                  </div>
                </div>
                <div v-else-if="ragRebuild.finishedAt" class="rag-progress-text">
                  上次重建：{{ ragRebuild.failed ? `${ragRebuild.failed} 篇失败` : '全部成功' }}
                  （{{ ragRebuild.done }} / {{ ragRebuild.total }}）
                </div>
              </div>
            </div>

            <div class="sgroup">
              <div class="sgroup-head">
                <h3 class="sgroup-title">向量模型</h3>
              </div>
              <div class="field-grid">
                <div class="field">
                  <label class="field-label" for="rag-embed-type">Embedding 模型来源</label>
                  <select id="rag-embed-type" v-model="form.ragEmbedType" @change="onEmbedTypeChange">
                    <option value="local">本地模型（Local）</option>
                    <option value="remote">远程 API（OpenAI-Compatible）</option>
                  </select>
                  <p class="field-hint">本地模式无需 Base URL / API Key，首次使用时自动下载模型。</p>
                </div>
                <div class="field">
                  <label class="field-label" for="rag-embed-model">Embedding 模型名称</label>
                  <input id="rag-embed-model" v-model="form.ragEmbedModel" :placeholder="form.ragEmbedType === 'local' ? '由智能下载自动确定' : 'text-embedding-3-small'"
                    :disabled="form.ragEmbedType === 'local'" @change="onEmbedModelChange" />
                  <p class="field-hint">本地模式按显卡自动确定（N 卡 ≥4G 显存用 bge-large，否则 bge-small）；远程模式填服务商模型名。</p>
                </div>
                <div class="field">
                  <label class="field-label" for="rag-base-url">Base URL</label>
                  <input id="rag-base-url" v-model="form.ragEmbedBaseUrl" placeholder="https://api.openai.com/v1" :disabled="form.ragEmbedType !== 'remote'" />
                </div>
                <div class="field">
                  <label class="field-label" for="rag-api-key">API Key</label>
                  <div class="key-row">
                    <input id="rag-api-key" v-model="form.ragEmbedApiKey" :type="showRagKey ? 'text' : 'password'" placeholder="sk-..." :disabled="form.ragEmbedType !== 'remote'" />
                    <button class="mini" type="button" @click="showRagKey = !showRagKey">{{ showRagKey ? '隐藏' : '显示' }}</button>
                  </div>
                  <p class="field-hint">仅远程模式需要。</p>
                </div>
                <div class="field span-2">
                  <label class="field-label" for="rag-ocr">知识库文档解析引擎（OCR）</label>
                  <select id="rag-ocr" v-model="form.ragOcrEngine">
                    <option value="docling">Docling（更精细，支持图片识别）</option>
                    <option value="markitdown">MarkItDown（快速）</option>
                  </select>
                  <p class="field-hint">知识库维护上传时解析文档所使用的引擎，默认 Docling。</p>
                </div>
              </div>

              <div v-if="form.ragEmbedType === 'local' && !form.ragLocalDownloaded" id="rag-model" class="download-box">
                <div class="download-text">
                  <div class="switch-title">本地模型下载</div>
                  <p class="field-hint">自动检测网络（不可直连时走 hf-mirror 镜像）与显卡（N 卡 ≥4G 显存下载 bge-large，否则 bge-small），模型较大请耐心等待。</p>
                </div>
                <div class="actions">
                  <button class="btn primary" type="button" @click="downloadModel" :disabled="downloading">
                    <span v-if="downloading" class="btn-spinner"></span>
                    <span v-else class="btn-label"><AppIcon name="download" :size="14" />下载模型</span>
                    <span v-if="downloading">下载中…</span>
                  </button>
                  <span v-if="downloadResult" :class="downloadResult.ok ? 'ok' : 'bad-text'" class="field-hint">{{ downloadResult.text }}</span>
                </div>
              </div>
              <div v-else-if="form.ragEmbedType === 'local'" id="rag-model" class="download-box">
                <div class="download-text">
                  <div class="switch-title">本地模型状态</div>
                  <p class="field-hint">模型已下载{{ form.ragEmbedModel ? `：${form.ragEmbedModel}` : '' }}，可直接用于入库与检索。</p>
                </div>
                <div class="actions">
                  <span class="ok"><AppIcon name="check" :size="13" />已就绪</span>
                  <button class="mini" type="button" @click="redownloadModel" :disabled="downloading" title="清除已下载状态并重新下载">重新下载</button>
                  <span v-if="downloadResult" :class="downloadResult.ok ? 'ok' : 'bad-text'" class="field-hint">{{ downloadResult.text }}</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- 工作区 -->
        <section v-show="activeSection === 'workspace'" class="panel" aria-labelledby="sec-workspace">
          <header class="panel-head">
            <span class="panel-icon"><AppIcon name="folder" :size="16" /></span>
            <div class="panel-head-text">
              <h2 id="sec-workspace" class="panel-title">工作区</h2>
              <p class="panel-sub">Agent 读写文件、执行命令的根目录</p>
            </div>
          </header>
          <div class="panel-body">
            <div class="sgroup">
              <div class="field">
                <label class="field-label" for="workspace-path">当前工作区</label>
                <div class="workspace-row">
                  <input id="workspace-path" :value="workspaceDisplay" readonly class="mono workspace-path" />
                  <button class="btn" type="button" @click="pickWorkspace">
                    <AppIcon name="folder" :size="14" />选择目录
                  </button>
                  <button class="btn" type="button" @click="resetWorkspace" :disabled="!form.workspace">恢复默认</button>
                </div>
                <p class="field-hint">
                  文件工具（ls / read_file / write_file / edit_file / glob / grep）与 shell 都以此目录为根，相对路径相对它解析；留空则使用应用内部 runtime 目录。
                </p>
                <p class="field-hint">
                  技能库与任务清单始终留在应用数据目录，不受工作区影响；正在生成的那一轮仍使用旧工作区，下一条消息起生效。
                </p>
              </div>
            </div>
          </div>
        </section>

        <!-- 数据与备份 -->
        <section v-show="activeSection === 'backup'" class="panel" aria-labelledby="sec-backup">
          <header class="panel-head">
            <span class="panel-icon"><AppIcon name="package" :size="16" /></span>
            <div class="panel-head-text">
              <h2 id="sec-backup" class="panel-title">数据与备份</h2>
              <p class="panel-sub">导出配置、对话与向量库，方便换机迁移</p>
            </div>
          </header>
          <div class="panel-body">
            <div class="sgroup">
              <div class="field">
                <label class="field-label">导出备份</label>
                <div class="actions">
                  <button class="btn primary" type="button" :disabled="backupBusy" @click="exportBackupAction">
                    <span v-if="backupBusy" class="btn-spinner"></span>
                    {{ backupBusy ? '正在导出…' : '选择目录并导出' }}
                  </button>
                  <span class="field-hint">会生成独立的 sassy-cat-backup-日期-时间 目录</span>
                </div>
                <ul class="backup-list">
                  <li><span class="bl-key">包含</span>config.user.json、messages.sqlite（一致性快照）、Chroma 向量库、上传文件、MCP 服务器配置与技能库</li>
                  <li><span class="bl-key">不含</span>体积通常很大的 checkpoints.sqlite（Agent 现场）</li>
                  <li><span class="bl-key">注意</span>备份内含 API Key 等敏感配置，请妥善保管</li>
                  <li><span class="bl-key">迁移</span>退出优墨后，把备份目录内容覆盖到新机器的 userData 目录（Windows 默认 %APPDATA%\sassy-cat）</li>
                </ul>
                <div v-if="backupError" class="bad-text backup-result">{{ backupError }}</div>
                <div v-if="backupResult" class="backup-result">
                  <span class="ok">
                    <AppIcon name="check" :size="13" />
                    已导出 {{ backupResult.items?.length || 0 }} 项 · {{ formatBytes(backupResult.totalSize) }}
                  </span>
                  <code class="backup-path" :title="backupResult.path">{{ backupResult.path }}</code>
                  <button class="mini" type="button" @click="openBackupFolder">打开文件夹</button>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- 闲置提醒 -->
        <section v-show="activeSection === 'idle'" class="panel" aria-labelledby="sec-idle">
          <header class="panel-head">
            <span class="panel-icon"><AppIcon name="clock" :size="16" /></span>
            <div class="panel-head-text">
              <h2 id="sec-idle" class="panel-title">闲置提醒</h2>
              <p class="panel-sub">久未互动时让本喵叫你一声</p>
            </div>
          </header>
          <div class="panel-body">
            <div class="sgroup">
              <div class="switch-row no-line">
                <div class="switch-text">
                  <div class="switch-title">启用闲置提醒</div>
                  <p class="switch-desc">长时间没有互动时，桌宠会主动冒个泡；关闭后不再打扰。</p>
                </div>
                <label class="toggle">
                  <input type="checkbox" v-model="form.idleEnabled" aria-label="启用闲置提醒" />
                  <span class="toggle-track"><span class="toggle-thumb"></span></span>
                </label>
              </div>
              <div class="field-grid">
                <div class="field">
                  <label class="field-label" for="idle-threshold">闲置阈值（分钟）</label>
                  <input id="idle-threshold" type="number" v-model.number="form.idleThreshold" min="1" :disabled="!form.idleEnabled" />
                </div>
                <div class="field">
                  <label class="field-label" for="idle-quiet">提醒冷却（分钟）</label>
                  <input id="idle-quiet" type="number" v-model.number="form.idleQuiet" min="1" :disabled="!form.idleEnabled" />
                  <p class="field-hint">两次提醒之间至少间隔这么久，避免连续打扰。</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- 提醒事项 -->
        <section v-show="activeSection === 'reminder'" class="panel" aria-labelledby="sec-reminder">
          <header class="panel-head">
            <span class="panel-icon"><AppIcon name="bell" :size="16" /></span>
            <div class="panel-head-text">
              <h2 id="sec-reminder" class="panel-title">提醒事项</h2>
              <p class="panel-sub">检查频率与气泡停留时长</p>
            </div>
          </header>
          <div class="panel-body">
            <div class="sgroup">
              <div class="field-grid">
                <div class="field">
                  <label class="field-label">检查间隔（秒）</label>
                  <div class="stepper">
                    <button type="button" class="step-btn" @click="step('reminderPoll', -1, 3, 30)" :disabled="form.reminderPoll <= 3"><AppIcon name="minus" :size="14" /></button>
                    <input type="number" v-model.number="form.reminderPoll" min="3" max="30" class="step-input"
                      @blur="clamp('reminderPoll', 3, 30, 5)" />
                    <button type="button" class="step-btn" @click="step('reminderPoll', 1, 3, 30)" :disabled="form.reminderPoll >= 30"><AppIcon name="plus" :size="14" /></button>
                  </div>
                  <p class="field-hint">范围 3~30 秒，默认 5 秒；越小触发越及时。</p>
                </div>
                <div class="field">
                  <label class="field-label" for="reminder-duration">气泡显示时长（秒）</label>
                  <select id="reminder-duration" v-model.number="form.reminderDuration">
                    <option v-for="d in reminderDurationOptions" :key="d" :value="d">{{ d }} 秒</option>
                  </select>
                  <p class="field-hint">提醒弹出时桌宠气泡的停留时长，默认 8 秒。</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- 网络代理 -->
        <section v-show="activeSection === 'proxy'" class="panel" aria-labelledby="sec-proxy">
          <header class="panel-head">
            <span class="panel-icon"><AppIcon name="globe" :size="16" /></span>
            <div class="panel-head-text">
              <h2 id="sec-proxy" class="panel-title">网络代理</h2>
              <p class="panel-sub">HTTP / HTTPS 代理与直连白名单</p>
            </div>
          </header>
          <div class="panel-body">
            <div class="sgroup">
              <div class="switch-row no-line">
                <div class="switch-text">
                  <div class="switch-title">启用 HTTP / HTTPS 代理</div>
                  <p class="switch-desc">保存后 Electron 立即生效；Python Agent 需在启用 / 停用后点击顶部「重启服务进程」以刷新代理环境变量。</p>
                </div>
                <label class="toggle">
                  <input type="checkbox" v-model="form.proxyEnabled" aria-label="启用 HTTP / HTTPS 代理" />
                  <span class="toggle-track"><span class="toggle-thumb"></span></span>
                </label>
              </div>
              <div class="field-grid">
                <div class="field">
                  <label class="field-label" for="proxy-http">HTTP 代理</label>
                  <input id="proxy-http" v-model="form.proxyHttp" placeholder="http://127.0.0.1:7890" :disabled="!form.proxyEnabled" />
                  <p class="field-hint">支持 http:// 或 socks5:// 前缀。</p>
                </div>
                <div class="field">
                  <label class="field-label" for="proxy-https">HTTPS 代理</label>
                  <input id="proxy-https" v-model="form.proxyHttps" placeholder="留空则与 HTTP 代理相同" :disabled="!form.proxyEnabled" />
                </div>
                <div class="field span-2">
                  <label class="field-label" for="proxy-no">绕过代理（NO_PROXY）</label>
                  <input id="proxy-no" v-model="form.proxyNoProxy" placeholder="localhost,127.0.0.1,*.example.com" :disabled="!form.proxyEnabled" />
                  <p class="field-hint">逗号分隔的主机名单，命中这些地址的请求不走代理。</p>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>

    <div v-if="toast" class="toast" role="status">{{ toast }}</div>

    <!-- 新增 LLM 配置档弹窗 -->
    <div v-if="showAddProfile" class="modal-overlay" @click.self="showAddProfile = false">
      <div class="modal" role="dialog" aria-modal="true" aria-labelledby="add-profile-title">
        <h3 id="add-profile-title">新增 LLM 配置档</h3>
        <div class="field">
          <label class="field-label" for="new-profile-name">配置档名称</label>
          <input id="new-profile-name" v-model="newProfileName" placeholder="例如 work、personal" @keydown.enter="addProfile" ref="profileNameInput" />
          <p class="field-hint" :class="{ bad: newProfileError }">{{ newProfileError || '仅允许字母、数字、下划线和短横线' }}</p>
        </div>
        <div class="modal-actions">
          <button class="btn" type="button" @click="showAddProfile = false">取消</button>
          <button class="btn primary" type="button" @click="addProfile">确定</button>
        </div>
      </div>
    </div>

    <!-- 新增 Agent 配置档弹窗 -->
    <div v-if="showAddAgentProfile" class="modal-overlay" @click.self="showAddAgentProfile = false">
      <div class="modal" role="dialog" aria-modal="true" aria-labelledby="add-agent-title">
        <h3 id="add-agent-title">新增 Agent 配置档</h3>
        <div class="field">
          <label class="field-label" for="new-agent-name">配置档名称</label>
          <input id="new-agent-name" v-model="newAgentProfileName" placeholder="例如 work、personal" @keydown.enter="addAgentProfile" ref="agentProfileNameInput" />
          <p class="field-hint" :class="{ bad: newAgentProfileError }">{{ newAgentProfileError || '仅允许字母、数字、下划线和短横线' }}</p>
        </div>
        <div class="modal-actions">
          <button class="btn" type="button" @click="showAddAgentProfile = false">取消</button>
          <button class="btn primary" type="button" @click="addAgentProfile">确定</button>
        </div>
      </div>
    </div>

    <!-- 切换 Embedding 模型确认弹窗 -->
    <div v-if="showEmbedConfirm" class="modal-overlay" @click.self="cancelEmbedChange">
      <div class="modal" role="dialog" aria-modal="true" aria-labelledby="embed-confirm-title">
        <h3 id="embed-confirm-title">确认切换 Embedding 模型？</h3>
        <p class="field-hint modal-copy">
          切换后，知识库中所有已入库文档的向量数据将不再匹配，需要重新 Embedding 才能继续使用。
          <br />
          是否确认切换？
        </p>
        <div class="modal-actions">
          <button class="btn" type="button" @click="cancelEmbedChange">取消</button>
          <button class="btn primary" type="button" @click="confirmEmbedChange">确认切换</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAgentSocket } from '../composables/useAgentSocket'
import { useRestartState } from '../composables/useRestartState'
import { useModelDownloadState } from '../composables/useModelDownloadState'
import { useTTS } from '../composables/useTTS'
import { useTheme } from '../composables/useTheme'
import { downloadEmbeddingModel } from '../api/embeddingModelDownload'
import { getRagHealth, getRebuildStatus, rebuildKbIndex } from '../api/kb'
import { exportBackup } from '../api/backup'
import AppIcon from '../components/AppIcon.vue'

const { connect, send, on } = useAgentSocket()
const api = window.electronAPI
const { mode: themeMode, setTheme } = useTheme()
const themeOptions = [
  { value: 'dark', label: '深色', icon: 'moon' },
  { value: 'light', label: '浅色', icon: 'sun' },
  { value: 'system', label: '跟随系统', icon: 'monitor' },
]
const route = useRoute()

// 分类导航：左侧分类 + 右侧单面板。整页原本是 12 张卡片纵向堆叠，
// 模型连接一张就有 20+ 字段，改成「一次只看一组」，面板内部再分组/折叠。
const pageEl = ref(null)
const activeSection = ref('theme')
const navGroups = [
  {
    title: '常规',
    items: [
      { id: 'theme', label: '外观主题', icon: 'sun' },
      { id: 'pet', label: '桌宠', icon: 'bot' },
      { id: 'voice', label: '语音朗读', icon: 'volume' },
    ],
  },
  {
    title: '模型与 Agent',
    items: [
      { id: 'llm', label: '模型连接', icon: 'plug' },
      { id: 'agent', label: 'Agent 配置', icon: 'brain' },
      { id: 'dsh', label: 'dsh 子代理', icon: 'layers' },
    ],
  },
  {
    title: '知识与数据',
    items: [
      { id: 'rag', label: '知识库', icon: 'database' },
      { id: 'workspace', label: '工作区', icon: 'folder' },
      { id: 'backup', label: '数据与备份', icon: 'package' },
    ],
  },
  {
    title: '提醒与系统',
    items: [
      { id: 'idle', label: '闲置提醒', icon: 'clock' },
      { id: 'reminder', label: '提醒事项', icon: 'bell' },
      { id: 'proxy', label: '网络代理', icon: 'globe' },
    ],
  },
]

function selectSection(id) {
  activeSection.value = id
  // 切换分类时回到页面顶部，否则会停在上一组滚动到一半的位置
  pageEl.value?.closest('.content')?.scrollTo({ top: 0 })
}

// 「前往下载模型」深链：面板是 v-show 隐藏的，必须先激活知识库再滚动定位
function revealRagModel() {
  activeSection.value = 'rag'
  nextTick(() => {
    setTimeout(() => {
      document.getElementById('rag-model')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }, 300)
  })
}

// 语音朗读（TTS）：中文语音枚举、试听、配置刷新
const { getZhVoices, testVoice, loadConfig: loadTtsConfig, ttsState, speaking } = useTTS()

// 模块级单例状态：切换 tab 导致组件卸载/重新挂载时，重启进度与提示不丢失
const { restarting, restartDone, toast } = useRestartState()
// 模型下载进度同样为模块级单例：下载中切换 tab 后动画与结果不丢失
const { downloading, result: downloadResult } = useModelDownloadState()

const activeProfile = ref('default')
const profiles = ref({})
const activeAgentProfile = ref('default')
const agentProfiles = ref({})

// ---- RAG 索引健康 / 全量重建 ----
const ragHealth = ref(null)
const ragHealthLoading = ref(false)

// ---- 数据备份 ----
const backupBusy = ref(false)
const backupResult = ref(null)
const backupError = ref('')

function formatBytes(bytes) {
  const n = Number(bytes || 0)
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`
}

async function exportBackupAction() {
  if (backupBusy.value) return
  const picked = await api?.pickDirectory?.({
    title: '选择备份保存位置',
    buttonLabel: '保存到此目录',
  })
  if (!picked || picked.canceled) return
  if (!picked.success) {
    backupError.value = '选择目录失败：' + (picked.message || '')
    return
  }
  backupBusy.value = true
  backupError.value = ''
  try {
    backupResult.value = await exportBackup(picked.path)
  } catch (e) {
    backupError.value = `导出失败：${e.message}`
  } finally {
    backupBusy.value = false
  }
}

function openBackupFolder() {
  if (backupResult.value?.path) api?.openPath?.(backupResult.value.path)
}
const ragRebuild = reactive({
  running: false, total: 0, done: 0, failed: 0, current: '', finishedAt: null,
})
let ragPollTimer = null
const ragRebuildPercent = computed(() => {
  if (!ragRebuild.total) return ragRebuild.running ? 3 : 0
  return Math.min(100, Math.round((ragRebuild.done / ragRebuild.total) * 100))
})

function shortError(text, max = 140) {
  const s = String(text || '')
  return s.length > max ? s.slice(0, max) + '…' : s
}

async function loadRagHealth() {
  ragHealthLoading.value = true
  try {
    const res = await getRagHealth()
    ragHealth.value = res
    if (res.rebuild) Object.assign(ragRebuild, res.rebuild)
    if (ragRebuild.running) startRagPoll()
  } catch (e) {
    ragHealth.value = { error: e.message }
  } finally {
    ragHealthLoading.value = false
  }
}

function stopRagPoll() {
  if (ragPollTimer) {
    clearInterval(ragPollTimer)
    ragPollTimer = null
  }
}

function startRagPoll() {
  if (ragPollTimer) return
  ragPollTimer = setInterval(async () => {
    try {
      const state = await getRebuildStatus()
      Object.assign(ragRebuild, state)
      if (!state.running) {
        stopRagPoll()
        await loadRagHealth()
      }
    } catch {
      // 轮询失败不弹窗；下一轮继续尝试
    }
  }, 1200)
}

async function startRagRebuild() {
  if (ragRebuild.running) return
  const ok = window.confirm(
    '重建全部知识库索引？\n\n会先清空现有向量，再按原始文件重新 OCR / 分块 / embedding。\n源文件已丢失的文档会被标记为失败。'
  )
  if (!ok) return
  try {
    const state = await rebuildKbIndex()
    Object.assign(ragRebuild, state)
    startRagPoll()
  } catch (e) {
    window.alert('启动重建失败：' + e.message)
  }
}
// 主 Agent 当前激活 LLM 摘要：dsh 勾选「复用主 Agent」时用于提示实际生效的连接
const mainLlmSummary = computed(() => {
  const p = profiles.value[activeProfile.value] || {}
  return `${p.model || '未设置模型'} · ${p.baseUrl || '未设置 Base URL'}`
})
// 工作区展示：未设置时说明回退到应用内部目录
const workspaceDisplay = computed(() => form.workspace || '默认：应用内部 runtime 目录')
// 提醒气泡显示时长可选值（秒），范围 3~30
const reminderDurationOptions = [3, 5, 8, 10, 15, 20, 30]
// 主 Agent LLM 上下文窗口（token）：范围与默认值与 config_loader.DEFAULTS 保持一致
const DEFAULT_CONTEXT_WINDOW = 262144
const CONTEXT_WINDOW_MIN = 8192
const CONTEXT_WINDOW_MAX = 1048576
// 单次回复最大输出 token（maxTokens）：范围与默认值与 config_loader.DEFAULTS 保持一致
const DEFAULT_MAX_TOKENS = 8192
const MAX_TOKENS_MIN = 256
const MAX_TOKENS_MAX = 1048576
// 上下文自动压缩（llm.profiles.<name>.contextCompression）：触发百分比与保留条数的范围/默认值，
// 与 config_loader.DEFAULTS 及 agent/engine.py 的解析逻辑保持一致
const DEFAULT_CC_THRESHOLD = 80
const CC_THRESHOLD_MIN = 10
const CC_THRESHOLD_MAX = 95
const DEFAULT_CC_RETAIN_TOKENS = 0
const CC_RETAIN_TOKENS_MAX = 65536
const DEFAULT_CC_SUMMARY_INPUT = 65536
const CC_SUMMARY_INPUT_MAX = 262144
const DEFAULT_CC_HEADROOM = 8192
const CC_HEADROOM_MAX = 65536
// 媒体守卫（contextCompression.media*，见 agent/middlewares.py::trim_media_history）：
// 图片默认全量保留、逐张压缩；只有总预算超限才从最旧一端 offload。
const DEFAULT_MEDIA_MAX_KB = 1024
const MEDIA_MAX_KB_MIN = 0
const MEDIA_MAX_KB_MAX = 16384
const DEFAULT_MEDIA_MAX_PX = 1568
const MEDIA_MAX_PX_MIN = 256
const MEDIA_MAX_PX_MAX = 4096
const DEFAULT_MEDIA_BUDGET_KB = 8192
const MEDIA_BUDGET_KB_MAX = 131072
const DEFAULT_MEDIA_MAX_IMAGES = 24
const MEDIA_MAX_IMAGES_MAX = 200
const DEFAULT_MEDIA_OFFLOAD_KB = 1024
const MEDIA_OFFLOAD_KB_MAX = 16384
// dsh 子代理：输出上限（DashScope qwen 系只接受 [1,131072]）与推理强度可选值
const DSH_MAX_TOKENS_LIMIT = 131072
const dshReasoningEffortOptions = [
  { value: '', label: '不指定（适配器默认）' },
  { value: 'off', label: 'off（关闭思考）' },
  { value: 'low', label: 'low' },
  { value: 'high', label: 'high' },
  { value: 'max', label: 'max' },
]
// 高危工具人工确认清单（与 Python agent/engine.py 的 interrupt_on 工具集对应）
const interruptTools = [
  { name: 'execute', label: '执行命令（execute）' },
  { name: 'write_file', label: '写入文件（write_file）' },
  { name: 'edit_file', label: '编辑文件（edit_file）' },
  { name: 'delete', label: '删除文件（delete）' },
  { name: 'call_dsh', label: '委托子代理（call_dsh）' },
]
const defaultInterruptOn = () => Object.fromEntries(interruptTools.map((t) => [t.name, true]))
const form = reactive({
  provider: 'openai', baseUrl: '', apiKey: '', model: '', temperature: 0.7, contextWindow: DEFAULT_CONTEXT_WINDOW, maxTokens: DEFAULT_MAX_TOKENS, extraParamsText: '{}',
  // 上下文自动压缩（随当前 LLM 配置档保存）
  contextCompressionEnabled: true, contextCompressionModel: '', contextCompressionThreshold: DEFAULT_CC_THRESHOLD,
  contextCompressionRetainTokens: DEFAULT_CC_RETAIN_TOKENS, contextCompressionSummaryInput: DEFAULT_CC_SUMMARY_INPUT, contextCompressionHeadroom: DEFAULT_CC_HEADROOM,
  // 媒体守卫（同样随当前 LLM 配置档保存；不受上面的自动压缩开关影响）
  contextMediaMaxKB: DEFAULT_MEDIA_MAX_KB, contextMediaMaxPx: DEFAULT_MEDIA_MAX_PX,
  contextMediaBudgetKB: DEFAULT_MEDIA_BUDGET_KB, contextMediaMaxImages: DEFAULT_MEDIA_MAX_IMAGES, contextMediaOffloadKB: DEFAULT_MEDIA_OFFLOAD_KB,
  persona: '', memoryWindow: 50, recursionLimit: 100, idleEnabled: true, idleThreshold: 30, idleQuiet: 10,
  // 工作区（agent.workspace，空=应用内部 runtime；切换即时保存，不随配置档保存）
  workspace: '',
  petEnabled: true,
  petSize: 1, petOpacity: 1, dndEnabled: false, dndStart: '22:00', dndEnd: '08:00',
  quickAskShortcut: 'Alt+Shift+Q',
  reminderPoll: 5, reminderDuration: 8,
  tavilyApiKey: '',
  dsApiKey: '',
  agentEnableOcr: true, agentOcrEngine: 'markitdown',
  interruptOn: defaultInterruptOn(),
  // 技能脚本免确认（execute 白名单，见 python/agent/command_policy.py）
  autoApproveSkillScripts: true,
  ragAutoEmbedding: true, ragHybrid: true, ragChunkSize: 1000, ragChunkOverlap: 200, ragCandidateMultiplier: 4, ragEmbedType: 'local', ragEmbedModel: 'BAAI/bge-small-zh-v1.5',
  ragEmbedBaseUrl: '', ragEmbedApiKey: '', ragOcrEngine: 'docling',
  ragLocalDownloaded: false,
  proxyEnabled: false, proxyHttp: '', proxyHttps: '', proxyNoProxy: '',
  // dsh 子代理（顶层独立配置块 dsh.*）
  dshUseMainLlm: true, dshBaseUrl: '', dshApiKey: '', dshModel: '',
  dshSystemPrompt: '', dshMaxTokens: DSH_MAX_TOKENS_LIMIT, dshReasoningEffort: '',
  voiceEnabled: false, voiceEngine: 'web-speech', voiceAutoRead: false,
  voiceVoiceName: '', voiceRate: 1, voicePitch: 1
})

const recordingKey = ref(false)
const hotkeyError = ref('')
const hotkeyStatus = ref(null)
const showKey = ref(false)
const showTavilyKey = ref(false)
const showDsKey = ref(false)
const showRagKey = ref(false)
const showDshKey = ref(false)
const dshKeyRevealed = ref(false)
// 模板层（config.json）内置默认 dsh 提示词，供「恢复默认提示词」还原
const defaultDshPrompt = ref('')
const extraError = ref('')
const testing = ref(false)
const testResult = ref(null)
const preview = ref('')
const keyRevealed = ref(false)
const showAddProfile = ref(false)
const newProfileName = ref('')
const newProfileError = ref('')
const profileNameInput = ref(null)
const showAddAgentProfile = ref(false)
const newAgentProfileName = ref('')
const newAgentProfileError = ref('')
const agentProfileNameInput = ref(null)

// Embedding 模型切换确认：记录已保存（配置中落盘）的模型来源与名称，
// 变更时弹窗提示知识库文档需要重新 Embedding
let savedEmbedType = 'local'
let savedEmbedModel = ''
const showEmbedConfirm = ref(false)
const embedPendingChange = ref(null) // { kind: 'type' | 'model', value: 新值 }

// 弹窗打开时自动聚焦输入框
// 弹窗打开时自动聚焦输入框
watch(showAddProfile, (val) => {
  if (val) {
    newProfileName.value = ''
    newProfileError.value = ''
    nextTick(() => profileNameInput.value?.focus())
  }
})
watch(showAddAgentProfile, (val) => {
  if (val) {
    newAgentProfileName.value = ''
    newAgentProfileError.value = ''
    nextTick(() => agentProfileNameInput.value?.focus())
  }
})
function showToast(text) {
  toast.value = text
  setTimeout(() => (toast.value = ''), 2500)
}

function validateExtra() {
  try { JSON.parse(form.extraParamsText || '{}'); extraError.value = '' }
  catch (e) { extraError.value = 'JSON 格式错误' }
}

function clamp(key, min, max, fallback) {
  const v = Number(form[key])
  if (!Number.isFinite(v)) { form[key] = fallback; return }
  form[key] = Math.min(max, Math.max(min, Math.round(v)))
}

function step(key, delta, min, max) {
  const cur = Number(form[key])
  const base = Number.isFinite(cur) ? cur : min
  form[key] = Math.min(max, Math.max(min, base + delta))
}

// 高危操作确认：一键全部打断 / 全部放行
function setAllInterrupt(value) {
  for (const t of interruptTools) form.interruptOn[t.name] = value
}

// ---------- 语音朗读（TTS） ----------
// 中文语音下拉选项（响应式：系统语音异步就绪后自动刷新）
const voiceOptions = computed(() => getZhVoices())

// 简洁化语音名：去 Microsoft 前缀与中文区段，避免下拉框被全名撑爆
function voiceLabel(v) {
  const raw = v.name || ''
  const short = raw
    .replace(/^Microsoft\s*/i, '')
    .replace(/\s*\(Natural\)\s*-\s*Chinese/i, '')
    .replace(/\s*-{1,2}\s*Chinese\s*\([^)]*\)\s*$/i, '')
    .replace(/\s*\(zh-CN\)\s*$/i, '')
    .trim() || raw
  const lang = (v.lang || '').replace('_', '-')
  const tag = v.localService ? '· 本地' : v.online ? '· 在线' : ''
  return `${short}（${lang}${tag}）`
}

const voiceNoVoicesHint = computed(() => {
  if (!ttsState.ready) return '未检测到系统语音，请检查系统「语音」设置。'
  return '未检测到中文语音，可能需要安装中文语言包（Win10/11 自带 Huihui / Kangkang / Yaoyao）；将自动使用系统默认语音朗读。'
})

// 试听：用当前表单（未保存）的语音/语速/音调试读一句话
// 试听是否进行中（useTTS 播放 voice-test 时置位，播完/停止后复位）
const testingVoice = computed(() => speaking.value === 'voice-test')

function voicePreview() {
  const ok = testVoice('喵～本喵就是这么可爱！', {
    voiceName: form.voiceVoiceName,
    rate: form.voiceRate,
    pitch: form.voicePitch,
  })
  if (!ok) showToast('系统不支持语音播放，或未检测到语音引擎')
}

async function loadConfig() {
  const res = await api.getConfig()
  if (!res.success) return showToast('配置加载失败')
  const cfg = res.config
  profiles.value = cfg.llm?.profiles || { default: { label: '默认' } }
  activeProfile.value = cfg.llm?.activeProfile || 'default'
  agentProfiles.value = cfg.agent?.profiles || { default: { label: '默认' } }
  activeAgentProfile.value = cfg.agent?.activeProfile || 'default'
  fillFormFromProfile()
  form.idleEnabled = cfg.pet?.idleReminder?.enabled !== false
  form.workspace = cfg.agent?.workspace || ''
  form.idleThreshold = cfg.pet?.idleReminder?.thresholdMinutes ?? 30
  form.idleQuiet = cfg.pet?.idleReminder?.quietPeriodMinutes ?? 10
  form.petEnabled = cfg.pet?.enabled !== false
  form.petSize = Number(cfg.pet?.appearance?.size) || 1
  form.petOpacity = Number(cfg.pet?.appearance?.opacity) || 1
  form.dndEnabled = cfg.pet?.doNotDisturb?.enabled === true
  form.dndStart = cfg.pet?.doNotDisturb?.start || '22:00'
  form.dndEnd = cfg.pet?.doNotDisturb?.end || '08:00'
  form.quickAskShortcut = cfg.pet?.quickAsk?.shortcut ?? 'Alt+Shift+Q'
  // 提醒事项
  form.reminderPoll = cfg.pet?.reminders?.pollIntervalSeconds ?? 5
  const durSec = Math.round((cfg.pet?.reminders?.bubbleDurationMs ?? 8000) / 1000)
  form.reminderDuration = reminderDurationOptions.includes(durSec)
    ? durSec
    : reminderDurationOptions.reduce((a, b) => Math.abs(b - durSec) < Math.abs(a - durSec) ? b : a)
  // 网络代理
  form.proxyEnabled = cfg.network?.proxy?.enabled === true
  form.proxyHttp = cfg.network?.proxy?.http || ''
  form.proxyHttps = cfg.network?.proxy?.https || ''
  form.proxyNoProxy = cfg.network?.proxy?.noProxy || ''
  // 语音朗读（TTS）
  form.voiceEnabled = cfg.voice?.enabled === true
  form.voiceEngine = cfg.voice?.engine || 'web-speech'
  form.voiceAutoRead = cfg.voice?.autoRead === true
  form.voiceVoiceName = cfg.voice?.voiceName || ''
  form.voiceRate = cfg.voice?.rate ?? 1
  form.voicePitch = cfg.voice?.pitch ?? 1
  // Tavily API Key：掩码处理
  const tavilyKey = cfg.agent?.tavilyApiKey || ''
  form.tavilyApiKey = tavilyKey.length > 3 ? '***' + tavilyKey.slice(-3) : tavilyKey
  // DeepSeek API Key：同样掩码处理
  const dsKey = cfg.agent?.dsApiKey || ''
  form.dsApiKey = dsKey.length > 3 ? '***' + dsKey.slice(-3) : dsKey
  // 对话 OCR 引擎（开关缺省视为开启，与后端默认一致）
  form.agentEnableOcr = cfg.agent?.enableOcr !== false
  form.agentOcrEngine = cfg.agent?.ocrEngine === 'docling' ? 'docling' : 'markitdown'
  // 高危操作人工确认：缺省视为打断（与后端默认一致）
  const interruptOn = cfg.agent?.interruptOn || {}
  form.interruptOn = Object.fromEntries(
    interruptTools.map((t) => [t.name, interruptOn[t.name] !== false])
  )
  // 技能脚本免确认：缺省视为开启（与 Python DEFAULTS 一致）
  form.autoApproveSkillScripts = cfg.agent?.autoApproveSkillScripts !== false
  // 知识库（RAG）
  form.ragAutoEmbedding = cfg.rag?.autoEmbedding !== false
  form.ragHybrid = cfg.rag?.retrieval?.hybrid !== false
  form.ragChunkSize = Number(cfg.rag?.retrieval?.chunkSize) || 1000
  form.ragChunkOverlap = Number(cfg.rag?.retrieval?.chunkOverlap) || 0
  form.ragCandidateMultiplier = Number(cfg.rag?.retrieval?.candidateMultiplier) || 4
  form.ragEmbedType = cfg.rag?.embeddingModel?.type === 'remote' ? 'remote' : 'local'
  form.ragEmbedModel = cfg.rag?.embeddingModel?.model || ''
  // 本地模型已下载状态（下载成功后由本页面写入配置，切换回来即不再显示下载按钮）
  form.ragLocalDownloaded = cfg.rag?.embeddingModel?.downloaded === true
  form.ragEmbedBaseUrl = cfg.rag?.embeddingModel?.baseUrl || ''
  const ragKey = cfg.rag?.embeddingModel?.apiKey || ''
  form.ragEmbedApiKey = ragKey.length > 3 ? '***' + ragKey.slice(-3) : ragKey
  form.ragOcrEngine = cfg.rag?.ocrEngine === 'markitdown' ? 'markitdown' : 'docling'
  // 记录已保存的 Embedding 配置，用于判断用户是否切换了模型
  savedEmbedType = form.ragEmbedType
  savedEmbedModel = form.ragEmbedModel
  // dsh 子代理（顶层独立配置块，缺省视为「复用主 Agent LLM」）
  form.dshUseMainLlm = cfg.dsh?.useMainLlm !== false
  form.dshBaseUrl = cfg.dsh?.llm?.baseUrl || ''
  const dshKey = cfg.dsh?.llm?.apiKey || ''
  form.dshApiKey = dshKey.length > 3 ? '***' + dshKey.slice(-3) : dshKey
  form.dshModel = cfg.dsh?.llm?.model || ''
  form.dshSystemPrompt = cfg.dsh?.systemPrompt || ''
  form.dshMaxTokens = cfg.dsh?.maxTokens ?? DSH_MAX_TOKENS_LIMIT
  form.dshReasoningEffort = cfg.dsh?.reasoningEffort || ''
  dshKeyRevealed.value = false
  // 内置默认 dsh 提示词取自模板层（用户层只会覆盖它，取不回来）
  const tpl = await api.getConfigTemplate?.()
  if (tpl && tpl.success) defaultDshPrompt.value = tpl.template?.dsh?.systemPrompt || ''
}

// ---------- 快捷键录制 ----------
const hotkeyDisplay = computed(() => {
  if (recordingKey.value) return '按下组合键…'
  return form.quickAskShortcut || '未设置（已禁用）'
})

// KeyboardEvent -> Electron accelerator 字符串
function eventToAccelerator(e) {
  const mods = []
  if (e.ctrlKey) mods.push('Ctrl')
  if (e.altKey) mods.push('Alt')
  if (e.shiftKey) mods.push('Shift')
  if (e.metaKey) mods.push('Super')
  const KEY_MAP = {
    Control: 'Ctrl', Alt: 'Alt', Shift: 'Shift', Meta: 'Super',
    ArrowUp: 'Up', ArrowDown: 'Down', ArrowLeft: 'Left', ArrowRight: 'Right',
    ' ': 'Space', Escape: 'Esc', Delete: 'Delete', Backspace: 'Backspace',
    PageUp: 'PageUp', PageDown: 'PageDown', Home: 'Home', End: 'End', Insert: 'Insert'
  }
  let key = KEY_MAP[e.key]
  if (!key) {
    if (e.key.length === 1) {
      key = e.key.toUpperCase()
    } else if (/^F\d{1,2}$/.test(e.key)) {
      key = e.key
    } else {
      return null // 不支持的键（如 CapsLock、输入法键等）
    }
  }
  if (mods.includes(key)) return null // 纯修饰键组合无效
  if (!mods.length) {
    hotkeyError.value = '快捷键必须包含至少一个修饰键（Ctrl / Alt / Shift / Win）'
    return null
  }
  hotkeyError.value = ''
  return [...mods, key].join('+')
}

function startRecord() {
  recordingKey.value = true
  hotkeyError.value = ''
}

function stopRecord() {
  recordingKey.value = false
  hotkeyError.value = ''
}

async function onRecordKeydown(e) {
  if (!recordingKey.value) return
  if (e.key === 'Escape') { stopRecord(); return }
  const acc = eventToAccelerator(e)
  if (!acc) return
  recordingKey.value = false
  // 立即保存并等待主进程注册结果（注册失败时可再次录制换键）
  const res = await api.setConfig('pet.quickAsk.shortcut', acc)
  if (!res.success) return showToast('保存失败: ' + (res.message || ''))
  form.quickAskShortcut = acc
  showToast('快捷键已保存，正在注册…')
}

function fillFormFromProfile() {
  const p = profiles.value[activeProfile.value] || {}
  form.provider = p.provider || 'openai'
  form.baseUrl = p.baseUrl || ''
  form.apiKey = p.apiKey || '' // 掩码值 ***abc
  form.model = p.model || ''
  // 采样温度：缺省或非法值回退 0.7，与 config_loader.DEFAULTS 保持一致
  form.temperature = Number.isFinite(Number(p.temperature)) ? Number(p.temperature) : 0.7
  // 上下文窗口：缺省或非法值回退默认值，与 config_loader.DEFAULTS 保持一致
  form.contextWindow = Number.isFinite(Number(p.contextWindow)) ? Number(p.contextWindow) : DEFAULT_CONTEXT_WINDOW
  // 最大输出 token：缺省或非法值回退默认值，与 config_loader.DEFAULTS 保持一致
  form.maxTokens = Number.isFinite(Number(p.maxTokens)) ? Number(p.maxTokens) : DEFAULT_MAX_TOKENS
  // 上下文自动压缩：缺省视为启用，阈值/保留条数非法值回退默认，与 config_loader.DEFAULTS 保持一致
  const cc = p.contextCompression || {}
  form.contextCompressionEnabled = cc.enabled !== false
  form.contextCompressionModel = cc.model || ''
  form.contextCompressionThreshold = Number.isFinite(Number(cc.threshold)) ? Number(cc.threshold) : DEFAULT_CC_THRESHOLD
  form.contextCompressionRetainTokens = Number.isFinite(Number(cc.retainTokens)) ? Number(cc.retainTokens) : DEFAULT_CC_RETAIN_TOKENS
  form.contextCompressionSummaryInput = Number.isFinite(Number(cc.summaryInputTokens)) ? Number(cc.summaryInputTokens) : DEFAULT_CC_SUMMARY_INPUT
  form.contextCompressionHeadroom = Number.isFinite(Number(cc.headroomTokens)) ? Number(cc.headroomTokens) : DEFAULT_CC_HEADROOM
  // 媒体守卫：缺省或非法值回退默认；旧版的 mediaKeep/mediaJpegQuality 已废弃
  form.contextMediaMaxKB = Number.isFinite(Number(cc.mediaMaxKB)) ? Number(cc.mediaMaxKB) : DEFAULT_MEDIA_MAX_KB
  form.contextMediaMaxPx = Number.isFinite(Number(cc.mediaMaxPx)) ? Number(cc.mediaMaxPx) : DEFAULT_MEDIA_MAX_PX
  form.contextMediaBudgetKB = Number.isFinite(Number(cc.mediaBudgetKB)) ? Number(cc.mediaBudgetKB) : DEFAULT_MEDIA_BUDGET_KB
  form.contextMediaMaxImages = Number.isFinite(Number(cc.mediaMaxImages)) ? Number(cc.mediaMaxImages) : DEFAULT_MEDIA_MAX_IMAGES
  form.contextMediaOffloadKB = Number.isFinite(Number(cc.mediaOffloadKB)) ? Number(cc.mediaOffloadKB) : DEFAULT_MEDIA_OFFLOAD_KB
  form.extraParamsText = JSON.stringify(p.extraParams || {}, null, 2)
  keyRevealed.value = false
  validateExtra()
  // Agent 配置从独立的 agent profile 读取
  const ap = agentProfiles.value[activeAgentProfile.value] || {}
  form.persona = ap.persona || ''
  form.memoryWindow = ap.memoryWindow ?? 50
  form.recursionLimit = ap.recursionLimit ?? 100
}

async function switchProfile(name) {
  activeProfile.value = name
  await api.setConfig('llm.activeProfile', name)
  fillFormFromProfile()
}

// ---------- 工作区 ----------
// 工作区是顶层 agent.workspace，不是 Agent 配置档的一部分：选择后立即落盘并热重载，
// 不依赖「保存设置」；这样切换目录和切换模型一样是即时动作。
async function pickWorkspace() {
  if (!api?.pickDirectory) return showToast('当前环境不支持目录选择')
  const picked = await api.pickDirectory({
    title: '选择工作区目录',
    defaultPath: form.workspace || undefined,
  })
  if (!picked || picked.canceled) return
  if (!picked.success) return showToast('选择目录失败: ' + (picked.message || ''))
  const res = await api.setConfig('agent.workspace', picked.path)
  if (!res.success) return showToast('保存工作区失败: ' + (res.message || ''))
  form.workspace = picked.path
  send('config.invalidate', { paths: ['agent'] })
  showToast('工作区已切换，下一条消息生效 ✓')
}

async function resetWorkspace() {
  if (!form.workspace) return
  const res = await api.setConfig('agent.workspace', '')
  if (!res.success) return showToast('保存工作区失败: ' + (res.message || ''))
  form.workspace = ''
  send('config.invalidate', { paths: ['agent'] })
  showToast('已恢复默认工作区')
}

async function switchAgentProfile(name) {
  activeAgentProfile.value = name
  await api.setConfig('agent.activeProfile', name)
  fillFormFromProfile()
}

function validateProfileName(name, existingProfiles) {
  if (!name || !name.trim()) return '请输入配置档名称'
  if (!/^[a-zA-Z0-9_-]+$/.test(name.trim())) return '仅允许字母、数字、下划线和短横线'
  if (existingProfiles[name.trim()]) return '该配置档已存在'
  return ''
}

async function addProfile() {
  const name = newProfileName.value.trim()
  const err = validateProfileName(name, profiles.value)
  if (err) { newProfileError.value = err; return }
  const base = JSON.parse(JSON.stringify(profiles.value.default || { provider: 'openai', baseUrl: '', apiKey: '', model: '', extraParams: {} }))
  base.label = name
  const res = await api.setConfig(`llm.profiles.${name}`, base)
  if (!res.success) return showToast('新增配置档失败: ' + (res.message || ''))
  newProfileName.value = ''
  newProfileError.value = ''
  showAddProfile.value = false
  await loadConfig()
  await switchProfile(name)
  showToast(`已新增 LLM 配置档「${name}」`)
}

async function deleteProfile() {
  if (activeProfile.value === 'default') return showToast('default 配置档不可删除')
  if (!confirm(`确定要删除 LLM 配置档「${activeProfile.value}」吗？此操作不可撤销。`)) return
  const name = activeProfile.value
  const cfg = await api.getConfig()
  if (!cfg.success) return showToast('读取配置失败')
  const profilesCopy = JSON.parse(JSON.stringify(cfg.config.llm?.profiles || {}))
  delete profilesCopy[name]
  const res = await api.setConfig('llm.profiles', profilesCopy)
  if (!res.success) return showToast('删除配置档失败: ' + (res.message || ''))
  await loadConfig()
  await switchProfile('default')
  showToast(`已删除 LLM 配置档「${name}」`)
}

async function addAgentProfile() {
  const name = newAgentProfileName.value.trim()
  const err = validateProfileName(name, agentProfiles.value)
  if (err) { newAgentProfileError.value = err; return }
  const base = JSON.parse(JSON.stringify(agentProfiles.value.default || { persona: '', memoryWindow: 50, recursionLimit: 100 }))
  base.label = name
  const res = await api.setConfig(`agent.profiles.${name}`, base)
  if (!res.success) return showToast('新增 Agent 配置档失败: ' + (res.message || ''))
  newAgentProfileName.value = ''
  newAgentProfileError.value = ''
  showAddAgentProfile.value = false
  await loadConfig()
  await switchAgentProfile(name)
  showToast(`已新增 Agent 配置档「${name}」`)
}

async function deleteAgentProfile() {
  if (activeAgentProfile.value === 'default') return showToast('default Agent 配置档不可删除')
  if (!confirm(`确定要删除 Agent 配置档「${activeAgentProfile.value}」吗？此操作不可撤销。`)) return
  const name = activeAgentProfile.value
  const cfg = await api.getConfig()
  if (!cfg.success) return showToast('读取配置失败')
  const agentProfilesCopy = JSON.parse(JSON.stringify(cfg.config.agent?.profiles || {}))
  delete agentProfilesCopy[name]
  const res = await api.setConfig('agent.profiles', agentProfilesCopy)
  if (!res.success) return showToast('删除 Agent 配置档失败: ' + (res.message || ''))
  await loadConfig()
  await switchAgentProfile('default')
  showToast(`已删除 Agent 配置档「${name}」`)
}

async function revealKey() {
  if (keyRevealed.value) return
  const res = await api.getRawProfileKey(activeProfile.value)
  if (res.success) { form.apiKey = res.apiKey; keyRevealed.value = true }
}

// dsh 独立 LLM 的 apiKey 同样是掩码展示，聚焦输入框时按需拉取真实值
async function revealDshKey() {
  if (dshKeyRevealed.value) return
  const res = await api.getRawDshKey?.()
  if (res && res.success) { form.dshApiKey = res.apiKey; dshKeyRevealed.value = true }
}

function resetDshPrompt() {
  form.dshSystemPrompt = defaultDshPrompt.value
  showToast('已恢复默认 dsh 提示词（保存后生效）')
}

async function saveAll() {
  validateExtra()
  if (extraError.value) return showToast('额外参数 JSON 无效，未保存')
  const llmPrefix = `llm.profiles.${activeProfile.value}`
  const agentPrefix = `agent.profiles.${activeAgentProfile.value}`
  const patches = [
    { path: 'llm.activeProfile', value: activeProfile.value },
    { path: `${llmPrefix}.provider`, value: form.provider },
    { path: `${llmPrefix}.baseUrl`, value: form.baseUrl.trim() },
    { path: `${llmPrefix}.model`, value: form.model.trim() },
    { path: `${llmPrefix}.temperature`, value: Number.isFinite(Number(form.temperature)) ? Number(form.temperature) : 0.7 },
    { path: `${llmPrefix}.contextWindow`, value: Number.isFinite(Number(form.contextWindow)) ? Number(form.contextWindow) : DEFAULT_CONTEXT_WINDOW },
    { path: `${llmPrefix}.maxTokens`, value: Number.isFinite(Number(form.maxTokens)) ? Number(form.maxTokens) : DEFAULT_MAX_TOKENS },
    // 上下文自动压缩（与当前 LLM 配置档绑定）
    { path: `${llmPrefix}.contextCompression.enabled`, value: !!form.contextCompressionEnabled },
    { path: `${llmPrefix}.contextCompression.model`, value: form.contextCompressionModel || '' },
    { path: `${llmPrefix}.contextCompression.threshold`, value: Number.isFinite(Number(form.contextCompressionThreshold)) ? Number(form.contextCompressionThreshold) : DEFAULT_CC_THRESHOLD },
    { path: `${llmPrefix}.contextCompression.retainTokens`, value: Math.max(0, Math.min(CC_RETAIN_TOKENS_MAX, Number(form.contextCompressionRetainTokens) || 0)) },
    { path: `${llmPrefix}.contextCompression.summaryInputTokens`, value: Math.max(0, Math.min(CC_SUMMARY_INPUT_MAX, Number(form.contextCompressionSummaryInput) || 0)) },
    { path: `${llmPrefix}.contextCompression.headroomTokens`, value: Math.max(0, Math.min(CC_HEADROOM_MAX, Number(form.contextCompressionHeadroom) || 0)) },
    // 媒体守卫：单图压缩目标 / 总预算 / 张数预算 / offload 阶梯（0 是合法值，故用 isFinite）
    { path: `${llmPrefix}.contextCompression.mediaMaxKB`, value: Number.isFinite(Number(form.contextMediaMaxKB)) ? Number(form.contextMediaMaxKB) : DEFAULT_MEDIA_MAX_KB },
    { path: `${llmPrefix}.contextCompression.mediaMaxPx`, value: Number.isFinite(Number(form.contextMediaMaxPx)) ? Number(form.contextMediaMaxPx) : DEFAULT_MEDIA_MAX_PX },
    { path: `${llmPrefix}.contextCompression.mediaBudgetKB`, value: Number.isFinite(Number(form.contextMediaBudgetKB)) ? Number(form.contextMediaBudgetKB) : DEFAULT_MEDIA_BUDGET_KB },
    { path: `${llmPrefix}.contextCompression.mediaMaxImages`, value: Number.isFinite(Number(form.contextMediaMaxImages)) ? Number(form.contextMediaMaxImages) : DEFAULT_MEDIA_MAX_IMAGES },
    { path: `${llmPrefix}.contextCompression.mediaOffloadKB`, value: Number.isFinite(Number(form.contextMediaOffloadKB)) ? Number(form.contextMediaOffloadKB) : DEFAULT_MEDIA_OFFLOAD_KB },
    { path: `${llmPrefix}.extraParams`, value: JSON.parse(form.extraParamsText || '{}') },
    { path: 'agent.activeProfile', value: activeAgentProfile.value },
    { path: `${agentPrefix}.persona`, value: form.persona },
    { path: `${agentPrefix}.memoryWindow`, value: Number(form.memoryWindow) || 50 },
    { path: `${agentPrefix}.recursionLimit`, value: Number(form.recursionLimit) || 100 },
    { path: 'pet.idleReminder.enabled', value: form.idleEnabled },
    { path: 'pet.idleReminder.thresholdMinutes', value: form.idleThreshold },
    { path: 'pet.idleReminder.quietPeriodMinutes', value: form.idleQuiet },
    { path: 'pet.enabled', value: !!form.petEnabled },
    { path: 'pet.appearance.size', value: Math.max(0.75, Math.min(1.3, Number(form.petSize) || 1)) },
    { path: 'pet.appearance.opacity', value: Math.max(0.35, Math.min(1, Number(form.petOpacity) || 1)) },
    { path: 'pet.doNotDisturb.enabled', value: !!form.dndEnabled },
    { path: 'pet.doNotDisturb.start', value: form.dndStart || '22:00' },
    { path: 'pet.doNotDisturb.end', value: form.dndEnd || '08:00' },
    { path: 'pet.reminders.pollIntervalSeconds', value: Number(form.reminderPoll) || 5 },
    { path: 'pet.reminders.bubbleDurationMs', value: (Number(form.reminderDuration) || 8) * 1000 },
    { path: 'pet.quickAsk.shortcut', value: form.quickAskShortcut },
    { path: 'network.proxy.enabled', value: !!form.proxyEnabled },
    { path: 'network.proxy.http', value: form.proxyHttp.trim() },
    { path: 'network.proxy.https', value: form.proxyHttps.trim() },
    { path: 'network.proxy.noProxy', value: form.proxyNoProxy.trim() },
    // 语音朗读（TTS）
    { path: 'voice.enabled', value: !!form.voiceEnabled },
    { path: 'voice.engine', value: form.voiceEngine || 'web-speech' },
    { path: 'voice.autoRead', value: !!form.voiceAutoRead },
    { path: 'voice.voiceName', value: form.voiceVoiceName },
    { path: 'voice.rate', value: Number(form.voiceRate) || 1 },
    { path: 'voice.pitch', value: Number(form.voicePitch) || 1 },
    { path: 'agent.enableOcr', value: !!form.agentEnableOcr },
    { path: 'agent.ocrEngine', value: form.agentOcrEngine === 'docling' ? 'docling' : 'markitdown' },
    { path: 'agent.interruptOn', value: { ...form.interruptOn } },
    { path: 'agent.autoApproveSkillScripts', value: !!form.autoApproveSkillScripts },
    { path: 'rag.autoEmbedding', value: !!form.ragAutoEmbedding },
    { path: 'rag.retrieval.hybrid', value: !!form.ragHybrid },
    { path: 'rag.retrieval.chunkSize', value: Math.max(100, Math.min(8000, Number(form.ragChunkSize) || 1000)) },
    { path: 'rag.retrieval.chunkOverlap', value: Math.max(0, Math.min(4000, Number(form.ragChunkOverlap) || 0)) },
    { path: 'rag.retrieval.candidateMultiplier', value: Math.max(1, Math.min(10, Number(form.ragCandidateMultiplier) || 4)) },
    { path: 'rag.embeddingModel.type', value: form.ragEmbedType === 'remote' ? 'remote' : 'local' },
    { path: 'rag.embeddingModel.baseUrl', value: form.ragEmbedBaseUrl.trim() },
    { path: 'rag.ocrEngine', value: form.ragOcrEngine === 'markitdown' ? 'markitdown' : 'docling' },
    // dsh 子代理（顶层独立配置块）
    { path: 'dsh.useMainLlm', value: !!form.dshUseMainLlm },
    { path: 'dsh.llm.baseUrl', value: form.dshBaseUrl.trim() },
    { path: 'dsh.llm.model', value: form.dshModel.trim() },
    { path: 'dsh.systemPrompt', value: form.dshSystemPrompt },
    { path: 'dsh.maxTokens', value: Number(form.dshMaxTokens) || DSH_MAX_TOKENS_LIMIT },
    { path: 'dsh.reasoningEffort', value: form.dshReasoningEffort || '' },
  ]
  // 本地模式的模型名由智能下载写入（downloadModel 内即时落盘），保存时不覆盖；
  // 仅远程模式允许用户自定义模型名
  if (form.ragEmbedType === 'remote') {
    patches.push({ path: 'rag.embeddingModel.model', value: form.ragEmbedModel.trim() })
  }
  // 远程模式下才写入 embedding apiKey（非掩码时）；本地模式清空
  if (form.ragEmbedType === 'remote' && !String(form.ragEmbedApiKey).startsWith('***')) {
    patches.push({ path: 'rag.embeddingModel.apiKey', value: form.ragEmbedApiKey.trim() })
  }
  // 代理启用时做简单格式校验
  if (form.proxyEnabled && !form.proxyHttp.trim() && !form.proxyHttps.trim()) {
    return showToast('已启用代理，请至少填写 HTTP 或 HTTPS 代理地址')
  }
  // 仅在用户实际编辑过 key（非掩码）时写入
  if (!String(form.apiKey).startsWith('***')) {
    patches.push({ path: `${llmPrefix}.apiKey`, value: form.apiKey.trim() })
  }
  // Tavily API Key：仅在非掩码时写入
  if (!String(form.tavilyApiKey).startsWith('***')) {
    patches.push({ path: 'agent.tavilyApiKey', value: form.tavilyApiKey.trim() })
  }
  // DeepSeek API Key：仅在非掩码时写入
  if (!String(form.dsApiKey).startsWith('***')) {
    patches.push({ path: 'agent.dsApiKey', value: form.dsApiKey.trim() })
  }
  // dsh 独立 LLM 的 apiKey：同样仅在非掩码时写入
  if (!String(form.dshApiKey).startsWith('***')) {
    patches.push({ path: 'dsh.llm.apiKey', value: form.dshApiKey.trim() })
  }
  let res
  try {
    res = await api.setConfigMany(patches)
  } catch (e) {
    return showToast('保存失败: ' + ((e && e.message) || e))
  }
  if (!res || !res.success) return showToast('保存失败: ' + ((res && res.message) || '未知错误'))
  keyRevealed.value = false
  // 通知 Python 热重建 agent（同时让 agent.ocrEngine / rag 配置热重载）
  send('config.invalidate', { paths: ['llm', 'agent', 'rag', 'dsh'] })
  showToast('已保存，配置热生效 ✓')
  await loadConfig()
  // 同步 TTS 运行时状态（自动朗读设置即时对聊天页生效）
  await loadTtsConfig()
}

function resetPersona() {
  form.persona = ''
  showToast('已恢复默认人设（保存后生效）')
}

async function restartAgent() {
  if (restarting.value) return
  restarting.value = true
  restartDone.value = false

  const res = await api.restartAgent()
  if (!res.success) {
    restarting.value = false
    showToast('重启失败: ' + (res.message || ''))
    return
  }

  // 等待 Python 服务实际启动完成（主进程发送 status-update running:true）
  const started = await new Promise((resolve) => {
    const timer = setTimeout(() => {
      api.offStatusUpdate?.(onStarted)
      resolve(false)
    }, 30000) // 30s 超时

    const onStarted = (status) => {
      if (status && status.running) {
        clearTimeout(timer)
        api.offStatusUpdate?.(onStarted)
        resolve(true)
      }
    }
    api.onStatusUpdate?.(onStarted)
  })

  restarting.value = false
  if (started) {
    restartDone.value = true
    showToast('服务重启成功 ✓')
    setTimeout(() => { restartDone.value = false }, 2500)
  } else {
    showToast('服务启动超时，请检查日志')
  }
}

async function testConnection() {
  testing.value = true
  testResult.value = null

  const baseUrl = form.baseUrl.trim()
  let apiKey = form.apiKey.trim()
  const model = form.model.trim()

  if (!baseUrl || !apiKey || !model) {
    testing.value = false
    testResult.value = { ok: false, text: '请先填写 Base URL、API Key 和模型名称' }
    return
  }

  // 如果 apiKey 是掩码值（***开头），先从后端获取真实 key
  if (apiKey.startsWith('***')) {
    const res = await api.getRawProfileKey(activeProfile.value)
    if (res.success) {
      apiKey = res.apiKey
    } else {
      testing.value = false
      testResult.value = { ok: false, text: '无法获取真实 API Key，请先点击「显示」按钮' }
      return
    }
  }

  try {
    const result = await api.testLlmConnection({ baseUrl, apiKey, model })
    if (result.ok) {
      testResult.value = { ok: true, text: `连接成功（${result.latencyMs}ms）：${result.reply}` }
    } else {
      testResult.value = { ok: false, text: `连接失败：${result.error}` }
    }
  } catch (error) {
    testResult.value = { ok: false, text: `连接失败：${error.message}` }
  } finally {
    testing.value = false
  }
}

// 下载逻辑不依赖组件实例：await 的 Promise 由模块级函数持有，
// 即使下载中途切换 tab 导致本组件卸载，完成后仍会写回模块级单例状态并落盘配置
async function downloadModel() {
  if (downloading.value) return
  downloading.value = true
  downloadResult.value = null
  try {
    const res = await downloadEmbeddingModel()
    // 下载成功：把实际下载的模型名与已下载状态写入配置（config.user.json），
    // 下次进入设置页读到 downloaded=true 即不再显示下载按钮
    const patchRes = await api.setConfigMany([
      { path: 'rag.embeddingModel.model', value: res.model || '' },
      { path: 'rag.embeddingModel.localPath', value: res.path || '' },
      { path: 'rag.embeddingModel.downloaded', value: true },
    ])
    if (!patchRes.success) {
      downloadResult.value = { ok: false, text: `模型已下载但写入配置失败：${patchRes.message || ''}` }
      return
    }
    form.ragEmbedModel = res.model || form.ragEmbedModel
    savedEmbedModel = form.ragEmbedModel // 模型已落盘，同步切换基线
    form.ragLocalDownloaded = true
    downloadResult.value = { ok: true, text: `下载完成 ✓ ${res.model || ''}` }
    showToast('模型下载完成 ✓')
  } catch (e) {
    downloadResult.value = { ok: false, text: `下载失败：${e.message}` }
  } finally {
    downloading.value = false
  }
}

// 清除已下载状态并重新走智能下载（例如更换显卡后想升级到大模型）
async function redownloadModel() {
  if (downloading.value) return
  if (!confirm('确定要清除已下载状态并重新下载模型吗？（本地缓存的模型文件不会被删除）')) return
  const res = await api.setConfig('rag.embeddingModel.downloaded', false)
  if (!res.success) return showToast('清除下载状态失败: ' + (res.message || ''))
  form.ragLocalDownloaded = false
  await downloadModel()
}

// ---------- Embedding 模型切换确认 ----------
function onEmbedTypeChange() {
  if (form.ragEmbedType === savedEmbedType) return
  embedPendingChange.value = { kind: 'type', value: form.ragEmbedType }
  showEmbedConfirm.value = true
}

function onEmbedModelChange() {
  if (form.ragEmbedModel === savedEmbedModel) return
  embedPendingChange.value = { kind: 'model', value: form.ragEmbedModel }
  showEmbedConfirm.value = true
}

// 取消：回滚为已保存的模型配置
function cancelEmbedChange() {
  const pending = embedPendingChange.value
  if (pending?.kind === 'type') form.ragEmbedType = savedEmbedType
  else if (pending?.kind === 'model') form.ragEmbedModel = savedEmbedModel
  showEmbedConfirm.value = false
  embedPendingChange.value = null
}

// 确认：保留新值，并同步基线，避免重复弹窗
function confirmEmbedChange() {
  const pending = embedPendingChange.value
  if (pending?.kind === 'type') savedEmbedType = form.ragEmbedType
  else if (pending?.kind === 'model') savedEmbedModel = form.ragEmbedModel
  showEmbedConfirm.value = false
  embedPendingChange.value = null
}

function togglePreview() {
  if (preview.value) {
    preview.value = ''
  } else {
    connect()
    send('prompt.preview', { persona: form.persona })
  }
}

onMounted(() => {
  loadConfig()
  loadRagHealth()
  connect()
  // 知识库页「前往下载模型」跳转过来时，切到知识库面板并滚动到模型下载区域
  if (route.hash === '#rag-model') revealRagModel()
  on('prompt.preview.result', (p) => { preview.value = p.prompt })
  // 快捷键注册结果：主进程注册/重注册后经 shortcut-status 广播
  api.onShortcutStatus?.((p) => {
    if (p && p.shortcut === undefined) return
    hotkeyStatus.value = p.success
      ? (p.shortcut ? { ok: true, text: `✓ ${p.shortcut} 已生效` } : { ok: true, text: '快速提问快捷键已禁用' })
      : { ok: false, text: `✗ 注册失败：${p.message || '未知原因'}，请换一个组合键` }
  })
  // 初始查询当前注册状态
  api.getShortcutStatus?.().then((p) => {
    if (p && p.success && p.shortcut) hotkeyStatus.value = { ok: true, text: `✓ ${p.shortcut} 已生效` }
  })
})

onBeforeUnmount(() => {
  stopRagPoll()
})

// 已停留在设置页时再次点「前往下载模型」不会重挂载组件，hash 变化单独监听
watch(() => route.hash, (hash) => {
  if (hash === '#rag-model') revealRagModel()
})
</script>

<style scoped>
/* =========================================================
   设置页 · 分栏导航 + 单面板
   左侧分类导航（常规 / 模型与 Agent / 知识与数据 / 提醒与系统），
   右侧只渲染当前面板，长表单靠「分组 + 双列 + 折叠」收敛。
   所有颜色都走 token / color-mix，浅色主题自动适配。
   ========================================================= */

.settings-page {
  --pad-x: 32px;
  --pad-top: 26px;
  max-width: 1180px;
  margin: 0 auto;
  padding-bottom: 4px;
  animation: fadeUp var(--dur-slow) var(--ease-out) backwards;
}

@keyframes fadeUp {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: none; }
}

/* ===== 顶部：标题 + 全局保存 ===== */
.settings-topbar {
  position: sticky;
  top: 0;
  z-index: 40;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  flex-wrap: wrap;
  margin: 0 calc(-1 * var(--pad-x)) 0;
  padding: 13px var(--pad-x) 13px;
  background: color-mix(in srgb, var(--ink-950) 84%, transparent);
  border-bottom: 1px solid var(--line-1);
  backdrop-filter: blur(18px) saturate(130%);
  -webkit-backdrop-filter: blur(18px) saturate(130%);
}

.topbar-head {
  min-width: 0;
}

.eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.18em;
  color: var(--amber-500);
}

.topbar-line {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-top: 2px;
}

.page-title {
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.2;
  color: var(--text-1);
}

.topbar-note {
  font-size: 11.5px;
  color: var(--text-4);
  white-space: nowrap;
}

.global-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

/* ===== 按钮 ===== */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  height: 34px;
  padding: 0 14px;
  font-family: inherit;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-1);
  background: var(--ink-750);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  cursor: pointer;
  white-space: nowrap;
  transition: background var(--dur-fast) var(--ease-out), border-color var(--dur-fast),
    color var(--dur-fast), transform var(--dur-fast), box-shadow var(--dur-fast), filter var(--dur-fast);
}

.btn:hover:not(:disabled) {
  background: var(--ink-700);
  border-color: var(--line-3);
}

.btn:active:not(:disabled) {
  transform: translateY(1px);
}

.btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.btn.primary {
  color: var(--amber-ink);
  background: var(--amber-grad);
  border-color: transparent;
  font-weight: 650;
  box-shadow: var(--shadow-1), inset 0 1px 0 color-mix(in srgb, var(--amber-100) 30%, transparent);
}

.btn.primary:hover:not(:disabled) {
  filter: brightness(1.06);
  box-shadow: var(--shadow-amber), inset 0 1px 0 color-mix(in srgb, var(--amber-100) 32%, transparent);
}

.btn.warn {
  color: var(--warn-400);
  background: color-mix(in srgb, var(--warn-400) 8%, transparent);
  border-color: color-mix(in srgb, var(--warn-400) 28%, transparent);
}

.btn.warn:hover:not(:disabled) {
  color: var(--warn-400);
  background: color-mix(in srgb, var(--warn-400) 14%, transparent);
  border-color: color-mix(in srgb, var(--warn-400) 44%, transparent);
}

.btn.warn.is-done {
  color: var(--jade-400);
  background: var(--jade-a12);
  border-color: color-mix(in srgb, var(--jade-400) 32%, transparent);
}

.btn-spinner {
  width: 12px;
  height: 12px;
  border: 1.5px solid color-mix(in srgb, currentColor 30%, transparent);
  border-top-color: currentColor;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

.btn-check {
  color: currentColor;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.mini {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 28px;
  padding: 0 10px;
  font-family: inherit;
  font-size: 11.5px;
  font-weight: 500;
  color: var(--text-2);
  background: transparent;
  border: 1px solid var(--line-2);
  border-radius: var(--r-xs);
  cursor: pointer;
  white-space: nowrap;
  transition: background var(--dur-fast), border-color var(--dur-fast), color var(--dur-fast);
}

.mini:hover:not(:disabled) {
  color: var(--text-1);
  background: var(--ink-750);
  border-color: var(--line-3);
}

.mini:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.mini.danger {
  color: var(--coral-400);
  background: var(--coral-a12);
  border-color: color-mix(in srgb, var(--coral-400) 32%, transparent);
}

.mini.danger:hover:not(:disabled) {
  color: var(--coral-400);
  background: color-mix(in srgb, var(--coral-400) 18%, transparent);
  border-color: color-mix(in srgb, var(--coral-400) 52%, transparent);
}

.mini.danger:disabled {
  opacity: 0.35;
}

/* ===== 两栏：分类导航 + 内容 ===== */
.settings-shell {
  display: grid;
  grid-template-columns: 208px minmax(0, 1fr);
  gap: 34px;
  align-items: start;
  padding-top: 24px;
}

.settings-nav {
  position: sticky;
  top: 82px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  max-height: calc(100vh - 110px);
  overflow-y: auto;
  padding: 2px 4px 8px 0;
}

.settings-nav::-webkit-scrollbar {
  width: 6px;
}

.nav-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-group-title {
  padding: 0 10px;
  margin-bottom: 5px;
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.14em;
  color: var(--text-4);
}

.nav-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  height: 34px;
  padding: 0 10px;
  font-family: inherit;
  font-size: 13px;
  font-weight: 450;
  text-align: left;
  color: var(--text-3);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--r-sm);
  cursor: pointer;
  transition: background var(--dur-fast) var(--ease-out), color var(--dur-fast), border-color var(--dur-fast);
}

.nav-item:hover {
  color: var(--text-1);
  background: color-mix(in srgb, var(--ink-750) 60%, transparent);
}

.nav-item.active {
  color: var(--amber-200);
  background: var(--amber-a08);
  border-color: var(--amber-a20);
  box-shadow: inset 2px 0 0 var(--amber-400);
}

.nav-icon {
  color: currentColor;
  opacity: 0.8;
}

.nav-item.active .nav-icon {
  opacity: 1;
}

.nav-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.nav-note {
  padding: 2px 10px;
  font-size: 11px;
  line-height: 1.5;
  color: var(--text-5);
}

/* ===== 面板 ===== */
.settings-main {
  width: 100%;
  min-width: 0;
  max-width: 1000px;
}

.panel {
  background: linear-gradient(180deg, var(--ink-850), var(--ink-800));
  border: 1px solid var(--line-1);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-1), var(--hairline);
  overflow: hidden;
  animation: panel-in var(--dur) var(--ease-out);
}

@keyframes panel-in {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: none; }
}

.panel-head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 17px 22px;
  border-bottom: 1px solid var(--line-1);
}

.panel-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  color: var(--amber-300);
  background: var(--amber-a08);
  border: 1px solid var(--amber-a20);
  border-radius: var(--r-sm);
}

.panel-head-text {
  min-width: 0;
}

.panel-title {
  font-size: 15px;
  font-weight: 650;
  letter-spacing: -0.01em;
  line-height: 1.3;
  color: var(--text-1);
}

.panel-sub {
  margin-top: 2px;
  font-size: 12px;
  color: var(--text-4);
}

.panel-body {
  padding: 4px 22px 20px;
}

/* ===== 分组 ===== */
.sgroup {
  padding: 16px 0;
  border-top: 1px solid var(--line-1);
}

.sgroup:first-child {
  border-top: 0;
  padding-top: 12px;
}

.sgroup:last-child {
  padding-bottom: 4px;
}

.sgroup-head {
  margin-bottom: 2px;
}

.sgroup-title {
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.1em;
  color: var(--text-3);
}

.sgroup-desc {
  margin-top: 3px;
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--text-4);
}

.sgroup > * + * {
  margin-top: 14px;
}

/* ===== 字段 ===== */
.field {
  display: flex;
  flex-direction: column;
  gap: 7px;
  min-width: 0;
}

.field-label,
.field > label {
  font-size: 12.5px;
  font-weight: 500;
  line-height: 1.4;
  color: var(--text-2);
}

.field-label-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.inline-val {
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--amber-300);
  font-variant-numeric: tabular-nums;
}

.field-hint {
  font-size: 11.5px;
  line-height: 1.55;
  color: var(--text-4);
}

.theme-picker + .field-hint {
  margin-top: 10px;
}

.field-hint.bad {
  color: var(--coral-400);
}

.field-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px 18px;
}

.field-grid > .field {
  min-width: 0;
}

.span-2 {
  grid-column: 1 / -1;
}

/* ===== 开关行 ===== */
.switch-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  padding: 12px 0;
}

.switch-row + .switch-row {
  border-top: 1px solid var(--line-1);
}

.switch-row.no-line {
  border-top: 0;
}

.switch-text {
  min-width: 0;
}

.switch-title {
  font-size: 13px;
  font-weight: 550;
  color: var(--text-1);
}

.switch-desc {
  margin-top: 3px;
  max-width: 64ch;
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--text-4);
}

.toggle {
  position: relative;
  flex-shrink: 0;
  width: 38px;
  height: 22px;
  margin-top: 1px;
  cursor: pointer;
}

.toggle input {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  margin: 0;
  opacity: 0;
  cursor: pointer;
}

.toggle-track {
  position: relative;
  display: block;
  width: 100%;
  height: 100%;
  background: var(--ink-700);
  border: 1px solid var(--line-2);
  border-radius: var(--r-full);
  transition: background var(--dur) var(--ease-out), border-color var(--dur), box-shadow var(--dur);
}

.toggle-thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  background: var(--text-4);
  border-radius: 50%;
  transition: transform var(--dur) var(--ease-spring), background var(--dur);
}

.toggle input:checked + .toggle-track {
  background: var(--amber-grad);
  border-color: transparent;
  box-shadow: 0 2px 8px -3px color-mix(in srgb, var(--amber-400) 55%, transparent);
}

.toggle input:checked + .toggle-track .toggle-thumb {
  transform: translateX(16px);
  background: var(--amber-ink);
}

.toggle input:focus-visible + .toggle-track {
  outline: 2px solid var(--amber-a55);
  outline-offset: 2px;
}

.toggle input:disabled + .toggle-track {
  opacity: 0.4;
  cursor: not-allowed;
}

/* ===== 子分组（父开关下的配置） ===== */
.sub-panel {
  padding: 14px;
  background: color-mix(in srgb, var(--ink-1000) 46%, transparent);
  border: 1px solid var(--line-1);
  border-radius: var(--r-md);
}

.sub-panel > * + * {
  margin-top: 14px;
}

/* ===== 折叠区 ===== */
.fold {
  margin-top: 16px;
  background: color-mix(in srgb, var(--ink-1000) 40%, transparent);
  border: 1px solid var(--line-1);
  border-radius: var(--r-md);
  transition: border-color var(--dur-fast);
}

.fold:hover {
  border-color: var(--line-2);
}

.fold > summary {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 11px 14px;
  font-size: 12.5px;
  color: var(--text-2);
  cursor: pointer;
  list-style: none;
  user-select: none;
}

.fold > summary::-webkit-details-marker {
  display: none;
}

.fold[open] > summary {
  border-bottom: 1px solid var(--line-1);
}

.fold-chevron {
  color: var(--text-4);
  transition: transform var(--dur) var(--ease-out);
}

.fold[open] .fold-chevron {
  transform: rotate(90deg);
}

.fold-title {
  font-weight: 550;
  color: var(--text-2);
}

.fold-meta {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-4);
}

.fold-body {
  padding: 14px;
}

.fold-tip {
  margin-bottom: 12px;
}

/* ===== 输入控件 ===== */
.panel-body input:not([type='range']):not([type='checkbox']):not([type='radio']),
.panel-body select,
.panel-body textarea,
.modal input {
  width: 100%;
  height: 36px;
  padding: 0 12px;
  font-family: inherit;
  font-size: 13px;
  color: var(--text-1);
  background: var(--ink-1000);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  transition: border-color var(--dur-fast), background var(--dur-fast), box-shadow var(--dur-fast);
}

.panel-body select,
.modal select {
  cursor: pointer;
}

.panel-body textarea,
.modal textarea {
  height: auto;
  min-height: 78px;
  padding: 9px 12px;
  line-height: 1.6;
  resize: vertical;
}

.panel-body input:focus,
.panel-body select:focus,
.panel-body textarea:focus,
.modal input:focus,
.modal textarea:focus {
  border-color: var(--amber-a55);
  box-shadow: 0 0 0 3px var(--amber-a12);
  outline: none;
}

.panel-body input:disabled,
.panel-body select:disabled,
.panel-body textarea:disabled {
  color: var(--text-3);
  background: color-mix(in srgb, var(--ink-900) 72%, transparent);
  border-color: var(--line-1);
  cursor: not-allowed;
}

.panel-body input::placeholder,
.panel-body textarea::placeholder {
  color: var(--text-5);
}

.panel-body input[type='checkbox'] {
  width: 14px;
  height: 14px;
  accent-color: var(--amber-400);
  cursor: pointer;
}

.panel-body input[type='range'] {
  accent-color: var(--amber-400);
}

.mono {
  font-family: var(--font-mono);
  font-size: 12.5px;
  letter-spacing: -0.01em;
}

.persona {
  min-height: 158px;
  line-height: 1.65;
}

/* ===== 步进器 ===== */
.stepper {
  display: flex;
  align-items: stretch;
  height: 36px;
  overflow: hidden;
  background: var(--ink-1000);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
}

.stepper:focus-within {
  border-color: var(--amber-a55);
  box-shadow: 0 0 0 3px var(--amber-a12);
}

.step-btn {
  display: grid;
  place-items: center;
  width: 34px;
  flex-shrink: 0;
  color: var(--text-3);
  background: transparent;
  border: 0;
  cursor: pointer;
  transition: background var(--dur-fast), color var(--dur-fast);
}

.step-btn:hover:not(:disabled) {
  color: var(--text-1);
  background: var(--ink-750);
}

.step-btn:disabled {
  color: var(--text-5);
  cursor: not-allowed;
}

.stepper .step-input {
  flex: 1;
  min-width: 0;
  height: 34px;
  padding: 0 4px;
  text-align: center;
  font-variant-numeric: tabular-nums;
  background: transparent;
  border: 0;
  border-radius: 0;
}

.stepper .step-input:focus {
  box-shadow: none;
}

/* ===== 键值 / 行内 ===== */
.key-row,
.workspace-row,
.inline-row,
.profile-row,
.hotkey-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.key-row > input,
.workspace-row > input,
.inline-row > select,
.profile-row > select {
  flex: 1 1 240px;
  min-width: 0;
}

.profile-row > select {
  height: 36px;
}

.profile-row > .btn,
.workspace-row > .btn,
.inline-row > .btn {
  height: 36px;
}

.key-row > .mini {
  height: 36px;
}

.voice-select {
  flex: 1 1 260px;
}

.workspace-path {
  color: var(--text-2);
}

.actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.actions .field-hint {
  margin: 0;
}

.ok {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: var(--jade-400);
}

.bad-text {
  font-size: 12px;
  color: var(--coral-400);
}

/* ===== 主题选择 ===== */
.theme-picker {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.theme-option {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 10px;
  padding: 10px;
  font-family: inherit;
  text-align: left;
  background: var(--ink-1000);
  border: 1px solid var(--line-2);
  border-radius: var(--r-md);
  cursor: pointer;
  transition: border-color var(--dur-fast), background var(--dur-fast), box-shadow var(--dur-fast), transform var(--dur-fast);
}

.theme-option:hover {
  border-color: var(--line-3);
  transform: translateY(-1px);
}

.theme-option.active {
  border-color: var(--amber-a55);
  box-shadow: 0 0 0 1px var(--amber-a20), var(--shadow-amber);
}

.theme-swatch {
  position: relative;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  width: 100%;
  height: 64px;
  padding: 9px 11px;
  overflow: hidden;
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
}

.swatch-sample {
  font-size: 21px;
  font-weight: 600;
  line-height: 1;
  letter-spacing: 0.01em;
}

.swatch-dot {
  width: 9px;
  height: 9px;
  margin-bottom: 2px;
  border-radius: 50%;
}

.theme-dark .theme-swatch {
  background:
    radial-gradient(130% 120% at 96% 4%, rgba(239, 168, 76, 0.22), transparent 62%),
    linear-gradient(150deg, #090C11, #12161F 60%, #1A202B);
}

.theme-dark .swatch-sample {
  color: #EBE9E4;
}

.theme-dark .swatch-dot {
  background: #EFA84C;
  box-shadow: 0 0 10px rgba(239, 168, 76, 0.6);
}

.theme-light .theme-swatch {
  background:
    radial-gradient(100% 110% at 96% 4%, rgba(18, 122, 102, 0.1), transparent 58%),
    linear-gradient(150deg, #E9EEEC, #F7F9F8 60%, #FFFFFF);
}

.theme-light .swatch-sample {
  color: #0F1C1A;
}

.theme-light .swatch-dot {
  background: #127A66;
  box-shadow: 0 0 10px rgba(18, 122, 102, 0.35);
}

.theme-system .theme-swatch {
  background: linear-gradient(90deg, #090C11 0 50%, #F1F4F3 50% 100%);
}

.theme-system .swatch-sample {
  color: #EBE9E4;
}

/* 跟随系统：左右各一个 Aa，直观表达「两套外观」 */
.theme-system .theme-swatch::after {
  position: absolute;
  right: 11px;
  bottom: 9px;
  content: 'Aa';
  font-size: 21px;
  font-weight: 600;
  line-height: 1;
  color: #0F1C1A;
}

.theme-system .swatch-dot {
  display: none;
}

.theme-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.theme-name {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  font-weight: 500;
  color: var(--text-1);
}

.theme-badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 6px;
  font-size: 10.5px;
  font-weight: 600;
  color: var(--amber-300);
  background: var(--amber-a12);
  border-radius: var(--r-full);
}

/* ===== 双滑杆 ===== */
.range-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 20px;
  padding: 12px 14px;
  background: color-mix(in srgb, var(--ink-1000) 42%, transparent);
  border: 1px solid var(--line-1);
  border-radius: var(--r-md);
}

.range-field {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
}

.range-label {
  font-size: 12px;
  color: var(--text-3);
}

.range-value {
  min-width: 40px;
  font-family: var(--font-mono);
  font-size: 11.5px;
  text-align: right;
  color: var(--amber-300);
}

/* ===== 快捷键录制 ===== */
.hotkey-box {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 220px;
  height: 38px;
  padding: 0 16px;
  font-family: var(--font-mono);
  font-size: 12.5px;
  color: var(--text-1);
  background: var(--ink-1000);
  border: 1px dashed var(--line-3);
  border-radius: var(--r-sm);
  cursor: pointer;
  user-select: none;
  transition: border-color var(--dur-fast), box-shadow var(--dur-fast), color var(--dur-fast);
}

.hotkey-box:hover {
  border-color: var(--amber-a35);
}

.hotkey-box.recording {
  color: var(--amber-300);
  border-color: var(--amber-a55);
  border-style: solid;
  box-shadow: 0 0 0 3px var(--amber-a12);
}

.hotkey-box.bad {
  color: var(--coral-400);
  border-color: color-mix(in srgb, var(--coral-400) 55%, transparent);
}

/* ===== TTS 试听 ===== */
.eq {
  display: inline-flex;
  align-items: flex-end;
  gap: 2px;
  height: 12px;
  margin-right: 2px;
}

.eq i {
  width: 2px;
  height: 4px;
  background: currentColor;
  animation: eq 900ms ease-in-out infinite;
}

.eq i:nth-child(2) { animation-delay: 150ms; }
.eq i:nth-child(3) { animation-delay: 300ms; }

@keyframes eq {
  0%, 100% { height: 4px; }
  50% { height: 12px; }
}

/* ===== 提示条 ===== */
.notice {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  padding: 11px 13px;
  font-size: 12px;
  line-height: 1.55;
  color: var(--text-2);
  background: var(--azure-a12);
  border: 1px solid color-mix(in srgb, var(--azure-400) 24%, transparent);
  border-radius: var(--r-md);
}

.notice svg {
  flex-shrink: 0;
  margin-top: 1px;
  color: var(--azure-400);
}

/* ===== RAG 参数 / 健康度 ===== */
.rag-retrieval-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.rag-num {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  color: var(--text-3);
}

.rag-num input {
  height: 34px;
  font-variant-numeric: tabular-nums;
}

.rag-health {
  padding: 14px;
  background: color-mix(in srgb, var(--ink-1000) 44%, transparent);
  border: 1px solid var(--line-1);
  border-radius: var(--r-md);
}

.rag-health.bad {
  border-color: color-mix(in srgb, var(--warn-400) 34%, transparent);
  background: color-mix(in srgb, var(--warn-400) 6%, transparent);
}

.rag-health-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px 16px;
}

.rh-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12.5px;
  color: var(--text-1);
  font-variant-numeric: tabular-nums;
}

.rh-label {
  font-size: 10.5px;
  letter-spacing: 0.1em;
  color: var(--text-4);
}

.rag-warn {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 12px;
  padding: 9px 11px;
  font-size: 11.5px;
  line-height: 1.55;
  color: var(--warn-400);
  background: var(--warn-a12);
  border: 1px solid color-mix(in srgb, var(--warn-400) 22%, transparent);
  border-radius: var(--r-sm);
}

.rag-warn svg {
  flex-shrink: 0;
  margin-top: 1px;
}

.rag-health-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 12px;
}

.rag-health-tip {
  font-size: 11px;
  line-height: 1.5;
  color: var(--text-4);
}

.rag-progress {
  margin-top: 12px;
}

.rag-progress-bar {
  height: 5px;
  overflow: hidden;
  background: var(--ink-700);
  border-radius: var(--r-full);
}

.rag-progress-bar span {
  display: block;
  height: 100%;
  background: var(--amber-grad);
  transition: width var(--dur-slow) var(--ease-out);
}

.rag-progress-text {
  margin-top: 6px;
  font-size: 11.5px;
  color: var(--text-4);
  font-variant-numeric: tabular-nums;
}

/* ===== 本地模型下载 ===== */
.download-box {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-top: 16px;
  padding: 12px 14px;
  background: color-mix(in srgb, var(--amber-400) 4%, transparent);
  border: 1px dashed var(--line-3);
  border-radius: var(--r-md);
}

.download-text {
  flex: 1 1 320px;
  min-width: 0;
}

.download-text .field-hint {
  margin-top: 3px;
}

/* ===== 备份结果 ===== */
.backup-list {
  display: grid;
  gap: 6px;
  margin-top: 12px;
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--text-4);
}

.backup-list li {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr);
  gap: 10px;
}

.bl-key {
  color: var(--text-3);
  font-weight: 500;
}

.backup-result {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 12px;
  padding: 11px 13px;
  background: var(--jade-a12);
  border: 1px solid color-mix(in srgb, var(--jade-400) 24%, transparent);
  border-radius: var(--r-md);
}

.backup-path {
  flex: 1 1 240px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--text-3);
}

/* ===== 高危操作勾选 ===== */
.interrupt-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: 2px 14px;
  padding: 10px 14px;
  background: var(--ink-1000);
  border: 1px solid var(--line-1);
  border-radius: var(--r-md);
}

.check {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  font-size: 12.5px;
  color: var(--text-2);
  cursor: pointer;
  user-select: none;
}

/* ===== 提示词预览 ===== */
.preview-box {
  max-height: 380px;
  margin-top: 12px;
  padding: 14px;
  overflow: auto;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.65;
  color: var(--text-2);
  white-space: pre-wrap;
  background: var(--ink-1000);
  border: 1px solid var(--line-1);
  border-radius: var(--r-md);
}

/* ===== 弹窗 ===== */
.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: color-mix(in srgb, var(--ink-1000) 72%, transparent);
  backdrop-filter: blur(4px);
  animation: fadeIn var(--dur) var(--ease-out);
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.modal {
  width: 410px;
  max-width: 100%;
  padding: 22px;
  background: linear-gradient(180deg, var(--ink-850), var(--ink-800));
  border: 1px solid var(--line-2);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-3), var(--hairline);
  animation: modal-in var(--dur) var(--ease-spring);
}

@keyframes modal-in {
  from { opacity: 0; transform: translateY(8px) scale(0.985); }
  to { opacity: 1; transform: none; }
}

.modal h3 {
  margin: 0 0 16px;
  font-size: 16px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text-1);
}

.modal .field {
  margin-bottom: 14px;
}

.modal-copy {
  margin: 0 0 12px;
  font-size: 12.5px;
  line-height: 1.65;
  color: var(--text-3);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 4px;
}

/* ===== Toast ===== */
.toast {
  position: fixed;
  top: 22px;
  left: 50%;
  z-index: 9999;
  max-width: calc(100vw - 40px);
  padding: 10px 18px;
  font-size: 12.5px;
  font-weight: 600;
  text-align: center;
  color: var(--amber-100);
  background: color-mix(in srgb, var(--ink-900) 92%, transparent);
  border: 1px solid var(--amber-a35);
  border-radius: var(--r-full);
  box-shadow: var(--shadow-3), var(--hairline);
  backdrop-filter: blur(12px);
  transform: translateX(-50%);
  animation: toast-in var(--dur) var(--ease-spring);
}

@keyframes toast-in {
  from { opacity: 0; transform: translateX(-50%) translateY(-12px); }
  to { opacity: 1; transform: translateX(-50%) translateY(0); }
}

/* ===== 响应式 ===== */
@media (max-width: 1080px) {
  .settings-shell {
    grid-template-columns: 186px minmax(0, 1fr);
    gap: 26px;
  }
}

@media (max-width: 980px) {
  .settings-page {
    --pad-x: 18px;
    --pad-top: 20px;
  }

  .settings-topbar {
    padding-top: 11px;
    padding-bottom: 11px;
  }
}

@media (max-width: 900px) {
  .settings-shell {
    grid-template-columns: minmax(0, 1fr);
    gap: 14px;
    padding-top: 16px;
  }

  .settings-nav {
    position: static;
    flex-direction: row;
    gap: 6px;
    max-height: none;
    padding: 0 0 4px;
    overflow-x: auto;
    overflow-y: hidden;
    border-bottom: 1px solid var(--line-1);
    scrollbar-width: none;
  }

  .settings-nav::-webkit-scrollbar {
    width: 0;
    height: 0;
  }

  .nav-group {
    display: contents;
  }

  .nav-group-title,
  .nav-note {
    display: none;
  }

  .nav-item {
    width: auto;
    flex: 0 0 auto;
    height: 32px;
    padding: 0 12px;
    border-radius: var(--r-full);
  }

  .nav-item.active {
    box-shadow: none;
  }
}

@media (max-width: 720px) {
  .settings-topbar {
    align-items: flex-start;
  }

  .global-actions {
    width: 100%;
  }

  .panel-head {
    padding: 14px 16px;
  }

  .panel-body {
    padding: 2px 16px 16px;
  }

  .field-grid,
  .range-grid,
  .rag-retrieval-row,
  .rag-health-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .theme-picker {
    grid-template-columns: minmax(0, 1fr);
  }

  .theme-swatch {
    height: 52px;
  }

  .toggle {
    margin-top: 0;
  }
}
</style>
