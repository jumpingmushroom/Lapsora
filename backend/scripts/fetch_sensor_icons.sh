#!/usr/bin/env bash
# Downloads curated multicolor sensor icons (Twemoji, CC-BY 4.0) into
# app/assets/sensor_icons/. Mirrors backend/scripts/fetch_weather_icons.sh.
set -euo pipefail
DEST="$(cd "$(dirname "$0")/.." && pwd)/app/assets/sensor_icons"
mkdir -p "$DEST"
BASE="https://raw.githubusercontent.com/jdecked/twemoji/main/assets/72x72"

declare -A ICONS=(
  [thermometer]=1f321
  [humidity]=1f4a7
  [water]=1f6b0
  [wind]=1f4a8
  [power]=26a1
  [light]=1f4a1
  [battery]=1f50b
  [gauge]=23f1
)

for key in "${!ICONS[@]}"; do
  curl -fsSL "$BASE/${ICONS[$key]}.png" -o "$DEST/$key.png"
  echo "fetched $key"
done
echo "Done. $(ls -1 "$DEST" | wc -l) icons in $DEST"
