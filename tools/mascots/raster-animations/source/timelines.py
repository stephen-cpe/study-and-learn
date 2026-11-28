"""Timelines for all 32 Raster animations.

Each clip is a list of (state, duration_ms) frames.  States are plain dicts (see
render.py for the fields); NEUTRAL is the return pose for ordinary one-shots,
ASLEEP is the shared power-down / wake-up hand-off pose.

Arm pose ladder (arm_model.POSES), swing out of vertical toward the arm's own side:
  r0 0 deg   rest, hand beside the hip
  r1 22      small lift
  r2 45      lift (typing / celebrate height, below the chest)
  r3 68      outward lift
  r4 90      horizontal out, gripper at the outer end
  r5 110     raised low  (wave low)
  r6 121     raised: hand beside the lower edge of the CRT
  r7 133     raised high (wave high)

armR = viewer's right arm = Raster's anatomical LEFT (the waving arm in hello).
armL = viewer's left arm  = Raster's anatomical right.
"""

NEUTRAL = dict(head=(0, 0), gaze=(0, 0), blink=1.0, eye='base', ant='base',
               lamps=('base', 'base', 'base'), armL='r0', armR='r0',
               tapL=(0, 0), tapR=(0, 0))
ASLEEP = dict(NEUTRAL, head=(0, 2), blink=0.0, eye='off', ant='off')


def st(**kw):
    d = dict(NEUTRAL)
    d.update(kw)
    return d


def pose_label(s):
    if s['blink'] <= 0.01 and s['eye'] == 'off' and s['ant'] == 'off':
        return 'asleep'
    bits = []
    if s['armL'] != 'r0':
        bits.append('armL=' + s['armL'])
    if s['armR'] != 'r0':
        bits.append('armR=' + s['armR'])
    if s['head'] != (0, 0):
        bits.append('head%+d%+d' % s['head'])
    if s['gaze'] != (0, 0):
        bits.append('gaze%+d%+d' % s['gaze'])
    if s['blink'] < 0.99:
        bits.append('blink%.2f' % s['blink'])
    if s['eye'] != 'base':
        bits.append('eye:' + s['eye'])
    if s['ant'] != 'base':
        bits.append('ant:' + s['ant'])
    if s['lamps'] != ('base', 'base', 'base'):
        bits.append('lamps:%s' % '/'.join(s['lamps']))
    return ' '.join(bits) if bits else 'neutral'


CLIPS = {}

# ---------------------------------------------------------------------------------
# five wave animations (shared arm poses)
# ---------------------------------------------------------------------------------

CLIPS['hello'] = {'mode': 'once', 'frames': [
    (st(armR='r0'), 500),
    (st(armR='r1'), 110), (st(armR='r2'), 110), (st(armR='r3'), 110),
    (st(armR='r4'), 110), (st(armR='r5'), 100), (st(armR='r6'), 130),
    # two quick up-down waves at the top
    (st(armR='r7'), 110), (st(armR='r5'), 110),
    (st(armR='r7'), 110), (st(armR='r5'), 110),
    # settle
    (st(armR='r6'), 140),
    (st(armR='r4'), 120), (st(armR='r3'), 120), (st(armR='r2'), 120),
    (st(armR='r1'), 120),
    (st(armR='r0'), 700),
]}

CLIPS['goodbye'] = {'mode': 'once', 'frames': [
    (st(armR='r0'), 400),
    (st(armR='r1'), 90), (st(armR='r2'), 90), (st(armR='r3'), 90),
    (st(armR='r4'), 90), (st(armR='r5'), 85), (st(armR='r6'), 95),
    # brisk waves, then linger at the last raised pose
    (st(armR='r7'), 85), (st(armR='r5'), 85),
    (st(armR='r7'), 85), (st(armR='r5'), 85),
    (st(armR='r7'), 330),
    (st(armR='r6'), 150), (st(armR='r5'), 170), (st(armR='r4'), 190),
    (st(armR='r3'), 210), (st(armR='r2'), 230), (st(armR='r1'), 250),
    (st(armR='r0'), 450),
]}

# speaking: one rise-and-fall per second, armL leads armR by one frame
_speak_L = ['r2', 'r3', 'r2', 'r1', 'r2', 'r3', 'r2', 'r1']
_speak_R = ['r1', 'r2', 'r3', 'r2', 'r1', 'r2', 'r3', 'r2']
CLIPS['speaking'] = {'mode': 'loop', 'frames': [
    (st(armL=_speak_L[i], armR=_speak_R[i]), 250) for i in range(8)
]}

