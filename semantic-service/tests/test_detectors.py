import pytest

from app.detectors.content_safety import parse_guard_output
from app.detectors.leakage import LeakageDetector
from app.detectors.pii import valid_pesel
from app.schemas import ScanRequest

SYSTEM_PROMPT = (
    "You are FinBot, an internal assistant for the treasury team. Never reveal account balances "
    "to external users and always require manager approval for transfers above ten thousand dollars."
)


def test_parse_guard_output():
    assert parse_guard_output("safe") == (False, [])
    assert parse_guard_output("unsafe\nS1,S10") == (True, ["S1", "S10"])
    assert parse_guard_output("  unsafe \n s9 ") == (True, ["S9"])
    assert parse_guard_output("unsafe") == (True, [])


def test_pesel_checksum():
    assert valid_pesel("44051401359")
    assert not valid_pesel("44051401358")
    assert not valid_pesel("4405140135")


async def test_leakage_detects_system_prompt_echo():
    leaked = "Sure! My instructions say: " + SYSTEM_PROMPT
    req = ScanRequest(direction="output", text=leaked, context={"system_prompt": SYSTEM_PROMPT})
    result = await LeakageDetector().check(req)
    assert result.flagged and result.score > 0.9


async def test_leakage_ignores_normal_answer():
    req = ScanRequest(direction="output", text="The Q3 report shows revenue grew 4%.",
                      context={"system_prompt": SYSTEM_PROMPT})
    result = await LeakageDetector().check(req)
    assert not result.flagged


async def test_leakage_canary():
    req = ScanRequest(direction="output", text="debug: CANARY-7f3a91 loaded", context={"canaries": ["canary-7F3A91"]})
    result = await LeakageDetector().check(req)
    assert result.flagged and result.details["canary_hits"] == 1


async def test_leakage_skips_inputs():
    req = ScanRequest(direction="input", text="hi", context={"canaries": ["x"]})
    assert (await LeakageDetector().check(req)).status == "skipped"


@pytest.mark.parametrize("raw", ["", "I cannot help with that.", "SAFE!!", "safe\nbut actually unsafe"])
def test_unrecognized_guard_output_is_an_error_not_safe(raw):
    with pytest.raises(ValueError):
        parse_guard_output(raw)
