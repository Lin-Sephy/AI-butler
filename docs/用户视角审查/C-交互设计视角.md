# C 视角：AI 交互设计师同行

> 2026-04-22 小克 review，2026-04-23 增量更新
>
> 视角定义：一个挑剔的 AI 交互设计师同行——她不是产品目标用户，但会盯交互一致性、状态反馈、空态/错误态、微交互、可达性。这是最苛刻的视角，也最像 Sephy 自己平时的审美。
>
> 和 A/B 视角的根本区别：**不问"对不对"，问"好不好"**。很多 C 视角的问题对功能无害，但会让一个懂行的同行扫一眼就说"这个东西一看就是 MVP"。

---

## ✅ 执行记录（2026-04-23）

原审查 13 条，按"用户真看得出 vs 同行洁癖"重评并分档处理：

| # | 条目 | 决定 + 改动 |
|---|---|---|
| **C-2** | `window.confirm` 原生弹窗污染 | **做了**。新建 `contexts/ConfirmContext.jsx` + `useConfirm()` hook，替换 6 处 `window.confirm`。弹窗走 design tokens（雪白底 + 雾蓝 primary + `var(--transition)`）。SettingsPanel 清空 AI 记忆用 `danger: true` 红按钮 |
| **C-5** | 加载态五种写法 | **做了（视觉统一，文案保留）**。5 处加载态统一 `fontSize: 14 + color subtle + textAlign center + fontFamily 继承`；App 冷启三档文案 / ChatPage "正在唤醒小白……" / TasksPage / SettingsPanel / LlmConfig 文案都保留原样 |
| **C-8** | thinking 泡泡位置偏移 | **做了**。`StoatHalf.jsx` 泡泡 `translateX 40%→30%` + `top -10→4`，视觉上贴到白鼬头顶 |
| **C-10** | 错误文案暴露 API 路径 | **做了**（合并进 C-1 的 message 归一化层）。`lib/api.js` 改 apiFetch：技术细节进 `console.error`（双层暴露），UI 只看归一化友好文案 |
| **C-11** | 空态文案冷暖不一致 | **做了**。SettingsPanel "（还没有印象）" → "还在慢慢了解你呢" |
| **C-12** | Modal 遮罩关闭策略不一致 | **做了（方案 A）**。PlanConfirmModal 遮罩点击不关（只能点"好"或 ×）；NewTaskModal keyword 非空时 confirm，空直接关 |
| **C-3** | 抽 `<Button>` 组件 | **砍了**（用户无感 + ROI 负 + Sephy "做多了是洁癖"） |
| **C-4** | ChatBubble/SpeechBubble 统一 | **砍了**（Sephy 看 HTML 对比后亲自否："现在这版还好点"）|
| **C-6** | 删除按钮三种视觉表达 | **砍了**（场景不同，任务卡列表 vs 弹窗临时 vs Modal 关闭 × 本就不该统一）|
| **C-7** | 可达性 A11Y 全档短板 | **砍了**（无键盘用户 / 无盲人用户需求；aria-label 的细节 Sephy 也要求不显 UI 上）|
| **C-8 上半** | StoatHalf 硬切无 crossfade | **砍了**（现状可接受，不是 bug 只是可接受的瞬切）|
| **C-9** | Typography 12 个字号 | **暂留不做**（Sephy 说先留着）|
| **C-13** | input disabled 无视觉反馈 | **手机测试阶段收**（Sephy 决定）|

**配色备注**：原稿里"松针绿 primary 按钮"是按 `plan.md` 最早期写法，实际配色走雾蓝（`design-tokens.css:13` 明确"放弃绿色"）。执行时按实际雾蓝做。

**测试状态**：L1 pytest 48 全过；UI 改动手工验证见 `手工测试指引.md`。

---

## 一个总判断（先说结论）

v2 前端最核心的问题不是哪个组件做得不好，而是**没有设计系统**。每个组件都在重新发明自己的 Button / Input / Modal / ErrorBanner 样式。局部看每个都合理，放在一起就显得零散。

这是 MVP 阶段的正常状态——先做功能。Sephy 的判断：**不砸设计系统**，因为：
- 用户大多看不出一致性问题（字号差 1-2px / padding 差 4px 这类）
- 上线前按钮样式已经定稿，大改概率低
- 抽组件的 5-6h + 迁移风险 > 未来一次手动改样式的 1-2h

