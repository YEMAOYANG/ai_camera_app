#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]

INK = (30, 41, 51, 255)
MUTED = (82, 96, 109, 255)
SURFACE = (247, 249, 250, 255)
CARD = (255, 255, 255, 255)
LINE = (226, 232, 238, 255)
TEAL = (50, 108, 143, 255)
TEAL_DARK = (30, 86, 111, 255)
MINT = (206, 240, 224, 255)
SKY = (190, 225, 247, 255)
AMBER = (178, 123, 20, 255)
SUCCESS = (58, 132, 99, 255)


def ensure(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def rounded_rectangle_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=255)
    return mask


def resize_square(source: Image.Image, size: int, *, opaque: bool = True) -> Image.Image:
    image = source.resize((size, size), Image.Resampling.LANCZOS)
    if opaque:
        background = Image.new("RGBA", (size, size), SURFACE)
        background.alpha_composite(image)
        image = background
    return image.convert("RGBA")


def save_png(image: Image.Image, path: Path) -> None:
    ensure(path.parent)
    image.save(path, "PNG", optimize=True)


def vertical_gradient(size: tuple[int, int], top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    width, height = size
    image = Image.new("RGBA", size)
    pixels = image.load()
    for y in range(height):
        ratio = y / max(height - 1, 1)
        color = tuple(int(top[i] * (1 - ratio) + bottom[i] * ratio) for i in range(3)) + (255,)
        for x in range(width):
            pixels[x, y] = color
    return image


def draw_soft_shadow(canvas: Image.Image, box: tuple[int, int, int, int], radius: int, blur: int, alpha: int) -> None:
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(shadow)
    draw.rounded_rectangle(box, radius=radius, fill=(22, 42, 58, alpha))
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(shadow)


def draw_brand_symbol(canvas: Image.Image, box: tuple[int, int, int, int], *, with_tile: bool) -> None:
    draw = ImageDraw.Draw(canvas)
    x0, y0, x1, y1 = box
    width = x1 - x0
    height = y1 - y0
    scale = min(width, height)

    if with_tile:
        draw_soft_shadow(canvas, box, int(scale * 0.18), int(scale * 0.05), 34)
        draw.rounded_rectangle(box, radius=int(scale * 0.18), fill=CARD)

    cx = (x0 + x1) // 2
    top = y0 + int(height * 0.2)
    shield = [
        (cx, top),
        (x0 + int(width * 0.76), y0 + int(height * 0.32)),
        (x0 + int(width * 0.71), y0 + int(height * 0.66)),
        (cx, y0 + int(height * 0.83)),
        (x0 + int(width * 0.29), y0 + int(height * 0.66)),
        (x0 + int(width * 0.24), y0 + int(height * 0.32)),
    ]
    draw.polygon(shield, fill=(235, 249, 243, 255), outline=TEAL, width=max(2, int(scale * 0.035)))

    lens_r = int(scale * 0.16)
    draw.ellipse((cx - lens_r, y0 + int(height * 0.43) - lens_r, cx + lens_r, y0 + int(height * 0.43) + lens_r), fill=TEAL)
    draw.ellipse((cx - int(lens_r * 0.45), y0 + int(height * 0.43) - int(lens_r * 0.45), cx + int(lens_r * 0.45), y0 + int(height * 0.43) + int(lens_r * 0.45)), fill=SKY)
    draw.arc(
        (cx - int(scale * 0.22), y0 + int(height * 0.52), cx + int(scale * 0.22), y0 + int(height * 0.76)),
        start=20,
        end=150,
        fill=SUCCESS,
        width=max(2, int(scale * 0.035)),
    )
    draw.line(
        [
            (x0 + int(width * 0.44), y0 + int(height * 0.66)),
            (x0 + int(width * 0.5), y0 + int(height * 0.72)),
            (x0 + int(width * 0.62), y0 + int(height * 0.59)),
        ],
        fill=SUCCESS,
        width=max(2, int(scale * 0.038)),
        joint="curve",
    )


def create_app_icon(size: int = 1024) -> Image.Image:
    canvas = vertical_gradient((size, size), (241, 249, 246), (222, 238, 247))
    draw = ImageDraw.Draw(canvas)

    draw.ellipse((-size * 0.12, -size * 0.08, size * 0.56, size * 0.52), fill=(210, 241, 225, 210))
    draw.ellipse((size * 0.48, size * 0.56, size * 1.16, size * 1.1), fill=(191, 225, 247, 190))
    draw.rounded_rectangle(
        (int(size * 0.13), int(size * 0.13), int(size * 0.87), int(size * 0.87)),
        radius=int(size * 0.19),
        fill=(255, 255, 255, 220),
        outline=(207, 223, 232, 255),
        width=int(size * 0.018),
    )
    draw_brand_symbol(
        canvas,
        (int(size * 0.24), int(size * 0.2), int(size * 0.76), int(size * 0.78)),
        with_tile=False,
    )
    draw.ellipse((int(size * 0.68), int(size * 0.18), int(size * 0.82), int(size * 0.32)), fill=(255, 246, 218, 255))
    draw.ellipse((int(size * 0.72), int(size * 0.22), int(size * 0.78), int(size * 0.28)), fill=AMBER)
    return canvas.convert("RGBA")


def create_mark(size: int) -> Image.Image:
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw_brand_symbol(canvas, (int(size * 0.08), int(size * 0.08), int(size * 0.92), int(size * 0.92)), with_tile=True)
    return canvas


def draw_card(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int = 24) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=CARD, outline=LINE, width=2)


