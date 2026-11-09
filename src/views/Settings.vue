<template>
  <div class="page settings-page">
    <header class="page-header">
      <div class="page-head-main">
        <div class="eyebrow">
          <AppIcon name="settings" :size="12" />
          偏好设置
        </div>
        <h1 class="page-title">设置</h1>
        <p class="page-subtitle">模型连接与人设配置，保存后热生效</p>
      </div>

      <!-- 全局操作 -->
      <div class="global-actions">
        <button class="btn primary" @click="saveAll">
          <AppIcon name="check" :size="14" />
          保存设置
        </button>
        <button class="btn warn" :class="{ 'is-done': restartDone }" @click="restartAgent" :disabled="restarting">
          <span v-if="restarting" class="btn-spinner"></span>
          <AppIcon v-else-if="restartDone" name="check" :size="14" class="btn-check" />
          <AppIcon v-else name="refresh" :size="14" />
          <span v-if="!restarting && !restartDone">重启服务进程</span>
        </button>
      </div>
    </header>

    <div class="settings-grid">
    <!-- 模型连接 -->
    <section class="card">
      <div class="card-header">
        <span class="card-icon"><AppIcon name="plug" :size="15" /></span>
        <div class="card-head-main">
          <div class="card-title">模型连接</div>
          <div class="card-sub">主 Agent 的 LLM 连接、采样与上下文策略</div>
        </div>
      </div>
      <div class="card-body form">
        <div class="field">
          <label>配置档</label>
          <div class="profile-row">
            <select :value="activeProfile" @change="switchProfile($event.target.value)">
              <option v-for="(p, name) in profiles" :key="name" :value="name">{{ p.label || name }}</option>
            </select>
            <button class="btn" @click="showAddProfile = true" title="新增配置档"><AppIcon name="plus" :size="14" />新增</button>
            <button class="btn warn" @click="deleteProfile" :disabled="activeProfile === 'default'" title="删除当前配置档（default 不可删除）"><AppIcon name="trash" :size="14" />删除</button>
          </div>
        </div>
        <div class="field">
          <label>Provider</label>
          <select v-model="form.provider">
            <option value="openai">OpenAI‑Compatible</option>
            <option value="deepseek">DeepSeek-Compatible</option>
          </select>
          <span class="hint">OpenAI: reasoning 放在 content 中；DeepSeek: reasoning 放在 reasoning_content 中</span>
        </div>
        <div class="field">
          <label>Base URL</label>
          <input v-model="form.baseUrl" placeholder="http://localhost:8080/v1" />
        </div>
        <div class="field">
          <label>API Key</label>
          <div class="key-row">
            <input v-model="form.apiKey" :type="showKey ? 'text' : 'password'" placeholder="sk-..." @focus="revealKey" />
            <button class="mini" @click="showKey = !showKey">{{ showKey ? '隐藏' : '显示' }}</button>
          </div>
        </div>
        <div class="field">
          <label>模型名称</label>
          <input v-model="form.model" placeholder="Qwen3.6-35B" />
        </div>
        <div class="field">
          <label>采样温度（Temperature）<span class="inline-val">{{ Number(form.temperature).toFixed(2) }}</span></label>
          <input type="range" min="0" max="2" step="0.05" v-model.number="form.temperature" />
          <span class="hint">范围 0~2，越低回答越稳定、越高越发散（默认 0.7）；仅作用于当前配置档</span>
        </div>
        <div class="field">
          <label>上下文窗口（contextWindow）</label>
          <div class="stepper">
            <button type="button" class="step-btn" @click="step('contextWindow', -8192, CONTEXT_WINDOW_MIN, CONTEXT_WINDOW_MAX)" :disabled="form.contextWindow <= CONTEXT_WINDOW_MIN"><AppIcon name="minus" :size="14" /></button>
            <input type="number" v-model.number="form.contextWindow" :min="CONTEXT_WINDOW_MIN" :max="CONTEXT_WINDOW_MAX" class="step-input"
              @blur="clamp('contextWindow', CONTEXT_WINDOW_MIN, CONTEXT_WINDOW_MAX, DEFAULT_CONTEXT_WINDOW)" />
            <button type="button" class="step-btn" @click="step('contextWindow', 8192, CONTEXT_WINDOW_MIN, CONTEXT_WINDOW_MAX)" :disabled="form.contextWindow >= CONTEXT_WINDOW_MAX"><AppIcon name="plus" :size="14" /></button>
          </div>
          <span class="hint">模型单次可处理的最大 token 数（含输入+输出），用于上下文压缩的阈值判断；范围 8192~1048576，默认 262144</span>
        </div>
        <div class="field">
          <label class="check"><input type="checkbox" v-model="form.contextCompressionEnabled" /> 启用上下文自动压缩</label>
          <span class="hint">对话上下文接近模型窗口上限时，自动把久远历史总结成一条摘要并保留近期原文，避免请求溢出（默认开启；关闭则仅按条数裁剪）</span>
        </div>
        <template v-if="form.contextCompressionEnabled">
          <div class="field">
            <label>压缩使用的模型</label>
            <select v-model="form.contextCompressionModel">
              <option value="">跟随当前配置档（{{ profiles[activeProfile]?.label || activeProfile }}）</option>
              <option v-for="(p, name) in profiles" :key="name" :value="name">{{ p.label || name }}</option>
            </select>
            <span class="hint">生成摘要所用的 LLM；可选择独立配置档，留空则复用当前激活的模型</span>
          </div>
          <div class="field">
            <label>触发压缩的上下文占用 <span class="inline-val">{{ form.contextCompressionThreshold }}%</span></label>
            <input type="range" :min="CC_THRESHOLD_MIN" :max="CC_THRESHOLD_MAX" step="5" v-model.number="form.contextCompressionThreshold" />
            <span class="hint">当前上下文估算 token 达到 contextWindow 的该比例时触发压缩，范围 10~95%（默认 80%）</span>
          </div>
          <div class="field">
            <label>压缩后保留的最近消息（条）</label>
            <div class="stepper">
              <button type="button" class="step-btn" @click="step('contextCompressionKeep', -1, CC_KEEP_MIN, CC_KEEP_MAX)" :disabled="form.contextCompressionKeep <= CC_KEEP_MIN"><AppIcon name="minus" :size="14" /></button>
              <input type="number" v-model.number="form.contextCompressionKeep" :min="CC_KEEP_MIN" :max="CC_KEEP_MAX" class="step-input"
                @blur="clamp('contextCompressionKeep', CC_KEEP_MIN, CC_KEEP_MAX, DEFAULT_CC_KEEP)" />
              <button type="button" class="step-btn" @click="step('contextCompressionKeep', 1, CC_KEEP_MIN, CC_KEEP_MAX)" :disabled="form.contextCompressionKeep >= CC_KEEP_MAX"><AppIcon name="plus" :size="14" /></button>
            </div>
            <span class="hint">压缩完成后保留的最近原始消息条数，范围 1~200（默认 10）</span>
          </div>
        </template>
        <!-- 媒体守卫（contextCompression.media*，见 agent/middlewares.py::trim_media_history）：
             与上面的「自动压缩」开关相互独立 —— 关掉自动压缩只是不做摘要，历史图片的收敛照常生效，
             否则 read_file 读图 / 用户上传附件会把上下文越撑越大，直到上游报「上下文超长」。 -->
        <div class="field">
          <label>历史图片保留条数（每种来源）</label>
          <div class="stepper">
            <button type="button" class="step-btn" @click="step('contextMediaKeep', -1, MEDIA_KEEP_MIN, MEDIA_KEEP_MAX)" :disabled="form.contextMediaKeep <= MEDIA_KEEP_MIN"><AppIcon name="minus" :size="14" /></button>
            <input type="number" v-model.number="form.contextMediaKeep" :min="MEDIA_KEEP_MIN" :max="MEDIA_KEEP_MAX" class="step-input"
              @blur="clamp('contextMediaKeep', MEDIA_KEEP_MIN, MEDIA_KEEP_MAX, DEFAULT_MEDIA_KEEP)" />
            <button type="button" class="step-btn" @click="step('contextMediaKeep', 1, MEDIA_KEEP_MIN, MEDIA_KEEP_MAX)" :disabled="form.contextMediaKeep >= MEDIA_KEEP_MAX"><AppIcon name="plus" :size="14" /></button>
          </div>
          <span class="hint">read_file 读到的图与用户上传的图「各自」保留最近 N 条（0~20，默认 1）；更早的图片会被替换成带原始路径的文字占位，模型可按需用 read_file 重新读取 —— 于是上下文里的图片数不会随对话轮数增长；0 = 图片一律不保留（模型看不到任何历史图）</span>
        </div>
        <div class="field">
          <label>单条消息图片体积上限（KB）</label>
          <div class="stepper">
            <button type="button" class="step-btn" @click="step('contextMediaMaxKB', -128, MEDIA_MAX_KB_MIN, MEDIA_MAX_KB_MAX)" :disabled="form.contextMediaMaxKB <= MEDIA_MAX_KB_MIN"><AppIcon name="minus" :size="14" /></button>
            <input type="number" v-model.number="form.contextMediaMaxKB" :min="MEDIA_MAX_KB_MIN" :max="MEDIA_MAX_KB_MAX" class="step-input"
              @blur="clamp('contextMediaMaxKB', MEDIA_MAX_KB_MIN, MEDIA_MAX_KB_MAX, DEFAULT_MEDIA_MAX_KB)" />
            <button type="button" class="step-btn" @click="step('contextMediaMaxKB', 128, MEDIA_MAX_KB_MIN, MEDIA_MAX_KB_MAX)" :disabled="form.contextMediaMaxKB >= MEDIA_MAX_KB_MAX"><AppIcon name="plus" :size="14" /></button>
          </div>
          <span class="hint">单条消息内的图片合计超过该值即触发降采样（0~16384KB，默认 512）；0 = 不做体积限制（只靠上面的条数收敛）；把「条数」与「体积」同时设为 0 即等于关闭本机制</span>
        </div>
        <div class="field">
          <label>降采样后图片最长边（px）</label>
          <div class="stepper">
            <button type="button" class="step-btn" @click="step('contextMediaMaxPx', -128, MEDIA_MAX_PX_MIN, MEDIA_MAX_PX_MAX)" :disabled="form.contextMediaMaxPx <= MEDIA_MAX_PX_MIN"><AppIcon name="minus" :size="14" /></button>
            <input type="number" v-model.number="form.contextMediaMaxPx" :min="MEDIA_MAX_PX_MIN" :max="MEDIA_MAX_PX_MAX" class="step-input"
              @blur="clamp('contextMediaMaxPx', MEDIA_MAX_PX_MIN, MEDIA_MAX_PX_MAX, DEFAULT_MEDIA_MAX_PX)" />
            <button type="button" class="step-btn" @click="step('contextMediaMaxPx', 128, MEDIA_MAX_PX_MIN, MEDIA_MAX_PX_MAX)" :disabled="form.contextMediaMaxPx >= MEDIA_MAX_PX_MAX"><AppIcon name="plus" :size="14" /></button>
          </div>
          <span class="hint">超限图片重编码为 JPEG 时的最长边像素（128~4096，默认 1280）；越小越省上下文，但字迹与细节也越模糊</span>
        </div>
        <div class="field">
          <label>降采样 JPEG 质量 <span class="inline-val">{{ form.contextMediaJpegQuality }}</span></label>
          <input type="range" :min="MEDIA_JPEG_QUALITY_MIN" :max="MEDIA_JPEG_QUALITY_MAX" step="5" v-model.number="form.contextMediaJpegQuality" />
          <span class="hint">30~95（默认 80），越低体积越小、画质越差；仅作用于被降采样的超限图片</span>
        </div>
        <div class="field">
          <label>最大输出 token（maxTokens）</label>
          <div class="stepper">
            <button type="button" class="step-btn" @click="step('maxTokens', -1024, MAX_TOKENS_MIN, MAX_TOKENS_MAX)" :disabled="form.maxTokens <= MAX_TOKENS_MIN"><AppIcon name="minus" :size="14" /></button>
            <input type="number" v-model.number="form.maxTokens" :min="MAX_TOKENS_MIN" :max="MAX_TOKENS_MAX" class="step-input"
              @blur="clamp('maxTokens', MAX_TOKENS_MIN, MAX_TOKENS_MAX, DEFAULT_MAX_TOKENS)" />
            <button type="button" class="step-btn" @click="step('maxTokens', 1024, MAX_TOKENS_MIN, MAX_TOKENS_MAX)" :disabled="form.maxTokens >= MAX_TOKENS_MAX"><AppIcon name="plus" :size="14" /></button>
          </div>
          <span class="hint">模型单次回复允许生成的最大 token 数；范围 256~1048576，默认 8192</span>
        </div>
        <div class="field">
          <label>额外参数（JSON）</label>
          <textarea v-model="form.extraParamsText" rows="3" class="mono" @input="validateExtra"></textarea>
          <span class="hint" :class="{ bad: extraError }">{{ extraError || '个性化模型参数，例如 {"enable_thinking": true}、{"reasoning_effort": "high"}' }}</span>
        </div>
        <div class="actions">
          <button class="btn" @click="testConnection" :disabled="testing">{{ testing ? '测试中…' : '测试连接' }}</button>
          <span v-if="testResult" :class="testResult.ok ? 'ok' : 'bad-text'">{{ testResult.text }}</span>
        </div>
      </div>
    </section>

    <!-- Agent 配置 -->
    <section class="card">
      <div class="card-header">
        <span class="card-icon"><AppIcon name="brain" :size="15" /></span>
        <div class="card-head-main">
          <div class="card-title">Agent 配置</div>
          <div class="card-sub">人设提示词、记忆窗口与高危操作确认</div>
        </div>
      </div>
      <div class="card-body form">
        <div class="field">
          <label>配置档</label>
          <div class="profile-row">
            <select :value="activeAgentProfile" @change="switchAgentProfile($event.target.value)">
              <option v-for="(p, name) in agentProfiles" :key="name" :value="name">{{ p.label || name }}</option>
            </select>
            <button class="btn" @click="showAddAgentProfile = true" title="新增 Agent 配置档"><AppIcon name="plus" :size="14" />新增</button>
            <button class="btn warn" @click="deleteAgentProfile" :disabled="activeAgentProfile === 'default'" title="删除当前 Agent 配置档（default 不可删除）"><AppIcon name="trash" :size="14" />删除</button>
          </div>
        </div>
        <div class="field">
          <label>人设提示词（可编辑，留空使用默认傲娇猫咪人设）</label>
          <textarea v-model="form.persona" rows="10" class="mono persona"
            placeholder="你是「优墨」……（支持 {app_name} {time} {os_user} 变量）"></textarea>
          <span class="hint">{{ form.persona.length }} 字</span>
        </div>
        <div class="field">
          <label>记忆窗口（条）</label>
          <div class="stepper">
            <button type="button" class="step-btn" @click="step('memoryWindow', -1, 2, 500)" :disabled="form.memoryWindow <= 2"><AppIcon name="minus" :size="14" /></button>
            <input type="number" v-model.number="form.memoryWindow" min="2" max="500" class="step-input"
              @blur="clamp('memoryWindow', 2, 500, 50)" />
            <button type="button" class="step-btn" @click="step('memoryWindow', 1, 2, 500)" :disabled="form.memoryWindow >= 500"><AppIcon name="plus" :size="14" /></button>
          </div>
          <span class="hint">对话上下文保留的最近消息条数，超出后自动裁剪（默认 50）</span>
        </div>
        <div class="field">
          <label>递归上限（步）</label>
          <div class="stepper">
            <button type="button" class="step-btn" @click="step('recursionLimit', -1, 1, 9999)" :disabled="form.recursionLimit <= 1"><AppIcon name="minus" :size="14" /></button>
            <input type="number" v-model.number="form.recursionLimit" min="1" max="9999" class="step-input"
              @blur="clamp('recursionLimit', 1, 9999, 100)" />
            <button type="button" class="step-btn" @click="step('recursionLimit', 1, 1, 9999)" :disabled="form.recursionLimit >= 9999"><AppIcon name="plus" :size="14" /></button>
          </div>
          <span class="hint">单轮对话 Agent 可执行的最大步数（含工具调用），范围 1~9999，过小会提前中断（默认 100）</span>
        </div>
        <div class="field">
          <label>Tavily API Key（网络搜索工具）</label>
          <div class="key-row">
            <input v-model="form.tavilyApiKey" :type="showTavilyKey ? 'text' : 'password'" placeholder="tvly-..." />
            <button class="mini" @click="showTavilyKey = !showTavilyKey">{{ showTavilyKey ? '隐藏' : '显示' }}</button>
          </div>
          <span class="hint">用于 internet_search 工具，留空则无法使用网络搜索功能</span>
        </div>
        <div class="field">
          <label class="check"><input type="checkbox" v-model="form.agentEnableOcr" /> 启用对话文档解析（OCR）</label>
          <span class="hint">开启后，Agent 对话中上传的文档会进行 OCR 解析并入库；关闭后仅保存文件到存储目录，不做解析</span>
        </div>
        <div class="field" v-if="form.agentEnableOcr">
          <label>对话文档解析引擎（OCR）</label>
          <select v-model="form.agentOcrEngine">
            <option value="markitdown">MarkItDown（快速）</option>
            <option value="docling">Docling（更精细，支持图片识别）</option>
          </select>
          <span class="hint">Agent 对话中解析上传文档所使用的引擎，默认 MarkItDown</span>
        </div>
        <div class="field">
          <label>高危操作人工确认（Interrupt）</label>
          <div class="interrupt-grid">
            <label v-for="t in interruptTools" :key="t.name" class="check">
              <input type="checkbox" v-model="form.interruptOn[t.name]" /> {{ t.label }}
            </label>
          </div>
          <div class="actions">
            <button class="mini" type="button" @click="setAllInterrupt(true)">全部打断</button>
            <button class="mini" type="button" @click="setAllInterrupt(false)">全部放行</button>
          </div>
          <span class="hint">勾选的工具在 Agent 执行前会中断并等待你确认（同意/拒绝）；取消勾选则直接放行自动执行</span>
        </div>
        <div class="field">
          <label class="check">
            <input type="checkbox" v-model="form.autoApproveSkillScripts" />
            技能脚本免确认（skills 下的 scripts 目录）
          </label>
          <span class="hint">
            开启后，运行技能自带脚本（python skills/技能名/scripts/脚本.py，可带前置 Set-Location）不再弹确认；
            其它命令、以及带管道 / 重定向 / 变量 / 反引号等拼接写法的命令仍会打断。
            仅在勾选上面的「执行命令（execute）」时生效。
          </span>
        </div>
        <div class="actions">
          <button class="btn" @click="togglePreview">{{ preview ? '隐藏完整提示词' : '预览完整提示词' }}</button>
          <button class="btn" @click="resetPersona">恢复默认人设</button>
        </div>
        <pre v-if="preview" class="preview-box">{{ preview }}</pre>
      </div>
    </section>

    <!-- 工作区 -->
    <section class="card wide">
      <div class="card-header">
        <span class="card-icon"><AppIcon name="folder" :size="15" /></span>
        <div class="card-head-main">
          <div class="card-title">工作区</div>
          <div class="card-sub">Agent 读写文件、执行命令的根目录</div>
        </div>
      </div>
      <div class="card-body form">
        <div class="field">
          <label>当前工作区</label>
          <div class="workspace-row">
            <input :value="workspaceDisplay" readonly class="mono workspace-path" />
            <button class="btn" type="button" @click="pickWorkspace">
              <AppIcon name="folder" :size="14" />选择目录
            </button>
            <button class="btn" type="button" @click="resetWorkspace" :disabled="!form.workspace">恢复默认</button>
          </div>
          <span class="hint">
            文件工具（ls / read_file / write_file / edit_file / glob / grep）与 shell 都以此目录为根，
            相对路径相对它解析；留空则使用应用内部 runtime 目录。
          </span>
          <span class="hint">
            技能库与任务清单始终留在应用数据目录，不受工作区影响；正在生成的那一轮仍使用旧工作区，下一条消息起生效。
          </span>
        </div>
      </div>
    </section>

    <!-- dsh 子代理（DeepSeek Harness） -->
    <section class="card wide">
      <div class="card-header">
        <span class="card-icon"><AppIcon name="layers" :size="15" /></span>
        <div class="card-head-main">
          <div class="card-title">dsh 子代理（DeepSeek Harness）</div>
          <div class="card-sub">子代理的连接方式、输出上限与系统提示词</div>
        </div>
      </div>
      <div class="card-body form">
        <div class="field">
          <span class="hint">dsh 会自动带上主 Agent 的 skills：委托执行时会挂载「技能管理」里的同一套技能，按需加载，无需重复配置。</span>
        </div>
        <div class="field">
          <label class="check"><input type="checkbox" v-model="form.dshUseMainLlm" /> 复用主 Agent 的 LLM</label>
          <span class="hint">
            勾选时 dsh 直接使用「模型连接」中当前激活的配置档（{{ mainLlmSummary }}）；取消勾选则使用下方独立连接参数
          </span>
        </div>
        <!-- 复用主 Agent LLM 时，独立连接参数整组隐藏（值仍随保存一起落盘，不丢失） -->
        <template v-if="!form.dshUseMainLlm">
          <div class="field">
            <label>Base URL</label>
            <input v-model="form.dshBaseUrl" placeholder="http://localhost:8080/v1" />
          </div>
          <div class="field">
            <label>API Key</label>
            <div class="key-row">
              <input v-model="form.dshApiKey" :type="showDshKey ? 'text' : 'password'" placeholder="sk-..." @focus="revealDshKey" />
              <button class="mini" @click="showDshKey = !showDshKey">{{ showDshKey ? '隐藏' : '显示' }}</button>
            </div>
          </div>
          <div class="field">
            <label>模型名称</label>
            <input v-model="form.dshModel" placeholder="Qwen3.6-35B" />
            <span class="hint">dsh 路由名固定为 deepseek-official，模型 id 原样透传给网关，填服务商/自建服务实际使用的模型名</span>
          </div>
        </template>
        <div class="field">
          <label>系统提示词</label>
          <textarea v-model="form.dshSystemPrompt" rows="12" class="mono persona"
            placeholder="留空则使用内置默认 dsh 提示词"></textarea>
          <span class="hint">{{ form.dshSystemPrompt.length }} 字 · 支持 {shell_guidance} 变量，会在运行平台展开为 pwsh / bash 指引</span>
        </div>
        <div class="field">
          <label>最大输出 tokens</label>
          <div class="stepper">
            <button type="button" class="step-btn" @click="step('dshMaxTokens', -1024, 1, DSH_MAX_TOKENS_LIMIT)" :disabled="form.dshMaxTokens <= 1"><AppIcon name="minus" :size="14" /></button>
            <input type="number" v-model.number="form.dshMaxTokens" min="1" :max="DSH_MAX_TOKENS_LIMIT" class="step-input"
              @blur="clamp('dshMaxTokens', 1, DSH_MAX_TOKENS_LIMIT, DSH_MAX_TOKENS_LIMIT)" />
            <button type="button" class="step-btn" @click="step('dshMaxTokens', 1024, 1, DSH_MAX_TOKENS_LIMIT)" :disabled="form.dshMaxTokens >= DSH_MAX_TOKENS_LIMIT"><AppIcon name="plus" :size="14" /></button>
          </div>
          <span class="hint">dsh 单次响应的输出上限，范围 1~131072（DashScope qwen 系只接受该区间，默认 131072）</span>
        </div>
        <div class="field">
          <label>推理强度（reasoningEffort）</label>
          <select v-model="form.dshReasoningEffort">
            <option v-for="o in dshReasoningEffortOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>
          <span class="hint">仅 dsh 适配器识别（deepseek-official）；与主 Agent 的「额外参数」互不影响</span>
        </div>
        <div class="actions">
          <button class="btn" @click="resetDshPrompt">恢复默认提示词</button>
        </div>
      </div>
    </section>

    <!-- 知识库（RAG） -->
    <section class="card wide">
      <div class="card-header">
        <span class="card-icon"><AppIcon name="database" :size="15" /></span>
        <div class="card-head-main">
          <div class="card-title">知识库（RAG）</div>
          <div class="card-sub">上传自动入库与向量模型配置</div>
        </div>
      </div>
      <div class="card-body form">
        <div class="field">
          <label class="check"><input type="checkbox" v-model="form.ragAutoEmbedding" /> 聊天上传文件自动入库</label>
          <span class="hint">开启后，普通对话中上传的文件将异步自动 Embedding 到默认知识库</span>
        </div>
        <div class="field">
          <label class="check"><input type="checkbox" v-model="form.ragHybrid" /> 混合检索（向量 + 关键词）</label>
          <span class="hint">默认开启：向量语义召回 + BM25 关键词召回，再用 RRF 融合；对编号、专有名词、代码标识符更稳。关闭后回到纯向量 top-k</span>
        </div>
        <div class="field">
          <label>索引健康</label>
          <div class="rag-health" :class="{ bad: ragHealth && !ragHealth.dimensionMatch && !ragHealth.empty }">
            <div class="rag-health-grid">
              <span class="rh-item"><span class="rh-label">模型</span>{{ ragHealth?.embeddingModel?.model || '—' }}</span>
              <span class="rh-item">
                <span class="rh-label">维度</span>
                {{ ragHealth ? `${ragHealth.embeddingDim ?? '—'} / 集合 ${ragHealth.collectionDim ?? '—'}` : '检测中…' }}
              </span>
              <span class="rh-item">
                <span class="rh-label">分块 / 文档</span>
                {{ ragHealth ? `${ragHealth.count} / ${ragHealth.documentCount}` : '—' }}
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
          <span class="hint">向量维度与集合不一致时，上传新文档会失败；重建会从原始文件重新生成全部索引</span>
        </div>
        <div class="field">
          <label>Embedding 模型来源</label>
          <select v-model="form.ragEmbedType" @change="onEmbedTypeChange">
            <option value="local">本地模型（Local）</option>
            <option value="remote">远程 API（OpenAI-Compatible）</option>
          </select>
          <span class="hint">本地模式无需 Base URL / API Key，首次使用时自动下载模型</span>
        </div>
        <div class="field">
          <label>Embedding 模型名称</label>
          <input v-model="form.ragEmbedModel" :placeholder="form.ragEmbedType === 'local' ? '由智能下载自动确定' : 'text-embedding-3-small'"
            :disabled="form.ragEmbedType === 'local'" @change="onEmbedModelChange" />
          <span class="hint">本地模式下模型由「智能下载」按显卡条件自动确定（N 卡 ≥4G 显存用 bge-large，否则 bge-small），无需手动填写；远程模式填服务商模型名</span>
        </div>
        <div class="field">
          <label>Base URL</label>
          <input v-model="form.ragEmbedBaseUrl" placeholder="https://api.openai.com/v1" :disabled="form.ragEmbedType !== 'remote'" />
        </div>
        <div class="field">
          <label>API Key</label>
          <div class="key-row">
            <input v-model="form.ragEmbedApiKey" :type="showRagKey ? 'text' : 'password'" placeholder="sk-..." :disabled="form.ragEmbedType !== 'remote'" />
            <button class="mini" @click="showRagKey = !showRagKey">{{ showRagKey ? '隐藏' : '显示' }}</button>
          </div>
          <span class="hint">仅远程模式需要</span>
        </div>
        <div class="field">
          <label>知识库文档解析引擎（OCR）</label>
          <select v-model="form.ragOcrEngine">
            <option value="docling">Docling（更精细，支持图片识别）</option>
            <option value="markitdown">MarkItDown（快速）</option>
          </select>
          <span class="hint">知识库维护上传时解析文档所使用的引擎，默认 Docling</span>
        </div>
        <div v-if="form.ragEmbedType === 'local' && !form.ragLocalDownloaded" id="rag-model" class="field">
          <label>本地模型下载</label>
          <div class="actions">
            <button class="btn primary" @click="downloadModel" :disabled="downloading">
              <span v-if="downloading" class="btn-spinner"></span>
              <span v-else class="btn-label"><AppIcon name="download" :size="14" />下载模型</span>
              <span v-if="downloading">下载中…</span>
            </button>
            <span v-if="downloadResult" :class="downloadResult.ok ? 'ok' : 'bad-text'">{{ downloadResult.text }}</span>
          </div>
          <span class="hint">自动检测网络（不可直连时走 hf-mirror 镜像）与显卡（N 卡 ≥4G 显存下载 bge-large，否则 bge-small），模型较大请耐心等待</span>
        </div>
        <div v-else-if="form.ragEmbedType === 'local'" id="rag-model" class="field">
          <label>本地模型状态</label>
          <div class="actions">
            <span class="ok"><AppIcon name="check" :size="13" />模型已下载{{ form.ragEmbedModel ? `：${form.ragEmbedModel}` : '' }}</span>
            <button class="mini" @click="redownloadModel" :disabled="downloading" title="清除已下载状态并重新下载">重新下载</button>
            <span v-if="downloadResult" :class="downloadResult.ok ? 'ok' : 'bad-text'">{{ downloadResult.text }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- 网络代理 -->
    <section class="card">
      <div class="card-header">
        <span class="card-icon"><AppIcon name="globe" :size="15" /></span>
        <div class="card-head-main">
          <div class="card-title">网络代理</div>
          <div class="card-sub">HTTP / HTTPS 代理与直连白名单</div>
        </div>
      </div>
      <div class="card-body form">
        <div class="field">
          <label class="check"><input type="checkbox" v-model="form.proxyEnabled" /> 启用 HTTP / HTTPS 代理</label>
          <span class="hint">保存后 Electron 立即生效；Python Agent 需在启用/停用后点击顶部「重启服务进程」以刷新代理环境变量</span>
        </div>
        <div class="field">
          <label>HTTP 代理</label>
          <input v-model="form.proxyHttp" placeholder="http://127.0.0.1:7890" :disabled="!form.proxyEnabled" />
          <span class="hint">支持 http:// 或 socks5:// 前缀，例如 http://127.0.0.1:7890</span>
        </div>
        <div class="field">
          <label>HTTPS 代理</label>
          <input v-model="form.proxyHttps" placeholder="留空则与 HTTP 代理相同" :disabled="!form.proxyEnabled" />
        </div>
        <div class="field">
          <label>绕过代理（NO_PROXY）</label>
          <input v-model="form.proxyNoProxy" placeholder="localhost,127.0.0.1,*.example.com" :disabled="!form.proxyEnabled" />
          <span class="hint">逗号分隔的主机名单，命中这些地址的请求不走代理</span>
        </div>
      </div>
    </section>

    <!-- 语音朗读（TTS） -->
    <section class="card">
      <div class="card-header">
        <span class="card-icon"><AppIcon name="volume" :size="15" /></span>
        <div class="card-head-main">
          <div class="card-title">语音朗读（TTS）</div>
          <div class="card-sub">系统语音、语速与音调</div>
        </div>
      </div>
      <div class="card-body form">
        <div class="field">
          <label>语音方案</label>
          <select v-model="form.voiceEngine">
            <option value="web-speech">Web Speech API（系统语音 · 无需 GPU）</option>
            <option value="local" disabled>本地 TTS（N 卡 ≥8GB，Phase 2 敬请期待）</option>
          </select>
          <span class="hint">当前方案使用系统自带语音，无需显卡、零依赖；本地 TTS 将随 GPU 推理支持逐步开放</span>
        </div>
        <div class="field">
          <label class="check"><input type="checkbox" v-model="form.voiceEnabled" /> 启用语音朗读</label>
          <span class="hint">开启后，每条 AI 回复气泡下都会出现朗读按钮</span>
        </div>
        <div class="field">
          <label class="check"><input type="checkbox" v-model="form.voiceAutoRead" :disabled="!form.voiceEnabled" /> AI 自动朗读</label>
          <span class="hint">开启后 AI 回复生成时自动朗读；内置播放缓冲抗网络波动，回复结束会补全剩余内容</span>
        </div>
        <div class="field">
          <label>中文语音</label>
          <div class="profile-row">
            <select v-model="form.voiceVoiceName" class="voice-select" :disabled="!form.voiceEnabled">
              <option v-for="v in voiceOptions" :key="v.name" :value="v.name">{{ voiceLabel(v) }}</option>
            </select>
            <button class="mini voice-preview-btn" type="button" :disabled="!form.voiceEnabled" @click="voicePreview" :title="testingVoice ? '正在试听…' : '试听当前语音'">
              <template v-if="testingVoice"><span class="eq"><i></i><i></i><i></i></span>试听中</template>
              <template v-else>试听</template>
            </button>
          </div>
          <span class="hint" v-if="!voiceOptions.length">{{ voiceNoVoicesHint }}</span>
          <span class="hint" v-else>选择朗读时使用的语音；留空则自动挑选中文语音</span>
        </div>
        <div class="field">
          <label>语速 <span class="inline-val">{{ form.voiceRate.toFixed(1) }}</span></label>
          <input type="range" min="0.5" max="2" step="0.1" v-model.number="form.voiceRate" :disabled="!form.voiceEnabled" />
        </div>
        <div class="field">
          <label>音调 <span class="inline-val">{{ form.voicePitch.toFixed(1) }}</span></label>
          <input type="range" min="0.5" max="2" step="0.1" v-model.number="form.voicePitch" :disabled="!form.voiceEnabled" />
        </div>
      </div>
    </section>

    <!-- 闲置提醒 -->
    <section class="card">
      <div class="card-header">
        <span class="card-icon"><AppIcon name="clock" :size="15" /></span>
        <div class="card-head-main">
          <div class="card-title">闲置提醒</div>
          <div class="card-sub">久未互动时让本喵叫你一声</div>
        </div>
      </div>
      <div class="card-body form inline">
        <label class="check"><input type="checkbox" v-model="form.idleEnabled" /> 启用</label>
        <label>闲置阈值（分钟）<input type="number" v-model.number="form.idleThreshold" min="1" class="num" /></label>
        <label>提醒冷却（分钟）<input type="number" v-model.number="form.idleQuiet" min="1" class="num" /></label>
      </div>
    </section>

    <!-- 提醒事项 -->
    <section class="card">
      <div class="card-header">
        <span class="card-icon"><AppIcon name="bell" :size="15" /></span>
        <div class="card-head-main">
          <div class="card-title">提醒事项</div>
          <div class="card-sub">检查频率与气泡停留时长</div>
        </div>
      </div>
      <div class="card-body form">
        <div class="field">
          <label>检查间隔（秒）</label>
          <div class="stepper">
            <button type="button" class="step-btn" @click="step('reminderPoll', -1, 3, 30)" :disabled="form.reminderPoll <= 3"><AppIcon name="minus" :size="14" /></button>
            <input type="number" v-model.number="form.reminderPoll" min="3" max="30" class="step-input"
              @blur="clamp('reminderPoll', 3, 30, 5)" />
            <button type="button" class="step-btn" @click="step('reminderPoll', 1, 3, 30)" :disabled="form.reminderPoll >= 30"><AppIcon name="plus" :size="14" /></button>
          </div>
          <span class="hint">后台检查提醒是否到点的频率，范围 3~30 秒（默认 5 秒，越小触发越及时）</span>
        </div>
        <div class="field">
          <label>气泡显示时长（秒）</label>
          <select v-model.number="form.reminderDuration">
            <option v-for="d in reminderDurationOptions" :key="d" :value="d">{{ d }} 秒</option>
          </select>
          <span class="hint">提醒弹出时桌宠气泡的停留时长，可选 3~30 秒（默认 8 秒）</span>
        </div>
      </div>
    </section>

    <!-- 桌宠 -->
    <section class="card">
      <div class="card-header">
        <span class="card-icon"><AppIcon name="bot" :size="15" /></span>
        <div class="card-head-main">
          <div class="card-title">桌宠</div>
          <div class="card-sub">显示开关与快速提问快捷键</div>
        </div>
      </div>
      <div class="card-body form">
        <div class="field">
          <label class="check"><input type="checkbox" v-model="form.petEnabled" /> 启用桌宠</label>
          <span class="hint">桌宠不可见时（关闭或右键临时隐藏），提醒事项与闲置提醒将以系统通知呈现，不再使用桌宠气泡</span>
        </div>
        <div class="field">
          <label>快速提问快捷键（全局生效，唤起桌宠输入框）</label>
          <div class="hotkey-row">
            <div
              class="hotkey-box" :class="{ recording: recordingKey, bad: hotkeyError }"
              tabindex="0" title="点击后按下组合键进行录制"
              @click="startRecord" @blur="stopRecord"
              @keydown.prevent="onRecordKeydown"
            >{{ hotkeyDisplay }}</div>
            <button v-if="form.quickAskShortcut" class="mini" @click="form.quickAskShortcut = ''">禁用</button>
          </div>
          <span class="hint" :class="{ bad: hotkeyError }">
            {{ hotkeyError || (recordingKey ? '请按下组合键（需包含 Ctrl / Alt / Shift / Win），Esc 取消' : '例如 Alt+Shift+Q；留空表示禁用') }}
          </span>
          <span v-if="hotkeyStatus" :class="hotkeyStatus.ok ? 'ok' : 'bad-text'">{{ hotkeyStatus.text }}</span>
        </div>
      </div>
    </section>
    </div>

    <div v-if="toast" class="toast">{{ toast }}</div>

    <!-- 新增 LLM 配置档弹窗 -->
    <div v-if="showAddProfile" class="modal-overlay" @click.self="showAddProfile = false">
      <div class="modal">
        <h3>新增 LLM 配置档</h3>
        <div class="field">
          <label>配置档名称</label>
          <input v-model="newProfileName" placeholder="例如 work、personal" @keydown.enter="addProfile" ref="profileNameInput" />
          <span class="hint" :class="{ bad: newProfileError }">{{ newProfileError || '仅允许字母、数字、下划线和短横线' }}</span>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="showAddProfile = false">取消</button>
          <button class="btn primary" @click="addProfile">确定</button>
        </div>
      </div>
    </div>

    <!-- 新增 Agent 配置档弹窗 -->
    <div v-if="showAddAgentProfile" class="modal-overlay" @click.self="showAddAgentProfile = false">
      <div class="modal">
        <h3>新增 Agent 配置档</h3>
        <div class="field">
          <label>配置档名称</label>
          <input v-model="newAgentProfileName" placeholder="例如 work、personal" @keydown.enter="addAgentProfile" ref="agentProfileNameInput" />
          <span class="hint" :class="{ bad: newAgentProfileError }">{{ newAgentProfileError || '仅允许字母、数字、下划线和短横线' }}</span>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="showAddAgentProfile = false">取消</button>
          <button class="btn primary" @click="addAgentProfile">确定</button>
        </div>
      </div>
    </div>

    <!-- 切换 Embedding 模型确认弹窗 -->
    <div v-if="showEmbedConfirm" class="modal-overlay" @click.self="cancelEmbedChange">
      <div class="modal">
        <h3>确认切换 Embedding 模型？</h3>
        <p class="hint" style="line-height: 1.6; margin: 0 0 8px;">
          切换后，知识库中所有已入库文档的向量数据将不再匹配，需要重新 Embedding 才能继续使用。
          <br />
          是否确认切换？
        </p>
        <div class="modal-actions">
          <button class="btn" @click="cancelEmbedChange">取消</button>
          <button class="btn primary" @click="confirmEmbedChange">确认切换</button>
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
import { downloadEmbeddingModel } from '../api/embeddingModelDownload'
import { getRagHealth, getRebuildStatus, rebuildKbIndex } from '../api/kb'
import AppIcon from '../components/AppIcon.vue'

const { connect, send, on } = useAgentSocket()
const api = window.electronAPI
const route = useRoute()
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
const DEFAULT_CC_KEEP = 10
const CC_KEEP_MIN = 1
const CC_KEEP_MAX = 200
// 媒体守卫（contextCompression.media*，见 agent/middlewares.py::trim_media_history）：
// 历史图片的保留条数 / 单条体积上限 / 降采样参数，默认值与 config_loader.DEFAULTS 一致
const DEFAULT_MEDIA_KEEP = 1
const MEDIA_KEEP_MIN = 0
const MEDIA_KEEP_MAX = 20
const DEFAULT_MEDIA_MAX_KB = 512
const MEDIA_MAX_KB_MIN = 0
const MEDIA_MAX_KB_MAX = 16384
const DEFAULT_MEDIA_MAX_PX = 1280
const MEDIA_MAX_PX_MIN = 128
const MEDIA_MAX_PX_MAX = 4096
const DEFAULT_MEDIA_JPEG_QUALITY = 80
const MEDIA_JPEG_QUALITY_MIN = 30
const MEDIA_JPEG_QUALITY_MAX = 95
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
  contextCompressionEnabled: true, contextCompressionModel: '', contextCompressionThreshold: DEFAULT_CC_THRESHOLD, contextCompressionKeep: DEFAULT_CC_KEEP,
  // 媒体守卫（同样随当前 LLM 配置档保存；不受上面的自动压缩开关影响）
  contextMediaKeep: DEFAULT_MEDIA_KEEP, contextMediaMaxKB: DEFAULT_MEDIA_MAX_KB, contextMediaMaxPx: DEFAULT_MEDIA_MAX_PX, contextMediaJpegQuality: DEFAULT_MEDIA_JPEG_QUALITY,
  persona: '', memoryWindow: 50, recursionLimit: 100, idleEnabled: true, idleThreshold: 30, idleQuiet: 10,
  // 工作区（agent.workspace，空=应用内部 runtime；切换即时保存，不随配置档保存）
  workspace: '',
  petEnabled: true,
  quickAskShortcut: 'Alt+Shift+Q',
  reminderPoll: 5, reminderDuration: 8,
  tavilyApiKey: '',
  agentEnableOcr: true, agentOcrEngine: 'markitdown',
  interruptOn: defaultInterruptOn(),
  // 技能脚本免确认（execute 白名单，见 python/agent/command_policy.py）
  autoApproveSkillScripts: true,
  ragAutoEmbedding: true, ragHybrid: true, ragEmbedType: 'local', ragEmbedModel: 'BAAI/bge-small-zh-v1.5',
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
  form.contextCompressionKeep = Number.isFinite(Number(cc.keepRecent)) ? Number(cc.keepRecent) : DEFAULT_CC_KEEP
  // 媒体守卫：缺省或非法值回退默认，与 config_loader.DEFAULTS 保持一致
  form.contextMediaKeep = Number.isFinite(Number(cc.mediaKeep)) ? Number(cc.mediaKeep) : DEFAULT_MEDIA_KEEP
  form.contextMediaMaxKB = Number.isFinite(Number(cc.mediaMaxKB)) ? Number(cc.mediaMaxKB) : DEFAULT_MEDIA_MAX_KB
  form.contextMediaMaxPx = Number.isFinite(Number(cc.mediaMaxPx)) ? Number(cc.mediaMaxPx) : DEFAULT_MEDIA_MAX_PX
  form.contextMediaJpegQuality = Number.isFinite(Number(cc.mediaJpegQuality)) ? Number(cc.mediaJpegQuality) : DEFAULT_MEDIA_JPEG_QUALITY
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
  const picked = await api.pickDirectory({ defaultPath: form.workspace || undefined })
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
    { path: `${llmPrefix}.contextCompression.keepRecent`, value: Number(form.contextCompressionKeep) || DEFAULT_CC_KEEP },
    // 媒体守卫：历史图片保留条数 / 单条体积上限 / 降采样参数（0 是合法值，故用 isFinite 而非 ||）
    { path: `${llmPrefix}.contextCompression.mediaKeep`, value: Number.isFinite(Number(form.contextMediaKeep)) ? Number(form.contextMediaKeep) : DEFAULT_MEDIA_KEEP },
    { path: `${llmPrefix}.contextCompression.mediaMaxKB`, value: Number.isFinite(Number(form.contextMediaMaxKB)) ? Number(form.contextMediaMaxKB) : DEFAULT_MEDIA_MAX_KB },
    { path: `${llmPrefix}.contextCompression.mediaMaxPx`, value: Number.isFinite(Number(form.contextMediaMaxPx)) ? Number(form.contextMediaMaxPx) : DEFAULT_MEDIA_MAX_PX },
    { path: `${llmPrefix}.contextCompression.mediaJpegQuality`, value: Number.isFinite(Number(form.contextMediaJpegQuality)) ? Number(form.contextMediaJpegQuality) : DEFAULT_MEDIA_JPEG_QUALITY },
    { path: `${llmPrefix}.extraParams`, value: JSON.parse(form.extraParamsText || '{}') },
    { path: 'agent.activeProfile', value: activeAgentProfile.value },
    { path: `${agentPrefix}.persona`, value: form.persona },
    { path: `${agentPrefix}.memoryWindow`, value: Number(form.memoryWindow) || 50 },
    { path: `${agentPrefix}.recursionLimit`, value: Number(form.recursionLimit) || 100 },
    { path: 'pet.idleReminder.enabled', value: form.idleEnabled },
    { path: 'pet.idleReminder.thresholdMinutes', value: form.idleThreshold },
    { path: 'pet.idleReminder.quietPeriodMinutes', value: form.idleQuiet },
    { path: 'pet.enabled', value: !!form.petEnabled },
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
  // dsh 独立 LLM 的 apiKey：同样仅在非掩码时写入
  if (!String(form.dshApiKey).startsWith('***')) {
    patches.push({ path: 'dsh.llm.apiKey', value: form.dshApiKey.trim() })
  }
  const res = await api.setConfigMany(patches)
  if (!res.success) return showToast('保存失败: ' + (res.message || ''))
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
  // 知识库页「前往下载模型」跳转过来时，滚动定位到模型下载区域
  if (route.hash === '#rag-model') {
    nextTick(() => {
      setTimeout(() => {
        document.getElementById('rag-model')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }, 300)
    })
  }
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
</script>

<style scoped>
.settings-page {
  max-width: 1200px;
  margin: 0 auto;
  animation: fadeUp var(--dur-slow) var(--ease-out) backwards;
}

.settings-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
}
@media (min-width: 1080px) {
  .settings-grid {
    grid-template-columns: 1fr 1fr;
  }
  /* 模型连接和 Agent 配置占满整行（内容较多） */
  .settings-grid .card:nth-child(1),
  .settings-grid .card:nth-child(2) {
    grid-column: 1 / -1;
  }
}
/* 内容较长的卡片（如 dsh 子代理）显式占满整行，不依赖 nth-child 位置 */
.settings-grid .card.wide {
  grid-column: 1 / -1;
}
/* ===== 页头 ===== */
/* 设置页很长：页头（含保存 / 重启）吸顶，滚到任何位置都能一键保存。
   半透明 + 模糊，避免破坏整页的「墨面」质感 */
