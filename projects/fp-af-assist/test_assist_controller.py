"""Offline safety and numerical tests; this module never accesses USB."""

import math
import unittest

from assist_controller import Config, U32_MAX, quadratic_peak, run


class SimulatedBackend:
    def __init__(self, curve=lambda p: 1000.0, position=0, lo=-1000, hi=1000):
        self.curve = curve
        self.position = position
        self.lo, self.hi = lo, hi
        self.calls = []
        self.observation_count = 0
        self.motion_count = 0
        self.stop_count = 0
        self.mutate = None
        self.fail_move = None
        self.stop_error = False

    def sample(self):
        self.observation_count += 1
        observation = {
            "position": self.position, "h": self.curve(self.position),
            "l": 700, "gain": [117, 985, 131, 0],
            "context": ["nonrecording", [784, 341, 128, 128], "area0"],
            "valid": True, "min_position": self.lo, "max_position": self.hi,
        }
        if self.mutate:
            self.mutate(observation, self)
        return observation

    def observe(self):
        self.calls.append(("observe", self.position))
        return self.sample()

    def move_to(self, target):
        self.motion_count += 1
        self.calls.append(("move", target))
        if self.fail_move == self.motion_count:
            # Hardware may already have moved when its completion reply fails.
            self.position = target
            raise TimeoutError("uncertain movement")
        self.position = target
        return self.sample()

    def stop(self):
        self.stop_count += 1
        self.calls.append(("stop", self.position))
        if self.stop_error:
            raise TimeoutError("stop verification failed")
        return {"verified": True, "position": self.position}


