"""Sagittal-plane visualizer for the bipedal gait in src/gait.py.

Runs entirely in matplotlib — no robot hardware needed. Sliders let you tune
step length, clearance, standing height, swing velocity and leg geometry, and
the animation re-renders the gait cycle live.

Install (once):
    uv add --dev matplotlib    # or: pip install matplotlib

Run:
    uv run python src/playground/gait_viz.py
"""

import math
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.animation import FFMpegWriter, FuncAnimation, PillowWriter
from matplotlib.widgets import Button, Slider


@dataclass
class Params:
    L1: float = 5.0  # thigh length (cm)
    L2: float = 5.7  # shin length (cm)
    stand_height: float = 10.2  # nominal hip-to-foot distance while standing
    stand_offset_x: float = -0.75  # constant x bias applied to every foot setpoint
    step_clearance: float = 0.5  # how far the swing foot lifts
    step_length: float = 0.75  # forward foot travel either side of center
    step_velocity: float = 0.04  # seconds per IK substep (smaller = faster)
    substeps: int = 8  # IK samples per swing phase; cycle has 2*substeps frames


HIP_SEPARATION = 4.0  # purely visual: spread the two hips apart on screen
matplotlib.use("WebAgg")


def ik(x: float, z: float, L1: float, L2: float) -> tuple[float, float, float]:
    """Mirror of gait._ik (CCW positive, standing pose = (0, 0, 0)).

    Kept here so this file stands alone and so any future tweak to the IK
    can be tested visually before porting back.
    """
    d = math.sqrt(x**2 + z**2)
    if d < abs(L1 - L2) or d > L1 + L2:
        raise ValueError(f"unreachable: d={d:.3f}, L1={L1}, L2={L2}")
    theta_1 = math.acos((L2**2 + d**2 - L1**2) / (2 * L2 * d))
    theta_2 = math.acos((L1**2 + d**2 - L2**2) / (2 * L1 * d))
    theta_d = math.pi - theta_1 - theta_2
    theta_x = math.atan(x / z)
    theta_hip = theta_2 + theta_x
    theta_knee = theta_d - math.pi
    theta_ankle = -(theta_hip + theta_knee)
    return math.degrees(theta_hip), math.degrees(theta_knee), math.degrees(theta_ankle)


def knee_xy(
    hip: tuple[float, float],
    foot: tuple[float, float],
    L1: float,
    L2: float,
) -> tuple[float, float] | None:
    """Geometric knee placement: intersect two circles (hip, L1) and (foot, L2),
    pick the solution where the knee bends forward (human-like)."""
    hx, hy = hip
    fx, fy = foot
    dx, dy = fx - hx, fy - hy
    d = math.hypot(dx, dy)
    if d > L1 + L2 or d < abs(L1 - L2) or d == 0:
        return None
    a = (L1**2 - L2**2 + d**2) / (2 * d)
    h = math.sqrt(max(L1**2 - a**2, 0.0))
    ux, uy = dx / d, dy / d
    # Perpendicular such that the knee sits forward (+x) when the foot is
    # roughly below the hip; works because (-uy, ux) rotates u by +90°.
    px, py = -uy, ux
    return hx + a * ux + h * px, hy + a * uy + h * py


def render_gait_animation(p: Params, n_cycles: int = 2):
    """Build a self-contained animation for export. Returns (fig, anim, fps).

    fps = 1/step_velocity so playback runs at the same wall-clock speed as the
    robot would. The caller is responsible for saving and closing the figure.
    """
    frames = gait_frames(p)
    fps = max(1.0 / max(p.step_velocity, 1e-3), 1.0)

    fig, ax = plt.subplots(figsize=(7, 7))
    ax.set_aspect("equal")
    ax.set_xlim(-8, 8)
    ax.set_ylim(-14, 2)
    ax.set_title(
        f"step_length={p.step_length:.2f}  clearance={p.step_clearance:.2f}  "
        f"stand_height={p.stand_height:.2f}  stand_offset_x={p.stand_offset_x:+.2f}\n"
        f"step_velocity={p.step_velocity:.3f}s  substeps={int(p.substeps)}  "
        f"L1={p.L1:.2f}  L2={p.L2:.2f}",
        fontsize=9,
    )
    ax.grid(True, alpha=0.3)
    ax.axhline(0, color="0.6", lw=0.5)

    (hip_bar,) = ax.plot([], [], "k-", lw=2)
    (left_leg,) = ax.plot([], [], "o-", color="tab:blue", lw=2, ms=6)
    (right_leg,) = ax.plot([], [], "o-", color="tab:red", lw=2, ms=6)
    (left_trail,) = ax.plot([], [], color="tab:blue", lw=0.7, alpha=0.4)
    (right_trail,) = ax.plot([], [], color="tab:red", lw=0.7, alpha=0.4)
    trail_l: list[tuple[float, float]] = []
    trail_r: list[tuple[float, float]] = []

    def render(idx: int):
        xl, zl, xr, zr = frames[idx % len(frames)]
        hip_l = (-HIP_SEPARATION / 2, 0.0)
        hip_r = (HIP_SEPARATION / 2, 0.0)
        foot_l = (hip_l[0] + xl, -zl)
        foot_r = (hip_r[0] + xr, -zr)
        kl = knee_xy(hip_l, foot_l, p.L1, p.L2)
        kr = knee_xy(hip_r, foot_r, p.L1, p.L2)
        if kl is None or kr is None:
            return ()
        hip_bar.set_data([hip_l[0], hip_r[0]], [hip_l[1], hip_r[1]])
        left_leg.set_data([hip_l[0], kl[0], foot_l[0]], [hip_l[1], kl[1], foot_l[1]])
        right_leg.set_data([hip_r[0], kr[0], foot_r[0]], [hip_r[1], kr[1], foot_r[1]])
        trail_l.append(foot_l)
        trail_r.append(foot_r)
        left_trail.set_data(*zip(*trail_l))
        right_trail.set_data(*zip(*trail_r))
        return hip_bar, left_leg, right_leg, left_trail, right_trail

    anim = FuncAnimation(
        fig,
        render,
        frames=len(frames) * n_cycles,
        interval=int(1000 / fps),
        blit=False,
        repeat=False,
    )
    return fig, anim, fps


