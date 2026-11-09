"""Compile this lesson's picture-table variants without embedding other pages' art."""

from pathlib import Path
import re


PAGE_ASSETS = {
    "light-and-field": {"sun-moon", "field-pull"},
    "tips-and-dust": {"tip-cone", "dust-beam"},
    "more-together": {"people-follow", "people-group", "tree-grove", "forest-view"},
    "new-characters": {"studio", "tears", "seedling-bed", "tilted-frame"},
    "work-together": {"paper-build", "paper-built"},
    "words": {"studio", "field-pull", "dust-beam", "paired-hands", "gold-leaves",
              "tree-grove", "forest-view", "care-help", "happy-child"},
}
IMAGE = re.compile(r"__IMG:([a-z0-9-]+)__")


def materialize(pages: Path) -> None:
    templates = pages / "templates"
    html = (templates / "learning-table.html").read_text(encoding="utf-8")
    css = (templates / "learning-table.css").read_text(encoding="utf-8")
    script = (templates / "learning-table.js").read_text(encoding="utf-8").splitlines(keepends=True)
    for page, assets in PAGE_ASSETS.items():
        compiled = []
        for line in script:
            ids = set(IMAGE.findall(line))
            if not ids or ids <= assets:
                compiled.append(line)
        script_text = "".join(compiled)
        if set(IMAGE.findall(script_text)) != assets:
            raise ValueError(f"Incomplete image mapping for {page}")
        for ext, content in (("html", html), ("css", css), ("js", script_text)):
            (pages / f"{page}.{ext}").write_text(content, encoding="utf-8")


if __name__ == "__main__":
    materialize(Path(__file__).resolve().parent)