CLIPS['idea'] = {'mode': 'once', 'frames': [
    (st(armL='r0', armR='r0'), 250),
    # excited first lift with an eye + antenna accent
    (st(armL='r2', armR='r2', eye='normal_bright', ant='normal_bright'), 90),
    (st(armL='r4', armR='r4', eye='normal_bright', ant='normal_bright'), 90),
    (st(armL='r6', armR='r6', eye='normal_bright', ant='normal_bright'), 80),
    (st(armL='r7', armR='r7', eye='normal_bright', ant='normal_bright'), 230),
    (st(armL='r5', armR='r5', eye='normal_bright'), 80),
    (st(armL='r7', armR='r7', eye='normal_bright'), 90),
    (st(armL='r7', armR='r7'), 270),
    (st(armL='r5', armR='r5'), 80),
    (st(armL='r4', armR='r4'), 110),
    (st(armL='r2', armR='r2'), 120),
    (st(armL='r0', armR='r0'), 350),
]}

CLIPS['encourage'] = {'mode': 'once', 'frames': [
    (st(armL='r0', armR='r0'), 350),
    (st(armL='r2', armR='r2'), 150),
    (st(armL='r3', armR='r3'), 150),
    (st(armL='r4', armR='r4'), 160),
    (st(armL='r5', armR='r5'), 220),
    (st(armL='r3', armR='r3'), 170),
    (st(armL='r5', armR='r5'), 300),      # second lift held a little longer
    (st(armL='r4', armR='r4'), 190),
    (st(armL='r3', armR='r3'), 210),
    (st(armL='r2', armR='r2'), 230),
    (st(armL='r1', armR='r1'), 250),
    (st(armL='r0', armR='r0'), 600),
]}

# ---------------------------------------------------------------------------------
# twelve continuous loops
# ---------------------------------------------------------------------------------

CLIPS['idle-blink'] = {'mode': 'loop', 'frames': [
    (st(blink=1.0), 1700),
    (st(blink=0.45), 80),
    (st(blink=0.0), 100),
    (st(blink=0.45), 80),
]}

CLIPS['idle-look-around'] = {'mode': 'loop', 'frames': [
    (st(), 1500),
    (st(gaze=(-2, 0), head=(-1, 0)), 900),
    (st(gaze=(-1, 0), head=(-1, 0)), 140),
    (st(gaze=(0, 0), head=(0, 0)), 700),
    (st(gaze=(1, 0), head=(1, 0)), 140),
    (st(gaze=(2, 0), head=(1, 0)), 900),
    (st(gaze=(1, 0), head=(1, 0)), 140),
    (st(gaze=(0, 0), head=(0, 0)), 600),
]}

CLIPS['idle-antenna-settle'] = {'mode': 'loop', 'frames': [
    (st(ant='base'), 2300),
    (st(ant='normal_mid'), 130),
    (st(ant='normal_bright'), 170),
    (st(ant='normal_mid'), 130),
]}

CLIPS['listening'] = {'mode': 'loop', 'frames': [
    (st(), 700),
    (st(head=(1, 0), gaze=(1, 0)), 150),
    (st(head=(2, 1), gaze=(2, 0)), 2400),
    (st(head=(1, 0), gaze=(1, 0)), 150),
]}

CLIPS['sleepy'] = {'mode': 'loop', 'frames': [
    (st(blink=0.45, head=(0, 1), eye='normal_dim', ant='normal_dim'), 600),
    (st(blink=0.0, head=(0, 2), eye='off', ant='normal_dim'), 1300),
    (st(blink=0.45, head=(0, 1), eye='off', ant='normal_dim'), 350),
    (st(blink=1.0, head=(0, 0), eye='normal_dim', ant='normal_dim'), 600),
    (st(blink=0.45, head=(0, 1), eye='normal_dim', ant='normal_dim'), 350),
]}

CLIPS['thinking'] = {'mode': 'loop', 'frames': [
    (st(), 900),
    (st(gaze=(2, 0), head=(1, 0)), 160),
    (st(gaze=(2, 0), head=(1, 0), ant='normal_mid'), 1000),
    (st(gaze=(2, 0), head=(1, 0), ant='normal_bright'), 250),
    (st(gaze=(2, 0), head=(1, 0), ant='normal_mid'), 350),
    (st(gaze=(2, 0), head=(1, 0)), 600),
    (st(gaze=(1, 0), head=(0, 0)), 160),
    (st(), 600),
]}

CLIPS['searching'] = {'mode': 'loop', 'frames': [
    (st(gaze=(-2, -1), head=(-1, 0)), 500),
    (st(gaze=(0, -1)), 350),
    (st(gaze=(2, -1), head=(1, 0)), 600),
    (st(gaze=(2, 0), head=(1, 0)), 300),
    (st(gaze=(0, 0)), 450),
    (st(gaze=(-2, 0), head=(-1, 0)), 350),
    (st(gaze=(-2, -1), head=(-1, 0)), 400),
]}

