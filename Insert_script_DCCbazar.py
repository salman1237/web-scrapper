# import_products_smart_fill_with_images_and_meta.py
"""
Reads products CSV and:
- Inserts NEW products
- For EXISTING products: fills only missing/empty columns (price, offer price, description)
- Never overwrites existing good data

CSV columns expected (exact):
  Name, Category, Price, Offer Price, Description, Product URL, Image Path

New features:
1. Image support: uses CSV column "Image Path". Inserts into `files` and `entity_files` (zone 'base_image').
2. Brand creation: creates brand named "<Category>_Brand" (slugified) and assigns to product if missing.
3. SKU: generate as product_id + first2(category) + first2(product_name) (lowercased) if sku missing.
4. Meta: populate meta_data + meta_data_translations (meta_title = product name, meta_description = product description).
5. Tags: pick up to 3 unique random words from title+description as tags (creates tags/tag_translations and product_tags).
All existing smart-fill behavior preserved.
"""

import pandas as pd
import mysql.connector
import re
import unicodedata
import sys
import time
import os
import random

# ---------- CONFIG ----------
CSV_FILE = "DCC_bazar_products.csv"
DB_CONF = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "skoder_fleet_probashi"
}
BATCH_COMMIT_SIZE = 100  # commit every N rows
LOCALE = "en"
DEFAULT_FILE_USER_ID = 1        # user_id to use when inserting files
DEFAULT_FILE_DISK = "public_storage"  # disk value when inserting files
# ----------------------------

def simple_slugify(text, max_length=190):
    if not text:
        return ""
    text = str(text)
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[^\w\s-]', '', text.lower())
    text = re.sub(r'[-\s]+', '-', text.strip())
    return text[:max_length]

def parse_price(price_str):
    if not price_str or pd.isna(price_str):
        return None
    price_str = str(price_str).strip()
    price_str = re.sub(r'[৳$€£¥]', '', price_str).strip()
    price_str = price_str.replace(',', '')
    try:
        return float(price_str)
    except (ValueError, TypeError):
        return None

def is_empty_value(value):
    if value is None:
        return True
    if pd.isna(value):
        return True
    if isinstance(value, (int, float)) and value == 0:
        return True
    if isinstance(value, str) and (not value.strip() or value.strip() == '0'):
        return True
    return False

# Connect to DB
try:
    conn = mysql.connector.connect(**DB_CONF)
except mysql.connector.Error as err:
    print("DB connection error:", err)
    sys.exit(1)

cursor = conn.cursor(buffered=True)

# ---------------- Helper functions ----------------

def get_or_create_category(name):
    """Return category_id (create if needed)."""
    if not name or pd.isna(name):
        return None
    name = str(name).strip()
    if not name:
        return None
    cursor.execute("SELECT category_id FROM category_translations WHERE LOWER(name) = LOWER(%s) LIMIT 1", (name,))
    row = cursor.fetchone()
    if row:
        return int(row[0])
    slug = simple_slugify(name)
    cursor.execute("SELECT id FROM categories WHERE slug = %s LIMIT 1", (slug,))
    row = cursor.fetchone()
    if row:
        return int(row[0])
    cursor.execute("SELECT COALESCE(MAX(id),0)+1 FROM categories")
    new_id = int(cursor.fetchone()[0])
    now = time.strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("INSERT INTO categories (id, slug, is_active, created_at, updated_at) VALUES (%s, %s, 1, %s, %s)",
                   (new_id, slug, now, now))
    cursor.execute("INSERT INTO category_translations (id, category_id, locale, name) VALUES (%s, %s, %s, %s)",
                   (new_id, new_id, LOCALE, name))
    print(f"Created category '{name}' with id {new_id}")
    return new_id

def get_or_create_brand_from_category_name(category_name):
    """Brand name format: '<Category>_Brand'"""
    if not category_name or pd.isna(category_name):
        return None
    cat_name = str(category_name).strip()
    if not cat_name:
        return None
    brand_name = f"{cat_name}_Brand"
    slug = simple_slugify(brand_name)
    cursor.execute("SELECT id FROM brands WHERE slug = %s LIMIT 1", (slug,))
    row = cursor.fetchone()
    if row:
        return int(row[0])
    cursor.execute("SELECT COALESCE(MAX(id),0)+1 FROM brands")
    new_brand_id = int(cursor.fetchone()[0])
    now = time.strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("INSERT INTO brands (id, slug, is_active, created_at, updated_at) VALUES (%s, %s, 1, %s, %s)",
                   (new_brand_id, slug, now, now))
    # brand_translations exists in your dump
    cursor.execute("SELECT COALESCE(MAX(id),0)+1 FROM brand_translations")
    new_bt_id = int(cursor.fetchone()[0])
    cursor.execute("INSERT INTO brand_translations (id, brand_id, locale, name) VALUES (%s, %s, %s, %s)",
                   (new_bt_id, new_brand_id, LOCALE, brand_name))
    print(f"Created brand '{brand_name}' with id {new_brand_id}")
    return new_brand_id

