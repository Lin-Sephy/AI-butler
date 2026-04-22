# AI 身体状态计划管家 — Web App 产品设计 v2

> 2026-04-14 下午，Sephy + 小克重写。
> 基础来自 2026-04-13 的 v1.2（三页结构+极简方向），在此之上补齐多用户、视觉方向、形象、冷启动等结构性决定。
> 旧版本归档在 `docs/decisions/`（v0.1 纯后端迁移 / v1.0 像素空间 / v1.1 推翻过程）。

---

## 一句话定义

**极简专注工具 + 一个了解你的 AI 陪伴。** 打开能立刻开始专注，聊天中积累关系。

---

## 核心产品原则

1. **打开能立刻开始专注。** 任何横在中间的东西都要问一遍"必要吗"。
2. **AI 陪伴是差异化，不是装饰。** 聊天室是一等公民，不是隐藏在二级入口。
3. **小白是陪伴锚点，不是游戏元素。** 存在但不要求操作。
4. **片面信息比没信息更危险。** 不预填、不问问卷；小白对新用户保持空白，靠自然对话攒记忆。
5. **从第一步就输了怎么谈以后。** —— Sephy

---

## 差异化 & 壁垒（从 v1.0 抢救回来的思考）

市面上的专注软件（番茄 3亿 / Forest 1亿 / 异星专注 10万）有游戏化但没 AI 陪伴；AI 聊天产品有陪伴但没专注场景。这个产品把两者拼起来，**但保持极简——游戏化是 v1.0 证伪的陷阱**。

**壁垒：AI 对用户的了解不可转移。** 用户跟小白聊出来的人设、记忆、节律感，沉淀在产品里——换 app 就换了。这是比界面漂亮更结实的差异化。

---

## 页面结构：四页 Tab

### 页面 1：任务面板（默认首页）

- 今日任务列表
- 手动新建任务按钮
- **循环任务管理**入口（添加 / 删除）
- 点击任务 → 全屏专注遮罩
- **小白不出现**（保持工具感）
- 背景：冷雪白（全局统一底色）

**为什么默认这个：** 打开 → 看到任务 → 一键开始。最短路径，跟番茄 todo 打开即用对齐。

### 页面 2：小白聊天室

- AI 聊天界面（沿用 Streamlit MVP 已验证的体验）
- **双 mode 设计**：默认进入是"闲玩 mode"（白鼬全身居中、点身体逗状态、无消息流），用户发送第一条消息切入"聊天 mode"（白鼬半身趴聊天框上沿、消息流复现）—— 详见 `docs/桌宠设计.md` "聊天页双 mode layout" 章节
- 背景：冷雪白底 + 极淡针叶树剪影水印暗纹 + 缓慢落雪效果（两个 mode 共用）
- AI 识别任务意图 → 弹"记录/再聊聊"按钮 → 用户同意 → 任务写入页面 1
- **聊天相关设置入口**（右上角 ⚙️）：人格选择 / 自粘贴性格 / 小白命名 / 用户手记 / AI 自动记忆查看清空 / **API key**（与"我的"页共享同一份配置）

### 页面 3：数据统计

- 今日任务时间环形图
- 本周专注时间累计
- **小白不出现**
- 背景：冷雪白（全局统一底色）

### 页面 4：我的（账号 + API key 集中地）

- **账号 / 邮箱绑定**（多用户：Supabase Anonymous → 绑邮箱防丢数据）
- **API key**（与聊天页 ⚙️ 共享同一份配置，BYOK Bring Your Own Key——v2 上线前补，开发期占位禁用）
- 关于 / 版本

**为什么单独成 tab：** 账号和 API key 是产品级配置，跟具体使用场景无关；聊天偏好（人格/性格/记忆）就近放聊天页 ⚙️，使用动线不绕。

### 导航

底部 Tab，四个图标：**任务 / 聊天 / 数据 / 我的**。

### 任务流转

```
聊天室识别任务      用户手动新建
    ↓                  ↓
 用户同意            任务入列
    ↓                  ↓
    └────── 页面 1 任务列表 ──────┘
                   ↓
             用户点"开始"
                   ↓
         全屏专注遮罩 + 桌宠小白
                   ↓
              完成 / 中断
                   ↓
              记录到数据页
```

---

## 专注遮罩（页面 1 的全屏覆盖）

