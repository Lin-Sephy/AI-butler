# Web App 迁移方案 v0.1

> 2026-04-07 Sephy + 小克制定

## 一句话目标

把小管家从 Streamlit 迁移到 FastAPI + React，解决 Streamlit 的界面限制和部署问题。

## 技术栈

| 组件 | 技术选型 | 说明 |
|------|----------|------|
| 后端 | FastAPI（Python） | REST API，复用现有 core/、db/、prompts/ |
| 前端 | React | 替代 Streamlit 界面 |
| 数据库 | Supabase（PostgreSQL） | 已创建项目，直接用云数据库 |
| AI 模型 | DeepSeek V3.2 | 不变 |

## 现有代码评估

**可以直接复用的（不改或只做小修）：**
- `core/energy.py` — 精力系统，无外部依赖
- `core/intent.py` — DeepSeek 调用，清理 3 个 legacy 函数（call_ai、get_system_prompt、build_user_message）
- `core/rules_engine.py` — 纯 Python 规则引擎，无外部依赖
- `core/task_manager.py` — 任务状态流转，依赖 db
- `core/memory.py` — 记忆系统，依赖 db + DeepSeek
- `db/database.py` — SQLite CRUD，需重写为 Supabase 客户端调用
- `prompts/system_prompt.py` — prompt 模板，无外部依赖

**需要改的：**
- `config.py` — 去掉 streamlit import，改为纯 .env 读取
- `app.py` — 整个替换为 FastAPI 应用

## 开发计划

### 第一步：后端骨架

**小克做：**
- 改 config.py，去掉 streamlit 依赖，加入 Supabase 配置
- 清理 intent.py、prompts/ 里的 legacy 兼容函数
- 重写 db/database.py，从 SQLite 迁移到 Supabase
- 在 Supabase 建表（复用现有 6 张表的结构）
- 建 FastAPI 应用，把 app.py 的业务流程拆成 REST API

**Sephy 做：** 无

**完成标志：** Sephy 在浏览器打开 `http://localhost:8000/docs` 能看到 API 文档页面

**讨论节点：** Sephy 确认后端跑通，再进入第二步

---

### 第二步：前端聊天主界面

**小克做：**
- 创建 React 项目
- 实现聊天界面：消息列表、输入框、记录/再聊聊按钮
- 先按现有布局搭（左侧栏 + 右侧聊天区）

**Sephy 做：** 看实际界面效果，给出设计方向

**完成标志：** Sephy 在浏览器打开能跟小白正常聊天

**讨论节点：** 界面布局、风格、移动端优先级。Sephy 拿着实物决定设计方向

---

### 第三步：补完侧边栏功能

**小克做：**
- 精力系统（档位显示 + 手动调整）
- 任务栏（进行中/待完成/已完成/预定任务）
- 循环任务管理（添加/删除每日任务）
- 记忆库（手记 + AI 记忆显示/清空）
- 人格选择（INFP/INTJ/INTP）

**Sephy 做：** 确认哪些功能原样迁移、哪些趁机重新设计

**讨论节点：** 第三步开始前讨论，避免做完才发现方向不对

---

### 第四步：部署

**Sephy 需要注册的账号：**

| 平台 | 用途 | 怎么注册 | 什么时候注册 |
|------|------|----------|-------------|
| Vercel (vercel.com) | 托管 React 前端 | 用 GitHub 账号登录即可 | 第三步做完后 |
| Render (render.com) | 托管 FastAPI 后端 | 用 GitHub 账号登录即可 | 第三步做完后 |
| Supabase (supabase.com) | 云数据库 | ✅ 已注册，项目已创建（Mumbai 区域） | — |

**小克做：** 配置部署流程、写部署文档

**Sephy 做：** 注册上述账号（都支持 GitHub 一键登录，不需要额外操作）

**讨论节点：** 部署平台确认（如果 Sephy 有其他偏好的平台）

---

## 不在这次范围内

- Prompt 优化（独立方向，不混在迁移里）
- 新功能开发（先保证现有功能完整迁移）

## 已知需要顺手清理的（不单独做，迁移过程中处理）

| 问题 | 位置 | 说明 |
|------|------|------|
| streamlit import | config.py | 迁移阻断点，第一步处理 |
| SQLite → Supabase | db/database.py | 整个重写，第一步处理 |
| 3 个 legacy 函数 | intent.py、prompts/ | 无调用，删掉 |
| 无连接池 | db/database.py | Supabase 客户端自带，迁移后自动解决 |
| 未使用的数据库字段 | energy_log、user_profile | sleep_hours、state_tags、avg_energy_7d |
