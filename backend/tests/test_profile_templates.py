from unittest.mock import patch

from app.models import Profile, ProfileTemplate, Stream


def test_profile_render_columns_default_to_fixed(db):
    s = Stream(name="s", source_type="rtsp", url="rtsp://x")
    db.add(s)
    db.commit()
    p = Profile(stream_id=s.id, name="p")
    db.add(p)
    db.commit()
    db.refresh(p)
    assert p.fps_mode == "fixed"
    assert p.render_target_seconds == 20
    assert p.render_fps == 24
    assert p.render_format == "mp4"


def test_template_render_columns_default_to_fixed(db):
    t = ProfileTemplate(name="t", category="Custom")
    db.add(t)
    db.commit()
    db.refresh(t)
    assert t.fps_mode == "fixed"
    assert t.render_target_seconds == 20
    assert t.render_fps == 24
    assert t.render_format == "mp4"


def test_create_template_accepts_render_config(client):
    body = {
        "name": "Print Preset", "category": "3D Printing",
        "interval_seconds": 10, "quality": 90,
        "fps_mode": "target_duration", "render_target_seconds": 20,
        "render_fps": 24, "render_format": "mp4",
    }
    r = client.post("/api/profile-templates/", json=body)
    assert r.status_code == 201, r.text
    got = r.json()
    assert got["fps_mode"] == "target_duration"
    assert got["render_target_seconds"] == 20


def test_apply_template_stamps_render_config_onto_profile(client):
    sid = client.post("/api/streams/", json={"name": "cam", "url": "rtsp://x"}).json()["id"]
    tpl = client.post("/api/profile-templates/", json={
        "name": "P", "category": "3D Printing", "interval_seconds": 10, "quality": 90,
        "fps_mode": "target_duration", "render_target_seconds": 15, "render_fps": 30, "render_format": "mp4",
    }).json()
    with patch("app.routers.profile_templates.scheduler"):
        r = client.post(f"/api/profile-templates/{tpl['id']}/apply", json={"stream_id": sid})
    assert r.status_code == 201, r.text
    prof = r.json()
    assert prof["fps_mode"] == "target_duration"
    assert prof["render_target_seconds"] == 15
    assert prof["render_fps"] == 30
    assert prof["render_format"] == "mp4"
