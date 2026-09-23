"""Rule-based coaching feedback from metric assessments."""

from __future__ import annotations

from .reference import Assessment

MAX_POINTS = 4

# Most important first; used to break ties between equally severe issues.
PRIORITY = [
    ("contact", "wrist_height"),
    ("contact", "elbow_angle"),
    ("trophy", "front_knee_flexion"),
    ("trophy", "back_knee_flexion"),
    ("racket_drop", "elbow_angle"),
    ("trophy", "trunk_tilt"),
    ("contact", "front_knee_flexion"),
    ("trophy", "elbow_angle"),
    ("racket_drop", "trunk_tilt"),
    ("contact", "trunk_tilt"),
]

RULES: dict[tuple[str, str, str], str] = {
    ("contact", "wrist_height", "low"):
        "Hit the ball higher: at contact your wrist is at {value:.2f} body heights "
        "(target {lo:.2f}-{hi:.2f}). Reach up fully and drive up with your legs.",
    ("contact", "wrist_height", "high"):
        "Your contact point measures unusually high ({value:.2f} body heights). "
        "Check the camera is level and side-on.",
    ("contact", "elbow_angle", "low"):
        "Straighten your hitting arm at contact: your elbow is at {value:.0f}° "
        "(target {lo:.0f}-{hi:.0f}°). A bent arm loses height and power.",
    ("trophy", "front_knee_flexion", "low"):
        "Bend your front knee more in the trophy position ({value:.0f}°, target "
        "{lo:.0f}-{hi:.0f}°) so you can push up into the ball.",
    ("trophy", "front_knee_flexion", "high"):
        "You sit very deep on your front knee at the trophy ({value:.0f}°, target "
        "{lo:.0f}-{hi:.0f}°); a slightly shallower bend is easier to push out of quickly.",
    ("trophy", "back_knee_flexion", "low"):
        "Load your back leg more at the trophy position ({value:.0f}°, target "
        "{lo:.0f}-{hi:.0f}°).",
    ("trophy", "back_knee_flexion", "high"):
        "Your back knee is very bent at the trophy ({value:.0f}°, target {lo:.0f}-{hi:.0f}°).",
    ("trophy", "elbow_angle", "low"):
        "Your hitting elbow is tightly bent at the trophy ({value:.0f}°, target "
        "{lo:.0f}-{hi:.0f}°); lift the racket up with the elbow near shoulder height.",
    ("trophy", "elbow_angle", "high"):
        "Your hitting arm is too straight at the trophy ({value:.0f}°, target "
        "{lo:.0f}-{hi:.0f}°); bend the elbow to set up the racket drop.",
    ("trophy", "trunk_tilt", "low"):
        "Tilt your shoulders more at the trophy ({value:.0f}° from vertical, target "
        "{lo:.0f}-{hi:.0f}°): the tossing shoulder should be higher than the hitting one.",
    ("trophy", "trunk_tilt", "high"):
        "You lean a lot at the trophy ({value:.0f}° from vertical, target "
        "{lo:.0f}-{hi:.0f}°), which can pull the toss and your balance off line.",
    ("racket_drop", "elbow_angle", "low"):
        "Your elbow folds very tightly in the racket drop ({value:.0f}°, target "
        "{lo:.0f}-{hi:.0f}°).",
    ("racket_drop", "elbow_angle", "high"):
        "Let the racket drop deeper behind your back: your elbow only bends to "
        "{value:.0f}° (target {lo:.0f}-{hi:.0f}°), which shortens the swing path.",
    ("racket_drop", "trunk_tilt", "low"):
        "Keep your trunk tilted through the racket drop ({value:.0f}°, target {lo:.0f}-{hi:.0f}°).",
    ("racket_drop", "trunk_tilt", "high"):
        "You lean too far during the racket drop ({value:.0f}°, target {lo:.0f}-{hi:.0f}°).",
    ("contact", "front_knee_flexion", "high"):
        "Extend your legs fully by contact: your front knee is still bent {value:.0f}° "
        "(target {lo:.0f}-{hi:.0f}°).",
    ("contact", "trunk_tilt", "low"):
        "Your trunk is very upright at contact ({value:.0f}°, target {lo:.0f}-{hi:.0f}°).",
    ("contact", "trunk_tilt", "high"):
        "You are leaning a lot at contact ({value:.0f}°, target {lo:.0f}-{hi:.0f}°); "
        "try to hit up and through the ball rather than falling sideways.",
}

SEVERITY = {"off": 0, "borderline": 1}

ALL_GOOD = "Everything we could measure is within the reference ranges. Nice serve!"
NOTHING_MEASURED = (
    "We couldn't measure enough of the serve to give feedback. Film side-on with "
    "your whole body in frame."
)


def _rank(a: Assessment) -> tuple[int, int]:
    key = (a.phase, a.metric)
    priority = PRIORITY.index(key) if key in PRIORITY else len(PRIORITY)
    return SEVERITY[a.status], priority


def generate(assessments: list[Assessment], max_points: int = MAX_POINTS) -> list[str]:
    """Up to ``max_points`` messages, worst and most important first."""
    issues = [a for a in assessments if a.status in SEVERITY and a.direction is not None]
    points = []
    for a in sorted(issues, key=_rank):
        template = RULES.get((a.phase, a.metric, a.direction))
        if template is None:
            continue
        lo, hi = a.range.good
        points.append(template.format(value=a.value, lo=lo, hi=hi))
        if len(points) == max_points:
            break
    if points:
        return points
    if any(a.status == "good" for a in assessments):
        return [ALL_GOOD]
    return [NOTHING_MEASURED]
