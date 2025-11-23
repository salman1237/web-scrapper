import requests
from bs4 import BeautifulSoup
from openpyxl import Workbook
import time

class Product:
    def __init__(self, name=None, category=None, type_=None, brand=None, size=None, price=None, offer_price=None, description=None):
        self.name = name or ""
        self.category = category or ""
        self.type = type_ or ""
        self.brand = brand or ""
        self.size = size or ""
        self.price = price or 0
        self.offer_price = offer_price or 0
        self.description = description or ""

    def to_list(self):
        return [self.name, self.category, self.type, self.brand, self.size, self.price, self.offer_price, self.description]

# List of categories to scrape
categories = ['skin-care', 'food', 'makeup', 'supplement']
base_url = 'https://koreanmartbd.com/product-category/'

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'
}

all_products = []

for category in categories:
    print(f"\n=== Scraping category: {category} ===")
    
    category_url = f"{base_url}{category}/"
    
    try:
        r = requests.get(category_url, headers=headers)
        soup = BeautifulSoup(r.content, 'lxml')

        productlist = soup.find_all('div', class_='product-element-top')
        productURLs = []

        for item in productlist:
            url = item.find('a')
            if url and 'href' in url.attrs:
                productURLs.append(url['href'])

        print(f"Found {len(productURLs)} products in {category} category")

        for i, link in enumerate(productURLs):
            try:
                print(f"Processing product {i+1}/{len(productURLs)} in {category}")
                
                r = requests.get(link, headers=headers)
                soup = BeautifulSoup(r.content, 'lxml')

                # Get product name with error handling
                try:
                    p_name = soup.find('h1', class_='product_title entry-title wd-entities-title').text.strip()
                except (AttributeError, IndexError):
                    p_name = ""

                # Get product description with error handling
                try:
                    p_desc = soup.find('div', class_='woocommerce-Tabs-panel panel entry-content wc-tab woocommerce-Tabs-panel--description color-scheme-dark').text.strip()
                except (AttributeError, IndexError):
                    p_desc = ""

                # Get product brand with error handling
                try:
                    p_brand = soup.find('div', class_='woocommerce-Tabs-panel panel entry-content wc-tab woocommerce-Tabs-panel--additional_information color-scheme-dark wd-single-attrs wd-layout-list wd-style-bordered').find('tr', class_='woocommerce-product-attributes-item woocommerce-product-attributes-item--attribute_pa_brand').find('td', class_='woocommerce-product-attributes-item__value').text.strip()
                except (AttributeError, IndexError):
                    p_brand = ""

                # Get product type with error handling
                try:
                    p_type = soup.find('div', class_='woocommerce-Tabs-panel panel entry-content wc-tab woocommerce-Tabs-panel--additional_information color-scheme-dark wd-single-attrs wd-layout-list wd-style-bordered').find('tr', class_='woocommerce-product-attributes-item woocommerce-product-attributes-item--attribute_pa_product-type').find('td', class_='woocommerce-product-attributes-item__value').text.strip()
                except (AttributeError, IndexError):
                    p_type = ""

                # Get product size with error handling
                try:
                    p_size = soup.find('div', class_='woocommerce-Tabs-panel panel entry-content wc-tab woocommerce-Tabs-panel--additional_information color-scheme-dark wd-single-attrs wd-layout-list wd-style-bordered').find('tr', class_='woocommerce-product-attributes-item woocommerce-product-attributes-item--attribute_pa_size').find('td', class_='woocommerce-product-attributes-item__value').text.strip()
                except (AttributeError, IndexError):
                    p_size = ""

                # Get prices with error handling
                p_price = ""
                p_offer_price = ""
                try:
                    price_elements = soup.find('p', class_='price').find_all('bdi')
                    if len(price_elements) >= 1:
                        p_price = price_elements[0].find(string=True, recursive=False).strip()
                    if len(price_elements) >= 2:
                        p_offer_price = price_elements[1].find(string=True, recursive=False).strip()
                except (AttributeError, IndexError):
                    pass

                # Create product with category
                product = Product(
                    name=p_name,
                    description=p_desc,
                    brand=p_brand,
                    size=p_size,
                    price=p_price,
                    offer_price=p_offer_price,
                    type_=p_type,
                    category=category.replace('-', ' ').title()  # Convert 'skin-care' to 'Skin Care'
                )

                all_products.append(product)
                print(f"✓ Successfully scraped: {p_name}")

                # Add a small delay to be respectful to the server
                time.sleep(1)

            except Exception as e:
                print(f"✗ Error processing {link}: {str(e)}")
                continue

    except Exception as e:
        print(f"✗ Error accessing category {category}: {str(e)}")
        continue

print(f"\n=== Scraping Complete ===")
print(f"Total products scraped across all categories: {len(all_products)}")

# Save to Excel file
def save_to_excel(products, filename="koreanmart_products.xlsx"):
    wb = Workbook()
    ws = wb.active
    ws.title = "Products"
    
    # Headers
    headers = ["Name", "Category", "Type", "Brand", "Size", "Price", "Offer Price", "Description"]
    ws.append(headers)
    
    # Data
    for product in products:
        ws.append(product.to_list())
    
    # Auto-adjust column widths
    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = (max_length + 2)
        ws.column_dimensions[column_letter].width = adjusted_width
    
    wb.save(filename)
    print(f"Data saved to {filename}")

# Save all products to Excel
save_to_excel(all_products)

# Print summary by category
from collections import defaultdict
category_summary = defaultdict(int)
for product in all_products:
    category_summary[product.category] += 1

print("\n=== Category Summary ===")
for category, count in category_summary.items():
    print(f"{category}: {count} products")