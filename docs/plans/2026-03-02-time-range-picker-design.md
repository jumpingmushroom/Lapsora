# Time Range Picker Redesign

## Problem

The Generate Timelapse dialog uses `<input type="datetime-local">` for start/end dates. Firefox renders this without a time picker, making it impossible to select a time range. Additionally, there are no quick-select presets, requiring users to manually type dates for common cases like "last 24 hours."

## Design

Replace the two `datetime-local` inputs with a preset chip row + split date/time inputs for custom ranges.

### Preset Chips

A horizontally wrapping row of clickable pills:
- Last 24h (default)
- Today
- Yesterday
- Last 7d
- Last 30d
- This week
- Last week
- Custom

Clicking a preset highlights it and auto-computes `period_start`/`period_end`. No date/time inputs are shown for presets.

### Custom Range

When "Custom" chip is active, show split inputs:
```
Start:  [ date input ] [ time input ]
End:    [ date input ] [ time input ]
```

Uses `<input type="date">` + `<input type="time">` (both cross-browser compatible) instead of `<input type="datetime-local">`.

### Preset Computation (Client-Side)

| Preset | Start | End |
|--------|-------|-----|
| Last 24h | now - 24h | now |
| Today | midnight today | now |
| Yesterday | midnight yesterday | midnight today |
| Last 7d | now - 7d | now |
| Last 30d | now - 30d | now |
| This week | Monday 00:00 | now |
| Last week | prev Monday 00:00 | prev Sunday 23:59 |

### State

- `selectedPreset`: string, default `'last24h'`
- `period_start`/`period_end`: computed from preset or set manually in custom mode

### Files Modified

- `frontend/src/lib/components/GenerateDialog.svelte` (only file)

### No Backend Changes

The backend already accepts `period_start`/`period_end` as custom date strings.
