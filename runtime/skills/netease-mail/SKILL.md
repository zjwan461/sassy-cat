---
name: netease-mail
description: >
  接入并操作网易系邮箱（@163.com / @126.com / @yeah.net / @188.com / 网易企业邮，也兼容 QQ 邮箱等
  IMAP 服务商）：收发信、列邮件、搜索、读正文、发带附件邮件、标记已读/未读，以及 535 / Unsafe Login 等报错排障。Use
  this skill whenever the user mentions 网易邮箱 / 163邮箱 / 126邮箱 / yeah.net /
  188邮箱 / QQ邮箱, wants to bind an email account to a client or their own
  code, set up IMAP/SMTP or 客户端授权码, read/send/search mails from a script,
  mark emails as read/unread, build email automation, or hits errors like
  "535 Authentication failed"、"SELECT Unsafe Login"、"LOGIN Login
  error"、"=?utf-8?B?"、连接超时。Triggers on:
  邮箱接入、邮件自动化、IMAP、SMTP、POP3、授权码、收邮件、发邮件、标记已读、标记未读、清未读、定时收信、邮件监控、邮件通知、mailbox。
---

# 网易邮箱接入与自动化

一站式处理网易系邮箱的接入与日常操作。**核心踩坑点已经封进脚本，不要自己重写。**

---

## 铁律（违反必然失败）

1. **第三方登录必须用 16 位客户端授权码**，不是登录密码 → 否则 `535 Authentication failed`。
2. **IMAP 登录成功后、`SELECT` 之前必须先发 `ID` 命令** → 否则
   `SELECT Unsafe Login. Please contact kefu@188.com for help`。
   （`imaplib` 默认没把 `ID` 注册在 AUTH 状态，模块加载时必须先执行
   `imaplib.Commands["ID"] = ("AUTH",)`，否则连 `ID` 都发不出去，直接 `KeyError: 'ID'`。）
3. 收信一律用 `UID` 语义（`imap.uid('FETCH', ...)`），不要用会漂移的邮件序号。
4. **改邮箱状态（已读/未读）与发信一样是两段式硬闸门**：必须先 `--dry-run` 预览、
   经用户确认，再带 `--confirm <token>` 执行。没有令牌时脚本直接拒绝，不会写入。

脚本 `scripts/net163_mail.py` 已内置第 1、2 条的修复与第 3、4 条的正确用法，直接用即可。

---

## 服务器参数速查（个人邮箱四后缀通用）

| 用途 | 地址 | 端口 | 加密 |
|---|---|---|---|
| IMAP | `imap.163.com` | 993 | SSL |
| SMTP | `smtp.163.com` | 465 | SSL |
| POP3 | `pop.163.com` | 995 | SSL |

网易企业邮箱用 `imaphz.qiye.163.com` / `smtphz.qiye.163.com`。
QQ 邮箱用 `imap.qq.com` / `smtp.qq.com`（同样需要授权码，同样要发 `ID` 命令）。
完整对照（含不加密端口、客户端配置）见 `references/netease_servers.md`。

---

## 工作流

### 第 0 步：先确认前置条件（缺了直接失败，别跳过）

问用户或自行确认两点：

- 邮箱网页版【设置 → POP3/SMTP/IMAP】里，IMAP/SMTP 服务**是否已开启**（默认关闭）；
- **是否已生成 16 位客户端授权码**（只显示一次，需用户自己复制）。

若用户还没做，直接把 `references/netease_servers.md` 的「二、获取客户端授权码」讲给他，
不要尝试用登录密码硬试。

### 第 1 步：配置凭据

凭据优先级：**命令行参数 > 环境变量 > 配置文件**。

```bash
# 方式 A：写本地配置文件（推荐，之后无需重复传）
python scripts/net163_mail.py config \
  --user you@163.com --auth-code 十六位授权码

# 方式 B：环境变量
export NETEASE_EMAIL=you@163.com
export NETEASE_AUTH_CODE=十六位授权码
```

配置文件默认落在 `~/.netease_mail.json`（权限 600）。
**提醒用户不要把授权码提交进 git 仓库。**

### 第 2 步：跑自检，确认真的通了

**动手做任何收信/发信/改状态之前，先跑 `test`。** 它会依次验证 IMAP 登录、ID 命令、
列文件夹、SMTP 登录，一次定位是哪一环断了。

```bash
python scripts/net163_mail.py test
```

返回 `"ok": true` 再继续；否则按返回的 `hint` 跳到第 5 步排障。

### 第 3 步：执行具体操作

