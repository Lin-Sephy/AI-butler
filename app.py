import streamlit as st
import uuid
from db.database import (
    init_db, save_action_log, get_user_memo, save_user_memo,
    get_ai_memo, clear_ai_memo,
    save_chat_message, load_session_messages,
)
from core.memory import update_ai_memory, get_filtered_daily_memo, bump_on_mention
from core.energy import get_current_energy, update_energy, ENERGY_LEVELS
from core.intent import call_ai
from core.rules_engine import (
    validate_reply, check_energy_drift, should_show_action_buttons, get_follow_up,
)
from core.task_manager import (
    create_task, pause_task, resume_task, complete_task, abandon_task,
    get_active_task, update_task_minutes, get_today_tasks, delete_task,
    create_recurring_task, get_recurring_tasks, delete_recurring_task,
    spawn_daily_tasks, start_idle_task,
    create_scheduled_task, get_scheduled_tasks, get_due_scheduled_tasks,
    start_scheduled_task,
)

# ---------- 数据库初始化 + 每日循环任务生成 ----------
init_db()
spawn_daily_tasks()

# ---------- 页面配置 ----------
st.set_page_config(page_title="AI 身体状态计划管家", page_icon="🏠", layout="centered")
st.title("AI 身体状态计划管家")

# ---------- session_state 初始化 ----------
def add_message(role: str, content: str):
    """添加消息到 session_state 并同步存库。"""
    st.session_state.messages.append({"role": role, "content": content})
    save_chat_message(st.session_state.session_id, role, content)


if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    saved = load_session_messages(st.session_state.session_id)
    if saved:
        st.session_state.messages = saved
    else:
        greeting = "来啦～"
        st.session_state.messages = [{"role": "assistant", "content": greeting}]
        save_chat_message(st.session_state.session_id, "assistant", greeting)
if "energy" not in st.session_state:
    st.session_state.energy = get_current_energy()
if "last_ai_response" not in st.session_state:
    st.session_state.last_ai_response = None  # 最近一次 AI 返回的完整 JSON
if "energy_confirm_pending" not in st.session_state:
    st.session_state.energy_confirm_pending = False  # 是否在等用户确认精力值
if "active_task" not in st.session_state:
    st.session_state.active_task = get_active_task()  # 恢复未完成任务
if "schedule_pending" not in st.session_state:
    st.session_state.schedule_pending = None  # 待用户确认的预定任务
if "schedule_dismissed" not in st.session_state:
    st.session_state.schedule_dismissed = set()  # 用户拒绝过的预定（keyword+time）
if "msg_count" not in st.session_state:
    st.session_state.msg_count = 0  # 用户消息计数，每 10 轮触发记忆更新
if "pending_switch" not in st.session_state:
    st.session_state.pending_switch = None  # "换一个"待处理标记

# ---------- 小白人设（侧边栏） ----------
PERSONA_OPTIONS = {
    "infp": "共情型（INFP）",
    "intj": "军师型（INTJ）",
    "rest": "休息型（REST）",
    "intp": "观察型（INTP）",
    "challenger": "挑战型（找茬）",
}

if "persona" not in st.session_state:
    st.session_state.persona = "infp"

st.sidebar.markdown("### 小白性格")
persona_labels = list(PERSONA_OPTIONS.values())
persona_keys = list(PERSONA_OPTIONS.keys())
selected_persona_label = st.sidebar.radio(
    "选择小白的性格",
    persona_labels,
    index=persona_keys.index(st.session_state.persona),
    key="persona_radio",
)
st.session_state.persona = persona_keys[persona_labels.index(selected_persona_label)]

# ---------- 精力系统（侧边栏） ----------
st.sidebar.markdown("### 今日精力")

energy = st.session_state.energy
level = energy["energy_level"]
info = ENERGY_LEVELS[level]

source_label = {"inherited": "静默继承", "manual": "手动设置", "ai_assessed": "AI 评估"}
st.sidebar.caption(f"来源：{source_label.get(energy['source'], energy['source'])}")

st.sidebar.markdown(
    f'<div style="font-size:1.4em; color:{info["color"]}; font-weight:bold;">'
    f'{level} 档 · {info["label"]}</div>',
    unsafe_allow_html=True,
)

options = [1, 2, 3, 4, 5]
labels = [f"{v} - {ENERGY_LEVELS[v]['label']}" for v in options]
selected_label = st.sidebar.radio(
    "调整精力档位", labels, index=level - 1, key="energy_radio",
)
selected_value = int(selected_label[0])