class ControllerTests(unittest.TestCase):
    def assert_limits(self, result, start, lo=-1000, hi=1000, max_step=100, budget=12):
        self.assertLessEqual(len(result["moves"]), budget)
        previous = start
        for move in result["moves"]:
            self.assertEqual(previous, move["from"])
            self.assertLessEqual(abs(move["target"] - previous), max_step)
            self.assertLessEqual(abs(move["target"] - start), 100)
            self.assertGreaterEqual(move["target"], lo)
            self.assertLessEqual(move["target"], hi)
            previous = move["target"]

    def test_flat_returns_to_origin_and_confirms_without_focus_claim(self):
        backend = SimulatedBackend()
        result = run(backend)
        self.assertEqual("completed", result["status"])
        self.assertEqual("no_significant_improvement", result["reason"])
        self.assertEqual(0, backend.position)
        self.assertTrue(result["confirmed"])
        self.assertFalse(result["optical_focus_verified"])
        self.assertEqual("final_confirmation", result["observations"][-1]["purpose"])
        self.assertEqual(0, backend.stop_count)
        self.assert_limits(result, 0)

    def test_quadratic_proposal_is_measured_and_confirmed(self):
        backend = SimulatedBackend(lambda p: 1000 - 0.12 * (p - 20) ** 2)
        result = run(backend)
        self.assertEqual("completed", result["status"])
        self.assertEqual("improved", result["reason"])
        self.assertEqual(20, result["quadratic_target"])
        self.assertEqual(20, result["selected_position"])
        self.assertEqual(20, backend.position)
        self.assertFalse(result["at_search_boundary"])
        self.assertTrue(any(s["purpose"] == "quadratic_probe" for s in result["observations"]))
        self.assert_limits(result, 0)

    def test_monotonic_edge_is_not_claimed_as_bracketed_optimum(self):
        backend = SimulatedBackend(lambda p: 1000 + 2 * p)
        result = run(backend)
        self.assertEqual("completed", result["status"])
        self.assertEqual(100, backend.position)
        self.assertTrue(result["at_search_boundary"])
        self.assertIsNone(result["quadratic_target"])
        self.assert_limits(result, 0)

    def test_negative_monotonic_direction(self):
        backend = SimulatedBackend(lambda p: 1000 - 2 * p)
        result = run(backend)
        self.assertEqual(-100, result["selected_position"])
        self.assertEqual("completed", result["status"])
        self.assert_limits(result, 0)

    def test_subthreshold_improvement_does_not_justify_new_position(self):
        backend = SimulatedBackend(lambda p: 1000 + 0.5 * p)
        result = run(backend)
        self.assertEqual(0, result["selected_position"])
        self.assertEqual("no_significant_improvement", result["reason"])
        self.assertEqual(0, backend.position)

    def test_mechanical_bounds_clip_search(self):
        backend = SimulatedBackend(lambda p: 1000 + p, position=95, lo=0, hi=110)
        result = run(backend)
        self.assertEqual("completed", result["status"])
        self.assert_limits(result, 95, lo=0, hi=110)
        self.assertEqual([0, 110], result["limits"]["allowed_positions"])

    def test_at_near_limit_only_moves_inward(self):
        backend = SimulatedBackend(lambda p: 2000 - 2 * p, position=110, lo=0, hi=110)
        result = run(backend)
        self.assertEqual(10, backend.position)
        self.assertEqual("completed", result["status"])
        self.assert_limits(result, 110, lo=0, hi=110)

    def test_no_mechanical_range_still_performs_final_confirmation(self):
        backend = SimulatedBackend(position=12, lo=12, hi=12)
        result = run(backend)
        self.assertEqual("completed", result["status"])
        self.assertEqual(0, backend.motion_count)
        self.assertEqual(2, backend.observation_count)

    def test_two_move_budget_reserves_return(self):
        backend = SimulatedBackend()
        result = run(backend, config=Config(max_moves=2))
        self.assertEqual("completed", result["status"])
        self.assertEqual(0, backend.position)
        self.assert_limits(result, 0, budget=2)

    def test_small_steps_segment_routes(self):
        backend = SimulatedBackend(lambda p: 1000 + 2 * p)
        result = run(backend, config=Config(step=25, max_step=25))
        self.assertEqual("completed", result["status"])
        self.assert_limits(result, 0, max_step=25)

    def test_radius_stays_hard_bounded(self):
        backend = SimulatedBackend(lambda p: 1000 + 10 * p)
        result = run(backend, config=Config(radius=20, step=10))
        self.assertEqual(20, result["selected_position"])
        self.assertTrue(all(abs(m["target"]) <= 20 for m in result["moves"]))

    def test_transport_fault_never_returns_to_original(self):
        backend = SimulatedBackend()
        backend.fail_move = 1
        result = run(backend)
        self.assertEqual("fault", result["status"])
        self.assertEqual([("observe", 0), ("move", 50), ("stop", 50)], backend.calls)
        self.assertFalse(result["moves"][0]["completed"])
        self.assertFalse(result["confirmed"])

    def test_failed_stop_is_reported_and_not_retried(self):
        backend = SimulatedBackend()
        backend.fail_move = 1
        backend.stop_error = True
        result = run(backend)
        self.assertEqual("fault", result["status"])
        self.assertFalse(result["stop"]["verified"])
        self.assertEqual(1, backend.stop_count)
        self.assertEqual(1, backend.motion_count)

    def test_cancel_before_initial_observation(self):
        backend = SimulatedBackend()
        result = run(backend, cancel=lambda: True)
        self.assertEqual("cancelled", result["status"])
        self.assertEqual([("stop", 0)], backend.calls)

    def test_cancel_after_first_move_no_recovery(self):
        backend = SimulatedBackend()
        result = run(backend, cancel=lambda: backend.motion_count >= 1)
        self.assertEqual("cancelled", result["status"])
        self.assertEqual(1, backend.motion_count)
        self.assertEqual(50, backend.position)
        self.assertEqual("stop", backend.calls[-1][0])

    def test_cancel_event_before_move_prevents_request(self):
        backend = SimulatedBackend()
        flag = [False]
        def event(item):
            if item["kind"] == "observation":
                flag[0] = True
        result = run(backend, cancel=lambda: flag[0], event=event)
        self.assertEqual("cancelled", result["status"])
        self.assertEqual(0, backend.motion_count)

    def test_cancel_from_movement_event_prevents_issue(self):
        backend = SimulatedBackend()
        flag = [False]
        def event(item):
            if item["kind"] == "move_requested":
                flag[0] = True
        result = run(backend, cancel=lambda: flag[0], event=event)
        self.assertEqual("cancelled", result["status"])
        self.assertEqual(0, backend.motion_count)
        self.assertFalse(result["moves"][0]["issued"])

    def test_keyboard_interrupt_stops(self):
        backend = SimulatedBackend()
        def event(item):
            if item["kind"] == "move_requested":
                raise KeyboardInterrupt()
        result = run(backend, event=event)
        self.assertEqual("cancelled", result["status"])
        self.assertEqual(1, backend.stop_count)
        self.assertEqual(0, backend.motion_count)

    def test_event_cannot_mutate_controller_observation(self):
        backend = SimulatedBackend()
        def event(item):
            if item["kind"] == "observation":
                item["sample"]["position"] = 99999
                item["sample"]["h"] = 1
        result = run(backend, event=event)
        self.assertEqual("completed", result["status"])
        self.assertEqual(0, result["selected_position"])
        self.assert_limits(result, 0)

    def test_context_or_gain_change_stops_without_return(self):
        for field in ("context", "gain"):
            with self.subTest(field=field):
                backend = SimulatedBackend()
                def mutate(observation, sim):
                    if sim.observation_count >= 2:
                        observation[field] = ["changed"]
                backend.mutate = mutate
                result = run(backend)
                self.assertEqual("fault", result["status"])
                self.assertIn("gain_or_context_changed", result["reason"])
                self.assertEqual(1, backend.motion_count)
                self.assertEqual(50, backend.position)

    def test_invalid_observation_stops(self):
        backend = SimulatedBackend()
        backend.mutate = lambda obs, sim: obs.update(valid=False)
        result = run(backend)
        self.assertEqual("fault", result["status"])
        self.assertEqual(0, backend.motion_count)

    def test_invalid_or_saturated_h_values(self):
        for h in (0, -1, math.nan, math.inf, U32_MAX, U32_MAX + 1, True, "2"):
            with self.subTest(h=h):
                backend = SimulatedBackend(lambda p: h)
                result = run(backend)
                self.assertEqual("fault", result["status"])
                self.assertEqual(0, backend.motion_count)

    def test_l_ratio_does_not_affect_controller(self):
        results = []
        for l in (0, 1, U32_MAX, None):
            backend = SimulatedBackend(lambda p: 1000 + 2 * p)
            backend.mutate = lambda obs, sim: obs.update(l=l)
            results.append(run(backend)["selected_position"])
        self.assertEqual([100] * 4, results)

    def test_wrong_actual_position_is_fault_not_success(self):
        backend = SimulatedBackend()
        def mutate(observation, sim):
            if sim.motion_count:
                observation["position"] += 1
        backend.mutate = mutate
        result = run(backend)
        self.assertEqual("fault", result["status"])
        self.assertEqual("actual_position_does_not_match_target", result["reason"])
        self.assertEqual(1, backend.motion_count)

    def test_observed_position_outside_radius_is_fault(self):
        backend = SimulatedBackend()
        def mutate(observation, sim):
            if sim.motion_count:
                observation["position"] = 101
        backend.mutate = mutate
        result = run(backend)
        self.assertIn("outside_allowed_bounds", result["reason"])
        self.assertEqual(1, backend.motion_count)

    def test_initial_outside_mechanical_bounds(self):
        backend = SimulatedBackend(position=110, lo=0, hi=100)
        result = run(backend)
        self.assertEqual("fault", result["status"])
        self.assertEqual(0, backend.motion_count)

    def test_missing_bounds_rejected_before_motion(self):
        backend = SimulatedBackend()
        backend.mutate = lambda obs, sim: obs.pop("min_position")
        result = run(backend)
        self.assertEqual("fault", result["status"])
        self.assertEqual(0, backend.motion_count)

    def test_later_bound_change_faults_without_return(self):
        backend = SimulatedBackend()
        def mutate(observation, sim):
            if sim.motion_count:
                observation["max_position"] = 90
        backend.mutate = mutate
        result = run(backend)
        self.assertEqual("fault", result["status"])
        self.assertIn("mechanical_bounds_changed", result["reason"])
        self.assertEqual(1, backend.motion_count)

    def test_final_confirmation_rejects_contrast_loss_without_more_moves(self):
        backend = SimulatedBackend(lambda p: 1000 + 2 * p)
        def mutate(observation, sim):
            if sim.calls[-1][0] == "observe" and sim.observation_count > 1:
                observation["h"] = 1000
        backend.mutate = mutate
        result = run(backend)
        self.assertEqual("unconfirmed", result["status"])
        self.assertFalse(result["confirmed"])
        self.assertEqual("observe", backend.calls[-1][0])

    def test_final_confirmation_requires_significant_improvement_again(self):
        backend = SimulatedBackend(lambda p: 1000 + 0.7 * p)
        def mutate(observation, sim):
            if sim.calls[-1][0] == "observe" and sim.observation_count > 1:
                observation["h"] = 1029
        backend.mutate = mutate
        result = run(backend)
        self.assertEqual("unconfirmed", result["status"])

    def test_final_context_change_is_fault(self):
        backend = SimulatedBackend()
        def mutate(observation, sim):
            if sim.calls[-1][0] == "observe" and sim.observation_count > 1:
                observation["context"] = ["recording"]
        backend.mutate = mutate
        result = run(backend)
        self.assertEqual("fault", result["status"])
        self.assertFalse(result["confirmed"])

    def test_observer_failure_cannot_prevent_stop(self):
        backend = SimulatedBackend()
        def event(_):
            raise RuntimeError("UI gone")
        result = run(backend, event=event)
        self.assertEqual("fault", result["status"])
        self.assertEqual(1, backend.stop_count)
        self.assertEqual(0, backend.motion_count)

    def test_configuration_hard_limits(self):
        for values in ({"radius": 101}, {"radius": 0}, {"max_step": 101},
                       {"step": 101}, {"max_moves": 13}, {"max_moves": 1},
                       {"radius": True}, {"improvement": 0.029},
                       {"improvement": math.nan}, {"improvement": 1}):
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    Config(**values)

    def test_many_parabolas_never_break_motion_constraints(self):
        for center in range(-150, 151, 13):
            for origin in (-99, 0, 99):
                for budget in (2, 4, 8, 12):
                    backend = SimulatedBackend(
                        lambda p: 10000 - 0.1 * (p - center) ** 2,
                        position=origin, lo=-120, hi=120)
                    result = run(backend, config=Config(max_moves=budget))
                    with self.subTest(center=center, origin=origin, budget=budget):
                        self.assertEqual("completed", result["status"])
                        self.assert_limits(result, origin, lo=-120, hi=120, budget=budget)
                        self.assertEqual(result["selected_position"], backend.position)


