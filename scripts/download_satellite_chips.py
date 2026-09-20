"""Download two-season, 12-band Sentinel-2 L2A chips for statewide samples."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import time

import ee
import numpy as np
import pandas as pd
import requests

from kerala_land_lab.earth import initialize, load_env
from kerala_land_lab.satellite import geotiff_array, source_image


def download_one(row: dict, output: Path, patch_m: int, attempts: int = 4) -> dict:
    point_id = row["point_id"]
    destination = output / f"{point_id}.npz"
    if destination.exists():
        with np.load(destination) as archive:
            chips = archive["chips"]
            return {"point_id": point_id, "status": "existing", "path": str(destination), "valid_fraction": float(np.any(chips > 0, axis=(0, 1)).mean())}
    region = ee.Geometry.Point([float(row["lng"]), float(row["lat"])]).buffer(patch_m / 2).bounds()
    image = source_image(region)
    error = None
    for attempt in range(attempts):
        try:
            url = image.getDownloadURL({"name": point_id, "region": region, "dimensions": "224x224", "crs": "EPSG:32643", "format": "GEO_TIFF"})
            with requests.get(url, timeout=180, headers={"Connection": "close"}) as response:
                response.raise_for_status()
                content = response.content
            array = geotiff_array(content)
            if array.shape != (24, 224, 224):
                raise ValueError(f"Unexpected exported shape {array.shape}")
            chips = array.reshape(2, 12, 224, 224).astype(np.uint16)
            valid_fraction = float(np.any(chips > 0, axis=(0, 1)).mean())
            if valid_fraction < 0.70:
                raise ValueError(f"Only {valid_fraction:.1%} valid pixels")
            temporary = destination.with_suffix(".tmp.npz")
            np.savez_compressed(temporary, chips=chips, lat=np.float32(row["lat"]), lng=np.float32(row["lng"]), district=row["district"])
            os.replace(temporary, destination)
            return {"point_id": point_id, "status": "downloaded", "path": str(destination), "valid_fraction": valid_fraction}
        except Exception as exc:
            error = exc
            print(f"{point_id} attempt {attempt + 1}/{attempts}: {type(exc).__name__}: {exc}", flush=True)
            time.sleep(2 ** attempt)
    return {"point_id": point_id, "status": "error", "error": f"{type(error).__name__}: {error}"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data/processed/kerala_statewide_features.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/sentinel2_chips"))
    parser.add_argument("--patch-m", type=int, default=2240, help="Ground width represented by each 224px chip")
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Concurrent HTTPS downloads. Keep at 1 on macOS to avoid native OpenSSL crashes.",
    )
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    load_env(); initialize(); args.output.mkdir(parents=True, exist_ok=True)
    frame = pd.read_csv(args.data)
    if args.limit:
        frame = frame.head(args.limit)
    rows = [row._asdict() for row in frame.itertuples(index=False)]
    records = []

    def save_manifest():
        temporary = args.output / "manifest.tmp.json"
        temporary.write_text(json.dumps(records, indent=2) + "\n")
        os.replace(temporary, args.output / "manifest.json")

    if args.workers == 1:
        for number, row in enumerate(rows, 1):
            record = download_one(row, args.output, args.patch_m)
            records.append(record)
            print(f"[{number}/{len(rows)}] {record['point_id']} {record['status']}", flush=True)
            if number % 10 == 0:
                save_manifest()
    else:
        print("Warning: concurrent HTTPS can crash Python's native OpenSSL on macOS; use --workers 1 if this occurs.", flush=True)
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = [executor.submit(download_one, row, args.output, args.patch_m) for row in rows]
            for number, future in enumerate(as_completed(futures), 1):
                record = future.result()
                records.append(record)
                print(f"[{number}/{len(futures)}] {record['point_id']} {record['status']}", flush=True)
                if number % 10 == 0:
                    save_manifest()
    save_manifest()
    failures = [record for record in records if record["status"] == "error"]
    print(json.dumps({"requested": len(records), "complete": len(records) - len(failures), "failed": len(failures), "output": str(args.output)}, indent=2))
    if failures:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
