"""The 32 Pip animation timelines (shared motion definitions).

Each entry: (filename-stem, category, behavior, steps, start_pose, end_pose)
A step is (pose, duration_ms).  Poses build on riglib.pose(); shared numbers
(blink timing, gaze offsets, tilt/tail amounts) come from rig.json so they can
be adjusted in one place.  Loops end on their starting pose so the wrap seam is
invisible; one-shots start and finish neutral (power-down/wake-up share the
"resting" endpoint).
"""
from riglib import pose, lerp_pose, snap, RIG

T = RIG["timing"]
M = RIG["motion"]
G = RIG["eyes"]["gazes"]
SWAY = M["tail_sway_deg"]
WAG = M["tail_wag_deg"]
SETTLE = M["tail_settle_deg"]
DEEP = M["tilt_deep"]
OPP = M["tilt_opposite"]

def g(name):
    return list(G[name])

def tween(p0, p1, steps, ms):
    return [(snap(lerp_pose(p0, p1, (i + 1) / steps)), ms) for i in range(steps)]

def move(g0, g1, ms=90):
    """Pupil travel between two gaze offsets with one deliberate in-between."""
    a = pose(gaze=list(g0))
    b = pose(gaze=list(g1))
    mid = [(g0[i] + g1[i]) / 2 for i in range(2)]
    return [(snap(pose(gaze=mid)), ms), (snap(pose(gaze=list(g1))), 0)]

REST = pose(head_dy=3, tail_rot=SETTLE, lid=[1, 1], mouth="C")   # power-down end == wake-up start