- 全屏盖住任务列表
- 计时器（正/倒计时可切换）
- 白噪音开关
- 结束按钮
- **桌宠小白在角落**：SVG 白鼬 + 极简雪地氛围（针叶树剪影 + 落雪）
- 结束后遮罩消失，回任务列表

（桌宠具体行为——眨眼频率、待机动作、专注时要不要动——待 #3 剩余部分讨论后补。）

---

## 视觉方向

### 路径：SVG 矢量 + CSS 动画

**不是像素风。** 走现代温馨插画族群（Headspace / Apple Journal / Duolingo 气质），跟像素风（Stardew Valley 气质）区分开。

**决策理由：**
- 像素路径小白 + 现代任务面板会打架；SVG 路径全局视觉语言统一
- SVG 工作量比像素低一个量级（单 SVG + CSS keyframes，不用画每一帧）
- SVG 流线曲线最适合表现白鼬身形

**放弃的：** Sprout Lands 像素素材作为角色主视觉；仅保留它作为装饰图标级别的纹理参考。

### 配色：雪地+松林，不做"温暖壁炉"路线

**内核：不催促、允许慢下来的林间雪地感**。专注 app 赛道里没人用这个调，辨识度高，跟白鼬黑尾尖形成角色与 UI 色系的一体化。

| 层 | 颜色 | 用处 |
|---|---|---|
| 底色（全局统一） | 冷雪白（#F4F7FA 或 #EEF2F5 附近） | 所有页面背景 |
| 主色 | 松针深绿（#2D4A3E 附近） | 重点按钮、导航高亮、数据主线 |
| 辅色 | 浅苔绿（#8BA77E 附近） | 次要信息、进度条、标签底 |
| 点缀 | 黑（#1A1A1A） | 关键文字、图标、白鼬黑尾尖呼应 |

**避免"太单一"的五个技巧（原型里变成滑杆）：**
1. 多层白（纯雪白 / 乳白 / 偏蓝冷白三层）
2. 多层绿（深松针 / 中苔绿 / 浅灰绿按信息重要性递减）
3. 纹理点缀（任务卡片底极淡纸纹或雪粒纹，不是装饰图案）
4. 细线勾勒（手绘钢笔感细分隔线，不是粗描边，带"插画书页"感）
5. 雪地暗纹（陪伴区背景极淡的针叶树剪影水印）

### 其他锚点

1. **圆角：** 16-20px，呼应白鼬流线身形（12px 硬圆会破坏气质）
2. **字体数字：** 待定——衬线体（Fraunces/Cormorant 冷峻版）或细线 sans（Inter Thin / IBM Plex Light），两个都搭但调性不同，做原型时都给 Sephy 看
3. **过渡：** 300-400ms ease-out，雪地慢节奏
4. **空状态文案：** 句子不短语（"今天还没给自己安排点什么呢" 不写"暂无任务"）

### 落地方式：HTML 可交互原型调参

做前端第一步之前先做一个 `prototype.html`——单页 HTML，左半渲染核心元素，右半滑杆面板。Sephy 浏览器拖拽调参，不用学工具。调完右上角"导出 design tokens JSON"按钮下载一份，小克解析成 React design tokens。

**滑杆参数（都做成 HSL 三轴 + 数值 input 双模式）：**
- 底色 / 主色 / 辅色 / 点缀色（四个独立组，每组 H + S + L 各一条）
- 圆角半径（0-24px）
- 过渡时长（100-600ms）
- 阴影 blur（0-20px）+ 阴影 opacity（0-0.3）
- 正文字重（100-900）
- 字体族（下拉：Inter / Fraunces / IBM Plex Serif / Cormorant / 系统默认）
- 行距（1.2-2.0）
- 纸纹强度 / 针叶树暗纹强度（各一条 0-1 opacity）

**要渲染的核心元素（一页展示）：**
- 任务卡（标题 + 时间 + 状态 icon + 两个操作按钮）
- 主按钮 + 次按钮
- 聊天气泡（用户侧 + 小白侧两种）
- 计时器数字（大号，用于专注遮罩）
- 空状态（带句子文案："今天还没给自己安排点什么呢"）
- Tab 导航（底部三图标）
- 输入框 + 分隔线

**不走 `frontend-design` skill**——那个 skill 做成品 UI，我们要的是调参工具。直接手写最简 HTML + Vanilla JS 即可。

---

## 小白形象：冬毛白鼬 + 雪地

### 形象

