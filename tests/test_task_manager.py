"""任务日边界相关纯逻辑测试。"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from core.task_manager import _sweep_finished_focus_tasks, _task_day_start

CN_TZ = timezone(timedelta(hours=8))


def test_task_day_before_4am_belongs_to_previous_day():
    now = datetime(2026, 5, 15, 3, 59, tzinfo=CN_TZ)

    assert _task_day_start(now) == datetime(2026, 5, 14, 4, 0, tzinfo=CN_TZ)


def test_task_day_at_4am_starts_new_day():
    now = datetime(2026, 5, 15, 4, 0, tzinfo=CN_TZ)

    assert _task_day_start(now) == datetime(2026, 5, 15, 4, 0, tzinfo=CN_TZ)


def test_sweep_finished_focus_tasks_completes_expired_countdown():
    now = datetime(2026, 5, 15, 12, 0, tzinfo=CN_TZ)
    rows = [{
        "id": 1,
        "started_at": "2026-05-15T10:30:00+08:00",
        "default_minutes": 90,
    }]

    with patch("core.task_manager.now_cn", return_value=now), \
         patch("core.task_manager._get", return_value=rows), \
         patch("core.task_manager._patch") as patch_task:
        _sweep_finished_focus_tasks("user-1")

    patch_task.assert_called_once()
    assert patch_task.call_args.args[2]["status"] == "completed"
    assert patch_task.call_args.args[2]["completed_at"] == "2026-05-15T12:00:00+08:00"


def test_sweep_finished_focus_tasks_keeps_running_countdown():
    now = datetime(2026, 5, 15, 11, 59, tzinfo=CN_TZ)
    rows = [{
        "id": 1,
        "started_at": "2026-05-15T10:30:00+08:00",
        "default_minutes": 90,
    }]

    with patch("core.task_manager.now_cn", return_value=now), \
         patch("core.task_manager._get", return_value=rows), \
         patch("core.task_manager._patch") as patch_task:
        _sweep_finished_focus_tasks("user-1")

    patch_task.assert_not_called()


def test_sweep_finished_focus_tasks_ignores_open_timer():
    now = datetime(2026, 5, 15, 12, 0, tzinfo=CN_TZ)
    rows = [{
        "id": 1,
        "started_at": "2026-05-15T10:30:00+08:00",
        "default_minutes": None,
    }]

    with patch("core.task_manager.now_cn", return_value=now), \
         patch("core.task_manager._get", return_value=rows), \
         patch("core.task_manager._patch") as patch_task:
        _sweep_finished_focus_tasks("user-1")

    patch_task.assert_not_called()
