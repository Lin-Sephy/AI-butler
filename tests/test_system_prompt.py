from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from prompts.system_prompt import PERSONA_infp, build_chat_message, get_chat_prompt


CN_TZ = timezone(timedelta(hours=8))


def test_build_chat_message_includes_weekday():
    now = datetime(2026, 5, 22, 17, 16, tzinfo=CN_TZ)

    with patch("db.database.now_cn", return_value=now):
        message = build_chat_message("今天不是周五吗")

    assert "当前时间：2026-05-22 17:16，星期五" in message


def test_get_chat_prompt_defaults_to_preset_one():
    prompt = get_chat_prompt(custom_persona="")

    assert PERSONA_infp in prompt


def test_get_chat_prompt_uses_custom_persona_when_provided():
    custom = "说话更直接，但不要冷冰冰。"

    prompt = get_chat_prompt(custom_persona=custom)

    assert custom in prompt
    assert PERSONA_infp not in prompt
