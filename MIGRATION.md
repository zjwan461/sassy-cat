# 数据库 Migration 指南

本项目消息库（SQLite，用户数据目录下的 `messages.sqlite`）的表结构由 **Alembic** 管理，
初始化数据（seed）在迁移之后自动执行。应用启动时**完全自动升级**，用户无感。

- 迁移目录：`python/server/db/migrations/`
- 模型定义：`python/server/db/models.py`
- seed 模块：`python/server/db/seed.py`
- 运行时入口：`python/server/db/database.py` 的 `init_db()`
- 验证脚本：`tests/tmp_test_migration.py`（临时数据目录，不影响真实用户数据）

---

## 启动时发生了什么

```
init_db()
 ├─ 检测旧库？（无 alembic_version 表但有旧业务表）
 │     └─ 是 → alembic stamp 0001_initial（存量库标记基线，仅历史一次）
 ├─ alembic upgrade head（应用所有未应用的迁移：新表 / 改列 / 迁移内数据操作）
 ├─ 创建 SQLAlchemy 异步引擎与会话工厂
 └─ run_seeds()（幂等地铺底/维护初始化数据）
```

因此：**只需提交迁移文件 + seed 函数，下次启动自动生效，无需手工操作。**

---

## 场景 A：修改表 / 新增表（schema 变更）

### 第 1 步：改模型

在 `python/server/db/models.py` 中修改 SQLAlchemy 模型
（加列、改类型、删列、删表、新建表都在这里改）。

### 第 2 步：生成迁移脚本

在**仓库根目录**执行（CMD）。`SASSY_CAT_DATA_DIR` 指到一个空的临时目录，
autogenerate 需要一个"对比库"，**不要对着真实用户库跑**：

```bat
mkdir .tmp-miggen 2>nul & set SASSY_CAT_DATA_DIR=%CD%\.tmp-miggen & .venv\Scripts\python.exe -m alembic -c python/server/db/migrations/alembic.ini revision --autogenerate -m "add xxx column"
```

会在 `python/server/db/migrations/versions/` 下生成新迁移文件
（如 `0003_add_xxx_column.py`），`down_revision` 自动链到当前 head。

> 用完后记得删除 `.tmp-miggen` 目录。

### 第 3 步：人工审查生成的 SQL（必做）

autogenerate 在 SQLite 上有已知盲区，逐项检查：

| 检查项 | 说明 |
| --- | --- |
| 删列 / 改列类型 | 可能生成不出来或不可靠，需手写 `op.batch_alter_table(...)` |
| 索引 / 外键 | diff 是否完整（命名索引偶尔漏检） |
| 数据迁移 | 旧列数据拷贝到新列等，必须手写，autogenerate 不会生成 |
| downgrade | 确认能回滚（至少删掉新增的表/列） |
| NOT NULL 新列 | SQLite 必须走 batch 模式，否则 DDL 报错 |

改列/删列的正确写法示例：

```python
def upgrade() -> None:
    with op.batch_alter_table("messages") as batch:
        batch.add_column(sa.Column("new_col", sa.Text(), nullable=True))
        batch.drop_column("old_col")
```

### 第 4 步：验证

```bat
.venv\Scripts\python.exe tests\tmp_test_migration.py
```

该脚本覆盖三条路径：**全新库建表、旧库 stamp+升级、重启幂等**。
若迁移版本号断言（如 `0002_system_meta`）过期，同步更新脚本中的预期值。

### 第 5 步：提交

`models.py` + 新迁移文件**一起提交**。

> ⚠️ 迁移文件一旦合并/发布，**永远不要再修改**它——要改结构就追加新迁移。
> 已升级过的库不会重跑旧迁移，改了也不会生效，只会造成新老环境不一致。

---

## 场景 B：铺底数据（seed）

初始化/常驻维护的数据写在 `python/server/db/seed.py`：

1. 新增 `async def seed_xxx()` 函数，**必须幂等**——先查再插或 upsert，
   参考现有的 `seed_system_meta()` 写法。
2. 把函数追加到 `run_seeds()` 的 `seeds` 列表，**列表顺序即执行顺序**
   （有数据依赖的放后面）。

注意事项：

- 单个 seed 失败只记 error、不阻断启动（`run_seeds` 已做隔离）。
- seed 用异步会话 `get_session()`，写完**必须显式 `await session.commit()`**
  （项目惯例，session 退出不自动提交）。

### 迁移 vs seed 怎么选？

| | 放迁移 `upgrade()` | 放 seed |
| --- | --- | --- |
| 典型场景 | 建表时灌入的固定数据、结构变更伴生的数据搬迁 | 需要随版本刷新/校正的键值、默认配置 |
| 执行次数 | 仅一次（随版本号） | 每次启动都执行（要求幂等） |
| 实现方式 | `op.bulk_insert(table, rows)` | async 函数 + ORM |

**经验法则：结构相关的固定数据放迁移；需要长期维护/刷新的数据放 seed。**

---

## 常见问题

### 存量老用户升级会不会报错？

不会。老库（由 `create_all` 建出、无 `alembic_version` 表）启动时会被自动
`stamp` 到基线版本 `0001_initial`（见 `database.py` 的
`_LEGACY_BASELINE_REVISION`），之后的迁移正常增量执行，数据不丢。

### `alembic.ini` 为什么不能写中文？

configparser 按系统默认编码（Windows 为 GBK）读取该文件，含中文注释会直接
`UnicodeDecodeError` 崩溃。**该文件保持 ASCII-only**，注释写在 `env.py` 里。

### 命令行手动查看/操作迁移（可选）

```bat
set SASSY_CAT_DATA_DIR=%APPDATA%\sassy-cat
.venv\Scripts\python.exe -m alembic -c python/server/db/migrations/alembic.ini current
.venv\Scripts\python.exe -m alembic -c python/server/db/migrations/alembic.ini history
.venv\Scripts\python.exe -m alembic -c python/server/db/migrations/alembic.ini heads
```

> 谨慎使用 `downgrade`：SQLite 上回滚不一定安全，且**生产环境不做 downgrade**，
> 出问题用新迁移向前修复（forward-fix）。

### 新增一张表的完整清单

1. `models.py` 加模型类
2. `alembic revision -m "add xxx table"`（手工写迁移，或 autogenerate 后审查）
3. 迁移 `upgrade()` 里 `op.create_table(...)` + 需要则 `op.create_index(...)`
4. `downgrade()` 里对应 `op.drop_index` + `op.drop_table`
5. 如需铺底数据：迁移里 `bulk_insert` 或 seed.py 加函数
6. 跑 `tests/tmp_test_migration.py` 验证后一起提交
