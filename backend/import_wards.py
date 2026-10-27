import json
from pathlib import Path

from database import SessionLocal
from models import MunicipalWard


GEOJSON_PATH = Path("geo/Bhopal_wards_clean.geojson")


def normalize_ward_number(value):
    """
    Convert ward numbers like:
    '02' -> '2'
    '06' -> '6'
    '76' -> '76'
    """
    value = str(value).strip()

    if not value:
        return None

    try:
        return str(int(value))
    except ValueError:
        return value


def import_wards():

    with open(GEOJSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    db = SessionLocal()

    try:
        inserted = 0
        skipped = 0

        seen = set()

        for feature in data["features"]:

            properties = feature.get("properties", {})
            geometry = feature.get("geometry")

            raw_ward_number = properties.get("Ward_Number")

            ward_number = normalize_ward_number(raw_ward_number)

            if not ward_number or not geometry:
                skipped += 1
                continue

            # Prevent duplicate wards inside GeoJSON
            if ward_number in seen:
                print(f"Skipping duplicate GeoJSON ward: {ward_number}")
                skipped += 1
                continue

            seen.add(ward_number)

            # Check database
            existing = (
                db.query(MunicipalWard)
                .filter(
                    MunicipalWard.ward_number == ward_number
                )
                .first()
            )

            if existing:
                print(f"Already exists: Ward {ward_number}")
                skipped += 1
                continue

            ward_name = str(
                properties.get("Name", "Unknown")
            ).strip()

            zone = properties.get("zone")

            population_raw = properties.get("population")

            try:
                population = (
                    int(population_raw)
                    if population_raw not in (None, "")
                    else None
                )
            except (ValueError, TypeError):
                population = None

            ward = MunicipalWard(
                ward_number=ward_number,
                ward_name=ward_name,
                zone=str(zone) if zone is not None else None,
                population=population,
                boundary_geojson=json.dumps(
                    geometry,
                    ensure_ascii=False
                ),
            )

            db.add(ward)
            inserted += 1

        db.commit()

        print("--------------------------------")
        print(f"Inserted wards: {inserted}")
        print(f"Skipped wards: {skipped}")
        print("--------------------------------")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    import_wards()