.page-header {
  position: sticky;
  top: -26px;
  z-index: 20;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  flex-wrap: wrap;
  margin: 0 -32px 22px;
  padding: 20px 32px 16px;
  background: rgba(9, 12, 17, 0.82);
  backdrop-filter: blur(14px);
  border-bottom: 1px solid var(--line-1);
}

.page-head-main {
  min-width: 0;
}

.eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.2em;
  color: var(--amber-500);
  margin-bottom: 8px;
}

.page-title {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--text-1);
  line-height: 1.25;
}

.page-subtitle {
  margin-top: 7px;
  font-size: 13px;
  color: var(--text-3);
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
    color var(--dur-fast), transform var(--dur-fast), box-shadow var(--dur-fast),
    filter var(--dur-fast);
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
  background: var(--amber-grad);
  border-color: transparent;
  color: var(--amber-ink);
  font-weight: 650;
  box-shadow: var(--shadow-1), inset 0 1px 0 color-mix(in srgb, var(--amber-100) 30%, transparent);
}

.btn.primary:hover:not(:disabled) {
  background: var(--amber-grad);
  filter: brightness(1.06);
  box-shadow: var(--shadow-amber), inset 0 1px 0 color-mix(in srgb, var(--amber-100) 34%, transparent);
}

.btn.warn {
  background: var(--coral-a12);
  border-color: color-mix(in srgb, var(--coral-400) 32%, transparent);
  color: var(--coral-400);
}

