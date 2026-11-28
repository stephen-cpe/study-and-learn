"""Build the Trace animation pack: 32 animations -> GIFs, PNG frames, manifest,
preview gallery.

The choreography for every animation is defined below in terms of the shared
motion blocks in motions.py (blink, gaze, brow lifts, LED states, lean / squash
/ hop).  Adjust a block there (or a sequence here) and re-run to regenerate.

Run:  python trace-animations/source/build.py            (build everything)
      python trace-animations/source/build.py idle-blink (build one animation)
"""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

from PIL import Image

from motions import (ANCHOR_X, ANCHOR_Y, BLINK_STEPS, DOUBLE_BLINK_STEPS,
                     DOUBLE_BLINK_STEPS_2, NEUTRAL, Pose, Rig, SLOW_BLINK_STEPS,
                     blink_frames, brows, eyes, gaze, glide, hold, hop, lean,
                     led, lids, move, squash)

OUT = Path(__file__).resolve().parent
PACK = OUT.parent
GIFS = PACK / "gifs"
FRAMES = PACK / "frames"
CANVAS = 140


# --------------------------------------------------------------------------
# choreography (poses + per-frame durations in ms)
# --------------------------------------------------------------------------
def animations() -> dict[str, dict]:
    N = NEUTRAL
    A: dict[str, dict] = {}

    def add(name, category, behavior, frames, start="neutral", end="neutral", desc=""):
        A[name] = {"category": category, "behavior": behavior, "frames": frames,
                   "start": start, "end": end, "description": desc}

    CAT_IDLE = "Idle and attention"
    CAT_WORK = "Assistant activity"
    CAT_FEED = "Feedback and reactions"
    CAT_DIR = "Direction, greetings, and transitions"

    # ---- 01-08 idle and attention ----------------------------------------
    add("idle-blink", CAT_IDLE, "loop",
        seq(hold(N, 2200), blink_frames(N), hold(N, 1400)),
        desc="Hold the curious expression, blink once quickly, reopen.")

    add("idle-double-blink", CAT_IDLE, "one-shot",
        seq(hold(N, 600), blink_frames(N, DOUBLE_BLINK_STEPS), hold(N, 260),
            blink_frames(N, DOUBLE_BLINK_STEPS_2), hold(N, 700)),
        desc="Two short blinks with an open beat; the second is quicker.")

    look_l = brows(eyes(gaze(N, (-3, 0)), (-2, 0)), (-1, 0, 0.0))
    look_r = brows(eyes(gaze(N, (2, 0)), (1, 0)), (1, 0, 0.0))
    add("idle-look-around", CAT_IDLE, "loop",
        seq(hold(N, 1400), glide(N, look_l, 240, 2), hold(look_l, 1100),
            glide(look_l, look_r, 220, 2), hold(look_r, 650),
            glide(look_r, N, 260, 2), hold(N, 1000)),
        desc="Eyes drift left, pause, glance right, return home. Wire stays still.")

    sway_l = lean(N, -0.03)
    sway_r = lean(N, 0.03)
    add("idle-sway", CAT_IDLE, "loop",
        seq(hold(N, 700), glide(N, sway_l, 350, 2), hold(sway_l, 450),
            glide(sway_l, N, 350, 2), hold(N, 300),
            glide(N, sway_r, 350, 2), hold(sway_r, 450), glide(sway_r, N, 350, 2)),
        desc="Upper wire leans a few cells each way; bottom stays planted.")

    watch = gaze(N, (-2, 2))
    noticed = brows(watch, (-1, -3, 0.0), (1, -3, 0.0))
    add("notice", CAT_IDLE, "one-shot",
        seq(hold(N, 500), glide(N, watch, 150, 1), hold(watch, 450),
            glide(watch, noticed, 160, 1), hold(noticed, 1100),
            glide(noticed, N, 250, 2), hold(N, 400)),
        desc="Pupils turn to the viewer first; brows lift a beat later.")

    listen = lean(gaze(N, (-1, 1)), -0.025)
    nod = squash(listen, 0.975)
    add("listening", CAT_IDLE, "loop",
        seq(hold(listen, 1100), glide(listen, nod, 90, 1), hold(nod, 80),
            glide(nod, listen, 110, 1), hold(listen, 1300),
            glide(listen, nod, 90, 1), hold(nod, 80),
            glide(nod, listen, 110, 1), hold(listen, 1100)),
        desc="Lean to one side, attentive gaze, small occasional nods.")

    track1 = gaze(N, (-2, 0))
    track2 = gaze(N, (-1, -1))
    curious = brows(track2, (-1, -4, 0.05), (1, -1, 0.0))
    add("curious", CAT_IDLE, "one-shot",
        seq(hold(N, 400), glide(N, track1, 140, 1), hold(track1, 200),
            glide(track1, track2, 160, 1), glide(track2, curious, 160, 1),
            hold(curious, 1400), glide(curious, N, 240, 2), hold(N, 400)),
        desc="One brow rises while the pupils track just above the viewer.")

    s1 = lids(brows(squash(N, 0.985), (0, 1, 0.0), (0, 1, 0.0)), 0.8)
    s2 = lids(brows(squash(N, 0.97), (0, 1, 0.0), (0, 1, 0.0)), 0.6)
    s3 = lids(brows(squash(N, 0.965), (0, 1, 0.0), (0, 1, 0.0)), 0.5)
    add("sleepy", CAT_IDLE, "loop",
        seq(hold(N, 1000), glide(N, s1, 500, 2), hold(s1, 400),
            glide(s1, s2, 400, 2), hold(s2, 300), glide(s2, s3, 300, 2),
            hold(s3, 600), glide(s3, s1, 450, 2), hold(s1, 300),
            glide(s1, N, 400, 2)),
        desc="Lids droop, the upper loop dips, then the eyes ease open.")

    # ---- 09-16 assistant activity ----------------------------------------
    think = gaze(N, (-3, -1))
    add("thinking", CAT_WORK, "loop",
        seq(hold(led(think, "bright"), 650), hold(led(think, "mid"), 650),
            hold(led(think, "bright"), 650), hold(led(think, "mid"), 650)),
        desc="Look up to one side; the status light slowly pulses (teal tones).")

    p1 = gaze(N, (-3, 1))
    p2 = gaze(N, (0, 0))
    p3 = gaze(N, (2, -1))
    add("searching", CAT_WORK, "loop",
        seq(hold(p1, 450), glide(p1, p2, 130, 1), hold(p2, 450),
            glide(p2, p3, 130, 1), hold(p3, 550), hold(p3, 500),
            glide(p3, p1, 160, 2)),
        desc="Pupils scan in three deliberate stops, pause, return to the first.")

    def sweep(y, x0=-2, x1=2, step_ms=90):
        out = []
        xs = list(range(x0, x1))
        for a, b in zip(xs, xs[1:]):
            out.extend(glide(gaze(N, (a, y)), gaze(N, (b, y)), step_ms, 1))
        return out

    r_start = gaze(N, (-2, 0))
    add("reading", CAT_WORK, "loop",
        seq(hold(r_start, 200), sweep(0), hold(gaze(N, (2, 0)), 250),
            glide(gaze(N, (2, 0)), r_start, 70, 1), hold(r_start, 60),
            glide(r_start, gaze(N, (-2, 1)), 70, 1), sweep(1),
            hold(gaze(N, (2, 1)), 250),
            glide(gaze(N, (2, 1)), r_start, 100, 2)),
        desc="Eyes scan a short line, snap back, repeat one cell lower, reset.")

    t_pose = gaze(N, (0, 2))
    tip1 = squash(t_pose, 0.988)
    add("typing", CAT_WORK, "loop",
        seq(hold(t_pose, 140), (tip1, 120), (t_pose, 90), (tip1, 140),
            (t_pose, 80), (tip1, 160), (t_pose, 100), (tip1, 130),
            (t_pose, 90), (tip1, 110), (t_pose, 150)),
        desc="Look slightly down; short irregular upper-body dips for keystrokes.")

    def write_line(y, back_to):
        out = []
        out.extend(glide(gaze(N, (-4, y)), gaze(N, (2, y)), 780, 6))
        out.extend(hold(gaze(N, (2, y)), 550))
        out.extend(glide(gaze(N, (2, y)), back_to, 330, 3))
        return out

    w_start = gaze(N, (-4, 0))
    add("writing", CAT_WORK, "loop",
        seq(hold(w_start, 250), write_line(0, gaze(N, (-4, 1))),
            write_line(1, w_start)),
        desc="One long smooth eye sweep, pause at the end, return for the next line.")

    f_pose = gaze(N, (-1, 0))
    add("processing", CAT_WORK, "loop",
        seq(hold(led(f_pose, "dim"), 800), hold(led(f_pose, "mid"), 800),
            hold(led(f_pose, "bright"), 800), hold(led(f_pose, "mid"), 800)),
        desc="Focused gaze; the status light cycles dim-medium-bright, quietly.")

    glancing = gaze(N, (1, 2))
    add("waiting", CAT_WORK, "loop",
        seq(hold(N, 2200), glide(N, glancing, 220, 2), hold(glancing, 1300),
            glide(glancing, N, 260, 2), hold(N, 2400)),
        desc="Patient holds with one glance toward the collared tip.")

    up = gaze(N, (-1, -1))
    lit = led(brows(up, (-1, -4, 0.0), (1, -4, 0.0)), "bright")
    add("idea", CAT_WORK, "one-shot",
        seq(hold(N, 350), glide(N, up, 150, 1), hold(up, 500),
            glide(up, lit, 150, 1), hold(lit, 1400),
            glide(lit, N, 280, 2), hold(N, 400)),
        desc="Glance up, pause, both brows lift as the light brightens once.")

    # ---- 17-24 feedback and reactions ------------------------------------
    n1 = squash(led(N, "bright"), 0.975)
    n2 = squash(led(N, "bright"), 0.94)
    n3 = squash(led(N, "bright"), 0.99)
    add("success", CAT_FEED, "one-shot",
        seq(hold(N, 300), glide(N, n1, 110, 1), glide(n1, n2, 110, 1),
            hold(n2, 90), glide(n2, n3, 120, 1), glide(n3, led(N, "bright"), 140, 1),
            hold(led(N, "bright"), 650), hold(N, 350)),
        desc="One confident nod and one clear teal acknowledgment pulse.")

    antic = squash(N, 0.93, 1.04)
    lift1 = hop(N, -4, 1.06)
    peak = hop(N, -8, 1.02)
    fall = hop(N, -3, 1.0)
    land = hop(N, 1, 0.93)
    settle = squash(N, 0.985, 1.01)
    add("celebrate", CAT_FEED, "one-shot",
        seq(hold(N, 250), glide(N, antic, 130, 1), hold(antic, 70),
            glide(antic, lift1, 90, 1), glide(lift1, peak, 100, 1),
            hold(peak, 90), glide(peak, fall, 90, 1), glide(fall, land, 90, 1),
            hold(land, 110), glide(land, settle, 110, 1),
            glide(settle, N, 130, 1), hold(N, 350)),
        desc="Anticipation, buoyant hop, landing, quick settle (biggest move).")

    a1 = squash(N, 0.98)
    a2 = squash(N, 0.965)
    a3 = squash(N, 0.99)
    add("acknowledge", CAT_FEED, "one-shot",
        seq(hold(N, 350), glide(N, a1, 110, 1), glide(a1, a2, 110, 1),
            hold(a2, 100), glide(a2, a3, 110, 1), glide(a3, N, 120, 1),
            hold(N, 450)),
        desc="A restrained single nod; steady eyes, steady light.")

    ua = gaze(N, (-3, 1))
    ub = gaze(N, (-1, 1))
    hes = brows(ua, (-1, -3, 0.08), (1, 1, 0.0))
    add("unsure", CAT_FEED, "one-shot",
        seq(hold(N, 350), glide(N, ua, 150, 1), hold(ua, 260),
            glide(ua, ub, 130, 1), hold(ub, 220), glide(ub, ua, 130, 1),
            hold(ua, 240), glide(ua, hes, 140, 1), hold(hes, 800),
            glide(hes, N, 250, 2), hold(N, 400)),
        desc="Pupils hesitate between two spots; one brow lifts, one stays low.")

    look = gaze(N, (-3, 0))
    tilt = lean(brows(look, (-1, -2, 0.06), (1, 0, -0.02)), 0.035)
    add("confused", CAT_FEED, "one-shot",
        seq(hold(N, 350), glide(N, look, 150, 1), hold(look, 250),
            glide(look, tilt, 220, 1), hold(tilt, 900),
            glide(tilt, N, 280, 2), hold(N, 400)),
        desc="Look one way, tilt the upper loop the other way, puzzled hold.")

    alert = move(brows(gaze(N, (-1, 0)), (0, -3, 0.0), (0, -3, 0.0)), 0, -1)
    alert = replace(alert, vscale=1.04, hscale=0.98)
    add("warning", CAT_FEED, "one-shot",
        seq(hold(N, 350), glide(N, alert, 120, 1), hold(alert, 1500),
            glide(alert, N, 220, 2), hold(N, 400)),
        desc="Straighten and hold an alert posture (reads in grayscale).")

    rec = lean(move(led(N, "dim"), 0, 2), -0.02)
    add("error", CAT_FEED, "one-shot",
        seq(hold(N, 350), glide(N, rec, 100, 1), hold(rec, 60),
            [(lids(rec, 0.55), 60), (lids(rec, 0.0), 70), (lids(rec, 0.55), 60)],
            hold(rec, 120), glide(rec, N, 180, 2), hold(N, 850)),
        desc="Recoil, one blink, recover to a composed pose; light dims briefly.")

    soft = lids(brows(squash(N, 0.985), (0, 2, 0.0), (0, 2, 0.0)), 0.8)
    ease = lids(brows(squash(N, 0.99), (0, 1, 0.0), (0, 1, 0.0)), 0.85)
    add("relieved", CAT_FEED, "one-shot",
        seq(hold(N, 350), glide(N, soft, 250, 2), hold(soft, 550),
            glide(soft, ease, 300, 2), hold(ease, 350),
            glide(ease, N, 250, 2), hold(N, 350)),
        desc="Lower the brows, soften the lids, ease the loop back to rest.")

    # ---- 25-32 direction, greetings, transitions -------------------------
    left = brows(eyes(gaze(N, (-3, 0)), (-2, 0)), (-2, 0, 0.0))
    add("look-left", CAT_DIR, "one-shot",
        seq(hold(N, 350), glide(N, left, 180, 2), hold(left, 1150),
            glide(left, N, 250, 2), hold(N, 350)),
        desc="Both pupils move left and hold to direct attention.")

    right = brows(eyes(gaze(N, (2, 0)), (1, 0)), (2, 0, 0.0))
    add("look-right", CAT_DIR, "one-shot",
        seq(hold(N, 350), glide(N, right, 180, 2), hold(right, 1150),
            glide(right, N, 250, 2), hold(N, 350)),
        desc="Same timing as look-left, with the pupils moving right.")

    u1 = gaze(N, (0, -1))
    u2 = brows(u1, (-1, -2, 0.0), (1, -2, 0.0))
    add("look-up", CAT_DIR, "one-shot",
        seq(hold(N, 350), glide(N, u1, 150, 1), hold(u1, 130),
            glide(u1, u2, 160, 1), hold(u2, 1050),
            glide(u2, N, 250, 2), hold(N, 350)),
        desc="Pupils lead upward, then the brows lift slightly.")

    d1 = gaze(N, (0, 2))
    d2 = lean(brows(d1, (0, 1, 0.0), (0, 1, 0.0)), 0.03)
    add("look-down", CAT_DIR, "one-shot",
        seq(hold(N, 350), glide(N, d1, 150, 1), hold(d1, 130),
            glide(d1, d2, 170, 1), hold(d2, 1050),
            glide(d2, N, 250, 2), hold(N, 350)),
        desc="Lower the pupils and tip the upper loop forward a little.")

    onv = gaze(N, (-1, 1))
    b1 = hop(onv, -3, 1.04)
    b2 = hop(onv, 1, 0.96)
    wave = brows(onv, (-1, -4, 0.0), (1, -1, 0.0))
    add("hello", CAT_DIR, "one-shot",
        seq(hold(N, 300), glide(N, b1, 100, 1), hold(b1, 70),
            glide(b1, b2, 90, 1), hold(b2, 80), glide(b2, onv, 110, 1),
            hold(onv, 120), glide(onv, wave, 160, 1), hold(wave, 1150),
            glide(wave, N, 250, 2), hold(N, 350)),
        desc="A small welcoming bounce, then an asymmetric brow lift.")

    bowp = lean(squash(N, 0.975), 0.055)
    add("goodbye", CAT_DIR, "one-shot",
        seq(hold(N, 350), glide(N, bowp, 200, 2),
            [(lids(bowp, 0.5), 90), (lids(bowp, 0.0), 150), (lids(bowp, 0.5), 90)],
            hold(bowp, 250), glide(bowp, N, 300, 2), hold(N, 400)),
        desc="A warm longer blink and a gentle bow, ending on the original pose.",
        start="neutral", end="neutral")

    d0 = lids(brows(squash(N, 0.965), (0, 2, 0.0), (0, 2, 0.0)), 0.35, right=0.30)
    w_l1 = lids(d0, 0.75, right=0.35)
    w_l2 = lids(d0, 0.95, right=0.55)
    w_l3 = lids(d0, 1.0, right=0.85)
    w_l4 = lids(brows(squash(N, 0.99), (0, 1, 0.0), (0, 1, 0.0)), 1.0)
    add("wake-up", CAT_DIR, "one-shot",
        seq(hold(d0, 700), [(w_l1, 250)], hold(w_l1, 150), [(w_l2, 280)],
            hold(w_l2, 120), [(w_l3, 240)], hold(w_l3, 100), [(w_l4, 220)],
            hold(w_l4, 150), glide(w_l4, N, 200, 1), hold(N, 350)),
        desc="From the drooped pose, one eye opens first, then straighten.",
        start="drooped-sleepy", end="neutral")

    p_m = led(N, "mid")
    p_d = led(brows(N, (0, 1, 0.0), (0, 1, 0.0)), "dim")
    p_o1 = lids(led(brows(squash(N, 0.99), (0, 2, 0.0), (0, 2, 0.0)), "off"), 0.45)
    p_o2 = lids(brows(squash(N, 0.975), (0, 2, 0.0), (0, 2, 0.0)), 0.0)
    p_o2 = led(p_o2, "off")
    add("power-down", CAT_DIR, "one-shot",
        seq(hold(N, 450), glide(N, p_m, 350, 1), hold(p_m, 300),
            glide(p_m, p_d, 350, 1), hold(p_d, 300), glide(p_d, p_o1, 350, 2),
            hold(p_o1, 250), glide(p_o1, p_o2, 350, 2), hold(p_o2, 1300)),
        desc="Dim the light, lower the brows, settle eyes-closed and hold.",
        start="neutral", end="eyes-closed-rest")

    return A


