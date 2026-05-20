from __future__ import annotations

from app.guardrails.secret_redactor import redact_secrets


def test_spring_datasource_password_is_redacted() -> None:
    assert redact_secrets("spring.datasource.password=abc123") == "spring.datasource.password=<REDACTED>"


def test_aws_access_key_is_redacted() -> None:
    fake_access_key = "AKIA" + "ABCDEFGHIJKLMNOP"
    text = f"aws.key={fake_access_key}"
    assert "AKIA" not in redact_secrets(text)


def test_jwt_secret_is_redacted() -> None:
    assert redact_secrets("jwt.secret=my-secret") == "jwt.secret=<REDACTED>"


def test_normal_code_remains_unchanged() -> None:
    code = "public class Demo { private String name; }"
    assert redact_secrets(code) == code
