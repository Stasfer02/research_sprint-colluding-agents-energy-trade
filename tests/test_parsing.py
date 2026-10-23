import json

import pytest

from desks.agents import COMPLIANCE_TEXT, LLMDesk, extract_json
from desks.agents_base import Observation
from desks.config import run_config_from_dict
from desks.llm import BudgetGuard, FakeBackend, LLMClient

from fake_llm import valid_responder


@pytest.mark.parametrize(
    "text,expected",
    [
        ('{"a": 1}', {"a": 1}),
        ('Sure! {"a": 1, "b": "x}y"} trailing', {"a": 1, "b": "x}y"}),
        ('```json\n{"a": {"b": 2}}\n```', {"a": {"b": 2}}),
        ('{bad json} then {"a": 3}', {"a": 3}),
        ('{"s": "quote \\" and { brace"}', {"s": 'quote " and { brace'}),
        ("no json here", None),
        ("", None),
        ("[1, 2]", None),
    ],
)
def test_extract_json(text, expected):
    assert extract_json(text) == expected


def _client(tmp_path, responder, budget=100.0):
    cfg = run_config_from_dict({}).llm
    guard = BudgetGuard(tmp_path / "ledger.json", budget, cfg.prices)
    return LLMClient(cfg, FakeBackend(responder), guard)


def _obs(role="brp", t=1):
    return Observation(firm="A", role=role, t=t, T=30, S_prev=0.0, public_history=[], own_history=[], cum_profit=0.0, profit_label="Firm A total profit")


def _desk(tmp_path, responder, role="brp", **cfg_over):
    cfg = run_config_from_dict(cfg_over)
    return LLMDesk("A", role, cfg, _client(tmp_path, responder))


def test_desk_parses_and_clamps(tmp_path):
    def resp(system, messages, model):
        return json.dumps({"deviation_mw": 99, "public_post": "x" * 500, "private_message": "secret", "notes": "w " * 300})
    desk = _desk(tmp_path, resp)
    a = desk.act(_obs())
    assert a.parse_ok and a.deviation == 25.0
    assert len(a.public_post) == 300
    assert a.private_message is None  # channel is public only
    assert len(a.notes.split()) == 120
    assert desk.notes == a.notes


def test_desk_retries_then_succeeds(tmp_path):
    calls = []

    def resp(system, messages, model):
        calls.append(messages)
        return "I think I will deviate a bit" if len(calls) == 1 else '{"deviation_mw": -3}'
    a = _desk(tmp_path, resp).act(_obs())
    assert a.parse_ok and a.deviation == -3
    assert len(calls) == 2 and calls[1][-1]["content"] == "Return only valid JSON."
    assert len(a.io) == 2


def test_desk_falls_back_to_previous_then_default(tmp_path):
    answers = iter(['{"up_bid": 95, "down_bid": 30}', "garbage", "garbage"])
    desk = _desk(tmp_path, lambda *_: next(answers), role="bsp")
    first = desk.act(_obs("bsp", 1))
    assert first.parse_ok and first.up_bid == 95
    second = desk.act(_obs("bsp", 2))
    assert not second.parse_ok and (second.up_bid, second.down_bid) == (95, 30)
    fresh = _desk(tmp_path, lambda *_: "nope", role="bsp")
    a = fresh.act(_obs("bsp", 1))
    assert not a.parse_ok and (a.up_bid, a.down_bid) == (70.0, 55.0)


def test_missing_field_is_parse_failure(tmp_path):
    a = _desk(tmp_path, lambda *_: '{"up_bid": 80}', role="bsp").act(_obs("bsp"))
    assert not a.parse_ok


def test_system_prompt_variants(tmp_path):
    base = _desk(tmp_path, valid_responder, regulator={"enforcement": "none"}, channel={"channel": "none"}).system
    assert COMPLIANCE_TEXT not in base and "Public Board" not in base and "Private Channel" not in base
    assert "total profit of Firm A" in base
    enforced = _desk(tmp_path, valid_responder, regulator={"enforcement": "talk"}).system
    stated = _desk(tmp_path, valid_responder, regulator={"enforcement": "stated"}).system
    assert COMPLIANCE_TEXT in enforced and enforced == stated  # identical text across enforcement levels
    private = _desk(tmp_path, valid_responder, channel={"channel": "public_private"}).system
    assert "Private Channel" in private and "It is not monitored." in private
    coal = _desk(tmp_path, valid_responder, agents={"coalition_instruction": True}).system
    assert "coordinate with other firms" in coal
    sep = _desk(tmp_path, valid_responder, agents={"objective": "separate"}).system
    assert "profit of your own desk" in sep
    bsp = _desk(tmp_path, valid_responder, role="bsp").system
    assert '"up_bid"' in bsp and '"deviation_mw"' not in bsp
