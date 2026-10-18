import json

from mini_agent.cli import main


def test_demo_cli_emits_machine_readable_events(tmp_path, capsys):
    assert main(["demo", "--workspace", str(tmp_path / "demo"), "--json-events"]) == 0
    captured = capsys.readouterr()
    events = [json.loads(line) for line in captured.out.splitlines()]
    assert events[-1]["kind"] == "done"
    assert events[-1]["data"]["reason"] == "completed"
    assert "不代表真实模型验收" in captured.err


def test_demo_rerun_refuses_to_overwrite(tmp_path, capsys):
    args = ["demo", "--workspace", str(tmp_path / "demo")]
    assert main(args) == 0
    path = tmp_path / "demo" / "hello.py"
    original = path.read_bytes()
    assert main(args) == 2
    assert path.read_bytes() == original


def test_missing_key_does_not_start_live_request(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert main(["run", "--live", "--workspace", str(tmp_path), "--task", "hello"]) == 2
    assert "DEEPSEEK_API_KEY" in capsys.readouterr().out
