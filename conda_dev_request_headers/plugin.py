"""Conda plugin registration for development request headers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from conda.plugins import hookimpl

from .headers import RULES_FILE_SETTING, RULES_SETTING, HeaderConfig

if TYPE_CHECKING:
    from collections.abc import Iterable

    from conda.plugins.types import CondaRequestHeader, CondaSetting


@hookimpl
def conda_settings() -> Iterable[CondaSetting]:
    """Register conda-native settings for development request headers."""
    from conda.common.configuration import PrimitiveParameter, SequenceParameter
    from conda.plugins.types import CondaSetting

    yield CondaSetting(
        name=RULES_SETTING,
        description=(
            "Development request-header rules. Each rule is "
            "'<selector> <header-name> <header-value-template>'."
        ),
        parameter=SequenceParameter(
            PrimitiveParameter("", element_type=str),
            default=(),
            string_delimiter="\n",
        ),
    )
    yield CondaSetting(
        name=RULES_FILE_SETTING,
        description="Path to a development request-header rules file.",
        parameter=PrimitiveParameter("", element_type=str),
    )


@hookimpl
def conda_session_headers(host: str) -> Iterable[CondaRequestHeader]:
    """Register headers that apply to every request for *host*."""
    yield from HeaderConfig.from_sources().session_headers_for(host)


@hookimpl
def conda_request_headers(host: str, path: str) -> Iterable[CondaRequestHeader]:
    """Register headers that apply to a specific request path."""
    yield from HeaderConfig.from_sources().request_headers_for(host, path)
