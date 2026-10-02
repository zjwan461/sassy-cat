#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""netease-mail skill 自测（不联网）

覆盖三块：
1. 网易硬性规则：ID 命令必须早于 SELECT（含反向验证）。
2. 发信两段式确认闸门：无 --confirm 绝不外发、令牌与内容强绑定、令牌一次性。
3. 回复/转发：引用原文、会话头串联、前缀防重复、原附件带出、回复全部剔除自己。

运行：python tests/test_net163_mail.py
"""
import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "net163_mail.py"
spec = importlib.util.spec_from_file_location("net163_mail", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["net163_mail"] = mod
spec.loader.exec_module(mod)


# ---------------------------------------------------------------- 替身
class FakeIMAP:
    """记录调用顺序的 IMAP 替身。"""
    instances = []

    def __init__(self, host, port, ssl_context=None):
        self.host, self.port = host, port
        self.calls = []
        FakeIMAP.instances.append(self)
        self._selected = None

    def login(self, user, code):
        self.calls.append(("login", user, code))
        return "OK", [b"LOGIN completed"]

    def _simple_command(self, name, *args):
        self.calls.append(("_simple_command", name, *args))
        return "OK", [b"ID completed"]

    def select(self, mailbox, readonly=False):
        # 网易真实行为：SELECT 之前没发 ID 就拒绝
        if not any(c[0] == "_simple_command" and c[1] == "ID" for c in self.calls):
            raise mod.imaplib.IMAP4.error("SELECT Unsafe Login. Please contact kefu@188.com for help")
        self.calls.append(("select", mailbox))
        self._selected = mailbox
        return "OK", [b"1"]

    def list(self):
        self.calls.append(("list",))
        return "OK", [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren) "/" "Sent"']

    def uid(self, *args):
        self.calls.append(("uid",) + args)
        return "OK", [b""]

    def logout(self):
        self.calls.append(("logout",))
        return "BYE", [b"bye"]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def credit_card_message():
    """构造一封「客户来信 + 附件」，用于回复/转发用例。"""
    msg = EmailMessage()
    msg["From"] = "王客户 <client@example.com>"
    msg["To"] = "suben@formssi.com"
    msg["Cc"] = "cc1@example.com, cc2@example.com"
    msg["Reply-To"] = "replyto@example.com"
    msg["Subject"] = "信用卡账单问题"
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = mid = make_msgid()
    msg.set_content("账单金额有问题，请核实。")
    msg.add_attachment(b"PDF-BYTES", maintype="application", subtype="pdf", filename="bill.pdf")
    return msg, mid


class FakeIMAPWithMessage(FakeIMAP):
    """uid FETCH (RFC822) 返回指定邮件。"""
    payload: bytes = b""

    def uid(self, *args):
        self.calls.append(("uid",) + args)
        if len(args) >= 2 and args[0] == "FETCH" and "RFC822" in str(args[-1]) and "HEADER" not in str(args[-1]):
            return "OK", [(f'1 (RFC822 {{{len(self.payload)}}})'.encode(), self.payload), b")"]
        return "OK", [b""]


class RecordingSMTP:
    """记录真正外发的邮件；用来断言「不该发的时候一封都没发」。"""
    sent = []
    logins = []

    def __init__(self, host, port, context=None):
        self.host, self.port = host, port
        RecordingSMTP.logins.append(host)

    def login(self, user, code):
        return "OK"

    def noop(self):
        return "OK"

    def send_message(self, msg):
        RecordingSMTP.sent.append(msg)
        return {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeIMAPMark(FakeIMAP):
    """支持 SEARCH / FETCH(FLAGS+HEADER) / STORE 的替身，用于 mark 子命令。"""
    seen_map: dict = {}        # uid -> 是否已读
    search_result: bytes = b""

    def uid(self, *args):
        self.calls.append(("uid",) + args)
        cmd = args[0]
        if cmd == "SEARCH":
            return "OK", [self.search_result]
        if cmd == "FETCH":
            uid = args[1].decode() if isinstance(args[1], bytes) else str(args[1])
            flag = "\\Seen" if self.seen_map.get(uid) else ""
            head = (f'Subject: t{uid}\r\nFrom: f{uid}@example.com\r\n'
                    f'To: me@example.com\r\nDate: Mon, 01 Sep 2026 10:00:00 +0800\r\n'
                    f'Message-ID: <m{uid}@x>\r\n\r\n').encode()
            return "OK", [(f'1 (UID {uid} FLAGS ({flag}) RFC822.HEADER {{{len(head)}}})'.encode(), head), b")"]
        if cmd == "STORE":
            # IMAP 允许 "1,3" 这种逗号集合，替身要按集合展开
            uidset = (args[1].decode() if isinstance(args[1], bytes) else str(args[1]))
            value = True if "+FLAGS" in args else False
            for uid in uidset.split(","):
                self.seen_map[uid] = value
            return "OK", [b"1 (UID %s FLAGS (\\Seen))" % uidset.encode()]
        return "OK", [b""]


class NetworkTripwire:
    """测试期间的网络断路开关：任何真实 socket 连接都直接抛错。

    这是「测试绝不误发真实邮件」的物理保证——即使将来有人新写了测试却忘了打桩，
    也会立刻报错，而不是把邮件发给真人。
    """
    _orig_connect = None

    @classmethod
    def install(cls):
        import socket

        def blocked(self, address, *a, **kw):
            family = getattr(self, "family", None)
            if family == getattr(socket, "AF_UNIX", None):
                return cls._orig_connect(self, address, *a, **kw)
            raise RuntimeError(
                f"测试禁止真实网络连接（拦截目标 {address!r}）。"
                "请给测试打桩，不要连外网。"
            )

        if cls._orig_connect is None:
            cls._orig_connect = socket.socket.connect
            socket.socket.connect = blocked

    @classmethod
    def remove(cls):
        import socket

        if cls._orig_connect is not None:
            socket.socket.connect = cls._orig_connect
            cls._orig_connect = None


class BaseCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["NETEASE_OUTBOX_DIR"] = str(Path(self.tmp.name) / "outbox")
        FakeIMAP.instances.clear()
        RecordingSMTP.sent.clear()
        RecordingSMTP.logins.clear()
        self._imap = mod.imaplib.IMAP4_SSL
        self._smtp = mod.smtplib.SMTP_SSL
        mod.imaplib.IMAP4_SSL = FakeIMAP
        mod.smtplib.SMTP_SSL = RecordingSMTP
        NetworkTripwire.install()

    def tearDown(self):
        mod.imaplib.IMAP4_SSL = self._imap
        mod.smtplib.SMTP_SSL = self._smtp
        NetworkTripwire.remove()
        os.environ.pop("NETEASE_OUTBOX_DIR", None)
        self.tmp.cleanup()

    def creds(self):
        return {"user": "u@163.com", "auth_code": "X" * 16,
                "imap_host": "imap.163.com", "smtp_host": "smtp.163.com"}

    def run_cli(self, argv):
        """跑一次 CLI，捕获 stdout 里的 JSON。"""
        import io
        from contextlib import redirect_stdout
        args = mod.build_parser().parse_args(argv)
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = args.func(args)
        out = buf.getvalue().strip()
        return code, (json.loads(out) if out.startswith("{") else {})

    def base(self, *tail):
        return ["--user", "suben@formssi.com", "--auth-code", "X" * 16,
                "--imap-host", "imaphz.qiye.163.com", "--smtp-host", "smtphz.qiye.163.com", *tail]


# ---------------------------------------------------------------- 网易硬性规则
class TestIDOrder(BaseCase):
    def test_id_registered_as_auth_state(self):
        self.assertIn("ID", mod.imaplib.Commands)
        self.assertIn("AUTH", mod.imaplib.Commands["ID"])

    def test_id_sent_before_select(self):
        imap = mod.connect_imap(self.creds())
        names = [c[0] if c[0] != "_simple_command" else "ID" for c in imap.calls]
        self.assertEqual(names, ["login", "ID", "select"],
                         f"调用顺序错误，网易会报 Unsafe Login：{names}")
        self.assertEqual(imap.calls[2][1], "INBOX")

    def test_select_without_id_would_fail(self):
        """反向证明：跳过 ID 就会触发网易的 Unsafe Login 拦截。"""
        imap = FakeIMAP("imap.163.com", 993)
        imap.login("u@163.com", "X" * 16)
        with self.assertRaises(mod.imaplib.IMAP4.error) as ctx:
            imap.select("INBOX")
        self.assertIn("Unsafe Login", str(ctx.exception))

    def test_custom_host_preserved(self):
        creds = self.creds()
        creds["imap_host"] = "imaphz.qiye.163.com"
        imap = mod.connect_imap(creds)
        self.assertEqual(imap.host, "imaphz.qiye.163.com")
        self.assertEqual(imap.port, 993)


# ---------------------------------------------------------------- 确认闸门
class TestConfirmGate(BaseCase):
    def test_plain_send_is_blocked(self):
        """核心红线：不带 --confirm 绝不允许外发。"""
        code, out = self.run_cli(self.base(
            "send", "--to", "a@example.com", "--subject", "hi", "--body", "hello"))
        self.assertEqual(code, 1)
        self.assertFalse(out["ok"])
        self.assertIn("未提供用户确认令牌", out["error"])
        self.assertEqual(RecordingSMTP.sent, [], "没有用户确认竟然发出去了！")

    def test_reply_and_forward_are_blocked_without_confirm(self):
        for cmd, tail in [("reply", ["--uid", "1"]),
                          ("forward", ["--uid", "1", "--to", "a@example.com"])]:
            with self.subTest(cmd=cmd):
                code, out = self.run_cli(self.base(cmd, *tail, "--body", "x"))
                self.assertEqual(code, 1)
                self.assertIn("未提供用户确认令牌", out["error"])
        self.assertEqual(RecordingSMTP.sent, [])

    def test_network_tripwire_actually_blocks_real_connections(self):
        """反向验证断路器有效：真实 socket 连接必须被拦下。

        没有这个用例，断路器可能只是个摆设，而「测试绝不外发」就只是句空话。
        """
        import socket
        s = socket.socket()
        try:
            with self.assertRaises(RuntimeError) as ctx:
                s.connect(("smtp.163.com", 465))
        finally:
            s.close()
        self.assertIn("测试禁止真实网络连接", str(ctx.exception))

    def test_dry_run_returns_token_and_never_sends(self):
        code, out = self.run_cli(self.base(
            "send", "--to", "a@example.com", "--subject", "hi", "--body", "hello", "--dry-run"))
        self.assertEqual(code, 0)
        self.assertTrue(out["dry_run"])
        self.assertTrue(out["requires_confirmation"])
        self.assertEqual(len(out["confirm_token"]), 16)
        self.assertEqual(out["message"]["to"], ["a@example.com"])
        self.assertEqual(out["message"]["body"], "hello")
        self.assertEqual(RecordingSMTP.sent, [], "dry-run 竟然发了邮件")

    def test_confirm_with_correct_token_sends_once(self):
        _, prev = self.run_cli(self.base(
            "send", "--to", "a@example.com", "--subject", "hi", "--body", "hello", "--dry-run"))
        token = prev["confirm_token"]
        code, out = self.run_cli(self.base(
            "send", "--to", "a@example.com", "--subject", "hi", "--body", "hello",
            "--confirm", token))
        self.assertEqual(code, 0)
        self.assertTrue(out["sent"])
        self.assertEqual(len(RecordingSMTP.sent), 1)
        sent = RecordingSMTP.sent[0]
        self.assertEqual(sent["To"], "a@example.com")
        self.assertEqual(sent["Subject"], "hi")
        self.assertEqual(sent["From"], "suben@formssi.com")

    def test_token_is_single_use(self):
        _, prev = self.run_cli(self.base(
            "send", "--to", "a@example.com", "--subject", "hi", "--body", "hello", "--dry-run"))
        token = prev["confirm_token"]
        self.run_cli(self.base("send", "--to", "a@example.com", "--subject", "hi",
                               "--body", "hello", "--confirm", token))
        code, out = self.run_cli(self.base("send", "--to", "a@example.com", "--subject", "hi",
                                           "--body", "hello", "--confirm", token))
        self.assertEqual(code, 1)
        self.assertIn("无效或已被使用", out["error"])
        self.assertEqual(len(RecordingSMTP.sent), 1, "同一个令牌被重复使用，发了不止一封")

    def test_content_change_invalidates_token(self):
        """用户确认的是 hello，实际想发 hacked —— 必须拒绝。"""
        _, prev = self.run_cli(self.base(
            "send", "--to", "a@example.com", "--subject", "hi", "--body", "hello", "--dry-run"))
        token = prev["confirm_token"]
        code, out = self.run_cli(self.base(
            "send", "--to", "a@example.com", "--subject", "hi", "--body", "hacked",
            "--confirm", token))
        self.assertEqual(code, 1)
        self.assertIn("内容与用户确认时不一致", out["error"])
        self.assertEqual(RecordingSMTP.sent, [])

    def test_recipient_change_invalidates_token(self):
        _, prev = self.run_cli(self.base(
            "send", "--to", "a@example.com", "--subject", "hi", "--body", "hello", "--dry-run"))
        token = prev["confirm_token"]
        code, out = self.run_cli(self.base(
            "send", "--to", "attacker@evil.com", "--subject", "hi", "--body", "hello",
            "--confirm", token))
        self.assertEqual(code, 1)
        self.assertEqual(RecordingSMTP.sent, [])

    def test_attachment_change_invalidates_token(self):
        p1 = Path(self.tmp.name) / "a.txt"
        p1.write_text("AAA", encoding="utf-8")
        p2 = Path(self.tmp.name) / "b.txt"
        p2.write_text("BBB", encoding="utf-8")
        _, prev = self.run_cli(self.base(
            "send", "--to", "a@example.com", "--subject", "s", "--body", "b",
            "--attach", str(p1), "--dry-run"))
        token = prev["confirm_token"]
        code, _ = self.run_cli(self.base(
            "send", "--to", "a@example.com", "--subject", "s", "--body", "b",
            "--attach", str(p2), "--confirm", token))
        self.assertEqual(code, 1)
        # 即使文件名相同、内容不同也必须拦住
        p3 = Path(self.tmp.name) / "c.txt"
        p3.write_text("AAA", encoding="utf-8")
        _, prev2 = self.run_cli(self.base(
            "send", "--to", "a@example.com", "--subject", "s", "--body", "b",
            "--attach", str(p3), "--dry-run"))
        p3.write_text("CCC", encoding="utf-8")
        code2, _ = self.run_cli(self.base(
            "send", "--to", "a@example.com", "--subject", "s", "--body", "b",
            "--attach", str(p3), "--confirm", prev2["confirm_token"]))
        self.assertEqual(code2, 1, "附件内容被改过，令牌必须失效")
        self.assertEqual(RecordingSMTP.sent, [])

    def test_bogus_token_rejected(self):
        code, out = self.run_cli(self.base(
            "send", "--to", "a@example.com", "--subject", "hi", "--body", "hello",
            "--confirm", "deadbeefdeadbeef"))
        self.assertEqual(code, 1)
        self.assertIn("无效或已被使用", out["error"])
        self.assertEqual(RecordingSMTP.sent, [])

    def test_dry_run_and_confirm_conflict(self):
        code, out = self.run_cli(self.base(
            "send", "--to", "a@example.com", "--subject", "hi", "--body", "hello",
            "--dry-run", "--confirm", "x" * 16))
        self.assertEqual(code, 1)
        self.assertIn("不能同时使用", out["error"])

    def test_drafts_listing(self):
        self.run_cli(self.base("send", "--to", "a@example.com", "--subject", "待确认信",
                               "--body", "b", "--dry-run"))
        code, out = self.run_cli(self.base("drafts"))
        self.assertEqual(code, 0)
        self.assertEqual(out["count"], 1)
        self.assertEqual(out["drafts"][0]["subject"], "待确认信")

    def test_html_send_roundtrip(self):
        _, prev = self.run_cli(self.base(
            "send", "--to", "a@example.com", "--subject", "报表", "--body", "<b>hi</b>",
            "--html", "--dry-run"))
        code, out = self.run_cli(self.base(
            "send", "--to", "a@example.com", "--subject", "报表", "--body", "<b>hi</b>",
            "--html", "--confirm", prev["confirm_token"]))
        self.assertEqual(code, 0)
        self.assertTrue(out["sent"])
        self.assertEqual(RecordingSMTP.sent[0].get_content_type(), "multipart/alternative")


# ---------------------------------------------------------------- 回复 / 转发
class TestReplyForward(BaseCase):
    def setUp(self):
        super().setUp()
        self.orig, self.mid = credit_card_message()
        self.raw = self.orig.as_bytes()

        class WithMsg(FakeIMAPWithMessage):
            payload = self.raw

        mod.imaplib.IMAP4_SSL = WithMsg
        self.WithMsg = WithMsg

    def test_reply_defaults(self):
        code, out = self.run_cli(self.base("reply", "--uid", "1", "--body", "收到", "--dry-run"))
        self.assertEqual(code, 0)
        m = out["message"]
        # 收件人取 Reply-To，而不是 From
        self.assertEqual(m["to"], ["replyto@example.com"])
        self.assertEqual(m["subject"], "Re: 信用卡账单问题")
        self.assertEqual(m["action"], "reply")
        self.assertEqual(m["in_reply_to"], self.mid)
        self.assertIn(self.mid, m["references"])
        self.assertIn("收到", m["body"])
        self.assertIn("> 账单金额有问题", m["body"])

    def test_reply_prefix_not_duplicated(self):
        orig = EmailMessage()
        orig["From"] = "a@b.com"
        orig["Subject"] = "Re: Re: 已经回复过"
        orig["Message-ID"] = make_msgid()
        orig.set_content("x")

        class WithMsg(FakeIMAPWithMessage):
            payload = orig.as_bytes()

        mod.imaplib.IMAP4_SSL = WithMsg
        _, out = self.run_cli(self.base("reply", "--uid", "1", "--body", "y", "--dry-run"))
        self.assertEqual(out["message"]["subject"], "Re: Re: 已经回复过",
                         "重复叠加了 Re: 前缀")

    def test_reply_all_collects_to_and_cc_minus_self(self):
        code, out = self.run_cli(self.base(
            "--user", "suben@formssi.com", "reply", "--uid", "1", "--all",
            "--body", "ok", "--dry-run"))
        self.assertEqual(code, 0)
        m = out["message"]
        self.assertEqual(m["action"], "reply_all")
        self.assertEqual(m["to"], ["replyto@example.com"])
        self.assertIn("cc1@example.com", m["cc"])
        self.assertIn("cc2@example.com", m["cc"])
        self.assertNotIn("suben@formssi.com", m["cc"], "回复全部不该把自己放进抄送")

    def test_reply_explicit_to_wins(self):
        _, out = self.run_cli(self.base(
            "reply", "--uid", "1", "--to", "boss@formssi.com", "--body", "x", "--dry-run"))
        self.assertEqual(out["message"]["to"], ["boss@formssi.com"])

    def test_reply_no_quote(self):
        _, out = self.run_cli(self.base(
            "reply", "--uid", "1", "--body", "简短回复", "--no-quote", "--dry-run"))
        self.assertEqual(out["message"]["body"], "简短回复")

    def test_reply_keeps_explicit_subject(self):
        _, out = self.run_cli(self.base(
            "reply", "--uid", "1", "--subject", "自定义主题", "--body", "x", "--dry-run"))
        self.assertEqual(out["message"]["subject"], "自定义主题")

    def test_forward_carries_body_and_original_attachments(self):
        code, out = self.run_cli(self.base(
            "forward", "--uid", "1", "--to", "colleague@formssi.com",
            "--body", "请帮忙看下", "--dry-run"))
        self.assertEqual(code, 0)
        m = out["message"]
        self.assertEqual(m["action"], "forward")
        self.assertEqual(m["subject"], "Fwd: 信用卡账单问题")
        self.assertIn("请帮忙看下", m["body"])
        self.assertIn("转发的邮件", m["body"])
        self.assertIn("账单金额有问题", m["body"])
        names = [a["filename"] for a in m["attachments"]]
        self.assertIn("bill.pdf", names, "转发没带上原附件")

    def test_forward_no_attachments_flag(self):
        _, out = self.run_cli(self.base(
            "forward", "--uid", "1", "--to", "x@y.com", "--body", "f",
            "--no-attachments", "--dry-run"))
        self.assertEqual(out["message"]["attachments"], [])

    def test_forward_plus_new_attachment(self):
        extra = Path(self.tmp.name) / "note.txt"
        extra.write_text("mine", encoding="utf-8")
        _, out = self.run_cli(self.base(
            "forward", "--uid", "1", "--to", "x@y.com", "--body", "f",
            "--attach", str(extra), "--dry-run"))
        names = [a["filename"] for a in out["message"]["attachments"]]
        self.assertIn("bill.pdf", names)
        self.assertIn("note.txt", names)

    def test_forward_can_be_confirmed_and_sent(self):
        _, prev = self.run_cli(self.base(
            "forward", "--uid", "1", "--to", "colleague@formssi.com",
            "--body", "看下", "--dry-run"))
        code, out = self.run_cli(self.base(
            "forward", "--uid", "1", "--to", "colleague@formssi.com",
            "--body", "看下", "--confirm", prev["confirm_token"]))
        self.assertEqual(code, 0)
        self.assertTrue(out["sent"])
        self.assertEqual(len(RecordingSMTP.sent), 1)
        sent = RecordingSMTP.sent[0]
        payloads = [p.get_filename() for p in sent.iter_attachments()]
        self.assertEqual(payloads, ["bill.pdf"])

    def test_reply_can_be_confirmed_and_sent(self):
        _, prev = self.run_cli(self.base("reply", "--uid", "1", "--body", "收到", "--dry-run"))
        code, out = self.run_cli(self.base(
            "reply", "--uid", "1", "--body", "收到", "--confirm", prev["confirm_token"]))
        self.assertEqual(code, 0)
        self.assertTrue(out["sent"])
        sent = RecordingSMTP.sent[0]
        self.assertEqual(sent["To"], "replyto@example.com")
        self.assertEqual(sent["In-Reply-To"], self.mid)

    def test_missing_uid_reports_cleanly(self):
        class Empty(FakeIMAP):
            def uid(self, *args):
                self.calls.append(("uid",) + args)
                return "OK", [None]

        mod.imaplib.IMAP4_SSL = Empty
        code, out = self.run_cli(self.base("reply", "--uid", "999", "--body", "x", "--dry-run"))
        self.assertEqual(code, 1)
        self.assertIn("不存在", out["error"])

    def test_forward_requires_recipient(self):
        with self.assertRaises(SystemExit):
            mod.build_parser().parse_args(["forward", "--uid", "1"])


# ---------------------------------------------------------------- 纯函数
class TestHelpers(BaseCase):
    def test_with_prefix(self):
        self.assertEqual(mod.with_prefix("账单", "re"), "Re: 账单")
        self.assertEqual(mod.with_prefix("Re: 账单", "re"), "Re: 账单")
        self.assertEqual(mod.with_prefix("回复：账单", "re"), "回复：账单")
        self.assertEqual(mod.with_prefix("账单", "fwd"), "Fwd: 账单")
        self.assertEqual(mod.with_prefix("Fwd: 账单", "fwd"), "Fwd: 账单")
        self.assertEqual(mod.with_prefix("FW: 账单", "fwd"), "FW: 账单")
        self.assertEqual(mod.with_prefix("", "re"), "Re:")

    def test_collect_addrs_dedup_and_exclude(self):
        got = mod.collect_addrs(["A <a@b.com>", "a@b.com", "C <c@d.com>"],
                                exclude={"c@d.com"})
        self.assertEqual(got, ["A <a@b.com>"])

    def test_addr_of(self):
        self.assertEqual(mod.addr_of("某人 <x@y.com>"), "x@y.com")
        self.assertEqual(mod.addr_of("x@y.com"), "x@y.com")
        self.assertEqual(mod.addr_of(None), "")

    def test_token_stability_and_sensitivity(self):
        base = {"to": ["a@b.com"], "subject": "s", "body": "x"}
        t1 = mod.draft_token(base)
        self.assertEqual(t1, mod.draft_token(dict(base)), "同样内容应得到同样的令牌")
        self.assertNotEqual(t1, mod.draft_token({**base, "body": "y"}))


# ---------------------------------------------------------------- CLI 接线
class TestCLI(BaseCase):
    ALL_CMDS = ["config", "test", "folders", "list", "search", "read", "send",
                "reply", "forward", "drafts", "mark"]

    def test_config_roundtrip_and_permissions(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / "cfg.json"
            args = mod.build_parser().parse_args(
                ["config", "--config", str(cfg), "--user", "a@126.com", "--auth-code", "Y" * 16])
            self.assertEqual(args.func(args), 0)
            data = json.loads(cfg.read_text(encoding="utf-8"))
            self.assertEqual(data["user"], "a@126.com")
            self.assertEqual(data["imap_host"], "imap.163.com")
            loaded = mod.load_creds(mod.build_parser().parse_args(
                ["test", "--config", str(cfg)]))
            self.assertEqual(loaded["auth_code"], "Y" * 16)

    def test_send_requires_recipient(self):
        with self.assertRaises(SystemExit):
            mod.build_parser().parse_args(["send", "--subject", "hi"])

    def test_send_requires_subject(self):
        code, out = self.run_cli(self.base(
            "send", "--to", "a@b.com", "--body", "x", "--dry-run"))
        self.assertEqual(code, 1)
        self.assertIn("缺少主题", out["error"])

    def test_creds_args_work_in_both_positions(self):
        p = mod.build_parser()
        a = p.parse_args(["--user", "a@163.com", "list"])
        b = p.parse_args(["list", "--user", "a@163.com"])
        self.assertEqual(a.user, b.user)
        self.assertEqual(a.user, "a@163.com")

    def test_every_subcommand_wired_and_accepts_creds(self):
        """每个子命令都要有 func，且凭据参数写前写后都能被解析到。"""
        p = mod.build_parser()
        extra = {
            "read": ["--uid", "1"],
            "send": ["--to", "x@example.com", "--subject", "s", "--dry-run"],
            "reply": ["--uid", "1", "--dry-run"],
            "forward": ["--uid", "1", "--to", "x@example.com", "--dry-run"],
        }
        for cmd in self.ALL_CMDS:
            with self.subTest(cmd=cmd):
                tail = extra.get(cmd, [])
                ns = p.parse_args(["--user", "before@163.com", cmd, *tail])
                self.assertTrue(callable(getattr(ns, "func", None)), f"{cmd} 没绑定 handler")
                self.assertEqual(ns.user, "before@163.com")
                ns2 = p.parse_args([cmd, *tail, "--user", "after@163.com"])
                self.assertEqual(ns2.user, "after@163.com")
                ns3 = p.parse_args([cmd, *tail])
                self.assertIsNone(ns3.user, f"{cmd} 不该凭空造出 user")

    def test_confirm_flags_present_on_all_sending_commands(self):
        """三个发信子命令都必须有 --dry-run 与 --confirm，一个都不能漏。"""
        p = mod.build_parser()
        cases = [["send", "--to", "a@b.com", "--subject", "s"],
                 ["reply", "--uid", "1"],
                 ["forward", "--uid", "1", "--to", "a@b.com"]]
        for tail in cases:
            with self.subTest(cmd=tail[0]):
                ns = p.parse_args([*tail, "--dry-run"])
                self.assertTrue(ns.dry_run)
                ns = p.parse_args([*tail, "--confirm", "tok"])
                self.assertEqual(ns.confirm, "tok")
                self.assertFalse(ns.dry_run)

    def test_decode_mime_header(self):
        import base64
        raw = "=?utf-8?B?" + base64.b64encode("测试主旨".encode()).decode() + "?="
        self.assertEqual(mod.decode_mime(raw), "测试主旨")
        self.assertEqual(mod.decode_mime("Plain ASCII"), "Plain ASCII")
        self.assertEqual(mod.decode_mime(""), "")


# ---------------------------------------------------------------- 标记已读/未读
class TestMark(BaseCase):
    def setUp(self):
        super().setUp()
        # 每个用例一套干净的邮箱状态
        self.seen = {"1": False, "2": True, "3": False}
        FakeIMAPMark.seen_map = dict(self.seen)
        FakeIMAPMark.search_result = b"1 2 3"
        self._imap_cls = mod.imaplib.IMAP4_SSL
        mod.imaplib.IMAP4_SSL = FakeIMAPMark

    def tearDown(self):
        mod.imaplib.IMAP4_SSL = self._imap_cls
        super().tearDown()

    def stores(self):
        return [c for c in FakeIMAPMark.instances for c in c.calls if c[0] == "uid" and c[1] == "STORE"]

    def test_mark_without_confirm_is_blocked(self):
        """核心红线：不带 --confirm 绝不改动邮箱状态。"""
        code, out = self.run_cli(self.base("mark", "--uids", "1"))
        self.assertEqual(code, 1)
        self.assertIn("未提供用户确认令牌", out["error"])
        self.assertEqual(self.stores(), [], "没有用户确认竟然改了 flags！")

    def test_dry_run_previews_and_never_stores(self):
        code, out = self.run_cli(self.base("mark", "--uids", "1", "3", "--dry-run"))
        self.assertEqual(code, 0)
        self.assertTrue(out["dry_run"])
        self.assertEqual(out["action"], "标记为已读")
        self.assertEqual([m["uid"] for m in out["preview"]], ["1", "3"])
        self.assertFalse(out["preview"][0]["seen"])
        self.assertEqual(self.stores(), [], "dry-run 竟然改了 flags")

    def test_confirm_changes_flags_to_seen(self):
        _, prev = self.run_cli(self.base("mark", "--uids", "1", "3", "--dry-run"))
        code, out = self.run_cli(self.base("mark", "--uids", "1", "3",
                                           "--confirm", prev["confirm_token"]))
        self.assertEqual(code, 0)
        self.assertEqual(out["changed"], 2)
        self.assertTrue(FakeIMAPMark.seen_map["1"])
        self.assertTrue(FakeIMAPMark.seen_map["3"])

    def test_token_invalidated_when_scope_changes(self):
        """预览的是 UID 1，确认后偷偷改成 UID 2 —— 必须拒绝。"""
        _, prev = self.run_cli(self.base("mark", "--uids", "1", "--dry-run"))
        code, out = self.run_cli(self.base("mark", "--uids", "2",
                                           "--confirm", prev["confirm_token"]))
        self.assertEqual(code, 1)
        self.assertIn("不一致", out["error"])
        self.assertEqual(self.stores(), [])

    def test_unseen_direction_removes_flag(self):
        _, prev = self.run_cli(self.base("mark", "--uids", "2", "--unseen", "--dry-run"))
        self.assertEqual(prev["action"], "标记为未读")
        code, out = self.run_cli(self.base("mark", "--uids", "2", "--unseen",
                                           "--confirm", prev["confirm_token"]))
        self.assertEqual(code, 0)
        self.assertFalse(FakeIMAPMark.seen_map["2"])

    def test_only_changed_skips_already_correct(self):
        """--only-changed：状态已经正确的邮件不写入。"""
        _, prev = self.run_cli(self.base("mark", "--uids", "1", "2", "--only-changed", "--dry-run"))
        code, out = self.run_cli(self.base("mark", "--uids", "1", "2", "--only-changed",
                                           "--confirm", prev["confirm_token"]))
        self.assertEqual(code, 0)
        self.assertEqual(out["changed"], 1, "UID 2 本来就是已读，不该再写一次")
        self.assertEqual(len(self.stores()), 1)

    def test_default_scope_uses_unseen_on_server(self):
        self.run_cli(self.base("mark", "--dry-run"))
        last = FakeIMAPMark.instances[0]
        searches = [c for c in last.calls if c[0] == "uid" and c[1] == "SEARCH"]
        self.assertTrue(searches, "默认应走服务端 UNSEEN 搜索")
        self.assertIn("UNSEEN", searches[0])

    def test_all_flag_switches_search_to_all(self):
        self.run_cli(self.base("mark", "--all", "--dry-run"))
        last = FakeIMAPMark.instances[0]
        searches = [c for c in last.calls if c[0] == "uid" and c[1] == "SEARCH"]
        self.assertIn("ALL", searches[0])

    def test_filters_build_imap_criteria(self):
        self.run_cli(self.base("mark", "--since", "2026-09-01", "--before", "2026-09-30",
                               "--subject", "发票", "--from-addr", "boss@x.com", "--dry-run"))
        last = FakeIMAPMark.instances[0]
        crit = " ".join(str(x) for c in last.calls if c[0] == "uid" and c[1] == "SEARCH"
                        for x in c[3:])
        self.assertIn("SINCE 01-Sep-2026", crit)
        self.assertIn("BEFORE 30-Sep-2026", crit)
        self.assertIn('SUBJECT "发票"', crit)
        self.assertIn('FROM "boss@x.com"', crit)

    def test_empty_result_noop(self):
        FakeIMAPMark.search_result = b""
        code, out = self.run_cli(self.base("mark", "--dry-run"))
        self.assertEqual(code, 0)
        self.assertEqual(out["count"], 0)

    def test_store_uses_backslash_seen_flag(self):
        _, prev = self.run_cli(self.base("mark", "--uids", "1", "--dry-run"))
        self.run_cli(self.base("mark", "--uids", "1", "--confirm", prev["confirm_token"]))
        stores = self.stores()
        self.assertTrue(stores)
        flat = " ".join(stores[0])
        self.assertIn("+FLAGS", flat)
        self.assertIn(r"\Seen", flat)

    def test_mark_wired_with_confirm_flags(self):
        p = mod.build_parser()
        ns = p.parse_args(["mark", "--dry-run"])
        self.assertTrue(ns.dry_run)
        ns = p.parse_args(["mark", "--confirm", "tok"])
        self.assertEqual(ns.confirm, "tok")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    unittest.main(verbosity=2)


if __name__ == "__main__":
    main()