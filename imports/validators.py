"""
Row validation — the dry run, and the same code the real run uses.

⚠️  **The dry run and the execution share this file entirely.**

    Two validators means a file that passes the preview and fails the run, and
    the admin has no reason ever to trust the preview again. So `validate_*`
    below is called by both: once with nothing written, then once per chunk as
    the rows go in. The second pass is not redundant — the catalogue can change
    between the preview and the confirmation, and a category deleted in that
    window has to fail loudly rather than resolve to `None`.

⚠️  And validation **never raises**. It returns errors.

    An exception per bad row turns ten thousand rows into ten thousand
    try/except frames and stops at the first one. The admin needs all of them at
    once — that is the entire value of a dry run over just pressing go.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from catalog import rules
from catalog.models import RegulatoryClass, StorageCondition
from imports import references, spec
from imports.reader import Row


@dataclass
class RowError:
    sheet: str
    row_number: int
    message: str
    column: str = ""
    value: str = ""
    identifier: str = ""


@dataclass
class CleanRow:
    """A row that passed. `values` is ready to hand to the model constructor."""

    number: int
    identifier: str
    values: dict[str, object]
    #: CREATE or UPDATE — decided here so the writer does not decide it twice.
    action: str = "CREATE"


@dataclass
class SheetResult:
    clean: list[CleanRow] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
    created: int = 0
    updated: int = 0
    skipped: int = 0

    def extend(self, other: SheetResult) -> None:
        self.clean.extend(other.clean)
        self.errors.extend(other.errors)
        self.created += other.created
        self.updated += other.updated
        self.skipped += other.skipped


# ═══════════════════════════════════════════════════════════
#  Shared row mechanics
# ═══════════════════════════════════════════════════════════


def _base_errors(
    row: Row,
    sheet: str,
    columns: dict[str, spec.Column],
    *,
    creating: bool = True,
) -> list[RowError]:
    """
    Everything checkable without touching the database: coercion, required, length.

    ⚠️  Coercion failures come **first and are reported as themselves**.

        A price cell holding "٤٥ جنيه" fails to coerce and lands as `None`,
        which the required check then reports as "missing". Telling the admin a
        filled cell is empty sends them looking at the wrong thing entirely.

    ⚠️  And `creating` decides whether the mandatory fields are mandatory **for
        this row**.

        "Required" is a statement about bringing a product into existence. A row
        updating the price of a product that already has a name and a category
        does not need to restate them, and demanding it is what would force the
        admin to re-upload thirty unchanged columns to change one. An update row
        still needs its key — without that there is nothing to update — and the
        key is `required` on every sheet, so it is checked below either way.
    """
    errors = [
        RowError(
            sheet=sheet,
            row_number=row.number,
            column=columns[key].header if key in columns else key,
            value=raw,
            message=message,
            identifier=row.identifier,
        )
        for key, raw, message in row.cell_errors
    ]
    failed_coercion = {key for key, _, _ in row.cell_errors}

    for key, column in columns.items():
        value = row.values.get(key)
        missing = value is None or value == "" or value == {}

        must_have = column.required and (creating or key == spec.KEY_COLUMN.get(sheet))
        if must_have and missing and key not in failed_coercion:
            errors.append(
                RowError(
                    sheet=sheet,
                    row_number=row.number,
                    column=column.header,
                    message="حقل إلزامي فارغ",
                    identifier=row.identifier,
                )
            )
            continue

        if column.required_when and missing:
            other_key, triggers = column.required_when
            if str(row.values.get(other_key) or "") in triggers:
                other = columns.get(other_key)
                errors.append(
                    RowError(
                        sheet=sheet,
                        row_number=row.number,
                        column=column.header,
                        message=(
                            f"إلزامي لأن «{other.header if other else other_key}» "
                            f"= {row.values.get(other_key)}"
                        ),
                        identifier=row.identifier,
                    )
                )

        if column.max_length and isinstance(value, str) and len(value) > column.max_length:
            errors.append(
                RowError(
                    sheet=sheet,
                    row_number=row.number,
                    column=column.header,
                    value=value[:80],
                    message=f"أطول من الحد ({len(value)} حرفًا والحد {column.max_length})",
                    identifier=row.identifier,
                )
            )

    return errors


def _resolve(
    row: Row,
    key: str,
    table: dict,
    column: spec.Column,
    sheet: str,
    errors: list[RowError],
    *,
    hint: str = "",
    by_name: dict | None = None,
):
    """
    A reference lookup that reports the value it could not find.

    ⚠️  `by_name` is the second attempt, never the first. The slug is the
        identifier the template offers and the one that cannot be ambiguous; the
        name is the fallback for a file that came from a supplier rather than
        from the template.
    """
    raw = row.get(key)
    if raw in (None, ""):
        return None

    raw = str(raw).strip()

    # ⚠️  Membership, not truthiness — the value may legitimately be `None`.
    #
    #     On a dry run the caller seeds these maps with the brands the file will
    #     create once it actually runs, and those have no id yet. Testing the
    #     value instead of the key made "create the missing brands" an option
    #     that could never be used: the preview rejected every row naming one,
    #     and execution is only reachable from a preview that passed.
    if raw in table:
        return table[raw]
    if by_name is not None and raw.casefold() in by_name:
        return by_name[raw.casefold()]

    errors.append(
        RowError(
            sheet=sheet,
            row_number=row.number,
            column=column.header,
            value=raw[:120],
            message=f"قيمة غير موجودة{hint}",
            identifier=row.identifier,
        )
    )
    return None


def _choice(
    row: Row,
    key: str,
    allowed: dict[str, str],
    column: spec.Column,
    sheet: str,
    errors: list[RowError],
    *,
    default: str = "",
) -> str:
    raw = row.get(key)
    if raw in (None, ""):
        return default

    # ⚠️  Case-folded and stripped. Excel autocorrect capitalises "otc" to "Otc",
    #     and rejecting that teaches the admin nothing about their data.
    candidate = str(raw).strip().upper()
    if candidate in allowed:
        return candidate

    errors.append(
        RowError(
            sheet=sheet,
            row_number=row.number,
            column=column.header,
            value=str(raw)[:80],
            message=f"قيمة غير مسموحة — المسموح: {'، '.join(list(allowed)[:8])}",
            identifier=row.identifier,
        )
    )
    return default


#: Which value key a column writes into, where the two differ.
_PRODUCT_VALUE_KEY = {"category_path": "category_id"}
_VARIANT_VALUE_KEY = {"parent_sku": "product_id"}


def _drop_blank_mandatories(row: Row, sheet: str, values: dict, value_key: dict) -> None:
    """
    On an update, a blank cell in a create-mandatory column means **leave it alone**.

    ⚠️  Without this, an update row with an empty price column writes `0.00` —
        because that is the default the create path needs — and the product goes
        on sale for nothing. The same blank would empty a name and a category,
        which the database refuses, or a `kind`, which it does not.

        A blank in an *optional* column still clears it: that is how the admin
        removes a description, and there is no other way to say it. The
        distinction is exactly the set of fields a product cannot exist without.
    """
    for column in spec.columns_for(sheet):
        if not column.required:
            continue
        if row.values.get(column.key) in (None, "", {}):
            values.pop(value_key.get(column.key, column.key), None)


# ═══════════════════════════════════════════════════════════
#  products
# ═══════════════════════════════════════════════════════════

#: Columns copied straight through once they have passed the base checks.
_PRODUCT_PASSTHROUGH = (
    "sku",
    "name_ar",
    "name_en",
    "barcode",
    "registration_number",
    "active_ingredient_ar",
    "active_ingredient_en",
    "strength",
    "pack_size",
    "short_description_ar",
    "short_description_en",
    "description_ar",
    "description_en",
    "meta_title_ar",
    "meta_title_en",
    "meta_description_ar",
    "meta_description_en",
)


def validate_products(
    rows: list[Row],
    data: references.ReferenceData,
    *,
    mode: str,
    existing_skus: dict[str, object],
    duplicate_skus: set[str],
) -> SheetResult:
    """
    ⚠️  Both lookups are passed in, never queried here.

        Asking "does this SKU exist?" per row is one query per row. The caller
        loads the SKUs of the whole chunk in a single `IN` query.

        And `duplicate_skus` comes from a scan of the **whole file**, done once
        before any chunk ran — a chunk cannot see a repeat of its own SKU seven
        thousand rows later, and that is precisely the duplicate that gets
        through. See `services._scan_duplicates`.
    """
    sheet = spec.Sheet.PRODUCTS
    columns = spec.column_map(sheet)
    result = SheetResult()

    for row in rows:
        values: dict[str, object] = {}
        sku = str(row.get("sku") or "").strip()

        # ⚠️  The action is decided **before** the base checks run, because the
        #     base checks depend on it: an update row is not missing a name it
        #     was never asked to supply.
        action = (
            "UPDATE"
            if sku and sku in existing_skus and mode != spec.ImportMode.CREATE_ONLY
            else "CREATE"
        )
        errors = _base_errors(row, sheet, columns, creating=action == "CREATE")

        # ── Identity and mode ──────────────────────────────
        if sku:
            if sku in duplicate_skus:
                errors.append(
                    RowError(
                        sheet=sheet,
                        row_number=row.number,
                        column=columns["sku"].header,
                        value=sku,
                        message="هذا الرمز مكرّر في الملف — احذف الصف الزائد أو غيّر رمزه",
                        identifier=sku,
                    )
                )

            exists = sku in existing_skus
            if exists and mode == spec.ImportMode.CREATE_ONLY:
                errors.append(
                    RowError(
                        sheet=sheet,
                        row_number=row.number,
                        column=columns["sku"].header,
                        value=sku,
                        message="الرمز موجود مسبقًا — والنمط المختار «إضافة الجديد فقط»",
                        identifier=sku,
                    )
                )
            elif not exists and mode == spec.ImportMode.UPDATE_ONLY:
                errors.append(
                    RowError(
                        sheet=sheet,
                        row_number=row.number,
                        column=columns["sku"].header,
                        value=sku,
                        message="الرمز غير موجود — والنمط المختار «تحديث الموجود فقط»",
                        identifier=sku,
                    )
                )

        # ── References ─────────────────────────────────────
        values["category_id"] = _resolve(
            row,
            "category_path",
            data.categories,
            columns["category_path"],
            sheet,
            errors,
            hint=" — انسخ المسار من ورقة «القيم المسموحة»",
        )
        values["brand_id"] = _resolve(
            row,
            "brand_slug",
            data.brands,
            columns["brand_slug"],
            sheet,
            errors,
            by_name=data.brand_names,
        )
        values["manufacturer_id"] = _resolve(
            row,
            "manufacturer_slug",
            data.manufacturers,
            columns["manufacturer_slug"],
            sheet,
            errors,
            by_name=data.manufacturer_names,
        )
        values["tax_class_id"] = _resolve(
            row, "tax_class_code", data.tax_classes, columns["tax_class_code"], sheet, errors
        )
        values["access_policy_id"] = _resolve(
            row,
            "access_policy_code",
            data.access_policies,
            columns["access_policy_code"],
            sheet,
            errors,
        )

        # ── Enumerations ───────────────────────────────────
        values["kind"] = _choice(row, "kind", data.kinds, columns["kind"], sheet, errors)
        values["regulatory_class"] = _choice(
            row,
            "regulatory_class",
            data.regulatory_classes,
            columns["regulatory_class"],
            sheet,
            errors,
            default=RegulatoryClass.NOT_APPLICABLE,
        )
        values["dosage_form"] = _choice(
            row, "dosage_form", data.dosage_forms, columns["dosage_form"], sheet, errors
        )
        values["storage_condition"] = _choice(
            row,
            "storage_condition",
            data.storage_conditions,
            columns["storage_condition"],
            sheet,
            errors,
            default=StorageCondition.ROOM,
        )

        # ── Numbers and flags ──────────────────────────────
        price = row.get("base_price")
        if price is not None and Decimal(str(price)) < 0:
            errors.append(
                RowError(
                    sheet=sheet,
                    row_number=row.number,
                    column=columns["base_price"].header,
                    value=str(price),
                    message="السعر لا يكون سالبًا",
                    identifier=sku,
                )
            )
        values["base_price"] = price if price is not None else Decimal("0.00")

        weight = row.get("weight_grams")
        if weight is not None and int(weight) < 0:
            errors.append(
                RowError(
                    sheet=sheet,
                    row_number=row.number,
                    column=columns["weight_grams"].header,
                    value=str(weight),
                    message="الوزن لا يكون سالبًا",
                    identifier=sku,
                )
            )
        values["weight_grams"] = weight

        values["requires_prescription"] = bool(row.values.get("requires_prescription") or False)

        # ⚠️  `is_active` defaults to **False**, and the default is the feature.
        #
        #     Ten thousand products appearing in the storefront the instant an
        #     import finishes is not a fast import, it is an outage with a
        #     catalogue attached. The sheet may say otherwise per row; silence
        #     means draft.
        values["is_active"] = bool(row.values.get("is_active") or False)
        values["is_featured"] = bool(row.values.get("is_featured") or False)

        for key in _PRODUCT_PASSTHROUGH:
            values[key] = row.values.get(key) or ""

        # ── The cross-field regulatory rule — shared with the admin form ──
        for column_key, message in rules.regulatory_errors(
            kind=values["kind"],
            regulatory_class=values["regulatory_class"],
            requires_prescription=values["requires_prescription"],
        ).items():
            errors.append(
                RowError(
                    sheet=sheet,
                    row_number=row.number,
                    column=columns[column_key].header if column_key in columns else column_key,
                    value=str(values.get(column_key, ""))[:80],
                    message=message,
                    identifier=sku,
                )
            )

        # ⚠️  A restricted product with no policy is a **warning-shaped error**.
        #
        #     `access_policy = None` means the default policy, which means
        #     everyone. On an ordinary supply that is correct and intended. On
        #     something the file itself classified as prescription-only it is the
        #     exact mistake `ProductFormOptionsAPI` was rewritten to prevent, and
        #     it is invisible afterwards — the product looks fine in every list.
        if (
            values["regulatory_class"] in (RegulatoryClass.PRESCRIPTION, RegulatoryClass.CONTROLLED)
            and values.get("access_policy_id") is None
        ):
            errors.append(
                RowError(
                    sheet=sheet,
                    row_number=row.number,
                    column=columns["access_policy_code"].header,
                    message=(
                        "صنف مقيّد تنظيميًا بلا سياسة وصول — الفراغ هنا يعني «الجميع»، "
                        "أي نشره لكل زائر"
                    ),
                    identifier=sku,
                )
            )

        if errors:
            result.errors.extend(errors)
            continue

        if action == "UPDATE":
            _drop_blank_mandatories(row, sheet, values, _PRODUCT_VALUE_KEY)

        result.clean.append(
            CleanRow(number=row.number, identifier=sku, values=values, action=action)
        )
        if action == "CREATE":
            result.created += 1
        else:
            result.updated += 1

    return result


# ═══════════════════════════════════════════════════════════
#  stock
# ═══════════════════════════════════════════════════════════


def validate_stock(
    rows: list[Row],
    data: references.ReferenceData,
    *,
    known_skus: dict[str, object],
    known_variant_skus: dict[str, object],
) -> SheetResult:
    """
    ⚠️  A stock row names a product that may not exist **yet** — it is created by
        the products sheet in an earlier phase of the same job.

        So membership in `known_skus` is what counts, and the value may be
        `None`: on a dry run the caller seeds the map with the SKUs the file
        itself will create, which have no id because nothing has been written.
        Testing `is None` instead of `in` is what made the preview reject every
        correct stock row in a file that also carried its products.
    """
    sheet = spec.Sheet.STOCK
    columns = spec.column_map(sheet)
    result = SheetResult()

    for row in rows:
        errors = _base_errors(row, sheet, columns)
        sku = str(row.get("sku") or "").strip()

        product_id = known_skus.get(sku)
        if sku and sku not in known_skus:
            errors.append(
                RowError(
                    sheet=sheet,
                    row_number=row.number,
                    column=columns["sku"].header,
                    value=sku,
                    message="لا يوجد منتج بهذا الرمز — لا في الملف ولا في الكتالوج",
                    identifier=sku,
                )
            )

        variant_sku = str(row.get("variant_sku") or "").strip()
        variant_id = None
        if variant_sku:
            variant_id = known_variant_skus.get(variant_sku)
            if variant_sku not in known_variant_skus:
                errors.append(
                    RowError(
                        sheet=sheet,
                        row_number=row.number,
                        column=columns["variant_sku"].header,
                        value=variant_sku,
                        message="لا توجد نسخة بهذا الرمز",
                        identifier=sku,
                    )
                )

        quantity = row.get("quantity")
        if quantity is not None and int(quantity) <= 0:
            errors.append(
                RowError(
                    sheet=sheet,
                    row_number=row.number,
                    column=columns["quantity"].header,
                    value=str(quantity),
                    message="الكمية يجب أن تكون موجبة — الصفر ليس رصيدًا افتتاحيًا",
                    identifier=sku,
                )
            )

        unit_cost = row.get("unit_cost")
        if unit_cost is not None and Decimal(str(unit_cost)) < 0:
            errors.append(
                RowError(
                    sheet=sheet,
                    row_number=row.number,
                    column=columns["unit_cost"].header,
                    value=str(unit_cost),
                    message="التكلفة لا تكون سالبة",
                    identifier=sku,
                )
            )

        location_code = str(row.get("location_code") or "").strip()
        location_id = None
        if location_code:
            location_id = _resolve(
                row, "location_code", data.locations, columns["location_code"], sheet, errors
            )
        elif not data.default_location_code:
            # ⚠️  No location named and no default configured. `receive()` would
            #     take `location=None` and fail deep inside `_locked_stock` with
            #     an error naming neither the row nor the reason.
            errors.append(
                RowError(
                    sheet=sheet,
                    row_number=row.number,
                    column=columns["location_code"].header,
                    message="لا يوجد موقع مخزني افتراضي — حدّد الموقع في الملف أو عيّن افتراضيًا",
                    identifier=sku,
                )
            )

        expires_at = row.get("expires_at")
        manufactured_at = row.get("manufactured_at")
        if expires_at and manufactured_at and expires_at < manufactured_at:
            errors.append(
                RowError(
                    sheet=sheet,
                    row_number=row.number,
                    column=columns["expires_at"].header,
                    value=str(expires_at),
                    message="تاريخ الصلاحية قبل تاريخ الإنتاج",
                    identifier=sku,
                )
            )

        if errors:
            result.errors.extend(errors)
            continue

        result.clean.append(
            CleanRow(
                number=row.number,
                identifier=sku,
                values={
                    "product_id": product_id,
                    "variant_id": variant_id,
                    "location_id": location_id,
                    "quantity": int(quantity),
                    "unit_cost": unit_cost,
                    "expires_at": expires_at,
                    "manufactured_at": manufactured_at,
                    "supplier_batch_number": row.values.get("supplier_batch_number") or "",
                },
            )
        )
        result.created += 1

    return result


# ═══════════════════════════════════════════════════════════
#  variants
# ═══════════════════════════════════════════════════════════


def validate_variants(
    rows: list[Row],
    *,
    known_skus: dict[str, object],
    existing_variant_skus: set[str],
    duplicate_skus: set[str],
) -> SheetResult:
    sheet = spec.Sheet.VARIANTS
    columns = spec.column_map(sheet)
    result = SheetResult()

    for row in rows:
        parent_sku = str(row.get("parent_sku") or "").strip()
        sku = str(row.get("sku") or "").strip()

        action = "UPDATE" if sku and sku in existing_variant_skus else "CREATE"
        errors = _base_errors(row, sheet, columns, creating=action == "CREATE")

        product_id = known_skus.get(parent_sku)
        if parent_sku and parent_sku not in known_skus:
            errors.append(
                RowError(
                    sheet=sheet,
                    row_number=row.number,
                    column=columns["parent_sku"].header,
                    value=parent_sku,
                    message="لا يوجد منتج أصل بهذا الرمز",
                    identifier=sku,
                )
            )

        if sku:
            if sku in duplicate_skus:
                errors.append(
                    RowError(
                        sheet=sheet,
                        row_number=row.number,
                        column=columns["sku"].header,
                        value=sku,
                        message="رمز نسخة مكرّر في الملف",
                        identifier=sku,
                    )
                )

            # ⚠️  `ProductVariant.sku` and `Product.sku` are two unique columns on
            #     two tables, and nothing stops a variant taking a product's code.
            #     The point-of-sale scanner then resolves one barcode to two
            #     different things depending on which lookup ran first.
            if sku in known_skus:
                errors.append(
                    RowError(
                        sheet=sheet,
                        row_number=row.number,
                        column=columns["sku"].header,
                        value=sku,
                        message="هذا الرمز مستخدم كرمز منتج — لا يصلح رمزًا لنسخة",
                        identifier=sku,
                    )
                )

        if errors:
            result.errors.extend(errors)
            continue

        variant_values = {
            "product_id": product_id,
            "sku": sku,
            "name_ar": row.values.get("name_ar") or "",
            "name_en": row.values.get("name_en") or "",
            "barcode": row.values.get("barcode") or "",
            "price_adjustment": row.get("price_adjustment") or Decimal("0.00"),
            "weight_grams": row.get("weight_grams"),
            "attributes": row.values.get("attributes") or {},
        }

        if action == "UPDATE":
            _drop_blank_mandatories(row, sheet, variant_values, _VARIANT_VALUE_KEY)

        result.clean.append(
            CleanRow(number=row.number, identifier=sku, action=action, values=variant_values)
        )
        if action == "CREATE":
            result.created += 1
        else:
            result.updated += 1

    return result
