import math
from pathlib import Path

import pytest

from harv.parser import parse
from harv.pipeline import execute_source
from harv.semantic import SemanticError, check


ROOT = Path(__file__).parents[1]


def read_example(name: str) -> str:
    return (ROOT / "examples" / name).read_text(encoding="utf-8")


def test_rain_model_has_consistent_units_positive_constraints_and_expected_solution():
    source = read_example("rain.harv")
    check(parse(source))
    _, _, rows = execute_source(source)

    rain0 = 5.5555555556e-6
    decay = 5.5555555556e-4
    soil0 = 0.04
    infiltration = 0.7
    drainage = 2.7777777778e-4
    final_time = 7200.0

    assert len(rows) == 721
    assert all(row["rain_rate"] > 0 for row in rows)
    assert all(row["soil_water"] > 0 and row["runoff_depth"] >= 0 for row in rows)
    assert all(a["rain_rate"] > b["rain_rate"] for a, b in zip(rows, rows[1:]))
    assert all(a["runoff_depth"] <= b["runoff_depth"] for a, b in zip(rows, rows[1:]))

    exp_decay = math.exp(-decay * final_time)
    exp_drain = math.exp(-drainage * final_time)
    expected_rain = rain0 * exp_decay
    expected_runoff = (1 - infiltration) * rain0 / decay * (1 - exp_decay)
    expected_soil = soil0 * exp_drain + infiltration * rain0 * (exp_decay - exp_drain) / (drainage - decay)
    assert rows[-1]["rain_rate"] == pytest.approx(expected_rain, rel=1e-10)
    assert rows[-1]["soil_water"] == pytest.approx(expected_soil, rel=1e-10)
    assert rows[-1]["runoff_depth"] == pytest.approx(expected_runoff, rel=1e-10)


def test_orbit_model_rejects_dimensionally_wrong_gravity_expression():
    source = read_example("orbit.harv")
    invalid = source.replace(
        "dvx_dt = -mu*x / (x*x + y*y)^1.5",
        "dvx_dt = -mu*x / (x*x + y*y)",
    )
    with pytest.raises(SemanticError, match="se esperaba"):
        check(parse(invalid))


def test_orbit_matches_kepler_and_conserves_newtonian_invariants():
    source = read_example("orbit.harv")
    check(parse(source))
    _, _, rows = execute_source(source)
    mu = rows[0]["mu"]
    radius0 = math.hypot(rows[0]["x"], rows[0]["y"])
    speed0 = math.hypot(rows[0]["vx"], rows[0]["vy"])
    mean_motion = math.sqrt(mu / radius0**3)
    initial_energy = 0.5 * speed0**2 - mu / radius0
    initial_angular_momentum = rows[0]["x"] * rows[0]["vy"] - rows[0]["y"] * rows[0]["vx"]

    assert len(rows) == 2915
    assert 2 * math.pi / mean_motion == pytest.approx(5828.516637686, rel=1e-12)
    for row in rows:
        phase = mean_motion * row["t"]
        expected_x = radius0 * math.cos(phase)
        expected_y = radius0 * math.sin(phase)
        position_error = math.hypot(row["x"] - expected_x, row["y"] - expected_y) / radius0
        assert position_error < 1e-10

        radius = math.hypot(row["x"], row["y"])
        speed = math.hypot(row["vx"], row["vy"])
        energy = 0.5 * speed**2 - mu / radius
        angular_momentum = row["x"] * row["vy"] - row["y"] * row["vx"]
        assert abs((energy - initial_energy) / initial_energy) < 1e-11
        assert abs((angular_momentum - initial_angular_momentum) / initial_angular_momentum) < 1e-11


