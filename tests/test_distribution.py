import ast
import io
import re
import tempfile
import unittest
from pathlib import Path

from mktgkit import __version__, cli
from tools.render_system_map import drawing

ROOT = Path(__file__).resolve().parents[1]


class DistributionTests(unittest.TestCase):
    def test_python39_syntax_and_versions(self):
        self.assertIn(f'version = "{__version__}"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        for name in ("mktgkit", "tests", "tools", "recipes"):
            for path in (ROOT / name).rglob("*.py"):
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 9))

    def test_demo_is_reproducible_and_readme_quotes_it(self):
        outputs = []
        for _ in range(2):
            out, err = io.StringIO(), io.StringIO()
            self.assertEqual(cli.main(["demo"], stdout=out, stderr=err), 0, err.getvalue())
            outputs.append(out.getvalue())
        self.assertEqual(outputs[0], outputs[1])
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for excerpt in re.findall(r"\x60{3}text\n(.*?)\n\x60{3}", readme, flags=re.DOTALL):
            self.assertIn(excerpt, outputs[0])
        self.assertIn("Allowed Q-0004", outputs[0])

    def test_documentation_assets_and_links(self):
        for mode in ["light", "dark"]:
            self.assertEqual(
                (ROOT / "assets" / f"system-map-{mode}.svg").read_text(encoding="utf-8"),
                drawing(mode == "dark"),
            )
        for doc in [ROOT / "README.md", *(ROOT / "docs").rglob("*.md")]:
            for link in re.findall(r"\[[^\]\n]+\]\(([^) ]+)\)", doc.read_text(encoding="utf-8")):
                if link.startswith(("https://", "http://", "#", "mailto:")):
                    continue
                self.assertTrue((doc.parent / link.split("#")[0]).exists(), f"{doc.name}: {link}")

    def test_seeded_queue_is_generated_by_real_commands(self):
        from tools.build_example import build

        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "new"
            build(target)
            for sub in ("queue", "log", "brain/edits", "drafts"):
                installed = sorted(p.relative_to(target) for p in (target / sub).rglob("*") if p.is_file())
                committed = sorted(
                    p.relative_to(ROOT / "examples/wrenfield")
                    for p in (ROOT / "examples/wrenfield" / sub).rglob("*")
                    if p.is_file()
                )
                self.assertEqual(installed, committed)
                for path in installed:
                    self.assertEqual(
                        (target / path).read_text(encoding="utf-8"),
                        (ROOT / "examples/wrenfield" / path).read_text(encoding="utf-8"),
                    )
