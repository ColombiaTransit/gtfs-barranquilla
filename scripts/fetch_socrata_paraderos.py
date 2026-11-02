#!/usr/bin/env python3
"""Download and audit Transmetro Socrata route-stop sequences (no third-party deps).

This is supplementary research data; it does not overwrite the existing
KML-derived GTFS stops or shapes.
"""
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

ENDPOINT = "https://www.datos.gov.co/resource/hxy3-94yh.json"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, help="Use a previously downloaded JSON snapshot")
    p.add_argument("--output", type=Path, default=Path("data/research/socrata"))
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.input:
        records = json.loads(args.input.read_text(encoding="utf-8"))
    else:
        url = ENDPOINT + "?" + urlencode({"$limit": 50000, "$order": "nombre_ruta,secuencia_parada"})
        with urlopen(url, timeout=45) as response:
            records = json.load(response)
    if not isinstance(records, list):
        raise ValueError("Expected a list of Socrata rows")
    (args.output / "paraderos_raw.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    rows = []
    for rec in records:
        try:
            seq = int(rec["secuencia_parada"])
            lat = float(rec["coordenada_y"])
            lon = float(rec["coordenada_x"])
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError(f"Invalid stop row: {rec}") from exc
        rows.append({
            "route_label": rec["nombre_ruta"],
            "stop_name": rec["nombre_parada"],
            "stop_sequence": seq,
            "stop_lat": lat,
            "stop_lon": lon,
            "schedule_reference": "A5-3" if rec["nombre_ruta"].startswith("A5-3 ") else "",
        })
    rows.sort(key=lambda r: (r["route_label"], r["stop_sequence"]))
    with (args.output / "route_stops.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else [
            "route_label", "stop_name", "stop_sequence", "stop_lat", "stop_lon", "schedule_reference"
        ])
        writer.writeheader()
        writer.writerows(rows)
    by_route = defaultdict(list)
    by_name = defaultdict(set)
    for r in rows:
        by_route[r["route_label"]].append(r["stop_sequence"])
        by_name[r["stop_name"]].add((r["stop_lat"], r["stop_lon"]))
    anomalies = {name: seq for name, seq in by_route.items()
                 if sorted(seq) != list(range(1, len(seq) + 1))}
    report = {
        "rows": len(rows),
        "route_labels": len(by_route),
        "unique_stop_names": len(by_name),
        "unique_coordinate_pairs": len({(r["stop_lat"], r["stop_lon"]) for r in rows}),
        "names_with_multiple_coordinate_pairs": {
            name: len(coords) for name, coords in sorted(by_name.items())
            if len(coords) > 1
        },
        "sequence_anomalies": anomalies,
        "route_counts": dict(sorted(Counter(r["route_label"] for r in rows).items())),
    }
    (args.output / "quality_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in report.items() if k not in
                      ("route_counts", "names_with_multiple_coordinate_pairs")}, indent=2))


if __name__ == "__main__":
    main()