.btn.warn:hover:not(:disabled) {
  background: color-mix(in srgb, var(--coral-400) 18%, transparent);
  border-color: color-mix(in srgb, var(--coral-400) 52%, transparent);
}

/* 重启完成：同一颗按钮转为「安静的绿灯」，避免珊瑚色里跳出一枚绿勾 */
.btn.warn.is-done {
  background: var(--jade-a12);
  border-color: color-mix(in srgb, var(--jade-400) 32%, transparent);
  color: var(--jade-400);
}

.btn-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.btn-check {
  color: var(--jade-400);
}

.btn-spinner {
  width: 13px;
  height: 13px;
  flex-shrink: 0;
  border: 2px solid color-mix(in srgb, currentColor 25%, transparent);
  border-top-color: currentColor;
  border-radius: 50%;
  animation: spin 0.75s linear infinite;
}

/* ===== RAG 索引健康 ===== */
.rag-health {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
}

.rag-health.bad {
  border-color: rgba(233, 119, 110, 0.28);
  background: rgba(233, 119, 110, 0.045);
}

.rag-health-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 18px;
}

.rh-item {
  color: var(--text-2);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.rh-label {
  margin-right: 5px;
  color: var(--text-4);
  font-size: 10.5px;
}

.rag-warn {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  color: var(--coral-400);
  font-size: 11.5px;
  line-height: 1.55;
}

.rag-warn :deep(svg) {
  flex-shrink: 0;
  margin-top: 2px;
}

.rag-health-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.rag-health-tip {
  color: var(--text-4);
  font-size: 10.5px;
}

.rag-progress {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.rag-progress-bar {
  height: 5px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 999px;
}

.rag-progress-bar span {
  display: block;
  height: 100%;
  background: var(--amber-grad);
  border-radius: inherit;
  transition: width 0.3s ease;
}

.rag-progress-text {
  color: var(--text-4);
  font-size: 10.5px;
  font-variant-numeric: tabular-nums;
}

/* ===== 卡片 ===== */
.card {  position: relative;
  background: linear-gradient(180deg, var(--ink-850), var(--ink-800));
  border: 1px solid var(--line-1);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-1), var(--hairline);
  overflow: hidden;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 14px 20px;
  border-bottom: 1px solid var(--line-1);
}

.card-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  border-radius: var(--r-sm);
  color: var(--amber-300);
  background: var(--amber-a08);
  border: 1px solid var(--amber-a20);
}

