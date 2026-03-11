"""
Extract each band from rainfall_4km_multiband.tif into a separate COG.
Band number maps to date: band 1 -> 2025-12-01, band 2 -> 2025-12-02, etc.

Also stacks the per-day COGs back into a VRT (rainfall_4km_multiband.vrt).

NOTE on positive NS resolution:
  The source TIF uses a polar stereographic CRS whose geotransform has a
  positive Y resolution (+4762.5), meaning rows are ordered bottom-to-top.
  Both `gdal raster select` and `gdalbuildvrt` / `gdal raster stack` reject
  files with positive NS resolution. `gdalwarp` correctly handles this by
  flipping the row order and updating the geotransform origin to the
  top-left corner, producing a standard negative-Y-resolution COG.
"""

import json
import subprocess
from datetime import date, timedelta

INPUT = "rainfall_4km_multiband.tif"
VRT_OUTPUT = "rainfall_4km_multiband.vrt"
START_DATE = date(2025, 12, 1)
NUM_BANDS = 20

outputs = []
for band in range(1, NUM_BANDS + 1):
    d = START_DATE + timedelta(days=band - 1)
    output = f"rainfall_4km_{d.strftime('%Y%m%d')}.tif"
    print(f"Band {band} -> {output}")

    # Approach 1 (abandoned): `gdal raster select` preserves the source
    # positive NS resolution, so the output COGs are rejected by both
    # `gdal raster stack` and `gdalbuildvrt` when building the VRT.
    # subprocess.run(
    #     [
    #         "gdal", "raster", "select",
    #         "--of", "COG",
    #         "--co", "COMPRESS=DEFLATE",
    #         "--overwrite",
    #         "-b", str(band),
    #         INPUT,
    #         output,
    #     ],
    #     check=True,
    # )

    # Approach 2: `gdalwarp` re-grids to the same CRS, which flips the row
    # order and moves the geotransform origin to the top-left, yielding a
    # standard negative-Y-resolution COG compatible with gdalbuildvrt.
    subprocess.run(
        [
            "gdalwarp",
            "-of", "COG",
            "-co", "COMPRESS=DEFLATE",
            "-overwrite",
            "-b", str(band),
            INPUT,
            output,
        ],
        check=True,
    )
    outputs.append(output)

print(f"Stacking {len(outputs)} files -> {VRT_OUTPUT}")
# gdal raster stack does not support positive NS resolution (polar stereographic CRS)
# subprocess.run(
#     [
#         "gdal", "raster", "stack",
#         "--of", "VRT",
#         "--overwrite",
#         *outputs,
#         VRT_OUTPUT,
#     ],
#     check=True,
# )
subprocess.run(
    ["gdalbuildvrt", "-separate", "-overwrite", VRT_OUTPUT, *outputs],
    check=True,
)

# ── Verify pixel values match between source TIF and VRT ─────────────────────
print("Verifying pixel values match between source and VRT...")
CHECK_LON, CHECK_LAT = -120.720280, 48.346940

def pixel_values(path, lon, lat):
    result = subprocess.run(
        ["gdal", "raster", "pixel-info", "--position-crs=WGS84", path, str(lon), str(lat)],
        capture_output=True, text=True, check=True,
    )
    features = json.loads(result.stdout)["features"]
    return {b["band_number"]: b["raw_value"] for b in features[0]["properties"]["bands"]}

src_vals = pixel_values(INPUT, CHECK_LON, CHECK_LAT)
vrt_vals = pixel_values(VRT_OUTPUT, CHECK_LON, CHECK_LAT)

mismatches = [
    (band, src_vals[band], vrt_vals[band])
    for band in src_vals
    if src_vals[band] != vrt_vals[band]
]
if mismatches:
    for band, src, vrt in mismatches:
        print(f"  MISMATCH band {band}: source={src}  vrt={vrt}")
    raise SystemExit("Verification failed: VRT values differ from source TIF.")

print(f"  OK — all {len(src_vals)} bands match at ({CHECK_LON}, {CHECK_LAT})")
print("Done.")
