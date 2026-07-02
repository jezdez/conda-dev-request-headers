"""Header rule parsing for the conda request-header plugin."""

from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping
    from typing import Final

from conda.plugins.types import CondaRequestHeader

INLINE_RULES_ENV_VAR: Final = "CONDA_DEV_REQUEST_HEADERS"
RULES_FILE_ENV_VAR: Final = "CONDA_DEV_REQUEST_HEADERS_FILE"
RULES_SETTING: Final = "dev_request_headers"
RULES_FILE_SETTING: Final = "dev_request_headers_file"
HEADER_NAME_RE: Final = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
FORBIDDEN_HEADER_NAMES: Final = frozenset(
    {
        "accept-charset",
        "accept-encoding",
        "access-control-request-headers",
        "access-control-request-method",
        "connection",
        "content-length",
        "cookie",
        "date",
        "dnt",
        "expect",
        "host",
        "keep-alive",
        "origin",
        "referer",
        "set-cookie",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "via",
    }
)
FORBIDDEN_METHOD_OVERRIDE_HEADER_NAMES: Final = frozenset(
    {"x-http-method", "x-http-method-override", "x-method-override"}
)
FORBIDDEN_HTTP_METHODS: Final = frozenset({"connect", "trace", "track"})


@dataclass(frozen=True)
class HeaderSelector:
    """Host and optional path prefix matched against conda request URLs."""

    host_pattern: str
    path_prefix: str | None = None

    @classmethod
    def parse(cls, selector: str) -> HeaderSelector | None:
        selector = selector.strip()
        if selector == "*":
            return cls(host_pattern="*")
        if not selector:
            return None

        parsed = urlsplit(selector if "://" in selector else f"//{selector}")
        if parsed.scheme and parsed.scheme not in {"http", "https"}:
            return None
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            return None
        if not parsed.netloc:
            return None

        path_prefix = cls.parse_path_prefix(parsed.path)
        return cls(
            host_pattern=parsed.netloc.lower().rstrip("."), path_prefix=path_prefix
        )

    @staticmethod
    def parse_path_prefix(path: str) -> str | None:
        if not path or path == "/":
            return None
        if not path.startswith("/"):
            path = f"/{path}"
        return path.rstrip("/") or None

    @property
    def is_session_scoped(self) -> bool:
        return self.path_prefix is None

    def matches_host(self, host: str) -> bool:
        host = host.lower().rstrip(".")
        if self.host_pattern == "*":
            return True
        if self.host_pattern.startswith("*."):
            suffix = self.host_pattern[1:]
            return host.endswith(suffix) and host != self.host_pattern[2:]
        return host == self.host_pattern

    def matches_request(self, host: str, path: str) -> bool:
        if not self.matches_host(host):
            return False
        if self.path_prefix is None:
            return True
        if not path.startswith("/"):
            path = f"/{path}"
        return path == self.path_prefix or path.startswith(f"{self.path_prefix}/")


@dataclass(frozen=True)
class HeaderRule:
    """A selector plus the headers yielded when it matches."""

    selector: HeaderSelector
    headers: tuple[tuple[str, str], ...]

    @classmethod
    def parse_line(
        cls, line: str, environ: Mapping[str, str] | None = None
    ) -> HeaderRule | None:
        try:
            parts = shlex.split(line, comments=True)
        except ValueError:
            return None
        if len(parts) < 3:
            return None

        selector = HeaderSelector.parse(parts[0])
        if selector is None:
            return None

        name = parts[1]
        value_template = " ".join(parts[2:])
        value = cls.render_value(value_template, environ)
        if value is None or not cls.header_is_allowed(name, value):
            return None

        return cls(selector=selector, headers=((name, value),))

    @staticmethod
    def render_value(
        value_template: str, environ: Mapping[str, str] | None = None
    ) -> str | None:
        if environ is None:
            environ = os.environ
        try:
            return Template(value_template).substitute(environ)
        except (KeyError, ValueError):
            return None

    @staticmethod
    def header_is_allowed(name: str, value: str) -> bool:
        normalized_name = name.lower()
        if not HEADER_NAME_RE.fullmatch(name):
            return False
        if any(character in value for character in "\r\n\0"):
            return False
        if normalized_name in FORBIDDEN_HEADER_NAMES:
            return False
        if normalized_name.startswith(("proxy-", "sec-")):
            return False
        if (
            normalized_name in FORBIDDEN_METHOD_OVERRIDE_HEADER_NAMES
            and value.lower() in FORBIDDEN_HTTP_METHODS
        ):
            return False
        return True


