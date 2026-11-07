"""`hermes send --edit`: in-place Telegram edits via editMessageText (telegram package stubbed)."""

from __future__ import annotations

import asyncio
import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from tools import send_message_senders as senders


def _install_telegram(monkeypatch, bot):
    parse_mode = SimpleNamespace(MARKDOWN_V2="MarkdownV2", HTML="HTML")
    constants = SimpleNamespace(ParseMode=parse_mode)
    monkeypatch.setitem(sys.modules, "telegram", SimpleNamespace(Bot=lambda **_kw: bot, constants=constants))
    monkeypatch.setitem(sys.modules, "telegram.constants", constants)
    monkeypatch.setattr(senders, "_telegram_bot", lambda token: bot)


def _bot(**kw):
    bot = MagicMock()
    bot.edit_message_text = AsyncMock(**({"return_value": SimpleNamespace(message_id=4711)} | kw))
    return bot


def test_edit_calls_edit_message_text_with_numeric_ids(monkeypatch):
    bot = _bot()
    _install_telegram(monkeypatch, bot)
    result = asyncio.run(senders._edit_telegram("tok", "-1001", "4711", "build 3/8"))
    assert result["success"] and result["edited"] and result["message_id"] == "4711"
    kwargs = bot.edit_message_text.await_args.kwargs
    assert kwargs["message_id"] == 4711 and kwargs["chat_id"] == -1001
    bot.send_message.assert_not_called()


def test_not_modified_is_success(monkeypatch):
    bot = _bot(side_effect=Exception("Bad Request: message is not modified"))
    _install_telegram(monkeypatch, bot)
    result = asyncio.run(senders._edit_telegram("tok", "-1001", "4711", "same"))
    assert result["success"] and result["unchanged"]


def test_parse_error_falls_back_to_plain_text(monkeypatch):
    calls = []

    async def edit(**kw):
        calls.append(kw["parse_mode"])
        if kw["parse_mode"] is not None:
            raise Exception("Can't parse entities")
        return SimpleNamespace(message_id=4711)

    bot = MagicMock()
    bot.edit_message_text = edit
    _install_telegram(monkeypatch, bot)
    result = asyncio.run(senders._edit_telegram("tok", "-1001", "4711", "a_b*c"))
    assert result["success"] and calls[-1] is None and len(calls) == 2


def test_too_long_text_is_an_error_not_truncated(monkeypatch):
    bot = _bot()
    _install_telegram(monkeypatch, bot)
    result = asyncio.run(senders._edit_telegram("tok", "-1001", "4711", "x" * 5000))
    assert "error" in result and "4096" in result["error"]
    bot.edit_message_text.assert_not_called()


def test_non_numeric_message_id_is_rejected(monkeypatch):
    bot = _bot()
    _install_telegram(monkeypatch, bot)
    result = asyncio.run(senders._edit_telegram("tok", "-1001", "abc", "x"))
    assert "numeric" in result["error"]


def test_other_errors_are_reported_not_swallowed(monkeypatch):
    bot = _bot(side_effect=Exception("Bad Request: message to edit not found"))
    _install_telegram(monkeypatch, bot)
    result = asyncio.run(senders._edit_telegram("tok", "-1001", "4711", "x"))
    assert "error" in result and "not found" in result["error"]


def test_edit_action_refuses_non_telegram_targets():
    from tools.send_message_tool import send_message_tool
    out = json.loads(send_message_tool({"action": "edit", "target": "discord:#ops", "message": "x", "message_id": "1"}))
    assert "only supported for telegram" in out["error"]


def test_edit_action_requires_message_id():
    from tools.send_message_tool import send_message_tool
    out = json.loads(send_message_tool({"action": "edit", "target": "telegram", "message": "x"}))
    assert "message_id" in out["error"]