class QuadraticTests(unittest.TestCase):
    @staticmethod
    def fit(xs, ys):
        return quadratic_peak(*[{"position": x, "h": y} for x, y in zip(xs, ys)])

    def test_symmetric(self):
        self.assertEqual(0, self.fit([-50, 0, 50], [750, 1000, 750]))

    def test_shifted_large_positions(self):
        center = 1000020
        xs = [999950, 1000000, 1000050]
        self.assertEqual(center, self.fit(xs, [1000 - 0.12 * (x - center) ** 2 for x in xs]))

    def test_negative_rounding(self):
        xs = [-70, -20, 30]
        self.assertEqual(-21, self.fit(xs, [1000 - 0.1 * (x + 20.6) ** 2 for x in xs]))

    def test_flat_tie_convex_and_monotonic_rejected(self):
        for ys in ([1, 1, 1], [1, 2, 2], [3, 1, 3], [1, 2, 3]):
            self.assertIsNone(self.fit([-50, 0, 50], ys))

    def test_bad_spacing_rejected(self):
        self.assertIsNone(self.fit([0, 1, 100], [1, 100, 1]))
        self.assertIsNone(self.fit([0, 0, 100], [1, 100, 1]))

    def test_nearly_flat_curvature_rejected(self):
        self.assertIsNone(self.fit([-50, 0, 50], [1e6, 1e6 + 1e-4, 1e6]))


if __name__ == "__main__":
    unittest.main()
