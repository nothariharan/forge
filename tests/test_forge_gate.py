import pytest

from cli.approve import resolve
from core.ledger import Ledger
from tools import forge_gate

GATE = {"gate_id": "G1", "action": "Run E1", "risk": "low", "status": "pending", "policy": "P6"}


def _ledger(tmp_path):
    led = Ledger(tmp_path / "l.db")
    led.append("r", "safety", "GATE_OPENED", GATE, refs={"gate_id": "G1"})
    return led


def test_no_decision_times_out(tmp_path):
    assert forge_gate.wait_for_decision(_ledger(tmp_path), "r", "G1", timeout=0.3, poll=0.1) is None


def test_ui_or_cli_approval_releases_gate(tmp_path):
    led = _ledger(tmp_path)
    e = resolve(led, "r", "G1", approve=True, via="lab-ui")
    assert e["agent"] == "human" and e["payload"]["status"] == "approved"
    assert forge_gate.wait_for_decision(led, "r", "G1", timeout=1, poll=0.1) == "approved"


def test_deny_and_double_resolve(tmp_path):
    led = _ledger(tmp_path)
    resolve(led, "r", "G1", approve=False, via="cli")
    assert forge_gate.wait_for_decision(led, "r", "G1", timeout=1, poll=0.1) == "denied"
    with pytest.raises(SystemExit):
        resolve(led, "r", "G1", approve=True, via="cli")


def test_unapproved_command_is_refused(tmp_path):
    rc = forge_gate.main(["--run-id", "r", "--gate-id", "G1", "--db", str(tmp_path / "l.db"), "--", "python", "rm.py"])
    assert rc == 5


def test_denied_gate_never_runs_command(tmp_path, monkeypatch):
    led = _ledger(tmp_path)
    resolve(led, "r", "G1", approve=False, via="cli")
    ran = []
    monkeypatch.setattr(forge_gate.subprocess, "run", lambda *a, **k: ran.append(a))
    rc = forge_gate.main(["--run-id", "r", "--gate-id", "G1", "--db", str(tmp_path / "l.db"), "--timeout", "1",
                          "--", ".venv/bin/python", "tools/tess_resolution_shift.py"])
    assert rc == 3 and ran == []