- **冬毛白鼬**：纯白身 + 黑眼睛 + 黑尾尖 + 粉色小鼻子
- 锁定"冬毛"不做季节切换（产品视觉稳定）
- "小白"这个名字是 Streamlit MVP 留下的情感资产，字面就是白色的白鼬，形名一致

### 为什么白鼬（不是寄居蟹/水豚/其他）

- **人养**的真实感（雪貂家族是宠物）
- 动作带宽大：站立偷看、拱背、蜷球、钻洞——SVG 贝塞尔曲线表现流线身形最到位
- "小白"字面匹配（冬毛本来就是白）
- 没有"换壳"这种天然游戏化机制——反而更符合极简原则

### 雪地背景

- 解决纯白在米白底上对比度弱的问题
- "温馨"的天然载体：雪地 + 屋内暖光 + 小白鼬
- 只在**聊天室**和**专注遮罩**出现；任务页/数据页保持纯米白，不铺雪地

### 桌宠行为（待定）

- 核心状态目标 10-15 个：idle / 聊天 / 思考 / 开心 / 困倦 / 睡觉 / 伸懒腰 / 抬头看 等
- 眨眼频率、待机小动作、专注中要不要动——待 #3 剩余部分讨论

### 参考 Clawd 源码（在 `C:/Users/Administrator/Desktop/clawd-on-desk/`）

**只参考代码 + 技法，不碰视觉资产**（Anthropic 吉祥物，授权风险）。
- 状态机设计（`src/state.js` 的优先级驱动）
- SVG + CSS @keyframes 动画模式
- "存在但不抢戏"的桌宠设计哲学

### 点缀物件（围巾/坐垫）

第一版**不做**。留作未来换装系统的种子（温和彩蛋，不是菜地格子那种游戏化）。

---

## 多用户

### 身份：Supabase Anonymous Auth

- 用户首次打开 → 后端自动发 JWT + 在 `auth.users` 建匿名记录
- 从第一天起就是正式 user_id，所有数据挂在它下面
- 未来绑定邮箱：一行 `updateUser({ email })` → 同一 user_id 上绑，**数据零迁移**

**对比被否的方案：**
- Magic Link 开屏登录 —— 违反"打开即用"
- localStorage 土法匿名 id —— 以后加邮箱登录要写迁移脚本，有丢数据风险

### 数据隔离：Supabase RLS

- 所有表开行级安全（RLS），自动按 user_id 过滤
- 现有后端代码（单用户 MVP 的遗产）要逐个 API 检查加 user_id 条件：聊天 / 任务 / 精力 / 记忆

### 绑定邮箱入口

- 设置页"绑定邮箱（防止换设备丢失）"入口，冷静克制
- 可以**最多**弹一条温和提示（不骚扰）
- "用户不登录丢数据不关我们事"——Sephy 原话，作为产品边界

### 前端：Auth Context

- 用 `@supabase/supabase-js` 官方 SDK
- 全局 context 管理登录态 + token 自动刷新
- 未登录（浏览器首次）→ 自动走匿名注册流程，用户无感

---

## 冷启动：不预填

新用户第一次打开 **不弹自我介绍问卷**、不问名字职业目标。

**理由：** 提前给 AI 简略信息会让 AI "问问问"（追着那条线索）或陷入模板化。例：用户说自己在考研，小白会永远往考研偏，但用户开场可能根本不想聊。

**怎么做：** 小白初始空白，靠对话自然攒记忆（现有记忆系统已做这件事）。

---

## 时间盘子：十多天（80-120h）

预算分配（粗估）：

| 模块 | 工时 |
|---|---|
| 骨架三页 Tab + 全屏专注遮罩 | ~20h |
| 多用户 + Supabase Anonymous Auth + RLS | ~10h |
| 聊天室接现有 API + 任务记录回写 | ~15h |
| 白鼬桌宠（2 张新 SVG + 6 state 状态机 + CSS 动画） | 5-8h |
| 视觉 HTML 原型 + 调参 → design tokens | ~10h |
| 数据页 + 打磨 + 部署 | ~15h |
| **合计** | **75-78h** |

桌宠从 11 状态砍到 6 state 后节省约 10-17h，从盘子上沿退下来留了点缓冲。加任何新东西前先看这个缓冲够不够。

---

## 开发顺序

### 第 0 步：视觉 HTML 原型 + 多用户改造 ✅ 完成（2026-04-15）