if selected_value != st.session_state.energy["energy_level"]:
    update_energy(selected_value, "manual")
    st.session_state.energy = {
        "energy_level": selected_value,
        "source": "manual",
        "label": ENERGY_LEVELS[selected_value]["label"],
        "color": ENERGY_LEVELS[selected_value]["color"],
    }
    st.rerun()

def _on_start_idle(task_id: int):
    """用户在侧边栏点击待完成的循环任务，直接开始。"""
    energy_now = st.session_state.energy["energy_level"]
    try:
        task = start_idle_task(task_id, energy_now)
        st.session_state.active_task = task
        add_message("assistant", f"开始「{task['keyword']}」！加油～")
    except ValueError:
        add_message("assistant", "你现在还有一个任务在进行中哦，先完成或放弃它再开始新的吧。")


def _on_delete_task(task_id: int):
    """删除任务的回调，删除后触发页面刷新。"""
    delete_task(task_id)


def _on_start_scheduled(task_id: int):
    """用户点击预定任务的开始按钮。"""
    energy_now = st.session_state.energy["energy_level"]
    try:
        task = start_scheduled_task(task_id, energy_now)
        st.session_state.active_task = task
        add_message("assistant", f"开始「{task['keyword']}」！加油～")
    except ValueError:
        add_message("assistant", "你现在还有一个任务在进行中哦，先完成或放弃它再开始新的吧。")

# ---------- 今日任务（侧边栏） ----------
st.sidebar.markdown("---")
st.sidebar.markdown("### 今日任务")

today_tasks = get_today_tasks()
if today_tasks:
    active = [t for t in today_tasks if t["status"] in ("executing", "paused")]
    idle = [t for t in today_tasks if t["status"] == "idle"]
    done = [t for t in today_tasks if t["status"] == "completed"]

    if active:
        st.sidebar.markdown("**── 进行中 ──**")
        for t in active:
            icon = "🔵" if t["status"] == "executing" else "⏸️"
            duration_text = f" · {t['default_minutes']}min" if t.get("default_minutes") else ""
            st.sidebar.markdown(f"　{icon} {t['keyword']}{duration_text}")

    if idle:
        st.sidebar.markdown("**── 待完成 ──**")
        for t in idle:
            duration_text = f" · {t['default_minutes']}min" if t.get("default_minutes") else ""
            st.sidebar.button(
                f"⬜ {t['keyword']}{duration_text}（每日）",
                key=f"start_idle_{t['id']}",
                on_click=_on_start_idle, args=(t["id"],),
            )

    # 预定任务
    scheduled = get_scheduled_tasks()
    if scheduled:
        st.sidebar.markdown("**── 预定任务 ──**")
        for t in scheduled:
            time_label = t["scheduled_at"][5:16] if t.get("scheduled_at") else ""
            duration_text = f" · {t['default_minutes']}min" if t.get("default_minutes") else ""
            with st.sidebar.expander(f"🕐 {t['keyword']}　{time_label}{duration_text}"):
                st.button("开始", key=f"start_sched_{t['id']}",
                          on_click=_on_start_scheduled, args=(t["id"],))
                st.button("删除", key=f"del_sched_{t['id']}",
                          on_click=_on_delete_task, args=(t["id"],))

    if done:
        st.sidebar.markdown("**── 已完成 ──**")
        work_done = [t for t in done if t.get("task_type", "work") == "work"]
        rest_done = [t for t in done if t.get("task_type") == "rest"]
        if work_done:
            st.sidebar.markdown("📚 工作/学习")
            for t in work_done:
                duration_text = f" · {t['default_minutes']}min" if t.get("default_minutes") else ""
                with st.sidebar.expander(f"✅ {t['keyword']}{duration_text}"):
                    st.button("删除", key=f"del_task_{t['id']}",
                              on_click=_on_delete_task, args=(t["id"],))
        if rest_done:
            st.sidebar.markdown("🌿 休息")
            for t in rest_done:
                duration_text = f" · {t['default_minutes']}min" if t.get("default_minutes") else ""
                with st.sidebar.expander(f"✅ {t['keyword']}{duration_text}"):
                    st.button("删除", key=f"del_task_{t['id']}",
                              on_click=_on_delete_task, args=(t["id"],))
else:
    st.sidebar.caption("还没有任务，跟小白聊聊吧～")

