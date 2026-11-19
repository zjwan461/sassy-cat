# GPT-SoVITS 进程内集成说明

本文档对应 `python/tts/` 包：

| 文件 | 作用 |
|---|---|
| `gpt_sovits_engine.py` | 推理适配层（唯一与 GPT-SoVITS 耦合的文件） |
| `voices.json` | 音色注册表 + 下载清单（含 sha256、下载地址、授权） |
| `fetch_voices.py` | 音色下载 / 校验工具（只用标准库） |
| `requirements-tts.txt` | 推理所需依赖（Python 3.11） |

记录把 GPT-SoVITS 推理**跑在 agent 同一进程里**的全部注意事项。所有数据都是在本机（RTX 5060 Ti 16G）实测得到的，不是推算。

---

## 1. 为什么是进程内

面向普通用户的客户端不能要求用户自己下载、安装、配置一个 GPT-SoVITS，因此选择 vendor 一份冻结快照，随安装包分发，在 agent 进程内直接 `import`。

由此带来的取舍（接受即可，不用再纠结）：

| 代价 | 说明 |
|---|---|
| 单一故障域 | TTS 里任何 CUDA OOM / 原生崩溃会带崩整个 agent，必须用 `try/except` 包住并降级 |
| 版本锁死 | torch / transformers / numpy 被 TTS 依赖钉死，不要和 agent 的其它重依赖混装版本 |
| 驱动绑定 | cu128 要求较新驱动；老机器用户需要明确提示 |
| 安装包变大 | 模型 + torch 约 3~5 GB |

**关键原则：耦合到一个「vendor 进安装包的冻结快照」，而不是耦合到上游仓库。**
上游出 v5 也不跟，除非产品确实需要。`gpt_sovits_engine.py` 是唯一需要动的文件。

---

## 2. 三个硬约束（踩过才知道）

### 2.1 cwd 必须是 GPT-SoVITS 仓库根目录

实测三种失败方式：

| 时机 | 现象 |
|---|---|
| 从别的目录 `import` 时 | `ModuleNotFoundError: No module named 'ERes2NetV2'`（`sv.py` 用 `os.getcwd()` 拼搜索路径） |
| 加载完成后再改 cwd，处理中文 | `FileNotFoundError: 'GPT_SoVITS/text/G2PWModel_1.1.zip'`（G2PW 是懒加载的） |
| 上述两种情况之后 | 日文 `pyopenjtalk` 同理（`japanese.py` 也捕获了 `os.getcwd()`） |

引擎的处理方式（已验证有效）：

1. `_in_vendor()` 上下文管理器在加载期间临时 `chdir`，退出时还原；
2. `_prewarm_text_frontends()` 在 cwd 正确时把中/日/英文本前端**强制初始化**一遍；
3. 预热之后再切走 cwd，实测中英日文本处理全部正常。

> 所以：**加载阶段必须独占 cwd**，之后就不需要了。`_in_vendor` 内部有 `RLock`，因为 cwd 是进程级状态，多线程改会互相踩。

### 2.2 首次合成有一次性开销（约 19 秒）

实测：模型加载 16.8 s；**加载后第一次 `say()` 还要 19.2 s**（CUDA 内核编译 / 首跑开销）；第二次开始 1.3 s。

引擎用 `warmup=True` 在 `load()` 末尾自动跑一句废话把这笔账吃掉。**启动流程必须等它跑完再允许用户交互**，否则用户点“说话”会以为程序卡死。

### 2.3 GPU 推理必须串行

`TTS.run()` 不是线程安全的，显存也不允许并发。引擎用一把 `_gpu_lock` 保证串行。

- 上层如果有多路请求，请排队，不要并发调用 `say()`。
- 要打断播放：取消上层任务即可，正在算的那句最多再跑 0.3~1 秒。

---

## 3. 快速接入

```python
from tts import get_engine, TTSUnavailable

try:
    engine = get_engine()              # 单例；首次约 17 s + 预热 19 s
except TTSUnavailable as e:
    log.error("语音不可用，降级为纯文字: %s", e)
    engine = None

if engine:
    sr, audio = engine.say("你好，我是你的助手。")
    engine.write_wav("reply.wav", sr, audio)
```

在 asyncio 里**不要直接 await**（它是阻塞调用）：

```python
sr, audio = await asyncio.to_thread(engine.say, text)
```

流式（边合成边播，首包更快）：

```python
for sr, chunk in engine.say_stream(text):
    player.write(chunk)          # 每个 chunk 是 int16 numpy 片段，顺序写即可
```

切换情绪（毫秒级，不重载模型）：

```python
from tts import load_voice_config
_, voices, _ = load_voice_config("python/tts/voices.json")
engine.switch_voice(voices["tangyuge_apology"])
```

命令行自检：

```bash
python python/tts/gpt_sovits_engine.py --selftest
```

它会打印运行时信息、音色列表（含自动识别的版本）、然后合成一句话并输出 wav + RTF。

### 3.1 已实现的后端接口

