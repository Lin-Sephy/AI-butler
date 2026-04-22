# C 视角：AI 交互设计师同行

> 2026-04-22 小克 review
>
> 视角定义：一个挑剔的 AI 交互设计师同行——她不是产品目标用户，但会盯交互一致性、状态反馈、空态/错误态、微交互、可达性。这是最苛刻的视角，也最像 Sephy 自己平时的审美。
>
> 和 A/B 视角的根本区别：**不问"对不对"，问"好不好"**。很多 C 视角的问题对功能无害，但会让一个懂行的同行扫一眼就说"这个东西一看就是 MVP"。

---

## 一个总判断（先说结论）

v2 前端最核心的问题不是哪个组件做得不好，而是**没有设计系统**。每个组件都在重新发明自己的 Button / Input / Modal / ErrorBanner 样式。局部看每个都合理，放在一起就显得零散。

这是 MVP 阶段的正常状态——先做功能。但如果要让一个同行"看一眼就觉得是认真做的产品"，下一步该集中做一次**设计系统抽取**，而不是继续加新功能。

下面按"同行最先注意到的几类"整理。

---

## C-1. 错误展示四种并存

同一个 app 里"出错了"有四种不同的视觉呈现：

| 位置 | 形态 | 代码 |
|---|---|---|
| TasksPage action 失败 | 原生 `alert()` 弹窗 | `TasksPage.jsx:50, 59` |
| ChatPage 消息发送失败 | 页面顶 `ErrorBanner`（#fee/#fbb/#933） | `ChatPage.jsx:138` |
| SettingsPanel 加载失败 | `ErrorBanner` + 重试按钮 | `SettingsPanel.jsx:216` |
| SettingsPanel 保存失败 | 底部红字 span | `SettingsPanel.jsx:328` |
| LlmConfig 保存失败 | 底部红字 span | `LlmConfig.jsx:232` |
| PlanConfirmModal 改失败 | inline 红卡片（颜色 hardcode） | `PlanConfirmModal.jsx:123-131` |
| FocusOverlay 失败 | **完全没有反馈** | `FocusOverlay.jsx:94-117` |

**原生 `alert()` 是最刺眼的**——浏览器默认样式，跟 IBM Plex Serif + 雪白松针绿调性完全撕裂。

**小克倾向**：抽一个 `<ErrorBanner>` / `<ErrorToast>` 到 `frontend/src/components/`，所有错误走它。`alert()` 全数替换。工作量 1-2h，视觉一致性立刻起来。

---

## C-2. window.confirm 原生弹窗污染调性

同一个讲究视觉的产品，五处用的是浏览器原生 confirm：

- `SettingsPanel.jsx:91`  "有改动没保存，确定关闭？"
- `SettingsPanel.jsx:152` "清空小白对你的印象？"
- `ChatPage.jsx:105,240`  "清空当前对话开新的？"
- `PersonaPresets.jsx:49` "会覆盖当前性格描述，确定？"
- `LlmConfig.jsx:128`     "清空自带配置，回到用默认服务？"

Windows Chrome / macOS Safari / iOS Safari 的原生 confirm 长相都不一样，每种都破坏产品调性。

**小克倾向**：写一个 `<ConfirmDialog>` Modal，复用设置弹窗样式（雪白底 + 松针绿 primary 按钮 + 300ms ease-out 过渡）。全部替换。1-2h。

---

## C-3. 按钮样式在五六个文件里重复声明，细节不一致

同是"primary button"，数值不一样：

| 位置 | padding | border-radius |
|---|---|---|
| `SettingsPanel primaryBtnStyle` | `10px 24px` | `var(--radius)` |
| `LlmConfig primaryBtnStyle` | `8px 20px` | `var(--radius)` |
| `PlanConfirmModal` 底部 inline | `10px 24px` | `var(--radius)` |
| `NewTaskModal` 提交按钮 inline | `10px 24px` | `var(--radius)` |
| `TasksPage` "+ 新建任务" inline | `14px 20px` | `var(--radius)` |
| `ChatPage` 发送按钮 inline | `10px 20px` | `var(--radius)` |

