import math
import hashlib
import json
from pathlib import Path

import pytest

from harv.cli import main
from harv.lexer import lex
from harv.ir import dumps as dump_ir, fingerprint as ir_fingerprint, lower, to_document
from harv.machine import MachineModelError, loads, run_json
from harv.parser import ParseError, parse
from harv.semantic import SemanticError, check
from harv.solver import run, run_ir
from harv.units import parse_unit, same, unit_scale


ROOT = Path(__file__).parents[1]


def read_example(name):
    return (ROOT / "examples" / name).read_text(encoding="utf-8")


def test_lexer_tracks_source_location_and_scientific_numbers():
    tokens = lex("state S {\n x: scalar # comment\n y = 1e-5 // another\n}")
    assert tokens[0].value == "state" and (tokens[0].line, tokens[0].column) == (1, 1)
    number = next(token for token in tokens if token.value == "1e-5")
    assert number.kind == "NUMBER" and (number.line, number.column) == (3, 6)


def test_parser_builds_ast_with_unary_expression_precedence():
    program = parse(read_example("decay.harv"))
    expr = program.operator.assignments[0].expr
    assert expr.kind == "binary" and expr.value == "*"
    assert expr.children[0].kind == "unary" and expr.children[0].value == "-"
    assert expr.children[1].kind == "name" and expr.children[1].value == "x"


def test_parser_reports_line_and_column():
    with pytest.raises(ParseError, match=r"línea 2, columna"):
        parse("state S {\n x scalar\n}")


def test_units_parse_compositions():
    assert same(parse_unit("m/s^2"), {"m": 1, "s": -2})
    assert same(parse_unit("1/s"), {"s": -1})
    assert same(parse_unit("kg/m^3"), {"kg": 1, "m": -3})
    assert same(parse_unit("Pa"), parse_unit("kg/m/s^2"))
    assert same(parse_unit("USD/year"), {"USD": 1, "s": -1})
    assert same(parse_unit("rad/s"), {"s": -1})
    assert unit_scale("deg") == pytest.approx(math.pi / 180)


def test_economic_ode_with_consistent_dimensions_is_accepted():
    source = """state Economy {
 GDP: scalar<USD>
 inflation: scalar<1/year>
 demand: scalar<USD/year>
 money_supply: scalar<USD>
 money_growth: scalar<1/year>
 sensitivity: scalar<1/year>
}
init Economy {
 GDP = 1e12<USD>
 inflation = 0.02<1/year>
 demand = 0.9e12<USD/year>
 money_supply = 2e12<USD>
 money_growth = 0.05<1/year>
 sensitivity = 0.1<1/year>
}
operator Market {
 dGDP_dt = demand - inflation*GDP
 dinflation_dt = sensitivity*(money_growth-inflation)
 ddemand_dt = 0<USD/year^2>
 dmoney_supply_dt = money_growth*money_supply
 dmoney_growth_dt = 0<1/year^2>
 dsensitivity_dt = 0<1/year^2>
}
evolve Economy using Market {
 dt = 0.25<year>
 duration = 40<year>
 method = RK4
}
observe GDP
"""
    program = check(parse(source))
    rows = run(program)
    assert len(rows) == 161
    assert rows[-1]["t"] == pytest.approx(40 * 365.25 * 24 * 60 * 60)


def test_economic_unit_checker_rejects_stock_plus_rate():
    source = """state Economy {
 GDP: scalar<USD>
 demand: scalar<USD/year>
}
init Economy { GDP = 1<USD> demand = 1<USD/year> }
operator Market {
 dGDP_dt = GDP + demand
 ddemand_dt = 0<USD/year^2>
}
evolve Economy using Market { dt = 0.25<year> duration = 1<year> method = RK4 }
"""
    with pytest.raises(SemanticError, match="sumar/restar unidades"):
        check(parse(source))


def test_sir_example_conserves_population_and_has_an_epidemic_peak():
    rows = run(parse(read_example("sir.harv")))
    assert len(rows) == 4001
    totals = [row["S"] + row["I"] + row["R"] for row in rows]
    assert all(total == pytest.approx(1.0, abs=2e-12) for total in totals)
    assert max(row["I"] for row in rows) > rows[0]["I"]
    assert rows[-1]["I"] < rows[0]["I"]


