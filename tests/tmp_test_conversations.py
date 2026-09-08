# -*- coding: utf-8 -*-
"""conversations 模块自测（临时数据目录，不污染真实 userData）"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

tmp = tempfile.mkdtemp(prefix="sassy-test-")
import paths
paths.init(tmp)

from server import conversations as c

# 1. 首次使用：自动创建默认会话并激活
aid = c.active_id()
assert aid and aid.startswith("conv-"), f"active_id 异常: {aid}"
lst = c.list_sorted()
assert len(lst) == 1 and lst[0]["title"] == "新对话", lst

# 2. 新建 + 激活
# 2. 新建 + 激活（"新对话"按钮路径：默认标题）
conv2 = c.create()
assert c.active_id() == conv2["id"]
assert len(c.list_sorted()) == 2

# 3. auto_title：默认标题才改名；已改名不覆盖
assert c.auto_title(conv2["id"], "帮我写个爬虫") is not None
assert c.get(conv2["id"])["title"] == "帮我写个爬虫"
assert c.auto_title(conv2["id"], "不该覆盖") is None
assert c.get(conv2["id"])["title"] == "帮我写个爬虫"
# 自定义标题的会话不被 auto_title 覆盖
conv_custom = c.create("已命名")
assert c.auto_title(conv_custom["id"], "也不覆盖") is None
assert c.get(conv_custom["id"])["title"] == "已命名"
c.delete(conv_custom["id"])
long_text = "一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十"
conv3 = c.create()
c.auto_title(conv3["id"], long_text)
assert len(c.get(conv3["id"])["title"]) == 24, c.get(conv3["id"])["title"]

# 4. 切换激活
c.set_active(aid)
assert c.active_id() == aid
assert c.set_active("conv-nonexist") is None

# 5. rename / touch
c.rename(aid, "我的主对话")
assert c.get(aid)["title"] == "我的主对话"
import time
before = c.get(conv3["id"])["updatedAt"]
time.sleep(1.01)
c.touch(conv3["id"])
assert c.get(conv3["id"])["updatedAt"] > before
assert c.list_sorted()[0]["id"] == conv3["id"]  # 最近更新的排最前

# 6. 删除非激活会话
assert c.delete(conv3["id"]) is True
assert c.get(conv3["id"]) is None
assert c.active_id() == aid  # 激活不受影响

# 7. 删除激活会话：自动回退到最近更新的其他会话
c.create("占位")  # 再建一个非激活
c.set_active(aid)
assert c.delete(aid) is True
assert c.active_id() != aid and c.active_id() is not None

# 8. 删除最后一个：自动补建默认
for item in list(c.list_sorted()):
    c.delete(item["id"])
assert len(c.list_sorted()) == 1 and c.active_id() == c.list_sorted()[0]["id"]

# 9. 原子写 + 重新加载（模拟重启）：缓存清空后从文件恢复
c2 = c.create("重启前会话")
c._cache = None
assert c.get(c2["id"]) is not None
assert c.active_id() == c2["id"]

# 10. activeId 悬空（指向被外部删除的会话）：回退到最近更新
doc = json.load(open(paths.data_path("conversations.json"), encoding="utf-8"))
doc["activeId"] = "conv-ghost"
json.dump(doc, open(paths.data_path("conversations.json"), "w", encoding="utf-8"), ensure_ascii=False)
c._cache = None
assert c.active_id() in [x["id"] for x in doc["conversations"]], c.active_id()

# 11. 文件损坏：备份并重建
with open(paths.data_path("conversations.json"), "w", encoding="utf-8") as f:
    f.write("{ broken json !!!")
c._cache = None
assert c.active_id() is not None
assert os.path.isfile(paths.data_path("conversations.json.bak"))

shutil.rmtree(tmp, ignore_errors=True)
print("ALL PASS (11/11)")