**primary / secondary / subtle / ghost 四种按钮变体，每个页面都在重新发明**。

**小克倾向**：抽 `<Button variant="primary|secondary|ghost" size="sm|md">` 到 `components/ui/`。这是设计系统第一块砖。所有按钮迁过去。4-6h 工作量。砸下去之后后续新功能开发效率会上来。

---

## C-4. ChatBubble 和 SpeechBubble 是两套视觉语言

同一个小白，历史视图和主视图的气泡用的**是两套独立实现**：

| | ChatBubble（历史视图） | SpeechBubble（主视图） |
|---|---|---|
| 头像 | 有 | 无 |
| AI 气泡背景 | `color-accent-soft`（偏绿） | `color-surface`（偏白） |
| 气泡尖角 | 用 `borderBottomXxxRadius` 做 | 用 `rotate(45deg)` 方块做 |
| 气泡边框 | `1px solid accent` | `1.5px solid line` |
| maxWidth | 75% | 78%（主视图 AI） / 85%（主视图用户） |

**用户切 📃 历史 和 主视图时，会"咦这是两个不同的产品吗"**——同一组信息用两套视觉语言，是设计系统缺失的典型症状。

**小克倾向**：主视图用"漫画气泡 + 居中白鼬"是差异化核心，要保留。但**历史视图的 ChatBubble 应该成为主视图 SpeechBubble 的"无泡尾简化版"**——共用颜色、边框、圆角、字号。抽到一个 `<Bubble>` 组件，通过 `variant` prop 控制有无泡尾/头像。

---

## C-5. 加载态五种写法

- TasksPage：`<CenterText>加载中…</CenterText>`（80px padding）
- ChatPage：`<CenterText>正在唤醒小白……</CenterText>`
- SettingsPanel：`<p>加载中…</p>`
- LlmConfig：自己的小 div `加载中…`
- PersonaPresets：按钮 disabled + opacity 0.5 + `cursor: wait`（**做得最好**）

**五个地方四种"加载中"表达**。

**小克倾向**：PersonaPresets 的"保留布局 + disabled 状态"是最成熟的 pattern——**加载态应该尽量不换布局**（避免 layout shift），只把该区域 disabled + 降透明度。抽 `<Skeleton>` 或 `<LoadingOverlay>`。

---

## C-6. 删除按钮三种视觉表达

同一个"删除某条"语义：

- TaskCard：小胶囊 "删除"（文字） —— `ActionBtn subtle`
- PlanConfirmModal TaskRow：32×32 方形 `×`
- SettingsPanel / PlanConfirmModal 标题栏：22px 大 `×` 字符

**三种删除**。同行看一眼：这到底是同一个产品吗？

**小克倾向**：规范——
- **关闭弹窗** → 右上 `×`
- **删除列表项** → 小胶囊 "删除" 或 32×32 × 图标（任选一种贯彻到底）
- **销毁性主动作**（比如"清空记忆"）→ 文字按钮 + 红色或警示色

---

## C-7. 可达性（A11Y）全档短板

同行会直接指出来的三件事：

- **全项目找不到 `:focus-visible` 样式**。Tab 键过一遍所有按钮，键盘用户看不出当前焦点在哪。inline 的 `outline: 'none'` 反而是在**关掉**浏览器默认的焦点环。
- **弹窗没有 focus trap**。打开 NewTaskModal/SettingsPanel/PlanConfirmModal 后按 Tab 会跑到弹窗外的 DOM。关闭后焦点不归位。
- **弹窗没有 Escape 关闭**。`onClick={onClose}` 只响应背景点击和 `×` 按钮点击，键盘用户只能用鼠标关闭。
- **图标按钮没有 aria-label**。`HistoryIcon` / `CirclePlus` / `Gear` 对屏幕阅读器都只是"空按钮"。