def seq(*chunks) -> list[tuple[Pose, int]]:
    out: list[tuple[Pose, int]] = []
    for c in chunks:
        if isinstance(c, tuple) and len(c) == 2 and isinstance(c[1], int):
            out.append(c)
        else:
            out.extend(c)
    return out


# --------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------
def palette_indices() -> tuple[list[int], dict]:
    pal = [tuple(c) for c in json.loads((OUT / "palette.json").read_text())]
    flat = [0, 0, 0]
    index = {}
    for i, c in enumerate(pal):
        flat += list(c)
        index[c] = i + 1
    flat += [0] * (768 - len(flat))
    return flat, index


FLAT_PALETTE, COLOR_INDEX = palette_indices()
TRANSPARENT_INDEX = 0


def to_p(img: Image.Image) -> Image.Image:
    p = Image.new("P", (CANVAS, CANVAS))
    p.putpalette(FLAT_PALETTE)
    src = img.load()
    memo: dict = {}
    data = []
    for y in range(CANVAS):
        for x in range(CANVAS):
            r, g, b, a = src[x, y]
            if a < 128:
                data.append(TRANSPARENT_INDEX)
                continue
            key = (r, g, b)
            idx = memo.get(key)
            if idx is None:
                best, bd = 1, 1 << 30
                for col, i in COLOR_INDEX.items():
                    d = (col[0] - r) ** 2 + (col[1] - g) ** 2 + (col[2] - b) ** 2
                    if d < bd:
                        bd, best = d, i
                memo[key] = idx = best
            data.append(idx)
    p.putdata(data)
    return p


