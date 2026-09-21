# -*- coding: utf-8 -*-
"""create_skill 工具临时测试：
1. 基本创建（含 files 辅助文件）
2. copies 从虚拟环境复制产物
3. 非法名称自动 slugify / 不可转换时报错
4. 同名冲突拒绝 + overwrite 备份
5. 越界路径拒绝
6. 生成的 SKILL.md 可被 deepagents SkillsMiddleware 与 skills_api 正确解析
运行：python tests/tmp_test_create_skill.py（在项目根目录）
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "python"))

from agent.tools.builtin_tools import create_skill, SKILLS_ROOT, work_dir  # noqa: E402

TEST_SLUG = "tmp-test-skill"
TEST_DIR = os.path.join(SKILLS_ROOT, TEST_SLUG)


def cleanup():
    shutil.rmtree(TEST_DIR, ignore_errors=True)
    # 清理 overwrite 产生的备份目录
    for name in os.listdir(SKILLS_ROOT):
        if name.startswith(TEST_SLUG + ".bak-"):
            shutil.rmtree(os.path.join(SKILLS_ROOT, name), ignore_errors=True)


def main():
    cleanup()
    os.makedirs(SKILLS_ROOT, exist_ok=True)

    # 准备一个虚拟环境中的产物文件用于 copies
    src_dir = os.path.join(work_dir, "tmp")
    os.makedirs(src_dir, exist_ok=True)
    src_file = os.path.join(src_dir, "clean_data.py")
    with open(src_file, "w", encoding="utf-8") as f:
        f.write("print('hello skill')\n")

    try:
        # 1. 基本创建
        r = create_skill.invoke({
            "name": "TMP Test Skill!!",  # 故意给不合规名称，测 slugify
            "description": "测试技能：用于验证 create_skill 工具，当主人说测试技能时使用。",
            "instructions": "# 测试技能\n\n## 工作流\n1. 运行 scripts/clean_data.py\n2. 输出结果",
            "files": [{"path": "references/notes.md", "content": "# 备注\n指导要点"}],
            "copies": [{"src": "/tmp/clean_data.py", "dest": "scripts/clean_data.py"}],
        })
        assert "已创建成功" in r and "tmp-test-skill" in r, f"用例1失败: {r}"
        assert os.path.isfile(os.path.join(TEST_DIR, "SKILL.md"))
        assert os.path.isfile(os.path.join(TEST_DIR, "references", "notes.md"))
        assert os.path.isfile(os.path.join(TEST_DIR, "scripts", "clean_data.py"))
        print("✅ 用例1 基本创建 + slugify + files + copies 通过")

        # 2. 同名拒绝
        r = create_skill.invoke({
            "name": TEST_SLUG,
            "description": "重复测试",
            "instructions": "x",
        })
        assert "已存在" in r and "overwrite" in r, f"用例2失败: {r}"
        print("✅ 用例2 同名冲突拒绝 通过")

        # 3. overwrite 备份
        r = create_skill.invoke({
            "name": TEST_SLUG,
            "description": "覆盖后的描述",
            "instructions": "# 新版",
            "overwrite": True,
        })
        assert "已创建成功" in r and "备份" in r, f"用例3失败: {r}"
        print("✅ 用例3 overwrite 覆盖 + 备份 通过")

        # 4. 越界路径拒绝
        r = create_skill.invoke({
            "name": "evil-skill",
            "description": "越界测试",
            "instructions": "x",
            "files": [{"path": "../escaped.txt", "content": "bad"}],
        })
        assert "非法" in r, f"用例4失败: {r}"
        assert not os.path.exists(os.path.join(SKILLS_ROOT, "escaped.txt"))
        assert not os.path.exists(os.path.join(SKILLS_ROOT, "evil-skill"))
        print("✅ 用例4 越界路径拒绝（不落盘） 通过")

        # 5. 完全无法转换的名称
        r = create_skill.invoke({
            "name": "!!!???###",
            "description": "名称测试",
            "instructions": "x",
        })
        assert "无法转换" in r, f"用例5失败: {r}"
        print("✅ 用例5 非法名称报错 通过")

        # 6. description 为空拒绝
        r = create_skill.invoke({"name": "empty-desc", "description": "", "instructions": "x"})
        assert "不能为空" in r, f"用例6失败: {r}"
        print("✅ 用例6 空描述拒绝 通过")

        # 7. deepagents SkillsMiddleware 能解析生成的 SKILL.md
        with open(os.path.join(TEST_DIR, "SKILL.md"), "r", encoding="utf-8") as f:
            content = f.read()
        print("---- 生成的 SKILL.md ----")
        print(content)
        print("--------------------------")
        from deepagents.middleware.skills import _parse_skill_metadata
        meta = _parse_skill_metadata(content, os.path.join(TEST_DIR, "SKILL.md"), TEST_SLUG)
        assert meta is not None, "用例7失败：deepagents 无法解析 SKILL.md"
        assert meta["name"] == TEST_SLUG, f"用例7失败：name 不匹配 {meta}"
        assert "覆盖后的描述" in meta["description"], f"用例7失败：description 不匹配 {meta}"
        print("✅ 用例7 deepagents SkillsMiddleware 解析 通过")

        # 8. skills_api 的极简 frontmatter 解析也能识别
        from server.skills_api import _parse_frontmatter
        fm = _parse_frontmatter(content)
        assert fm.get("name") == TEST_SLUG, f"用例8失败: {fm}"
        assert "覆盖后的描述" in fm.get("description", ""), f"用例8失败: {fm}"
        print("✅ 用例8 skills_api _parse_frontmatter 解析 通过")

        print("\n全部用例通过 🎉")
    finally:
        cleanup()
        os.remove(src_file)


if __name__ == "__main__":
    main()
