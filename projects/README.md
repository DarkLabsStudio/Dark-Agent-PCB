# Projects

Create one directory per board here, for example:

```text
projects/
└── my_board/
    ├── my_board.kicad_pro
    ├── my_board.kicad_sch
    ├── my_board.kicad_pcb
    ├── bom.csv
    ├── gerbers/
    └── previews/
```

Start by copying `examples/led_indicator/` and renaming the three KiCad files to the
same base name. Follow [`../setup.md`](../setup.md) for the full workflow, then run:

```bash
python scripts/runner.py projects/my_board --refresh
```

Commit the source files, BOM, Gerbers, and previews together. Do not commit the
generated `exports/` or `renders/` directories; they are ignored by git.
