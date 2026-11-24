"""Install the packaged workspace without overwriting an existing client."""

import json
import shutil
import tempfile
from pathlib import Path

from .errors import MktgError

TEMPLATE = Path(__file__).parent / "template"
EXAMPLE = Path(__file__).parent / "_example"
if not EXAMPLE.is_dir():
    EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "wrenfield"
DIRS = (
    "drafts",
    "queue",
    "batches",
    "log",
    "brain/offers",
    "brain/customers",
    "brain/brand",
    "brain/claims",
    "brain/results",
    "brain/edits",
    "brain/skills",
    "brain/research",
)


def init(target, *, name=None, example=False):
    target = Path(target).absolute()
    if target.is_symlink() or (target.exists() and (not target.is_dir() or any(target.iterdir()))):
        raise MktgError("destination must be new or empty", path=target.name)
    target.parent.mkdir(parents=True, exist_ok=True)
    source = EXAMPLE if example else TEMPLATE
    if not (source / "mktgkit.json").is_file():
        raise MktgError("workspace resources missing; reinstall the complete package")
    with tempfile.TemporaryDirectory(dir=target.parent, prefix=".mktgkit-init-") as tmp:
        build = Path(tmp) / "workspace"
        build.mkdir()
        for path in sorted(source.rglob("*")):
            rel = path.relative_to(source)
            if any(part in (".mktgkit-state", "__pycache__", ".git", "out") for part in rel.parts):
                continue
            if path.name.startswith("warehouse.db") or path.suffix == ".pyc":
                continue
            out = build.joinpath(
                *(s.replace("_dot_", ".", 1) if s.startswith("_dot_") else s for s in rel.parts)
            )
            if path.is_file():
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, out)
        for d in DIRS:
            (build / d).mkdir(parents=True, exist_ok=True)
        (build / "log/ledger.jsonl").touch(exist_ok=True)
        cfg = build / "mktgkit.json"
        data = json.loads(cfg.read_text(encoding="utf-8"))
        if not example or name:
            data["name"] = name or target.name
            cfg.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if target.exists():
            target.rmdir()
        build.rename(target)
    return target