def export(name: str, frames: list[tuple[Pose, int]], rig: Rig) -> dict:
    GIFS.mkdir(exist_ok=True)
    fdir = FRAMES / name
    fdir.mkdir(parents=True, exist_ok=True)
    for old in fdir.glob("*.png"):
        old.unlink()

    # render, then hold identical frames as one frame with a longer duration
    # (whole-pixel motion makes some interpolated steps identical)
    merged: list[list] = []
    for pose, ms in frames:
        im = rig.render(pose)
        ms = max(10, (ms + 5) // 10 * 10)
        if merged and merged[-1][2] == im.tobytes():
            merged[-1][1] += ms
        else:
            merged.append([im, ms, im.tobytes()])

    imgs = [m[0] for m in merged]
    durations = [m[1] for m in merged]
    for i, im in enumerate(imgs):
        im.save(fdir / f"{i:02d}.png")

    loop = ANIMS[name]["behavior"] == "loop"
    gif_path = GIFS / f"{name}.gif"
    pimgs = [to_p(im) for im in imgs]
    kwargs = dict(save_all=True, append_images=pimgs[1:], duration=durations,
                  transparency=TRANSPARENT_INDEX, disposal=2, optimize=False)
    if loop:
        kwargs["loop"] = 0
    pimgs[0].save(gif_path, **kwargs)

    return {
        "name": name,
        "category": ANIMS[name]["category"],
        "description": ANIMS[name]["description"],
        "gif": f"gifs/{name}.gif",
        "frames_dir": f"frames/{name}",
        "behavior": ANIMS[name]["behavior"],
        "loops": loop,
        "frame_count": len(imgs),
        "frame_durations_ms": durations,
        "total_duration_ms": sum(durations),
        "start_pose": ANIMS[name]["start"],
        "end_pose": ANIMS[name]["end"],
        "canvas": [CANVAS, CANVAS],
    }


# --------------------------------------------------------------------------
# preview gallery
# --------------------------------------------------------------------------
def write_preview(entries: list[dict]) -> None:
    cats = []
    for e in entries:
        if e["category"] not in cats:
            cats.append(e["category"])
    cards = ""
    for cat in cats:
        cards += f'<h2 class="cat">{cat}</h2><div class="grid">'
        for e in entries:
            if e["category"] != cat:
                continue
            kind = "loop" if e["loops"] else "one-shot"
            cards += f"""
      <div class="card" data-name="{e['name']}" data-gif="{e['gif']}"
           data-still="{e['frames_dir']}/00.png">
        <div class="meta">
          <span class="name">{e['name']}</span>
          <span class="tag {kind}">{kind}</span>
        </div>
        <div class="stages">
          <div class="stage"><img alt="{e['name']} 48px"><span class="px">48 px</span></div>
          <div class="stage"><img alt="{e['name']} 96px"><span class="px">96 px</span></div>
        </div>
        <div class="desc">{e['description']}</div>
        <div class="info">{e['frame_count']} frames &middot; {e['total_duration_ms']} ms
          &middot; {e['start_pose']} &rarr; {e['end_pose']}</div>
        <div class="controls">
          <button class="play">Play</button>
          <button class="replay">Replay</button>
          <button class="stop">Still</button>
        </div>
      </div>"""
        cards += "</div>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Trace animation pack</title>
<style>
  :root {{ --bg:#f2f3f7; --fg:#1b1d26; --card:#ffffff; --line:#d8dbe4; --stage:#e9ebf2; }}
  body.dark {{ --bg:#15171e; --fg:#e8eaf2; --card:#1e212b; --line:#343846; --stage:#0c0d12; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; padding:24px; background:var(--bg); color:var(--fg);
         font:14px/1.45 system-ui,Segoe UI,sans-serif; }}
  h1 {{ font-size:20px; margin:0 0 4px; }}
  .sub {{ opacity:.7; margin-bottom:16px; }}
  .bar {{ position:sticky; top:0; z-index:5; display:flex; gap:8px; flex-wrap:wrap;
          align-items:center; padding:10px 0 14px; background:var(--bg); }}
  button, select {{ font:inherit; padding:6px 12px; border:1px solid var(--line);
          border-radius:8px; background:var(--card); color:var(--fg); cursor:pointer; }}
  button:hover {{ border-color:#8ab4f8; }}
  .cat {{ font-size:15px; margin:22px 0 10px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:14px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:12px;
           padding:12px; }}
  .meta {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; }}
  .name {{ font-weight:600; }}
  .tag {{ font-size:11px; padding:2px 8px; border-radius:99px; border:1px solid var(--line); }}
  .tag.loop {{ color:#0a7d4b; border-color:#0a7d4b; }}
  .tag.one-shot {{ color:#a2570a; border-color:#a2570a; }}
  .stages {{ display:flex; gap:14px; align-items:flex-end; }}
  .stage {{ background:var(--stage); border:1px solid var(--line); border-radius:10px;
            padding:8px; display:flex; flex-direction:column; align-items:center; gap:4px; }}
  .stage img {{ image-rendering:pixelated; display:block; }}
  .stage:first-child img {{ width:48px; height:48px; }}
  .stage:last-child img {{ width:96px; height:96px; }}
  .px {{ font-size:10px; opacity:.6; }}
  .desc {{ margin:8px 0 4px; min-height:34px; }}
  .info {{ font-size:11px; opacity:.6; }}
  .controls {{ display:flex; gap:6px; margin-top:8px; }}
  .controls button {{ padding:4px 10px; font-size:12px; }}
</style>
</head>
<body>
  <h1>Trace animation pack</h1>
  <div class="sub">32 animations &middot; 140&times;140 canvas &middot; transparent GIF + PNG
    frames &middot; generated from trace.png</div>
  <div class="bar">
    <button id="bg">Dark background</button>
    <button id="playall">Play all</button>
    <button id="stopall">All still</button>
    <span class="sub" style="margin:0">Thumbnails stay still until you press Play.</span>
  </div>
  {cards}
<script>
  function applySizes() {{
    document.querySelectorAll('.card').forEach(card => {{
      const imgs = card.querySelectorAll('img');
      imgs.forEach(img => {{
        if (!img.dataset.state || img.dataset.state === 'still')
          img.src = card.dataset.still;
      }});
    }});
  }}
  function setPlay(card, mode) {{
    const imgs = card.querySelectorAll('img');
    imgs.forEach(img => {{
      if (mode === 'play') {{ img.dataset.state = 'play'; img.src = card.dataset.gif; }}
      else if (mode === 'replay') {{
        img.dataset.state = 'play';
        img.src = card.dataset.still;
        void img.offsetWidth;
        img.src = card.dataset.gif + '?t=' + Date.now();
      }} else {{ img.dataset.state = 'still'; img.src = card.dataset.still; }}
    }});
  }}
  document.querySelectorAll('.card').forEach(card => {{
    card.querySelector('.play').onclick = () => setPlay(card, 'play');
    card.querySelector('.replay').onclick = () => setPlay(card, 'replay');
    card.querySelector('.stop').onclick = () => setPlay(card, 'still');
    card.querySelector('.stages').onclick = () => setPlay(card, 'replay');
  }});
  document.getElementById('bg').onclick = function () {{
    document.body.classList.toggle('dark');
    this.textContent = document.body.classList.contains('dark')
      ? 'Light background' : 'Dark background';
  }};
  document.getElementById('playall').onclick = () =>
    document.querySelectorAll('.card').forEach(c => setPlay(c, 'play'));
  document.getElementById('stopall').onclick = () =>
    document.querySelectorAll('.card').forEach(c => setPlay(c, 'still'));
  applySizes();
</script>
</body>
</html>
"""
    (PACK / "preview.html").write_text(html, encoding="utf-8")


# --------------------------------------------------------------------------
def main() -> None:
    global ANIMS
    ANIMS = animations()
    only = set(sys.argv[1:])
    rig = Rig()
    entries = []
    for name, spec in ANIMS.items():
        if only and name not in only:
            continue
        entries.append(export(name, spec["frames"], rig))
        print(f"built {name}: {entries[-1]['frame_count']} frames, "
              f"{entries[-1]['total_duration_ms']} ms, "
              f"{'loop' if entries[-1]['loops'] else 'one-shot'}")

    if not only:
        (PACK / "manifest.json").write_text(
            json.dumps({
                "sprite": "trace.png",
                "working_grid": "128x128 cells at ~9.8x9.73 px/cell (measured)",
                "canvas": [CANVAS, CANVAS],
                "anchor": [ANCHOR_X, ANCHOR_Y],
                "count": len(entries),
                "animations": entries,
            }, indent=2), encoding="utf-8")
        write_preview(entries)
        print(f"wrote manifest.json and preview.html ({len(entries)} animations)")


ANIMS: dict[str, dict] = {}

if __name__ == "__main__":
    main()