def get_existing_product_data(slug):
    """Return dict of existing product data or None"""
    cursor.execute("""
        SELECT p.id, p.price, p.special_price, p.selling_price, pt.name, pt.description, p.brand_id, p.sku
        FROM products p
        LEFT JOIN product_translations pt ON p.id = pt.product_id AND pt.locale = %s
        WHERE p.slug = %s LIMIT 1
    """, (LOCALE, slug))
    row = cursor.fetchone()
    if not row:
        return None
    return {
        'id': row[0],
        'price': row[1],
        'special_price': row[2],
        'selling_price': row[3],
        'name': row[4],
        'description': row[5],
        'brand_id': row[6],
        'sku': row[7]
    }

def ensure_file_and_entity_for_product(product_id, image_path):
    """
    - Reuse files row if path matches
    - Insert files row otherwise
    - Ensure entity_files mapping (zone 'base_image')
    """
    if not image_path or pd.isna(image_path):
        return None
    image_path = str(image_path).strip()
    if not image_path:
        return None
    # remove query part if URL
    path_for_db = image_path.split('?')[0]
    filename = os.path.basename(path_for_db)
    extension = ''
    if '.' in filename:
        extension = filename.split('.')[-1].lower()
    now = time.strftime('%Y-%m-%d %H:%M:%S')

    # try find existing file by path
    cursor.execute("SELECT id FROM files WHERE path = %s LIMIT 1", (path_for_db,))
    row = cursor.fetchone()
    if row:
        file_id = int(row[0])
    else:
        cursor.execute("SELECT COALESCE(MAX(id),0)+1 FROM files")
        new_file_id = int(cursor.fetchone()[0])
        cursor.execute("""
            INSERT INTO files (id, user_id, filename, disk, path, extension, mime, size, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (new_file_id, DEFAULT_FILE_USER_ID, filename, DEFAULT_FILE_DISK, path_for_db, extension, '', '0', now, now))
        file_id = new_file_id
        print(f"  → Inserted file row id={file_id} path={path_for_db}")

    # ensure entity_files mapping (zone 'base_image')
    cursor.execute("""
        SELECT 1 FROM entity_files
        WHERE file_id = %s AND entity_type = %s AND entity_id = %s AND zone = %s LIMIT 1
    """, (file_id, 'Modules\\Product\\Entities\\Product', product_id, 'base_image'))
    if not cursor.fetchone():
        cursor.execute("SELECT COALESCE(MAX(id),0)+1 FROM entity_files")
        new_entity_file_id = int(cursor.fetchone()[0])
        cursor.execute("""
            INSERT INTO entity_files (id, file_id, entity_type, entity_id, zone, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (new_entity_file_id, file_id, 'Modules\\Product\\Entities\\Product', product_id, 'base_image', now, now))
        print(f"  → Mapped file_id={file_id} to product_id={product_id} as base_image (entity_files id={new_entity_file_id})")
    return file_id

def ensure_meta_for_product(product_id, meta_title, meta_description):
    """
    Ensure meta_data and meta_data_translations exist for the product.
    Only fills missing title/description (doesn't overwrite existing).
    """
    if not product_id:
        return
    cursor.execute("SELECT id FROM meta_data WHERE entity_type = %s AND entity_id = %s LIMIT 1",
                   ('Modules\\Product\\Entities\\Product', product_id))
    row = cursor.fetchone()
    now = time.strftime('%Y-%m-%d %H:%M:%S')
    if row:
        meta_id = int(row[0])
    else:
        cursor.execute("SELECT COALESCE(MAX(id),0)+1 FROM meta_data")
        meta_id = int(cursor.fetchone()[0])
        cursor.execute("INSERT INTO meta_data (id, entity_type, entity_id, created_at, updated_at) VALUES (%s, %s, %s, %s, %s)",
                       (meta_id, 'Modules\\Product\\Entities\\Product', product_id, now, now))
        print(f"  → Created meta_data id={meta_id} for product {product_id}")

    cursor.execute("SELECT meta_title, meta_description FROM meta_data_translations WHERE meta_data_id = %s AND locale = %s LIMIT 1",
                   (meta_id, LOCALE))
    row = cursor.fetchone()
    if row:
        cur_title, cur_desc = row
        need_update = False
        upd_parts = []
        params = []
        if (cur_title is None or cur_title == '') and meta_title:
            need_update = True
            upd_parts.append("meta_title = %s")
            params.append(meta_title)
        if (cur_desc is None or cur_desc == '') and meta_description:
            need_update = True
            upd_parts.append("meta_description = %s")
            params.append(meta_description)
        if need_update:
            params.append(meta_id)
            params.append(LOCALE)
            update_sql = f"UPDATE meta_data_translations SET {', '.join(upd_parts)} WHERE meta_data_id = %s AND locale = %s"
            cursor.execute(update_sql, params)
            print(f"  → Updated meta_data_translations for meta_id={meta_id}")
    else:
        cursor.execute("SELECT COALESCE(MAX(id),0)+1 FROM meta_data_translations")
        new_md_t_id = int(cursor.fetchone()[0])
        cursor.execute("INSERT INTO meta_data_translations (id, meta_data_id, locale, meta_title, meta_description) VALUES (%s, %s, %s, %s, %s)",
                       (new_md_t_id, meta_id, LOCALE, meta_title, meta_description))
        print(f"  → Inserted meta_data_translations id={new_md_t_id} for meta_id={meta_id}")

def extract_tag_words(title, description, max_tags=3):
    """
    From title+description, choose up to max_tags unique random words.
    Filter words length >= 3 and remove numeric/short tokens.
    """
    combined = ''
    if title and not pd.isna(title):
        combined += ' ' + str(title)
    if description and not pd.isna(description):
        combined += ' ' + str(description)
    words = re.findall(r"\b[^\d\W]{3,}\b", combined, flags=re.UNICODE)  # alpha >=3
    if not words:
        return []
    uniq = list({w.lower() for w in words})
    if len(uniq) <= max_tags:
        selected = uniq
    else:
        selected = random.sample(uniq, max_tags)
    return selected

def get_or_create_tag_id(tag_word):
    """Find tag by tag_translations.name or tag.slug; create if missing."""
    if not tag_word:
        return None
    word = str(tag_word).strip()
    if not word:
        return None
    cursor.execute("SELECT tag_id FROM tag_translations WHERE LOWER(name) = LOWER(%s) LIMIT 1", (word,))
    row = cursor.fetchone()
    if row:
        return int(row[0])
    slug = simple_slugify(word)
    cursor.execute("SELECT id FROM tags WHERE slug = %s LIMIT 1", (slug,))
    row = cursor.fetchone()
    if row:
        tag_id = int(row[0])
    else:
        cursor.execute("SELECT COALESCE(MAX(id),0)+1 FROM tags")
        tag_id = int(cursor.fetchone()[0])
        now = time.strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("INSERT INTO tags (id, slug, created_at, updated_at) VALUES (%s, %s, %s, %s)",
                       (tag_id, slug, now, now))
        print(f"  → Created tag '{word}' id={tag_id}")
    cursor.execute("SELECT 1 FROM tag_translations WHERE tag_id = %s AND LOWER(name) = LOWER(%s) LIMIT 1", (tag_id, word))
    if not cursor.fetchone():
        cursor.execute("SELECT COALESCE(MAX(id),0)+1 FROM tag_translations")
        new_tt_id = int(cursor.fetchone()[0])
        cursor.execute("INSERT INTO tag_translations (id, tag_id, locale, name) VALUES (%s, %s, %s, %s)",
                       (new_tt_id, tag_id, LOCALE, word))
    return tag_id

def ensure_product_tags(product_id, tag_words):
    if not tag_words:
        return
    for w in tag_words:
        tag_id = get_or_create_tag_id(w)
        if not tag_id:
            continue
        cursor.execute("SELECT 1 FROM product_tags WHERE product_id = %s AND tag_id = %s LIMIT 1", (product_id, tag_id))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO product_tags (product_id, tag_id) VALUES (%s, %s)", (product_id, tag_id))
            print(f"  → Mapped tag_id={tag_id} to product_id={product_id}")

# --------------- Core insert/update logic ----------------

def insert_or_smart_update_product(row):
    name = str(row.get("Name", "")).strip()
    category_name = row.get("Category", "")
    price_str = row.get("Price", "")
    offer_price_str = row.get("Offer Price", "")
    description = row.get("Description", "")
    # Product URL will be ignored as requested
    image_path = row.get("Image Path", "")

    if not name:
        print("Skipping row with empty Name")
        return None

    slug = simple_slugify(name)
    csv_price_val = parse_price(price_str)
    csv_offer_val = parse_price(offer_price_str)
    csv_selling_price = csv_offer_val if csv_offer_val is not None else csv_price_val

    existing_data = get_existing_product_data(slug)
    now = time.strftime('%Y-%m-%d %H:%M:%S')

    if existing_data:
        product_id = existing_data['id']
        updates = []
        update_params = []

        # Smart-fill price fields
        if is_empty_value(existing_data['price']) and csv_price_val is not None:
            updates.append("price = %s")
            update_params.append(csv_price_val)
            print(f"  → Filling missing price: {csv_price_val}")
        if is_empty_value(existing_data['special_price']) and csv_offer_val is not None:
            updates.append("special_price = %s")
            update_params.append(csv_offer_val)
            print(f"  → Filling missing special_price: {csv_offer_val}")
        current_selling_price = existing_data['selling_price']
        if (is_empty_value(current_selling_price) and csv_selling_price is not None) or \
           (current_selling_price == existing_data['price'] and csv_offer_val is not None):
            new_selling_price = csv_selling_price
            updates.append("selling_price = %s")
            update_params.append(new_selling_price)
            print(f"  → Updating selling_price: {new_selling_price}")

        # If brand missing, create brand from category and assign
        if is_empty_value(existing_data['brand_id']) and category_name and not pd.isna(category_name):
            brand_id = get_or_create_brand_from_category_name(str(category_name).strip())
            if brand_id:
                updates.append("brand_id = %s")
                update_params.append(brand_id)
                print(f"  → Assigned brand_id {brand_id}")

        # Generate SKU only if missing
        if is_empty_value(existing_data.get('sku')) or existing_data.get('sku') is None:
            cat_part = (re.sub(r'\W+', '', str(category_name).strip())[:2].lower() if category_name and not pd.isna(category_name) else '')
            prod_part = re.sub(r'\W+', '', name)[:2].lower()
            sku_generated = f"{product_id}{cat_part}{prod_part}"
            updates.append("sku = %s")
            update_params.append(sku_generated)
            print(f"  → Generated SKU: {sku_generated}")

        if updates:
            updates.append("updated_at = %s")
            update_params.append(now)
            update_params.append(product_id)
            update_sql = f"UPDATE products SET {', '.join(updates)} WHERE id = %s"
            cursor.execute(update_sql, update_params)

        # Fill missing description in translation
        if is_empty_value(existing_data['description']) and description and not pd.isna(description):
            cursor.execute("""
                UPDATE product_translations 
                SET description = %s 
                WHERE product_id = %s AND locale = %s
            """, (description, product_id, LOCALE))
            print(f"  → Filling missing description")

        # Map category if missing mapping
        if category_name and not pd.isna(category_name):
            cat_id = get_or_create_category(str(category_name).strip())
            if cat_id:
                cursor.execute("SELECT 1 FROM product_categories WHERE product_id=%s AND category_id=%s LIMIT 1",
                               (product_id, cat_id))
                if not cursor.fetchone():
                    cursor.execute("INSERT INTO product_categories (product_id, category_id) VALUES (%s, %s)",
                                   (product_id, cat_id))
                    print(f"  → Added category mapping")

        # Handle image insertion/mapping
        try:
            if image_path and not pd.isna(image_path):
                ensure_file_and_entity_for_product(product_id, image_path)
        except Exception as e:
            print(f"  ! Error handling image for product {product_id}: {e}")

        # Meta: meta_title = name, meta_description = description (only if missing)
        try:
            ensure_meta_for_product(product_id, name, description)
        except Exception as e:
            print(f"  ! Error ensuring meta for product {product_id}: {e}")

        # Tags: choose up to 3 unique random words
        try:
            tag_words = extract_tag_words(name, description, max_tags=3)
            ensure_product_tags(product_id, tag_words)
        except Exception as e:
            print(f"  ! Error ensuring tags for product {product_id}: {e}")

        action = "updated" if updates or (description and is_empty_value(existing_data['description'])) else "skipped_ok"
        print(f"SMART UPDATE: {name} - {action}")
        return action, product_id

    else:
        # Insert new product (preserves original fields)
        cursor.execute("SELECT COALESCE(MAX(id),0)+1 FROM products")
        new_product_id = int(cursor.fetchone()[0])

        cursor.execute("""
            INSERT INTO products (id, brand_id, tax_class_id, slug, price, special_price, selling_price, sku,
                                  manage_stock, qty, in_stock, viewed, is_active, created_at, updated_at, is_virtual)
            VALUES (%s, NULL, NULL, %s, %s, %s, %s, NULL, 0, NULL, 1, 0, 1, %s, %s, 0)
        """, (new_product_id, slug, csv_price_val, csv_offer_val, csv_selling_price, now, now))

        # product translations
        cursor.execute("SELECT COALESCE(MAX(id),0)+1 FROM product_translations")
        new_translation_id = int(cursor.fetchone()[0])
        cursor.execute("""
            INSERT INTO product_translations (id, product_id, locale, name, description, short_description)
            VALUES (%s, %s, %s, %s, %s, NULL)
        """, (new_translation_id, new_product_id, LOCALE, name, description))

        # category mapping
        if category_name and not pd.isna(category_name):
            cat_id = get_or_create_category(str(category_name).strip())
            if cat_id:
                cursor.execute("INSERT INTO product_categories (product_id, category_id) VALUES (%s, %s)",
                               (new_product_id, cat_id))

        # brand creation and assignment
        if category_name and not pd.isna(category_name):
            brand_id = get_or_create_brand_from_category_name(str(category_name).strip())
            if brand_id:
                cursor.execute("UPDATE products SET brand_id = %s WHERE id = %s", (brand_id, new_product_id))

        # SKU generation
        cat_part = (re.sub(r'\W+', '', str(category_name).strip())[:2].lower() if category_name and not pd.isna(category_name) else '')
        prod_part = re.sub(r'\W+', '', name)[:2].lower()
        sku_generated = f"{new_product_id}{cat_part}{prod_part}"
        cursor.execute("UPDATE products SET sku = %s WHERE id = %s", (sku_generated, new_product_id))
        print(f"  → Generated SKU for new product: {sku_generated}")

        # Image handling
        try:
            if image_path and not pd.isna(image_path):
                ensure_file_and_entity_for_product(new_product_id, image_path)
        except Exception as e:
            print(f"  ! Error handling image for new product {new_product_id}: {e}")

        # Meta
        try:
            ensure_meta_for_product(new_product_id, name, description)
        except Exception as e:
            print(f"  ! Error creating meta for new product {new_product_id}: {e}")

        # Tags
        try:
            tag_words = extract_tag_words(name, description, max_tags=3)
            ensure_product_tags(new_product_id, tag_words)
        except Exception as e:
            print(f"  ! Error ensuring tags for new product {new_product_id}: {e}")

        print(f"INSERTED NEW: {name} (ID: {new_product_id})")
        return "inserted", new_product_id

# ---------------- Main flow ----------------

def main():
    try:
        df = pd.read_csv(CSV_FILE, encoding='utf-8-sig')
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        return

    expected_cols = {"Name", "Category", "Price", "Offer Price", "Description", "Product URL", "Image Path"}
    if not expected_cols.issubset(set(df.columns)):
        print("CSV missing expected columns. Found:", df.columns.tolist())
        print("Expected columns (exact):", expected_cols)
        return

    processed = 0
    stats = {
        "inserted": 0,
        "updated": 0,
        "skipped_ok": 0,
        "skipped_empty": 0,
        "error": 0
    }

    print("Starting import (SMART FILL MODE - fills only missing data)...")

    for idx, row in df.iterrows():
        try:
            res = insert_or_smart_update_product(row)
            if res is None:
                stats["skipped_empty"] += 1
            else:
                action, pid = res
                stats[action] = stats.get(action, 0) + 1
        except Exception as e:
            print(f"Error processing row {idx+1}: {e}")
            conn.rollback()
            stats["error"] += 1
            continue

        processed += 1
        if processed % BATCH_COMMIT_SIZE == 0:
            conn.commit()
            print(f"Committed {processed} rows so far... Stats: {stats}")

    # final commit
    conn.commit()
    print("\n=== IMPORT COMPLETED ===")
    print(f"Total rows processed: {processed}")
    print(f"New products inserted: {stats['inserted']}")
    print(f"Existing products updated (missing data filled): {stats['updated']}")
    print(f"Existing products skipped (already complete): {stats['skipped_ok']}")
    print(f"Empty rows skipped: {stats['skipped_empty']}")
    print(f"Errors: {stats['error']}")

    cursor.close()
    conn.close()

if __name__ == "__main__":
    main()