已落地两个文件：`python/tts/service.py`（异步服务层）和 `python/server/tts_api.py`（路由），
并在 `server/app.py` 里 `include_router`，同时把预加载挂进 lifespan 的后台任务。

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/tts/status` | `{engine, enabled, available, loading, error, voice, voices[], device}` |
| `GET` | `/api/tts/voices` | 音色列表（含 `version`、`hasReferenceAudio`、`usable`） |
| `POST` | `/api/tts/say` | body `{text, voice?, speed?}` → `audio/wav` |
| `GET` | `/api/tts/say` | 同上，方便浏览器直接试：`?text=你好` |
| `POST` | `/api/tts/voice` | body `{name}` → 热切换音色（毫秒级） |
| `POST` | `/api/tts/preload` | 手动触发加载/预热 |

**实测（本机 RTX 5060 Ti）**

| 场景 | 耗时 |
|---|---|
| 首次 `POST /say`（含加载 17 s + 预热 19 s） | **36.9 s** |
| 第二次 `POST /say`（3 s 音频） | **1.34 s** |
| 切换音色后 `say`（3 s 音频） | **1.01 s** |
| `POST /voice` 切换音色 | < 10 ms |
| 返回体 | `audio/wav`，32 kHz 单声道 16-bit |

**设计要点**

- 引擎加载放在 `asyncio.to_thread` 里，绝不阻塞事件循环
- 一把 `asyncio.Lock` 保证 GPU 串行；引擎内部还有一把 `threading.Lock` 兜底
- 一切失败都转成 **503 + detail**，前端收到后回落 Web Speech，不要卡住对话
- `/voices` 在引擎未加载时也能返回完整列表（版本号靠读 `.pth` 前两字节）
- 预加载只在 `voice.engine` 为 `local`/`gpt-sovits` 时执行，且不阻塞启动

---

### 3.2 前端接入（已完成）

新增 `src/api/tts.js`，并改造 `src/composables/useTTS.js`——**只换播放核心，文本处理/缓冲/切句逻辑一行没动**。

`useTTS.js` 里新增的部分：

| 函数 | 作用 |
|---|---|
| `isLocalEngine()` | 判断 `ttsState.engine` 是否为 `local`/`gpt-sovits` |
| `enqueueLocal()` / `pumpLocal()` | 串行播放队列（GPU 只能串行，必须一句播完再请求下一句） |
| `requestAudio()` / `takeAudio()` | 请求 wav，并对**下一句做预取**，把合成时间藏进上一句的播放时间里 |
| `playBlobUrl()` | `Audio` 播放，播完回收 object URL |
| `stopLocal()` | 清空队列 + `AbortController.abort()` 在途请求 + 停当前音频 |
| `refreshLocalStatus()` | 拉 `/api/tts/status` + `/voices`，供设置页显示"准备中/可用/失败" |

关键设计：

- **`stop()` 和 `speechCancelSilent()` 都会调 `stopLocal()`**，用户点停止或开新轮次时不会出现"后台还在生成、前台已经停了"
- **预取只提前一句**，避免一次性把整段话全部塞给 GPU 排队
- 本地引擎失败时**只跳过该句**并 `console.warn`，不会让整段朗读中断
- `ttsState.gsvVoice` 对应配置项 `voice.gsvVoice`，切换音色走 `POST /api/tts/voice`（毫秒级，不重载模型）

`Settings.vue` 已把 `local` 选项放开（原来写着 `disabled` + "Phase 2 敬请期待"）。

---

## 4. 运行时与打包

### 4.1 不要用 GPT-SoVITS 仓库自带的 `runtime\`

那个是 **Python 3.9.13**，而现代 agent 框架通常要 3.10+。

推荐：**自己建环境，把 GPT-SoVITS 作为 vendor 目录塞进来**。

| 组件 | 要求 |
|---|---|
| Python | **3.11**（官方测试矩阵支持 3.10/3.11/3.12） |
| PyTorch | **2.8.0+cu128**（或 2.7.0+cu128）——必须 cu128，才含 `sm_120` |
| 依赖 | 按仓库 `requirements.txt`；不需要日文就砍掉 `pyopenjtalk`（难编译） |

`check_runtime()` 会主动检查 `sm_120` 是否在 `torch.cuda.get_arch_list()` 里，不满足直接抛带人话的错，而不是等到跑起来才崩。

> **坑：仓库自带的 runtime 是 embedded 版 Python**，有 `runtime\python39._pth`，
> 它会**忽略 `PYTHONPATH`**，所以 `python -m tts.xxx` 会报 `No module named 'tts'`。
> 两种解法：直接用文件路径跑（`python 项目\python\tts\gpt_sovits_engine.py --selftest`），
> 或者把 `python39._pth` 改成绝对路径 + 追加一行项目 `python\` 目录。
> 用自己建的 3.11 环境就没有这个问题。

### 4.2 依赖安装（两步）

依赖清单在 [`python/tts/requirements-tts.txt`](../python/tts/requirements-tts.txt)，是官方 `requirements.txt` 去掉训练 / WebUI / ASR / 导出后的推理精简集。

```bash
# 第一步：PyTorch 必须从 cu128 源装，PyPI 上是 CPU 版
pip install --index-url https://download.pytorch.org/whl/cu128 torch torchaudio

# 自检：必须能在 arch list 里看到 sm_120
python -c "import torch;print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_arch_list())"

# 第二步：其余依赖
pip install -r python/tts/requirements-tts.txt
```

几个容易卡住的地方：

| 问题 | 处理 |
|---|---|
| `opencc` 编译失败（Windows 需要 MSVC） | 换成 `pip install opencc-python-reimplemented`，模块名同样是 `opencc` |
| `pyopenjtalk` 装不上 | 不需要日文就整段删掉；需要的话先装 cmake + VS Build Tools |
| 缺 `matplotlib` / 其它包报 ImportError | 报什么装什么；权威清单仍是仓库根的 `requirements.txt` |
| `onnxruntime-gpu` 与 `onnxruntime` 冲突 | 只装一个，Windows + x86_64 用 `-gpu` 版 |
| 装完跑起来会卡死（不报错） | 文本前端缺本地资源，会触发联网下载 | 见 §8.1 |

`check_runtime()` 会主动检查 `sm_120` 是否在 `torch.cuda.get_arch_list()` 里，不满足直接抛带人话的错，而不是等到跑起来才崩。

> **坑：仓库自带的 runtime 是 embedded 版 Python**，有 `runtime\python39._pth`，
> 它会**忽略 `PYTHONPATH`**，所以 `python -m tts.xxx` 会报 `No module named 'tts'`。
> 两种解法：直接用文件路径跑（`python 项目\python\tts\gpt_sovits_engine.py --selftest`），
> 或者把 `python39._pth` 改成绝对路径 + 追加一行项目 `python\` 目录。
> 用自己建的 3.11 环境就没有这个问题。

### 4.3 目录布局与路径规则

**代码和权重是两个独立目录，都由 `config.json` 决定，不做任何目录探测。**

| 配置项 | 含义 | 留空时的默认值 |
|---|---|---|
| `voice.vendorDir` | GPT-SoVITS **代码**目录 | `<项目根>/vendor/gpt-sovits` |
| `voice.modelsDir` | **权重 + 参考音频**目录 | `<userData>/models/gpt-sovits` |

优先级：**`config.json` > 环境变量（`GSV_VENDOR_DIR` / `GSV_MODELS_DIR`，仅供调试）> 默认值**。

> 以前有一条“扫描同级 `GPT-SoVITS-v*` 目录”的兜底逻辑，**已删除**——
> 代码随仓库分发，路径必须可预期，不能让程序去猜安装在哪。

`voices.json` 里同样不允许写本机绝对路径，音色权重和参考音频都写作相对 `modelsDir` 的相对路径。

布局：

```
sassy-cat/
├── python/tts/                    # 适配层 + 音色表 + 下载器 + 依赖
├── vendor/gpt-sovits/             # 代码（进 git，约 60 MB）
│   ├── GPT_SoVITS/                # 含 text/、AR/、module/、TTS_infer_pack/
│   └── tools/                     # 只保留 i18n / audio_sr / my_utils / AP_BWE 代码
└── <userData>/models/gpt-sovits/  # 权重（不进 git，按需下载）
    ├── GPT_SoVITS/pretrained_models/   # hubert / bert / sv / G2PW 之外的底座
    ├── GPT_weights_v2ProPlus/
    ├── SoVITS_weights_v2ProPlus/
    └── 参考音频/