def create_welcome_hero(size: int) -> Image.Image:
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    s = size / 360

    draw.ellipse((18 * s, 30 * s, 340 * s, 328 * s), fill=(225, 242, 248, 255))
    draw.ellipse((0 * s, 156 * s, 174 * s, 344 * s), fill=(222, 245, 232, 255))
    draw.ellipse((224 * s, 28 * s, 356 * s, 156 * s), fill=(255, 246, 218, 255))

    draw_soft_shadow(canvas, (56, 86, size - 52, size - 50), int(24 * s), int(8 * s), 28)
    draw_card(draw, (int(56 * s), int(86 * s), int(308 * s), int(310 * s)), radius=int(24 * s))

    # Camera body.
    draw.rounded_rectangle((int(127 * s), int(68 * s), int(234 * s), int(158 * s)), radius=int(24 * s), fill=TEAL)
    draw.rounded_rectangle((int(146 * s), int(152 * s), int(215 * s), int(176 * s)), radius=int(9 * s), fill=TEAL_DARK)
    draw.rounded_rectangle((int(128 * s), int(176 * s), int(236 * s), int(193 * s)), radius=int(8 * s), fill=(205, 224, 233, 255))
    draw.ellipse((int(153 * s), int(84 * s), int(209 * s), int(140 * s)), fill=(236, 248, 252, 255))
    draw.ellipse((int(166 * s), int(97 * s), int(196 * s), int(127 * s)), fill=INK)
    draw.ellipse((int(176 * s), int(105 * s), int(187 * s), int(116 * s)), fill=SKY)
    draw.ellipse((int(212 * s), int(85 * s), int(226 * s), int(99 * s)), fill=(255, 246, 218, 255))

    # Child desk scene.
    draw.ellipse((int(92 * s), int(207 * s), int(142 * s), int(257 * s)), fill=(250, 219, 185, 255))
    draw.arc((int(86 * s), int(196 * s), int(148 * s), int(254 * s)), start=195, end=340, fill=INK, width=int(10 * s))
    draw.rounded_rectangle((int(78 * s), int(251 * s), int(154 * s), int(296 * s)), radius=int(18 * s), fill=(190, 225, 247, 255))
    draw.rounded_rectangle((int(74 * s), int(286 * s), int(250 * s), int(306 * s)), radius=int(10 * s), fill=(221, 226, 231, 255))
    draw.rounded_rectangle((int(166 * s), int(226 * s), int(249 * s), int(278 * s)), radius=int(10 * s), fill=(255, 250, 239, 255), outline=(225, 202, 158, 255), width=int(2 * s))
    draw.line((int(184 * s), int(242 * s), int(231 * s), int(242 * s)), fill=(195, 161, 91, 255), width=int(3 * s))
    draw.line((int(184 * s), int(256 * s), int(220 * s), int(256 * s)), fill=(195, 161, 91, 255), width=int(3 * s))

    # Floating status chips.
    draw.rounded_rectangle((int(43 * s), int(45 * s), int(122 * s), int(84 * s)), radius=int(19 * s), fill=CARD, outline=LINE, width=int(2 * s))
    draw.ellipse((int(58 * s), int(58 * s), int(72 * s), int(72 * s)), fill=SUCCESS)
    draw.line((int(62 * s), int(66 * s), int(66 * s), int(70 * s), int(74 * s), int(60 * s)), fill=CARD, width=max(2, int(2 * s)))

    draw.rounded_rectangle((int(230 * s), int(204 * s), int(320 * s), int(250 * s)), radius=int(20 * s), fill=CARD, outline=LINE, width=int(2 * s))
    draw.ellipse((int(247 * s), int(219 * s), int(263 * s), int(235 * s)), fill=AMBER)
    draw.rectangle((int(272 * s), int(220 * s), int(302 * s), int(226 * s)), fill=(173, 186, 199, 255))
    draw.rectangle((int(272 * s), int(232 * s), int(292 * s), int(238 * s)), fill=(173, 186, 199, 255))

    return canvas.resize((size, size), Image.Resampling.LANCZOS)


def generate_flutter_assets() -> None:
    hero_specs = [(360, ""), (720, "2.0x"), (1080, "3.0x")]
    for size, folder in hero_specs:
        target = ROOT / "assets/images/welcome" / folder / "welcome_hero.png"
        save_png(create_welcome_hero(size), target)

    mark_specs = [(128, ""), (256, "2.0x"), (384, "3.0x")]
    for size, folder in mark_specs:
        target = ROOT / "assets/images/brand" / folder / "mira_mark.png"
        save_png(create_mark(size), target)