# ---------- 循环任务管理（侧边栏） ----------
st.sidebar.markdown("---")
with st.sidebar.expander("管理每日任务"):
    # 添加新循环任务
    new_kw = st.text_input("任务名称", key="new_recurring_kw")
    new_type = st.selectbox("类型", ["work", "rest"],
                            format_func=lambda x: "工作/学习" if x == "work" else "休息",
                            key="new_recurring_type")
    new_min = st.number_input("建议时长（分钟）", min_value=5, max_value=120, value=25,
                              key="new_recurring_min")
    if st.button("添加", key="btn_add_recurring"):
        if new_kw.strip():
            create_recurring_task(new_kw.strip(), new_type, new_min)
            spawn_daily_tasks()  # 立即生成今天的 idle 任务
            st.rerun()

    # 显示已有循环任务，可删除
    recurring = get_recurring_tasks()
    if recurring:
        st.markdown("**已有每日任务：**")
        for rec in recurring:
            col_name, col_del = st.columns([3, 1])
            with col_name:
                st.caption(f"{rec['keyword']} · {rec.get('default_minutes', '')}min")
            with col_del:
                st.button("删", key=f"del_rec_{rec['id']}",
                          on_click=delete_recurring_task, args=(rec["id"],))

# ---------- 记忆库（侧边栏） ----------
st.sidebar.markdown("---")
with st.sidebar.expander("我的手记"):
    current_memo = get_user_memo()
    new_memo = st.text_area(
        "写下你的背景信息，小白会记住",
        value=current_memo,
        placeholder="例如：我是大三学生，正在准备考研，主要科目是数学和英语。上午效率比较高，下午容易犯困。",
        height=120,
        key="memo_input",
    )
    if st.button("保存", key="btn_save_memo"):
        save_user_memo(new_memo)
        st.success("已保存！")

with st.sidebar.expander("AI 记忆"):
    ai_memo = get_ai_memo()
    if ai_memo.strip():
        st.markdown(ai_memo)
    else:
        st.caption("小白还没记住什么，聊几轮就会自动学习～")
    if ai_memo.strip():
        if st.button("清空 AI 记忆", key="btn_clear_ai_memo"):
            clear_ai_memo()
            st.success("已清空！")
            st.rerun()


# ---------- 错误处理 ----------

import logging

def safe_callback(fn):
    """回调保护装饰器，出错时显示友好提示而非崩溃。"""
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            logging.error(f"回调 {fn.__name__} 出错: {type(e).__name__}: {e}")
            add_message("assistant", "哎呀，出了点小问题。你再试一次？")
    return wrapper


# ---------- 反馈按钮回调 ----------

@safe_callback
def on_accept():
    """用户点击"开始"——创建任务或预定任务。"""
    resp = st.session_state.last_ai_response
    if resp is None:
        return
    energy_now = st.session_state.energy["energy_level"]
    save_action_log(
        energy=energy_now,
        intent=resp.get("combo", ""),
        strategy=resp.get("willingness", ""),
        recommendation=resp.get("task_keyword", ""),
        user_action="accept",
    )
    task_kw = resp.get("task_keyword", "这件事")
    suggested_minutes = resp.get("suggested_minutes")
    task_type = resp.get("task_type", "work")
    task = create_task(keyword=task_kw, combo=resp.get("combo", ""),
                       energy_level=energy_now, suggested_minutes=suggested_minutes,
                       task_type=task_type)
    st.session_state.active_task = task

    duration_text = f"建议专注 {task['default_minutes']} 分钟" if task["default_minutes"] else "不设时长限制，按自己节奏来"
    add_message("assistant", f"好的，开始「{task_kw}」！{duration_text}，随时可以暂停或完成～")
    st.session_state.last_ai_response = None
    st.session_state.switch_count = 0


@safe_callback
def on_switch():
    """用户点击"换一个"——标记状态，由主流程处理。"""
    resp = st.session_state.last_ai_response
    if resp is None:
        return
    energy_now = st.session_state.energy["energy_level"]
    save_action_log(
        energy=energy_now,
        intent=resp.get("combo", ""),
        strategy=resp.get("willingness", ""),
        recommendation=resp.get("task_keyword", ""),
        user_action="switch",
    )

    switch_count = st.session_state.get("switch_count", 0) + 1
    st.session_state.switch_count = switch_count

    if switch_count >= 2:
        # 第二次换：追问用户想做什么
        follow_up = get_follow_up()
        add_message("assistant", follow_up)
        st.session_state.last_ai_response = None
        st.session_state.switch_count = 0
    else:
        # 第一次换：标记待处理，由主流程调 API
        st.session_state.pending_switch = resp.get("task_keyword", "")
        st.session_state.last_ai_response = None


