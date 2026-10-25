"""One physical input line becomes one logical transcript line."""
import json
from pathlib import Path


class ParseError(ValueError):
    """The transcript contains no usable content."""


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def parse_transcript(path):
    lines = []
    for raw in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            value = json.loads(raw)
        except ValueError:
            line = raw
        else:
            if isinstance(value, dict):
                line = " ".join(strings(value))
            elif isinstance(value, list):
                line = " ".join(item for item in value if isinstance(item, str))
            else:
                line = raw
        lines.append(line)
    if not any(line.strip() for line in lines):
        raise ParseError("empty transcript: no usable text")
    return lines