```

### 4.3.1 代码目录里必须带什么

`vendor/gpt-sovits/` 需要 `GPT_SoVITS/` 全部源码，外加 `tools/` 的一个子集
（`TTS.py` 会 `from tools.audio_sr import AP_BWE` 和 `from tools.i18n.i18n import ...`）：

| 保留 | 说明 |
|---|---|
| `tools/__init__.py`、`tools/assets.py`、`tools/audio_sr.py`、`tools/my_utils.py` | 运行时被 import |
| `tools/i18n/` | 多语言 |
| `tools/AP_BWE_main/{datasets1,models}` | `audio_sr.py` 的依赖（代码，约 0.1 MB） |

| 剔除 | 原因 |
|---|---|
| `tools/asr/`（1.1 GB）、`tools/uvr5/`（718 MB）、`tools/denoise-model/` | 做数据集用，推理不需要 |
| `tools/AP_BWE_main/24kto48k/`（113 MB） | v3/v4 超分权重，按需再下 |
| `GPT_SoVITS/pretrained_models/` | 属于 modelsDir |
| `GPT_SoVITS/text/G2PWModel/`、`G2PWModel_1.1.zip`（83 MB） | 由下载器解压到 **modelsDir**（不在代码目录） |
| `__pycache__/` | 构建产物 |

实测 `vendor/gpt-sovits/` 总计 **669.0 MB**，其中 `G2PWModel`（607.9 MB，走下载、已 gitignore）
不算数，**真正进 git 的代码是 61.1 MB**：

| 部分 | 大小 | 说明 |
|---|---|---|
| `GPT_SoVITS/` 代码 + 英文词典 | ~24 MB | 必需 |
| `text/ja_userdic/` | 36.7 MB | **只做中文可以删**，删掉后仓库降到 24.4 MB（同时 `atri` 日文音色不可用） |

### 4.3.1.1 已剔除的训练 / 工具代码

裁剪依据不是“看名字”，而是**实跑一次推理，统计 `sys.modules` 里真正落在 vendor 下的文件**
（共 83 个），其余全部删除：

| 剔除 | 说明 |
|---|---|
| `s1_train.py`、`s2_train.py`、`s2_train_v3.py`、`s2_train_v3_lora.py` | 训练 |
| `prepare_datasets/`（1/2/3-get-*.py） | 数据集格式化 |
| `inference_webui.py`、`inference_webui_fast.py`、`inference_gui.py`、`inference_cli.py` | 图形界面 / CLI 入口 |
| `export_torch_script*.py`、`onnx_export.py` | 模型导出 |
| `stream_v2pro.py`、`download.py`、`configs/` | 各自独立的工具 / 训练配置 |
| `tools/i18n/scan_i18n.py`、`locale_diff.py` | 开发期扫描/对比工具，运行时不用 |
| `tools/i18n/locale/` 里除 `en_US.json`、`zh_CN.json` 外的 11 个语言包 | `TTS.py` 只在**日志文案**上用 i18n，其余语言永远用不到 |

保留的根目录文件只有三个：`sv.py`（说话人验证）、`process_ckpt.py`（版本识别）、`utils.py`。

关于 i18n：`TTS.py` 第 34 行确实 import 了 `tools.i18n.i18n`，所以**文件本身不能删**，
但它只用于 `print` / 异常文案，不参与任何逻辑或配置键。`I18nAuto` 找不到对应语言时会回退
`en_US.json`，所以只留 `en_US.json`（+ 想中文日志就留 `zh_CN.json`）即可，
`tools/i18n/` 从 290 KB 降到 40 KB。

> 删除后重新跑了一次完整推理验证：**正常出声**（311 KB wav，23.9 s 含加载预热）。
> 以后上游升级快照，照这张表再删一遍即可——判据就是“`sys.modules` 里有没有它”。

### 4.3.2 上游写死的路径，由适配层修正

上游有两处不读配置，直接把权重钉在**代码目录**下。我们拆目录后必须改指，否则会报
`ModuleNotFoundError` / `FileNotFoundError` / `HFValidationError`：

| 位置 | 上游写法 | 适配层处理 |
|---|---|---|
| 顶层模块名 `utils` | 权重里 pickle 存的是 `utils.HParams`（`GPT_SoVITS/utils.py`），而 sassy-cat 也有 `python/utils.py` | `_merge_conflicting_utils()` 把 GPT 的 utils 提升为 `sys.modules["utils"]` 并合并应用侧符号 |
| `GPT_SoVITS/sv.py` | `sv_path = "GPT_SoVITS/pretrained_models/sv/..."`（相对 cwd） | `_patch_hardcoded_paths()` 改模块变量 |
| `GPT_SoVITS/text/LangSegmenter/langsegmenter.py` | 用 `__file__` 反推到代码目录 | 覆盖 `fast_langdetect.infer._default_detector` 的 `cache_dir` |
| `GPT_SoVITS/text/chinese2.py` | `G2PWPinyin(model_dir="GPT_SoVITS/text/G2PWModel")`（相对 cwd） | `_patch_g2pw_model_dir()` 把相对路径重定向到 `models_dir` |
| `GPT_SoVITS/text/chinese2.py` | `os.environ.get("bert_path", "GPT_SoVITS/...")` 默认相对路径 | 加载时写死 `os.environ["bert_path"]` / `["cnhubert_base_path"]` 为绝对路径 |
| 中文前端（G2PW） | 相对 cwd 找模型 | 同上，且 `say_stream()` 推理期间同样持有 cwd |

> 都**没有改上游源码**，全部是运行时 patch 或环境变量。以后上游新增硬编码路径，
> 统一加在 `_patch_hardcoded_paths()` 里。
>
> **G2PW 为什么必须落在 `modelsDir`**：装到 `Program Files` 时安装目录不可写，
> 而 g2pw 在模型缺失时会尝试**下载并解压**。把它挪到用户可写的数据目录后，
> 代码目录全程只读，安装位置不再受限。
> 实测：`download_and_decompress('GPT_SoVITS/text/G2PWModel')` 被重定向到
> `<modelsDir>/GPT_SoVITS/text/G2PWModel`，`g2pW.onnx` 存在。

### 4.4 换一台机器 / 新同事接入：五步

```bash
# 1. 拿代码（GPT-SoVITS 放成兄弟目录，或 vendor/gpt-sovits）
git clone <sassy-cat>
git clone <GPT-SoVITS 仓库>

