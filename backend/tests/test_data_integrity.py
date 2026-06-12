"""Data-integrity guarantees: FK cascade enforcement, media-file cleanup on
delete, and schema validation that was previously bypassable.
"""

import os

from app.config import settings
from app.models import Capture, Profile, Stream, Timelapse


def _seed_stream_profile(db):
    s = Stream(name="S", url="enc")
    db.add(s)
    db.commit()
    db.refresh(s)
    p = Profile(stream_id=s.id, name="P")
    db.add(p)
    db.commit()
    db.refresh(p)
    return s, p


def test_fk_cascade_removes_child_rows_on_stream_delete(client, db):
    """With PRAGMA foreign_keys=ON + passive_deletes, deleting a stream must
    cascade to profiles, captures and timelapses at the DB level."""
    s, p = _seed_stream_profile(db)
    db.add(Capture(profile_id=p.id, file_path="captures/x.jpg"))
    db.add(Timelapse(profile_id=p.id, file_path="timelapses/v.mp4"))
    db.commit()
    cap_id = db.query(Capture).first().id
    tl_id = db.query(Timelapse).first().id
    prof_id = p.id

    resp = client.delete(f"/api/streams/{s.id}")
    assert resp.status_code == 204

    db.expire_all()
    assert db.get(Profile, prof_id) is None
    assert db.get(Capture, cap_id) is None
    assert db.get(Timelapse, tl_id) is None


def test_delete_profile_removes_media_dirs(client, db):
    s, p = _seed_stream_profile(db)
    cap_dir = os.path.join(settings.DATA_DIR, "captures", str(s.id), str(p.id))
    tl_dir = os.path.join(settings.DATA_DIR, "timelapses", str(p.id))
    os.makedirs(cap_dir, exist_ok=True)
    os.makedirs(tl_dir, exist_ok=True)
    open(os.path.join(cap_dir, "f.jpg"), "w").close()
    open(os.path.join(tl_dir, "v.mp4"), "w").close()

    resp = client.delete(f"/api/profiles/{p.id}")
    assert resp.status_code == 204
    assert not os.path.isdir(cap_dir)
    assert not os.path.isdir(tl_dir)


def test_delete_stream_removes_media_dirs(client, db):
    s, p = _seed_stream_profile(db)
    cap_dir = os.path.join(settings.DATA_DIR, "captures", str(s.id))
    tl_dir = os.path.join(settings.DATA_DIR, "timelapses", str(p.id))
    os.makedirs(os.path.join(cap_dir, str(p.id)), exist_ok=True)
    os.makedirs(tl_dir, exist_ok=True)
    open(os.path.join(tl_dir, "v.mp4"), "w").close()

    resp = client.delete(f"/api/streams/{s.id}")
    assert resp.status_code == 204
    assert not os.path.isdir(cap_dir)
    assert not os.path.isdir(tl_dir)


def test_template_rejects_zero_interval(client):
    resp = client.post(
        "/api/profile-templates/",
        json={"name": "bad", "category": "c", "interval_seconds": 0},
    )
    assert resp.status_code == 422


def test_schedule_rejects_zero_fps(client, db):
    _s, p = _seed_stream_profile(db)
    resp = client.post(
        "/api/timelapse-schedules/",
        json={"profile_id": p.id, "cron_expression": "0 0 * * *", "fps": 0},
    )
    assert resp.status_code == 422