```bash
# 列出所有邮件文件夹（中文文件夹也在这里，收不到邮件先看这一步）
python scripts/net163_mail.py folders

# 列最近 10 封
python scripts/net163_mail.py list --limit 10

# 只看未读
python scripts/net163_mail.py list --unread --limit 20

# 搜索（本地过滤，对中文友好，支持 --from / --subject / --keyword / --since）
python scripts/net163_mail.py search --subject 发票 --since 2026-01-01
python scripts/net163_mail.py search --from boss@corp.com --limit 5

# 读某封邮件正文（uid 从 list/search 结果里拿）
python scripts/net163_mail.py read --uid 12345
python scripts/net163_mail.py read --uid 12345 --include-html --max-chars 8000

# 发信 / 回复 / 转发：一律两段式，先预览再确认
python scripts/net163_mail.py send --to a@b.com --subject 周报 --body "见附件" --dry-run
# → 拿到 confirm_token 后，把内容展示给用户，用户点头再用同一命令 + --confirm 发出
python scripts/net163_mail.py send --to a@b.com --subject 周报 --body "见附件" \
  --confirm <token>

# 回复某封（--uid 来自 list/search；自动取 Reply-To + 串联 In-Reply-To/References）
python scripts/net163_mail.py reply --uid 12345 --body "收到，明天给结论" --dry-run
python scripts/net163_mail.py reply --uid 12345 --all --body "收到"          # 回复全部
python scripts/net163_mail.py reply --uid 12345 --no-quote --body "简短回复"  # 不引用原文

# 转发（默认连原邮件附件一起带，--no-attachments 可去掉）
python scripts/net163_mail.py forward --uid 12345 --to c@d.com --body "请帮忙看下" --dry-run

# 标记已读 / 未读（同样两段式，见下方专章）
python scripts/net163_mail.py mark --dry-run
```

**写操作纪律（硬闸门，不是建议）**：`send` / `reply` / `forward` / `mark` 四个子命令
**没有 `--confirm <token>` 就一定不会执行**，脚本会直接报错退出。正确流程：

1. 先带 `--dry-run` 跑一遍，输出里有 `confirm_token` 和完整的 `message` / `preview` 清单；
2. 把内容**完整展示给用户**，等用户明确同意；
3. 用户点头后，用**完全相同的参数**再加 `--confirm <token>` 执行。

令牌是内容哈希：正文、收件人、主题、附件（或 mark 的 mailbox/UID 集合）任何一处被改动，
旧令牌立即失效，脚本会拒绝并要求重新预览。令牌一次性，用过即废。**不要为了省事绕过这一步。**

输出全部是 JSON（`ensure_ascii=False`），Agent 可直接解析，无需再加工。

### 第 4 步：标记已读 / 未读（`mark`）

用户说「把未读邮件都标成已读」「清一下未读」「这几封标成未读」时用这个子命令。

**默认行为**：只处理 **INBOX 里的未读邮件**（服务端 `SEARCH UNSEEN`），不会误动已读邮件，
也不会碰其它文件夹。

```bash
# ① 预览：到底会改哪些邮件（务必先跑这个）
python scripts/net163_mail.py mark --dry-run

# ② 用户点头后，用完全相同参数 + 令牌执行
python scripts/net163_mail.py mark --confirm <token>
```

常用筛选（条件可叠加，是 AND 关系；`--uids` 与筛选条件互斥，混用会报错）：

```bash
# 按 UID 精准标记（UID 从 list / search 结果里拿）
python scripts/net163_mail.py mark --uids 6440 6441 --dry-run

# 按条件：主题关键词 / 发件人 / 日期区间
python scripts/net163_mail.py mark --subject 发票 --since 2026-10-01 --dry-run
python scripts/net163_mail.py mark --from-addr no-reply@news.termius.com --dry-run

# 只处理最近 20 封未读（取命中集合的最后 N 封，即最新的）
python scripts/net163_mail.py mark --limit 20 --dry-run

# 换个文件夹操作（如广告邮件 / 垃圾邮件夹）
python scripts/net163_mail.py mark --mailbox Junk --dry-run

# 反向：标记为「未读」
python scripts/net163_mail.py mark --uids 6446 --unseen --dry-run

# --all：连同已读一起处理（例如 --unseen 想把整个收件箱都变未读）
python scripts/net163_mail.py mark --all --unseen --dry-run

# --only-changed：跳过状态已经正确的邮件，省掉无谓写入
python scripts/net163_mail.py mark --all --only-changed --dry-run
```

实现要点（改脚本时别踩）：

- IMAP 的已读标志是 **`\Seen`**（带反斜杠），不是 `READ`；标已读用
  `UID STORE <set> +FLAGS (\Seen)`，标未读用 `-FLAGS (\Seen)`。
- `imaplib` 返回的 `FLAGS` 在响应**元组的第一个元素**里（`part[0]`），不在邮件正文里；
  解析时要同时扫 `bytes` 与 `tuple[0]`，并且**去掉反斜杠再比较**
  （`{f.lstrip("\\").lower() ...}`），否则已读/未读永远判断错。
- 读操作用 `readonly=True` 连接，写操作另开一个 `readonly=False` 连接 —— 预览阶段
  绝不会误标。
