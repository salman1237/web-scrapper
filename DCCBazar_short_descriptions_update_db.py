# update_all_short_descriptions.py
"""
Updates short_description for ALL existing products
using the CSV column: Short Description

Matching is done by slug(Name).

CSV Required Columns:
    Name, Short Description
"""

import pandas as pd
import mysql.connector
import unicodedata
import re
import sys


# ---------- CONFIG ----------
CSV_FILE = "DCC_bazar_products.csv"
DB_CONF = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "skoder_fleet_probashi"
}
LOCALE = "en"
# ----------------------------


def simple_slugify(text):
    if not text:
        return ""
    text = str(text)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[-\s]+", "-", text.strip())
    return text[:190]


# Connect DB
try:
    conn = mysql.connector.connect(**DB_CONF)
    cursor = conn.cursor(buffered=True)
except mysql.connector.Error as err:
    print("Database connection error:", err)
    sys.exit(1)


def get_translation_row(product_id):
    cursor.execute("""
        SELECT id FROM product_translations
        WHERE product_id=%s AND locale=%s LIMIT 1
    """, (product_id, LOCALE))
    row = cursor.fetchone()
    return row[0] if row else None


def get_product_id_by_slug(slug):
    cursor.execute("SELECT id FROM products WHERE slug=%s LIMIT 1", (slug,))
    row = cursor.fetchone()
    return row[0] if row else None


def update_short_description(product_id, new_short_desc):
    tr_id = get_translation_row(product_id)

    if not tr_id:
        return False

    cursor.execute("""
        UPDATE product_translations
        SET short_description=%s
        WHERE id=%s
    """, (new_short_desc, tr_id))

    return True


def main():
    try:
        df = pd.read_csv(CSV_FILE, encoding="utf-8-sig")
    except Exception as e:
        print("Error reading CSV:", e)
        return

    required_cols = {"Name", "Short Description"}
    if not required_cols.issubset(df.columns):
        print("CSV missing required columns:", df.columns.tolist())
        print("Required:", required_cols)
        return

    updated = 0
    missing = 0
    skipped = 0

    print("\nStarting FULL short_description update...\n")

    for _, row in df.iterrows():
        name = str(row.get("Name", "")).strip()
        short_desc = row.get("Short Description", "")

        if not name:
            skipped += 1
            continue

        new_sd = str(short_desc).strip()

        slug = simple_slugify(name)
        product_id = get_product_id_by_slug(slug)

        if not product_id:
            missing += 1
            print(f"NOT FOUND: {name}")
            continue

        success = update_short_description(product_id, new_sd)

        if success:
            updated += 1
            print(f"UPDATED: {name}")
        else:
            missing += 1
            print(f"TRANSLATION NOT FOUND: {name}")

    conn.commit()

    print("\n=== UPDATE COMPLETED ===")
    print(f"Short descriptions updated: {updated}")
    print(f"Translation missing: {missing}")
    print(f"Skipped (no name): {skipped}")

    cursor.close()
    conn.close()


if __name__ == "__main__":
    main()