# 2. 建环境（Python 3.11）
python -m venv .venv && .venv\Scripts\activate
pip install --index-url https://download.pytorch.org/whl/cu128 torch torchaudio
pip install -r python/tts/requirements-tts.txt

# 3. 拉音色（约 1.33 GB，自动校验 sha256）
python python/tts/fetch_voices.py

# 4. 自检
python python/tts/gpt_sovits_engine.py --selftest

# 5. 跑通就接入启动流程
```

第 3 步必须能用。如果某些文件下不下来（网络/代理），至少保证 `voices.json` 里 `default_voice` 对应的那套齐全，否则启动会失败。

---

## 5. 音色：下载地址与授权

清单权威来源是 [`python/tts/voices.json`](../python/tts/voices.json) 的 `sources` 段（含每文件的 size + sha256）。用脚本拉取：

```bash
python python/tts/fetch_voices.py --list                      # 看清单和直链
python python/tts/fetch_voices.py                            # 全量下载（已存在且校验通过会自动跳过）
python python/tts/fetch_voices.py --proxy http://localhost:11081   # 走代理
python python/tts/fetch_voices.py --endpoint https://hf-mirror.com  # 走镜像
python python/tts/fetch_voices.py --verify                   # 只校验
python python/tts/fetch_voices.py --only tangyuge-v2pp       # 只下某一套
```

### 5.1 五个来源

| source id | 音色 | 版本 | 下载地址 | 授权 | 商用 |
|---|---|---|---|---|---|
| `tangyuge-v2pp` | 唐雨格（6 种情绪） | v2ProPlus | [shiqianyan/TangYuGe-GPT-SoVITS-v2ProPlus](https://huggingface.co/shiqianyan/TangYuGe-GPT-SoVITS-v2ProPlus) | Apache-2.0 | ✅ |
| `narrator-v2pro` | 纪录片解说（合成音色） | v2Pro | [AxcLogo/GPT-SoVITS-v2Pro-zh-Documentary-Narrator](https://huggingface.co/AxcLogo/GPT-SoVITS-v2Pro-zh-Documentary-Narrator) | Apache-2.0 | ✅ |
| `bufeiyan-v2pro` | 步非烟（真人女声） | v2Pro | [AetherAllan/bufeiyan-gpt-sovits-v2pro](https://huggingface.co/AetherAllan/bufeiyan-gpt-sovits-v2pro) | other | ❌ |
| `zundamon-v2` | ずんだもん | v2 | [zunzunpj/zundamon_GPT-SoVITS](https://huggingface.co/zunzunpj/zundamon_GPT-SoVITS) | 未标注 | ❌ |
| `atri-v1` | 亚托莉 ATRI | v1 | [2DIPW/ATRI_GPT-SoVITS](https://huggingface.co/2DIPW/ATRI_GPT-SoVITS) | CC-BY-NC-SA-4.0 | ❌ |

直链格式（需要自己拼时）：

```
https://huggingface.co/<repo>/resolve/main/<仓库内路径>
```

路径里有中文 / 日文 / 空格时**必须逐段百分号编码**，`fetch_voices.py` 已经处理好了。

合计约 **1.33 GB**。其中只有前两个可以商用，打包发货只能带这两个（或让用户自备）。

### 5.2 音色表结构

`voices.json` 分两段，互不干扰：

- `voices` —— 引擎读，决定「哪对权重 + 哪条参考音频」
- `sources` —— `fetch_voices.py` 读，决定「从哪下、怎么校验、授权是什么」

同一对权重可以注册成多个音色（唐雨格就是 6 个条目共用一套权重，只换参考音频）。切换是毫秒级的，不重载模型。

### 5.3 注意事项

- **版本由文件头自动识别**（`detect_sovits_version()`），换音色不需要改代码。`05`=v2Pro、`06`=v2ProPlus；旧的 `PK` 头按体积判定 v1/v2。
- **v2Pro 与 v2ProPlus 共用同一个 GPT 底模 `s1v3.ckpt`**，GPT 侧区分不出来，区分依据在 SoVITS 头字节。两者**不能混搭**。
- `atri` 是 **v1**，能跑但相似度和稳定性弱于 v2ProPlus，也不支持粤语/韩语。
- `zundamon` **缺参考音频**（上游只给权重），需要自备 3~10 秒干声填进 `ref_audio`。
- **所有条目的 `prompt_text` 目前都是空**（无参考文本模式）。填上参考音频的逐字文本可以明显提升相似度，这一步需要人工转录。

---

## 6. 性能实测（RTX 5060 Ti 16G，v2ProPlus）

| 指标 | 数值 |
|---|---|
| 模型加载 | 16.8 s |
| 首次合成（一次性） | 19.2 s |
| 稳态 RTF | 0.23 ~ 0.29（5.7 s 语音约 1.3 s，6.4 s 语音约 1.8 s） |
| 常驻显存 | 1.24 GB |
| 输出 | 32000 Hz 单声道 int16 |

RTF 比官方标称的 0.028 高，原因是 `batch_size=1` + `cut5` 分片 + 文本前端开销。对 agent 场景已经远快于实时，够用。

**延迟预算**：单句体感延迟 ≈ 0.3~1.5 s（`say_stream` 更短），主要瓶颈通常不在 TTS，而在“等 LLM 出第一句”。建议做「LLM 流式输出 → 按句切 → 立刻合成」的流水线，而不是等整段回答生成完。

> 没有独显的用户走 CPU 模式，数据见 [§7](#7-cpu-推理没有独显时的兜底)。

---

## 7. CPU 推理（没有独显时的兜底）

**可以跑**，实测通过。同一台机器、同一个 v2ProPlus 模型：

| 指标 | CPU（Intel，6 线程） | GPU（5060 Ti） |
|---|---|---|
| 模型加载 | 4.8 s | 16.8 s |
| 首次合成（一次性开销） | 10.7 s / 产出 2.66 s 音频 | 19.2 s |
| 稳态 RTF | **≈ 0.98**（2.86 s 音频用 2.81 s） | 0.23 ~ 0.29 |
| 占用 | 内存 + CPU 线程，不占显存 | 1.24 GB 显存 |

**结论：能用，但只是「刚好赶上实时」。** 生成 10 秒语音大约要 10 秒，做后台预生成 / 批量导出没问题，做实时对话会明显卡顿。比 GPU 慢约 3~4 倍。

### 7.1 三个必须注意的点

1. **`is_half` 必须为 `False`**。CPU 不支持 fp16，传 `True` 会报错或算出错误结果。引擎里已经强制：

   ```python
   if device == "cpu":
       is_half = False
   ```

   而且 `check_runtime()` 检测不到 CUDA 时会打警告并自动回落，不会崩。

2. **CPU 会和 agent 其它部分抢资源**。Electron 界面、LLM 流式接收都在用 CPU，TTS 开满线程会互相拖慢。引擎已自动把线程数设为 `CPU 核数 - 1`，需要调整时设环境变量 `GSV_CPU_THREADS`。

3. **文本前端的开销在 CPU 上占比更大**。G2PW 多音字消歧本身就是 CPU 上的 onnx 推理（GPU 模式也一样跑 CPU），所以不是纯粹的「换 CPU 只线性变慢」。

### 7.2 用法：默认就是自动兜底

引擎的 `device` 参数默认是 **`"auto"`**：

| 传入 | 行为 |
|---|---|
| `"auto"`（默认） | 有 CUDA → `cuda`；没有 → `cpu` |
| `"cuda"` | 有 CUDA 用之；**没有则自动回落 `cpu`**，只打一条 warning，不抛异常 |
| `"cpu"` | 强制 CPU |

```python
engine = get_engine()               # 什么都不用传：有卡用卡，没卡用 CPU
engine = get_engine(device="cpu")   # 强制 CPU（压测 / 用户手动选择）
```

所以上层**不需要先判断有没有显卡**，直接调用即可；失败只可能是
权重缺失、依赖不全这类真问题，而不是"没显卡"。

CPU 模式下的自动调优：

| 项 | 行为 |
|---|---|
| `is_half` | 强制 `False`（CPU 不支持 fp16） |
| 线程数 | 默认 `CPU 核数 - 1`（给 UI 留一个核），可用环境变量 `GSV_CPU_THREADS=6` 覆盖 |
| 状态上报 | `/api/tts/status` 返回 `device` / `isCpu` / `cpuThreads`，前端可据此提示"当前用 CPU、会慢一些" |

**实测（模拟无 CUDA）**：

```
cuda_available = False
engine.device  = cpu
is_half        = False
cpu_threads    = 6
sample_rate    = 32000
audio_sec      = 3.40，wall = 6.50，RTF = 1.91（首次调用，含预热开销）
```

`voices.json` 不需要动，权重和参考音频完全通用。

### 7.3 如果确定要主推 CPU

| 手段 | 说明 |
|---|---|
| 换小模型 | `v2` 的 SoVITS 只有 81 MB，`v2ProPlus` 是 164 MB，明显更轻 |
| 走 ONNX | 仓库自带 `GPT_SoVITS/onnx_export.py`，支持 v1/v2、opset 16/17，导成 ONNX 后用 `onnxruntime` 跑 CPU，通常比原生 PyTorch CPU 快一截 |
| int8 量化 | **仓库没有现成脚本**，需要自己用 onnxruntime 的 quantization 工具做，属于额外工程量 |
| 分句更碎 | 用 `say_stream` + 更细的 `text_split_method`，让第一句更快出来 |

### 7.4 产品建议

**GPU 为主、CPU 兜底。** 检测不到可用 CUDA 时自动切 CPU，并降低预期——比如只在「朗读长文 / 导出音频」这类非实时场景开放语音，实时对话里关掉或提示用户。

这条降级路径在代码里已经留好：`check_runtime()` → `TTSEngine(device="cpu")` → 失败则 `TTSUnavailable` → 上层退化成纯文字。

---

## 8. 故障排查

| 报错 | 原因 | 处理 |
|---|---|---|
| `ModuleNotFoundError: No module named 'ERes2NetV2'` | cwd 不对 | 确保走 `TTSEngine.load()`（它内部会切 cwd），不要自己 `import TTS_infer_pack` |
| `AttributeError: Can't get attribute 'HParams' on <module 'utils' from 'python\\utils.py'>` | **顶层模块名撞车**：应用和 GPT-SoVITS 各有一个 `utils.py`，pickle 解析 `utils.HParams` 时命中了应用那份 | 引擎已在 `load()` 里调 `_merge_conflicting_utils()` 自动处理；单独跑脚本时同样生效 |
| `TypeError: Cannot read properties of undefined (reading 'handle')` at `main.js` 的 `ipcMain.handle` | 从 Electron 宿主（例如 DSH、VS Code 终端）里启动 `electron .` 时，环境里带着 `ELECTRON_RUN_AS_NODE=1`，electron.exe 会退化成纯 Node，`require('electron')` 只返回可执行文件路径 | 启动前 `Remove-Item Env:ELECTRON_RUN_AS_NODE`。这不是代码问题，`electron --version` 能看出来：正常应打印 `v28.x`，被劫持时会打印 Node 版本 |
| `FileNotFoundError: ...G2PWModel_1.1.zip` | 文本前端没预热就切走了 cwd | 保留 `_prewarm_text_frontends()` 调用 |
| `torch.cuda.OutOfMemoryError` | 显存被 agent 其它部分占满 | 降级纯文字；或先 `engine.close()` 再重启；设置里让用户关掉语音 |
| `RuntimeError: CUDA error: no kernel image is available` | torch 不含 `sm_120` | 换 cu128 的 torch |
| 首次合成卡 20 秒 | 预热被跳过 | `warmup=True` 并在启动阶段调用 |
| 声音像别人 / 不像 | 参考音频质量差或 `prompt_text` 没填 | 换更干净的 3~10 s 干声；填逐字文本 |
| 偶尔电音 / 破音 | v3 采样步数低 | `sample_steps` 提到 32（v3 才有） |
| 中文读错多音字 | 前端规范化 | 换 `text_split_method`；或在文本里改写 |
| 加载时卡死、CPU 不涨、内存停在 2 GB 左右 | 文本前端首次使用时联网下载资源 | 见 §8.1，三个陷阱 |
| `ImportError: TorchCodec is required for load_with_torchcodec` | torchaudio ≥ 2.9 的 `load()` 改成了 TorchCodec 实现 | 见 §8.1 第 4 条，引擎已内置 soundfile 兜底 |

