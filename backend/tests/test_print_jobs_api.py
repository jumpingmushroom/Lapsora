"""Delete semantics for PrusaLink print-history rows."""

import os
from datetime import UTC, datetime

import pytest

from app.models import PrintJob, Profile, Stream, Timelapse


def _stream(db):
    s = Stream(name="printer-cam", url="rtsp://x")
    db.add(s)
    db.commit()
    return s


def _finished_job(db, tmp_path, *, with_timelapse=True, status="finished"):
    s = _stream(db)
    tl_id = None
    if with_timelapse:
        video = tmp_path / "print.mp4"
        thumb = tmp_path / "print.jpg"
        video.write_bytes(b"video")
        thumb.write_bytes(b"thumb")
        p = Profile(stream_id=s.id, name="3D Print (auto)")
        db.add(p)
        db.commit()
        tl = Timelapse(
            profile_id=p.id,
            file_path=str(video), thumbnail_path=str(thumb), format="mp4",
            period_type="custom",
            period_start=datetime(2026, 8, 5, 14, 0, tzinfo=UTC),
            period_end=datetime(2026, 8, 5, 17, 0, tzinfo=UTC),
        )
        db.add(tl)
        db.commit()
        tl_id = tl.id
    pj = PrintJob(
        gcode_name="benchy.gcode", stream_id=s.id, status=status,
        started_at=datetime(2026, 8, 5, 14, 0, tzinfo=UTC),
        finished_at=datetime(2026, 8, 5, 17, 0, tzinfo=UTC) if status != "printing" else None,
        timelapse_id=tl_id,
    )
    db.add(pj)
    db.commit()
    return pj, tl_id


def test_delete_missing_job_is_404(client):
    resp = client.delete("/api/print-jobs/9999")
    assert resp.status_code == 404
    # A plain routing 404 (no DELETE route registered at all) returns
    # {"detail": "Not Found"}; only the handler's own `if not pj` branch
    # produces this message, so this pins down that the branch actually ran.
    assert resp.json()["detail"] == "Print job not found"


def test_cannot_delete_a_running_print(client, db, tmp_path):
    pj, _ = _finished_job(db, tmp_path, with_timelapse=False, status="printing")
    resp = client.delete(f"/api/print-jobs/{pj.id}")
    assert resp.status_code == 409
    assert db.get(PrintJob, pj.id) is not None


def test_delete_row_only_keeps_the_timelapse_and_its_files(client, db, tmp_path):
    pj, tl_id = _finished_job(db, tmp_path)
    video = db.get(Timelapse, tl_id).file_path

    assert client.delete(f"/api/print-jobs/{pj.id}").status_code == 204

    assert db.get(PrintJob, pj.id) is None
    assert db.get(Timelapse, tl_id) is not None
    assert os.path.isfile(video)


def test_delete_with_cascade_removes_timelapse_row_and_files(client, db, tmp_path):
    pj, tl_id = _finished_job(db, tmp_path)
    tl = db.get(Timelapse, tl_id)
    video, thumb = tl.file_path, tl.thumbnail_path

    resp = client.delete(f"/api/print-jobs/{pj.id}?delete_timelapse=true")

    assert resp.status_code == 204
    assert db.get(PrintJob, pj.id) is None
    assert db.get(Timelapse, tl_id) is None
    assert not os.path.isfile(video)
    assert not os.path.isfile(thumb)


def test_cascade_on_a_job_without_a_timelapse_is_a_no_op(client, db, tmp_path):
    pj, _ = _finished_job(db, tmp_path, with_timelapse=False)
    assert client.delete(f"/api/print-jobs/{pj.id}?delete_timelapse=true").status_code == 204
    assert db.get(PrintJob, pj.id) is None


def test_cancelled_prints_can_be_deleted(client, db, tmp_path):
    pj, _ = _finished_job(db, tmp_path, with_timelapse=False, status="cancelled")
    assert client.delete(f"/api/print-jobs/{pj.id}").status_code == 204