def test_3d_orbit_matches_inclined_kepler_solution_and_conserves_invariants():
    source = read_example("orbit_3d.harv")
    check(parse(source))
    _, _, rows = execute_source(source)
    initial = rows[0]
    r0 = (initial["x"], initial["y"], initial["z"])
    v0 = (initial["vx"], initial["vy"], initial["vz"])
    mu = initial["mu"]
    radius0 = math.sqrt(sum(value * value for value in r0))
    speed0 = math.sqrt(sum(value * value for value in v0))
    mean_motion = math.sqrt(mu / radius0**3)
    energy0 = 0.5 * speed0**2 - mu / radius0
    h0 = (r0[1] * v0[2] - r0[2] * v0[1],
          r0[2] * v0[0] - r0[0] * v0[2],
          r0[0] * v0[1] - r0[1] * v0[0])
    h0_norm = math.sqrt(sum(value * value for value in h0))

    assert len(rows) == 2915
    for row in rows:
        phase = mean_motion * row["t"]
        cosine, sine = math.cos(phase), math.sin(phase)
        expected_r = tuple(r0[i] * cosine + v0[i] / mean_motion * sine for i in range(3))
        expected_v = tuple(v0[i] * cosine - r0[i] * mean_motion * sine for i in range(3))
        actual_r = tuple(row[key] for key in ("x", "y", "z"))
        actual_v = tuple(row[key] for key in ("vx", "vy", "vz"))
        position_error = math.sqrt(sum((actual_r[i] - expected_r[i])**2 for i in range(3))) / radius0
        velocity_error = math.sqrt(sum((actual_v[i] - expected_v[i])**2 for i in range(3))) / speed0
        assert position_error < 1e-10
        assert velocity_error < 1e-10

        radius = math.sqrt(sum(value * value for value in actual_r))
        speed_squared = sum(value * value for value in actual_v)
        energy = 0.5 * speed_squared - mu / radius
        h = (actual_r[1] * actual_v[2] - actual_r[2] * actual_v[1],
             actual_r[2] * actual_v[0] - actual_r[0] * actual_v[2],
             actual_r[0] * actual_v[1] - actual_r[1] * actual_v[0])
        h_norm = math.sqrt(sum(value * value for value in h))
        assert abs((energy - energy0) / energy0) < 1e-11
        assert abs((h_norm - h0_norm) / h0_norm) < 1e-11
        assert abs(radius - radius0) / radius0 < 1e-10


def test_3d_orbit_rk4_error_decreases_at_fourth_order_when_step_is_halved():
    source = read_example("orbit_3d.harv").replace("duration = 5828<s>", "duration = 5824<s>")
    errors = []
    for dt in (8, 4, 2):
        model = source.replace("dt = 2<s>", f"dt = {dt}<s>")
        _, _, rows = execute_source(model)
        initial = rows[0]
        r0 = tuple(initial[key] for key in ("x", "y", "z"))
        v0 = tuple(initial[key] for key in ("vx", "vy", "vz"))
        mu = initial["mu"]
        radius0 = math.sqrt(sum(value * value for value in r0))
        mean_motion = math.sqrt(mu / radius0**3)
        max_error = 0.0
        for row in rows:
            phase = mean_motion * row["t"]
            expected = tuple(r0[i] * math.cos(phase) + v0[i] / mean_motion * math.sin(phase) for i in range(3))
            actual = tuple(row[key] for key in ("x", "y", "z"))
            max_error = max(max_error, math.sqrt(sum((actual[i] - expected[i])**2 for i in range(3))) / radius0)
        errors.append(max_error)

    # Classical RK4's global error scales as dt^4 while truncation dominates.
    assert 14.0 < errors[0] / errors[1] < 18.0
    assert 14.0 < errors[1] / errors[2] < 18.0


def test_3d_orbit_matches_analytic_solution_at_a_different_radius():
    source = read_example("orbit_3d.harv").replace("7.0e6<m>", "8.0e6<m>")
    speed_component = math.sqrt(3.986004418e14 / 8.0e6) / math.sqrt(2)
    source = source.replace("5335.865452630101<m/s>", f"{speed_component:.15f}<m/s>")
    _, _, rows = execute_source(source)
    initial = rows[0]
    r0 = tuple(initial[key] for key in ("x", "y", "z"))
    v0 = tuple(initial[key] for key in ("vx", "vy", "vz"))
    radius0 = math.sqrt(sum(value * value for value in r0))
    mean_motion = math.sqrt(initial["mu"] / radius0**3)

    for row in rows:
        phase = mean_motion * row["t"]
        expected = tuple(r0[i] * math.cos(phase) + v0[i] / mean_motion * math.sin(phase) for i in range(3))
        actual = tuple(row[key] for key in ("x", "y", "z"))
        error = math.sqrt(sum((actual[i] - expected[i])**2 for i in range(3))) / radius0
        assert error < 1e-10