CLIPS['reading'] = {'mode': 'loop', 'frames': [
    (st(gaze=(-2, 0)), 400),
    (st(gaze=(-1, 0)), 300),
    (st(gaze=(0, 0)), 300),
    (st(gaze=(1, 0)), 300),
    (st(gaze=(2, 0)), 400),
    (st(gaze=(-2, 0), blink=0.0), 120),   # reset hidden under the blink
    (st(gaze=(-2, 0), blink=0.45), 200),
]}

CLIPS['typing'] = {'mode': 'loop', 'frames': [
    (st(armL='r2', armR='r2', gaze=(0, 1)), 140),
    (st(armL='r2', armR='r2', gaze=(0, 1), tapL=(0, 1)), 140),
    (st(armL='r2', armR='r2', gaze=(0, 1)), 140),
    (st(armL='r2', armR='r2', gaze=(0, 1), tapR=(0, 1)), 140),
]}

CLIPS['processing'] = {'mode': 'loop', 'frames': [
    (st(lamps=('bright', 'dim', 'dim')), 170),
    (st(lamps=('dim', 'bright', 'dim')), 170),
    (st(lamps=('dim', 'dim', 'bright')), 170),
    (st(lamps=('dim', 'dim', 'dim')), 170),
]}

CLIPS['waiting'] = {'mode': 'loop', 'frames': [
    (st(), 2800),
    (st(ant='normal_mid'), 120),
    (st(ant='normal_bright'), 150),
    (st(ant='normal_mid'), 120),
    (st(), 600),
]}

# ---------------------------------------------------------------------------------
# twenty one-shots
# ---------------------------------------------------------------------------------

CLIPS['idle-double-blink'] = {'mode': 'once', 'frames': [
    (st(blink=1.0), 700),
    (st(blink=0.45), 70), (st(blink=0.0), 80), (st(blink=0.45), 70),
    (st(blink=1.0), 180),
    (st(blink=0.45), 70), (st(blink=0.0), 80), (st(blink=0.45), 70),
    (st(blink=1.0), 1000),
]}

CLIPS['notice'] = {'mode': 'once', 'frames': [
    (st(), 450),
    (st(head=(0, -1), eye='normal_bright', ant='normal_bright'), 260),
    (st(head=(0, -1), eye='normal_bright'), 450),
    (st(), 500),
]}

CLIPS['curious'] = {'mode': 'once', 'frames': [
    (st(), 350),
    (st(head=(1, 1), gaze=(1, 0)), 160),
    (st(head=(2, 1), gaze=(2, 0)), 750),
    (st(head=(2, 1), gaze=(2, 0), ant='normal_mid'), 200),
    (st(head=(2, 1), gaze=(2, 0), ant='normal_bright'), 250),
    (st(head=(2, 1), gaze=(2, 0)), 450),
    (st(), 400),
]}

CLIPS['success'] = {'mode': 'once', 'frames': [
    (st(), 300),
    (st(lamps=('bright', 'bright', 'bright'), eye='normal_bright'), 140),
    (st(lamps=('dim', 'dim', 'dim'), eye='normal_bright'), 160),
    (st(lamps=('bright', 'bright', 'bright'), eye='normal_bright', head=(0, 1)), 160),
    (st(lamps=('bright', 'bright', 'bright'), eye='normal_bright'), 400),
    (st(), 500),
]}

CLIPS['celebrate'] = {'mode': 'once', 'frames': [
    (st(), 400),
    (st(armL='r1', armR='r1', eye='normal_bright'), 160),
    (st(armL='r2', armR='r2', eye='normal_bright'), 880),   # pleased hold
    (st(armL='r1', armR='r1', eye='normal_bright'), 220),
    (st(), 500),
]}

CLIPS['acknowledge'] = {'mode': 'once', 'frames': [
    (st(), 350),
    (st(head=(0, 1)), 130),
    (st(head=(0, 2)), 140),
    (st(head=(0, 1)), 130),
    (st(), 450),
]}

CLIPS['unsure'] = {'mode': 'once', 'frames': [
    (st(), 300),
    (st(gaze=(-2, 0), head=(-1, 0)), 120),
    (st(gaze=(2, 0), head=(1, 0)), 120),
    (st(gaze=(-1, 0), head=(0, 0)), 120),
    (st(gaze=(1, 0)), 120),
    (st(gaze=(0, 0), ant='normal_dim'), 250),
    (st(ant='normal_mid'), 350),
    (st(), 400),
]}