def test_decay_units_and_rk4_match_analytic_solution():
    program = check(parse(read_example("decay.harv")))
    rows = run(program)
    assert len(rows) == 501
    assert rows[-1]["t"] == 5
    assert rows[-1]["x"] == pytest.approx(math.exp(-10), abs=2e-10)


def test_typed_ir_normalizes_units_and_solver_executes_ir():
    program = parse(read_example("decay.harv"))
    typed = lower(program)
    assert typed.fields[0].name == "x"
    assert typed.fields[0].dimension == (("m", 1, 1),)
    assert typed.fields[0].initial_si == 1.0
    assert typed.time.step_seconds == 0.01
    assert typed.time.steps == 500
    assert run_ir(typed) == run(program)


def test_typed_ir_json_matches_published_schema_and_fingerprint_is_canonical():
    import json
    import jsonschema
    program = parse(read_example("decay.harv"))
    typed = lower(program)
    schema = json.loads((ROOT / "schemas" / "harv-typed-ir-0.1.schema.json").read_text(encoding="utf-8"))
    document = to_document(typed)
    jsonschema.validate(document, schema)
    assert json.loads(dump_ir(typed)) == document
    commented = parse("# same model\n" + read_example("decay.harv"))
    assert ir_fingerprint(lower(commented)) == ir_fingerprint(typed)


