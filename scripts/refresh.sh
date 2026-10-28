#!/usr/bin/env bash
# Обновление календаря: WB API -> data/*.json -> index.html
# Ключи берутся из переменных INHOMEKA_WB_TOKEN и GROTEK_WB_TOKEN (в репозитории их нет).
set -euo pipefail
cd "$(dirname "$0")/.."
W=$(mktemp -d)
umask 077
printf 'INHOMEKA_WB_TOKEN=%s\nGROTEK_WB_TOKEN=%s\n' "$INHOMEKA_WB_TOKEN" "$GROTEK_WB_TOKEN" > "$W/.env"
python3 -u scripts/fetch_supplies.py --env "$W/.env" --out "$W/data.json" --date-from 2026-10-01 \
  --prev-supplies data/supplies.json --prev-items data/items.json
rm -f "$W/.env"
( cd "$W" && python3 "$OLDPWD/scripts/build_datasets.py" data.json )
cp "$W/supplies.json" "$W/items.json" data/
python3 scripts/make_html.py scripts/page.html data/supplies.json data/items.json index.html
echo "$W"