@safe_callback
def on_pause():
    """暂停当前任务。"""
    task = st.session_state.active_task
    if task:
        updated = pause_task(task["id"])
        st.session_state.active_task = updated
        add_message("assistant", f"「{task['keyword']}」已暂停，休息一下吧～想继续的时候点【继续】就行。")


@safe_callback
def on_resume():
    """继续当前任务。"""
    task = st.session_state.active_task
    if task:
        updated = resume_task(task["id"])
        st.session_state.active_task = updated
        add_message("assistant", f"继续「{task['keyword']}」！加油～")


@safe_callback
def on_complete():
    """完成当前任务。休息类任务弹精力确认，工作类不弹。"""
    task = st.session_state.active_task
    if task:
        updated = complete_task(task["id"])
        st.session_state.active_task = None
        energy_now = st.session_state.energy["energy_level"]
        save_action_log(
            energy=energy_now,
            intent=task.get("combo", ""),
            strategy="",
            recommendation=task.get("keyword", ""),
            user_action="complete",
        )
        add_message("assistant", f"「{task['keyword']}」完成了！干得漂亮～")
        if task.get("task_type") == "rest":
            st.session_state.energy_confirm_pending = "rest"


@safe_callback
def on_abandon():
    """放弃当前任务。"""
    task = st.session_state.active_task
    if task:
        updated = abandon_task(task["id"])
        st.session_state.active_task = None
        energy_now = st.session_state.energy["energy_level"]
        save_action_log(
            energy=energy_now,
            intent=task.get("combo", ""),
            strategy="",
            recommendation=task.get("keyword", ""),
            user_action="abandon",
        )
        add_message("assistant", f"没关系，「{task['keyword']}」先放一放。有时候放下也是一种选择。")


DURATION_OPTIONS = [10, 15, 25, 35, 45, 60, 90, 120]


@safe_callback
def on_change_duration():
    """循环切换任务时长。"""
    task = st.session_state.active_task
    if not task:
        return
    current = task.get("default_minutes")
    if current in DURATION_OPTIONS:
        idx = (DURATION_OPTIONS.index(current) + 1) % len(DURATION_OPTIONS)
    else:
        idx = 0
    new_minutes = DURATION_OPTIONS[idx]
    updated = update_task_minutes(task["id"], new_minutes)
    st.session_state.active_task = updated


@safe_callback
def on_energy_confirm(new_level: int):
    """用户确认精力值。"""
    update_energy(new_level, "manual")
    st.session_state.energy = {
        "energy_level": new_level,
        "source": "manual",
        "label": ENERGY_LEVELS[new_level]["label"],
        "color": ENERGY_LEVELS[new_level]["color"],
    }
    st.session_state.energy_confirm_pending = False
    # 同步侧边栏 radio 状态
    st.session_state.energy_radio = f"{new_level} - {ENERGY_LEVELS[new_level]['label']}"

    # 精力值变了，重新校验当前 AI 回复
    resp = st.session_state.last_ai_response
    if resp:
        is_valid, final_reply = validate_reply(resp, new_level)
        if not is_valid:
            resp["reply"] = final_reply
            # 替换最后一条 assistant 消息
            for i in range(len(st.session_state.messages) - 1, -1, -1):
                if st.session_state.messages[i]["role"] == "assistant":
                    st.session_state.messages[i]["content"] = final_reply
                    break


# ---------- 到期预定任务提醒 ----------
if "notified_scheduled" not in st.session_state:
    st.session_state.notified_scheduled = set()

due_tasks = get_due_scheduled_tasks()
for dt in due_tasks:
    if dt["id"] not in st.session_state.notified_scheduled:
        time_label = dt["scheduled_at"][11:16] if dt.get("scheduled_at") else ""
        reminder = f"你之前预定了 {time_label} 的「{dt['keyword']}」，时间到啦～要开始吗？可以在侧边栏点击开始。"
        add_message("assistant", reminder)
        st.session_state.notified_scheduled.add(dt["id"])