def test_cli_emits_versioned_typed_ir_json(capsys):
    import json
    import jsonschema
    assert main(["ir", str(ROOT / "examples" / "decay.harv")]) == 0
    document = json.loads(capsys.readouterr().out)
    schema = json.loads((ROOT / "schemas" / "harv-typed-ir-0.1.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(document, schema)


def test_cli_lowers_machine_json_to_same_typed_ir(capsys):
    import json
    assert main(["ir-json", str(ROOT / "examples" / "decay.harv.json")]) == 0
    from_machine = json.loads(capsys.readouterr().out)
    matching_name_source = read_example("decay.harv").replace("Decay", "exponential_decay")
    from_source = json.loads(dump_ir(lower(parse(matching_name_source))))
    assert from_machine == from_source


def test_typed_ir_rejects_nonfinite_initial_values_and_oversized_runs():
    nonfinite = read_example("decay.harv").replace("x = 1.0<m>", "x = 1e309<m>")
    with pytest.raises(ValueError, match="no finito"):
        lower(parse(nonfinite))
    oversized = read_example("decay.harv").replace("duration = 5<s>", "duration = 10001<s>")
    with pytest.raises(ValueError, match="límite"):
        lower(parse(oversized))


def test_bad_dimensions_are_rejected():
    source = read_example("decay.harv").replace("k: scalar<1/s>", "k: scalar<kg>").replace("k = 2.0<1/s>", "k = 2.0<kg>")
    with pytest.raises(SemanticError, match="tiene unidad"):
        check(parse(source))


def test_euler_solver_runs():
    source = read_example("decay.harv").replace("method = RK4", "method = Euler").replace("duration = 5<s>", "duration = 0.1<s>")
    rows = run(parse(source))
    assert len(rows) == 11
    assert rows[-1]["x"] == pytest.approx((1 - 0.02) ** 10)


def test_time_dependent_forcing_runs_and_is_reproducible():
    program = parse(read_example("forced.harv"))
    a, b = run(program), run(program)
    assert a == b
    assert math.isfinite(a[-1]["x"])


def test_logistic_and_pendulum_examples_pass_semantics():
    check(parse(read_example("logistic.harv")))
    check(parse(read_example("pendulum.harv")))


def test_pendulum_uses_first_order_state_and_explicit_rest_initial_condition():
    program = parse(read_example("pendulum.harv"))
    rows = run(program)
    assert rows[0]["theta"] == pytest.approx(0.2)
    assert rows[0]["omega"] == 0
    assert rows[1]["omega"] < 0  # restoring acceleration for positive theta


def test_cli_check(capsys):
    assert main(["check", str(ROOT / "examples" / "decay.harv")]) == 0
    assert "Status: PASS" in capsys.readouterr().out


def test_machine_json_and_harv_source_produce_identical_decay_trajectory():
    machine = (ROOT / "examples" / "decay.harv.json").read_text(encoding="utf-8")
    source = read_example("decay.harv")
    assert run_json(machine) == run(parse(source))


def test_machine_json_rejects_dimensionally_invalid_equation():
    import json
    machine = json.loads((ROOT / "examples" / "decay.harv.json").read_text(encoding="utf-8"))
    machine["derivatives"][0]["expr"] = {
        "op": "add",
        "left": {"op": "state", "name": "x"},
        "right": {"op": "parameter", "name": "k"},
    }
    with pytest.raises(MachineModelError, match="unidades"):
        loads(json.dumps(machine))


def test_machine_json_distinguishes_state_and_parameter_references():
    import json
    machine = json.loads((ROOT / "examples" / "decay.harv.json").read_text(encoding="utf-8"))
    machine["derivatives"][0]["expr"]["left"]["arg"]["op"] = "state"
    with pytest.raises(MachineModelError, match="state no declarado 'k'"):
        loads(json.dumps(machine))


def test_machine_json_rejects_nonintegral_or_excessive_step_counts():
    import json
    machine = json.loads((ROOT / "examples" / "decay.harv.json").read_text(encoding="utf-8"))
    machine["time"]["duration"]["value"] = 5.001
    with pytest.raises(MachineModelError, match="múltiplo entero"):
        loads(json.dumps(machine))
    machine["time"]["duration"]["value"] = 50001
    with pytest.raises(MachineModelError, match="límite"):
        loads(json.dumps(machine))


def test_machine_json_honors_nonzero_time_origin():
    import json
    machine = json.loads((ROOT / "examples" / "decay.harv.json").read_text(encoding="utf-8"))
    machine["parameters"][0]["value"] = 0
    machine["derivatives"][0]["expr"] = {
        "op": "mul",
        "left": {"op": "constant", "value": 1, "unit": "m/s^2"},
        "right": {"op": "time"},
    }
    machine["time"] = {
        "start": {"value": 2, "unit": "s"},
        "duration": {"value": 1, "unit": "s"},
        "step": {"value": 0.5, "unit": "s"},
    }
    rows = run_json(json.dumps(machine))
    assert rows[0]["t"] == 2
    assert rows[-1]["t"] == 3
    assert rows[-1]["x"] == pytest.approx(3.5)


def test_machine_json_cli_check(capsys):
    assert main(["check-json", str(ROOT / "examples" / "decay.harv.json")]) == 0
    assert "Status: PASS" in capsys.readouterr().out


def test_cli_run_writes_reproducibility_manifest_and_csv_hash(tmp_path, capsys):
    import jsonschema
    source = ROOT / "examples" / "decay.harv"
    csv_path = tmp_path / "decay.csv"
    manifest_path = tmp_path / "run.json"
    assert main(["run", str(source), "--csv", str(csv_path), "--manifest", str(manifest_path)]) == 0
    record = json.loads(manifest_path.read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "schemas" / "harv-run-record-0.1.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(record, schema)
    assert record["record_format"] == "harv.run-record/0.1"
    assert record["input"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert record["execution"]["solver"] == "RK4"
    assert record["execution"]["steps"] == 500
    assert record["typed_ir_sha256"] == ir_fingerprint(lower(parse(source.read_text(encoding="utf-8"))))
    assert record["output"]["csv_sha256"] == hashlib.sha256(csv_path.read_bytes()).hexdigest()
    assert "Run record:" in capsys.readouterr().out


def test_cli_prevents_manifest_from_overwriting_input(capsys):
    source = ROOT / "examples" / "decay.harv"
    original = source.read_bytes()
    assert main(["run", str(source), "--manifest", str(source)]) == 1
    assert source.read_bytes() == original
    assert "no puede sobrescribir" in capsys.readouterr().err
