# Assets — where things live and where YOU drop files

```
assets/
  inbox/            <- DROP ZONE: raw footage/photos you shot (any name, any format).
                       Tell Claude "check inbox" — clips get vetted, plates blurred,
                       cut into segments, and filed under cars/<car>/own/.
  music/            <- DROP ZONE: background tracks (mp3/wav) from the YouTube
                       Audio Library. The renderer auto-picks from here
                       (alphabetical) unless --music <path> overrides it.
  cars/<car-slug>/
    own/            <- vetted segments cut from YOUR footage (pool_*.mp4)
    images/         <- vetted CC/press stills + detail crops (+ attributions.json)
    press/          <- official manufacturer media-kit files (credit in description)
  stock/            <- hand-vetted Pexels b-roll (global, topic-tagged filenames)
  stock_archive/    <- rejected/parked stock (never used in renders)
```

Rules encoded in the pipeline:
- every asset is VIEWED before use (brand, plate, generation, quality)
- number plates blurred or excluded; no third-party watermarks, ever
- an asset appears at most once per video; look-alike shots get spaced
- filenames describe content (e.g. pool_03_side2.mp4, roxx_press_grille_detail.jpg)
  because the shot-matcher reads names to align visuals with the script
