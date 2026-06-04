import io

from PIL import Image

from app.services import logo_overlay as lo


def _make_logo(tmp_path, size=(200, 100), color=(255, 0, 0, 255)):
    path = tmp_path / "logo.png"
    Image.new("RGBA", size, color).save(path, "PNG")
    return str(path)


def test_compute_layout_none_when_missing(tmp_path):
    assert lo.compute_layout(None, 640, 360, 0.12, 0.8, "bottom-right") is None
    assert lo.compute_layout(str(tmp_path / "nope.png"), 640, 360, 0.12, 0.8, "bottom-right") is None


def test_compute_layout_resizes_preserving_aspect(tmp_path):
    path = _make_logo(tmp_path, size=(200, 100))  # 2:1
    layout = lo.compute_layout(path, 640, 360, 0.25, 1.0, "top-left")
    w, h = layout["logo"].size
    assert w == round(0.25 * 640)  # 160
    assert h == round(w * 100 / 200)  # aspect preserved -> 80


def test_compute_layout_anchors_each_corner(tmp_path):
    path = _make_logo(tmp_path, size=(100, 100))
    W, H = 640, 360
    margin = round(lo.MARGIN_PCT * W)
    layout = lo.compute_layout(path, W, H, 0.1, 1.0, "top-left")
    cw, ch = layout["logo"].size
    assert (layout["x"], layout["y"]) == (margin, margin)

    layout = lo.compute_layout(path, W, H, 0.1, 1.0, "top-right")
    assert (layout["x"], layout["y"]) == (W - cw - margin, margin)

    layout = lo.compute_layout(path, W, H, 0.1, 1.0, "bottom-left")
    assert (layout["x"], layout["y"]) == (margin, H - ch - margin)

    layout = lo.compute_layout(path, W, H, 0.1, 1.0, "bottom-right")
    assert (layout["x"], layout["y"]) == (W - cw - margin, H - ch - margin)


def test_opacity_scales_alpha(tmp_path):
    path = _make_logo(tmp_path, size=(100, 100), color=(255, 0, 0, 255))
    layout = lo.compute_layout(path, 640, 360, 0.1, 0.5, "top-left")
    alpha = layout["logo"].getchannel("A").getextrema()
    assert alpha[1] == 127  # 255 * 0.5 floored


def test_render_frame_modifies_frame(tmp_path):
    path = _make_logo(tmp_path, size=(100, 100), color=(0, 255, 0, 255))
    layout = lo.compute_layout(path, 640, 360, 0.2, 1.0, "top-left")
    img = Image.new("RGB", (640, 360), (10, 10, 10))
    before = list(img.getdata())
    lo.render_frame(img, layout)
    assert img.size == (640, 360)
    assert list(img.getdata()) != before


def test_upload_logo_accepts_image_and_rejects_garbage(client, monkeypatch, tmp_path):
    from app.routers import settings as settings_router

    monkeypatch.setattr(settings_router, "LOGO_DIR", tmp_path / "logos")
    monkeypatch.setattr(settings_router, "LOGO_PATH", tmp_path / "logos" / "logo.png")

    buf = io.BytesIO()
    Image.new("RGBA", (50, 50), (1, 2, 3, 255)).save(buf, "PNG")
    buf.seek(0)
    resp = client.post(
        "/api/settings/logo",
        files={"file": ("logo.png", buf, "image/png")},
    )
    assert resp.status_code == 200
    assert resp.json()["exists"] is True

    resp = client.post(
        "/api/settings/logo",
        files={"file": ("not.png", io.BytesIO(b"not an image"), "image/png")},
    )
    assert resp.status_code == 400
