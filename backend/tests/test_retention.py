from app.services.retention import get_storage_stats


def test_get_storage_stats_keys():
    stats = get_storage_stats()
    expected_keys = {
        "captures_count",
        "captures_size_bytes",
        "timelapses_count",
        "timelapses_size_bytes",
        "total_size_bytes",
        "disk_free_bytes",
        "disk_total_bytes",
    }
    assert set(stats.keys()) == expected_keys
