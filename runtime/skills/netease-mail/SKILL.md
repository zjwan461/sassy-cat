---
name: netease-mail
description: >
  接入并操作网易邮箱（@163.com / @126.com / @yeah.net / @188.com
  及网易企业邮箱）：收发信、列邮件、搜索、读正文、发带附件邮件，以及 535 / Unsafe Login 等报错排障。Use this
  skill whenever the user mentions 网易邮箱 / 163邮箱 / 126邮箱 / yeah.net /
  188邮箱, wants to bind an email account to a client or their own code, set
  up IMAP/SMTP or 客户端授权码, read/send/search mails from a script, build
  email automation, or hits errors like "535 Authentication
  failed"、"SELECT Unsafe Login"、"LOGIN Login
  error"、"=?utf-8?B?"、连接超时。Triggers on:
  邮箱接入、邮件自动化、IMAP、SMTP、POP3、授权码、收邮件、发邮件、定时收信、邮件监控、邮件通知、mailbox。
---

# 网易邮箱接入与自动化

一站式处理网易系邮箱的接入与日常操作。**核心踩坑点已经封进脚本，不要自己重写。**

---

## 铁律（违反必然失败）

1. **第三方登录必须用 16 位客户端授权码**，不是登录密码 → 否则 `535 Authentication failed`。
2. **IMAP 登录成功后、`SELECT` 之前必须先发 `ID` 命令** → 否则
   `SELECT Unsafe Login. Please contact kefu@188.com for help`。
3. 收信一律用 `UID` 语义（`imap.uid('FETCH', ...)`），不要用会漂移的邮件序号。

脚本 `scripts/net163_mail.py` 已内置第 1、2 条的修复与第 3 条的正确用法，直接用即可。

---

## 服务器参数速查（个人邮箱四后缀通用）

| 用途 | 地址 | 端口 | 加密 |
|---|---|---|---|
| IMAP | `imap.163.com` | 993 | SSL |
| SMTP | `smtp.163.com` | 465 | SSL |
| POP3 | `pop.163.com` | 995 | SSL |

网易企业邮箱用 `imaphz.qiye.163.com` / `smtphz.qiye.163.com`。
完整对照（含不加密端口、客户端配置）见 `references/netease_servers.md`。

---

## 工作流

### 第 0 步：先确认前置条件（缺了直接失败，别跳过）

问用户或自行确认两点：

- 网易邮箱网页版【设置 → POP3/SMTP/IMAP】里，IMAP/SMTP 服务**是否已开启**（默认关闭）；
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

**动手做任何收信/发信之前，先跑 `test`。** 它会依次验证 IMAP 登录、ID 命令、
列文件夹、SMTP 登录，一次定位是哪一环断了。

```bash
python scripts/net163_mail.py test
```

返回 `"ok": true` 再继续；否则按返回的 `hint` 跳到第 4 步排障。

### 第 3 步：执行具体操作

```bash
# 列出所有邮件文件夹（中文文件夹也在这里，收不到邮件先看这一步）
python scripts/net163_mail.py folders

# 列最近 10 封
python scripts/net163_mail.py list --limit 10

# 只看未读
python scripts/net163_mail.py list --unread --limit 20

# 搜索（本地过滤，对中文友好，支持 --from / --subject / --keyword / --since ）
python scripts/net163_mail.py search --subject 发票 --since 2026-01-01
python scripts/net163_mail.py search --from boss@corp.com --limit 5

# 读某封邮件正文（uid 从 list/search 结果里拿）
python scripts/net163_mail.py read --uid 12345
python scripts/net163_mail.py read --uid 12345 --include-html --max-chars 8000

# 发信（先 dry-run 确认一遍，再加附件/HTML）
python scripts/net163_mail.py send --to a@b.com --subject 周报 --body "见附件" --dry-run
python scripts/net163_mail.py send --to a@b.com --cc c@d.com \
  --subject 周报 --body-file /code/report.html --html --attach /code/report.pdf
```

**写操作纪律**：`send` 是真实外发动作。首次给用户发信时先跑一遍 `--dry-run`
把收件人/主题/正文/附件清单展示给用户确认，用户点头后再去掉 `--dry-run` 真正发送。

输出全部是 JSON（`ensure_ascii=False`），Agent 可直接解析，无需再加工。

### 第 4 步：遇到报错

先读 `references/troubleshooting.md`，按报错文本定位：

| 报错 | 一句话处置 |
|---|---|
| `535 Authentication failed` | 用了登录密码，或授权码错/失效 |
| `SELECT Unsafe Login...` | 漏发 IMAP `ID` 命令 |
| `LOGIN Login error` | 地址不完整或 IMAP 服务未开启 |
| 连接超时 | 993/465 被防火墙/代理拦截 |
| 中文主题乱码 | MIME 头未解码 |
| 列表为空 | 邮件被归类到「广告邮件」等文件夹，先 `folders` |

---

## 脚本说明：`scripts/net163_mail.py`

纯标准库（`imaplib` / `smtplib` / `email`），无第三方依赖，Python 3.8+。

**模块级关键补丁**（自己写代码时才需要，用脚本则已内置）：

```python
imaplib.Commands["ID"] = ("AUTH",)   # 必须在连接前执行，否则 ID 命令发不出去
```

连接顺序固定为：`login` → `_simple_command("ID", ...)` → `select`。顺序颠倒必被网易拒绝。

| 子命令 | 作用 |
|---|---|
| `config` | 把凭据写入本地配置文件 |
| `test` | 自检 IMAP + ID + 列目录 + SMTP |
| `folders` | 列出所有文件夹 |
| `list` | 列最近邮件，支持 `--unread` |
| `search` | 按发件人/主题/关键词/日期本地过滤 |
| `read` | 读某封正文，可选 HTML、截断长度 |
| `send` | 发信，支持 CC / HTML / 附件 / dry-run |

全局与子命令都接受 `--user / --auth-code / --imap-host / --smtp-host / --config`，
写在子命令前后均可。

---

## 自测

```bash
python tests/test_net163_mail.py
```

10 项用例，全部离线（FakeIMAP 替身），不消耗真实邮箱配额。
其中 `test_select_without_id_would_fail` 是**反向验证**：
故意跳过 ID 命令，断言必须抛出 `SELECT Unsafe Login`——保证补丁没被误删。

改动脚本后务必重跑；用例失败先看是不是 ID 补丁或 `argparse` 默认值被动了。

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
  想标记已读需显式用 `imap.store`，脚本暂不提供，避免误操作。
- 脚本目前只覆盖单账号。多账号场景给每个账号配一份 `--config` 文件即可。
