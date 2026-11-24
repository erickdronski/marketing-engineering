"""A small Markdown header format for scalars and lists. No YAML runtime."""

import json
import re
from pathlib import Path

from .errors import MktgError
from .workspace import atomic_write

KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*\Z")


def _tokens(value):
    """Split an inline list without treating a quoted comma as a separator."""
    start = 0
    quote = None
    escape = False
    for index, char in enumerate(value):
        if escape:
            escape = False
        elif quote == '"' and char == "\\":
            escape = True
        elif quote is not None:
            if char == quote:
                quote = None
        elif char in {"'", '"'} and not value[start:index].strip():
            quote = char
        elif char == ",":
            yield value[start:index].strip()
            start = index + 1
    if quote:
        raise ValueError("unclosed quote")
    yield value[start:].strip()


def _scalar(raw):
    raw = raw.strip()
    if raw.startswith('"'):
        value, end = json.JSONDecoder().raw_decode(raw)
        if raw[end:].strip() and not raw[end:].lstrip().startswith("#"):
            raise ValueError("unexpected text after quoted string")
        return value
    if raw.startswith("'"):
        match = re.fullmatch(r"'((?:[^']|'')*)'(?:\s+#.*)?", raw)
        if not match:
            raise ValueError("invalid single-quoted string")
        return match[1].replace("''", "'")
    raw = re.split(r"\s+#", raw, maxsplit=1)[0].rstrip()
    if raw in ("null", "~", ""):
        return None
    if raw in ("false", "true"):
        return raw == "true"
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    return raw


def parse(text, *, path="<text>"):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\n") != "---":
        return {}, text
    fields = {}
    last = None
    for number, line in enumerate(lines[1:], 2):
        raw = line.rstrip("\n")
        if raw == "---":
            return fields, "".join(lines[number:])
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        try:
            if raw.startswith((" ", "\t")):
                if last is None or not raw.lstrip().startswith("- "):
                    raise ValueError("expected a list item")
                if fields[last] is None:
                    fields[last] = []
                if not isinstance(fields[last], list):
                    raise ValueError("expected a scalar on its own line")
                fields[last].append(_scalar(raw.lstrip()[2:]))
                continue
            key, sep, value = raw.partition(":")
            if not sep or not KEY.fullmatch(key):
                raise ValueError("expected a field name followed by a colon")
            if key in fields:
                raise ValueError(f"duplicate field {key}")
            value = value.strip()
            if value.startswith("["):
                match = re.fullmatch(r"\[(.*)\](?:\s+#.*)?", value)
                if not match:
                    raise ValueError("unclosed list")
                fields[key] = [_scalar(token) for token in _tokens(match[1])] if match[1].strip() else []
            else:
                fields[key] = _scalar(value)
            last = key if not value else None
        except ValueError as exc:
            raise MktgError(f"line {number}: {exc}", path=path) from exc
    raise MktgError("missing closing ---", path=path)


def dump(fields, body):
    lines = ["---"]
    for name, value in fields.items():
        if not KEY.fullmatch(name):
            raise MktgError(f"invalid header key {name!r}")
        lines.append(name + ": " + json.dumps(value, ensure_ascii=False, allow_nan=False))
    return "\n".join(lines + ["---", body])


def read(path, *, rel=None):
    path = Path(path)
    return parse(path.read_text(encoding="utf-8"), path=rel or path.name)


def write(path, fields, body):
    atomic_write(path, dump(fields, body))
