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

`check_runtime()` 会主动检查 `sm_120` 是否在 `torch.cuda.get_arch_list()` 里，不满足直接抛带人话的错，而不是等到跑起来才崩。

> **坑：仓库自带的 runtime 是 embedded 版 Python**，有 `runtime\python39._pth`，
> 它会**忽略 `PYTHONPATH`**，所以 `python -m tts.xxx` 会报 `No module named 'tts'`。
> 两种解法：直接用文件路径跑（`python 项目\python\tts\gpt_sovits_engine.py --selftest`），
> 或者把 `python39._pth` 改成绝对路径 + 追加一行项目 `python\` 目录。
> 用自己建的 3.11 环境就没有这个问题。

### 4.3 目录布局与路径规则

**`voices.json` 里不允许出现本机绝对路径**，所有路径都相对 `vendor_dir`。`vendor_dir` 默认是 `null`，由程序自动探测：

| 优先级 | 来源 |
|---|---|
| 1 | 环境变量 `GSV_VENDOR_DIR` |
| 2 | `<项目根>/vendor/gpt-sovits/`（打包后的位置） |
| 3 | `<项目根>/../GPT-SoVITS-v*/`（开发机上的同级仓库） |
| 4 | `voices.json` 里显式写的 `vendor_dir`（一般留 `null`） |

打包布局：

```
sassy-cat/
├── python/tts/                 # 本包（适配层 + 音色表 + 下载器 + 依赖）
├── vendor/gpt-sovits/          # 打包时把 GPT-SoVITS 放这里
│   ├── GPT_SoVITS/             # 代码 + pretrained_models
│   ├── GPT_weights_v2ProPlus/  # 音色权重（fetch_voices.py 生成）
│   ├── SoVITS_weights_v2ProPlus/
│   └── 参考音频/
└── ...
```

开发机不需要改目录：只要 GPT-SoVITS 仓库和 `sassy-cat` 在同一层，引擎自己就能找到。

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

2. **CPU 会和 agent 其它部分抢资源**。Electron 界面、LLM 流式接收都在用 CPU，TTS 开满线程会互相拖慢。建议：

   ```python
   import torch
   torch.set_num_threads(max(1, (os.cpu_count() or 4) - 1))   # 留一个核给 UI
   ```

3. **文本前端的开销在 CPU 上占比更大**。G2PW 多音字消歧本身就是 CPU 上的 onnx 推理（GPU 模式也一样跑 CPU），所以不是纯粹的「换 CPU 只线性变慢」。

### 7.2 用法

```python
engine = get_engine(device="cpu")          # 其余参数不用改
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
| `FileNotFoundError: ...G2PWModel_1.1.zip` | 文本前端没预热就切走了 cwd | 保留 `_prewarm_text_frontends()` 调用 |
| `torch.cuda.OutOfMemoryError` | 显存被 agent 其它部分占满 | 降级纯文字；或先 `engine.close()` 再重启；设置里让用户关掉语音 |
| `RuntimeError: CUDA error: no kernel image is available` | torch 不含 `sm_120` | 换 cu128 的 torch |
| 首次合成卡 20 秒 | 预热被跳过 | `warmup=True` 并在启动阶段调用 |
| 声音像别人 / 不像 | 参考音频质量差或 `prompt_text` 没填 | 换更干净的 3~10 s 干声；填逐字文本 |
| 偶尔电音 / 破音 | v3 采样步数低 | `sample_steps` 提到 32（v3 才有） |
| 中文读错多音字 | 前端规范化 | 换 `text_split_method`；或在文本里改写 |

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

## 11. 后续适配 TODO

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