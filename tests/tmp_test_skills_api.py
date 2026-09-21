# -*- coding: utf-8 -*-
"""skills_api 快速验证：列表 / 详情 / 读文件 / 写文件 / 导入导出 / 路径穿越防护。"""
import asyncio
import io
import os
import shutil
import sys
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "python"))

from server import skills_api  # noqa: E402
from fastapi import HTTPException  # noqa: E402


async def main():
    # 0. 清理上次失败运行可能遗留的临时文件，保证幂等
    def _cleanup():
        base = os.path.join(skills_api.SKILLS_ROOT, "weather-skill", "scripts")
        for leftover in ("_tmp_new_helper.mjs", "_tmp_new_helper.mjs.bak", "geocode.py.bak"):
            p = os.path.join(base, leftover)
            if os.path.isfile(p):
                os.remove(p)
    _cleanup()

    # 1. 列表
    res = await skills_api.list_skills()
    names = [it["name"] for it in res["items"]]
    assert "weather-skill" in names, f"weather-skill 未出现在列表: {names}"
    wk = next(it for it in res["items"] if it["name"] == "weather-skill")
    print("list:", wk)
    assert wk["fileCount"] >= 5 and wk["referenceCount"] == 1 and wk["scriptCount"] == 2, wk

    # 2. 详情
    detail = await skills_api.get_skill("weather-skill")
    assert detail["skill"]["displayName"] == "weather-skill"
    assert detail["skillMd"].startswith("---"), "SKILL.md frontmatter 解析后原文缺失"
    dirs = {n["name"] for n in detail["tree"] if n["type"] == "dir"}
    files = {n["name"] for n in detail["tree"] if n["type"] == "file"}
    assert {"references", "scripts"} <= dirs, dirs
    assert {"SKILL.md", "README.md"} <= files, files
    print("detail dirs:", dirs, "files:", files)

    # 3. 读文件
    fr = await skills_api.read_skill_file("weather-skill", "references/clothing_guide.md")
    assert fr["content"], "文件内容为空"
    print("read ok, len =", len(fr["content"]))

    # 4. 写脚本文件（.py 脚本可编辑：改回原内容，验证成功路径 + 备份生成）
    script_fr = await skills_api.read_skill_file("weather-skill", "scripts/geocode.py")
    assert script_fr["content"], "脚本内容为空"

    class Payload:
        path = "scripts/geocode.py"
        content = script_fr["content"]
    wr = await skills_api.write_skill_file("weather-skill", Payload())
    assert wr["status"] == "success"
    bak = os.path.join(skills_api.SKILLS_ROOT, "weather-skill", "scripts", "geocode.py.bak")
    assert os.path.isfile(bak), "脚本备份文件未生成"
    os.remove(bak)  # 清理测试残留
    print("script write ok, backup created and cleaned")

    # 4.2 新建技能 + 生成 SKILL.md 骨架 + 同名冲突 + 非法名 + 删除整目录
    tmp_skill = "_tmp_test_skill"
    tmp_dir = os.path.join(skills_api.SKILLS_ROOT, tmp_skill)
    if os.path.isdir(tmp_dir):
        shutil.rmtree(tmp_dir)

    class CreatePayload:
        name = tmp_skill
    cr_skill = await skills_api.create_skill(CreatePayload())
    assert cr_skill["status"] == "success"
    skeleton = os.path.join(tmp_dir, "SKILL.md")
    assert os.path.isfile(skeleton), "新建技能未生成 SKILL.md"
    with open(skeleton, "r", encoding="utf-8") as f:
        md = f.read()
    assert md.startswith("---") and f"name: {tmp_skill}" in md, "SKILL.md 骨架缺少 frontmatter"
    # 新技能应出现在列表且详情可读
    res2 = await skills_api.list_skills()
    assert tmp_skill in [it["name"] for it in res2["items"]]
    detail2 = await skills_api.get_skill(tmp_skill)
    assert detail2["skillMd"].startswith("---")
    # 同名冲突
    try:
        await skills_api.create_skill(CreatePayload())
        raise AssertionError("同名技能应 409")
    except HTTPException as e:
        assert e.status_code == 409, e.status_code
    # 非法技能名
    for bad_name in ["../evil", "a/b", "..hidden", "中文名", ""]:
        class BadPayload:
            name = bad_name
        try:
            await skills_api.create_skill(BadPayload())
            raise AssertionError(f"非法技能名未被拦截: {bad_name!r}")
        except HTTPException as e:
            assert e.status_code == 400, (bad_name, e.status_code)
    # 删除技能（整目录）
    dr_skill = await skills_api.delete_skill(tmp_skill)
    assert dr_skill["status"] == "success"
    assert not os.path.exists(tmp_dir), "技能目录未被删除"
    # 删除不存在技能 404
    try:
        await skills_api.delete_skill(tmp_skill)
        raise AssertionError("删除不存在技能应 404")
    except HTTPException as e:
        assert e.status_code == 404, e.status_code
    print("create/delete skill ok (skeleton, list, conflict 409, bad names 400, rmtree, 404)")

    # 4.3 导出 / 导入 zip
    imported = "_tmp_imported_skill"
    imported_dir = os.path.join(skills_api.SKILLS_ROOT, imported)
    if os.path.isdir(imported_dir):
        shutil.rmtree(imported_dir)

    # 导出 weather-skill
    resp = await skills_api.export_skill("weather-skill")
    with zipfile.ZipFile(io.BytesIO(resp.body)) as zf_check:
        members = zf_check.namelist()
    assert any(m.startswith("weather-skill/") and m.endswith("SKILL.md") for m in members), members
    assert not any(m.endswith(".bak") for m in members), members
    print("export ok, members:", members)

    class FakeUpload:
        def __init__(self, filename, data):
            self.filename = filename
            self._data = data

        async def read(self):
            return self._data

    async def _import(data, name=None, overwrite=False):
        return await skills_api.import_skill(FakeUpload("pkg.zip", data), name=name, overwrite=overwrite)

    # 409：与现有技能同名且未勾选覆盖
    try:
        await _import(resp.body, name="weather-skill")
        raise AssertionError("同名导入应 409")
    except HTTPException as e:
        assert e.status_code == 409, e.status_code

    # 改名导入：把顶层目录重命名为 imported 后打包导入，内容完整还原
    buf2 = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(resp.body)) as zsrc, zipfile.ZipFile(buf2, "w") as zf2:
        for m in members:
            zf2.writestr(f"{imported}/{m[len('weather-skill/'):]}", zsrc.read(m))
    ir = await _import(buf2.getvalue())
    assert ir["status"] == "success" and ir["name"] == imported, ir
    assert os.path.isfile(os.path.join(imported_dir, "SKILL.md"))
    assert os.path.isfile(os.path.join(imported_dir, "scripts", "geocode.py"))
    # 导入的技能可正常读取详情
    d3 = await skills_api.get_skill(imported)
    assert d3["skillMd"].startswith("---")
    # 覆盖导入
    ir2 = await _import(buf2.getvalue(), name=imported, overwrite=True)
    assert ir2["status"] == "success"
    # 非法 zip / 空包 / 越界路径
    try:
        await _import(b"not a zip")
        raise AssertionError("非法 zip 应 400")
    except HTTPException as e:
        assert e.status_code == 400
    empty_buf = io.BytesIO()
    with zipfile.ZipFile(empty_buf, "w"):
        pass
    try:
        await _import(empty_buf.getvalue())
        raise AssertionError("空 zip 应 400")
    except HTTPException as e:
        assert e.status_code == 400
    evil_buf = io.BytesIO()
    with zipfile.ZipFile(evil_buf, "w") as zfe:
        zfe.writestr("evil/../../outside.txt", "x")
    try:
        await _import(evil_buf.getvalue(), name=imported)
        raise AssertionError("越界 zip 路径应 400")
    except HTTPException as e:
        assert e.status_code == 400
    assert not os.path.exists(os.path.join(skills_api.SKILLS_ROOT, "outside.txt"))
    # 清理导入的技能
    await skills_api.delete_skill(imported)
    assert not os.path.exists(imported_dir)
    print("import/export ok (zip roundtrip, rename, overwrite, 409/400 guards, cleanup)")

    # 4.5 新增文件（含子目录）+ 同名冲突 + 读回 + 清理
    class NewPayload:
        path = "scripts/_tmp_new_helper.mjs"  # 非常见白名单扩展名，验证启发式文本判定
        content = "// tmp test\n"
    cr = await skills_api.create_skill_file("weather-skill", NewPayload())
    assert cr["status"] == "success"
    try:
        await skills_api.create_skill_file("weather-skill", NewPayload())
        raise AssertionError("同名文件应 409")
    except HTTPException as e:
        assert e.status_code == 409, e.status_code
    back = await skills_api.read_skill_file("weather-skill", "scripts/_tmp_new_helper.mjs")
    assert back["content"] == "// tmp test\n"
    # 删除接口验证（同时清理本测试文件）
    dr = await skills_api.delete_skill_file("weather-skill", "scripts/_tmp_new_helper.mjs")
    assert dr["status"] == "success"
    assert not os.path.exists(os.path.join(skills_api.SKILLS_ROOT, "weather-skill", "scripts", "_tmp_new_helper.mjs"))
    try:
        await skills_api.delete_skill_file("weather-skill", "scripts/_tmp_new_helper.mjs")
        raise AssertionError("删除不存在文件应 404")
    except HTTPException as e:
        assert e.status_code == 404, e.status_code
    # 删除越界防护
    try:
        await skills_api.delete_skill_file("weather-skill", "../SKILL.md")
        raise AssertionError("越界删除应被拦截")
    except HTTPException as e:
        assert e.status_code in (400, 404), e.status_code
    print("create/delete file ok (mjs editable, conflict 409, read-back, delete + 404 + traversal blocked)")

    # 5. 路径穿越防护
    for bad in ["../../config.json", "SKILL.md/../../../etc/passwd", "/abs/path"]:
        try:
            await skills_api.read_skill_file("weather-skill", bad)
            raise AssertionError(f"越界路径未被拦截: {bad}")
        except HTTPException as e:
            assert e.status_code in (400, 404), e.status_code
    try:
        await skills_api.get_skill("..")
        raise AssertionError("非法技能名未被拦截")
    except HTTPException as e:
        assert e.status_code == 400
    print("path traversal blocked ok")

    # 6. 不存在的文件 / 技能
    try:
        await skills_api.read_skill_file("weather-skill", "nope.py")
        raise AssertionError("不存在文件应 404")
    except HTTPException as e:
        assert e.status_code == 404
    try:
        await skills_api.get_skill("not-exist-skill")
        raise AssertionError("不存在技能应 404")
    except HTTPException as e:
        assert e.status_code == 404
    print("404 handling ok")

    print("\nALL SKILLS_API TESTS PASSED ✅")


asyncio.run(main())
