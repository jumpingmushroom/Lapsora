from app.services.timelapse import _resolve_fps, FPS_MIN, FPS_MAX


def test_fixed_mode_returns_fps_unchanged():
    assert _resolve_fps("fixed", 24, 20, 999) == 24


def test_target_duration_computes_fps_from_frame_count():
    # 400 frames over 20s target -> 20 fps
    assert _resolve_fps("target_duration", 24, 20, 400) == 20


def test_target_duration_clamps_to_min_for_short_prints():
    # 10 frames / 20s -> round(0.5)=0 -> clamp up to FPS_MIN
    assert _resolve_fps("target_duration", 24, 20, 10) == FPS_MIN


def test_target_duration_clamps_to_max_for_huge_prints():
    # 100000 frames / 20s -> 5000 -> clamp down to FPS_MAX
    assert _resolve_fps("target_duration", 24, 20, 100000) == FPS_MAX


def test_target_duration_guards_zero_target_and_frames():
    assert _resolve_fps("target_duration", 24, 0, 400) == 24
    assert _resolve_fps("target_duration", 24, 20, 0) == 24