- UID 集合按 **50 个一批**下发（`STORE_CHUNK`），避免单条命令过长被服务端截断。
- 筛选条件在**服务端**用 IMAP `SEARCH` 完成（`SINCE`/`BEFORE` 需转成 `DD-Mon-YYYY`
  英文月份格式），比本地扫全箱快得多。

### 第 5 步：遇到报错

先读 `references/troubleshooting.md`，按报错文本定位：

| 报错 | 一句话处置 |
|---|---|
| `535 Authentication failed` | 用了登录密码，或授权码错/失效 |
| `SELECT Unsafe Login...` | 漏发 IMAP `ID` 命令 |
| `KeyError: 'ID'` | 没打 `imaplib.Commands["ID"] = ("AUTH",)` 这个补丁 |
| `LOGIN Login error` | 地址不完整或 IMAP 服务未开启 |
| 连接超时 | 993/465 被防火墙/代理拦截 |
| 中文主题乱码 | MIME 头未解码 |
| 列表为空 | 邮件被归类到「广告邮件」等文件夹，先 `folders` |
| `mark` 提示令牌不一致 | 预览之后邮箱变了（来了新邮件/UID 集合变化），重新 `--dry-run` |
| `mark` 返回 `count: 0` | 本来就没有未读邮件，属正常无事可做 |

---

## 脚本说明：`scripts/net163_mail.py`

纯标准库（`imaplib` / `smtplib` / `email` / `re`），无第三方依赖，Python 3.8+。

**模块级关键补丁**（自己写代码时才需要，用脚本则已内置）：

```python
imaplib.Commands["ID"] = ("AUTH",)   # 必须在连接前执行，否则 ID 命令发不出去
```

连接顺序固定为：`login` → `_simple_command("ID", ...)` → `select`。顺序颠倒必被网易拒绝。

| 子命令 | 作用 |
|---|---|
| `config` | 把凭据写入本地配置文件 |
| `test` | 自检 IMAP + ID + 列目录 + SMTP |
| `folders` | 列出所有邮件文件夹 |
| `list` | 列最近邮件，支持 `--unread` |
| `search` | 按发件人/主题/关键词/日期本地过滤 |
| `read` | 读某封正文，可选 HTML、截断长度 |
| `mark` | 标记已读/未读（服务端 SEARCH 过滤 + 两段式确认） |
| `send` | 发信，支持 CC / HTML / 附件 / dry-run |
| `reply` | 回复，自动取 Reply-To 并串联会话；`--all` 回复全部、`--no-quote` 不引用原文 |
| `forward` | 转发，默认随带原邮件附件；`--no-attachments` 可去掉 |
| `drafts` | 列出待确认的预览草稿（对应 `confirm_token`） |

全局与子命令都接受 `--user / --auth-code / --imap-host / --smtp-host / --config`，
写在子命令前后均可。

---

## 自测

```bash
python tests/test_net163_mail.py
```

53 项用例，全部离线（FakeIMAP / FakeIMAPMark / RecordingSMTP 替身），
**不消耗真实邮箱配额，也不会真的发出邮件或改动任何邮箱状态**。

`NetworkTripwire` 在测试期间替换了 `socket.connect`，任何真实网络连接都会直接报错——
即使将来有人新写测试却忘了打桩，也会立刻失败而不是把邮件发给真人。

另外几个反向验证用例：
- `test_select_without_id_would_fail`：故意跳过 ID 命令，断言必须抛 `SELECT Unsafe Login`；
- `test_plain_send_is_blocked`：不带 `--confirm` 发信，断言必须被拦截且 `sent` 为空；
- `test_mark_without_confirm_is_blocked`：不带 `--confirm` 标记已读，断言必须被拦截且
  没有任何 `STORE` 调用；
- `test_token_invalidated_when_scope_changes`：预览 UID 1 后改成 UID 2 执行，断言必须拒绝；
- `test_network_tripwire_actually_blocks_real_connections`：断路器自身的反向验证。

改动脚本后务必重跑；用例失败先看是不是 ID 补丁、`FLAGS` 解析或 `argparse` 默认值被动了。

---

## 参考文件

- `references/netease_servers.md` — 服务器参数、授权码获取步骤、错误码对照、客户端配置
- `references/troubleshooting.md` — 六大类故障的逐条排查与多语言修复方案
- `tests/test_net163_mail.py` — 离线自测

---

## 注意事项

- 授权码等同密码，**不要写进代码、日志或聊天记录**，只放本地配置文件或环境变量。
- 网易个人邮箱有每日发信上限，批量群发要加间隔，否则触发限流被拒。
- 收信默认只读打开（`readonly=True`），不会误把邮件标记为已读；
  想改状态请显式用 `mark` 子命令，并遵守两段式确认。
- `mark` 会真实改动邮箱 flags，属于不可逆操作（虽然可以再标回来），**必须先 dry-run
  给用户看清楚命中了哪些邮件**。
- 脚本目前只覆盖单账号。多账号场景给每个账号配一份 `--config` 文件即可。
