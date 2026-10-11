"""Compare HARV's inclined 3D circular orbit with its analytic solution."""
import csv
import math
import sys
from pathlib import Path


def analyze(source: Path) -> dict[str, float]:
    with source.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) < 2:
        raise ValueError("3D orbit trajectory needs at least two samples")

    axes, velocity_axes = ("x", "y", "z"), ("vx", "vy", "vz")
    initial = rows[0]
    r0 = tuple(float(initial[key]) for key in axes)
    v0 = tuple(float(initial[key]) for key in velocity_axes)
    mu = float(initial["mu"])
    radius0 = math.sqrt(sum(value * value for value in r0))
    speed0 = math.sqrt(sum(value * value for value in v0))
    mean_motion = math.sqrt(mu / radius0**3)
    energy0 = 0.5 * speed0**2 - mu / radius0
    h0 = (r0[1] * v0[2] - r0[2] * v0[1], r0[2] * v0[0] - r0[0] * v0[2], r0[0] * v0[1] - r0[1] * v0[0])
    h0_norm = math.sqrt(sum(value * value for value in h0))
    maxima = {"position": 0.0, "velocity": 0.0, "energy": 0.0, "angular_momentum": 0.0, "radius": 0.0}

    for row in rows:
        phase = mean_motion * float(row["t"])
        cosine, sine = math.cos(phase), math.sin(phase)
        actual_r = tuple(float(row[key]) for key in axes)
        actual_v = tuple(float(row[key]) for key in velocity_axes)
        expected_r = tuple(r0[i] * cosine + v0[i] / mean_motion * sine for i in range(3))
        expected_v = tuple(v0[i] * cosine - r0[i] * mean_motion * sine for i in range(3))
        maxima["position"] = max(maxima["position"], math.sqrt(sum((actual_r[i] - expected_r[i])**2 for i in range(3))) / radius0)
        maxima["velocity"] = max(maxima["velocity"], math.sqrt(sum((actual_v[i] - expected_v[i])**2 for i in range(3))) / speed0)
        radius = math.sqrt(sum(value * value for value in actual_r))
        energy = 0.5 * sum(value * value for value in actual_v) - mu / radius
        h = (actual_r[1] * actual_v[2] - actual_r[2] * actual_v[1], actual_r[2] * actual_v[0] - actual_r[0] * actual_v[2], actual_r[0] * actual_v[1] - actual_r[1] * actual_v[0])
        h_norm = math.sqrt(sum(value * value for value in h))
        maxima["energy"] = max(maxima["energy"], abs((energy - energy0) / energy0))
        maxima["angular_momentum"] = max(maxima["angular_momentum"], abs((h_norm - h0_norm) / h0_norm))
        maxima["radius"] = max(maxima["radius"], abs(radius - radius0) / radius0)

    return {
        "analytic_period_s": 2 * math.pi / mean_motion,
        "simulated_time_s": float(rows[-1]["t"]),
        "steps": float(len(rows) - 1),
        "max_position_error_fraction_of_radius": maxima["position"],
        "max_velocity_error_fraction_of_initial_speed": maxima["velocity"],
        "max_relative_specific_energy_drift": maxima["energy"],
        "max_relative_angular_momentum_magnitude_drift": maxima["angular_momentum"],
        "max_relative_radius_drift": maxima["radius"],
    }


if __name__ == "__main__":
    trajectory = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("outputs/orbit_3d_trajectory.csv")
    print(f"Inclined 3D Kepler orbit check for {trajectory}:")
    for key, value in analyze(trajectory).items():
        print(f"  {key}: {int(value) if key == 'steps' else f'{value:.8e}'}")