ANIMS = [
# ---------------------------------------------------------------- 01-08 idle
("idle-blink", "Idle and attention", "loop", [
    (pose(), T["blink_hold_ms"]),
    (pose(lid=[0.5, 0.5]), T["blink_half_ms"]),
    (pose(lid=[1, 1]), T["blink_close_ms"]),
    (pose(lid=[0.5, 0.5]), T["blink_open_ms"]),
    (pose(), 400),
], "neutral", "neutral"),

("idle-double-blink", "Idle and attention", "once", [
    (pose(), 1100),
    (pose(lid=[0.5, 0.5]), 70),
    (pose(lid=[1, 1]), 95),
    (pose(lid=[0.5, 0.5]), 55),
    (pose(), 380),
    (pose(lid=[0.5, 0.5]), 55),
    (pose(lid=[1, 1]), 80),
    (pose(lid=[0.5, 0.5]), 45),
    (pose(), 1150),
], "neutral", "neutral"),

("idle-look-around", "Idle and attention", "loop", [
    (pose(), 1200),
    (pose(gaze=[-2, 0]), 90),
    (pose(gaze=g("left")), T["glance_hold_ms"]),
    (pose(gaze=[0, 0]), 90),
    (pose(gaze=g("right")), T["glance_hold_ms"]),
    (pose(gaze=[2, 0]), 90),
    (pose(), 1200),
], "neutral", "neutral"),

("idle-tail-sway", "Idle and attention", "loop", [
    (pose(), 900),
    (pose(tail_rot=SWAY * 0.55), 500),
    (pose(tail_rot=SWAY), 650),
    (pose(tail_rot=SWAY * 0.55), 500),
    (pose(), 450),
    (pose(tail_rot=-SWAY * 0.55), 500),
    (pose(tail_rot=-SWAY), 650),
    (pose(tail_rot=-SWAY * 0.55), 500),
    (pose(), 900),
], "neutral", "neutral"),

("notice", "Idle and attention", "once", [
    (pose(), 550),
    (pose(conv=RIG["eyes"]["viewer_converge"]), 90),
    (pose(conv=RIG["eyes"]["viewer_converge"]), 380),
    (pose(conv=RIG["eyes"]["viewer_converge"], head_dy=M["head_lift"]), 430),
    (pose(conv=RIG["eyes"]["viewer_converge"], head_dy=M["head_lift"]), 250),
    (pose(conv=1), 220),
    (pose(), 700),
], "neutral", "neutral"),

("listening", "Idle and attention", "loop", [
    (pose(), 1300),
    (pose(conv=2), 130),
    (pose(conv=2), T["listen_gaze_delay_ms"] + 50),
    (pose(conv=2, head_pose="tilt", head_dy=-1), 250),
    (pose(conv=2, head_pose="tilt", head_dy=-1), T["listen_hold_ms"] + 50),
    (pose(conv=2), 300),
    (pose(), T["listen_quiet_ms"]),
], "neutral", "neutral"),

("curious", "Idle and attention", "once", [
    (pose(), 450),
    (pose(gaze=g("up_left")), 170),
    (pose(gaze=g("up_left")), 320),
    (pose(gaze=g("up_left"), head_pose="turn_L", arm_n=[2, -1, -8]), 250),
    (pose(gaze=g("up_left"), head_pose="turn_L", arm_n=[2, -1, -8]), 1300),
    (pose(gaze=[-1, -1]), 270),
    (pose(), 650),
], "neutral", "neutral"),

("sleepy", "Idle and attention", "loop", [
    (pose(), 1500),
    (pose(lid=[0.35, 0.35]), 380),
    (pose(lid=[0.7, 0.7], head_dy=1), 380),
    (pose(lid=[1, 1], head_dy=2), 520),
    (pose(lid=[1, 1], head_dy=2), 330),
    (pose(lid=[0.45, 0.45], head_dy=1), 260),
    (pose(), 850),
], "neutral", "neutral"),

# -------------------------------------------------------- 09-16 assistant work
("thinking", "Assistant activity", "loop", [
    (pose(), 700),
    (pose(gaze=[-1, -1]), 90),
    (pose(gaze=g("up_left")), 1500),
    (pose(gaze=g("up_left"), tail_rot=-3), 450),
    (pose(gaze=g("up_left")), 350),
    (pose(gaze=[-1, -1]), 90),
    (pose(), 700),
], "neutral", "neutral"),

("searching", "Assistant activity", "loop", [
    (pose(), 420),
    (pose(gaze=[-2, 0]), 70),
    (pose(gaze=g("left")), 780),
    (pose(gaze=[0, 1]), 70),
    (pose(gaze=[0, 1]), 640),
    (pose(gaze=[2, 0]), 70),
    (pose(gaze=g("right")), 480),
    (pose(gaze=g("right"), head_dx=1, head_rot=2.0), 680),
    (pose(), 520),
], "neutral", "neutral"),

("reading", "Assistant activity", "loop", [
    (pose(), 550),
    (pose(gaze=g("left")), 130),
    (pose(gaze=[-1, 0]), 120),
    (pose(gaze=[2, 0]), 120),
    (pose(gaze=g("right")), 280),
    (pose(gaze=g("left")), 70),
    (pose(gaze=[-1, 1]), 120),
    (pose(gaze=[2, 1]), 120),
    (pose(gaze=[4, 1]), 300),
    (pose(), 750),
], "neutral", "neutral"),

("typing", "Assistant activity", "loop", [
    (pose(), 350),
    (pose(gaze=g("down")), 220),
    (pose(gaze=g("down"), arm_n=[0, -2, 0]), 110),
    (pose(gaze=g("down")), 80),
    (pose(gaze=g("down"), arm_f=[0, -2, 0]), 95),
    (pose(gaze=g("down")), 130),
    (pose(gaze=g("down"), arm_n=[0, -2, 0]), 90),
    (pose(gaze=g("down"), arm_f=[0, -2, 0]), 105),
    (pose(gaze=g("down")), 70),
    (pose(gaze=g("down"), arm_n=[0, -2, 0]), 125),
    (pose(gaze=g("down")), 420),
    (pose(), 550),
], "neutral", "neutral"),

("speaking", "Assistant activity", "loop", [
    (pose(mouth="R"), 280),
    (pose(mouth="S"), 150),
    (pose(mouth="R"), 110),
    (pose(mouth="S"), 230),
    (pose(mouth="C"), 170),
    (pose(mouth="R"), 190),
    (pose(mouth="S"), 120),
    (pose(mouth="C"), 200),
    (pose(mouth="R"), 850),
], "neutral", "neutral"),

("processing", "Assistant activity", "loop", [
    (pose(gaze=[0, -1]), 1300),
    (pose(gaze=[0, -1], arm_n=[3, 1, -6]), T["tap_ms"]),
    (pose(gaze=[0, -1]), 160),
    (pose(gaze=[0, -1], arm_n=[3, 1, -6]), T["tap_ms"]),
    (pose(gaze=[0, -1]), 3250),
], "focused gaze", "focused gaze"),

("waiting", "Assistant activity", "loop", [
    (pose(), 2600),
    (pose(gaze=[1, 0]), 90),
    (pose(gaze=g("tail_side")), 700),
    (pose(gaze=[1, 0]), 90),
    (pose(), 2500),
], "neutral", "neutral"),

("idea", "Assistant activity", "once", [
    (pose(), 550),
    (pose(gaze=g("up")), 520),
    (pose(gaze=g("up"), head_dy=M["head_lift"], arm_n=[-1, -2, M["arm_wave_deg"] - 4]), 260),
    (pose(gaze=g("up"), head_dy=M["head_lift"], arm_n=[-1, -2, M["arm_wave_deg"] - 4]), 1350),
    (pose(gaze=[0, -1], head_dy=-1), 300),
    (pose(), 700),
], "neutral", "neutral"),

# --------------------------------------------------------- 17-24 feedback
("success", "Feedback and reactions", "once", [
    (pose(), 320),
    (pose(head_pose="chin_down"), 170),
    (pose(head_pose="chin_down"), 280),
    (pose(head_pose="chin_up_soft"), 190),
    (pose(), 260),
    (pose(tail_rot=WAG), 220),
    (pose(tail_rot=-WAG), 220),
    (pose(tail_rot=2), 180),
    (pose(), 520),
], "neutral", "neutral"),

("celebrate", "Feedback and reactions", "once", [
    (pose(), 250),
    (pose(body_dy=M["crouch"], lid=[0.3, 0.3]), 150),
    (pose(body_dy=-8, arm_n=[0, -2, 12], arm_f=[0, -2, 0]), 110),
    (pose(body_dy=-M["hop_height"], arm_n=[0, -3, 16], arm_f=[0, -3, 0], tail_rot=-4), 145),
    (pose(body_dy=-6, arm_n=[0, -2, 12], arm_f=[0, -2, 0], tail_rot=-2), 110),
    (pose(body_dy=M["crouch"], tail_rot=4), 135),
    (pose(body_dy=0, tail_rot=2), 155),
    (pose(), 550),
], "neutral", "neutral"),

("acknowledge", "Feedback and reactions", "once", [
    (pose(), 380),
    (pose(head_pose="chin_down"), 180),
    (pose(head_pose="chin_down"), 300),
    (pose(head_pose="chin_up_soft"), 190),
    (pose(), 850),
], "neutral", "neutral"),

("unsure", "Feedback and reactions", "once", [
    (pose(), 400),
    (pose(gaze=[1, 0]), 100),
    (pose(gaze=[2, -1]), 420),
    (pose(gaze=[2, -1], arm_n=[-1, -1, 10]), 350),
    (pose(gaze=[2, -1]), 250),
    (pose(gaze=[1, 0]), 230),
    (pose(), 550),
], "neutral", "neutral"),

("confused", "Feedback and reactions", "once", [
    (pose(), 430),
    (pose(gaze=g("left")), 320),
    (pose(gaze=[-2, 0]), 150),
    (pose(gaze=g("left")), 260),
    (pose(gaze=g("left"), head_rot=2.5), 210),
    (pose(gaze=g("left"), head_rot=2.5), 820),
    (pose(gaze=[-2, 0], head_rot=1), 180),
    (pose(), 640),
], "neutral", "neutral"),

("warning", "Feedback and reactions", "once", [
    (pose(), 300),
    (pose(tail_rot=-3), 160),
    (pose(tail_rot=0, head_rot=OPP * 0.8, head_dy=M["head_lift"], gaze=[0, -1], conv=1), 130),
    (pose(tail_rot=0, head_rot=OPP * 0.8, head_dy=M["head_lift"], gaze=[0, -1], conv=1), 1200),
    (pose(conv=0), 300),
    (pose(), 650),
], "neutral", "neutral"),

("error", "Feedback and reactions", "once", [
    (pose(), 350),
    (pose(head_dx=-2), 350),
    (pose(head_dx=-2, lid=[0.5, 0.5]), 70),
    (pose(head_dx=-2, lid=[1, 1]), 100),
    (pose(head_dx=-2, lid=[0.5, 0.5]), 60),
    (pose(head_dx=-1, head_dy=-1, gaze=[0, -1]), 650),
    (pose(), 600),
], "neutral", "neutral"),

("relieved", "Feedback and reactions", "once", [
    (pose(), 300),
    (pose(lid=[0.5, 0.5], head_dy=1, arm_n=[0, 1, 0], arm_f=[0, 1, 0]), 320),
    (pose(lid=[0.55, 0.55], head_dy=2, mouth="S", arm_n=[0, 1, 0], arm_f=[0, 1, 0]), 800),
    (pose(lid=[0.3, 0.3], head_dy=1, mouth="R"), 380),
    (pose(), 700),
], "neutral", "neutral"),

# --------------------------------------------- 25-32 direction / transitions
("look-left", "Direction, greetings, and transitions", "once", [
    (pose(), 400),
    (pose(gaze=[-2, 0]), 110),
    (pose(gaze=g("left")), 330),
    (pose(gaze=g("left"), head_pose="turn_L"), 230),
    (pose(gaze=g("left"), head_pose="turn_L"), 1250),
    (pose(gaze=g("left")), 190),
    (pose(gaze=[-2, 0]), 110),
    (pose(), 550),
], "neutral", "neutral"),

("look-right", "Direction, greetings, and transitions", "once", [
    (pose(), 400),
    (pose(gaze=[2, 0]), 110),
    (pose(gaze=g("right")), 330),
    (pose(gaze=g("right"), head_pose="turn_R"), 230),
    (pose(gaze=g("right"), head_pose="turn_R"), 1250),
    (pose(gaze=g("right")), 190),
    (pose(gaze=[2, 0]), 110),
    (pose(), 550),
], "neutral", "neutral"),

("look-up", "Direction, greetings, and transitions", "once", [
    (pose(), 420),
    (pose(gaze=g("up")), 140),
    (pose(gaze=g("up")), 320),
    (pose(gaze=g("up"), head_pose="chin_up"), 250),
    (pose(gaze=g("up"), head_pose="chin_up"), 1150),
    (pose(gaze=[0, -1]), 230),
    (pose(), 600),
], "neutral", "neutral"),

("look-down", "Direction, greetings, and transitions", "once", [
    (pose(), 420),
    (pose(gaze=g("down")), 140),
    (pose(gaze=g("down")), 320),
    (pose(gaze=g("down"), head_pose="chin_down"), 250),
    (pose(gaze=g("down"), head_pose="chin_down"), 1150),
    (pose(gaze=[0, 1]), 230),
    (pose(), 600),
], "neutral", "neutral"),

("hello", "Direction, greetings, and transitions", "once", [
    (pose(), 350),
    (pose(conv=2), 320),
    (pose(conv=2, arm_n=[0, -2, M["arm_wave_deg"]]), 190),
    (pose(conv=2, arm_n=[0, -1, 8]), 150),
    (pose(conv=2, arm_n=[0, -2, M["arm_wave_deg"]]), 190),
    (pose(conv=2), 220),
    (pose(), 650),
], "neutral", "neutral"),

("goodbye", "Direction, greetings, and transitions", "once", [
    (pose(), 350),
    (pose(lid=[0.5, 0.5]), 100),
    (pose(lid=[1, 1]), 330),
    (pose(lid=[0.5, 0.5]), 90),
    (pose(), 200),
    (pose(head_dy=1, head_rot=2.5), 260),
    (pose(head_dy=2, head_rot=3.5), 600),
    (pose(head_dy=1, head_rot=2), 300),
    (pose(), 700),
], "neutral", "neutral"),

("wake-up", "Direction, greetings, and transitions", "once", [
    (REST, 500),
    (pose(head_dy=3, tail_rot=SETTLE, lid=[1, 0.45], mouth="C"), 260),
    (pose(head_dy=3, tail_rot=SETTLE * 0.6, lid=[0.5, 0.0], mouth="C"), 260),
    (pose(head_dy=2, tail_rot=SETTLE * 0.3, lid=[0.25, 0], mouth="R"), 300),
    (pose(head_dy=1, mouth="R"), 280),
    (pose(), 700),
], "resting", "neutral"),

("power-down", "Direction, greetings, and transitions", "once", [
    (pose(), 450),
    (pose(tail_rot=SETTLE), 350),
    (pose(tail_rot=SETTLE, head_dy=1, lid=[0.4, 0.4]), 350),
    (pose(tail_rot=SETTLE, head_dy=2, lid=[0.75, 0.75], mouth="C"), 320),
    (REST, 1300),
], "neutral", "resting"),
]

POSE_STILLS = ["neutral", "turn_L", "turn_R", "chin_up", "chin_down", "tilt"]

# Acceptance diagnostic: cycle the three head-gesture families with the pupils
# pinned at neutral so only the head silhouette carries the meaning.
HEAD_DIAGNOSTIC = [
    (pose(), 700),
    (pose(head_pose="turn_L"), 800),
    (pose(), 450),
    (pose(head_pose="turn_R"), 800),
    (pose(), 450),
    (pose(head_pose="chin_down"), 650),
    (pose(head_pose="chin_up_soft"), 400),
    (pose(), 450),
    (pose(head_pose="tilt"), 800),
    (pose(), 700),
]

assert len(ANIMS) == 32, len(ANIMS)
assert len({a[0] for a in ANIMS}) == 32