- ✅ **prototype.html + design tokens 定稿** —— v1 淡蓝紫雪地，落地到 `frontend/src/design-tokens.css`，备份在 `docs/references/白鼬/tokens_候选v1_淡蓝紫雪地_选中.json`
- ✅ **后端改造完成** —— Supabase 新项目 `ieakiihfsaqqyyjdyjtt` 跑过 `db/migration_v2.sql`（6 表带 user_id + RLS + handle_new_user trigger）；`db/database.py` / `core/task_manager.py` / `core/memory.py` / `core/energy.py` / `api.py` 全部 user_id 化；新建 `core/auth.py` 用 PyJWT 验 Supabase ES256 JWT
- ✅ **前端骨架完成** —— React + Vite + `@supabase/supabase-js`，AuthContext 自动匿名登录，apiFetch 封装 JWT header，4 tab 占位 App
- ✅ **Render 部署后端** —— `https://ai-butler-1sp8.onrender.com`（Singapore，free tier）
- ✅ **端到端联通验证通过** —— 浏览器→匿名登录→JWT→Render→JWKS 验签→user_id→Supabase REST→`{"tasks":[]}` 返回

### 第 0.5 步：代码瘦身 + 单测基建 ✅ 完成（2026-04-16）

- ✅ **后端 simplify**（commit `df04880`）—— `db/database.py` 抽 `_get_profile_field/_set_profile_field` helper；`task_manager` 合并 `start_idle_task/start_scheduled_task` → `start_task(allowed_from=...)`；`memory` 抽 `_maybe_promote`；`auth.py` 删 HS256；清死代码
- ✅ **L1 纯逻辑单测** —— `tests/test_rules_engine.py` + `tests/test_memory.py`（pytest）；L1/L2 边界与"不写清单"写入 memory `feedback_testing_strategy.md`

### 第 1 步：页面 1 + 专注遮罩 ✅ 完成（2026-04-16，commit `300f0e1`）

- ✅ **TasksPage** —— 列任务（执行中→暂停→待完成排序）+ 已完成折叠 + 空状态文案
- ✅ **TaskCard** —— 5 状态视觉（dot/chip/操作按钮按状态分发）+ executing 左 3px 蓝边强调
- ✅ **NewTaskModal** —— 关键词 + 时长快选 [25/35/45/60/90/120] + 自填 + work/rest
- ✅ **FocusOverlay** —— 倒计时/正计时 + 暂停/完成/放弃 + 雪地针叶背景 + 白噪音/桌宠占位
- ✅ **视觉细调** —— 砍掉浮动 FAB 改 inline "+ 新建任务" 按钮长在列表末尾；placeholder 改 "给自己安排点什么"；全局去 italic（feedback memory 钉死）

**完成标志达成：** 打开 → 加任务 → 开始专注 → 结束，闭环跑通 ✅

### 第 2 步：页面 2 聊天室

#### 2a 已完成（commit `b76017e`）
- ✅ ChatContext + chatApi（小克2）—— send/record/dismissRec/resetSession + localStorage 跨刷新
- ✅ ChatPage 漫画气泡布局（白鼬永远居中超大 / 顶气泡小白带泡尾 / 底气泡用户右对齐堆叠 + opacity 渐弱 / 任务推荐按钮独立行 / 历史视图 📃 切到传统列表 / thinking 时藏旧气泡突出 3 点泡泡）
- ✅ 接入 FastAPI 聊天 API（/api/chat → reply + signal + task_recommendation 全链路通）
- ✅ 第一版 SVG（站立全身01 + 歪头03）已替换为更精修版（1歪头 / 2-3 思考侧脸正脸 / 4 思考侧脸半身）

#### 2b 已完成（2026-04-21/22，一系列小 commit）

