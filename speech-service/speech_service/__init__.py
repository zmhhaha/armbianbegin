"""Model-independent, single-process speech HTTP service."""

from .app import SpeechApplication
from .settings import SpeechSettings

__all__ = ["SpeechApplication", "SpeechSettings"]
