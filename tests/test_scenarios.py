import json

import pytest

from hgs2_lab.scenarios import Scenario, ScenarioError, load_scenarios, scenario_from_dict

VALID = {"name": "a", "method": "GET", "path": "/x"}


def test_from_dict_defaults_and_method_normalized():
    s = scenario_from_dict({**VALID, "method": "get"})
    assert s.method == "GET"
    assert s.repetitions == 1
    assert s.delay_seconds == 0.0
    assert s.headers == {} and s.body is None
    assert s.expected_status == ()


def test_from_dict_full():
    s = scenario_from_dict(
        {**VALID, "method": "POST", "repetitions": 3, "delay_seconds": 0.5,
         "headers": {"X-Test": "1"}, "body": {"k": 1}, "expected_status": [200, 201]}
    )
    assert s.expected_status == (200, 201)
    assert s.body == {"k": 1}


def test_expected_status_semantics():
    default = Scenario(name="a", method="GET", path="/x")
    assert default.is_expected_status(200) and default.is_expected_status(204)
    assert not default.is_expected_status(301) and not default.is_expected_status(500)
    custom = Scenario(name="a", method="GET", path="/x", expected_status=(404,))
    assert custom.is_expected_status(404)
    assert not custom.is_expected_status(200)


@pytest.mark.parametrize(
    "override",
    [
        {"name": 5}, {"name": ""},
        {"method": 5}, {"method": "TRACE"},
        {"path": 5}, {"path": "x"}, {"path": "//x"}, {"path": "/a b"},
        {"repetitions": 0}, {"repetitions": -1}, {"repetitions": 2.7}, {"repetitions": True}, {"repetitions": "3"},
        {"delay_seconds": -1}, {"delay_seconds": float("nan")}, {"delay_seconds": float("inf")},
        {"delay_seconds": "1"}, {"delay_seconds": True},
        {"headers": 5}, {"headers": {"A": 1}}, {"headers": {1: "x"}}, {"headers": {"bad name": "v"}},
        {"body": []}, {"body": "x"},
        {"expected_status": 200}, {"expected_status": [True]}, {"expected_status": [99]},
        {"expected_status": [600]}, {"expected_status": ["200"]},
        {"unknown_key": 1},
    ],
)
def test_invalid_scenario_dict(override):
    with pytest.raises(ScenarioError):
        scenario_from_dict({**VALID, **override})


@pytest.mark.parametrize("data", ["x", 5, None, ["a"]])
def test_non_dict_scenario_rejected(data):
    with pytest.raises(ScenarioError):
        scenario_from_dict(data)


@pytest.mark.parametrize("missing", ["name", "method", "path"])
def test_missing_required_field(missing):
    data = {k: v for k, v in VALID.items() if k != missing}
    with pytest.raises(ScenarioError, match=missing):
        scenario_from_dict(data)


def test_direct_construction_requires_uppercase_method():
    with pytest.raises(ScenarioError):
        Scenario(name="a", method="get", path="/x")


def write(tmp_path, data):
    p = tmp_path / "s.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_load_scenarios(tmp_path):
    p = write(tmp_path, {"scenarios": [VALID, {**VALID, "name": "b", "method": "POST", "body": {"k": 1}}]})
    result = load_scenarios(p)
    assert [s.name for s in result] == ["a", "b"]
    assert result[1].body == {"k": 1}


def test_duplicate_names(tmp_path):
    with pytest.raises(ScenarioError, match="benzersiz"):
        load_scenarios(write(tmp_path, {"scenarios": [VALID, VALID]}))


@pytest.mark.parametrize(
    "data",
    [{}, {"scenarios": {}}, {"scenarios": []}, {"scenarios": [VALID], "extra": 1}, {"scenarios": [VALID, 5]}, []],
)
def test_invalid_scenario_file_structure(tmp_path, data):
    with pytest.raises(ScenarioError):
        load_scenarios(write(tmp_path, data))


def test_missing_file(tmp_path):
    with pytest.raises(ScenarioError, match="bulunamadı"):
        load_scenarios(tmp_path / "yok.json")


def test_invalid_json(tmp_path):
    p = tmp_path / "s.json"
    p.write_text("{", encoding="utf-8")
    with pytest.raises(ScenarioError, match="JSON"):
        load_scenarios(p)


def test_path_is_directory(tmp_path):
    with pytest.raises(ScenarioError):
        load_scenarios(tmp_path)
