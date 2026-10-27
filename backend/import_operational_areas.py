import json
from pathlib import Path

from shapely.geometry import shape

from database import SessionLocal
from models import Area


GEOJSON_PATH = Path("geo/operational_areas.geojson")

WARD_ID = 79
LOCALITY_NAME = "छोला"


def import_areas():

    with open(GEOJSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    db = SessionLocal()

    try:
        inserted = 0
        skipped = 0

        for feature in data["features"]:

            properties = feature.get("properties", {})
            geometry = feature.get("geometry")

            area_name = properties.get("area_name")

            if not area_name or not geometry:
                skipped += 1
                continue

            existing = (
                db.query(Area)
                .filter(Area.area_name == area_name)
                .first()
            )

            if existing:
                print(f"Already exists: {area_name}")
                skipped += 1
                continue

            polygon = shape(geometry)
            centroid = polygon.centroid

            area = Area(
                area_name=area_name,
                latitude=centroid.y,
                longitude=centroid.x,
                locality_name=LOCALITY_NAME,
                ward_id=WARD_ID,
                boundary_geojson=json.dumps(
                    geometry,
                    ensure_ascii=False
                ),
                status="ACTIVE",
            )

            db.add(area)
            inserted += 1

        db.commit()

        print("--------------------------------")
        print(f"Inserted areas: {inserted}")
        print(f"Skipped areas: {skipped}")
        print("--------------------------------")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    import_areas()