### 8.1 装完依赖后仍然卡住？先查这四处

这四条都是我在 `.venv` 里真机踩出来的：**它们不会报错，只会静默挂住**，因为触发的是"首次使用时联网下载"。

**① pyopenjtalk 0.4.x 不内置词典（102 MB）**

第一次做日文文本处理时会去 GitHub 拉 `open_jtalk_dic_utf_8-1.11.tar.gz`，离线/代理受限时**阻塞不报错**。

```powershell
# 从 GPT-SoVITS 自带 runtime 里复制（它内置了）
Copy-Item <GPT-SoVITS>\runtime\Lib\site-packages\pyopenjtalk\open_jtalk_dic_utf_8-1.11 `
          <venv>\Lib\site-packages\pyopenjtalk\ -Recurse
# 或者设置环境变量
$env:OPEN_JTALK_DICT_DIR = "<某处>\open_jtalk_dic_utf_8-1.11"
```

引擎已加防护：`_open_jtalk_dict_available()` 检测不到词典就跳过日文预热并告警。

**② nltk 数据缺失（`averaged_perceptron_tagger` / `cmudict`）**

`g2p_en`（英文前端）依赖它们，缺失时 nltk 会自动下载。注意新旧 nltk 的标注器名字不同（`_eng` 后缀），两个都得有。

```powershell
# GPT-SoVITS 的 runtime 里带了老名字的资源，复制进用户缓存
robocopy <GPT-SoVITS>\runtime\nltk_data $env:APPDATA\nltk_data /E
```

引擎已加防护：`_nltk_en_available()` 检测不到就跳过英文预热并告警。

**③ 打包时必须把这两份资源一起带上**

否则用户机器上第一次朗读日文/英文就会卡死——而且是在你自己机器上测不出来的那种。

**④ `torchaudio.load` 需要 torchcodec（torchaudio ≥ 2.9）**

GPT-SoVITS 只在 `TTS.py:773` 用一次 `torchaudio.load(参考音频)`。两个选择：

| 方案 | 说明 |
|---|---|
| 装 torchcodec | `pip install torchcodec`，但 Windows 上还要额外的 FFmpeg 动态库，脆 |
| **引擎已内置的兜底** | `_patch_torchaudio_load()` 在检测不到 torchcodec 时，用 soundfile 实现同名函数（参考音频都是 wav，完全够用） |

实测：打了补丁后 RTF 0.32，与原生一致。

---

## 9. 降级策略（务必实现）

```python
try:
    sr, audio = engine.say(text)