def gait_frames(p: Params):
    """One full cycle of (xl, zl, xr, zr) foot offsets, mirroring gait.take_step.

    Each phase uses a fixed number of substeps (so cycle duration is
    independent of step_length), and every x is biased by stand_offset_x to
    match the real `i + STAND_OFFSET_X` / `-i + STAND_OFFSET_X` setpoints.
    """
    L = p.step_length
    ox = p.stand_offset_x
    n = max(int(p.substeps), 2)
    frames = []
    # Phase 1: right plants and pushes back, left swings forward (lifted).
    for k in range(n + 1):
        i = L - 2 * L * k / n  # sweeps L → -L inclusive
        frames.append((-i + ox, p.stand_height - p.step_clearance, i + ox, p.stand_height))
    # Phase 2: swap.
    for k in range(n + 1):
        i = L - 2 * L * k / n
        frames.append((i + ox, p.stand_height, -i + ox, p.stand_height - p.step_clearance))
    return frames


def main() -> None:
    p = Params()

    fig, ax = plt.subplots(figsize=(7, 8))
    plt.subplots_adjust(left=0.1, right=0.95, top=0.95, bottom=0.45)

    ax.set_aspect("equal")
    ax.set_xlim(-8, 8)
    ax.set_ylim(-14, 2)  # y increases upward; hip at 0, ground roughly at -stand_height
    ax.set_title("Gait preview — left=blue, right=red")
    ax.grid(True, alpha=0.3)
    ax.axhline(0, color="0.6", lw=0.5)

    (hip_bar,) = ax.plot([], [], "k-", lw=2)
    (left_leg,) = ax.plot([], [], "o-", color="tab:blue", lw=2, ms=6)
    (right_leg,) = ax.plot([], [], "o-", color="tab:red", lw=2, ms=6)
    (left_trail,) = ax.plot([], [], color="tab:blue", lw=0.7, alpha=0.4)
    (right_trail,) = ax.plot([], [], color="tab:red", lw=0.7, alpha=0.4)
    info = ax.text(0.02, 0.97, "", transform=ax.transAxes, va="top", fontsize=9, family="monospace")

    state = {
        "frames": gait_frames(p),
        "phase": 0.0,  # current gait position in substeps (fractional)
        "last_t": time.perf_counter(),
        "fps_t": time.perf_counter(),
        "fps_n": 0,
        "fps": 0.0,
        "trail_l": [],
        "trail_r": [],
    }

    def rebuild() -> None:
        state["frames"] = gait_frames(p)
        state["phase"] = 0.0
        state["trail_l"].clear()
        state["trail_r"].clear()

    def step(_unused):
        if not state["frames"]:
            return ()

        # Advance the gait by however much wall-clock time has elapsed,
        # so the visualization runs at the same speed as the real robot
        # regardless of how slow the renderer is.
        now = time.perf_counter()
        dt = now - state["last_t"]
        state["last_t"] = now
        state["phase"] = (state["phase"] + dt / max(p.step_velocity, 1e-4)) % len(state["frames"])

        # Track actual render fps so we can flag when the visualizer is
        # too slow to faithfully represent step_velocity.
        state["fps_n"] += 1
        if now - state["fps_t"] >= 0.5:
            state["fps"] = state["fps_n"] / (now - state["fps_t"])
            state["fps_n"] = 0
            state["fps_t"] = now

        xl, zl, xr, zr = state["frames"][int(state["phase"])]

        # Hips fixed in screen frame; +x = forward, +y = up.
        hip_l = (-HIP_SEPARATION / 2, 0.0)
        hip_r = (HIP_SEPARATION / 2, 0.0)
        # gait.py treats z as downward distance from the hip, so flip its sign.
        foot_l = (hip_l[0] + xl, -zl)
        foot_r = (hip_r[0] + xr, -zr)

        kl = knee_xy(hip_l, foot_l, p.L1, p.L2)
        kr = knee_xy(hip_r, foot_r, p.L1, p.L2)
        unreachable = kl is None or kr is None
        if unreachable:
            info.set_text("⚠ pose unreachable for current L1/L2/stand_height/stand_offset_x")
            return hip_bar, left_leg, right_leg, left_trail, right_trail, info

        hip_bar.set_data([hip_l[0], hip_r[0]], [hip_l[1], hip_r[1]])
        left_leg.set_data([hip_l[0], kl[0], foot_l[0]], [hip_l[1], kl[1], foot_l[1]])
        right_leg.set_data([hip_r[0], kr[0], foot_r[0]], [hip_r[1], kr[1], foot_r[1]])

        state["trail_l"].append(foot_l)
        state["trail_r"].append(foot_r)
        # Cap trail length so it doesn't grow forever.
        for key in ("trail_l", "trail_r"):
            if len(state[key]) > 240:
                del state[key][:-240]
        left_trail.set_data(*zip(*state["trail_l"]))
        right_trail.set_data(*zip(*state["trail_r"]))

        # Theoretical gait timing (assuming the robot can hit step_velocity).
        # Each cycle has 2*(substeps+1) frames; body advances ~4*step_length
        # per cycle (each leg pushes the body 2*step_length once).
        cycle_s = len(state["frames"]) * p.step_velocity
        body_speed = 4 * p.step_length / cycle_s if cycle_s > 0 else 0.0  # cm/s
        warn = "  ⚠ render too slow" if state["fps"] and state["fps"] < 1 / p.step_velocity else ""
        try:
            hip_deg, knee_deg, ankle_deg = ik(xl, zl, p.L1, p.L2)
            info.set_text(
                f"hip {hip_deg:+6.1f}°  knee {knee_deg:+6.1f}°  ankle {ankle_deg:+6.1f}°\n"
                f"cycle {cycle_s*1000:5.0f} ms  speed {body_speed:5.2f} cm/s  "
                f"render {state['fps']:4.1f} fps{warn}"
            )
        except (ValueError, ZeroDivisionError):
            info.set_text("⚠ IK undefined for this pose")

        return hip_bar, left_leg, right_leg, left_trail, right_trail, info

    slider_specs = [
        ("step_length", 0.1, 4.0, None),
        ("step_clearance", 0.0, 4.0, None),
        ("stand_height", 7.0, 10.6, None),
        ("stand_offset_x", -3.0, 3.0, None),
        ("step_velocity", 0.005, 0.2, None),
        ("substeps", 2, 40, 1),
        ("L1", 3.0, 8.0, None),
        ("L2", 3.0, 8.0, None),
    ]
    sliders: dict[str, Slider] = {}
    for i, (name, lo, hi, valstep) in enumerate(slider_specs):
        ax_s = plt.axes((0.18, 0.40 - i * 0.042, 0.68, 0.025))
        sliders[name] = Slider(ax_s, name, lo, hi, valinit=getattr(p, name), valstep=valstep)

    def on_geometry_change(_val: float) -> None:
        for name, s in sliders.items():
            if name != "step_velocity":
                setattr(p, name, s.val)
        rebuild()

    for name, s in sliders.items():
        if name != "step_velocity":
            s.on_changed(on_geometry_change)

    # Render as fast as the backend can manage (~33 fps target). The gait
    # itself is paced by wall-clock time inside step(), so the rendered speed
    # tracks step_velocity even when WebAgg can't hit the target framerate.
    anim = FuncAnimation(fig, step, interval=30, blit=False, cache_frame_data=False)

    def on_velocity_change(val: float) -> None:
        p.step_velocity = val

    sliders["step_velocity"].on_changed(on_velocity_change)

    save_ax = plt.axes((0.18, 0.02, 0.68, 0.04))
    save_btn = Button(save_ax, "Save animation (mp4 if available, else gif)")

    def on_save(_event) -> None:
        snap = Params(**vars(p))
        info.set_text("rendering animation…")
        fig.canvas.draw_idle()
        # Force the GUI to flush so the user sees the message before save() blocks.
        try:
            fig.canvas.flush_events()
        except Exception:
            pass

        out_dir = Path(__file__).parent / ".." / ".." / "local"
        out_dir.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        save_fig, save_anim, fps = render_gait_animation(snap, n_cycles=2)
        try:
            if FFMpegWriter.isAvailable():
                path = out_dir / f"gait_{stamp}.mp4"
                save_anim.save(str(path), writer=FFMpegWriter(fps=fps, bitrate=2000))
            else:
                path = out_dir / f"gait_{stamp}.gif"
                save_anim.save(str(path), writer=PillowWriter(fps=fps))
        finally:
            plt.close(save_fig)

        info.set_text(f"saved {path}  ({fps:.1f} fps)")
        fig.canvas.draw_idle()

    save_btn.on_clicked(on_save)
    # Hold a reference so the button isn't GC'd.
    fig._save_btn = save_btn  # type: ignore[attr-defined]

    plt.show()


if __name__ == "__main__":
    main()
