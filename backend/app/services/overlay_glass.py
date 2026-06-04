"""Shared frosted-glass card primitive used by frame overlays."""

from PIL import Image, ImageDraw, ImageFilter

RADIUS = 16


def draw_glass_card(base: Image.Image, x: int, y: int, cw: int, ch: int,
                    radius: int = RADIUS) -> Image.Image:
    """Paste a frosted-glass rounded card onto `base` (an RGBA image) at (x, y)
    with size (cw, ch), then add a translucent highlight border.

    Returns the image to continue drawing on. The border is drawn on its own
    RGBA layer and alpha-composited — drawing it directly then converting to RGB
    would drop the alpha and render a harsh solid-white outline.
    """
    region = base.crop((x, y, x + cw, y + ch)).filter(ImageFilter.GaussianBlur(8))
    tint = Image.new("RGBA", (cw, ch), (20, 22, 28, 150))
    card = Image.alpha_composite(region, tint)
    mask = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, cw - 1, ch - 1], radius=radius, fill=255)
    base.paste(card, (x, y), mask)

    border = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(border).rounded_rectangle(
        [x, y, x + cw - 1, y + ch - 1], radius=radius,
        outline=(255, 255, 255, 70), width=1,
    )
    return Image.alpha_composite(base, border)
