#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
netease-mail helper: 网易邮箱（@163.com / @126.com / @yeah.net / @188.com / 网易企业邮）
IMAP + SMTP 命令行工具。

设计要点（血的教训，勿删）：
1. 第三方登录必须用【16 位客户端授权码】，不是登录密码 —— 否则 535 Authentication failed。
2. 登录成功后、SELECT 之前必须发送 IMAP ID 命令 —— 否则 SELECT Unsafe Login。
   （imaplib 默认把 ID 注册在 AUTHENTICATED 状态之外，所以连接前要先改写 imaplib.Commands）
3. 收信一律用 UID 语义（imap.uid('FETCH', ...)），不要用会漂移的邮件序号。
4. 发信是【两段式硬闸门】：先 --dry-run 生成预览 + confirm_token（内容哈希），
   把预览展示给用户确认；用户点头后再带 --confirm <token> 执行同样命令才真正外发。
   没有 --confirm 时任何子命令都不会发信 —— 这是有意为之，勿删。
5. 输出一律 JSON（ensure_ascii=False），便于 Agent 直接解析。

用法见 SKILL.md
"""
from __future__ import annotations

import argparse
import email
import hashlib
import imaplib
import json
import mimetypes
import os
import smtplib
import ssl
import sys
import time
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from pathlib import Path

DEFAULT_IMAP_HOST = "imap.163.com"
DEFAULT_SMTP_HOST = "smtp.163.com"
IMAP_PORT = 993
SMTP_PORT = 465
CONFIG_PATH = Path.home() / ".netease_mail.json"
DRAFT_MAX_AGE_HOURS = 24

# 关键补丁：让未认证阶段就能发 ID 命令（网易风控要求）
imaplib.Commands["ID"] = ("AUTH",)

CLIENT_ID = ("name", "NetEaseMailSkill", "version", "1.1", "vendor", "local-agent")


# ---------------------------------------------------------------- 基础工具
def emit(obj) -> None:
    json.dump(obj, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def fail(msg: str, **extra) -> int:
    emit({"ok": False, "error": msg, **extra})
    return 1


def decode_mime(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def load_creds(args) -> dict:
    """优先级：命令行参数 > 环境变量 > 配置文件"""
    cfg: dict = {}
    cfg_path = Path(args.config) if getattr(args, "config", None) else CONFIG_PATH
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}

    def pick(cli_val, env_key, cfg_key, default=None):
        if cli_val:
            return cli_val
        if os.environ.get(env_key):
            return os.environ[env_key]
        if cfg.get(cfg_key):
            return cfg[cfg_key]
        return default

    return {
        "user": pick(getattr(args, "user", None), "NETEASE_EMAIL", "user"),
        "auth_code": pick(getattr(args, "auth_code", None), "NETEASE_AUTH_CODE", "auth_code"),
        "imap_host": pick(getattr(args, "imap_host", None), "NETEASE_IMAP_HOST", "imap_host", DEFAULT_IMAP_HOST),
        "smtp_host": pick(getattr(args, "smtp_host", None), "NETEASE_SMTP_HOST", "smtp_host", DEFAULT_SMTP_HOST),
        "config_path": cfg_path,
    }


def connect_imap(creds: dict, mailbox: str = "INBOX"):
    imap = imaplib.IMAP4_SSL(creds["imap_host"], IMAP_PORT, ssl_context=ssl.create_default_context())
    imap.login(creds["user"], creds["auth_code"])
    imap._simple_command("ID", '("' + '" "'.join(CLIENT_ID) + '")')  # 网易风控必需
    imap.select(mailbox, readonly=True)
    return imap


def fetch_message(imap, uid: str, mailbox: str = "INBOX"):
    """按 UID 取回完整邮件（含正文与附件），返回 email.message.Message。"""
    key = uid.encode() if isinstance(uid, str) else uid
    typ, data = imap.uid("FETCH", key, "(RFC822)")
    if typ != "OK" or not data or data[0] is None:
        raise LookupError(f"UID {uid} 不存在于 {mailbox}")
    raw = b""
    for part in data:
        if isinstance(part, tuple):
            raw += part[1]
    if not raw:
        raise LookupError(f"UID {uid} 取回内容为空（{mailbox}）")
    return email.message_from_bytes(raw)


def addr_of(value: str | None) -> str:
    """从 '显示名 <a@b.com>' 中取出纯地址。"""
    return parseaddr(value or "")[1] or ""


def collect_addrs(values, exclude=()) -> list[str]:
    """去重收集地址，保留用户书写的显示名；exclude 里的地址一律剔除。"""
    out: list[str] = []
    seen: set[str] = set()
    ex = {a.lower() for a in exclude if a}
    for v in values or []:
        v = (v or "").strip()
        if not v:
            continue
        key = (addr_of(v) or v).lower()
        if key in ex or key in seen:
            continue
        seen.add(key)
        out.append(v)
    return out


def with_prefix(subject: str, kind: str) -> str:
    """加 Re: / Fwd: 前缀，已有同类前缀则不重复叠加。

    中文客户端的回复/转发前缀有半角冒号与全角冒号两种写法，都要认。
    """
    s = (subject or "").strip()
    if kind == "re":
        labels, label = ("re", "回复", "答复", "回覆"), "Re"
    else:
        labels, label = ("fwd", "fw", "转发", "轉寄"), "Fwd"
    low = s.lower()
    for lab in labels:
        for sep in (":", "："):
            if low.startswith((lab + sep).lower()):
                return s
    return f"{label}: {s}" if s else f"{label}:"


def _esc(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------- 发信：内容装配
def _resolve_body(args) -> str:
    if getattr(args, "body_file", None):
        return Path(args.body_file).read_text(encoding="utf-8")
    return getattr(args, "body", "") or ""


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _add_file_attachments(msg: EmailMessage, paths) -> list[dict]:
    entries = []
    for p in paths or []:
        path = Path(p)
        data = path.read_bytes()
        ctype, _ = mimetypes.guess_type(path.name)
        maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=path.name)
        entries.append({"filename": path.name, "size": len(data), "sha256": _digest(data)})
    return entries


def _compose(creds: dict, *, to, cc, subject, body, html, attach_paths,
             raw_attachments=(), extra_headers=None, action="send", source_uid=None):
    """装配待发邮件 + 生成用于确认的内容清单（manifest）。manifest 一旦确定即不可变。"""
    msg = EmailMessage()
    msg["From"] = creds["user"]
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    for key, val in (extra_headers or {}).items():
        if val:
            msg[key] = val

    if html:
        msg.set_content("HTML 邮件，请使用支持 HTML 的客户端查看。")
        msg.add_alternative(body, subtype="html")
    else:
        msg.set_content(body)

    entries = _add_file_attachments(msg, attach_paths)
    for ra in raw_attachments:
        msg.add_attachment(ra["data"], maintype=ra["maintype"], subtype=ra["subtype"],
                           filename=ra["filename"])
        entries.append({"filename": ra["filename"], "size": len(ra["data"]),
                        "sha256": _digest(ra["data"])})

    manifest = {
        "action": action,
        "source_uid": source_uid,
        "from": creds["user"],
        "to": list(to),
        "cc": list(cc or []),
        "subject": subject,
        "html": bool(html),
        "in_reply_to": (extra_headers or {}).get("In-Reply-To"),
        "references": (extra_headers or {}).get("References"),
        "attachments": entries,
        "body": body,
    }
    return msg, manifest


def original_attachments(orig) -> list[dict]:
    """抽取原邮件里的附件（转发时原样带上）。"""
    out = []
    for part in orig.walk():
        if part.is_multipart():
            continue
        disp = str(part.get("Content-Disposition") or "")
        fname = part.get_filename()
        if not fname and "attachment" not in disp.lower():
            continue
        ctype = part.get_content_type()
        maintype, _, subtype = ctype.partition("/")
        data = part.get_payload(decode=True) or b""
        out.append({
            "filename": decode_mime(fname) or "unnamed",
            "maintype": maintype or "application",
            "subtype": subtype or "octet-stream",
            "data": data,
        })
    return out


def _attribution(orig) -> str:
    return f"On {decode_mime(orig.get('Date'))}, {decode_mime(orig.get('From'))} wrote:"


def text_reply_body(own: str, orig, quoted: bool = True) -> str:
    if not quoted:
        return own.strip()
    inner = _body_of(orig)["text"]
    parts = [own.strip(), "", _attribution(orig)]
    if inner:
        parts.append("\n".join("> " + ln for ln in inner.splitlines()))
    return "\n".join(parts).strip()


def html_reply_body(own: str, orig, quoted: bool = True) -> str:
    if not quoted:
        return own
    o = _body_of(orig)
    inner = o["html"] or "<br>".join(_esc(ln) for ln in o["text"].splitlines())
    return (
        f'<div>{own}</div>\n'
        f'<div class="quote">\n<p>{_esc(_attribution(orig))}</p>\n'
        f'<blockquote>{inner}</blockquote>\n</div>'
    )


def text_forward_body(own: str, orig, att_names=()) -> str:
    o = _body_of(orig)
    hdr = [
        "---------- 转发的邮件 ----------",
        f"发件人: {decode_mime(orig.get('From'))}",
        f"日期: {decode_mime(orig.get('Date'))}",
        f"主题: {decode_mime(orig.get('Subject'))}",
        f"收件人: {decode_mime(orig.get('To'))}",
    ]
    cc = decode_mime(orig.get("Cc"))
    if cc:
        hdr.append(f"抄送: {cc}")
    if att_names:
        hdr.append("附件: " + ", ".join(att_names))
    return "\n".join([own.strip(), "", *hdr, "", o["text"]]).strip()


def html_forward_body(own: str, orig, att_names=()) -> str:
    o = _body_of(orig)
    inner = o["html"] or "<br>".join(_esc(ln) for ln in o["text"].splitlines())
    hdr = [
        "---------- 转发的邮件 ----------",
        f"发件人: {_esc(decode_mime(orig.get('From')))}",
        f"日期: {_esc(decode_mime(orig.get('Date')))}",
        f"主题: {_esc(decode_mime(orig.get('Subject')))}",
        f"收件人: {_esc(decode_mime(orig.get('To')))}",
    ]
    cc = decode_mime(orig.get("Cc"))
    if cc:
        hdr.append(f"抄送: {_esc(cc)}")
    if att_names:
        hdr.append("附件: " + _esc(", ".join(att_names)))
    return (
        f'<div>{own}</div>\n'
        f'<div class="forwarded">\n' + "<br>\n".join(hdr) + f'\n<br><br>\n{inner}\n</div>'
    )


# ---------------------------------------------------------------- 发信：确认闸门
def outbox_dir() -> Path:
    return Path(os.environ.get("NETEASE_OUTBOX_DIR") or (Path.home() / ".netease_mail_outbox"))


def draft_token(manifest: dict) -> str:
    """内容指纹：正文/收件人/主题/附件哈希任意一处变化，令牌即失效。"""
    canon = json.dumps(manifest, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]


def _draft_path(token: str) -> Path:
    return outbox_dir() / f"{token}.json"


def _cleanup_drafts() -> None:
    d = outbox_dir()
    if not d.exists():
        return
    cutoff = time.time() - DRAFT_MAX_AGE_HOURS * 3600
    for f in d.glob("*.json"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
        except Exception:
            pass


def save_draft(token: str, manifest: dict) -> Path:
    d = outbox_dir()
    d.mkdir(parents=True, exist_ok=True)
    _cleanup_drafts()
    p = _draft_path(token)
    p.write_text(json.dumps({
        "token": token,
        "manifest": manifest,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "pending",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def load_draft(token: str):
    p = _draft_path(token)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def consume_draft(token: str) -> None:
    try:
        _draft_path(token).unlink()
    except Exception:
        pass


def _precheck_gate(args):
    """发信前的入口检查：把「必须经用户确认」这条红线断在最前面。

    放在读取邮箱之前，是为了不浪费一次 IMAP 往返，也让违规调用一眼可辨。
    返回 True 表示检查通过（可以继续装配内容），False 表示已经被拦截并已输出错误。
    """
    if getattr(args, "dry_run", False) and getattr(args, "confirm", None):
        fail("--dry-run 与 --confirm 不能同时使用",
             hint="预览时不带 --confirm；确认后发送时去掉 --dry-run")
        return False
    if not getattr(args, "dry_run", False) and not getattr(args, "confirm", None):
        fail("发送被拦截：未提供用户确认令牌，邮件没有发出",
             hint=("发信必须两段式：先加 --dry-run 预览内容并把 message 展示给用户，"
                   "用户确认后再用相同的参数加 --confirm <token> 执行"))
        return False
    return True


def _dispatch(args, creds: dict, msg: EmailMessage, manifest: dict) -> int:
    """发信统一出口：没有用户确认令牌，绝不外发。"""
    token = draft_token(manifest)

    if getattr(args, "dry_run", False):
        if getattr(args, "confirm", None):
            return fail("--dry-run 与 --confirm 不能同时使用",
                        hint="预览时不带 --confirm；确认后发送时去掉 --dry-run")
        p = save_draft(token, manifest)
        emit({
            "ok": True,
            "dry_run": True,
            "requires_confirmation": True,
            "confirm_token": token,
            "draft_file": str(p),
            "message": manifest,
            "hint": ("请把 message 内容完整展示给用户确认；用户同意后，"
                     f"用相同的参数再加 --confirm {token} 才会真正发出"),
        })
        return 0

    confirm = getattr(args, "confirm", None)
    if not confirm:
        return fail(
            "发送被拦截：未提供用户确认令牌，邮件没有发出",
            hint=("发信必须两段式：先加 --dry-run 预览内容并把 message 展示给用户，"
                  "用户确认后再用相同的参数加 --confirm <token> 执行"),
        )

    stored = load_draft(confirm)
    if stored is None:
        return fail(f"确认令牌无效或已被使用：{confirm}",
                    hint="重新用 --dry-run 生成预览与新的确认令牌")
    if stored.get("token") != token or stored.get("manifest") != manifest:
        return fail("内容与用户确认时不一致，已拒绝发送",
                    hint="正文/收件人/主题/附件被改动过，请重新预览并再次让用户确认")

    try:
        with smtplib.SMTP_SSL(creds["smtp_host"], SMTP_PORT,
                              context=ssl.create_default_context()) as s:
            s.login(creds["user"], creds["auth_code"])
            s.send_message(msg)
    except Exception as e:
        return fail(f"发送失败：{e}",
                    hint="535 通常是授权码错误；554 通常是内容被判为垃圾邮件/收件人拒收")

    consume_draft(confirm)
    emit({
        "ok": True,
        "sent": True,
        "action": manifest["action"],
        "from": creds["user"],
        "to": manifest["to"],
        "cc": manifest["cc"],
        "subject": manifest["subject"],
        "attachments": [a["filename"] for a in manifest["attachments"]],
        "confirmed_with": confirm,
        "note": "SMTP 已投递；本工具不写「已发送」，网页版已发送文件夹里可能看不到这封",
    })
    return 0


# ---------------------------------------------------------------- 子命令
def cmd_config(args) -> int:
    cfg_path = Path(args.config) if args.config else CONFIG_PATH
    data = {
        "user": args.user,
        "auth_code": args.auth_code,
        "imap_host": args.imap_host or DEFAULT_IMAP_HOST,
        "smtp_host": args.smtp_host or DEFAULT_SMTP_HOST,
    }
    cfg_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        cfg_path.chmod(0o600)
    except Exception:
        pass
    emit({"ok": True, "saved_to": str(cfg_path), "note": "授权码只保存本地，请勿提交到仓库"})
    return 0


def cmd_test(args) -> int:
    creds = load_creds(args)
    if not creds["user"] or not creds["auth_code"]:
        return fail("缺少账号或授权码：请设置环境变量 NETEASE_EMAIL / NETEASE_AUTH_CODE，或先跑 config 子命令")
    result = {"ok": True, "user": creds["user"], "imap": None, "smtp": None}
    try:
        imap = connect_imap(creds)
        typ, data = imap.list()
        result["imap"] = {
            "host": creds["imap_host"],
            "port": IMAP_PORT,
            "folders": [d.decode(errors="replace") if isinstance(d, bytes) else str(d) for d in data],
        }
        imap.logout()
    except imaplib.IMAP4.error as e:
        return fail(f"IMAP 失败：{e}", hint="检查授权码是否为16位客户端授权码、IMAP服务是否已开启")
    except Exception as e:
        return fail(f"IMAP 连接失败：{e}", hint="检查网络/防火墙是否放行 993 端口")

    try:
        with smtplib.SMTP_SSL(creds["smtp_host"], SMTP_PORT, context=ssl.create_default_context()) as s:
            s.login(creds["user"], creds["auth_code"])
            s.noop()
        result["smtp"] = {"host": creds["smtp_host"], "port": SMTP_PORT, "logged_in": True}
    except Exception as e:
        result["ok"] = False
        result["smtp"] = {"host": creds["smtp_host"], "port": SMTP_PORT, "error": str(e)}
    emit(result)
    return 0 if result["ok"] else 1


def _fetch_headers(imap, uids: list[bytes]) -> list[dict]:
    rows = []
    for uid in uids:
        typ, data = imap.uid("FETCH", uid, "(FLAGS RFC822.HEADER)")
        if typ != "OK" or not data or data[0] is None:
            continue
        raw = b""
        flags = ""
        for part in data:
            if isinstance(part, tuple):
                raw += part[1]
                flags += part[0].decode(errors="replace") if isinstance(part[0], bytes) else str(part[0])
            else:
                flags += part.decode(errors="replace") if isinstance(part, bytes) else str(part)
        msg = email.message_from_bytes(raw)
        try:
            date = parsedate_to_datetime(msg.get("Date")).isoformat()
        except Exception:
            date = decode_mime(msg.get("Date"))
        rows.append({
            "uid": uid.decode(),
            "mailbox": None,
            "from": decode_mime(msg.get("From")),
            "to": decode_mime(msg.get("To")),
            "subject": decode_mime(msg.get("Subject")),
            "date": date,
            "message_id": msg.get("Message-ID"),
            "flags": sorted(set(f for f in flags.replace("(", " ").replace(")", " ").split() if f.isupper())),
        })
    return rows


def _body_of(msg) -> dict:
    text_parts, html_parts, attachments = [], [], []
    for part in msg.walk():
        ctype = part.get_content_type()
        disp = str(part.get("Content-Disposition") or "")
        if "attachment" in disp.lower() or part.get_filename():
            attachments.append({
                "filename": decode_mime(part.get_filename()),
                "size": len(part.get_payload(decode=True) or b""),
            })
            continue
        if ctype == "text/plain":
            text_parts.append(part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace"))
        elif ctype == "text/html":
            html_parts.append(part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace"))
    return {"text": "\n".join(text_parts).strip(), "html": "\n".join(html_parts).strip(), "attachments": attachments}


def cmd_list(args) -> int:
    creds = load_creds(args)
    imap = connect_imap(creds, args.mailbox)
    try:
        typ, data = imap.uid("SEARCH", None, "ALL")
        uids = data[0].split() if data and data[0] else []
        if args.unread:
            typ, data = imap.uid("SEARCH", None, "UNSEEN")
            uids = data[0].split() if data and data[0] else []
        uids = uids[-args.limit:]
        rows = _fetch_headers(imap, list(reversed(uids)))
        for r in rows:
            r["mailbox"] = args.mailbox
        emit({"ok": True, "mailbox": args.mailbox, "total_matched": len(uids), "count": len(rows), "messages": rows})
    finally:
        try:
            imap.logout()
        except Exception:
            pass
    return 0


def cmd_search(args) -> int:
    creds = load_creds(args)
    imap = connect_imap(creds, args.mailbox)
    try:
        typ, data = imap.uid("SEARCH", None, "ALL")
        uids = data[0].split() if data and data[0] else []
        uids = uids[-args.scan:]
        rows = _fetch_headers(imap, list(reversed(uids)))
        needle_from = (args.from_ or "").lower()
        needle_subj = (args.subject or "").lower()
        needle_kw = (args.keyword or "").lower()
        hits = []
        for r in rows:
            if needle_from and needle_from not in r["from"].lower():
                continue
            if needle_subj and needle_subj not in r["subject"].lower():
                continue
            if needle_kw and needle_kw not in (r["subject"] + r["from"] + r["to"]).lower():
                continue
            if args.unseen and "SEEN" in r["flags"]:
                continue
            if args.since and (r["date"] or "")[:10] < args.since:
                continue
            r["mailbox"] = args.mailbox
            hits.append(r)
            if len(hits) >= args.limit:
                break
        emit({"ok": True, "mailbox": args.mailbox, "scanned": len(rows), "count": len(hits), "messages": hits})
    finally:
        try:
            imap.logout()
        except Exception:
            pass
    return 0


def cmd_read(args) -> int:
    creds = load_creds(args)
    imap = connect_imap(creds, args.mailbox)
    try:
        typ, data = imap.uid("FETCH", args.uid.encode(), "(RFC822)")
        if typ != "OK" or not data or data[0] is None:
            return fail(f"UID {args.uid} 不存在于 {args.mailbox}")
        raw = b""
        for part in data:
            if isinstance(part, tuple):
                raw += part[1]
        msg = email.message_from_bytes(raw)
        body = _body_of(msg)
        emit({
            "ok": True,
            "uid": args.uid,
            "mailbox": args.mailbox,
            "from": decode_mime(msg.get("From")),
            "to": decode_mime(msg.get("To")),
            "cc": decode_mime(msg.get("Cc")),
            "subject": decode_mime(msg.get("Subject")),
            "date": decode_mime(msg.get("Date")),
            "text": body["text"][: args.max_chars],
            "html": body["html"][: args.max_chars] if args.include_html else None,
            "attachments": body["attachments"],
        })
    finally:
        try:
            imap.logout()
        except Exception:
            pass
    return 0


def cmd_send(args) -> int:
    creds = load_creds(args)
    if not creds["user"] or not creds["auth_code"]:
        return fail("缺少账号或授权码")
    if not _precheck_gate(args):
        return 1
    if not (args.subject or "").strip():
        return fail("缺少主题：send 必须显式给 --subject")
    to = collect_addrs(args.to)
    if not to:
        return fail("收件人为空，请检查 --to")
    cc = collect_addrs(args.cc or [])
    body = _resolve_body(args)
    msg, manifest = _compose(creds, to=to, cc=cc, subject=args.subject, body=body,
                             html=args.html, attach_paths=args.attach, action="send")
    return _dispatch(args, creds, msg, manifest)


def cmd_reply(args) -> int:
    creds = load_creds(args)
    if not creds["user"] or not creds["auth_code"]:
        return fail("缺少账号或授权码")
    if not _precheck_gate(args):
        return 1
    imap = connect_imap(creds, args.mailbox)
    try:
        orig = fetch_message(imap, args.uid, args.mailbox)
    except LookupError as e:
        return fail(str(e))
    except imaplib.IMAP4.error as e:
        return fail(f"读取原邮件失败：{e}")
    finally:
        try:
            imap.logout()
        except Exception:
            pass

    me = (creds["user"] or "").lower()
    orig_from = addr_of(decode_mime(orig.get("From")))
    reply_to = addr_of(decode_mime(orig.get("Reply-To"))) or orig_from

    if args.to:
        to = collect_addrs(args.to)
    else:
        to = collect_addrs([reply_to])
    if not to:
        return fail("无法确定收件人：原邮件 From/Reply-To 解析为空，请显式指定 --to")

    if args.all:
        flat = [f"{n} <{a}>" if n else a
                for n, a in getaddresses([decode_mime(orig.get("To")),
                                          decode_mime(orig.get("Cc"))]) if a]
        cc = collect_addrs(flat, exclude={me, *[addr_of(t) for t in to]})
        cc = collect_addrs(list(cc) + collect_addrs(args.cc or []), exclude={me})
    else:
        cc = collect_addrs(args.cc or [], exclude={me})

    subject = args.subject or with_prefix(decode_mime(orig.get("Subject")), "re")
    mid = orig.get("Message-ID")
    refs = " ".join(x for x in [decode_mime(orig.get("References")), mid] if x).strip()
    extra = {"In-Reply-To": mid, "References": refs}

    own = _resolve_body(args)
    body = (html_reply_body(own, orig, quoted=not args.no_quote) if args.html
            else text_reply_body(own, orig, quoted=not args.no_quote))

    msg, manifest = _compose(creds, to=to, cc=cc, subject=subject, body=body, html=args.html,
                             attach_paths=args.attach, extra_headers=extra,
                             action="reply_all" if args.all else "reply", source_uid=args.uid)
    return _dispatch(args, creds, msg, manifest)


def cmd_forward(args) -> int:
    creds = load_creds(args)
    if not creds["user"] or not creds["auth_code"]:
        return fail("缺少账号或授权码")
    if not _precheck_gate(args):
        return 1
    imap = connect_imap(creds, args.mailbox)
    try:
        orig = fetch_message(imap, args.uid, args.mailbox)
    except LookupError as e:
        return fail(str(e))
    except imaplib.IMAP4.error as e:
        return fail(f"读取原邮件失败：{e}")
    finally:
        try:
            imap.logout()
        except Exception:
            pass

    to = collect_addrs(args.to)
    if not to:
        return fail("收件人为空，请检查 --to")
    cc = collect_addrs(args.cc or [], exclude={(creds["user"] or "").lower()})

    keep_atts = not args.no_attachments
    raw_atts = original_attachments(orig) if keep_atts else []
    att_names = [a["filename"] for a in raw_atts]

    subject = args.subject or with_prefix(decode_mime(orig.get("Subject")), "fwd")
    own = _resolve_body(args)
    body = (html_forward_body(own, orig, att_names) if args.html
            else text_forward_body(own, orig, att_names))

    msg, manifest = _compose(creds, to=to, cc=cc, subject=subject, body=body, html=args.html,
                             attach_paths=args.attach, raw_attachments=raw_atts,
                             action="forward", source_uid=args.uid)
    return _dispatch(args, creds, msg, manifest)


def cmd_folders(args) -> int:
    creds = load_creds(args)
    imap = imaplib.IMAP4_SSL(creds["imap_host"], IMAP_PORT, ssl_context=ssl.create_default_context())
    imap.login(creds["user"], creds["auth_code"])
    imap._simple_command("ID", '("' + '" "'.join(CLIENT_ID) + '")')
    typ, data = imap.list()
    folders = [d.decode(errors="replace") if isinstance(d, bytes) else str(d) for d in data]
    imap.logout()
    emit({"ok": True, "folders": folders})
    return 0


def cmd_drafts(args) -> int:
    """列出待确认的草稿（预览过但还没确认发送的）。"""
    d = outbox_dir()
    items = []
    if d.exists():
        for f in sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            m = data.get("manifest", {})
            items.append({
                "confirm_token": data.get("token"),
                "created_at": data.get("created_at"),
                "action": m.get("action"),
                "to": m.get("to"),
                "subject": m.get("subject"),
                "draft_file": str(f),
            })
    emit({"ok": True, "outbox": str(d), "count": len(items), "drafts": items})
    return 0


# ---------------------------------------------------------------- CLI
def _add_confirm_flags(sp: argparse.ArgumentParser) -> None:
    """发信类子命令共用的两段式确认开关。"""
    sp.add_argument("--dry-run", "--preview", dest="dry_run", action="store_true",
                    help="只预览不发送，生成 confirm_token 供用户确认")
    sp.add_argument("--confirm", metavar="TOKEN",
                    help="带上 --dry-run 生成的 confirm_token 才真正发送（缺此项一律不外发）")


def _add_send_body_flags(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("--subject")
    sp.add_argument("--body", default="")
    sp.add_argument("--body-file")
    sp.add_argument("--html", action="store_true", help="body 按 HTML 发送")
    sp.add_argument("--attach", nargs="+", help="附件路径，可多个")


def build_parser() -> argparse.ArgumentParser:
    # 公共凭据参数：全局与子命令均可传入（--user 写在前或在后都行）
    def add_common(parser: argparse.ArgumentParser, suppress_default: bool) -> None:
        """suppress_default=True 时，未传参不写入命名空间，避免覆盖上一级已解析的值。"""
        d = argparse.SUPPRESS if suppress_default else None
        parser.add_argument("--user", default=d, help="邮箱地址，如 you@163.com")
        parser.add_argument("--auth-code", default=d, help="16 位客户端授权码（不是登录密码）")
        parser.add_argument("--imap-host", default=d, help=f"默认 {DEFAULT_IMAP_HOST}")
        parser.add_argument("--smtp-host", default=d, help=f"默认 {DEFAULT_SMTP_HOST}")
        parser.add_argument("--config", default=d, help=f"配置文件路径，默认 {CONFIG_PATH}")

    root_common = argparse.ArgumentParser(add_help=False)
    add_common(root_common, suppress_default=False)

    p = argparse.ArgumentParser(description="网易邮箱 (163/126/yeah/188/企业邮) IMAP+SMTP 工具",
                                parents=[root_common])
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, help_text, **kw):
        sub_common = argparse.ArgumentParser(add_help=False)
        add_common(sub_common, suppress_default=True)
        sp = sub.add_parser(name, help=help_text, parents=[sub_common], **kw)
        sp.set_defaults(func=globals()[f"cmd_{name}"])
        return sp

    add("config", "把凭据写入本地配置文件")
    add("test", "自检：IMAP 登录 + ID + 列目录 + SMTP 登录")
    add("folders", "列出所有邮件文件夹")
    add("drafts", "列出待确认（已预览未发送）的草稿")

    sp = add("list", "列出最近邮件")
    sp.add_argument("--mailbox", default="INBOX")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--unread", action="store_true")

    sp = add("search", "搜索邮件（本地过滤，对中文友好）")
    sp.add_argument("--mailbox", default="INBOX")
    sp.add_argument("--from", dest="from_", help="发件人包含")
    sp.add_argument("--subject", help="主题包含")
    sp.add_argument("--keyword", help="关键词（主题/发件人/收件人）")
    sp.add_argument("--since", help="起始日期 YYYY-MM-DD")
    sp.add_argument("--unseen", action="store_true", help="只要未读")
    sp.add_argument("--scan", type=int, default=500, help="最多扫描最近多少封")
    sp.add_argument("--limit", type=int, default=20)

    sp = add("read", "读取某封邮件正文")
    sp.add_argument("--uid", required=True)
    sp.add_argument("--mailbox", default="INBOX")
    sp.add_argument("--include-html", action="store_true")
    sp.add_argument("--max-chars", type=int, default=4000)

    sp = add("send", "发送新邮件（必须先 --dry-run 预览并经用户确认）")
    sp.add_argument("--to", nargs="+", required=True)
    sp.add_argument("--cc", nargs="+")
    _add_send_body_flags(sp)
    sp.set_defaults(subject_required=True)
    _add_confirm_flags(sp)

    sp = add("reply", "回复邮件（自动引用原文并串联会话；--all 回复全部）")
    sp.add_argument("--uid", required=True, help="原邮件 UID（从 list/search 结果拿）")
    sp.add_argument("--mailbox", default="INBOX")
    sp.add_argument("--to", nargs="+", help="覆盖收件人（默认取原邮件 Reply-To/From）")
    sp.add_argument("--cc", nargs="+")
    sp.add_argument("--all", action="store_true", help="回复全部：原收件人+抄送，自动剔除自己")
    sp.add_argument("--no-quote", action="store_true", help="不引用原文")
    _add_send_body_flags(sp)
    _add_confirm_flags(sp)

    sp = add("forward", "转发邮件（原文 + 原附件一并带上）")
    sp.add_argument("--uid", required=True)
    sp.add_argument("--mailbox", default="INBOX")
    sp.add_argument("--to", nargs="+", required=True)
    sp.add_argument("--cc", nargs="+")
    sp.add_argument("--no-attachments", action="store_true", help="不带上原邮件的附件")
    _add_send_body_flags(sp)
    _add_confirm_flags(sp)

    return p


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    args = build_parser().parse_args()
    try:
        return args.func(args)
    except imaplib.IMAP4.error as e:
        return fail(f"IMAP 错误：{e}", hint="看不懂就查 references/troubleshooting.md")
    except KeyboardInterrupt:
        return fail("已中断")


if __name__ == "__main__":
    raise SystemExit(main())