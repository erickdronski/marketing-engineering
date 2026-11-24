"""Regenerate the two static diagrams used by the repository landing page."""

from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def drawing(dark=False):
    paper, ink, muted, line, accent, panel = (
        ("#101820", "#F1F5F7", "#B1C7D3", "#55717F", "#75D3B5", "#192B35")
        if dark
        else ("#F8FBFA", "#142D3A", "#375564", "#94ABA9", "#17694F", "#EAF3EF")
    )
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 322" role="img" aria-labelledby="title desc"><title id="title">The client operating loop</title><desc id="desc">An owner defines a goal, an agent prepares work, a reviewer signs off, and the operator records delivery and measures the result. Evidence informs the next brief.</desc><rect width="720" height="322" rx="15" fill="{paper}"/>'
    ]
    roles = [
        ("CLIENT OWNER", "Choose the outcome", "Define a number and its source."),
        ("AGENT TEAM", "Prepare the work", "Draft a change and cite the evidence."),
        ("REVIEWER", "Decide on this version", "Approve or return a specific edit."),
        ("OPERATOR", "Deliver and reconcile", "Record delivery, exceptions and results."),
    ]
    for i, (role, title, detail) in enumerate(roles):
        y = 15 + i * 67
        parts.append(f'<rect x="19" y="{y}" width="681" height="54" rx="7" fill="{panel}"/>')
        for x, off, text, size, color, weight in [
            (34, 32, role, 13, accent, 700),
            (180, 32, title, 18, ink, 650),
            (404, 32, detail, 14, muted, 400),
        ]:
            parts.append(
                f'<text x="{x}" y="{y + off}" font-family="system-ui,sans-serif" font-size="{size}" font-weight="{weight}" fill="{color}">{escape(text)}</text>'
            )
        if i < 3:
            parts.append(
                f'<path d="M49 {y + 54}v11m-3 -4 3 4 3 -4" stroke="{line}" fill="none" stroke-width="2"/>'
            )
    parts.append(
        f'<text x="34" y="302" fill="{accent}" font-family="system-ui,sans-serif" font-size="16" font-weight="600">The next brief starts with the last result and its source date.</text></svg>'
    )
    return "\n".join(parts) + "\n"


if __name__ == "__main__":
    folder = ROOT / "assets"
    folder.mkdir(exist_ok=True)
    for name in ("light", "dark"):
        (folder / f"system-map-{name}.svg").write_text(drawing(name == "dark"), encoding="utf-8")
