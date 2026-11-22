# Drive-Time Poster

Prints a drive-time map: stepped color bands for every few minutes of driving from a start point, with lakes and
roadless land left uncolored. It works for a whole state, a single county, any named place, or just the area
around the people and places you care about, which are marked with their drive times. Bands stretch along
interstates and squeeze through bridges such as the Mackinac Bridge. Ferries are never used. The output is a
vector PDF sized for a poster (24 × 36 in by default) plus a PNG preview.

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

The first run downloads road data from Geofabrik for the states the map needs (about 1.5 GB for all of
Michigan and its neighbors; one state for a county view) and reads it into compact caches in `data/`. Expect
20–40 minutes and about 8 GB of free memory for a statewide first run. After that, each poster takes a minute
or two. Results go to `out/<start>-<area>.pdf` and `.png`.

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

## Choosing what the map shows

Set `area` under `[view]`, or pass `--view`:

```bash
python poster.py --view "Michigan"                  # a state (or "MI")
python poster.py --view "Kent County, Michigan"     # a county
python poster.py --view "Grand Rapids, Michigan"    # any place: its outline on OpenStreetMap, at least 20 km across
python poster.py --view landmarks                   # fit the start and every landmark
```

A box works in the settings file: `area = [42.7, -86.0, 43.3, -85.2]` (south, west, north, east).

A state or county is drawn at full strength with its surroundings faded and outlined. The other kinds color
everything in the frame. The grid size, band width, road detail and town labels all scale with the area: a
county gets 5-minute bands, a 40 m grid and local roads; a state gets 30-minute bands and interstates.
When the start is outside the view, the colors begin at the nearest time on the map, so the whole palette is used.

## Landmarks

Mark family, friends or favorite places. Each gets a diamond on the map with its drive time beside it, and a
list under the legend sorted by time:

```toml
[[landmarks]]
name = "Grandma's"
at = "Holland, Michigan"

[[landmarks]]
name = "The cabin"
at = [44.9512, -85.2047]
```

Or add them from the command line (these add to the ones in the file; `--no-landmarks` drops those):

```bash
python poster.py --landmark "Grandma's=Holland, MI" --landmark "Cabin=44.9512,-85.2047" --view landmarks
```

As with start points, coordinates are never sent anywhere.

## Other settings (`poster.toml`)

| Setting | What it does |
| --- | --- |
| `view.area`, `view.margin_km` | What the map shows, and the space around it |
| `routing.regions` | `"auto"`, or a list of states, Geofabrik paths or local `.osm.pbf` files |
| `routing.include_canada` | Allow routes through Canada |
| `travel.band_minutes`, `major_every_minutes` | Band width and heavier contour lines (`"auto"` or minutes) |
| `travel.max_hours` | `"auto"` (farthest point on the map) or a number |
| `travel.gap_km` | Land farther than this from any public road stays uncolored |
| `travel.local_speed_kmh` | Speed for the last stretch between mapped roads |
| `poster.width_in`, `height_in` | Paper size in inches; type and line weights scale with it |
| `poster.title`, `subtitle` | `{start}`, `{view}` and `{band}` are filled in |
| `poster.palette` | `ember`, `tide` or `heath` |
| `poster.outside_opacity` | How strongly the surroundings of a state or county are colored (0 hides them) |
| `poster.draw_roads` | `"auto"`, a list such as `["motorway", "primary"]`, or `false` |
| `poster.png_dpi` | Set to 300 for a print-resolution PNG alongside the PDF |

Settings files from the first version (with a `[region]` section) still work.

## How it works

1. **Roads**: OpenStreetMap ways are read from the Geofabrik extracts with pyosmium. Speeds come from the
   `maxspeed` tag, or from the road class when it's missing. `oneway` is respected and junctions add a few
   seconds. Ferries are skipped.
2. **Drive times**: one shortest-path search (Dijkstra) from the start covers every road junction at once.
3. **The space between roads**: a grid over the poster frame (about 1,600 cells across). Times flow off the roads into the grid at
   `local_speed_kmh`, but never off a motorway between exits, off a bridge, or across water. Land more than
   `gap_km` from any public road is left out.
4. **Drawing**: the grid is smoothed and contoured with matplotlib. The bands are clipped to the Census state
   outlines (1:500k), so shorelines are crisp, and Natural Earth supplies inland lakes and Ontario.

Speeds are free-flow estimates: no traffic, weather or stops. Inland lakes come from Natural Earth, which only
has the larger ones, so on a county map small lakes are not cut out.

## Credits

Roads © OpenStreetMap contributors, available under the Open Database License; the poster prints this credit.
State and county outlines: U.S. Census Bureau cartographic boundaries. Lakes and provinces: Natural Earth (public domain).
Typefaces: Barlow and Barlow Condensed (SIL Open Font License), downloaded on first run.
