# Dark-Agent-PCB agent setup and acceptance contract

This file is the operational contract for agents working in this repository. Read it
in full before changing any project. The goal is a verified KiCad 10 board with a
schematic, PCB, BOM, Gerbers, drill files, position data, and a visible 3D preview.

This repository covers electronics. The companion mechanical repository is
**[Dark-Agent-CAD](https://github.com/DarkLabsStudio/Dark-Agent-CAD)**: an agent-ready
build123d workspace for parts, enclosures, STEP models, and VTK previews. Use the two
together when a board and its mechanical surroundings need to fit.

## 1. Non-negotiable rules

1. **Clone first.** Work from a clone of
   `https://github.com/DarkLabsStudio/Dark-Agent-PCB.git`.
2. **Run the baseline before editing.** The checked-in example must pass before a new
   board is created.
3. **Do not install KiCad or any optional dependency silently.** If KiCad 10,
   `kicad-cli`, or a requested tool is missing, stop and ask the human. Use the
   question tool for approval and for choices that affect the system.
4. **Do not weaken checks to make a board pass.** Fix the design, the export, or the
   project metadata. Never delete a failing net, remove a component, or suppress a
   check without explicit approval.
5. **Do not hand-edit generated artifacts.** BOM, Gerbers, drill files, position data,
   and previews are generated from the schematic and PCB by `scripts/runner.py`.
6. **Keep KiCad external.** Do not vendor KiCad binaries or libraries. Use the
   installed KiCad 10 symbol, footprint, and 3D-model libraries by name.
7. **Protect user work.** Inspect existing files before replacing them. Do not discard
   uncommitted changes or unrelated files.

## 2. Locate KiCad 10

Required version: **KiCad 10.0.x**. This repository was validated with **10.0.8**.

Find `kicad-cli`:

```powershell
# Windows, user-local install
$env:KICAD_CLI = "$env:LOCALAPPDATA\Programs\KiCad\10.0\bin\kicad-cli.exe"

# Windows, system install
$env:KICAD_CLI = "$env:ProgramFiles\KiCad\10.0\bin\kicad-cli.exe"

& $env:KICAD_CLI version
```

```bash
# macOS
export KICAD_CLI="/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"

# Linux
export KICAD_CLI="$(command -v kicad-cli)"

"$KICAD_CLI" version
```

The command must report `10.0.x`. If it reports another major version, stop and ask
which KiCad version to use. If `kicad-cli` is not found, the runner also searches
common install locations, but setting `KICAD_CLI` explicitly is preferred.

Python:

```bash
python --version
# or: python3 --version
# or on Windows: py -3.12 --version
```

Use Python 3.10 or newer. The runner has no third-party dependencies.

## 3. Baseline verification

From the repository root:

```bash
python scripts/runner.py examples/led_indicator
```

Expected behavior:

```text
PASS  KiCad 10.x
PASS  ERC
PASS  DRC and schematic parity
PASS  Netlist export
PASS  BOM export
PASS  Gerber export
PASS  Drill export
PASS  Position export
PASS  3D previews
PASS  Checked-in artifacts
PASS
```

For the reference board, the electrical result must be:

- ERC: **0 errors**
- DRC: **0 errors**
- Unconnected items: **0**
- Schematic parity issues: **0**
- BOM: at least one line item
- Gerbers: copper, mask, silkscreen, paste, Edge.Cuts, and job file present
- Drill: at least one `.drl` file plus drill report
- Position: `positions.csv` non-empty
- Previews: top, bottom, and isometric PNGs non-empty

Warnings are reported but are not failures. The headless CLI commonly reports
library-configuration warnings because it may not have the same global library table
setup as the GUI. Treat those as environmental unless the warning is an electrical or
geometry problem. Inspect the JSON reports before dismissing warnings.

Run with `--refresh` when you want to regenerate the canonical checked-in artifacts:

```bash
python scripts/runner.py examples/led_indicator --refresh
```

This adds an eleventh check, `Canonical artifacts refreshed`.

## 4. What the runner does

`scripts/runner.py`:

1. Finds KiCad 10 and verifies its major version.
2. Finds the single `.kicad_pro`, `.kicad_sch`, and `.kicad_pcb` in the project.
3. Runs `kicad-cli sch erc --format json --severity-all`.
4. Runs `kicad-cli pcb drc --format json --severity-all --schematic-parity`.
5. Exports a KiCad S-expression netlist.
6. Exports a grouped BOM with `Reference`, `Value`, `Footprint`, `MPN`, and `Qty`.
7. Exports Gerbers for `F.Cu`, `B.Cu`, paste, silkscreen, mask, and `Edge.Cuts`.
8. Exports Excellon drill files with separate PTH/NPTH files, drill maps, and a drill
   report.
9. Exports a pick-and-place position CSV.
10. Renders top, bottom, and isometric PNG previews with `kicad-cli pcb render`.
11. Checks that the checked-in BOM, Gerber directory, and top preview exist.
12. Writes `exports/<project>/verification_report.json` and `last_run.log`.

Generated outputs go to:

- `exports/<project>/` — ERC/DRC JSON, netlist, BOM, Gerbers, drill files, positions,
  report, and log.
- `renders/<project>/` — fresh preview PNGs.

Both directories are ignored by git. The canonical artifacts live inside the project
directory: `bom.csv`, `gerbers/`, and `previews/`.

## 5. Create a new board

### 5.1 Copy the reference project

Use a new directory under `projects/`:

```powershell
New-Item -ItemType Directory -Force projects\my_board
Copy-Item examples\led_indicator\led_indicator.kicad_pro projects\my_board\my_board.kicad_pro
Copy-Item examples\led_indicator\led_indicator.kicad_sch projects\my_board\my_board.kicad_sch
Copy-Item examples\led_indicator\led_indicator.kicad_pcb projects\my_board\my_board.kicad_pcb
```

```bash
mkdir -p projects/my_board
cp examples/led_indicator/led_indicator.kicad_pro projects/my_board/my_board.kicad_pro
cp examples/led_indicator/led_indicator.kicad_sch projects/my_board/my_board.kicad_sch
cp examples/led_indicator/led_indicator.kicad_pcb projects/my_board/my_board.kicad_pcb
```

Update `meta.filename` in the copied `.kicad_pro` to `my_board.kicad_pro`. Keep the
project, schematic, and PCB base names identical.

Do not copy the example's `gerbers/`, `previews/`, or `bom.csv` into the new project.
The runner will generate them after the design is verified.

### 5.2 Edit in KiCad 10

Open the project in KiCad 10. Recommended sequence:

1. Edit the schematic. Use official KiCad symbols and assign official footprints.
2. Add `PWR_FLAG` symbols to power nets when ERC reports `power_pin_not_driven`.
3. Add a schematic symbol for every footprint that must appear on the board, including
   mounting holes. Extra board footprints fail schematic parity.
4. Set useful `Value`, `Footprint`, `MPN`, and `Description` fields. The PCB footprint
   fields must match the schematic fields.
5. Use **Tools → Update PCB from Schematic** after schematic changes so references,
   values, footprints, MPN, and Description fields are synchronized.
6. Route the PCB. Keep the board outline closed on `Edge.Cuts`.
7. Run ERC and DRC in KiCad before exporting.

When editing the PCB, keep the design simple unless the task requires otherwise:

- 2 copper layers by default.
- 0.5 mm tracks are sufficient for the reference-style LED/power boards.
- Keep copper and silkscreen clear of mounting holes and board edges.
- Use official 3D models where available so renders are meaningful.
- Check that every pad has a net or an intentional no-connect.

### 5.3 Verify and refresh artifacts

From the repository root:

```bash
python scripts/runner.py projects/my_board --refresh
```

If the runner reports `DRC and schematic parity` failure, inspect:

```text
exports/my_board/drc.json
```

Look for `schematic_parity` entries. The usual fixes are:

- A board footprint has no matching schematic symbol (for example, an extra mounting
  hole).
- A footprint value or footprint ID differs from the schematic.
- `MPN` or `Description` exists in the schematic but is missing on the PCB footprint.
- The PCB was not updated after a schematic change.

Do not fix parity by deleting the fields from the schematic. Sync the PCB from the
schematic instead.

## 6. Manual export commands

The runner is the normal path. These commands are useful for targeted debugging.

```powershell
$cli = $env:KICAD_CLI
$proj = "examples\led_indicator\led_indicator.kicad_sch"
$board = "examples\led_indicator\led_indicator.kicad_pcb"

& $cli sch erc --format json --severity-all --output exports\erc.json $proj
& $cli pcb drc --format json --severity-all --schematic-parity --output exports\drc.json $board
& $cli sch export netlist --format kicadsexpr --output exports\netlist.net $proj
& $cli sch export bom --output exports\bom.csv --fields "Reference,Value,Footprint,MPN,QUANTITY" --labels "Refs,Value,Footprint,MPN,Qty" --group-by "Value,Footprint,MPN" --sort-field "Reference" $proj
& $cli pcb export gerbers --output exports\gerbers --layers "F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts" --precision 6 $board
& $cli pcb export drill --output exports\gerbers --format excellon --excellon-separate-th --generate-map --map-format svg --generate-report --report-path exports\gerbers\drill_report.txt $board
& $cli pcb export pos --output exports\gerbers\positions.csv --format csv --units mm --side both --exclude-dnp $board
& $cli pcb render --output renders\top.png --side top --background opaque --quality basic $board
```

On macOS/Linux, use `"$KICAD_CLI"` and forward slashes. `kicad-cli` also supports
`--help` for every subcommand.

## 7. Acceptance checklist

A board is ready only when all of these are true:

- [ ] `scripts/runner.py` exits with `PASS`.
- [ ] ERC errors: `0`.
- [ ] DRC errors: `0`.
- [ ] Unconnected items: `0`.
- [ ] Schematic-parity issues: `0`.
- [ ] Netlist exists and contains a `(nets` section.
- [ ] BOM has at least one line item and includes the intended MPNs.
- [ ] Gerbers include copper, mask, silkscreen, paste, `Edge.Cuts`, and a job file.
- [ ] Drill files include the expected PTH/NPTH holes.
- [ ] Position CSV exists and is non-empty.
- [ ] Top, bottom, and isometric previews exist and are non-empty.
- [ ] Checked-in `bom.csv`, `gerbers/`, and `previews/` are refreshed from the final
      design.
- [ ] No generated `exports/` or `renders/` directory is staged for commit.
- [ ] The human-facing report names any remaining warnings and fabrication caveats.

If a check cannot be completed, do not claim success. Report the exact failing check,
the relevant JSON/report path, and what the human needs to decide or install.

## 8. Final report format

Return a short report with:

```text
Board:
- Name and path:
- Purpose:
- Board size / layers:
- Main components and nets:

Verification:
- Runner result: PASS/FAIL
- ERC: N errors, N warnings
- DRC: N errors, N warnings, N unconnected, N parity
- BOM: N line items
- Fabrication files:
- Previews:

Warnings and caveats:
- ...

Next action:
- ...
```

For the reference board, do not report warnings as failures. For a new board, explain
whether each warning is electrical, geometric, or environmental.

## 9. Troubleshooting

### `kicad-cli was not found`

Set `KICAD_CLI` to the full executable path and run again. Do not install KiCad without
approval.

### `Failed to load schematic` or `Failed to load board`

The file may be malformed or from an incompatible KiCad version. Open it in KiCad 10
and save it, or use:

```bash
"$KICAD_CLI" sch upgrade path/to/project.kicad_sch
"$KICAD_CLI" pcb upgrade path/to/project.kicad_pcb
```

Do not try to repair a KiCad S-expression by deleting randomly. Prefer the GUI or a
scripted `pcbnew`/`kiutils` workflow, then re-run the checks.

### ERC: `Input Power pin not driven by any Output Power pins`

Add a `PWR_FLAG` symbol to each power net, or add an appropriate power-output pin.
Re-run ERC.

### ERC: `Pin not connected`

Connect the pin or add an intentional no-connect flag. Check symbol rotation and pin
coordinates carefully; a wire that looks close may not touch the pin.

### DRC: `schematic_parity` warnings

Open `exports/<project>/drc.json`. Sync the PCB from the schematic and add missing
`MPN`/`Description` fields on the PCB footprints if needed.

### DRC: `unconnected_items`

Route every pad to its net, or add a no-connect. Check that every net has a source and
a destination.

### DRC: malformed or open board outline

Use `Edge.Cuts` only, close the outline, and avoid gaps at corners. A rectangle made of
four segments is sufficient for simple boards.

### Library warnings

Headless `kicad-cli` may not see the GUI's global library tables. The warnings
`lib_symbol_issues`, `footprint_link_issues`, and `lib_footprint_issues` are usually
environmental. Do not remove library references just to silence them. Verify that the
board still exports and that ERC/DRC have zero errors.

### 3D render is slow or fails

Rendering is CPU-heavy. The runner uses `--quality basic` for predictable headless
runs. Ensure the KiCad 3D model libraries are installed. Use `--no-render` only for a
diagnostic run; a complete acceptance run must include previews.

## 10. Human escalation

Ask the human before:

- installing KiCad or any package;
- changing the KiCad major version;
- removing components, nets, or design rules to pass a check;
- sending a board to fabrication;
- overwriting unrelated or uncommitted work.
