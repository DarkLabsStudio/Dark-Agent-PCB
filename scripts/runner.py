#!/usr/bin/env python3
"""Validate a KiCad PCB project and regenerate its fabrication artifacts.

The runner is intentionally dependency-free. It locates KiCad 10's
``kicad-cli``, runs ERC/DRC, exports a netlist, BOM, Gerbers, drill files,
position data, and 3D previews, then checks the checked-in artifacts.

Run from the repository root:
    python scripts/runner.py examples/led_indicator
    python scripts/runner.py examples/led_indicator --refresh
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
MIN_MAJOR = 10


def find_kicad_cli() -> Path | None:
    override = os.environ.get("KICAD_CLI")
    if override:
        path = Path(override)
        if path.is_file():
            return path

    candidates: list[Path] = []
    if os.name == "nt":
        for root in [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "KiCad",
            Path(os.environ.get("ProgramFiles", "")) / "KiCad",
            Path(os.environ.get("ProgramFiles(x86)", "")) / "KiCad",
        ]:
            if root.is_dir():
                candidates.extend(root.glob("*/bin/kicad-cli.exe"))
    else:
        candidates.extend(
            [
                Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"),
                Path("/usr/bin/kicad-cli"),
                Path("/usr/local/bin/kicad-cli"),
            ]
        )

    which = shutil.which("kicad-cli")
    if which:
        candidates.insert(0, Path(which))

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def run(
    command: list[str],
    log: list[str],
    *,
    verbose: bool = False,
    cwd: Path | None = None,
    timeout: float = 180.0,
) -> subprocess.CompletedProcess[str]:
    log.append("\n$ " + " ".join(str(part) for part in command))
    try:
        result = subprocess.run(
            [str(part) for part in command],
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        stderr += f"\nTimed out after {timeout:.0f} s"
        log.append(stdout)
        log.append(stderr)
        return subprocess.CompletedProcess(
            [str(part) for part in command], 124, stdout, stderr
        )
    if result.stdout:
        log.append(result.stdout)
    if result.stderr:
        log.append(result.stderr)
    if verbose:
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
    return result


def find_project_files(project_dir: Path) -> tuple[Path, Path, Path]:
    projects = sorted(project_dir.glob("*.kicad_pro"))
    schematics = sorted(project_dir.glob("*.kicad_sch"))
    boards = sorted(project_dir.glob("*.kicad_pcb"))
    if len(projects) != 1 or len(schematics) != 1 or len(boards) != 1:
        raise SystemExit(
            f"Expected one .kicad_pro, one .kicad_sch, and one .kicad_pcb in "
            f"{project_dir}; found {len(projects)}, {len(schematics)}, "
            f"{len(boards)}."
        )
    return projects[0], schematics[0], boards[0]


def outcomes(data: dict, key: str) -> tuple[list[dict], list[dict]]:
    violations = data.get(key, [])
    errors = [item for item in violations if item.get("severity") == "error"]
    warnings = [item for item in violations if item.get("severity") != "error"]
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "project",
        nargs="?",
        default="examples/led_indicator",
        help="Project directory (default: examples/led_indicator)",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Copy generated BOM, Gerbers, and previews back into the project.",
    )
    parser.add_argument(
        "--no-render",
        action="store_true",
        help="Skip the 3D preview renders.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print full KiCad command output.",
    )
    args = parser.parse_args()

    project_dir = (REPO_ROOT / args.project).resolve()
    if not project_dir.is_dir():
        raise SystemExit(f"Project directory does not exist: {project_dir}")

    project_file, schematic, board = find_project_files(project_dir)
    name = project_file.stem
    output_dir = REPO_ROOT / "exports" / name
    render_dir = REPO_ROOT / "renders" / name
    output_dir.mkdir(parents=True, exist_ok=True)
    render_dir.mkdir(parents=True, exist_ok=True)

    kicad_cli = find_kicad_cli()
    if not kicad_cli:
        raise SystemExit(
            "kicad-cli was not found. Install KiCad 10 or set KICAD_CLI to the "
            "kicad-cli executable."
        )

    log: list[str] = []
    checks: list[dict[str, str]] = []
    version_text = "unknown"

    def check(name_: str, ok: bool, detail: str = "") -> None:
        checks.append(
            {
                "name": name_,
                "status": "PASS" if ok else "FAIL",
                "detail": detail,
            }
        )
        print(f"{'PASS' if ok else 'FAIL'}  {name_}" + (f"  ({detail})" if detail else ""))

    version = run([kicad_cli, "version"], log, verbose=args.verbose)
    version_text = (version.stdout or version.stderr).strip().splitlines()[0] if version.stdout or version.stderr else "unknown"
    major = 0
    if version_text and version_text[0].isdigit():
        major = int(version_text.split(".")[0])
    check(
        f"KiCad {MIN_MAJOR}.x",
        version.returncode == 0 and major == MIN_MAJOR,
        version_text,
    )
    if version.returncode != 0 or major != MIN_MAJOR:
        print("This repository targets KiCad 10.0.x. Set KICAD_CLI to a KiCad 10 executable.")
        return 1

    # ERC
    erc_path = output_dir / "erc.json"
    erc = run(
        [
            str(kicad_cli),
            "sch",
            "erc",
            "--format",
            "json",
            "--severity-all",
            "--output",
            str(erc_path),
            str(schematic),
        ],
        log,
        verbose=args.verbose,
    )
    erc_errors: list[dict] = []
    erc_warnings: list[dict] = []
    if erc.returncode == 0 and erc_path.is_file():
        erc_data = json.loads(erc_path.read_text(encoding="utf-8"))
        for sheet in erc_data.get("sheets", []):
            errors, warnings = outcomes(sheet, "violations")
            erc_errors.extend(errors)
            erc_warnings.extend(warnings)
    check("ERC", erc.returncode == 0 and not erc_errors, f"{len(erc_errors)} errors, {len(erc_warnings)} warnings")

    # DRC, including schematic parity and unconnected checks.
    drc_path = output_dir / "drc.json"
    drc = run(
        [
            str(kicad_cli),
            "pcb",
            "drc",
            "--format",
            "json",
            "--severity-all",
            "--schematic-parity",
            "--output",
            str(drc_path),
            str(board),
        ],
        log,
        verbose=args.verbose,
    )
    drc_errors: list[dict] = []
    drc_warnings: list[dict] = []
    unconnected: list[dict] = []
    parity: list[dict] = []
    if drc.returncode == 0 and drc_path.is_file():
        drc_data = json.loads(drc_path.read_text(encoding="utf-8"))
        drc_errors, drc_warnings = outcomes(drc_data, "violations")
        unconnected = drc_data.get("unconnected_items", [])
        parity = drc_data.get("schematic_parity", [])
    check(
        "DRC and schematic parity",
        drc.returncode == 0 and not drc_errors and not unconnected and not parity,
        f"{len(drc_errors)} errors, {len(drc_warnings)} warnings, "
        f"{len(unconnected)} unconnected, {len(parity)} parity",
    )

    # Netlist
    netlist_path = output_dir / "netlist.net"
    netlist = run(
        [
            str(kicad_cli),
            "sch",
            "export",
            "netlist",
            "--format",
            "kicadsexpr",
            "--output",
            str(netlist_path),
            str(schematic),
        ],
        log,
        verbose=args.verbose,
    )
    netlist_ok = (
        netlist.returncode == 0
        and netlist_path.is_file()
        and netlist_path.stat().st_size > 0
        and "(nets" in netlist_path.read_text(encoding="utf-8", errors="replace")
    )
    check("Netlist export", netlist_ok, str(netlist_path.name))

    # BOM
    bom_path = output_dir / "bom.csv"
    bom = run(
        [
            str(kicad_cli),
            "sch",
            "export",
            "bom",
            "--output",
            str(bom_path),
            "--fields",
            "Reference,Value,Footprint,MPN,QUANTITY",
            "--labels",
            "Refs,Value,Footprint,MPN,Qty",
            "--group-by",
            "Value,Footprint,MPN",
            "--sort-field",
            "Reference",
            str(schematic),
        ],
        log,
        verbose=args.verbose,
    )
    bom_rows: list[dict[str, str]] = []
    if bom.returncode == 0 and bom_path.is_file():
        with bom_path.open(newline="", encoding="utf-8") as handle:
            bom_rows = list(csv.DictReader(handle))
    check("BOM export", bom.returncode == 0 and bool(bom_rows), f"{len(bom_rows)} line items")

    # Gerbers
    gerber_dir = output_dir / "gerbers"
    if gerber_dir.exists():
        shutil.rmtree(gerber_dir)
    gerber_dir.mkdir(parents=True)
    gerbers = run(
        [
            str(kicad_cli),
            "pcb",
            "export",
            "gerbers",
            "--output",
            str(gerber_dir),
            "--layers",
            "F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts",
            "--precision",
            "6",
            str(board),
        ],
        log,
        verbose=args.verbose,
    )
    gerber_files = sorted(gerber_dir.glob("*"))
    required_gerbers = ["*-F_Cu.gtl", "*-B_Cu.gbl", "*-Edge_Cuts.gm1", "*-job.gbrjob"]
    gerbers_ok = gerbers.returncode == 0 and all(glob.glob(str(gerber_dir / pattern)) for pattern in required_gerbers)
    check("Gerber export", gerbers_ok, f"{len(gerber_files)} files")

    # Drill files and drill report
    drill_report = gerber_dir / "drill_report.txt"
    drill = run(
        [
            str(kicad_cli),
            "pcb",
            "export",
            "drill",
            "--output",
            str(gerber_dir),
            "--format",
            "excellon",
            "--excellon-separate-th",
            "--generate-map",
            "--map-format",
            "svg",
            "--generate-report",
            "--report-path",
            str(drill_report),
            str(board),
        ],
        log,
        verbose=args.verbose,
    )
    drills = sorted(gerber_dir.glob("*.drl"))
    drill_ok = drill.returncode == 0 and bool(drills) and drill_report.is_file()
    check("Drill export", drill_ok, f"{len(drills)} drill files")

    # Pick-and-place positions
    positions_path = gerber_dir / "positions.csv"
    positions = run(
        [
            str(kicad_cli),
            "pcb",
            "export",
            "pos",
            "--output",
            str(positions_path),
            "--format",
            "csv",
            "--units",
            "mm",
            "--side",
            "both",
            "--exclude-dnp",
            str(board),
        ],
        log,
        verbose=args.verbose,
    )
    check(
        "Position export",
        positions.returncode == 0 and positions_path.is_file() and positions_path.stat().st_size > 0,
        positions_path.name,
    )

    # 3D previews
    preview_paths: dict[str, Path] = {}
    if not args.no_render:
        render_specs = [
            ("top", ["--side", "top", "--width", "1000", "--height", "700"]),
            ("bottom", ["--side", "bottom", "--width", "1000", "--height", "700"]),
            (
                "iso",
                [
                    "--side",
                    "top",
                    "--width",
                    "1200",
                    "--height",
                    "850",
                    "--rotate",
                    "-45,0,45",
                    "--perspective",
                ],
            ),
        ]
        render_ok = True
        for label, extra in render_specs:
            preview = render_dir / f"{label}.png"
            render = run(
                [
                    str(kicad_cli),
                    "pcb",
                    "render",
                    "--output",
                    str(preview),
                    "--background",
                    "opaque",
                    "--quality",
                    "basic",
                    *extra,
                    str(board),
                ],
                log,
                verbose=False,
                timeout=300,
            )
            preview_paths[label] = preview
            if render.returncode != 0 or not preview.is_file() or preview.stat().st_size < 1000:
                render_ok = False
        check("3D previews", render_ok, "top, bottom, iso")
    else:
        check("3D previews", True, "skipped")

    # Checked-in artifacts
    canonical_bom = project_dir / "bom.csv"
    canonical_gerbers = project_dir / "gerbers"
    canonical_previews = project_dir / "previews"
    canonical_ok = (
        canonical_bom.is_file()
        and canonical_gerbers.is_dir()
        and any(canonical_gerbers.glob("*.gtl"))
        and canonical_previews.is_dir()
        and (canonical_previews / "top.png").is_file()
    )
    check("Checked-in artifacts", canonical_ok, "BOM, Gerbers, previews")

    if args.refresh:
        shutil.copy2(bom_path, canonical_bom)
        if canonical_gerbers.exists():
            shutil.rmtree(canonical_gerbers)
        shutil.copytree(gerber_dir, canonical_gerbers)
        canonical_previews.mkdir(parents=True, exist_ok=True)
        for label, source in preview_paths.items():
            if source.is_file():
                shutil.copy2(source, canonical_previews / f"{label}.png")
        check("Canonical artifacts refreshed", True, str(project_dir))

    report = {
        "project": str(project_dir),
        "kicad_cli": str(kicad_cli),
        "kicad_version": version_text,
        "generated": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "erc": {
            "errors": len(erc_errors),
            "warnings": len(erc_warnings),
            "report": str(erc_path),
        },
        "drc": {
            "errors": len(drc_errors),
            "warnings": len(drc_warnings),
            "unconnected": len(unconnected),
            "schematic_parity": len(parity),
            "report": str(drc_path),
        },
        "bom_line_items": len(bom_rows),
        "gerber_files": [path.name for path in gerber_files],
        "drill_files": [path.name for path in drills],
    }
    report_path = output_dir / "verification_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    (output_dir / "last_run.log").write_text("\n".join(log), encoding="utf-8")

    failures = [item for item in checks if item["status"] == "FAIL"]
    print()
    print(f"Report: {report_path}")
    print(f"ERC: {len(erc_errors)} errors, {len(erc_warnings)} warnings")
    print(f"DRC: {len(drc_errors)} errors, {len(drc_warnings)} warnings, "
          f"{len(unconnected)} unconnected, {len(parity)} parity")
    print(f"Checks: {len(checks) - len(failures)}/{len(checks)} passed")
    if failures:
        print("FAIL")
        for item in failures:
            print(f"  - {item['name']}: {item['detail']}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