.card-head-main {
  min-width: 0;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text-1);
}

.card-sub {
  margin-top: 1px;
  font-size: 11.5px;
  color: var(--text-4);
}

.card-body {
  padding: 20px;
}

/* ===== 字段节奏：统一 20px 分组间距 ===== */
.form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.form .field {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.form.inline {
  flex-direction: row;
  align-items: center;
  gap: 22px;
  flex-wrap: wrap;
}
.interrupt-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 8px 14px;
  padding: 12px 14px;
  background: var(--ink-1000);
  border: 1px solid var(--line-1);
  border-radius: var(--r-md);
}

.check {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
  color: var(--text-2);
  cursor: pointer;
  user-select: none;
}

.form.inline label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
  color: var(--text-3);
}

.form.inline label.check {
  color: var(--text-2);
}

.form.inline input.num {
  width: 84px;
}

label {
  font-size: 12px;
  color: var(--text-3);
}

/* ===== 输入控件：36px 高，深墨底，琥珀焦点环 ===== */
input:not([type]),
input[type='text'],
input[type='password'],
input[type='number'],
input[type='search'],
select,
textarea {
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

textarea {
  height: auto;
  min-height: 88px;
  padding: 10px 12px;
  line-height: 1.6;
  resize: vertical;
}

input::placeholder,
textarea::placeholder {
  color: var(--text-4);
}

input:not([type]):hover:not(:disabled),
input[type='text']:hover:not(:disabled),
input[type='password']:hover:not(:disabled),
input[type='number']:hover:not(:disabled),
input[type='search']:hover:not(:disabled),
select:hover:not(:disabled),
textarea:hover:not(:disabled) {
  border-color: var(--line-3);
}

input:not([type]):focus,
input[type='text']:focus,
input[type='password']:focus,
input[type='number']:focus,
input[type='search']:focus,
select:focus,
textarea:focus {
  outline: none;
  border-color: var(--amber-a55);
  background-color: var(--ink-900);
  box-shadow: 0 0 0 3px var(--amber-a12);
}

input:disabled,
select:disabled,
textarea:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 下拉：去掉原生箭头，改为发丝线三角 */
select {
  appearance: none;
  -webkit-appearance: none;
  padding-right: 32px;
  background-image: linear-gradient(45deg, transparent 50%, var(--text-3) 50%),
    linear-gradient(135deg, var(--text-3) 50%, transparent 50%);
  background-position: calc(100% - 16px) 15px, calc(100% - 11px) 15px;
  background-size: 5px 5px, 5px 5px;
  background-repeat: no-repeat;
  cursor: pointer;
}

select:disabled {
  cursor: not-allowed;
}

select option {
  background: var(--ink-800);
  color: var(--text-1);
}

/* 复选框：琥珀实心块 + 墨色对勾 */
input[type='checkbox'] {
  appearance: none;
  -webkit-appearance: none;
  position: relative;
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  margin: 0;
  border: 1px solid var(--line-4);
  border-radius: 5px;
  background: var(--ink-1000);
  cursor: pointer;
  transition: background var(--dur-fast), border-color var(--dur-fast), box-shadow var(--dur-fast);
}

input[type='checkbox']:hover:not(:disabled) {
  border-color: var(--amber-a55);
}

input[type='checkbox']:checked {
  background: var(--amber-grad);
  border-color: transparent;
}

input[type='checkbox']:checked::after {
  content: '';
  position: absolute;
  left: 5px;
  top: 1px;
  width: 4px;
  height: 8px;
  border: solid var(--amber-ink);
  border-width: 0 2px 2px 0;
  transform: rotate(43deg);
}

input[type='checkbox']:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

/* 滑杆：轨道与滑块由全局主题提供，这里只控宽度 */
input[type='range'] {
  width: 100%;
}

input[type='range']:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.mono {
  font-family: var(--font-mono);
}

.persona {
  line-height: 1.6;
}

.num {
  width: 84px;
  -moz-appearance: textfield;
  appearance: textfield;
}

.num::-webkit-outer-spin-button,
.num::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

/* ===== 步进器 ===== */
.stepper {
  display: inline-flex;
  align-items: stretch;
  width: fit-content;
  height: 36px;
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  overflow: hidden;
  background: var(--ink-1000);
  transition: border-color var(--dur-fast), box-shadow var(--dur-fast);
}

.stepper:focus-within {
  border-color: var(--amber-a55);
  box-shadow: 0 0 0 3px var(--amber-a12);
}

.stepper .step-input {
  width: 76px;
  height: 100%;
  padding: 0 4px;
  text-align: center;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  color: var(--text-1);
  background: transparent;
  border: none;
  border-radius: 0;
  box-shadow: none;
  -moz-appearance: textfield;
  appearance: textfield;
}

.stepper .step-input:focus {
  outline: none;
  border: none;
  background: transparent;
  box-shadow: none;
}

.stepper .step-input::-webkit-outer-spin-button,
.stepper .step-input::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

.step-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  padding: 0;
  border: none;
  background: transparent;
  color: var(--text-3);
  cursor: pointer;
  transition: background var(--dur-fast), color var(--dur-fast);
}

