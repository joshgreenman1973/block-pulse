# Block Pulse

How alive is a NYC block, by hour? An experiment using the public NYC DOT traffic-camera
feed (webcams.nyctmc.org) + a vision model to score street-level activity 0–10.

**Important caveat:** these are *traffic* cameras, not street-life cameras. They cover
roughly **1% of the city's ~6,300 street-miles** and ~7% of signalized intersections,
heavily concentrated in Manhattan. Of 962 cameras, ~744 sit on neighborhood streets and
only **~390 can actually see a sidewalk**; 87 of the 99 best are in Manhattan. The Bronx
and Staten Island are almost entirely highway and effectively unwatched here. This is
"the rhythm of the blocks the city happens to watch," not "the rhythm of New York."

## How it works
- `score_now.py` pulls the 99 "pristine" sidewalk cameras and scores each frame's
  pedestrian activity with Claude Haiku. Reads the API key from `ANTHROPIC_API_KEY`
  (env var on CI, macOS Keychain locally).
- A GitHub Action (`.github/workflows/capture.yml`) runs it hourly and commits:
  - `data/activity_log.csv` — full grain (every camera, every hour)
  - `data/latest.json` — most-recent read per camera (drives the map)
  - `data/timeline.json` — hourly citywide means (drives the rhythm chart)
- `index.html` is a static Leaflet map served by GitHub Pages.

## Data resolution / privacy
Frames are 352×240 — only aggregate activity is detectable, no individuals identifiable.
