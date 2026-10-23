import json
from pathlib import Path

from hgs2_lab import __version__
from hgs2_lab.config import LabConfig
from hgs2_lab.metadata import REDACTED, build_run_metadata, environment_info, redact, scenario_snapshot
from hgs2_lab.scenarios import Scenario

SECRET = "s3cr3t-value-123"


def secret_scenario():
    return Scenario(
        name="login",
        method="POST",
        path="/login",
        headers={"Authorization": f"Bearer {SECRET}", "X-Api-Key": SECRET, "Accept": "application/json"},
        body={"username": "u", "password": SECRET, "nested": {"refresh_token": SECRET}, "items": [{"cookie": SECRET}]},
        expected_status=(200,),
    )


def test_redact_masks_sensitive_keys_recursively_without_mutating_input():
    original = {"password": "p", "a": {"Token": "t"}, "l": [{"secret": "s"}], "ok": 1}
    result = redact(original)
    assert result == {"password": REDACTED, "a": {"Token": REDACTED}, "l": [{"secret": REDACTED}], "ok": 1}
    assert original["password"] == "p"


def test_scenario_snapshot_hides_secrets_but_keeps_other_fields():
    snap = scenario_snapshot(secret_scenario())
    assert SECRET not in json.dumps(snap)
    assert snap["headers"]["Accept"] == "application/json"
    assert snap["body"]["username"] == "u"
    assert snap["name"] == "login" and snap["expected_status"] == [200]


def test_run_metadata_contents_and_no_secrets():
    config = LabConfig(base_url="http://localhost:8080", output_dir=Path("o"), scenarios_file=Path("s"))
    meta = build_run_metadata(config, [secret_scenario()], "2026-01-01T00:00:00+00:00", "2026-01-01T00:01:00+00:00")
    assert set(meta) == {"tool_version", "started_at", "finished_at", "environment", "config", "scenarios"}
    assert meta["tool_version"] == __version__
    assert meta["config"]["base_url"] == "http://localhost:8080"
    assert len(meta["scenarios"]) == 1
    assert SECRET not in json.dumps(meta)


def test_environment_info_keys():
    info = environment_info()
    assert {"python_version", "python_implementation", "platform", "machine", "cpu_count"} <= set(info)
    json.dumps(info)
