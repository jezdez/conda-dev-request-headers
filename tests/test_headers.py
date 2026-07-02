"""Tests for conda_dev_request_headers.headers."""

from __future__ import annotations

import pytest

from conda_dev_request_headers.headers import (
    INLINE_RULES_ENV_VAR,
    RULES_FILE_ENV_VAR,
    HeaderConfig,
    HeaderRule,
    HeaderSelector,
)


def header_pairs(headers):
    return [(header.name, header.value) for header in headers]


@pytest.mark.parametrize(
    ("selector", "host", "expected"),
    [
        ("*", "repo.anaconda.com", True),
        ("repo.anaconda.com", "repo.anaconda.com", True),
        ("repo.anaconda.com", "Repo.Anaconda.Com", True),
        ("repo.anaconda.com", "repo.anaconda.com:8443", False),
        ("repo.anaconda.com:8443", "repo.anaconda.com:8443", True),
        ("*.example.test", "packages.example.test", True),
        ("*.example.test", "example.test", False),
        ("*.example.test", "other.test", False),
    ],
    ids=[
        "all-hosts",
        "exact-host",
        "case-insensitive",
        "port-must-be-explicit",
        "explicit-port",
        "wildcard-subdomain",
        "wildcard-excludes-root",
        "wildcard-other-domain",
    ],
)
def test_selector_matches_hosts(selector: str, host: str, expected: bool) -> None:
    parsed = HeaderSelector.parse(selector)

    assert parsed is not None
    assert parsed.matches_host(host) is expected


@pytest.mark.parametrize(
    ("selector", "host", "path", "expected"),
    [
        ("repo.anaconda.com/private", "repo.anaconda.com", "/private", True),
        ("repo.anaconda.com/private", "repo.anaconda.com", "/private/noarch", True),
        ("repo.anaconda.com/private", "repo.anaconda.com", "/public/private", False),
        ("https://repo.anaconda.com/private", "repo.anaconda.com", "/private", True),
    ],
    ids=["exact-path", "path-prefix", "wrong-prefix", "url-selector"],
)
def test_selector_matches_request_paths(
    selector: str, host: str, path: str, expected: bool
) -> None:
    parsed = HeaderSelector.parse(selector)

    assert parsed is not None
    assert parsed.matches_request(host, path) is expected


@pytest.mark.parametrize(
    "selector",
    [
        "",
        "/private",
        "ftp://repo.anaconda.com/private",
        "https://user:secret@repo.anaconda.com/private",
        "https://repo.anaconda.com/private?token=secret",
        "https://repo.anaconda.com/private#fragment",
    ],
    ids=[
        "empty",
        "path-only",
        "unsupported-scheme",
        "userinfo",
        "query",
        "fragment",
    ],
)
def test_selector_rejects_unsupported_forms(selector: str) -> None:
    assert HeaderSelector.parse(selector) is None


@pytest.mark.parametrize(
    ("name", "value", "expected"),
    [
        ("Authorization", "Bearer token", True),
        ("X-Api_Key", "token", True),
        ("Bad Header", "value", False),
        ("X-Injected", "one\ntwo", False),
        ("X-Nul", "one\0two", False),
        ("Host", "example.com", False),
        ("Cookie", "secret=value", False),
        ("Proxy-Authorization", "secret", False),
        ("Sec-Fetch-Site", "same-origin", False),
        ("X-HTTP-Method-Override", "TRACE", False),
        ("X-HTTP-Method-Override", "PATCH", True),
    ],
    ids=[
        "authorization",
        "token-header-name",
        "space-in-name",
        "newline-value",
        "nul-value",
        "host-forbidden",
        "cookie-forbidden",
        "proxy-prefix",
        "sec-prefix",
        "forbidden-method-override",
        "allowed-method-override",
    ],
)
def test_header_validation(name: str, value: str, expected: bool) -> None:
    assert HeaderRule.header_is_allowed(name, value) is expected


def test_rule_line_renders_environment_placeholders() -> None:
    rule = HeaderRule.parse_line(
        'repo.anaconda.com Authorization "Bearer ${TOKEN}"',
        {"TOKEN": "secret"},
    )

    assert rule is not None
    assert rule.headers == (("Authorization", "Bearer secret"),)


def test_rule_line_skips_missing_environment_placeholders() -> None:
    assert (
        HeaderRule.parse_line(
            'repo.anaconda.com Authorization "Bearer ${TOKEN}"',
            {},
        )
        is None
    )


def test_config_merges_matching_session_rules_in_order() -> None:
    config = HeaderConfig.from_sources(
        environ={},
        setting_rules=(
            "* X-Env global",
            "* X-Shared global",
            "repo.anaconda.com X-Shared host",
            'repo.anaconda.com Authorization "Bearer token"',
            "other.anaconda.com X-Env other",
            "repo.anaconda.com/private X-Path private",
        ),
    )

    headers = header_pairs(config.session_headers_for("repo.anaconda.com"))

    assert headers == [
        ("x-env", "global"),
        ("x-shared", "host"),
        ("authorization", "Bearer token"),
    ]


def test_config_yields_path_scoped_request_headers() -> None:
    config = HeaderConfig.from_sources(
        environ={},
        setting_rules=(
            "repo.anaconda.com X-Session host",
            "repo.anaconda.com/private X-Path private",
            "*.anaconda.com/private X-Wildcard private",
        ),
    )

    headers = header_pairs(
        config.request_headers_for("repo.anaconda.com", "/private/noarch/repodata.json")
    )

    assert headers == [
        ("x-session", "host"),
        ("x-path", "private"),
        ("x-wildcard", "private"),
    ]


def test_config_ignores_invalid_rules_and_headers() -> None:
    config = HeaderConfig.from_sources(
        environ={},
        setting_rules=(
            "X-Invalid selector",
            'repo.anaconda.com Authorization "Bearer token"',
            "repo.anaconda.com Cookie secret=value",
            "repo.anaconda.com X-Bad 'one\ntwo'",
        ),
    )

    assert header_pairs(config.session_headers_for("repo.anaconda.com")) == [
        ("authorization", "Bearer token")
    ]


def test_config_reads_explicit_environment_file(tmp_path) -> None:
    rules_file = tmp_path / "headers.txt"
    rules_file.write_text(
        'repo.anaconda.com Authorization "Bearer ${TOKEN}"\n',
        encoding="utf-8",
    )

    config = HeaderConfig.from_sources(
        environ={
            RULES_FILE_ENV_VAR: str(rules_file),
            "TOKEN": "secret",
        },
        setting_rules=(),
    )

    assert header_pairs(config.session_headers_for("repo.anaconda.com")) == [
        ("authorization", "Bearer secret")
    ]


def test_config_reads_inline_environment_rules() -> None:
    config = HeaderConfig.from_sources(
        environ={
            INLINE_RULES_ENV_VAR: 'repo.anaconda.com Authorization "Bearer ${TOKEN}"',
            "TOKEN": "secret",
        },
        setting_rules=(),
    )

    assert header_pairs(config.session_headers_for("repo.anaconda.com")) == [
        ("authorization", "Bearer secret")
    ]