- ✅ **聊天页 ⚙️ 设置面板**——`SettingsPanel.jsx` 六区块：小白命名 / 性格（`PersonaPresets` 子组件：预设 1/2/3 + 自定义 textarea） / 日常作息 / 用户手记 / AI 记忆（只读 + 清空） / API key（真 BYOK）
- ✅ **MBTI UX 改版**——前端按钮改"预设 1/2/3 + 摘要词"，避免用户改完 textarea 后按钮名称骗人；后端 `PERSONAS` 字典仍然保留 infp/intj/intp 作为 key
- ✅ **模式切换 UI (`ModeToggle`)**——顶栏"闲聊 ↔ 任务" toggle，mode 持久化到 localStorage（防 HMR 重载回退）；切换瞬间顶部飘一条胶囊提示 `ModeHintBanner`
- ✅ **v5 function calling 工具扩展**——`core/plan_tools.py` 加 `delete_tasks`（批量） + `create_tasks`（批量写入）+ `delete_task`（单条）；`intent.py` call_chat 的 `MAX_TOOL_ROUNDS` 从 5 提到 15，收集 tool 结果回传给前端
- ✅ **`PlanConfirmModal` P2 版**——原 P1 的 `/api/plan/extract` 流程整个砍掉，改成 DS 直接调 create_tasks 写库 → 前端拿到 `created_tasks` 后弹窗让用户"事后编辑"（改 keyword / 改时长 / 删）；后端加 `POST /api/task/{id}/keyword` 端点
- ✅ **HONESTY_RULES + MODE_SWITCH_HINT**——prompt 加硬约束防幻觉 + 闲聊模式下提到调整任务自动提示切计划模式
- ✅ **性能链路优化**——`db.database` 用 `httpx.Client` 持久连接复用 TLS（首次握手后后续 20-50ms）+ 3 次重试；`/api/chat` 的 Supabase 调用从 8 次砍到 4 次（`get_full_profile` 一次 SELECT \* + 砍 `get_current_energy` + 砍 `_build_task_board_text`）
- ✅ **前端 apiFetch 幂等重试**——GET 请求遇网络错/5xx 自动重试 2 次（500ms 间隔），POST/PUT/DELETE 不重试避免副作用
- ✅ **BYOK 前后端已通**——`LlmConfig.jsx` 子组件（5 预设 provider：DeepSeek / OpenAI / 智谱 / 硅基流动 / 其他）+ 后端 `/api/profile/llm` GET/PUT/DELETE + `db/migration_byok.sql` 加 4 字段 + `intent.py` `_get_client(user_llm)` 支持回退

#### 2 剩余待办
- ⏳ **手机端拉窄实测** —— Sephy 还没在真手机/devtools 模拟器上看，确认气泡/白鼬/堆叠在 iPhone 12 Pro 宽度（390px）下不挤不溢
- ⏳ **聊天记任务 → 任务页即刻刷新** —— ChatContext 已暴露 `lastCreatedTasks`，弹窗编辑体验有了；但 TasksPage 本身仍需切 tab 重 mount 才 fetch。apiFetch 加了自动重试后偶发 fail 大幅缓解，仍未做"主动广播刷新"
- ⏳ **state machine 接入新 SVG** —— 当前只用 stoat-standing；listening 时该换 1歪头，thinking 时换 2/4 思考侧脸（半身/全身按场景）。Step 3 整体状态机时统一接

**完成标志：** 聊天推任务 → 页面 1 看到 → 开始专注，全链路闭环

### 第 3 步：白鼬桌宠状态机（极简版）

- 2 张新 SVG 由 Sephy 画：sleeping（眼睛可 CSS 切换）+ happy（= 跳起来）
- 状态机 6 state（idle / listening / thinking / sleeping / focus-glance / happy），接入现有 front/side/side-half + 2 张新画，结构参考 Clawd `src/state.js`
- 微动作（blink / sleeping 眼睛睁闭）纯 CSS，不加 SVG
- 聊天室完整展示 / 专注遮罩角落桌宠两种形态；场景切换用 opacity fade（不走 intro）
- 详见 `docs/桌宠设计.md`

### 第 4 步：页面 3 数据统计 + 页面 4 我的

- 今日环形图 + 本周累计
- "我的"页骨架：账号 / API key 占位禁用 / 关于版本

### 第 5 步：打磨 + 部署

- 移动端适配
- 精力系统 UI 接入 ~~← v5.0 砍了，不做~~
- ✅ **BYOK API key 真实接入**（2026-04-22 完成）——user_profile 加 4 字段（provider / base_url / model / api_key）+ 后端 GET/PUT/DELETE `/api/profile/llm` + 前端 `LlmConfig.jsx` 5 预设 provider + `intent.py` 按用户配置切 client；**Supabase SQL migration 需要手动跑 `db/migration_byok.sql`**；api key 明文存 Supabase（上线前加密待做）；无 key 自动回退服务端默认 DeepSeek
- Vercel + Render 部署

---

## 上线前必做清单（2026-04-22 整理）

代码侧 v5 清理 + 修复已在 commit `0be2f29`→`1d0b702` 五连推完成，剩下**运维侧的人类动作**：

