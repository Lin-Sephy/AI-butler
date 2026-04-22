# AI-butler

AI 身体状态计划管家——通过陪伴式问答判断用户今天真实可用状态，并给出合适行动路径的 AI 小管家。

- **当前方向：** Web App v2（三页极简 + 白鼬桌宠 + 雪地）。设计见 `docs/plan.md`
- **开发文档入口：** `CLAUDE.md`（业务架构 + 工作规则）+ `docs/plan.md`（产品方向）

---

## 怎么跑起来

### v2 前端（开发模式）

```
cd frontend
npm install
npm run dev
```

浏览器访问 `http://localhost:5173`。

### 后端 API

- **SQL 变更**（表结构 / RLS 策略）→ Supabase Dashboard 的 SQL Editor 粘贴执行
- **API 代码改动**（`api.py` / `core/`）→ 改完推到 Render 验证，或配合前端 dev server 连远端 API

---

## 目录速览

- `api.py` — FastAPI 应用主入口
- `frontend/` — React + Vite 骨架（v2 前端）
- `core/` — 业务逻辑模块
- `db/database.py` — 数据访问层
- `prompts/` — 双 prompt 模板
- `docs/` — 产品文档 + 决定归档 + 参考素材
- `anchor_memory_lib/` / `anchor_db/` — ANCHOR 记忆系统
- `tests/` — 后端单元测试
