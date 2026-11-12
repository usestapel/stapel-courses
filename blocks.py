"""Typed lesson content blocks and their registry.

A lesson's ``blocks`` is a list of dicts, each with a ``type`` the registry
knows. A validator takes the raw dict (author input, untrusted) and returns
the cleaned dict to store, or raises :class:`BlockInvalid` with a short
machine reason. Built-ins:

- ``text``       ``{"type", "text" ≤ 20000, "format": "markdown" | "plain"}``
- ``video``      ``{"type", "media_id" ≤ 64, "caption"?}`` — a stapel-cdn or
  stapel-recordings id; courses never resolves it
- ``attachment`` ``{"type", "media_id", "name" ≤ 200}``
- ``embed``      ``{"type", "url" (https, host in EMBED_HOSTS when set), "title"?}``

``STAPEL_COURSES["BLOCK_TYPES"]`` merges ``{type: "dotted.path" | None}``
over these; a dotted path under a built-in name replaces it.
"""
from __future__ import annotations

from typing import Callable
from urllib.parse import urlsplit

from django.utils.module_loading import import_string

from .models import MAX_BLOCKS_PER_LESSON, MEDIA_ID_MAX_LENGTH

TEXT_MAX_LENGTH = 20_000
CAPTION_MAX_LENGTH = 300
NAME_MAX_LENGTH = 200
URL_MAX_LENGTH = 500


class BlockInvalid(ValueError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _string(raw: dict, key: str, max_length: int, *, required: bool = True) -> str:
    value = raw.get(key, "")
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise BlockInvalid(f"{key}_not_string")
    value = value.strip()
    if required and not value:
        raise BlockInvalid(f"{key}_required")
    if len(value) > max_length:
        raise BlockInvalid(f"{key}_too_long")
    return value


def text_block(raw: dict) -> dict:
    fmt = raw.get("format") or "markdown"
    if fmt not in ("markdown", "plain"):
        raise BlockInvalid("format_unknown")
    return {"type": "text", "text": _string(raw, "text", TEXT_MAX_LENGTH), "format": fmt}


def video_block(raw: dict) -> dict:
    return {
        "type": "video",
        "media_id": _string(raw, "media_id", MEDIA_ID_MAX_LENGTH),
        "caption": _string(raw, "caption", CAPTION_MAX_LENGTH, required=False),
    }


def attachment_block(raw: dict) -> dict:
    return {
        "type": "attachment",
        "media_id": _string(raw, "media_id", MEDIA_ID_MAX_LENGTH),
        "name": _string(raw, "name", NAME_MAX_LENGTH),
    }


def embed_block(raw: dict) -> dict:
    from .conf import courses_settings

    url = _string(raw, "url", URL_MAX_LENGTH)
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise BlockInvalid("url_not_https")
    hosts = [h.lower() for h in (courses_settings.EMBED_HOSTS or [])]
    if hosts and parts.hostname.lower() not in hosts:
        raise BlockInvalid("host_not_allowed")
    return {
        "type": "embed",
        "url": url,
        "title": _string(raw, "title", CAPTION_MAX_LENGTH, required=False),
    }


BUILTIN_BLOCK_TYPES: dict[str, str] = {
    "text": "stapel_courses.blocks.text_block",
    "video": "stapel_courses.blocks.video_block",
    "attachment": "stapel_courses.blocks.attachment_block",
    "embed": "stapel_courses.blocks.embed_block",
}


def block_type_paths() -> dict[str, str]:
    """Effective registry: built-ins <- settings, live entries only."""
    from .conf import courses_settings

    merged: dict[str, str | None] = dict(BUILTIN_BLOCK_TYPES)
    configured = courses_settings.BLOCK_TYPES or {}
    if isinstance(configured, dict):
        merged.update(configured)
    return {name: path for name, path in merged.items() if path}


def validator(block_type: str) -> Callable[[dict], dict] | None:
    path = block_type_paths().get(block_type)
    return import_string(path) if path else None


def clean_blocks(raw_blocks) -> list[dict]:
    """Validate a lesson's blocks; raises ``BlockInvalid`` with ``index``."""
    if raw_blocks is None:
        return []
    if not isinstance(raw_blocks, list):
        raise BlockInvalid("not_a_list")
    if len(raw_blocks) > MAX_BLOCKS_PER_LESSON:
        raise BlockInvalid("too_many_blocks")
    cleaned = []
    for index, raw in enumerate(raw_blocks):
        if not isinstance(raw, dict):
            raise _at(index, "not_an_object")
        fn = validator(str(raw.get("type") or ""))
        if fn is None:
            raise _at(index, "type_unknown")
        try:
            cleaned.append(fn(raw))
        except BlockInvalid as exc:
            raise _at(index, exc.reason) from None
    return cleaned


def _at(index: int, reason: str) -> BlockInvalid:
    exc = BlockInvalid(reason)
    exc.index = index
    return exc
