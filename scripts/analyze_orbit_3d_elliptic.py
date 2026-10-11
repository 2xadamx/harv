"""Audit an inclined elliptic HARV trajectory against Kepler's equation."""
import csv
import math
import sys
from pathlib import Path


def dot(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    return sum(x * y for x, y in zip(a, b))


def cross(a: tuple[float, ...], b: tuple[float, ...]) -> tuple[float, float, float]:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def solve_kepler(mean_anomaly: float, eccentricity: float) -> float:
    """Solve E - e sin(E) = M for the moderate eccentricity in this example."""
    eccentric_anomaly = mean_anomaly
    for _ in range(32):
        correction = (eccentric_anomaly - eccentricity * math.sin(eccentric_anomaly) - mean_anomaly) / (
            1 - eccentricity * math.cos(eccentric_anomaly)
        )
        eccentric_anomaly -= correction
        if abs(correction) < 1e-14:
            return eccentric_anomaly
    raise ArithmeticError("Kepler equation did not converge")


def analyze(source: Path) -> dict[str, float]:
    with source.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) < 2:
        raise ValueError("elliptic orbit trajectory needs at least two samples")

    first = rows[0]
    r0 = tuple(float(first[key]) for key in ("x", "y", "z"))
    v0 = tuple(float(first[key]) for key in ("vx", "vy", "vz"))
    mu = float(first["mu"])
    radius0 = math.sqrt(dot(r0, r0))
    speed0 = math.sqrt(dot(v0, v0))
    energy0 = 0.5 * speed0**2 - mu / radius0
    if energy0 >= 0:
        raise ValueError("analytic ellipse audit requires a bound orbit (negative specific energy)")
    semi_major_axis = -mu / (2 * energy0)
    h0 = cross(r0, v0)
    h0_norm = math.sqrt(dot(h0, h0))
    eccentricity = math.sqrt(max(0.0, 1 - h0_norm**2 / (mu * semi_major_axis)))
    if not 0 <= eccentricity < 1:
        raise ValueError("analytic ellipse audit requires eccentricity in [0, 1)")

    p_hat = tuple(value / radius0 for value in r0)
    q_hat = tuple(value / speed0 for value in v0)
    mean_motion = math.sqrt(mu / semi_major_axis**3)
    minor_scale = semi_major_axis * math.sqrt(1 - eccentricity**2)
    speed_scale = math.sqrt(mu / semi_major_axis)
    max_position_error = max_velocity_error = 0.0
    max_energy_drift = max_angular_momentum_drift = 0.0

    for row in rows:
        mean_anomaly = mean_motion * float(row["t"])
        eccentric_anomaly = solve_kepler(mean_anomaly, eccentricity)
        cosine, sine = math.cos(eccentric_anomaly), math.sin(eccentric_anomaly)
        denominator = 1 - eccentricity * cosine
        expected_r = tuple(
            semi_major_axis * (cosine - eccentricity) * p_hat[i]
            + minor_scale * sine * q_hat[i]
            for i in range(3)
        )
        expected_v = tuple(
            -semi_major_axis * mean_motion * sine / denominator * p_hat[i]
            + minor_scale * mean_motion * cosine / denominator * q_hat[i]
            for i in range(3)
        )
        actual_r = tuple(float(row[key]) for key in ("x", "y", "z"))
        actual_v = tuple(float(row[key]) for key in ("vx", "vy", "vz"))
        position_error = math.sqrt(sum((actual_r[i] - expected_r[i])**2 for i in range(3))) / semi_major_axis
        velocity_error = math.sqrt(sum((actual_v[i] - expected_v[i])**2 for i in range(3))) / speed_scale
        max_position_error = max(max_position_error, position_error)
        max_velocity_error = max(max_velocity_error, velocity_error)

        radius = math.sqrt(dot(actual_r, actual_r))
        energy = 0.5 * dot(actual_v, actual_v) - mu / radius
        h = cross(actual_r, actual_v)
        h_norm = math.sqrt(dot(h, h))
        max_energy_drift = max(max_energy_drift, abs((energy - energy0) / energy0))
        max_angular_momentum_drift = max(max_angular_momentum_drift, abs((h_norm - h0_norm) / h0_norm))

    return {
        "eccentricity": eccentricity,
        "analytic_period_s": 2 * math.pi / mean_motion,
        "simulated_time_s": float(rows[-1]["t"]),
        "steps": float(len(rows) - 1),
        "max_position_error_fraction_of_semimajor_axis": max_position_error,
        "max_velocity_error_fraction_of_characteristic_speed": max_velocity_error,
        "max_relative_specific_energy_drift": max_energy_drift,
        "max_relative_angular_momentum_magnitude_drift": max_angular_momentum_drift,
    }


if __name__ == "__main__":
    trajectory = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("outputs/orbit_3d_elliptic_trajectory.csv")
    print(f"Inclined 3D elliptic Kepler audit for {trajectory}:")
    for key, value in analyze(trajectory).items():
        print(f"  {key}: {int(value) if key == 'steps' else f'{value:.8e}'}")
