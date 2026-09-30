# 网易邮箱排障手册

按报错现象定位，逐条解决。

---

## 1. `SELECT Unsafe Login. Please contact kefu@188.com for help`（最高频）

**现象**：IMAP `login()` 成功，但紧接着 `select('INBOX')` 被服务器拒绝。

**根因**：网易对第三方 IMAP 客户端加了风控——客户端必须在 `SELECT` 之前先发一条
IMAP `ID` 命令（RFC 2971）声明自己的身份信息。`ID` 在标准协议里是可选命令，
但网易把它当成了前置验证条件，不声明就判定为「不安全登录」。
Python 的 `imaplib` 默认把 `ID` 注册在 AUTHENTICATED 状态之后，所以未认证阶段发不出去。

**修复（Python）**：两处改动，顺序不能错。

```python
import imaplib

# ① 模块级：改写命令注册表，让 ID 在未认证阶段可用（必须放在连接之前）
imaplib.Commands["ID"] = ("AUTH",)

imap = imaplib.IMAP4_SSL("imap.163.com", 993)
imap.login("you@163.com", "16位授权码")

# ② 登录成功后、select 之前：发送 ID
client_id = ("name", "MyClient", "version", "1.0", "vendor", "my-org")
imap._simple_command("ID", '("' + '" "'.join(client_id) + '")')

# ③ 现在才能 select
imap.select("INBOX")
```

**修复（其它语言）**：

- **Node.js**：原生 `imap` 包不发 `ID`，需换用 `imap-mkl` 等会在握手时发送 `ID` 的库；
  或自行在 `ready` 事件里发出 `ID` 命令后再 `openBox`。
- **imapclient（Python）**：`ID` 未被封装，仍需走上面的 `imaplib.Commands` 补丁后
  用底层 `_imap` 句柄发送。
- **Go / Rust / Java**：查所用库是否支持 `ID` 扩展；不支持则需在登录后手动注入原始命令。

> `ID` 命令未认证阶段发送是安全的：它只是声明客户端名与版本，不携带凭据。

---

## 2. `535 Authentication failed` / `Error: LOGIN Login error`

按顺序排查：

1. **用的是不是 16 位客户端授权码？** 网易不接受登录密码。这是最常见原因。
2. **服务开了吗？** 网页版【设置 → POP3/SMTP/IMAP】里 IMAP/SMTP 服务必须是开启状态。
3. **邮箱地址完整吗？** 必须是 `user@163.com` 全称，不能只写 `user`。
4. **授权码是否已失效？** 重新生成授权码后旧码立即作废。
5. **复制时带空格/换行了吗？** 授权码区分大小写，粘贴后检查首尾。

---

## 3. 连接超时 / `Connection refused`

- 确认 993 / 465 端口没被公司网络、防火墙或代理拦截；换手机热点试一次可快速判断。
- 公司网络只放行 25 端口时，可临时改用不加密模式排障（IMAP 143 / SMTP 25），
  确认网络通后再切回 SSL。
- 代理环境下需给 `imaplib` / `smtplib` 显式传代理，二者默认不走系统代理。

---

## 4. 中文主题显示成 `=?utf-8?B?xxxx?=`

MIME 编码头未解码。用标准库处理即可：

```python
from email.header import decode_header, make_header
subject = str(make_header(decode_header(raw_subject)))
```

正文乱码同理：按 `part.get_content_charset()` 解码，缺省回退 `utf-8` + `errors="replace"`。

---

## 5. 收到的邮件列表为空

- 以为 `SEARCH ALL` 就能拿到全部：网易对大邮箱会限制单次返回量，分批取。
- 只看 INBOX：网易会把部分邮件自动归类到「广告邮件」「订阅邮件」等文件夹，
  先 `LIST` 列出所有文件夹再定位。
- UID 与序号混用：`imap.uid('FETCH', uid, ...)` 才是 UID 语义，
  用 `imap.fetch(n, ...)` 拿的是会随删除变动的序号，两者不可混用。

---

## 6. 发送成功但对方没收到

- 检查「已发送」文件夹是否真有该邮件，确认服务端已受理。
- `554` / `550` 常见于：收件人地址不存在、正文含大量链接被判垃圾邮件、
  短时间内高频群发触发限流。
- 网易个人邮箱有每日发信量上限，批量发送需加间隔。