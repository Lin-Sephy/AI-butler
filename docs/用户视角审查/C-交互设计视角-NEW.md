# C 视角：交互设计师挑刺审查

> 2026-04-22 小克 review
>
> 视角定义：作为 AI 交互设计的同行，以用户会懵/烦/踩坑的细节为目标，找出设计欠缺一致性、反馈缺失、异常处理不统一的地方。不做百条清单，只挑真烫的（7 条以内）。

---

## 已知问题排除（A/B 视角已覆盖，不重复）

以下问题已在 A/B 视角记录并落地或决议，本文档跳过：
- FocusOverlay 的 🦦 → ❄（A-1，已做）
- 白噪音标签删除（A-2，已做）
- 闲聊模式关键词胶囊（A-3，已做）
- thinking 动态文案（A-4，已做）
- App 冷启文案（A-5，已做）
- FocusOverlay Date.now 改造（B-1，已做）
- 任务结转机制（B-3，已做）
- create_tasks scheduled_at（B-4，已做）
- 印象系统 token 限制（B-5，已做）

---

## 核心发现：5 个交互设计短板

### 🔥🔥 C-1. 错误反馈不一致，三层做法混杂

**代码位置**：
- TasksPage.jsx:49,58 / SettingsPanel.jsx:158 —— alert(e.message)
- SettingsPanel.jsx:145 / ChatPage.jsx:158 / PlanConfirmModal.jsx —— banner 或 state
- NewTaskModal.jsx —— 无错误处理

**现象**：
同一类操作的错误，有的用 alert 弹窗，有的用 banner。TasksPage 删任务失败弹 alert 打断用户，PlanConfirmModal 改任务失败用 banner 用户可能没看到。NewTaskModal 如果 onSubmit 出错？没有 try-catch，用户什么反馈都看不到，只看到按钮"记录中…"卡住。

**根因**：
没有统一的错误处理原则。alert() 是反模式，但多处还在用。

**小克倾向**：
建立错误反馈规范：
- 不可恢复操作（删除、清空）→ confirm 确认 + 如果失败 → alert/modal
- 批量更新、部分失败 → banner + 字段状态回滚
- 单一操作失败 → banner，不阻断流程
- 替换所有 alert()，用自实现 confirm modal
- 所有 modal 的 onSubmit 必须 try-catch

**优先级**：🔥🔥。错误反馈是用户信任基础。

---

### 🔥 C-2. 操作状态指示不一致，loading 展示风格割裂

**代码位置**：
- TaskCard.jsx:67-70 —— busy 禁用 + opacity 0.5，无文案
- NewTaskModal.jsx:133-144 —— submitting 禁用 + "记录中…"
- SettingsPanel.jsx:341-351 —— saving 禁用 + "保存中…"
- PlanConfirmModal.jsx —— 无 loading 反馈
- FocusOverlay.jsx —— 无防重复提交
- ChatPage.jsx:251-265 —— disabled + 文案"..."

**现象**：
有些操作有"记录中…"文案（用户知道在等），有些只禁用按钮没文案（用户不知道要等多久）。快速点两次可能导致重复请求。完成/放弃任务没有防重复。

**根因**：
没有统一的"操作中"状态规范。有些自管 loading，有些没有。

**小克倾向**：
所有耗时操作都显示进度：
- Button 操作中时 cursor: 'wait'
- 优先选择文案改 "中文…"（如"删除中…"）
- 防重复提交：操作中时禁用按钮或加 busy flag

工作量 1-2h，改：TaskCard / PlanConfirmModal 改操作加 loading 文案，FocusOverlay 加防重复。

**优先级**：🔥。影响响应感知。

---

### 🔥 C-3. 空态文案风格割裂，绘本语气不一致

**代码位置**：
- TasksPage.jsx:131 —— "今天还没给自己安排点什么呢" ✓
- ChatPage.jsx:313 —— "还没说过话呢" ✓
- SettingsPanel.jsx:300 —— "（还没有印象）" ✗ 冷淡括号
- PlanConfirmModal.jsx:135 —— "都删光了～" ✓

**现象**：
设置页看"小白的印象"空段时，显示 "（还没有印象）" —— 这是系统默认值文案，冷漠。对比任务页的"给自己安排点什么呢"的陪伴感，割裂明显。