# ---------- 渲染聊天历史 ----------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ---------- 精力值确认面板 ----------
if st.session_state.energy_confirm_pending:
    if st.session_state.energy_confirm_pending == "rest":
        st.info("休息结束了，你现在感觉怎么样？")
    else:
        st.info("你听起来状态跟之前不太一样，现在感觉怎么样？")
    cols = st.columns(5)
    energy_options = [
        (5, "精力充沛"), (4, "还行"), (3, "有点累"), (2, "很疲惫"), (1, "完全不行")
    ]
    for i, (val, label) in enumerate(energy_options):
        with cols[i]:
            st.button(label, key=f"energy_confirm_{val}",
                      on_click=on_energy_confirm, args=(val,))

# ---------- 预定任务确认面板 ----------
if st.session_state.schedule_pending is not None:
    pending = st.session_state.schedule_pending
    time_label = pending["scheduled_at"][5:16]
    st.info(f"预定「{pending['keyword']}」在 {time_label}，要加入预定吗？")
    col_yes, col_no = st.columns(2)
    with col_yes:
        def _confirm_schedule():
            p = st.session_state.schedule_pending
            create_scheduled_task(
                keyword=p["keyword"], scheduled_at=p["scheduled_at"],
                combo=p["combo"], energy_level=p["energy_level"],
                suggested_minutes=p["suggested_minutes"], task_type=p["task_type"],
            )
            add_message("assistant", f"好的，「{p['keyword']}」已预定在 {p['scheduled_at'][5:16]}～")
            st.session_state.schedule_pending = None
        st.button("预定", key="btn_confirm_schedule", type="primary", on_click=_confirm_schedule)
    with col_no:
        def _cancel_schedule():
            p = st.session_state.schedule_pending
            if p:
                st.session_state.schedule_dismissed.add(f"{p['keyword']}|{p['scheduled_at']}")
            st.session_state.schedule_pending = None
        st.button("不用了", key="btn_cancel_schedule", on_click=_cancel_schedule)

# ---------- 任务执行面板 ----------
if st.session_state.active_task is not None:
    task = st.session_state.active_task
    status_label = "执行中" if task["status"] == "executing" else "已暂停"
    duration_text = f"建议 {task['default_minutes']} 分钟" if task.get("default_minutes") else "无时长限制"

    st.info(f"当前任务：**{task['keyword']}**　｜　{status_label}　｜　{duration_text}")

    if task["status"] == "executing":
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.button("暂停", key="btn_pause", on_click=on_pause)
        with col2:
            st.button("完成", key="btn_complete", type="primary", on_click=on_complete)
        with col3:
            st.button("放弃", key="btn_abandon", on_click=on_abandon)
        with col4:
            st.button("换时长", key="btn_duration", on_click=on_change_duration)
    elif task["status"] == "paused":
        col1, col2 = st.columns(2)
        with col1:
            st.button("继续", key="btn_resume", type="primary", on_click=on_resume)
        with col2:
            st.button("放弃", key="btn_abandon", on_click=on_abandon)

# ---------- 渲染当前推荐的操作按钮 ----------
elif st.session_state.last_ai_response is not None and not st.session_state.energy_confirm_pending:
    resp = st.session_state.last_ai_response
    if should_show_action_buttons(resp):
        col1, col2 = st.columns(2)
        with col1:
            st.button("开始", key="btn_accept", type="primary", on_click=on_accept)
        with col2:
            st.button("换一个", key="btn_switch", on_click=on_switch)

# ---------- 处理"换一个"的 AI 调用 ----------
if st.session_state.get("pending_switch"):
    rejected = st.session_state.pending_switch
    st.session_state.pending_switch = None
    add_message("assistant", "好的，换一个～")

    energy_now = st.session_state.energy["energy_level"]
    try:
        with st.chat_message("assistant"):
            with st.spinner("小白正在想..."):
                history = st.session_state.messages[:-1]
                done_tasks = [t["keyword"] for t in get_today_tasks() if t["status"] == "completed"]
                switch_input = f"用户拒绝了「{rejected}」，请推荐一个不同的具体行动"
                memo = get_user_memo()
                ai_memo_text = get_ai_memo()
                daily_memo_text = get_filtered_daily_memo()
                new_resp = call_ai(switch_input, energy_now, chat_history=history,
                                   persona=st.session_state.persona,
                                   completed_tasks=done_tasks if done_tasks else None,
                                   user_memo=memo, ai_memo=ai_memo_text,
                                   daily_memo=daily_memo_text)
                # 换推荐走干活模式校验（不管 AI 返回什么模式）
                if new_resp.get("mode") == "task":
                    is_valid, final_reply = validate_reply(new_resp, energy_now)
                    if not is_valid:
                        new_resp["reply"] = final_reply
    except Exception as e:
        logging.error(f"换推荐失败: {type(e).__name__}: {e}")
        new_resp = {"mode": "chat", "reply": "换推荐时出了点问题，你跟我说说想做什么吧～"}

    add_message("assistant", new_resp["reply"])
    if new_resp.get("mode") == "task" and should_show_action_buttons(new_resp):
        st.session_state.last_ai_response = new_resp
    else:
        st.session_state.last_ai_response = None
    st.rerun()