**小克倾向**：
- 全局 CSS 加 `button:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }` —— 十分钟的活。
- `<Modal>` 组件化时加 focus trap + Escape + 焦点归位（用 `react-focus-lock` 库或手写 ~30 行）
- 图标按钮的 `<IconBtn title="...">` 现在 title 是鼠标悬停提示，改成 `aria-label={title}` 就同时解决屏幕阅读器——**一行改动**

---

## C-8. 微交互的两个痕迹

### StoatHalf 状态切换硬切

`StoatHalf.jsx:54` 的 `<img src={src}>` 根据 state 切 frontSrc/sideSrc。注释说有 `transition: 'opacity 200ms ease-out'`，但 src 替换不会触发 opacity 动画——那是属性过渡不是内容过渡。

**实际表现**：用户发送消息时，白鼬从正脸（idle/listening）瞬间硬切到侧脸（thinking）。没有过渡。

**小克倾向**：两张图层叠 + opacity 交替（crossfade），30 分钟工作量：
```jsx
<img src={frontSrc} style={{opacity: state === 'thinking' ? 0 : 1, ...}} />
<img src={sideSrc}  style={{opacity: state === 'thinking' ? 1 : 0, position: 'absolute', ...}} />
```

### thinking 泡泡位置偏移 40%

`StoatHalf.jsx:77` `transform: 'translateX(40%)'`——从 `left: 50%` 又往右偏 40%，最后大约落在容器宽的 90% 位置。不是头顶正中。

**上下文**：可能是为了对齐"侧脸白鼬的头部偏一侧"，但效果看起来像 UI bug。

**小克倾向**：侧脸时头偏哪边，泡泡就跟着偏。但 40% 偏移过大——建议 15-20%，视觉上还在"头上方"的语义里。

---

## C-9. Typography 系统缺失

统计了一下用到的 fontSize：**11, 12, 13, 14, 15, 16, 17, 18, 20, 22, 28, 96**。**12 个字号**在同一个产品里。

13/14 常常并存（哪个是"小字说明"？），11/12 也常并存（subtle label 一会 11 一会 12）。没有 design tokens 化，每个组件凭手感选。

**小克倾向**：锁 6-8 个字号档位（比如 11 / 13 / 14 / 16 / 20 / 28 / 96-display），写进 `design-tokens.css`，component 只能引用。工作量大概 2h，但砸下去视觉节奏立刻规整。

同样的病在 border-radius 上（`var(--radius)` 和 14/16/20/99/999 混用）和动画时长上（`1.6s / 4s / 1.4s / 1.8s / 400ms / 200ms` 几乎每处不一样）。

---

## C-10. 错误文案直接暴露 API 路径

`lib/api.js:63` 抛的 ApiError message 是 `API POST /api/task/123/start 失败: xxx`。然后 TasksPage `alert(e.message)` 直接给用户看。

用户看到 `API POST /api/task/...` 这种字符串会**以为是系统崩溃了**。

**小克倾向**：apiFetch 抛错时保留技术细节（console.error），**展示层用归一文案**：
- 网络层错误（TypeError）→ "网络有点慢，等等再试"
- 401 → "登录失效了，刷新一下"
- 4xx 其他 → 后端返回的 detail（通常是业务错误，可读）
- 5xx → "小白那边出了点问题，稍等"

---

## 二、没挑但值得记下的细节（不展开）

读代码时遇到的小细节，**不建议现在修**，但记下来避免未来小克重复发现：