所以 C 视角的"洁癖条目"大多砍了。留下的都是**用户真会懵**的场景。

---

## 剩余条目

### C-1. 错误展示四种并存（⏳ 上线前做）

C-10 已经做完了"message 归一化层"（技术细节进 console，UI 看友好文案）。**剩下的 C-1 是"展示层那一半"**：

| 位置 | 形态 |
|---|---|
| TasksPage action 失败 | 原生 `alert(e.message)` |
| ChatPage 消息发送失败 | 页面顶 `ErrorBanner` |
| SettingsPanel 加载失败 | `ErrorBanner` + 重试按钮 |
| SettingsPanel 保存失败 | 底部红字 span |
| LlmConfig 保存失败 | 底部红字 span |
| PlanConfirmModal 改失败 | inline 红卡片 |
| FocusOverlay 失败 | **完全没反馈** |

**上线前做**：抽 `<ErrorBanner>` / `<ErrorToast>` 组件到 `frontend/src/components/`，所有 `alert()` 替换，FocusOverlay 加错误反馈。2-3h 工作量。

**Sephy 之前明确要求**：**现在保留 alert 用来定位 bug**（错误长什么样决定测试时能不能立刻看到是哪层出错）。上线前再统一。

---

### C-9. Typography 系统缺失（先留着不做）

统计了一下用到的 fontSize：**11, 12, 13, 14, 15, 16, 17, 18, 20, 22, 28, 96**。**12 个字号**在同一个产品里。

**小克原倾向**：锁 6-8 个字号档位（11 / 13 / 14 / 16 / 20 / 28 / 96-display），写进 `design-tokens.css`。工作量 2h。

**Sephy 2026-04-23 决定**：**先留着不做**。和 C-3 同类——用户感知弱，砸一次工作量大但收益窄。上线后如果有新页面加入时发现层级乱再说。

---

### C-13. 输入框 disabled / readOnly 态无视觉反馈（手机测试阶段做）

`ChatPage.jsx` 发送时 `input.disabled={sending}`——但样式没变。桌面端影响小（发送按钮已变灰有兜底），**手机端比桌面更烫**：
- 手机无 hover / cursor 视觉
- 靠软键盘判断"能不能打字"，input disabled 可能让键盘弹不起来

**Sephy 2026-04-23 决定**：**和手机端其他 UX 问题一起在手机测试阶段统一收**（A 视角的手机端拉窄实测 + C-13 一起做）。

最小改动 15 分钟：
```js
opacity: sending ? 0.55 : 1,
cursor: sending ? 'not-allowed' : 'text',
```

---

## 二、没挑但值得记下的细节（不展开）

读代码时遇到的小细节，**不建议现在修**，但记下来避免未来小克重复发现：

- FocusOverlay 的完成/放弃按钮没有 busy 态，快速双点会发两次 POST（但后端 PATCH 条件保护得住，无数据风险）
- TaskCard 改任务要等 `fetchTasks` 刷新才看到；PlanConfirmModal 乐观更新。两种 pattern 在同一产品并存
- SettingsPanel 手机竖屏 `maxHeight: 80vh` 六区块挤在 533px 里滚动疲惫
- `/api/chat` 兜底文案 "哎呀，出了点小问题" 与 `intent.py` 的 "网络开小差了" 是两套，应该统一

这些每条都小。上线前如果集中做一次错误/文案 sweep 可以顺手清。

---

## 三、留给后续小克的上下文

- C 视角原本 13 条，Sephy 按"用户真看得出 vs 同行洁癖"做了分档。**大部分被砍**。
- **真的留到最后没做的只有 3 条**：C-1（上线前做）/ C-9（先留着）/ C-13（手机测试阶段）
- **请不要重新建议"砸一次设计系统"**——Sephy 的判断是 ROI 负。抽 Button/Modal/ErrorBanner 组件在"用户无感 + 未来改动不频繁"的前提下得不偿失。
- 未来写新功能时如果发现自己在重新声明 Button 样式 / 写 inline alert——那就是设计系统的**需求信号**。等信号累积到"真影响开发效率"再讨论，不是现在。
- 本文档 2026-04-22 与 A/B/D 视角同日写，2026-04-23 增量更新执行记录。四份合起来看比单独任何一份都值。
