from gitten.telegram_config import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_SESSION_PATH,
    GITTEN_DIR,
    load_config,
    save_config,
)


def test_default_paths_live_outside_the_project(tmp_path):
    # The whole point of the v1.3 security requirement: credentials and the
    # session must never resolve into a path under the repo checkout.
    repo_root = tmp_path  # stand-in for "the project folder"
    assert repo_root not in GITTEN_DIR.parents
    assert str(GITTEN_DIR) not in str(repo_root)
    assert GITTEN_DIR.name == ".gitten"
    assert DEFAULT_CONFIG_PATH.parent == GITTEN_DIR
    assert DEFAULT_SESSION_PATH.parent == GITTEN_DIR


def test_load_config_missing_file_returns_none(tmp_path):
    assert load_config(tmp_path / "does_not_exist.json") is None


def test_load_config_invalid_json_returns_none(tmp_path):
    path = tmp_path / "telegram_config.json"
    path.write_text("not valid json", encoding="utf-8")
    assert load_config(path) is None


def test_load_config_missing_keys_returns_none(tmp_path):
    path = tmp_path / "telegram_config.json"
    path.write_text('{"api_id": 12345}', encoding="utf-8")
    assert load_config(path) is None


def test_save_then_load_round_trips(tmp_path):
    path = tmp_path / "nested" / "telegram_config.json"
    save_config(12345, "abcdef0123456789abcdef0123456789", path)

    loaded = load_config(path)

    assert loaded == {"api_id": 12345, "api_hash": "abcdef0123456789abcdef0123456789"}


def test_save_config_creates_parent_directory(tmp_path):
    path = tmp_path / "a" / "b" / "c" / "telegram_config.json"
    save_config(1, "hash", path)
    assert path.exists()


def test_save_config_coerces_api_id_to_int_on_load(tmp_path):
    # Guards against a hand-edited config file where api_id was typed as a
    # string -- should still load cleanly rather than breaking Telethon.
    path = tmp_path / "telegram_config.json"
    path.write_text('{"api_id": "12345", "api_hash": "x"}', encoding="utf-8")
    assert load_config(path) == {"api_id": 12345, "api_hash": "x"}