- FocusOverlay 的完成/放弃按钮没有 busy 态，快速双点会发两次 POST（但后端 PATCH 条件保护得住，无数据风险）
- TaskCard 改任务要等 `fetchTasks` 刷新才看到；PlanConfirmModal 乐观更新。两种 pattern 在同一产品并存。
- ChatPage 发送中时 input 是 disabled 但没有视觉差异（用户看起来像能打字）
- SettingsPanel 手机竖屏 `maxHeight: 80vh` 六区块挤在 533px 里滚动疲惫
- `/api/chat` 兜底文案 "哎呀，出了点小问题" 与 `intent.py` 的 "网络开小差了" 是两套，应该统一
- TaskCard 的 `TYPE_LABEL = { work: 'work', rest: 'rest' }` 是英文，FocusOverlay 的 `focus / open` 也英文；但 chipText "进行中/已暂停/已完成" 是中文。英文只在"数字+单位"和"task_type 标签"出现，用户看不出规律。

这些每条都小，加起来就是"这个产品细节还没磨完"的印象来源。但它们的共同修法是**做完设计系统后一起清理**——现在单独修每一条反而会让代码更乱。

---

## 三、C 视角优先级建议

C 视角的特点是**"单独每条都不紧急，但合起来决定产品质感"**。建议按"一次性抽系统"而不是"一条条修"。

**集中 2-3 天砸一次设计系统（推荐做法）**：

1. 抽 `<Button>` / `<IconBtn>` 组件，细化 variant 和 size（4-6h）
2. 抽 `<Modal>` 组件，内置 focus trap + Escape + aria-*（3-4h）
3. 抽 `<ErrorBanner>` / `<ConfirmDialog>` 组件（2-3h）
4. 写 design-tokens.css 锁定字号 / 圆角 / 动画时长档位（2h）
5. 全项目迁移（一边迁一边清 C-3 到 C-6 问题）（4-6h）
6. 加全局 `:focus-visible` + `aria-label` 扫一遍图标按钮（1h）

**总计 16-22h**，砸完之后：
- 未来写新功能不再重新发明轮子
- A 视角和 B 视角的修复可以搭车用新组件（例如 A-3 的完成按钮确认对话、B-1 的弹窗都能复用新的 Modal）
- 同行扫一眼会知道这是"认真做"的产品

**单条修的烫度优先级（如果暂时没精力做大的）**：

1. 全局 `button:focus-visible` 样式（10 分钟，可达性起步）
2. 把五处 `window.confirm` 换成 `<ConfirmDialog>`（可以先写一个简单版）（2h）
3. `alert(e.message)` 全改 ErrorBanner（1h）
4. 图标按钮的 `title` 改成 `aria-label`（30 分钟）

---

## 四、C 视角暴露的产品阶段判断

三个视角合起来看，产品阶段的诊断更清楚：

- **A 视角**：新用户路径的"立刻就用"主张基本做到了，但入口引导、错误态、细节文案还粗糙 → 常规 MVP 状态
- **B 视角**：长期使用的底层机制断链四处 → 说明 v5 迁移时注意力全在"功能能跑"，没给"一个月后会怎样"留测试时间
- **C 视角**：设计系统没做 → 说明 v5 前端一直在"加功能"模式，没进过"集中整理"模式

**建议下一阶段不加新功能，做三件事**：
1. 把 A 视角的 5 件事修掉
2. 把 B-1（FocusOverlay Date.now）和 B-3（idle 2 天结转）修掉——这两件在毁数据/压用户
3. 砸一次设计系统

砸完之后再继续做桌宠状态机 / 数据页 / 我的页 / 上线收尾。会轻松很多。

---

## 五、留给后续小克的上下文

- C 视角是三个视角里**问题最多但单条最不紧急**的一个。未来小克一定会想"这清单太长了一条条修"——**不要这么做**。
- 正确的打开方式：把 C 视角当"下次集中整理期"的 backlog 来源。平时开发新功能时，发现自己在重新声明 Button 样式 / 写 inline alert——那就是设计系统的需求信号。
- C-7（可达性）是**唯一一组单独修也合理的**，因为键盘/屏幕阅读器用户没法等你砸设计系统。可以先做。
- 本文档 2026-04-22 与 A/B 视角同日写。三份合起来看比单独任何一份都值。
