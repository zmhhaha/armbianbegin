"""Operator configuration; no model or credential is chosen by a request."""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import os
from pathlib import Path
from typing import Mapping


def _name(value):
    return (type(value) is str and 1 <= len(value) <= 200 and value == value.strip()
            and not any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value))


def _number(value, minimum, maximum):
    return (type(value) in {int, float} and minimum <= value <= maximum
            and math.isfinite(value))


@dataclass(frozen=True)
class SpeechSettings:
    model: str
    voice: str
    token: str = field(repr=False)
    synthesis_timeout: float = 120.0
    body_timeout: float = 10.0
    min_speed: float = 0.5
    max_speed: float = 2.0
    max_request_bytes: int = 64 * 1024
    max_text_characters: int = 2000
    max_text_bytes: int = 16 * 1024
    max_audio_bytes: int = 32 * 1024 * 1024
    max_audio_seconds: float = 300.0

    def __post_init__(self):
        if not _name(self.model) or not _name(self.voice):
            raise ValueError("An explicit speech model and voice are required")
        if (type(self.token) is not str or not 1 <= len(self.token) <= 4096
                or any(not 33 <= ord(c) <= 126 for c in self.token)):
            raise ValueError("A valid speech credential is required")
        if (not _number(self.synthesis_timeout, 0.001, 300)
                or not _number(self.body_timeout, 0.001, 60)
                or not _number(self.min_speed, 0.25, 1)
                or not _number(self.max_speed, 1, 4)
                or not _number(self.max_audio_seconds, 0.001, 300)):
            raise ValueError("Invalid speech service limits")
        for value, low, high in (
            (self.max_request_bytes, 128, 128 * 1024),
            (self.max_text_characters, 1, 10_000),
            (self.max_text_bytes, 1, 64 * 1024),
            (self.max_audio_bytes, 44, 32 * 1024 * 1024),
        ):
            if type(value) is not int or not low <= value <= high:
                raise ValueError("Invalid speech service limits")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None):
        """Read mandatory model, voice and TOKEN_FILE; never reveal a path."""
        env = os.environ if env is None else env
        try:
            path = Path(env.get("TOKEN_FILE", ""))
            if not path.is_absolute() or not path.is_file():
                raise ValueError()
            # Follow projected Secret symlinks, while bounding the actual read.
            with path.open("rb") as stream:
                raw = stream.read(4097)
            if len(raw) > 4096:
                raise ValueError()
            token = raw.decode("ascii").strip()
        except (OSError, ValueError, UnicodeError, TypeError):
            raise ValueError("Speech credential file is unavailable") from None
        return cls(model=env.get("SPEECH_MODEL", ""), voice=env.get("SPEECH_VOICE", ""), token=token)
