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
