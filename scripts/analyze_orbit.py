"""Compare HARV's circular two-body trajectory with Kepler's analytic orbit."""
import csv
import math
import sys
from pathlib import Path


def analyze(source: Path) -> dict[str, float]:
    with source.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) < 2:
        raise ValueError("orbit trajectory needs at least two samples")
    mu = float(rows[0]["mu"])
    x0, y0 = float(rows[0]["x"]), float(rows[0]["y"])
    vx0, vy0 = float(rows[0]["vx"]), float(rows[0]["vy"])
    radius0 = math.hypot(x0, y0)
    speed0 = math.hypot(vx0, vy0)
    energy0 = 0.5 * speed0**2 - mu / radius0
    angular_momentum0 = x0 * vy0 - y0 * vx0
    mean_motion = math.sqrt(mu / radius0**3)

    max_energy_drift = 0.0
    max_angular_momentum_drift = 0.0
    max_radius_drift = 0.0
    for row in rows:
        x, y = float(row["x"]), float(row["y"])
        vx, vy = float(row["vx"]), float(row["vy"])
        radius = math.hypot(x, y)
        speed = math.hypot(vx, vy)
        energy = 0.5 * speed**2 - mu / radius
        angular_momentum = x * vy - y * vx
        max_energy_drift = max(max_energy_drift, abs((energy - energy0) / energy0))
        max_angular_momentum_drift = max(
            max_angular_momentum_drift,
            abs((angular_momentum - angular_momentum0) / angular_momentum0),
        )
        max_radius_drift = max(max_radius_drift, abs(radius - radius0) / radius0)

    final = rows[-1]
    time = float(final["t"])
    phase = mean_motion * time
    expected = (
        radius0 * math.cos(phase),
        radius0 * math.sin(phase),
        -radius0 * mean_motion * math.sin(phase),
        radius0 * mean_motion * math.cos(phase),
    )
    actual = tuple(float(final[key]) for key in ("x", "y", "vx", "vy"))
    position_error = math.hypot(actual[0] - expected[0], actual[1] - expected[1]) / radius0
    velocity_error = math.hypot(actual[2] - expected[2], actual[3] - expected[3]) / speed0
    return {
        "analytic_period_s": 2 * math.pi / mean_motion,
        "simulated_time_s": time,
        "steps": float(len(rows) - 1),
        "final_position_error_fraction_of_radius": position_error,
        "final_velocity_error_fraction_of_initial_speed": velocity_error,
        "max_relative_specific_energy_drift": max_energy_drift,
        "max_relative_angular_momentum_drift": max_angular_momentum_drift,
        "max_relative_radius_drift": max_radius_drift,
    }


if __name__ == "__main__":
    trajectory = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("outputs/orbit_trajectory.csv")
    results = analyze(trajectory)
    print(f"Keplerian orbit check for {trajectory}:")
    for key, value in results.items():
        if key == "steps":
            print(f"  {key}: {int(value)}")
        else:
            print(f"  {key}: {value:.8e}")
