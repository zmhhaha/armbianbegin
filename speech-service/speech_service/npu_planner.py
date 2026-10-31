"""Bounded, lossless planning before any NPU segment is rendered.

The approved frontend and profile selector remain authoritative. When the
nearest text boundary produces a short segment outside their 10% snap guard,
try a few neighboring word/punctuation boundaries in the parent instead.
There is no text rewriting, rate adjustment, or CPU waveform fallback here.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import math
from numbers import Real
from time import monotonic
from typing import Callable

APPROVED_MAX_SNAP_RATIO = 0.10
_BOUNDARY_PUNCTUATION = frozenset('。！？；，、')
_TOO_LONG = object()


class NpuPlanningError(RuntimeError):
    """No complete approved NPU plan was found within the search policy."""


class NpuPlanningBudgetExceeded(NpuPlanningError):
    """Planning stopped before rendering because its bounded budget ran out."""


@dataclass(frozen=True)
class PlanLimits:
    max_prepares: int = 96
    max_seconds: float = 25.0
    max_steps: int = 1024
    max_depth: int = 24
    max_candidates: int = 9
    max_cache_entries: int = 48
    max_segments: int = 256

    def __post_init__(self):
        caps = dict(max_prepares=256, max_steps=4096, max_depth=64,
                    max_candidates=17, max_cache_entries=128, max_segments=256)
        for name, maximum in caps.items():
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError('planning limits must be bounded positive integers')
        if (type(self.max_seconds) not in (int, float) or not math.isfinite(self.max_seconds)
                or not 0 < self.max_seconds <= 120):
            raise ValueError('planning time limit must be finite and in (0, 120]')


def plan_npu_segments(
    text: str,
    prepare: Callable,
    *,
    length_error: type[Exception],
    cancel_check: Callable | None = None,
    max_natural_d: int = 320,
    limits: PlanLimits = PlanLimits(),
    clock: Callable = monotonic,
) -> tuple:
    """Return the complete ordered plan, or raise without yielding any segment.

    ``prepare(fragment)`` must call the existing ``_prepare_candidate`` without
    changing its language, speed, style or cancellation arguments. Only the
    explicit phoneme-length exception is recoverable; other frontend failures
    propagate immediately. Budgets/cancellation are checked between frontend
    calls, whose own ``cancel_check`` still controls their CPU phases.

    The cache is local to this request. Its entry count, total prepare count,
    recursion depth, search steps, result segments and wall time are bounded.
    """
    if not isinstance(text, str) or not text.strip() or len(text) > 10000:
        raise ValueError('text must be non-empty and within the frontend input limit')
    if not callable(prepare) or not callable(clock) or cancel_check is not None and not callable(cancel_check):
        raise TypeError('planning callbacks must be callable')
    if not isinstance(length_error, type) or not issubclass(length_error, Exception):
        raise TypeError('length_error must be an explicit exception class')
    if type(max_natural_d) is not int or max_natural_d < 1 or not isinstance(limits, PlanLimits):
        raise ValueError('invalid NPU planning configuration')
    check_cancel = cancel_check or (lambda: None)
    started = clock()
    prepares = steps = 0
    cache: OrderedDict = OrderedDict()
    failed: set[tuple[int, int, int]] = set()

    def check():
        check_cancel()
        if clock() - started >= limits.max_seconds:
            raise NpuPlanningBudgetExceeded('NPU planning time budget exceeded')

    def candidate(start, end):
        nonlocal prepares
        check()
        key = (start, end)
        if key in cache:
            value = cache.pop(key)
            cache[key] = value
            return value
        if prepares >= limits.max_prepares:
            raise NpuPlanningBudgetExceeded('NPU planning frontend-call budget exceeded')
        prepares += 1
        try:
            prepared, profile = prepare(text[start:end])
        except length_error:
            value = _TOO_LONG
        else:
            if not isinstance(profile, dict) or type(profile.get('fallback')) is not bool:
                raise NpuPlanningError('frontend returned an invalid NPU profile')
            if profile['fallback'] is False:
                ratio = profile.get('snap_ratio')
                if (not isinstance(ratio, Real) or isinstance(ratio, bool) or not math.isfinite(ratio)
                        or not 0 <= ratio <= APPROVED_MAX_SNAP_RATIO):
                    raise NpuPlanningError('frontend profile exceeds the approved NPU snap guard')
            value = (prepared, profile)
        check()
        cache[key] = value
        if len(cache) > limits.max_cache_entries:
            cache.popitem(last=False)
        return value

    def solve(start, end, depth):
        nonlocal steps
        check()
        steps += 1
        if steps > limits.max_steps:
            raise NpuPlanningBudgetExceeded('NPU planning search-step budget exceeded')
        # Exhausting the depth allowance for this range does not prove it
        # impossible when another parent reaches it with more depth remaining.
        key = (start, end, depth)
        if key in failed:
            return None
        value = candidate(start, end)
        if value is not _TOO_LONG:
            prepared, profile = value
            if profile['fallback'] is False:
                return ((start, end, prepared, profile),)
            # A short rejected segment needs a different *parent* boundary.
            # Splitting it again would usually make both halves still shorter.
            if prepared.natural_D <= max_natural_d:
                failed.add(key)
                return None
        if depth >= limits.max_depth:
            failed.add(key)
            return None
        fragment = text[start:end]
        lo = start + len(fragment) - len(fragment.lstrip())
        hi = end - (len(fragment) - len(fragment.rstrip()))
        if hi - lo <= 1:
            failed.add(key)
            return None
        middle = (lo + hi) // 2
        boundaries = [index for index in range(lo + 1, hi)
                      if text[index - 1].isspace() or text[index - 1] in _BOUNDARY_PUNCTUATION]
        # First choice exactly matches the pinned vendor midpoint policy. Only
        # a bounded number of neighboring semantic boundaries are alternatives.
        candidates = sorted(boundaries, key=lambda index: (abs(index - middle), index))[:limits.max_candidates]
        if not candidates:
            candidates = [middle]
        for split in candidates:
            check()
            left = solve(start, split, depth + 1)
            if left is None:
                continue
            right = solve(split, end, depth + 1)
            if right is None or len(left) + len(right) > limits.max_segments:
                continue
            return left + right
        failed.add(key)
        return None

    plan = solve(0, len(text), 0)
    if plan is None or not 1 <= len(plan) <= limits.max_segments:
        raise NpuPlanningError('no complete approved NPU segmentation was found')
    cursor = 0
    for start, end, _prepared, profile in plan:
        if start != cursor or not start < end <= len(text) or profile.get('fallback') is not False:
            raise NpuPlanningError('NPU plan source coverage is invalid')
        cursor = end
    if cursor != len(text):
        raise NpuPlanningError('NPU plan source coverage is incomplete')
    check()
    return plan
