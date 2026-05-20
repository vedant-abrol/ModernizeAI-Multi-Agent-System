from __future__ import annotations

from app.config import Settings, _load_dotenv


def test_dotenv_overrides_inherited_bedrock_model(tmp_path, monkeypatch) -> None:
    (tmp_path / ".env").write_text(
        "BEDROCK_CHAT_MODEL_ID=us.anthropic.claude-opus-4-6-v1\n",
        encoding="utf-8",
    )

    with monkeypatch.context() as scoped:
        scoped.chdir(tmp_path)
        scoped.setenv("BEDROCK_CHAT_MODEL_ID", "us.anthropic.claude-sonnet-4-6")

        _load_dotenv()

        assert Settings().bedrock_chat_model_id == "us.anthropic.claude-opus-4-6-v1"


def test_settings_reads_environment_when_instantiated(monkeypatch) -> None:
    monkeypatch.setenv("BEDROCK_CHAT_MODEL_ID", "us.anthropic.claude-opus-4-6-v1")

    assert Settings().bedrock_chat_model_id == "us.anthropic.claude-opus-4-6-v1"
