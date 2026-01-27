# Automated E-Commerce Data Scraping & AI Content Enhancement System

## 1. Executive Summary
This project involves the development of a robust automated web scraping and data processing system designed to aggregate product data from multiple e-commerce platforms (DCC Bazar and Korean Mart). Beyond simple data extraction, the system integrates Artificial Intelligence (OpenAI API) to enhance product listings with SEO-optimized short descriptions. The solution streamlines the process of catalog management by automating data collection, cleaning, content generation, and database population.

## 2. Technical Architecture & Stack
*   **Programming Language:** Python
*   **Web Scraping:** `requests`, `BeautifulSoup4 (bs4)`, `lxml`
*   **Data Manipulation:** `pandas`, `openpyxl`
*   **AI Integration:** OpenAI API (GPT models)
*   **Concurrency:** Python `threading` and `concurrent.futures` (ThreadPoolExecutor)
*   **Database:** SQL (via generated scripts and direct updates)

## 3. Key Modules & Functionalities

### A. Multi-Site Web Scraping Engine
Two dedicated scraping modules were developed to handle different e-commerce site structures:
*   **DCC Bazar Scraper (`DCCbazar.py`):**
    *   **Target:** Scrapes 7+ specific categories (e.g., baby food, skincare, toys).
    *   **Extraction:** Captures Product Name, Price, Offer Price, Description, Image URLs, and Category.
    *   **Robustness:** Implements error handling for missing elements and network issues, ensuring the scraper continues running even if individual items fail. It supports resuming/appending to existing datasets.
*   **Korean Mart Scraper (`KoreanMart.py`):**
    *   **Target:** specialized scraping for beauty and food products.
    *   **Advanced Extraction:** Handles complex HTML structures to extract detailed attributes like Brand, Skin Type, Size, and Volume from tabular data.

### B. AI-Powered Content Enhancement
*   **Module:** `DCCBazar_short_description_generator_using_api.py`
*   **Functionality:** enhancing raw scraped data by generating professional, SEO-friendly short descriptions (50-80 words).
*   **Performance:** Utilizes a **multi-threaded architecture** (5 concurrent workers) to process API requests in parallel, significantly reducing the time required to process large datasets.
*   **Safety:** Implements thread locking (`threading.Lock`) to ensure safe concurrent writes to the Excel dataset.

### C. Data Management & Storage
*   **Image Processing (`DccBazarImageSave.py`):** Automated downloading and organization of product images into a local directory (`product_images/`).
*   **Database Integration (`Insert_script_DCCbazar.py`):** Scripts to transform the cleaned and enhanced data into SQL formats for direct injection into the production database.

## 4. Key Achievements / Learning Outcomes
*   **Automation:** Reduced manual data entry time by automating the collection of thousands of products.
*   **Data Engineering:** Gained experience in cleaning unstructured HTML data and structuring it into usable formats (Excel/SQL).
*   **AI Integration:** Successfully integrated Large Language Models (LLMs) into a data pipeline to add value (content generation) to raw data.
*   **Optimization:** Implemented concurrent processing to optimize network-bound tasks (API calls), demonstrating understanding of efficient software design.