.step-btn:first-child {
  border-right: 1px solid var(--line-1);
}

.step-btn:last-child {
  border-left: 1px solid var(--line-1);
}

.step-btn:hover:not(:disabled) {
  background: var(--ink-750);
  color: var(--amber-300);
}

.step-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
.hotkey-row {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.hotkey-box {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 180px;
  height: 36px;
  padding: 0 14px;
  border-radius: var(--r-sm);
  background: var(--ink-1000);
  border: 1px solid var(--line-2);
  color: var(--text-1);
  font-family: var(--font-mono);
  font-size: 12.5px;
  letter-spacing: 0.04em;
  cursor: pointer;
  user-select: none;
  text-align: center;
  transition: border-color var(--dur-fast), color var(--dur-fast), box-shadow var(--dur-fast);
}

.hotkey-box:hover {
  border-color: var(--line-3);
}

.hotkey-box.recording {
  border-color: var(--amber-a55);
  color: var(--amber-300);
  box-shadow: 0 0 0 3px var(--amber-a12);
  animation: hotkey-pulse 1.4s ease-in-out infinite;
}

.hotkey-box.bad {
  border-color: color-mix(in srgb, var(--coral-400) 55%, transparent);
  color: var(--coral-400);
}

@keyframes hotkey-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.55; }
}

