"""Import public OFF snapshots without generating requests or gold labels."""
from datetime import datetime

from approv.harness.openfoodfacts import OFF_FIELD_PROFILES, evidence_from
from approv.harness.shopping import Inventory, Product
from approv.types.core import AttributeSpec, CategorySchema, Criticality, Dimension


def import_off(records: list[dict], captured_at: datetime) -> tuple[Inventory, dict]:
    products = {}
    skipped = duplicates = 0
    for record in records:
        code = str(record.get("code") or "").strip()
        title = (record.get("product_name") or "").strip()
        if not code or not title:
            skipped += 1
            continue
        product = Product(id=code, title=title, evidence=evidence_from(record),
            source_url=f"https://world.openfoodfacts.org/product/{code}", raw=record)
        if code in products:
            if products[code] != product:
                raise ValueError(f"conflicting duplicate product {code}")
            duplicates += 1
        products[code] = product
    dimensions = {"brand": Dimension.NOMINAL, "net_weight": Dimension.MASS,
                  "net_volume": Dimension.VOLUME, "pack_count": Dimension.COUNT,
                  "unit_weight": Dimension.MASS, "unit_volume": Dimension.VOLUME}
    schema = CategorySchema(category_id="public.off.grocery", version="shopping-v1",
        attributes=tuple(AttributeSpec(name=k, dimension=v, criticality=Criticality.HARD)
                         for k, v in dimensions.items()), field_profiles=OFF_FIELD_PROFILES)
    inventory = Inventory(source="Open Food Facts contributor snapshot",
        source_license="ODbL 1.0; https://opendatacommons.org/licenses/odbl/1-0/",
        captured_at=captured_at, schema=schema, products=tuple(products.values()))
    return inventory, {"input_records": len(records), "products": len(products),
                       "missing_id_or_title": skipped, "identical_duplicates": duplicates}
