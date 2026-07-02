"""Tests for conda_dev_request_headers.plugin."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

from conda_dev_request_headers.headers import INLINE_RULES_ENV_VAR
from conda_dev_request_headers.plugin import (
    conda_request_headers,
    conda_session_headers,
    conda_settings,
)


def header_pairs(headers):
    return [(header.name, header.value) for header in headers]


def test_conda_session_headers_reads_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TOKEN", "token")
    monkeypatch.setenv(
        INLINE_RULES_ENV_VAR, 'repo.anaconda.com Authorization "Bearer ${TOKEN}"'
    )

    headers = header_pairs(conda_session_headers("repo.anaconda.com"))

    assert headers == [("authorization", "Bearer token")]


def test_conda_request_headers_reads_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        INLINE_RULES_ENV_VAR,
        "repo.anaconda.com/private X-Scope private",
    )

    headers = header_pairs(
        conda_request_headers("repo.anaconda.com", "/private/noarch")
    )

    assert headers == [("x-scope", "private")]


def test_conda_settings_registers_plugin_settings() -> None:
    items = {setting.name: setting for setting in conda_settings()}

    assert "dev_request_headers" in items
    assert "dev_request_headers_file" in items
    assert items["dev_request_headers"].description
    assert items["dev_request_headers_file"].description