.key-row {
  display: flex;
  gap: 10px;
  align-items: center;
}

.key-row input {
  flex: 1;
  min-width: 0;
}

/* 工作区：路径占满剩余宽度，按钮与 36px 输入框对齐 */
.workspace-row {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.workspace-row .workspace-path {
  flex: 1 1 260px;
  min-width: 0;
}

.workspace-row .btn {
  height: 36px;
}

.mini {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 36px;
  padding: 0 12px;
  font-family: inherit;
  font-size: 12.5px;
  font-weight: 500;
  color: var(--text-2);
  background: var(--ink-750);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  cursor: pointer;
  white-space: nowrap;
  transition: background var(--dur-fast), border-color var(--dur-fast), color var(--dur-fast);
}

.mini:hover:not(:disabled) {
  background: var(--ink-700);
  border-color: var(--line-3);
  color: var(--text-1);
}

.mini:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.hint {
  font-size: 11.5px;
  line-height: 1.65;
  color: var(--text-4);
}

.hint.bad {
  color: var(--coral-400);
}

/* 语音朗读（TTS）：滑杆与数值样式 */
.inline-val {
  margin-left: 6px;
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 600;
  color: var(--amber-300);
  font-variant-numeric: tabular-nums;
}
/* 语音下拉：压缩宽度（min-width:0 允许 flex 收缩），防止长语音名把「试听」按钮挤出可视区 */
.profile-row .voice-select { min-width: 0; flex: 1 1 150px; }

/* 试听按钮：播放中「均衡器」动画 */
.voice-preview-btn { gap: 6px; }
.eq { display: inline-flex; align-items: flex-end; gap: 2px; height: 12px; }
.eq i { width: 3px; border-radius: 1px; background: var(--amber-300); animation: eq-bounce 0.9s ease-in-out infinite; }
.eq i:nth-child(2) { animation-delay: 0.15s; }
.eq i:nth-child(3) { animation-delay: 0.3s; }
@keyframes eq-bounce { 0%, 100% { height: 4px; } 50% { height: 12px; } }

/* ===== 行内操作区 ===== */
.actions {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-top: 2px;
  flex-wrap: wrap;
}

/* 状态提示：胶囊徽章 */
.ok,
.bad-text {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 20px;
  padding: 2px 9px;
  font-size: 11px;
  font-weight: 600;
  line-height: 1.5;
  max-width: 100%;
  overflow-wrap: anywhere;
  border-radius: var(--r-full);
  border: 1px solid transparent;
}

.ok {
  color: var(--jade-400);
  background: var(--jade-a12);
  border-color: color-mix(in srgb, var(--jade-400) 24%, transparent);
}

.bad-text {
  color: var(--coral-400);
  background: var(--coral-a12);
  border-color: color-mix(in srgb, var(--coral-400) 24%, transparent);
}

.preview-box {
  margin-top: 0;
  max-height: 320px;
  padding: 14px;
  overflow: auto;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-2);
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--ink-1000);
  border: 1px dashed var(--line-3);
  border-radius: var(--r-md);
}

