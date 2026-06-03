#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)/app/assets/weather_icons"
mkdir -p "$DIR"
BASE="https://raw.githubusercontent.com/basmilius/weather-icons/v2/production/fill/png/1024"
ICONS=(
  clear-day clear-night
  partly-cloudy-day partly-cloudy-night
  overcast-day overcast-night overcast
  fog-day fog-night
  drizzle rain sleet snow thunderstorms
)
for name in "${ICONS[@]}"; do
  echo "fetching $name"
  curl -fsSL "$BASE/$name.png" -o "$DIR/$name.png"
done
echo "done -> $DIR"