### 1. BYOK 落地（最关键·另一个小克推进中）
- 后端：`user_profile.deepseek_api_key` 字段已建，`core/intent.py:call_chat` 已支持 `user_llm` 参数按需替换 DS 调用
- 前端：`LlmConfig.jsx` 组件已建，`SettingsPanel` 接上
- **未完成：** 强制 BYOK 检查——目前无 key 回退共享 key，任何人拿 URL 注册就烧我们的账单。BYOK 就位前**只能给内测熟人用**，不广发
- 完成后：Render 环境变量可以考虑删 `DEEPSEEK_API_KEY`，强制 BYOK

### 2. Render 环境变量加 `ALLOWED_ORIGINS`
- 前端部署到 Vercel 拿到域名后（比如 `https://ai-butler-xxx.vercel.app`），在 Render Dashboard → Settings → Environment 加：
  ```
  ALLOWED_ORIGINS=https://ai-butler-xxx.vercel.app
  ```
- 多个前端域名用逗号分隔（自己的测试域名也加进去）
- 不加的话后端退回 `*` 放行，能跑但不安全

### 3. 前端部署到 Vercel
- `frontend/.env.local` 本地填：
  - `VITE_SUPABASE_URL=https://ieakiihfsaqqyyjdyjtt.supabase.co`
  - `VITE_SUPABASE_ANON_KEY=<anon key>`
  - `VITE_API_BASE_URL=https://ai-butler-1sp8.onrender.com`
- Vercel 项目 Settings → Environment Variables 同步这三条（Production + Preview 都配）
- 部署后把 Vercel 给的域名填回 Render 的 `ALLOWED_ORIGINS`（见 #2）

### 4. 跑一次 L2 smoke 验证
- Render auto-deploy 完 + 前端部署完 + 环境变量配好后，本地跑：
  ```
  python scripts/smoke.py
  ```
- 10 步闭环：匿名登录 → 任务面板 → 聊天 → 手建任务 → 完成 → 计划模式触发 DS create_tasks → 清理
- Step 8-10（plan mode）DS 不一定每次都调 create_tasks——看 log 判断 function calling 链路是否通

### 5. 观察事项（非阻塞，上线后盯一阵）
- **MODE_SWITCH_HINT prompt 是否起作用**：闲聊模式下提到排计划时，DS 是否会顺口提"要不要切计划模式"。漏了或过度触发 → 调整 prompt
- **MAX_TOOL_ROUNDS = 15 是否够**：极端情况 DS 陷循环调同一工具会烧 15 次 API。看日志里有没有 `function calling 超过 15 轮未收敛` warning

---

## v5.0 前端对接（后端由小克做，前端待做）

背景：2026-04-20 prompt + 产品架构重构，详见 `docs/ds多版本prompt对比/2026-04-20_v5.0_开工文档.md`。以下是前端需要配合的改动：

### 聊天页 ✅ 全部完成（2026-04-22）

- ✅ **模式切换 UI（`ModeToggle`）**：header 左侧"闲聊 ↔ 任务" toggle，mode 持久化 localStorage（防 HMR/刷新回退）；切换时顶部胶囊提示"小白切换到任务模式了"
- ✅ **ChatRequest 去掉 `persona` 字段**：v5.0 架构落地
- ✅ **ChatRequest 加 `mode` 字段**：`"chat"` 或 `"plan"`
- ✅ **计划确认界面（改成 P2 版）**：从 P1（DS confirmed → 前端调 `/api/plan/extract` 提取 → 用户审核后批量写库）改成 **P2（DS 直接调 `create_tasks` 工具写库 → 前端 `PlanConfirmModal` 弹窗给用户事后编辑）**。`/api/plan/extract` 整个砍了，改由 `core/plan_tools.py` 的 function calling 工具直接动数据库；弹窗从"批量确认记录"改成单条改名 / 改时长 / 删除（各自独立端点）

### 设置页 ⚙️ ✅ 全部完成（2026-04-21/22）

