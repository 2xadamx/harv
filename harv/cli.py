"""Command line interface for HARV."""
import argparse
import csv
import hashlib
import json
import sys
import platform
from dataclasses import asdict
from pathlib import Path

from .lexer import LexError
from .ir import dumps as dump_ir, fingerprint as ir_fingerprint, lower
from .machine import MachineModelError, load_document
from .parser import ParseError, parse
from .pipeline import execute_program
from .semantic import SemanticError, check
from .solver import SolverError
from .units import UnitError, unit_scale

VERSION = "0.1.0"


def main(argv=None):
    parser = argparse.ArgumentParser(prog="harvc", description="HARV scalar ODE prototype")
    parser.add_argument("--version", action="version", version=f"harvc {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("check", "run", "ast", "ir", "check-json", "run-json", "ast-json", "ir-json"):
        item = sub.add_parser(command)
        item.add_argument("file")
        if command in {"run", "run-json"}:
            item.add_argument("--csv", dest="csv_path")
            item.add_argument("--manifest", dest="manifest_path", help="write a reproducibility record as JSON")
    args = parser.parse_args(argv)
    try:
        input_path = Path(args.file)
        if args.command == "run" and input_path.is_dir():
            if args.csv_path or args.manifest_path:
                raise ValueError("--csv y --manifest requieren ejecutar un archivo, no una carpeta")
            examples = sorted(input_path.glob("*.harv"))
            if not examples:
                raise ValueError(f"no hay ejemplos .harv en {input_path}")
            for example in examples:
                print(f"=== {example.name} ===")
                status = main(["run", str(example)])
                if status:
                    return status
            return 0
        input_bytes = input_path.read_bytes()
        source = input_bytes.decode("utf-8-sig")
        if args.command.endswith("-json"):
            from .machine import _decode
            document = _decode(source)
            program = load_document(document)
        else:
            document = None
            program = parse(source)
        if args.command in {"check", "check-json"}:
            check(program)
            print("Parsing... OK\nSemantic analysis... OK\nUnits... OK\nStatus: PASS")
        elif args.command in {"ast", "ast-json"}:
            print(json.dumps(asdict(program), indent=2, ensure_ascii=False))
        elif args.command in {"ir", "ir-json"}:
            print(dump_ir(lower(program)), end="")
        else:
            # Both frontends converge on typed IR and the same numerical solver.
            typed_program, rows = execute_program(program)
            if document is not None:
                start = document["time"]["start"]
                offset = float(start["value"]) * unit_scale(start["unit"])
                if offset:
                    for row in rows:
                        row["t"] += offset
            csv_path = Path(args.csv_path) if args.csv_path else None
            manifest_path = Path(args.manifest_path) if args.manifest_path else None
            if csv_path and csv_path.resolve() == input_path.resolve():
                raise ValueError("el archivo CSV de salida no puede sobrescribir el modelo de entrada")
            if manifest_path and manifest_path.resolve() == input_path.resolve():
                raise ValueError("el manifiesto no puede sobrescribir el modelo de entrada")
            if csv_path and manifest_path and manifest_path.resolve() == csv_path.resolve():
                raise ValueError("CSV y manifiesto deben usar rutas distintas")
            if args.csv_path:
                with csv_path.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                    writer.writeheader(); writer.writerows(rows)
            method = next(a.expr.value for a in program.evolve.assignments if a.name == "method")
            if args.manifest_path:
                csv_hash = _sha256_file(csv_path) if csv_path else None
                manifest = _run_manifest(
                    program=program,
                    input_path=input_path,
                    input_bytes=input_bytes,
                    source_format="harv.model/0.1" if document is not None else "harv.source/0.1",
                    rows=rows,
                    csv_path=csv_path,
                    csv_hash=csv_hash,
                    solver=method,
                    typed_ir_sha256=ir_fingerprint(typed_program),
                )
                manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
                print(f"Run record: {manifest_path}")
            print(f"Compiling...\nUnits OK\nSolver: {method}\ndt: {rows[1]['t']-rows[0]['t'] if len(rows)>1 else 0:g}\nsteps: {len(rows)-1}\nRunning...\nSimulation complete.")
            print("Final state:")
            print(json.dumps(rows[-1], indent=2, ensure_ascii=False))
        return 0
    except (OSError, LexError, ParseError, SemanticError, SolverError, UnitError,
            MachineModelError, ValueError, ArithmeticError) as exc:
        print(f"harvc: error: {exc}", file=sys.stderr)
        return 1


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_manifest(*, program, input_path, input_bytes, source_format, rows, csv_path, csv_hash, solver,
                  typed_ir_sha256):
    first_time, final_time = rows[0]["t"], rows[-1]["t"]
    step_seconds = rows[1]["t"] - first_time if len(rows) > 1 else 0.0
    return {
        "record_format": "harv.run-record/0.1",
        "input": {
            "file": input_path.name,
            "format": source_format,
            "sha256": hashlib.sha256(input_bytes).hexdigest(),
        },
        "model": {"name": program.state.name},
        "typed_ir_sha256": typed_ir_sha256,
        "execution": {
            "harv_version": VERSION,
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
            "solver": solver,
            "time_unit": "s",
            "start": first_time,
            "step": step_seconds,
            "duration": final_time - first_time,
            "steps": len(rows) - 1,
            "observations": [name for name in rows[0] if name != "t"],
        },
        "output": {
            "csv_file": csv_path.name if csv_path else None,
            "csv_sha256": csv_hash,
        },
    }


if __name__ == "__main__":
    raise SystemExit(main())