@dataclass(frozen=True)
class HeaderConfig:
    """Parsed development request-header configuration."""

    rules: tuple[HeaderRule, ...] = ()

    @classmethod
    def from_sources(
        cls,
        environ: Mapping[str, str] | None = None,
        setting_rules: tuple[str, ...] | None = None,
        setting_file: str | None = None,
    ) -> HeaderConfig:
        if environ is None:
            environ = os.environ

        if setting_rules is None and setting_file is None:
            setting_rules, setting_file = cls.conda_settings()
        else:
            setting_rules = setting_rules or ()
            setting_file = setting_file or ""

        rules = []
        rules.extend(cls.parse_lines(setting_rules, environ))
        if setting_file:
            rules.extend(cls.parse_file(setting_file, environ))
        if env_file := environ.get(RULES_FILE_ENV_VAR):
            rules.extend(cls.parse_file(env_file, environ))
        if inline_rules := environ.get(INLINE_RULES_ENV_VAR):
            rules.extend(cls.parse_lines(inline_rules.splitlines(), environ))
        return cls(rules=tuple(rules))

    @classmethod
    def parse_lines(
        cls, lines: Iterable[str], environ: Mapping[str, str] | None = None
    ) -> tuple[HeaderRule, ...]:
        rules = []
        for line in lines:
            rule = HeaderRule.parse_line(line, environ)
            if rule is not None:
                rules.append(rule)
        return tuple(rules)

    @classmethod
    def parse_file(
        cls, path: str, environ: Mapping[str, str] | None = None
    ) -> tuple[HeaderRule, ...]:
        try:
            text = Path(path).expanduser().read_text(encoding="utf-8")
        except OSError:
            return ()
        return cls.parse_lines(text.splitlines(), environ)

    @staticmethod
    def conda_settings() -> tuple[tuple[str, ...], str]:
        try:
            from conda.base.context import context as conda_context
        except Exception:
            return (), ""

        plugins = getattr(conda_context, "plugins", None)
        if plugins is None:
            return (), ""

        raw_rules = getattr(plugins, RULES_SETTING, ()) or ()
        raw_file = getattr(plugins, RULES_FILE_SETTING, "") or ""
        if isinstance(raw_rules, str):
            rules = (raw_rules,)
        else:
            rules = tuple(rule for rule in raw_rules if isinstance(rule, str))
        return rules, raw_file if isinstance(raw_file, str) else ""

    def session_headers_for(self, host: str) -> Iterator[CondaRequestHeader]:
        merged = self.merged_headers(host=host, path=None)
        for name, value in merged.values():
            yield CondaRequestHeader(name=name, value=value)

    def request_headers_for(self, host: str, path: str) -> Iterator[CondaRequestHeader]:
        merged = self.merged_headers(host=host, path=path)
        for name, value in merged.values():
            yield CondaRequestHeader(name=name, value=value)

    def merged_headers(self, host: str, path: str | None) -> dict[str, tuple[str, str]]:
        merged: dict[str, tuple[str, str]] = {}
        for rule in self.rules:
            if path is None:
                if not rule.selector.is_session_scoped:
                    continue
                if not rule.selector.matches_host(host):
                    continue
            elif not rule.selector.matches_request(host, path):
                continue
            for name, value in rule.headers:
                merged[name.lower()] = (name, value)
        return merged