def generate_ios_assets(icon: Image.Image) -> None:
    appicon_dir = ROOT / "ios/Runner/Assets.xcassets/AppIcon.appiconset"
    ios_icon_sizes = {
        "Icon-App-20x20@1x.png": 20,
        "Icon-App-20x20@2x.png": 40,
        "Icon-App-20x20@3x.png": 60,
        "Icon-App-29x29@1x.png": 29,
        "Icon-App-29x29@2x.png": 58,
        "Icon-App-29x29@3x.png": 87,
        "Icon-App-40x40@1x.png": 40,
        "Icon-App-40x40@2x.png": 80,
        "Icon-App-40x40@3x.png": 120,
        "Icon-App-60x60@2x.png": 120,
        "Icon-App-60x60@3x.png": 180,
        "Icon-App-76x76@1x.png": 76,
        "Icon-App-76x76@2x.png": 152,
        "Icon-App-83.5x83.5@2x.png": 167,
        "Icon-App-1024x1024@1x.png": 1024,
    }
    for filename, size in ios_icon_sizes.items():
        save_png(resize_square(icon, size, opaque=True).convert("RGB"), appicon_dir / filename)

    launch_dir = ROOT / "ios/Runner/Assets.xcassets/LaunchImage.imageset"
    for filename, scale in {
        "LaunchImage.png": 1,
        "LaunchImage@2x.png": 2,
        "LaunchImage@3x.png": 3,
    }.items():
        canvas = Image.new("RGBA", (168 * scale, 185 * scale), (0, 0, 0, 0))
        mark = create_mark(132 * scale)
        canvas.alpha_composite(mark, ((canvas.width - mark.width) // 2, int(16 * scale)))
        save_png(canvas, launch_dir / filename)


def generate_android_assets(icon: Image.Image) -> None:
    densities = {
        "mdpi": 1.0,
        "hdpi": 1.5,
        "xhdpi": 2.0,
        "xxhdpi": 3.0,
        "xxxhdpi": 4.0,
    }
    for density, scale in densities.items():
        mipmap_dir = ROOT / f"android/app/src/main/res/mipmap-{density}"
        launcher_size = int(48 * scale)
        save_png(resize_square(icon, launcher_size, opaque=True), mipmap_dir / "ic_launcher.png")
        save_png(resize_square(icon, launcher_size, opaque=True), mipmap_dir / "ic_launcher_round.png")

        foreground_size = int(108 * scale)
        foreground = Image.new("RGBA", (foreground_size, foreground_size), (0, 0, 0, 0))
        mark_size = int(70 * scale)
        mark = create_mark(mark_size)
        foreground.alpha_composite(mark, ((foreground_size - mark_size) // 2, (foreground_size - mark_size) // 2))
        save_png(foreground, mipmap_dir / "ic_launcher_foreground.png")

        mark = create_mark(round(132 * scale))
        launch = Image.new("RGBA", (round(168 * scale), round(185 * scale)), (0, 0, 0, 0))
        launch.alpha_composite(mark, ((launch.width - mark.width) // 2, round(16 * scale)))
        save_png(launch, mipmap_dir / "launch_image.png")

    adaptive_dir = ROOT / "android/app/src/main/res/mipmap-anydpi-v26"
    ensure(adaptive_dir)
    adaptive_icon = """<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@drawable/ic_launcher_background" />
    <foreground android:drawable="@mipmap/ic_launcher_foreground" />
</adaptive-icon>
"""
    (adaptive_dir / "ic_launcher.xml").write_text(adaptive_icon, encoding="utf-8")
    (adaptive_dir / "ic_launcher_round.xml").write_text(adaptive_icon, encoding="utf-8")

    drawable_dir = ROOT / "android/app/src/main/res/drawable"
    ensure(drawable_dir)
    (drawable_dir / "ic_launcher_background.xml").write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android" android:shape="rectangle">
    <solid android:color="#E7F3F7" />
</shape>
""",
        encoding="utf-8",
    )


def main() -> None:
    icon = create_app_icon(1024)
    generate_flutter_assets()
    generate_ios_assets(icon)
    generate_android_assets(icon)

    manifest = {
        "generated": [
            "assets/images/welcome/welcome_hero.png",
            "assets/images/welcome/2.0x/welcome_hero.png",
            "assets/images/welcome/3.0x/welcome_hero.png",
            "assets/images/brand/mira_mark.png",
            "assets/images/brand/2.0x/mira_mark.png",
            "assets/images/brand/3.0x/mira_mark.png",
            "ios/Runner/Assets.xcassets/AppIcon.appiconset/*.png",
            "ios/Runner/Assets.xcassets/LaunchImage.imageset/LaunchImage*.png",
            "android/app/src/main/res/mipmap-*/ic_launcher*.png",
            "android/app/src/main/res/mipmap-*/launch_image.png",
        ]
    }
    (ROOT / "assets/images/mobile-image-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
