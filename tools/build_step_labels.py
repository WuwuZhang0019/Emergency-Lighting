"""Regenerate red DCL step-number glyph runs. Date: 2026-10-15."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
START = ";; BEGIN GENERATED RED STEP LABELS"
END = ";; END GENERATED RED STEP LABELS"
LABELS = ("第一步：", "第二步：", "第三步：", "第四步：")


def glyph_runs(label):
    font = ImageFont.truetype("C:/Windows/Fonts/simsun.ttc", 14)
    image = Image.new("1", (56, 14), 0)
    ImageDraw.Draw(image).text((0, -1), label, font=font, fill=1)
    runs = []
    for y in range(image.height):
        x = 0
        while x < image.width:
            if image.getpixel((x, y)):
                start = x
                while x < image.width and image.getpixel((x, y)):
                    x += 1
                runs.append((start, y, x - start))
            else:
                x += 1
    return runs


def build():
    groups = []
    for label in LABELS:
        runs = glyph_runs(label)
        lines = ["    " + " ".join("(%d %d %d)" % run for run in runs[i:i + 8])
                 for i in range(0, len(runs), 8)]
        groups.append("  ; " + label + "\n  (" + "\n".join(lines) + ")")
    source = (START + "\n;; Date: 2026-10-15. SimSun 14 px, 56 x 14; runtime has no font/file dependency.\n"
              "(defun EL:StepLabelRuns (index)\n  (nth (1- index) '\n(\n" + "\n".join(groups) + "\n)))\n" + END)
    path = ROOT / "src/panel.lsp"
    text = path.read_text(encoding="utf-8")
    if START in text:
        a, b = text.index(START), text.index(END) + len(END)
        text = text[:a] + source + text[b:]
    else:
        text += "\n" + source + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    print("Updated four red step-number glyphs")


if __name__ == "__main__":
    build()
