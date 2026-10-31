"""No models: exercise boundary recovery, atomic planning and finite budgets."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from speech_service.npu_planner import (
    NpuPlanningBudgetExceeded, NpuPlanningError, PlanLimits, plan_npu_segments,
)


class TooLong(ValueError):
    pass


class Cancelled(RuntimeError):
    pass


def prepared(duration):
    target = min((160, 200, 240, 280, 320), key=lambda value: (abs(value - duration), value))
    ratio = abs(target / duration - 1)
    return SimpleNamespace(natural_D=duration), {
        'fallback': ratio > 0.10, 'snap_ratio': ratio, 'natural_D': duration, 'target_D': target,
    }


class PlannerTests(unittest.TestCase):
    TEXT = '甲甲，乙乙，丙丙，丁丁，'

    def plan(self, text, prepare, **kwargs):
        return plan_npu_segments(text, prepare, length_error=TooLong, **kwargs)

    def mapping(self, durations):
        calls = []

        def prepare(text):
            calls.append(text)
            value = durations[text]
            if value == 'long':
                raise TooLong('phoneme length outside 1..200')
            return prepared(value)

        return prepare, calls

    def assert_coverage(self, text, plan):
        self.assertEqual(''.join(text[start:end] for start, end, _, _ in plan), text)
        self.assertEqual([start for start, _, _, _ in plan], [0] + [end for _, end, _, _ in plan[:-1]])
        self.assertTrue(all(profile['fallback'] is False and profile['snap_ratio'] <= .10
                            for _, _, _, profile in plan))

    def test_first_boundary_181_gap_recovers_at_neighbor_without_changing_text(self):
        text = self.TEXT
        prepare, calls = self.mapping({text: 'long', text[:6]: 181, text[:3]: 160, text[3:]: 300})
        plan = self.plan(text, prepare)
        self.assertEqual([(start, end) for start, end, _, _ in plan], [(0, 3), (3, 12)])
        self.assertEqual(calls, [text, text[:6], text[:3], text[3:]])
        self.assert_coverage(text, plan)

    def test_right_short_segment_can_move_parent_boundary_after_left_plan_succeeds(self):
        text = self.TEXT
        prepare, calls = self.mapping({text: 600, text[:6]: 200, text[6:]: 181,
                                        text[:3]: 160, text[3:]: 300})
        plan = self.plan(text, prepare)
        self.assertEqual([(start, end) for start, end, _, _ in plan], [(0, 3), (3, 12)])
        self.assertIn(text[6:], calls)
        self.assert_coverage(text, plan)

    def test_backtracking_reuses_prepared_source_range(self):
        text = self.TEXT
        prepare, calls = self.mapping({text: 600, text[:6]: 500, text[:3]: 160,
                                        text[3:6]: 160, text[6:]: 181, text[3:]: 300})
        plan = self.plan(text, prepare)
        self.assertEqual(calls.count(text[:3]), 1)
        self.assert_coverage(text, plan)

    def test_already_approved_whole_text_does_not_split_or_rewrite(self):
        calls = []
        text = '  原稿 SDK、标点。\n'
        plan = self.plan(text, lambda value: (calls.append(value), prepared(240))[1])
        self.assertEqual(calls, [text])
        self.assertEqual(len(plan), 1)
        self.assert_coverage(text, plan)

    def test_approved_355_duration_is_retained_even_above_largest_target(self):
        plan = self.plan('原稿', lambda text: prepared(355))
        self.assertEqual(len(plan), 1)
        self.assert_coverage('原稿', plan)

    def test_unknown_vocabulary_error_propagates_without_trying_boundaries(self):
        calls = []
        error = ValueError('unknown/dropped phoneme(s)')

        def prepare(text):
            calls.append(text)
            raise error

        with self.assertRaises(ValueError) as raised:
            self.plan(self.TEXT, prepare)
        self.assertIs(raised.exception, error)
        self.assertEqual(calls, [self.TEXT])

    def test_unplannable_late_segment_yields_nothing_before_failure(self):
        rendered = []

        def prepare(text):
            if text == self.TEXT:
                raise TooLong()
            return prepared(200 if text == self.TEXT[:6] else 181)

        with self.assertRaises(NpuPlanningError):
            for segment in self.plan(self.TEXT, prepare):
                rendered.append(segment)
        self.assertEqual(rendered, [])

    def test_no_increase_of_snap_guard_even_when_profile_claims_no_fallback(self):
        with self.assertRaisesRegex(NpuPlanningError, 'snap guard'):
            self.plan('原稿', lambda text: (SimpleNamespace(natural_D=181),
                      {'fallback': False, 'snap_ratio': abs(200 / 181 - 1)}))

    def test_whitespace_stays_attached_and_no_whitespace_only_fragment_is_prepared(self):
        text = ' 甲， \n乙， '
        calls = []

        def prepare(fragment):
            self.assertTrue(fragment.strip())
            calls.append(fragment)
            if '甲' in fragment and '乙' in fragment:
                raise TooLong()
            return prepared(160)

        plan = self.plan(text, prepare)
        self.assert_coverage(text, plan)
        self.assertTrue(calls)

    def test_prepare_call_budget_stops_search_before_more_cpu_work(self):
        calls = []

        def prepare(text):
            calls.append(text)
            raise TooLong()

        with self.assertRaisesRegex(NpuPlanningBudgetExceeded, 'frontend-call'):
            self.plan(self.TEXT, prepare, limits=PlanLimits(max_prepares=1))
        self.assertEqual(calls, [self.TEXT])

    def test_time_budget_is_checked_after_a_cpu_prepare_returns(self):
        clock = [0.0]

        def prepare(text):
            clock[0] = 2.0
            return prepared(200)

        with self.assertRaisesRegex(NpuPlanningBudgetExceeded, 'time budget'):
            self.plan('原稿', prepare, limits=PlanLimits(max_seconds=1), clock=lambda: clock[0])

    def test_cancellation_before_cpu_work_and_after_a_prepare_propagates(self):
        calls = []

        def cancel():
            raise Cancelled()

        with self.assertRaises(Cancelled):
            self.plan('原稿', lambda text: calls.append(text), cancel_check=cancel)
        self.assertEqual(calls, [])
        cancelled = [False]

        def prepare(text):
            cancelled[0] = True
            return prepared(200)

        def check():
            if cancelled[0]:
                raise Cancelled()

        with self.assertRaises(Cancelled):
            self.plan('原稿', prepare, cancel_check=check)

    def test_search_step_budget_is_independent_of_frontend_cache(self):
        with self.assertRaisesRegex(NpuPlanningBudgetExceeded, 'search-step'):
            self.plan(self.TEXT, lambda text: (_ for _ in ()).throw(TooLong()),
                      limits=PlanLimits(max_steps=1))

    def test_segment_and_depth_limits_reject_a_plan_without_dropping_text(self):
        def prepare(text):
            if len(text) > 1:
                raise TooLong()
            return prepared(160)

        with self.assertRaises(NpuPlanningError):
            self.plan('甲乙', prepare, limits=PlanLimits(max_segments=1))
        with self.assertRaises(NpuPlanningError):
            self.plan('甲乙丙丁', prepare, limits=PlanLimits(max_depth=1))

    def test_boundary_candidate_budget_bounds_backtracking(self):
        text = self.TEXT
        prepare, calls = self.mapping({text: 'long', text[:6]: 181})
        with self.assertRaises(NpuPlanningError):
            self.plan(text, prepare, limits=PlanLimits(max_candidates=1))
        self.assertEqual(calls, [text, text[:6]])

    def test_request_local_cache_never_reuses_another_voice_or_rate_request(self):
        calls = []
        prepare = lambda text: (calls.append(text), prepared(200))[1]
        self.plan('原稿', prepare)
        self.plan('原稿', prepare)
        self.assertEqual(calls, ['原稿', '原稿'])

    def test_depth_failure_can_be_revisited_with_more_depth_remaining(self):
        text = '甲甲，乙乙，丙丙，丁丁，戊戊，己己，庚庚，辛辛，'

        def prepare(fragment):
            if fragment in (text[:3], text[3:6], text[6:]):
                return prepared(200)
            raise TooLong()

        plan = self.plan(text, prepare, limits=PlanLimits(max_depth=2))
        self.assertEqual([(start, end) for start, end, _, _ in plan], [(0, 3), (3, 6), (6, 24)])
        self.assert_coverage(text, plan)


if __name__ == '__main__':
    unittest.main()
