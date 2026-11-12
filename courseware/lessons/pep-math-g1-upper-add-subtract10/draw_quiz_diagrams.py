"""Draw exact quantities for the bags, counters, and cake questions."""

from pathlib import Path

from PIL import Image, ImageDraw


BACKGROUND = "#f8f7ed"
BLUE = "#84c3dd"
OUTLINE = "#28668b"
CROSS = "#a2253b"
CAKES_BEFORE = tuple((x, y) for y in (111, 180) for x in (88, 153, 218, 283, 348))
CAKES_IN_BAG = ((750, 169), (816, 169))


def counter(draw, x, y, radius=25):
    draw.ellipse((x - radius, y - radius, x + radius, y + radius),
                 fill=BLUE, outline=OUTLINE, width=3)
    draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill="#e0f5fd")


def ten_grid(crossed):
    image = Image.new("RGB", (900, 272), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((30, 30, 870, 220), 24, fill="#edf3e9", outline="#a9bba7", width=4)
    for index in range(10):
        x, y = 174 + 112 * (index % 5), 78 + 94 * (index // 5)
        draw.rounded_rectangle((x - 41, y - 37, x + 41, y + 37), 13,
                               fill="#fffdf6", outline="#c2cdb7", width=3)
        counter(draw, x, y)
        if index < crossed:
            draw.line((x - 22, y + 23, x + 22, y - 23), fill=CROSS, width=5)
    return image


def equal_bags():
    image = Image.new("RGB", (900, 340), BACKGROUND)
    draw = ImageDraw.Draw(image)
    # An open bag reveals the five counters. The second bag moves away as a group.
    for x, y, color in ((290, 198, "#dab78e"), (610, 141, "#a6bda9")):
        draw.rounded_rectangle((x - 114, y - 62, x + 114, y + 104), 46,
                               fill=color, outline="#78664c", width=5)
        draw.ellipse((x - 101, y - 68, x + 101, y + 62),
                     fill="#fff8e8", outline="#78664c", width=4)
        draw.arc((x - 105, y - 68, x + 105, y + 66), 6, 173, fill="#9a7851", width=4)
        for dx, dy in ((-48, -22), (0, -22), (48, -22), (-24, 23), (24, 23)):
            counter(draw, x + dx, y + dy, 19)
        draw.arc((x + 90, y + 36, x + 136, y + 75), 310, 230, fill="#78664c", width=5)
    draw.line((754, 210, 754, 106), fill="#496754", width=8)
    draw.polygon(((731, 111), (754, 82), (777, 111)), fill="#496754")
    return image


def round_cakes():
    image = Image.new("RGB", (900, 290), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((25, 46, 402, 246), 28, fill="#d6e8e5", outline="#649e99", width=6)
    draw.rounded_rectangle((42, 63, 385, 228), 20, fill="#e9f3ee", outline="#abcac2", width=4)
    # The large arrow goes from the starting plate to the later scene.
    draw.line((425, 145, 486, 145), fill="#42645e", width=8)
    draw.polygon(((480, 124), (508, 145), (480, 166)), fill="#42645e")
    # A cover conceals the plate's remaining quantity. Only the bag is visible.
    draw.ellipse((530, 196, 691, 233), fill="#d6e8e5", outline="#649e99", width=4)
    draw.rounded_rectangle((588, 91, 631, 120), 13, fill="#78a49e", outline="#4a807b", width=3)
    draw.rounded_rectangle((535, 111, 686, 212), 40, fill="#a3c5c0", outline="#4a807b", width=4)
    draw.arc((592, 129, 632, 165), 180, 423, fill="#315f5a", width=6)
    draw.line((621, 160, 612, 175, 612, 180), fill="#315f5a", width=6)
    draw.ellipse((608, 185, 616, 193), fill="#315f5a")
    draw.polygon(((710, 61), (852, 61), (869, 247), (695, 247)), fill="#e7be85")
    draw.line(((710, 61), (852, 61), (869, 247), (695, 247), (710, 61)), fill="#987248", width=4)
    draw.line((709, 87, 854, 87), fill="#987248", width=5)
    draw.rounded_rectangle((720, 128, 846, 211), 17, fill="#fff6dd", outline="#ad8555", width=3)
    for x, y in (*CAKES_BEFORE, *CAKES_IN_BAG):
        draw.ellipse((x - 24, y - 24, x + 24, y + 24),
                     fill="#edb162", outline="#ac6e32", width=3)
        for dx, dy in ((-9, -8), (7, -10), (-3, 5), (9, 10)):
            draw.ellipse((x + dx - 2, y + dy - 2, x + dx + 2, y + dy + 2), fill="#b86c3d")
    return image


def render():
    assets = Path(__file__).resolve().parent / "assets"
    equal_bags().save(assets / "quiz-equal-bags.png")
    round_cakes().save(assets / "quiz-round-cakes.png")
    for key, count in (("quiz-ten", 0), ("quiz-remove-one", 1),
                       ("quiz-remove-eight", 8), ("quiz-remove-nine", 9)):
        ten_grid(count).save(assets / (key + ".png"))


if __name__ == "__main__":
    render()