except TTSUnavailable as e:
    log.warning("TTS 失败，降级: %s", e)
    ui.show_text_only(text)          # 退化成纯文字，不要卡住整个对话
```

另外建议：

- 启动时做一次 `check_runtime()`，失败就**隐藏语音开关**，而不是让用户点了报错；
- 连续 3 次推理失败 → 自动禁用 TTS 并提示重启；
- 用户可用“插话”打断播放：取消上层任务 + 清空播放队列。

---

## 10. 合规提醒

- 音色模型的授权各不相同：该批音色中 `atri`（《ATRI》角色）、`bufeiyan`（真人声音）**禁止商用/禁止二次分发**，二次元角色还有版权问题。
- 商业分发前必须逐个确认 license，**不要把二次元或真人音色打进安装包**。
- 建议预留「用户自备音色」入口：放 `voices.json` 就能加，不依赖代码。

---

## 11. 打包与分发

### 11.1 三方分工：谁需要 GPT-SoVITS

GPT-SoVITS **不是**一个要"安装"的软件——它没有安装程序、不写注册表、不装服务，就是一堆文件夹（Python 源码 + 模型权重）。"安装"只是把文件夹放到某个目录再 import。

| 角色 | 需要 GPT-SoVITS 吗 | 从哪来 |
|---|---|---|
| **开发者（本机）** | 需要，但已经有了 | 同级目录的 `GPT-SoVITS-v*/`，引擎自动探测 |
| **打包时** | 需要复制一份进项目 | `sassy-cat/vendor/gpt-sovits/`，跟客户端一起打包 |
| **终端用户** | **完全不需要** | 只下载安装包，里面已经包含着 |

用户永远不知道自己电脑里有 GPT-SoVITS，就像用户不知道 Electron 客户端里有 Chromium。

### 11.2 用户端到底需要什么

| 依赖 | 用户要装吗 | 说明 |
|---|---|---|
| Python | ❌ | 随包分发 venv 或冻结 |
| CUDA Toolkit | ❌ | PyTorch 的 cu128 wheel 自带 CUDA 运行时（cudnn/cublas 都在 wheel 里） |
| **NVIDIA 显卡驱动** | ✅ | 唯一需要的前置条件 |
| GPT-SoVITS | ❌ | 在 `vendor/` 里 |

### 11.3 打包清单（按实测体积）

> **重要：模型权重不进 git 仓库。**
> 仓库里只放代码（`GPT_SoVITS/` 的 .py，约 10 MB）+ `voices.json` 清单 + 下载脚本。
> 权重在用户于设置页开启「本地 GPT-SoVITS」时**按需下载**，落在用户数据目录，
> 不进仓库、不进安装包。`.gitignore` 已按目录 + 扩展名双重排除（实测 6 类路径全部 IGNORED）。
>
> 这样做的代价是首次开启要下约 2 GB；好处是仓库不被几 GB 二进制污染、安装包瘦身、
> 换音色不用重新发版。

### 11.3.1 按需下载的实现

| 文件 | 作用 |
|---|---|
| `python/tts/voices.json` 的 `base_models` 段 | 基础模型清单（仓库、远端路径、字节数、是否解压） |
| `python/tts/voices.json` 的 `sources` 段 | 音色权重清单（含 sha256） |
| `python/tts/downloader.py` | 下载器：进度上报、取消、跳过已校验文件、zip 解压 |
| `python/server/tts_api.py` | `POST /download/start`、`GET /download/status`、`POST /download/cancel` |
| `src/api/tts.js` + `Settings.vue` | 设置页的「下载模型」按钮 + 进度条 |

### 11.3.1.0 依赖安装怎么接进启动流程

应用的启动流程（`electron/python-env-checker.js` → `checkAndSetup()`）只做三件事：
建 venv → 检查 `requirements.txt` → 缺就 `pip install -r requirements.txt`。
**它不会去读 `requirements-tts.txt`。**

TTS 依赖**故意不并进 `requirements.txt`**，原因有三：

1. 体积：多装 ~300 MB，而大部分用户可能从不开启本地语音
2. **版本冲突**：`numpy<2.0` / `transformers<=4.50` 会降级已装好的环境，
   而基础依赖里的 `sentence-transformers==6.0.1` 声明需要 `transformers>=5`
3. 降级影响面：Chromadb / 嵌入模型都依赖 numpy，全局降级风险大于收益

所以改成**按需安装**，与模型下载同一条路径：

```
用户在设置页点「下载模型」
        │
        ├─ IPC `tts:ensure-deps`  → PythonEnvChecker.ensureOptionalRequirements('python/tts/requirements-tts.txt')
        │      ├─ 已装齐 → 秒返回（实测 1.5 s，39 条全部命中）
        │      └─ 有缺失 → pip install -r（日志走现有日志通道）
        │
        └─ POST /api/tts/download/start → 下载权重
