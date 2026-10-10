"""Zip each Claude skill in skills/ so it can be uploaded or unzipped into ~/.claude/skills.

    python scripts/package_skills.py --out dashboard/skills

Each archive holds one folder named after the skill (hrc-voting/SKILL.md, …), which is the layout
Claude.ai's skill upload and Claude Code's skills directory expect. Timestamps are fixed so the
same sources give the same bytes. The Pages workflow runs this, so no archive is committed.
"""
import argparse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP = {"__pycache__", ".DS_Store"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for sk in sorted(p for p in (ROOT / "skills").iterdir() if (p / "SKILL.md").exists()):
        target = out / f"{sk.name}.zip"
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for f in sorted(sk.rglob("*")):
                if f.is_file() and not (SKIP & set(f.parts)) and f.suffix != ".pyc":
                    zi = zipfile.ZipInfo(f"{sk.name}/{f.relative_to(sk).as_posix()}", (2026, 1, 1, 0, 0, 0))
                    zi.compress_type = zipfile.ZIP_DEFLATED
                    zi.external_attr = (0o755 if f.suffix == ".py" else 0o644) << 16
                    z.writestr(zi, f.read_bytes())
        print(f"{target.name}: {target.stat().st_size/1e6:.2f} MB")


if __name__ == "__main__":
    main()
