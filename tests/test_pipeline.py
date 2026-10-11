import math
import json
from pathlib import Path

import pytest
import jsonschema

from harv.ast import Program
from harv.ir import TypedProgram
from harv.machine import run_json
from harv.pipeline import compile_source, execute_source
from harv.solver import SolverError


ROOT = Path(__file__).parents[1]
DECAY = (ROOT / "examples" / "decay.harv").read_text(encoding="utf-8")
POSITIVE_DECAY = (ROOT / "examples" / "positive_decay.harv").read_text(encoding="utf-8")


def test_parser_semantics_compile_to_typed_ir():
    program, typed = compile_source(DECAY)
    assert isinstance(program, Program)
    assert isinstance(typed, TypedProgram)
    assert typed.solver == "RK4"
    assert typed.time.steps == 500


def test_source_runs_through_ir_solver_to_analytic_decay():
    program, typed, rows = execute_source(DECAY)
    assert program.state.name == typed.name == "Decay"
    assert len(rows) == 501
    assert math.isclose(rows[-1]["x"], math.exp(-10), rel_tol=1e-6)


def test_positive_state_constraint_is_carried_and_satisfied():
    program, typed, rows = execute_source(POSITIVE_DECAY)
    assert len(program.constraints) == len(typed.constraints) == 1
    assert rows[0]["x"] > 0 and rows[-1]["x"] > 0
    commented = "# shift diagnostic line numbers\n" + POSITIVE_DECAY
    _, shifted_typed = compile_source(commented)
    from harv.ir import fingerprint
    assert fingerprint(typed) == fingerprint(shifted_typed)


def test_solver_stops_at_rk_stage_when_constraint_is_violated():
    violation = (ROOT / "tests" / "fixtures" / "constraint_violation.harv").read_text(encoding="utf-8")
    with pytest.raises(SolverError, match=r"constraint 1 .*incumplida .*t=0.5 s"):
        execute_source(violation)


def test_machine_json_constraints_use_the_same_solver_check():
    model = json.loads((ROOT / "examples" / "positive_decay.harv.json").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "schemas" / "harv-model-0.1.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(model, schema)
    assert all(row["x"] > 0 for row in run_json(json.dumps(model)))

    model["states"][0]["initial"] = {"value": 0.5, "unit": "m"}
    model["derivatives"][0]["expr"] = {"op": "constant", "value": -1, "unit": "m/s"}
    with pytest.raises(SolverError, match=r"constraint 1 incumplida en t=0.5 s"):
        run_json(json.dumps(model))


def test_example_cli_runs_and_reports_final_state(capsys):
    from harv.cli import main

    assert main(["run", str(ROOT / "examples")]) == 0
    output = capsys.readouterr().out
    assert "Simulation complete." in output
    assert '"x": 4.5399930377993055e-05' in output
    assert output.count("Simulation complete.") == len(list((ROOT / "examples").glob("*.harv")))
