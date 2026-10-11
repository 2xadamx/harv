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
