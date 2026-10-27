import json
from pathlib import Path

from shapely.geometry import shape, mapping, box
from shapely.ops import unary_union


INPUT = Path("geo/Bhopal_wards_clean.geojson")
OUTPUT = Path("geo/operational_areas.geojson")

TARGET_WARD = "76"


def load_ward():
    with open(INPUT, "r", encoding="utf-8") as f:
        data = json.load(f)

    for feature in data["features"]:
        ward_number = str(
            feature.get("properties", {}).get("Ward_Number", "")
        ).strip()

        if ward_number == TARGET_WARD:
            return feature

    raise ValueError(f"Ward {TARGET_WARD} not found")


def create_four_areas(polygon):

    minx, miny, maxx, maxy = polygon.bounds

    midx = (minx + maxx) / 2
    midy = (miny + maxy) / 2

    cells = [
        ("Area 1", box(minx, midy, midx, maxy)),
        ("Area 2", box(midx, midy, maxx, maxy)),
        ("Area 3", box(minx, miny, midx, midy)),
        ("Area 4", box(midx, miny, maxx, midy)),
    ]

    result = []

    for name, cell in cells:

        clipped = polygon.intersection(cell)

        if clipped.is_empty:
            continue

        # Clean tiny geometry artifacts
        clipped = clipped.buffer(0)

        result.append((name, clipped))

    return result


def main():

    ward = load_ward()

    polygon = shape(ward["geometry"])

    print("Ward:", TARGET_WARD)
    print("Original geometry:", polygon.geom_type)
    print("Original area:", polygon.area)

    areas = create_four_areas(polygon)

    features = []

    for index, (name, area) in enumerate(areas, start=1):

        features.append({
            "type": "Feature",
            "properties": {
                "ward_number": TARGET_WARD,
                "area_name": f"Chhola Operational Area {index}",
                "area_number": index,
            },
            "geometry": mapping(area),
        })

    output = {
        "type": "FeatureCollection",
        "features": features,
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(
            output,
            f,
            ensure_ascii=False,
        )

    print("Operational areas:", len(features))
    print("Saved:", OUTPUT)


if __name__ == "__main__":
    main()