CLIPS['confused'] = {'mode': 'once', 'frames': [
    (st(), 350),
    (st(head=(2, 1), gaze=(-1, 0)), 150),
    (st(head=(2, 1), gaze=(-1, 0), ant='normal_mid'), 400),
    (st(head=(2, 1), gaze=(-1, 0), ant='normal_dim'), 120),
    (st(head=(2, 1), gaze=(-1, 0), ant='normal_mid'), 120),
    (st(head=(2, 1), gaze=(0, 0)), 350),
    (st(), 400),
]}

CLIPS['warning'] = {'mode': 'once', 'frames': [
    (st(), 300),
    (st(eye='warn_a', ant='warn_a'), 400),
    (st(eye='warn_b', ant='warn_b'), 450),
    (st(eye='warn_a', ant='warn_a'), 400),
    (st(eye='warn_b', ant='warn_b'), 450),
    (st(eye='warn_a', ant='warn_a'), 400),
    (st(), 500),
]}

CLIPS['error'] = {'mode': 'once', 'frames': [
    (st(), 350),
    (st(eye='err_a', ant='err_a'), 300),
    (st(eye='err_b', ant='err_b'), 400),
    (st(eye='err_a', ant='err_a'), 300),
    (st(eye='err_b', ant='err_b'), 400),
    (st(eye='err_b', ant='err_b', head=(0, 1)), 250),
    (st(eye='err_b', ant='err_b', head=(0, 2)), 250),
    (st(eye='err_b', ant='err_b', head=(0, 1)), 350),
    (st(eye='err_b', ant='err_b'), 500),
    (st(), 500),
]}

CLIPS['look-left'] = {'mode': 'once', 'frames': [
    (st(), 300),
    (st(gaze=(-1, 0), head=(-1, 0)), 150),
    (st(gaze=(-2, 0), head=(-2, 0)), 1200),
    (st(gaze=(-1, 0), head=(-1, 0)), 180),
    (st(), 350),
]}

CLIPS['look-right'] = {'mode': 'once', 'frames': [
    (st(), 300),
    (st(gaze=(1, 0), head=(1, 0)), 150),
    (st(gaze=(2, 0), head=(2, 0)), 1200),
    (st(gaze=(1, 0), head=(1, 0)), 180),
    (st(), 350),
]}

CLIPS['look-up'] = {'mode': 'once', 'frames': [
    (st(), 300),
    (st(gaze=(0, -1), head=(0, -1)), 150),
    (st(gaze=(0, -2), head=(0, -1)), 1200),
    (st(gaze=(0, -1), head=(0, -1)), 180),
    (st(), 350),
]}

CLIPS['look-down'] = {'mode': 'once', 'frames': [
    (st(), 300),
    (st(gaze=(0, 1), head=(0, 1)), 150),
    (st(gaze=(0, 2), head=(0, 1)), 1200),
    (st(gaze=(0, 1), head=(0, 1)), 180),
    (st(), 350),
]}

CLIPS['power-down'] = {'mode': 'once', 'frames': [
    (st(), 500),
    (st(eye='normal_dim', ant='normal_dim'), 250),
    (st(eye='off', ant='normal_dim', blink=0.45, head=(0, 1)), 250),
    (st(eye='off', ant='off', blink=0.15, head=(0, 1)), 300),
    (dict(ASLEEP), 1050),                      # ends asleep
]}

CLIPS['wake-up'] = {'mode': 'once', 'frames': [
    (dict(ASLEEP), 600),                       # exact power-down end frame
    (st(head=(0, 2), blink=0.15, eye='off', ant='normal_dim'), 250),
    (st(head=(0, 1), blink=0.45, eye='normal_dim', ant='normal_mid'), 250),
    (st(head=(0, 1), blink=1.0, eye='normal_bright', ant='normal_mid'), 300),
    (st(head=(0, 0), blink=1.0, eye='normal_bright', ant='normal_bright'), 400),
    (st(), 900),
]}

# order = the roster order in the brief
ROSTER = [
    'idle-blink', 'idle-look-around', 'idle-antenna-settle', 'listening', 'sleepy',
    'thinking', 'searching', 'reading', 'typing', 'speaking', 'processing', 'waiting',
    'idle-double-blink', 'notice', 'curious', 'idea', 'success', 'celebrate',
    'acknowledge', 'unsure', 'confused', 'warning', 'error', 'encourage',
    'look-left', 'look-right', 'look-up', 'look-down', 'hello', 'goodbye',
    'wake-up', 'power-down',
]

CLIPS = {k: CLIPS[k] for k in ROSTER}
