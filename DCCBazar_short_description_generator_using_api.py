import pandas as pd
from openai import OpenAI
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# Initialize OpenAI client
client = OpenAI(api_key="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")  # Replace with your actual API key

file_path = "DCC_bazar_products.xlsx"

# Load Excel
df = pd.read_excel(file_path)

# Create column if missing
if "Short Description" not in df.columns:
    df["Short Description"] = ""

lock = threading.Lock()  # To protect Excel saving


def generate_short_description(index, row):
    # Skip if already filled
    if isinstance(row["Short Description"], str) and row["Short Description"].strip():
        return index, row["Short Description"], "skipped"

    prompt = f"""
Act as a professional e-commerce SEO copywriter. Create a compelling short product description (50–80 words).

Product Information:
- Name: {row['Name']}
- Category: {row['Category']}
- Current Description: {row['Description']}

Requirements:
- Start with the main benefit
- Include key features
- Use SEO keywords naturally
- Maintain a persuasive tone
"""

    try:
        response = client.chat.completions.create(
            model="gpt-5-nano",
            messages=[
                {"role": "system", "content": "You are an expert e-commerce copywriter specializing in SEO-optimized product descriptions."},
                {"role": "user", "content": prompt}
            ],
        )
        desc = response.choices[0].message.content.strip()
        return index, desc, "generated"

    except Exception as e:
        return index, f"ERROR: {e}", "error"


print("🚀 Starting MULTI-THREADED short description generation...\n")

# Thread pool with 5 workers (safe, fast)
executor = ThreadPoolExecutor(max_workers=5)
futures = []

# Submit only the rows that need processing
for index, row in df.iterrows():
    futures.append(executor.submit(generate_short_description, index, row))

# Process completed futures as they finish
for future in as_completed(futures):
    index, desc, status = future.result()

    if status == "skipped":
        print(f"⏩ Row {index+1} already has description → SKIPPED\n")
        continue

    if status == "error":
        print(f"❌ Error in row {index+1}: {desc}\n")
        continue

    # Print result
    print(f"✔ Row {index+1} processed")
    print(desc)
    print("-----------------------------------------------------\n")

    # Save in Excel (MAIN THREAD ONLY)
    with lock:
        df.at[index, "Short Description"] = desc
        df.to_excel(file_path, index=False)
        print(f"💾 Saved row {index+1} to Excel.\n")

print("✅ All done! Multi-threading completed successfully.")
