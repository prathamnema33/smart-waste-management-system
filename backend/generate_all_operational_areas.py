import json
import math
from pathlib import Path

from shapely.geometry import shape, box, mapping
from shapely.ops import unary_union
from shapely.validation import explain_validity


INPUT = Path("geo/Bhopal_wards_clean.geojson")
OUTPUT = Path("geo/operational_areas_all.geojson")


def make_valid_polygon(geometry):
    """
    Make a geometry valid while keeping the actual ward boundary.
    """
    if not geometry.is_valid:
        geometry = geometry.buffer(0)

    if geometry.geom_type == "MultiPolygon":
        # Keep all pieces; don't arbitrarily discard geometry.
        return geometry

    return geometry


def choose_area_count(polygon):
    """
    Estimate subdivision count from polygon size.

    We intentionally keep this moderate because these are
    operational waste-management areas, not official localities.
    """
    minx, miny, maxx, maxy = polygon.bounds

    width = maxx - minx
    height = maxy - miny

    # Approximate geographic extent.
    extent = max(width, height)

    if extent < 0.008:
        return 2
    elif extent < 0.015:
        return 3
    elif extent < 0.025:
        return 4
    elif extent < 0.040:
        return 5
    else:
        return 6


def split_polygon(polygon, n):
    """
    Split polygon using a grid and clip every cell against
    the real ward polygon.

    This guarantees operational areas remain inside the ward.
    """
    minx, miny, maxx, maxy = polygon.bounds

    width = maxx - minx
    height = maxy - miny

    # Choose a grid close to square.
    cols = max(1, math.ceil(math.sqrt(n)))
    rows = max(1, math.ceil(n / cols))

    cell_width = width / cols
    cell_height = height / rows

    pieces = []

    for row in range(rows):
        for col in range(cols):
            x1 = minx + col * cell_width
            y1 = miny + row * cell_height
            x2 = minx + (col + 1) * cell_width
            y2 = miny + (row + 1) * cell_height

            cell = box(x1, y1, x2, y2)
            clipped = polygon.intersection(cell)

            if clipped.is_empty:
                continue

            if clipped.geom_type in ("Polygon", "MultiPolygon"):
                pieces.append(clipped)

    # We may get fewer pieces than requested because some grid
    # cells don't intersect the ward.
    pieces.sort(key=lambda g: g.area, reverse=True)

    return pieces[:n]


def process_ward(feature):
    properties = feature.get("properties", {})
    geometry_data = feature.get("geometry")

    ward_number = str(properties.get("Ward_Number", "")).strip()
    ward_name = properties.get("Name", "Unknown")
    zone = properties.get("zone")
    population = properties.get("population")

    if not ward_number or not geometry_data:
        return []

    polygon = shape(geometry_data)
    polygon = make_valid_polygon(polygon)

    if polygon.is_empty:
        print(f"SKIP Ward {ward_number}: empty geometry")
        return []

    area_count = choose_area_count(polygon)

    pieces = split_polygon(polygon, area_count)

    results = []

    for index, piece in enumerate(pieces, start=1):

        if not piece.is_valid:
            piece = piece.buffer(0)

        if piece.is_empty:
            continue

        centroid = piece.centroid

        results.append({
            "type": "Feature",
            "properties": {
                "ward_number": ward_number,
                "ward_name": ward_name,
                "zone": zone,
                "population": population,
                "area_number": index,
                "area_name": (
                    f"{ward_name} - Operational Area {index}"
                ),
                "locality_name": ward_name,
            },
            "geometry": mapping(piece),
        })

    return results


def main():

    print("Reading:", INPUT)

    with open(INPUT, "r", encoding="utf-8") as f:
        data = json.load(f)

    features = data["features"]

    # Ward 76 occurs twice in the source file.
    # Keep only the first occurrence so we have 85 unique wards.
    wards = {}

    for feature in features:
        ward_number = str(
            feature.get("properties", {}).get("Ward_Number", "")
        ).strip()

        if not ward_number:
            continue

        if ward_number in wards:
            print(
                f"Duplicate Ward {ward_number} found - "
                f"ignoring duplicate feature."
            )
            continue

        wards[ward_number] = feature

    print("--------------------------------")
    print("Source features:", len(features))
    print("Unique wards:", len(wards))
    print("--------------------------------")

    all_features = []

    for ward_number in sorted(
        wards.keys(),
        key=lambda x: int(x) if x.isdigit() else x
    ):

        feature = wards[ward_number]

        generated = process_ward(feature)

        all_features.extend(generated)

        print(
            f"Ward {ward_number}: "
            f"{len(generated)} operational areas"
        )

    output = {
        "type": "FeatureCollection",
        "features": all_features,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    with open(
        OUTPUT,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            output,
            f,
            ensure_ascii=False,
            indent=2
        )

    print("--------------------------------")
    print("Generated areas:", len(all_features))
    print("Output:", OUTPUT)
    print("--------------------------------")


if __name__ == "__main__":
    main()