```

为此对 `python-env-checker.js` 做了三处**向后兼容**的改造：

| 改动 | 说明 |
|---|---|
| `checkDependenciesInstalled(file = 'requirements.txt')` | 接受任意 requirements 路径 |
| `installDependencies(file = 'requirements.txt')` | 同上 |
| 新增 `ensureOptionalRequirements(file)` | 检查 + 缺则安装，返回 `{success, installed, message}` |

顺带修了解析器：现在会先去掉 `;` 之后的环境标记再比对包名，
否则 `onnxruntime-gpu ; platform_system == ...` 这类行会被判为「无法解析」。

**安装完必须重启后端**：当前 Python 进程已经 import 了旧版本，pip 装完不会热生效。
设置页会提示「依赖已安装完成，请点右上角「重启」」，`ensureOptionalRequirements`
的返回值里带 `installed: true` 供前端判断。

> 实测：`ensureOptionalRequirements('python/tts/requirements-tts.txt')`
> → `{"success":true,"installed":false,"message":"依赖已就绪"}`，1.5 秒；
> 用一个不存在的包名测试缺失分支 → 正确返回 `false` 并触发安装流程。

**两段清单的分工**

`base_models` 里的三个包：

| id | 内容 | 大小 | 必需 |
|---|---|---|---|
| `base-models` | HuBERT + BERT + SV（`lj1995/GPT-SoVITS`） | 940 MB | ✅ |
| `g2pw` | 中文多音字模型（zip，自动解压） | 562 MB | ✅ |
| `base-voice-v2proplus` | s1v3.ckpt + s2Gv2ProPlus（零样本克隆用） | 339 MB | ⭕ |

音色（`sources`）按需下载，每个包 230~315 MB。

**落盘位置：`models_dir`**

引擎现在区分两个目录：

| 目录 | 内容 | 配置项 | 默认值 |
|---|---|---|---|
| `vendor_dir` | GPT-SoVITS **代码** | `voice.vendorDir` | `<项目根>/vendor/gpt-sovits` |
| `models_dir` | **权重 + 参考音频** | `voice.modelsDir` | `<userData>/models/gpt-sovits` |

优先级：**`config.json` > 环境变量（`GSV_VENDOR_DIR` / `GSV_MODELS_DIR`，仅调试）> 默认值**。

例外：**G2PWModel 现在也落在 `models_dir`**（`<modelsDir>/GPT_SoVITS/text/G2PWModel`）。
它原来是放代码目录的，但那样装到 `Program Files` 就不可写了（g2pw 缺模型时会尝试下载解压）。
改由 `_patch_g2pw_model_dir()` 把上游写死的相对路径重定向过去，代码目录因此**全程只读**。

**实测（vendor 用仓库副本、models 用另一个目录）**：

```
vendor = F:\workspaces\sassy-cat\vendor\gpt-sovits
models = F:\workspaces\GPT-SoVITS-v2pro-20250604-nvidia50
engine = local，voice = tangyuge_apology（来自 config.json 的 voice.gsvVoice）
合成 275,244 字节（约 4.3 s，32 kHz）
```

**实测**：清单展开 32 个文件 / 3.06 GB；`missing_required()` 在本机返回 0；
`POST /download/start` 触发后状态机 `idle → running → done`，已存在文件被正确跳过，
percent 到 100。

只有 v2ProPlus 单音色 + 中文时的**必带项**：

| 内容 | 大小 |
|---|---|
| `GPT_SoVITS/` 代码（AR / module / TTS_infer_pack / text 等，不含权重） | ~10 MB |
| `pretrained_models/chinese-hubert-base` | 180 MB |
| `pretrained_models/chinese-roberta-wwm-ext-large` | 621 MB |
| `pretrained_models/fast_langdetect` | 125 MB |
| `pretrained_models/sv`（v2Pro 系列要用的 SV 模型） | 103 MB |
| `text/G2PWModel`（中文多音字消歧） | 608 MB |
| 音色权重（一对 ckpt + pth） | 314 MB |
| 参考音频 | 1 MB |
| **小计** | **≈ 1.96 GB** |

建议额外带上（让用户能"不训练直接推底模"）：

| 内容 | 大小 |
|---|---|
| `pretrained_models/v2Pro/`（s2Gv2ProPlus + s2Gv2Pro + 判别器） | 587 MB |
| `pretrained_models/s1v3.ckpt`（GPT 底模） | 148 MB |

**可以整块删掉（约 4.8 GB）**：

| 内容 | 大小 | 原因 |
|---|---|---|
| `pretrained_models/gsv-v4-pretrained/` | 789 MB | 只有 v4 用 |
| `pretrained_models/s2Gv3.pth` | 733 MB | 只有 v3 用 |
| `pretrained_models/gsv-v2final-pretrained/` | 338 MB | 只有 v2 用 |
| `pretrained_models/models--nvidia--bigvgan_v2_24khz_100band_256x/` | 215 MB | 只有 v3/v4 声码器用 |
| `s1bert25hz-*.ckpt` / `s2D488k.pth` / `s2G488k.pth` | 338 MB | 只有 v1 用 |
| `text/ja_userdic/` | 37 MB | 不做日文就删（同时别装 pyopenjtalk） |
| `tools/`（UVR5 分离 / ASR 标注 / BWE 超分） | **1966 MB** | 那是做数据集用的，客户端推理不需要 |
| `runtime/`（仓库自带的 Python 3.9） | **7447 MB** | 用自己的 venv，不重复带 |

**安装包体积估算**

| 部分 | 大小 |
|---|---|
| GPT-SoVITS 必需 + 底模 | ~2.7 GB |
| Python 环境（torch cu128 + 依赖，装好后） | ~4~6 GB |
| 客户端本体（Electron + node_modules） | ~200~400 MB |
| **合计** | **≈ 7~9 GB**，压缩后约 4~5 GB |

体积压不下去，TTS 模型的本质就是几百 MB 到几 GB 的权重。可以做的是：首装时只带一个音色，其余音色改成"按需下载"（`fetch_voices.py` 已经支持 `--only`）。

### 11.4 打包流程

```powershell
# 1. 建 vendor 目录
New-Item -ItemType Directory -Force sassy-cat\vendor\gpt-sovits

