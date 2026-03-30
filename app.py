import streamlit as st
import uuid
from db.database import (
    init_db, save_action_log, get_user_memo, save_user_memo,
    save_chat_message, load_session_messages,
)
from core.energy import get_current_energy, update_energy, ENERGY_LEVELS
from core.intent import call_ai
from core.rules_engine import (
    validate_reply, check_energy_drift, should_show_action_buttons, get_follow_up,
)
from core.task_manager import (
    create_task, pause_task, resume_task, complete_task, abandon_task,
    get_active_task, update_task_minutes, get_today_tasks,
    create_recurring_task, get_recurring_tasks, delete_recurring_task,
    spawn_daily_tasks, start_idle_task,
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
        greeting = "你好呀～我是小管家，你的 AI 小管家。今天想做点什么？"
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

    if done:
        st.sidebar.markdown("**── 已完成 ──**")
        work_done = [t for t in done if t.get("task_type", "work") == "work"]
        rest_done = [t for t in done if t.get("task_type") == "rest"]
        if work_done:
            st.sidebar.markdown("📚 工作/学习")
            for t in work_done:
                duration_text = f" · {t['default_minutes']}min" if t.get("default_minutes") else ""
                st.sidebar.markdown(f"　　✅ {t['keyword']}{duration_text}")
        if rest_done:
            st.sidebar.markdown("🌿 休息")
            for t in rest_done:
                duration_text = f" · {t['default_minutes']}min" if t.get("default_minutes") else ""
                st.sidebar.markdown(f"　　✅ {t['keyword']}{duration_text}")
else:
    st.sidebar.caption("还没有任务，跟小管家聊聊吧～")

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
with st.sidebar.expander("我的记忆库"):
    current_memo = get_user_memo()
    new_memo = st.text_area(
        "写下你的背景信息，小管家会记住",
        value=current_memo,
        placeholder="例如：我是大三学生，正在准备考研，主要科目是数学和英语。上午效率比较高，下午容易犯困。",
        height=120,
        key="memo_input",
    )
    if st.button("保存", key="btn_save_memo"):
        save_user_memo(new_memo)
        st.success("已保存！")


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
    """用户点击"开始"——创建任务并进入执行状态。"""
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


@safe_callback
def on_switch():
    """用户点击"换一个"——追问原因，不调 API。"""
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
    follow_up = get_follow_up()
    add_message("assistant", follow_up)
    st.session_state.last_ai_response = None  # 清除按钮状态，用户回答后走完整流程


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

# ---------- 用户输入 ----------
user_input = st.chat_input("跟我说说你现在的状态或想做的事...")

if user_input:
    add_message("user", user_input)

    # 立即渲染用户消息
    with st.chat_message("user"):
        st.markdown(user_input)

    energy_now = st.session_state.energy["energy_level"]

    # AI 思考中显示加载提示
    try:
        with st.chat_message("assistant"):
            with st.spinner("小管家正在想..."):
                history = st.session_state.messages[:-1]
                done_tasks = [t["keyword"] for t in get_today_tasks() if t["status"] == "completed"]
                memo = get_user_memo()
                ai_response = call_ai(user_input, energy_now, chat_history=history,
                                      completed_tasks=done_tasks if done_tasks else None,
                                      user_memo=memo)

                # 精力值动态感知
                _, needs_confirm = check_energy_drift(ai_response, energy_now)

                # 守门校验
                is_valid, final_reply = validate_reply(ai_response, energy_now)
                if not is_valid:
                    ai_response["reply"] = final_reply
    except Exception as e:
        logging.error(f"AI 处理流程出错: {type(e).__name__}: {e}")
        ai_response = {"reply": "哎呀，出了点小问题。你再说一次？", "combo": "C"}
        needs_confirm = False

    # 添加回复消息
    add_message("assistant", ai_response["reply"])

    # 设置状态
    if should_show_action_buttons(ai_response):
        st.session_state.last_ai_response = ai_response
    else:
        st.session_state.last_ai_response = None

    if needs_confirm:
        st.session_state.energy_confirm_pending = True

    st.rerun()
