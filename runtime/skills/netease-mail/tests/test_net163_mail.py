#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""netease-mail skill 自测（不联网）：

用 FakeIMAP 替身验证「ID 必须早于 SELECT」这条网易硬性规则，
以及 CLI 的 dry-run / config 行为。运行：python tests/test_net163_mail.py
"""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "net163_mail.py"
spec = importlib.util.spec_from_file_location("net163_mail", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["net163_mail"] = mod
spec.loader.exec_module(mod)


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


class TestIDOrder(unittest.TestCase):
    def setUp(self):
        FakeIMAP.instances.clear()
        self._orig = mod.imaplib.IMAP4_SSL
        mod.imaplib.IMAP4_SSL = FakeIMAP

    def tearDown(self):
        mod.imaplib.IMAP4_SSL = self._orig

    def creds(self):
        return {"user": "u@163.com", "auth_code": "X" * 16,
                "imap_host": "imap.163.com", "smtp_host": "smtp.163.com"}

    def test_id_registered_as_auth_state(self):
        self.assertIn("ID", mod.imaplib.Commands)
        self.assertIn("AUTH", mod.imaplib.Commands["ID"])

    def test_id_sent_before_select(self):
        imap = mod.connect_imap(self.creds())
        names = [c[0] if c[0] != "_simple_command" else f"ID" for c in imap.calls]
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


class TestCLI(unittest.TestCase):
    def test_config_roundtrip_and_permissions(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / "cfg.json"
            args = mod.build_parser().parse_args(
                ["config", "--config", str(cfg), "--user", "a@126.com", "--auth-code", "Y" * 16])
            self.assertEqual(args.func(args), 0)
            data = json.loads(cfg.read_text(encoding="utf-8"))
            self.assertEqual(data["user"], "a@126.com")
            self.assertEqual(data["imap_host"], "imap.163.com")
            # 凭据读取优先级：命令行 > 环境变量 > 配置文件
            loaded = mod.load_creds(mod.build_parser().parse_args(
                ["test", "--config", str(cfg)]))
            self.assertEqual(loaded["auth_code"], "Y" * 16)

    def test_send_dry_run_never_touches_network(self):
        args = mod.build_parser().parse_args([
            "send", "--user", "z@163.com", "--auth-code", "Z" * 16,
            "--to", "x@example.com", "--subject", "hi", "--body", "hello", "--dry-run",
        ])
        self.assertEqual(args.func(args), 0)

    def test_send_requires_recipient_and_subject(self):
        with self.assertRaises(SystemExit):
            mod.build_parser().parse_args(["send", "--user", "z@163.com", "--subject", "hi"])

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
        }
        for cmd in ["config", "test", "folders", "list", "search", "read", "send"]:
            with self.subTest(cmd=cmd):
                tail = extra.get(cmd, [])
                ns = p.parse_args(["--user", "before@163.com", cmd, *tail])
                self.assertTrue(callable(getattr(ns, "func", None)), f"{cmd} 没绑定 handler")
                self.assertEqual(ns.user, "before@163.com")
                ns2 = p.parse_args([cmd, *tail, "--user", "after@163.com"])
                self.assertEqual(ns2.user, "after@163.com")
                ns3 = p.parse_args([cmd, *tail])
                self.assertIsNone(ns3.user, f"{cmd} 不该凭空造出 user")


    def test_decode_mime_header(self):
        import base64
        raw = "=?utf-8?B?" + base64.b64encode("测试主旨".encode()).decode() + "?="
        self.assertEqual(mod.decode_mime(raw), "测试主旨")
        self.assertEqual(mod.decode_mime("Plain ASCII"), "Plain ASCII")
        self.assertEqual(mod.decode_mime(""), "")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    unittest.main(verbosity=2)


if __name__ == "__main__":
    main()