**根因**：
空态文案没纳入设计规范，每处自己想。

**小克倾向**：
统一文案为绘本语（亲切、温暖、有拟声词）：
- 还没有印象 → "还在慢慢了解你呢" 或 "小白还不知道你的故事～"

工作量 15 分钟，改 1-2 处。

**优先级**：💡。产品人格一致性。

---

### 💡 C-4. 模态框关闭策略不一致，有的 confirm 有的直接关

**代码位置**：
- NewTaskModal.jsx:36 / PlanConfirmModal.jsx:77 —— 遮罩点击直接关闭
- SettingsPanel.jsx:89-93 —— 遮罩点击检查 dirty，有改动才 confirm

**现象**：
用户在 PlanConfirmModal 认真改了几个任务，不小心点遮罩关闭，直接没了，无确认。SettingsPanel 因为有 dirty 检查，用户感觉被保护。不一致会让用户在某些页面大意。

**根因**：
没有模态框关闭策略规范。

**小克倾向**：
规范：modal 有输入内容但未提交 → 关闭前都要 confirm。
- NewTaskModal：有 keyword → confirm
- PlanConfirmModal：有改动（改名、改时长、删任务） → confirm
- SettingsPanel：已有 ✓

工作量 1h，改 2 处 modal。

**优先级**：💡。用户安全感。

---

### 💡 C-5. 按钮语义和视觉不匹配三处地方

**代码位置**：
- TasksPage.jsx:183-210 —— "新建任务"用 outline（虚线），但这是最重要的 CTA
- PlanConfirmModal.jsx:156-169 —— "好"用 primary，但语义是"看完了关闭"（应为 secondary）
- SettingsPanel.jsx 保存按钮 disabled 时变淡，用户迟疑"是不是我没填完"

**现象**：
任务页上最重要的入口"新建任务"长得像可选操作；PlanConfirmModal "好"（只是关闭）却用主色，让人以为有额外含义；保存按钮 disabled 时过度变淡。

**根因**：
按钮样式选择缺规范。

**小克倾向**：
建立按钮规范：
- Primary —— 创建、保存、执行操作（填充主色）
- Secondary —— 取消、关闭、不执行（outline + 灰）
- Tertiary —— 删除、放弃、可恢复操作（透明 + 灰）

立刻改：
- PlanConfirmModal "好" 从 primary → secondary
- TasksPage "新建任务" 从 outline → primary-soft 或加 icon

工作量 30 分钟。

**优先级**：💡。视觉层级细节。

---

### 💡 C-6. 输入框 disabled 态无视觉反馈

**代码位置**：
- ChatPage.jsx:237-250 —— input disabled={sending} 但样式不变
- PlanConfirmModal TaskRow —— onBlur 后无"已保存"反馈
- SettingsPanel AI 记忆 —— readOnly 有变淡，其他没有

**现象**：
ChatPage 发送时输入框 disabled 但看不出来，用户"咦，怎么打不了"；PlanConfirmModal 改任务名提交后，输入框无任何"已保存"视觉。

**根因**：
disabled / readOnly 时没有样式改变。

**小克倾向**：
所有 disabled/readOnly 输入框加样式：
```
background: var(--color-accent-soft)
cursor: not-allowed
opacity: 0.6
```

工作量 30 分钟，改 3-4 处 input。

**优先级**：💡。细节但给人"卡住了"的感觉。

---

## 优先级建议（只改 5 件）

1. **C-1 错误反馈统一** 🔥🔥 —— 3-4h（最高）
2. **C-2 操作状态指示** 🔥 —— 1-2h
3. **C-3 空态文案** 💡 —— 15 min
4. **C-5 按钮语义修正** 💡 —— 30 min
5. **C-4 模态框 dirty 检查** 💡 —— 1h

可后续做：C-6 (30min) 和网络超时提示 (backlog)

---

## 留给后续小克的话

C 视角没发现功能 bug，只有设计不一致。AI 陪伴工具的"小白人格"要一致，不能有时冷有时热。v5 迁移重写工程代码时，设计规范没同步。建议下一里程碑前把 button / input / error / empty 规范文档化，涉及代码改时一起 review。

