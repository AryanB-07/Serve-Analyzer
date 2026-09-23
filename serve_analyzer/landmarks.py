"""MediaPipe Pose landmark indices and hitting/tossing side mapping.

MediaPipe's LEFT/RIGHT refer to the player's anatomical sides, not the
viewer's, so a right-handed player hits with the RIGHT_* landmarks.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Hand

NUM_LANDMARKS = 33

NOSE = 0
LEFT_SHOULDER, RIGHT_SHOULDER = 11, 12
LEFT_ELBOW, RIGHT_ELBOW = 13, 14
LEFT_WRIST, RIGHT_WRIST = 15, 16
LEFT_HIP, RIGHT_HIP = 23, 24
LEFT_KNEE, RIGHT_KNEE = 25, 26
LEFT_ANKLE, RIGHT_ANKLE = 27, 28

SKELETON_EDGES: list[tuple[int, int]] = [
    (LEFT_SHOULDER, RIGHT_SHOULDER),
    (LEFT_SHOULDER, LEFT_ELBOW), (LEFT_ELBOW, LEFT_WRIST),
    (RIGHT_SHOULDER, RIGHT_ELBOW), (RIGHT_ELBOW, RIGHT_WRIST),
    (LEFT_SHOULDER, LEFT_HIP), (RIGHT_SHOULDER, RIGHT_HIP),
    (LEFT_HIP, RIGHT_HIP),
    (LEFT_HIP, LEFT_KNEE), (LEFT_KNEE, LEFT_ANKLE),
    (RIGHT_HIP, RIGHT_KNEE), (RIGHT_KNEE, RIGHT_ANKLE),
]


@dataclass(frozen=True)
class ArmSide:
    shoulder: int
    elbow: int
    wrist: int


@dataclass(frozen=True)
class LegSide:
    hip: int
    knee: int
    ankle: int


LEFT_ARM = ArmSide(LEFT_SHOULDER, LEFT_ELBOW, LEFT_WRIST)
RIGHT_ARM = ArmSide(RIGHT_SHOULDER, RIGHT_ELBOW, RIGHT_WRIST)
LEFT_LEG = LegSide(LEFT_HIP, LEFT_KNEE, LEFT_ANKLE)
RIGHT_LEG = LegSide(RIGHT_HIP, RIGHT_KNEE, RIGHT_ANKLE)


def hitting_arm(hand: Hand) -> ArmSide:
    return RIGHT_ARM if hand is Hand.RIGHT else LEFT_ARM


def tossing_arm(hand: Hand) -> ArmSide:
    return LEFT_ARM if hand is Hand.RIGHT else RIGHT_ARM


def front_leg(hand: Hand) -> LegSide:
    """The leg on the tossing side, which is in front in a standard serve stance."""
    return LEFT_LEG if hand is Hand.RIGHT else RIGHT_LEG


def back_leg(hand: Hand) -> LegSide:
    return RIGHT_LEG if hand is Hand.RIGHT else LEFT_LEG