.profile-row {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.profile-row select {
  flex: 1 1 160px;
  min-width: 0;
}

/* 与同排 36px 的下拉框对齐 */
.profile-row .btn {
  height: 36px;
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
  cursor: not-allowed;
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

.modal {
  width: 400px;
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
  display: flex;
  flex-direction: column;
  gap: 7px;
  margin-bottom: 14px;
}

.modal-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  margin-top: 4px;
}

/* Toast 提示 - 顶部居中 */
.toast {
  position: fixed;
  top: 22px;
  left: 50%;
  z-index: 9999;
  max-width: calc(100vw - 40px);
  padding: 10px 18px;
  transform: translateX(-50%);
  font-size: 12.5px;
  font-weight: 600;
  text-align: center;
  color: var(--amber-100);
  background: color-mix(in srgb, var(--ink-900) 92%, transparent);
  border: 1px solid var(--amber-a35);
  border-radius: var(--r-full);
  box-shadow: var(--shadow-3), var(--hairline);
  backdrop-filter: blur(12px);
  animation: toast-in var(--dur) var(--ease-spring);
}

@keyframes toast-in {
  from { opacity: 0; transform: translateX(-50%) translateY(-12px); }
  to { opacity: 1; transform: translateX(-50%) translateY(0); }
}

/* ===== 窄屏兜底：任何卡片都不横向溢出 ===== */
@media (max-width: 720px) {
  .page-header { align-items: flex-start; }
  .global-actions { width: 100%; }
  .card-header { padding: 13px 16px; }
  .card-body { padding: 16px; }
}

</style>
