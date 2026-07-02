"""PrintJob model + print-jobs API coverage."""

from datetime import UTC, datetime

from app.models import PrintJob, Profile, Stream, Timelapse


def _mk_stream(db) -> Stream:
    s = Stream(name="printer-cam", url="rtsp://x")
    db.add(s)
    db.commit()
    return s


def test_print_job_model_roundtrip(db):
    s = _mk_stream(db)
    pj = PrintJob(
        prusalink_job_id=42,
        gcode_name="benchy.gcode",
        stream_id=s.id,
        status="printing",
        started_at=datetime.now(UTC),
        estimated_seconds=3600.0,
        interval_seconds=7,
    )
    db.add(pj)
    db.commit()
    got = db.query(PrintJob).filter(PrintJob.status == "printing").one()
    assert got.gcode_name == "benchy.gcode"
    assert got.timelapse_id is None
    assert got.finished_at is None


def test_profile_managed_by_and_timelapse_name_columns(db):
    s = _mk_stream(db)
    p = Profile(stream_id=s.id, name="3D Print (auto)", managed_by="prusalink", enabled=False)
    db.add(p)
    db.commit()
    tl = Timelapse(profile_id=p.id, file_path="x.mp4", name="benchy.gcode")
    db.add(tl)
    db.commit()
    assert db.get(Profile, p.id).managed_by == "prusalink"
    assert db.get(Timelapse, tl.id).name == "benchy.gcode"


def test_link_print_job_sets_timelapse_id(db):
    from app.services.timelapse import _link_print_job
    s = _mk_stream(db)
    p = Profile(stream_id=s.id, name="x")
    db.add(p)
    db.commit()
    tl = Timelapse(profile_id=p.id, file_path="x.mp4")
    pj = PrintJob(stream_id=s.id, status="finished", started_at=datetime.now(UTC))
    db.add_all([tl, pj])
    db.commit()
    _link_print_job(db, pj.id, tl.id)
    assert db.get(PrintJob, pj.id).timelapse_id == tl.id
    # unknown print_job_id is a no-op, not an error
    _link_print_job(db, 99999, tl.id)


def test_list_print_jobs_newest_first(client, db):
    s = _mk_stream(db)
    for n in ("a.gcode", "b.gcode"):
        db.add(PrintJob(stream_id=s.id, gcode_name=n, status="finished",
                        started_at=datetime.now(UTC)))
    db.commit()
    got = client.get("/api/print-jobs").json()
    assert [j["gcode_name"] for j in got] == ["b.gcode", "a.gcode"]
    assert {"id", "status", "started_at", "timelapse_id"} <= set(got[0])