# ---------- 用户输入 ----------
user_input = st.chat_input("跟我说说你现在的状态或想做的事...")

if user_input:
    add_message("user", user_input)

    # 立即渲染用户消息
    with st.chat_message("user"):
        st.markdown(user_input)

    energy_now = st.session_state.energy["energy_level"]

    # AI 思考中显示加载提示
    needs_confirm = False
    try:
        with st.chat_message("assistant"):
            with st.spinner("小白正在想..."):
                history = st.session_state.messages[:-1]
                done_tasks = [t["keyword"] for t in get_today_tasks() if t["status"] == "completed"]
                memo = get_user_memo()
                ai_memo_text = get_ai_memo()
                daily_memo_text = get_filtered_daily_memo()
                ai_response = call_ai(user_input, energy_now, chat_history=history,
                                      persona=st.session_state.persona,
                                      completed_tasks=done_tasks if done_tasks else None,
                                      user_memo=memo, ai_memo=ai_memo_text,
                                      daily_memo=daily_memo_text)
    except Exception as e:
        logging.error(f"AI 处理流程出错: {type(e).__name__}: {e}")
        ai_response = {"mode": "chat", "reply": "哎呀，出了点小问题。你再说一次？"}

    # 根据 mode 走不同分支
    if ai_response.get("mode") == "task":
        # 干活模式：走守门校验 + 精力感知 + 按钮 + 预定任务
        _, needs_confirm = check_energy_drift(ai_response, energy_now)
        is_valid, final_reply = validate_reply(ai_response, energy_now)
        if not is_valid:
            ai_response["reply"] = final_reply

    # 添加回复消息
    add_message("assistant", ai_response["reply"])

    # 以下只在干活模式下处理
    if ai_response.get("mode") == "task":
        # 预定任务：AI 返回 scheduled_at 时，检查是否已存在，不重复弹确认
        if ai_response.get("scheduled_at") and ai_response.get("scheduled_keyword"):
            existing = get_scheduled_tasks()
            already_exists = any(
                t["keyword"] == ai_response["scheduled_keyword"]
                and t.get("scheduled_at", "").startswith(ai_response["scheduled_at"])
                for t in existing
            )
            dismiss_key = f"{ai_response['scheduled_keyword']}|{ai_response['scheduled_at']}"
            if already_exists or dismiss_key in st.session_state.schedule_dismissed:
                ai_response["scheduled_at"] = None
                ai_response["scheduled_keyword"] = None

        if ai_response.get("scheduled_at") and ai_response.get("scheduled_keyword"):
            st.session_state.schedule_pending = {
                "keyword": ai_response["scheduled_keyword"],
                "scheduled_at": ai_response["scheduled_at"],
                "combo": ai_response.get("combo", ""),
                "energy_level": energy_now,
                "suggested_minutes": ai_response.get("suggested_minutes"),
                "task_type": ai_response.get("task_type", "work"),
            }

        # 设置按钮状态
        if should_show_action_buttons(ai_response):
            st.session_state.last_ai_response = ai_response
        else:
            st.session_state.last_ai_response = None

        if needs_confirm:
            st.session_state.energy_confirm_pending = True
    else:
        # 聊天模式：不展示按钮，不触发校验
        st.session_state.last_ai_response = None

    # 每轮轻量匹配：用户输入命中已有记忆关键词时更新计数（零 API 成本）
    try:
        bump_on_mention(user_input)
    except Exception as e:
        logging.error(f"记忆关键词匹配失败: {type(e).__name__}: {e}")

    # 每 5 轮用户消息触发一次 AI 记忆更新
    st.session_state.msg_count += 1
    if st.session_state.msg_count % 5 == 0:
        try:
            update_ai_memory(st.session_state.messages)
        except Exception as e:
            logging.error(f"AI 记忆更新失败: {type(e).__name__}: {e}")

    st.rerun()
