"""Conservative, backend-independent single-ROI contrast assist (not DFD).

Backend contract:
    observe() -> a settled observation
    move_to(target: int) -> a *completed and settled* observation
    stop() -> a stop-verification dictionary

Observations contain ``position`` (actual integer lens position), ``h``, ``l``,
``gain`` and ``context`` (nonempty lists/tuples), and ``valid: True``. The first
observation also contains inclusive ``min_position`` and ``max_position``.
Context must identify every property that makes H comparable, including ROI,
AF-statistics configuration, exposure context and the non-recording state. The
backend owns freshness, hardware readiness, settling, completion, stop and
timeouts; ``valid`` is not a substitute for those checks.

Cancellation is checked before every backend observation/movement. A backend
must additionally handle cancellation while its own movement call is running.
No exception, cancellation or uncertain result initiates recovery movement.
The only automatic return is on the normal, fully verified path. A result is
never evidence of optical focus, and H/L ratio is not used by this controller.
"""

from dataclasses import dataclass
import copy
import math
import numbers
from typing import Any, Callable, Dict, List, Optional, Tuple


U32_MAX = 0xFFFFFFFF


@dataclass(frozen=True)
class Config:
    radius: int = 100
    step: int = 50
    max_step: int = 100
    max_moves: int = 12
    improvement: float = 0.03

    def __post_init__(self) -> None:
        for name in ("radius", "step", "max_step", "max_moves"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(name + " must be an integer")
        if not 1 <= self.radius <= 100:
            raise ValueError("radius must be in 1..100 pulses")
        if not 1 <= self.max_step <= 100:
            raise ValueError("max_step must be in 1..100 pulses")
        if not 1 <= self.step <= min(self.radius, self.max_step):
            raise ValueError("step must fit radius and max_step")
        if not 2 <= self.max_moves <= 12:
            raise ValueError("max_moves must be in 2..12")
        if (isinstance(self.improvement, bool)
                or not isinstance(self.improvement, numbers.Real)
                or not math.isfinite(self.improvement)
                or not 0.03 <= self.improvement < 1):
            raise ValueError("improvement must be finite and in [0.03, 1)")


class _Cancelled(Exception):
    pass


class _Fault(Exception):
    pass


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _Fault(label + " must be an integer")
    return value


def _sequence(value: Any, label: str) -> Tuple[Any, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise _Fault(label + " must be a nonempty list/tuple")
    # Reject non-finite numeric context values, which cannot compare reliably.
    def freeze(item: Any) -> Any:
        if isinstance(item, (list, tuple)):
            return tuple(freeze(child) for child in item)
        if isinstance(item, numbers.Real) and not math.isfinite(item):
            raise _Fault(label + " contains a non-finite value")
        if isinstance(item, dict):
            raise _Fault(label + " must not contain mutable mappings")
        return item
    return tuple(freeze(item) for item in value)


def quadratic_peak(left: Dict[str, Any], middle: Dict[str, Any],
                   right: Dict[str, Any]) -> Optional[int]:
    """Return a strictly interior integer vertex of a well-conditioned bracket.

    x is shifted/scaled before fitting. Flat/tied/nonconcave triples, tiny
    curvature relative to H, highly uneven spacing and rounded endpoints are
    rejected. This is a proposal for another measurement, never a focus result.
    """
    x0, x1, x2 = (sample["position"] for sample in (left, middle, right))
    y0, y1, y2 = (float(sample["h"]) for sample in (left, middle, right))
    if not x0 < x1 < x2 or not y1 > max(y0, y2):
        return None
    span = x2 - x0
    if min(x1 - x0, x2 - x1) / span < 0.1:
        return None
    u0, u2 = (x0 - x1) / span, (x2 - x1) / span
    slope0, slope2 = (y0 - y1) / u0, (y2 - y1) / u2
    a = (slope2 - slope0) / (u2 - u0)
    b = slope0 - a * u0
    scale = max(abs(y0), abs(y1), abs(y2), 1.0)
    if not math.isfinite(a) or a >= -scale * 1e-6:
        return None
    vertex = x1 + (-b / (2 * a)) * span
    if not math.isfinite(vertex) or not x0 < vertex < x2:
        return None
    # Lens positions are integral; ties use away-from-zero rounding.
    target = int(math.floor(vertex + 0.5) if vertex >= 0
                 else math.ceil(vertex - 0.5))
    return target if x0 < target < x2 else None


def run(backend: Any, cancel: Callable[[], bool] = lambda: False,
        event: Optional[Callable[[Dict[str, Any]], None]] = None,
        config: Optional[Config] = None) -> Dict[str, Any]:
    """Run a bounded search, returning an auditable JSON-compatible result.

    Status is ``completed``, ``unconfirmed``, ``cancelled`` or ``fault``.
    Completed means that the selected measured position was re-observed under
    matching conditions, not that the subject is optically in focus. Movement
    budgets include segmented transit and the normal return to the selected
    position. Invalid configuration raises ValueError before touching backend.
    """
    cfg = config or Config()
    if not isinstance(cfg, Config):
        raise ValueError("config must be a Config")
    observations: List[Dict[str, Any]] = []
    moves: List[Dict[str, Any]] = []
    events: List[Dict[str, Any]] = []
    result: Dict[str, Any] = {
        "version": "0.1", "method": "bounded_settled_H_contrast",
        "status": "fault", "reason": None, "confirmed": False,
        "optical_focus_verified": False, "initial_position": None,
        "selected_position": None, "final_position": None,
        "last_verified_position": None,
        "observations": observations, "moves": moves, "events": events,
        "quadratic_target": None, "stop": None,
        "limits": {"radius": cfg.radius, "max_step": cfg.max_step,
                   "max_moves": cfg.max_moves,
                   "improvement": cfg.improvement},
    }
    current: Optional[Dict[str, Any]] = None
    initial: Optional[Dict[str, Any]] = None
    selected: Optional[Dict[str, Any]] = None
    signature: Optional[Tuple[Any, ...]] = None
    allowed: Optional[Tuple[int, int]] = None
    mechanical_bounds: Optional[Tuple[int, int]] = None
    samples: Dict[int, Dict[str, Any]] = {}

    def emit(kind: str, **data: Any) -> None:
        item = dict(kind=kind, **data)
        events.append(item)
        if event is not None:
            event(copy.deepcopy(item))

    def check_cancel() -> None:
        if cancel():
            raise _Cancelled("cancel_requested")

    def validate(raw: Any, purpose: str,
                 expected: Optional[int] = None) -> Dict[str, Any]:
        nonlocal signature, allowed, mechanical_bounds, current
        if not isinstance(raw, dict) or raw.get("valid") is not True:
            raise _Fault("invalid_observation: " + purpose)
        position = _integer(raw.get("position"), "position")
        h = raw.get("h")
        if (isinstance(h, bool) or not isinstance(h, numbers.Real)
                or not math.isfinite(h) or not 0 < h < U32_MAX):
            raise _Fault("invalid_or_saturated_H: " + purpose)
        gain = _sequence(raw.get("gain"), "gain")
        context = _sequence(raw.get("context"), "context")
        if signature is None:
            lo = _integer(raw.get("min_position"), "min_position")
            hi = _integer(raw.get("max_position"), "max_position")
            if not lo <= position <= hi:
                raise _Fault("initial_position_outside_mechanical_bounds")
            mechanical_bounds = (lo, hi)
            allowed = (max(lo, position - cfg.radius),
                       min(hi, position + cfg.radius))
            signature = (gain, context)
            result["limits"]["allowed_positions"] = list(allowed)
        elif (gain, context) != signature:
            raise _Fault("gain_or_context_changed: " + purpose)
        if "min_position" in raw or "max_position" in raw:
            reported_bounds = (_integer(raw.get("min_position"), "min_position"),
                               _integer(raw.get("max_position"), "max_position"))
            if reported_bounds != mechanical_bounds:
                raise _Fault("mechanical_bounds_changed: " + purpose)
        if not allowed[0] <= position <= allowed[1]:
            raise _Fault("observed_position_outside_allowed_bounds")
        if expected is not None and position != expected:
            raise _Fault("actual_position_does_not_match_target")
        sample = {"position": position, "h": float(h), "l": raw.get("l"),
                  "gain": list(gain), "context": list(context),
                  "valid": True, "purpose": purpose}
        observations.append(sample)
        current = sample
        result["final_position"] = position
        result["last_verified_position"] = position
        emit("observation", sample=sample)
        return sample

    def record_search_sample(sample: Dict[str, Any]) -> None:
        nonlocal selected
        samples[sample["position"]] = sample
        # A sub-threshold drift never justifies changing the starting position.
        if sample["h"] >= initial["h"] * (1 + cfg.improvement):
            if selected["position"] == initial["position"] or sample["h"] > selected["h"]:
                selected = sample
                result["selected_position"] = sample["position"]

    def route(start: int, target: int) -> List[int]:
        points = []
        while start != target:
            delta = target - start
            start += min(abs(delta), cfg.max_step) * (1 if delta > 0 else -1)
            points.append(start)
        return points

    def can_probe(target: int) -> bool:
        if not allowed[0] <= target <= allowed[1]:
            return False
        path = route(current["position"], target)
        # Every transit observation may become best. Reserve enough movements
        # to return to any already measured or about-to-be-measured position.
        possible_best = list(samples) + path
        reserve = max((len(route(target, p)) for p in possible_best), default=0)
        return len(moves) + len(path) + reserve <= cfg.max_moves

    def move(target: int, purpose: str, searching: bool) -> Dict[str, Any]:
        if not allowed[0] <= target <= allowed[1]:
            raise _Fault("requested_position_outside_allowed_bounds")
        for next_position in route(current["position"], target):
            check_cancel()
            if len(moves) >= cfg.max_moves:
                raise _Fault("movement_budget_exhausted")
            request = {"from": current["position"], "target": next_position,
                       "purpose": purpose, "issued": False, "completed": False}
            moves.append(request)  # Count attempted movements, including errors.
            emit("move_requested", **request)
            check_cancel()
            request["issued"] = True
            result["final_position"] = None
            raw = backend.move_to(next_position)
            # A just-arrived cancellation still suppresses all subsequent work.
            check_cancel()
            sample = validate(raw, purpose, expected=next_position)
            request["completed"] = True
            if searching:
                record_search_sample(sample)
        return current

    try:
        check_cancel()
        initial = validate(backend.observe(), "initial")
        check_cancel()
        selected = initial
        samples[initial["position"]] = initial
        result["initial_position"] = initial["position"]
        result["selected_position"] = initial["position"]
        base = initial["position"]
        # Sample both sides where possible, within the same frozen context.
        for target in (min(allowed[1], base + cfg.step),
                       max(allowed[0], base - cfg.step)):
            if target != base and target not in samples and can_probe(target):
                move(target, "probe", True)

        # Extend only a direction supported by a significant measured increase.
        while selected["position"] != base:
            direction = 1 if selected["position"] > base else -1
            target = max(allowed[0], min(allowed[1],
                         selected["position"] + direction * cfg.step))
            if target in samples or not can_probe(target):
                break
            previous_score = selected["h"]
            move(target, "extend", True)
            if samples[target]["h"] < previous_score * (1 + cfg.improvement):
                break

        ordered = [samples[p] for p in sorted(samples)]
        strongest = max(ordered, key=lambda sample: sample["h"])
        index = ordered.index(strongest)
        if 0 < index < len(ordered) - 1:
            candidate = quadratic_peak(ordered[index - 1], strongest,
                                       ordered[index + 1])
            if (candidate is not None and candidate not in samples
                    and can_probe(candidate)):
                result["quadratic_target"] = candidate
                move(candidate, "quadratic_probe", True)

        # A measured best at the search edge is not a bracketed optimum.
        target = selected["position"]
        move(target, "normal_return_to_selected", False)
        check_cancel()
        final = validate(backend.observe(), "final_confirmation", expected=target)
        check_cancel()
        score_stable = final["h"] >= selected["h"] * (1 - cfg.improvement)
        improved = target != base
        improvement_confirmed = (not improved or
            final["h"] >= initial["h"] * (1 + cfg.improvement))
        result["selected_h"] = selected["h"]
        result["final_h"] = final["h"]
        result["relative_h_change"] = final["h"] / initial["h"] - 1
        result["at_search_boundary"] = target in allowed
        if not score_stable or not improvement_confirmed:
            result.update(status="unconfirmed", reason="final_contrast_not_confirmed")
        else:
            result.update(status="completed", confirmed=True,
                          reason="improved" if improved else "no_significant_improvement")
        emit("finished", status=result["status"], reason=result["reason"])
    except (Exception, KeyboardInterrupt) as error:
        result["status"] = ("cancelled" if isinstance(error, (_Cancelled, KeyboardInterrupt))
                            else "fault")
        result["confirmed"] = False
        result["reason"] = str(error) or type(error).__name__
        result["error_type"] = type(error).__name__
        # No recovery movement is permitted after uncertainty. stop() must be
        # an idempotent hardware stop, never "return to last best".
        try:
            result["stop"] = backend.stop()
        except Exception as stop_error:
            result["stop"] = {"verified": False, "error": str(stop_error),
                              "error_type": type(stop_error).__name__}
        # A broken observer must not suppress the result or a hardware stop.
        events.append({"kind": "finished", "status": result["status"],
                       "reason": result["reason"]})
    return result
