# Drive-Time Poster

Prints a state-sized drive-time map: stepped color bands for every 30 minutes of driving from a start point,
with lakes and roadless land left uncolored. Bands stretch along interstates, squeeze through the Mackinac Bridge
and jump Lake Michigan on the car ferries. The output is a vector PDF sized for a poster (24 × 36 in by default)
plus a PNG preview.

## Setup

Python 3.11 or newer.

```bash
cd travel-time-poster
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Make a poster

```bash
python poster.py
```

The first run downloads the road data from Geofabrik (about 1.5 GB for Michigan and its neighbors) and reads it
into compact caches in `data/`. Expect 20–40 minutes and about 8 GB of free memory for that step. After that,
each poster takes a minute or two. Results go to `out/<start>-drive.pdf` and `.png`.

## Choosing the start point

Set `start` in `poster.toml`, or pass `--start` on the command line, which overrides the file:

```bash
python poster.py --start "Marquette, Michigan"            # a place name or street address
python poster.py --start 42.7325,-84.5555                 # latitude,longitude
python poster.py --start 42.7325,-84.5555 --label "Home"  # coordinates with a name for the poster
python poster.py --start "Detroit, MI" --start "Grand Rapids, MI"   # several: time to the nearest one
```

- Place names are looked up once on OpenStreetMap's Nominatim service and remembered in `data/places.json`.
- Coordinates are never sent anywhere. Use them for a home address you'd rather keep private. In Google Maps,
  right-click a spot to copy its coordinates.
- `--label` (or `start_label`) sets the name printed on the poster and in the title. For coordinates it defaults
  to the coordinates themselves.
- With several starts, each spot is colored by whichever start is closest in drive time, and each pin is labeled.

Changing the start only reruns the routing and drawing. The road data is already cached.

## Other settings (`poster.toml`)

| Setting | What it does |
| --- | --- |
| `region.focus` | State that frames the poster and gets full-strength color |
| `region.routing` | Road extracts to route on. Add `"ontario"` to allow routes through Canada |
| `travel.band_minutes`, `major_every_hours` | Band width and heavier contour lines |
| `travel.max_hours` | `"auto"` (until the far corner of the state) or a number |
| `travel.gap_km` | Land farther than this from any public road stays uncolored |
| `travel.local_speed_kmh` | Speed for the last stretch between mapped roads |
| `travel.ferries` | `"car"`, `"all"` or `"none"` |
| `poster.width_in`, `height_in` | Paper size in inches; type and line weights scale with it |
| `poster.title`, `subtitle` | `{start}`, `{focus}` and `{band}` are filled in |
| `poster.palette` | `ember`, `tide` or `heath` |
| `poster.outside_opacity` | How strongly neighboring states are colored (0 hides them) |
| `poster.png_dpi` | Set to 300 for a print-resolution PNG alongside the PDF |

Another state works the same way: set `focus = "Ohio"` and list the extracts around it in `routing`
(any Geofabrik path such as `"north-america/us/kentucky"`, or a local `.osm.pbf` file).

## How it works

1. **Roads**: OpenStreetMap ways are read from the Geofabrik extracts with pyosmium. Speeds come from the
   `maxspeed` tag, or from the road class when it's missing. `oneway` is respected, junctions add a few seconds,
   and car ferries add a boarding wait.
2. **Drive times**: one shortest-path search (Dijkstra) from the start covers every road junction at once.
3. **The space between roads**: a 500 m grid over the poster frame. Times flow off the roads into the grid at
   `local_speed_kmh`, but never off a motorway between exits, off a bridge, or across water. Land more than
   `gap_km` from any public road is left out.
4. **Drawing**: the grid is smoothed and contoured with matplotlib. The bands are clipped to the Census state
   outlines (1:500k), so shorelines are crisp, and Natural Earth supplies inland lakes and Ontario.

Speeds are free-flow estimates: no traffic, weather or stops.

## Credits

Roads © OpenStreetMap contributors, available under the Open Database License; the poster prints this credit.
State outlines: U.S. Census Bureau cartographic boundaries. Lakes and provinces: Natural Earth (public domain).
Typefaces: Barlow and Barlow Condensed (SIL Open Font License), downloaded on first run.
