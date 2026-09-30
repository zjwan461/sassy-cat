#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
netease-mail helper: 网易邮箱 (163 / 126 / yeah / 188) IMAP + SMTP 命令行工具

设计要点（血的教训，勿删）：
1. 第三方登录必须用【16 位客户端授权码】，不是登录密码 —— 否则 535 Authentication failed
2. 登录成功后、SELECT 之前必须发送 IMAP ID 命令 —— 否则 SELECT Unsafe Login
   （imaplib 默认把 ID 注册在 AUTHENTICATED 状态之外，所以要先改写 imaplib.Commands）
3. 输出一律 JSON，便于 Agent 直接解析

用法见 SKILL.md
"""
from __future__ import annotations

import argparse
import email
import imaplib
import json
import mimetypes
import os
import smtplib
import ssl
import sys
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parsedate_to_datetime, parseaddr
from pathlib import Path

DEFAULT_IMAP_HOST = "imap.163.com"
DEFAULT_SMTP_HOST = "smtp.163.com"
IMAP_PORT = 993
SMTP_PORT = 465
CONFIG_PATH = Path.home() / ".netease_mail.json"

# 关键补丁：让未认证阶段就能发 ID 命令（网易风控要求）
imaplib.Commands["ID"] = ("AUTH",)

CLIENT_ID = ("name", "NetEaseMailSkill", "version", "1.0", "vendor", "local-agent")


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

    msg = EmailMessage()
    msg["From"] = creds["user"]
    msg["To"] = ", ".join(args.to)
    msg["Subject"] = args.subject
    if args.cc:
        msg["Cc"] = ", ".join(args.cc)

    body = args.body or (Path(args.body_file).read_text(encoding="utf-8") if args.body_file else "")
    if args.html:
        msg.set_content("HTML 邮件，请使用支持 HTML 的客户端查看。")
        msg.add_alternative(body, subtype="html")
    else:
        msg.set_content(body)

    for path in args.attach or []:
        p = Path(path)
        ctype, _ = mimetypes.guess_type(p.name)
        maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
        msg.add_attachment(p.read_bytes(), maintype=maintype, subtype=subtype, filename=p.name)

    if args.dry_run:
        emit({"ok": True, "dry_run": True, "from": creds["user"], "to": args.to, "cc": args.cc,
              "subject": args.subject, "attachments": [Path(p).name for p in (args.attach or [])],
              "body_preview": body[:300]})
        return 0

    try:
        with smtplib.SMTP_SSL(creds["smtp_host"], SMTP_PORT, context=ssl.create_default_context()) as s:
            s.login(creds["user"], creds["auth_code"])
            s.send_message(msg)
    except Exception as e:
        return fail(f"发送失败：{e}", hint="535 通常是授权码错误；554 通常是内容被判为垃圾邮件/收件人拒收")
    emit({"ok": True, "sent": True, "from": creds["user"], "to": args.to, "subject": args.subject})
    return 0


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


# ---------------------------------------------------------------- CLI
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

    p = argparse.ArgumentParser(description="网易邮箱 (163/126/yeah/188) IMAP+SMTP 工具",
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

    sp = add("send", "发送邮件")
    sp.add_argument("--to", nargs="+", required=True)
    sp.add_argument("--cc", nargs="+")
    sp.add_argument("--subject", required=True)
    sp.add_argument("--body", default="")
    sp.add_argument("--body-file")
    sp.add_argument("--html", action="store_true", help="body 按 HTML 发送")
    sp.add_argument("--attach", nargs="+")
    sp.add_argument("--dry-run", action="store_true", help="只打印将要发送的内容，不真正发出")

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