- ✅ **性格选择 UX 改版（`PersonaPresets`）**：MBTI 按钮改成"预设 1/2/3 + 摘要词"（共情陪伴 / 高效拆解 / 观察点破）——避免用户改完 textarea 后按钮名称骗人。点按钮填 custom_persona；非空时覆盖弹 confirm。后端 `PERSONAS` 字典保留 infp/intj/intp 作为 key
- ✅ 小白命名输入框
- ✅ 用户手记输入框（新加后端 `USER_MEMO_MAX_LENGTH = 2000` 校验 + GET 返回 max_length）
- ✅ AI 自动记忆查看 / 清空
- ✅ 日常作息输入框（`user_profile.daily_routine`）
- ✅ **API key 真 BYOK（`LlmConfig.jsx`）**：5 预设 provider（DeepSeek / OpenAI / 智谱 / 硅基流动 / 其他），切 provider 自动填 base_url + model 候选；api_key 掩码回显；独立保存/清空按钮——详见第 5 步

### 项目管理入口（v5 核心不依赖，前端延后）

- ⏳ 新页/新 Tab 或设置页子项：列项目、建项目、编辑摘要、看关联任务
- ⏳ 建任务 keyword 自动匹配 project keywords
- 后端项目 CRUD 已有（`/api/projects` 全套）+ `query_project` function 已注册，DS 能查；前端 UI 待做

### 数据统计页（第 4 页）

- ⏳ 复用后端 `/api/tasks/recent?days=7` 和 `/api/stats`（和计划模式喂 DS 共用）
- 今日环形图 + 本周累计

### 精力系统 UI

- ❌ **v5.0 砍了**，不再做精力档位选择、偏差检测、快捷确认按钮等任何精力 UI

### v5.1 方向（2026-04-21 测试 v5 时新发现，backlog）

- ⏳ **时间轴视图（对标"精力快充"01 图）**：任务页加时间轴模式——左侧时间刻度 + 右侧按 scheduled_at 排列的时间段卡片。见 `docs/references/竞品/精力快充/01_精力时间轴_时间栏下拉.jpg`
- ⏳ **`/api/task/record` 扩展接收 `scheduled_at` 和 `project_id`**（后端，前置依赖）：现在 record 端点只接 keyword/minutes/task_type，计划模式提取出的开始时间和项目归属写不进去；时间轴视图必须要先把 scheduled_at 能落库

### 上线后运维（backlog，非核心，等测完 v5 功能再评估）

- ⏳ **Render 冷启动防护**：免费版 15 分钟无请求会 sleep，第一次访问冷启动 30s，前端 fetch 会超时
  - 方案 A：`apiFetch` 加统一超时 15s + 首次失败自动重试 1 次 ← ✅ 前端 apiFetch 已加 GET 自动重试 2 次（2026-04-22）
  - 方案 B：Render 升付费 / cron 每 10 分钟 ping 保活
  - 触发条件：真实用户反馈打开就转圈 / console 看到 "Failed to fetch" 再做（A 已部分覆盖）
- ✅ **Supabase 连接根治：换 `httpx.Client()` 持久连接池**（2026-04-22 完成）
  - `db/database.py` 改用全局 `httpx.Client()`（max_connections=20，keepalive=10，keepalive_expiry=60s）复用 TLS session；重试次数从 2 提到 3；本地 → Singapore 的 SSL handshake 偶发超时从 ~23% 降到个位数
  - 上线 Render 后同云区链路理论上更稳，这层兜底仍保留

---


## 保留的

- ✅ 后端：FastAPI + Supabase（需加 RLS + user_id 过滤）
- ✅ AI 架构：DeepSeek V3.2 + 双 prompt + Python 规则引擎
- ✅ 精力系统、任务管理、记忆系统、跨天逻辑（Streamlit MVP 已验证）
- ✅ 自粘贴性格 + 小白命名功能
- ✅ git 工作流 + 里程碑 tag（pixel-v0.2 / pixel-v0.3 留档）

## 评估过但不采用

- Replit（在线 IDE + AI agent）：我们已经有 Claude Code + 本地栈，Replit 适合零基础从头起步，不是我们场景
- Magic Link 开屏登录：违反"打开即用"
- localStorage 土法匿名 id：迁移风险

---

## 已锁定的细节（2026-04-14 完成，指向对应文档）

- **桌宠状态机（v2 极简 6 state）+ 触发规则 + 优先级 + 打断逻辑** → `docs/桌宠设计.md`
- **任务-聊天数据耦合链路 + 跨页 state 同步方案** → `docs/功能去留清单.md` F 节
- **Streamlit MVP → v2 留/砍/改形态清单 + Sephy 已回复的六个细节** → `docs/功能去留清单.md`

---

*Plan v2 由 04-14 下午 Sephy + 小克讨论得出。v1.2 已被本版吸收。*
