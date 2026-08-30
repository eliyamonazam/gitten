import json

from gitten.focus import (
    DEFAULT_FOCUS_SUBSTRINGS,
    load_focus_substrings,
    matches_focus_process,
)


# -- matches_focus_process ---------------------------------------------------


def test_matches_pytest_default():
    assert matches_focus_process("C:\\venv\\python.exe -m pytest -q")


def test_matches_npm_test_default():
    assert matches_focus_process("npm test")


def test_matches_npm_run_build_default():
    assert matches_focus_process("npm run build")


def test_matches_cargo_test_default():
    assert matches_focus_process("cargo test --all")


def test_matches_go_test_default():
    assert matches_focus_process("go test ./...")


def test_case_insensitive_match():
    assert matches_focus_process("PYTEST -q")


def test_unrelated_process_does_not_match():
    assert not matches_focus_process("notepad.exe untitled.txt")


def test_custom_substrings_override_defaults():
    assert matches_focus_process("make check", substrings=["make check"])
    assert not matches_focus_process("pytest -q", substrings=["make check"])


# -- load_focus_substrings ---------------------------------------------------


def test_load_missing_file_returns_defaults(tmp_path):
    result = load_focus_substrings(tmp_path / "does_not_exist.json")
    assert result == DEFAULT_FOCUS_SUBSTRINGS


def test_load_valid_file_overrides_defaults(tmp_path):
    config = tmp_path / "focus_config.json"
    config.write_text(json.dumps({"substrings": ["make check"]}), encoding="utf-8")
    assert load_focus_substrings(config) == ["make check"]


def test_load_invalid_json_falls_back_to_defaults(tmp_path):
    config = tmp_path / "focus_config.json"
    config.write_text("not valid json", encoding="utf-8")
    assert load_focus_substrings(config) == DEFAULT_FOCUS_SUBSTRINGS