# 2. 复制代码（不含 weights 之外的大目录）
robocopy <GPT-SoVITS> sassy-cat\vendor\gpt-sovits GPT_SoVITS /E ^
    /XD pretrained_models\gsv-v4-pretrained pretrained_models\gsv-v2final-pretrained ^
        pretrained_models\models--nvidia--bigvgan_v2_24khz_100band_256x ^
        text\ja_userdic __pycache__

# 3. 拉音色（会按 voices.json 里的相对路径落盘，并校验 sha256）
python sassy-cat\python\tts\fetch_voices.py --vendor sassy-cat\vendor\gpt-sovits

# 4. 自检：此时应走 vendor 目录而不是开发机上的仓库
$env:GSV_VENDOR_DIR="sassy-cat\vendor\gpt-sovits"
python sassy-cat\python\tts\gpt_sovits_engine.py --selftest
```

第 2 步的 `robocopy` 只是示例，实际以 11.3 的清单为准——**删掉的东西比留下的多**。

### 11.5 版本策略

- 快照一旦 vendor 进去就**冻结**，不跟上游更新。上游出 v5 也不动。
- 换音色不需要动代码（版本由 `.pth` 文件头自动识别）。
- 只有跨大版本（v2ProPlus → v3/v4/v5）才需要改代码，且改动集中在 `gpt_sovits_engine.py` 一个文件。
- 在 `vendor/gpt-sovits/VERSION.txt` 里记下快照来源（仓库 tag / 打包日期），方便追溯。

---

## 12. 后续适配 TODO

- [ ] 决定打包布局：把 GPT-SoVITS 放进 `vendor/gpt-sovits/`，`voices.json` 的 `vendor_dir` 保持 `null` 即可
- [ ] 用 Python 3.11 + torch cu128 建独立环境，装 `python/tts/requirements-tts.txt`
- [ ] 跑 `python python/tts/fetch_voices.py` 拉齐音色并校验
- [ ] 跑 `--selftest` 确认能出声
- [ ] 人工转录各参考音频的 `prompt_text` 并填入 `voices.json`
- [ ] 给 `zundamon` 补一段 3~10 s 干声
- [ ] 启动流程接入预加载（后台线程），完成前 UI 显示“正在准备语音”
- [ ] 实现降级与开关
- [ ] 决定是否启用 CPU 兜底（见 §7），以及无独显用户的预期管理
- [ ] 确认商用音色授权，剔除不可分发的条目
- [ ] 视需要接入流式播放（`say_stream`）