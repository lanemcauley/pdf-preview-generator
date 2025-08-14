import os
import sys
import random
import requests
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from pdf2image import convert_from_path
from PyPDF2 import PdfReader
from rembg import remove

# --- CONFIGURATION ---
PDF_PATH = "manual.pdf"  # Path to your PDF file
OUTPUT_DIR = "output_images"
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"  # Adjust as needed

# --- PDF PROCESSING ---
def extract_pages(pdf_path):
    reader = PdfReader(pdf_path)
    num_pages = len(reader.pages)
    if num_pages < 6:
        raise ValueError("PDF must have at least 6 pages.")

    # Assume index page is page 0
    index_page = 0

    # Select 4 random, evenly spaced pages (excluding index)
    interval = (num_pages - 1) // 4
    random_pages = [index_page + interval * i + 1 for i in range(4)]
    random_pages = [min(p, num_pages - 1) for p in random_pages]

    pages_to_extract = [index_page] + random_pages
    return pages_to_extract

def save_pages_as_images(pdf_path, pages, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    images = convert_from_path(pdf_path, first_page=1, last_page=max(pages)+1)
    saved_paths = []
    for i, page_num in enumerate(pages):
        img = images[page_num]
        page_dir = os.path.join(output_dir, f"page_{page_num+1}")
        os.makedirs(page_dir, exist_ok=True)
        img_path = os.path.join(page_dir, f"page_{page_num+1}.png")
        img.save(img_path)
        saved_paths.append(img_path)
    return saved_paths

# --- INTERNET IMAGE SEARCH (using Bing Image Search API as an example) ---
def search_product_image(query, api_key):
    endpoint = "https://api.bing.microsoft.com/v7.0/images/search"
    headers = {"Ocp-Apim-Subscription-Key": api_key}
    params = {"q": query, "count": 1, "imageType": "Photo"}
    response = requests.get(endpoint, headers=headers, params=params)
    response.raise_for_status()
    results = response.json()
    if results["value"]:
        img_url = results["value"][0]["contentUrl"]
        img_data = requests.get(img_url).content
        return Image.open(BytesIO(img_data))
    else:
        raise Exception("No image found.")

# --- REMOVE BACKGROUND (using rembg) ---
def remove_background(img):
    img_no_bg = remove(img)
    return Image.open(BytesIO(img_no_bg))

# --- ADD TEXT TO IMAGE ---
def add_text_to_image(img, title, product_number):
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_PATH, 40)
    text = f"{title}\nProduct: {product_number}"
    text_w, text_h = draw.multiline_textsize(text, font=font)
    x = (img.width - text_w) // 2
    y = img.height - text_h - 20
    draw.rectangle([x-10, y-10, x+text_w+10, y+text_h+10], fill=(0,0,0,128))
    draw.multiline_text((x, y), text, font=font, fill="white", align="center")
    return img

# --- MAIN ---
def main():
    # 1. Extract PDF metadata
    reader = PdfReader(PDF_PATH)
    title = reader.metadata.title or "Manual"
    product_number = reader.metadata.subject or "Unknown"

    # 2. Extract pages
    pages = extract_pages(PDF_PATH)
    saved_paths = save_pages_as_images(PDF_PATH, pages, OUTPUT_DIR)
    print("Saved PDF pages as images:", saved_paths)

    # 3. Search for product image
    api_key = os.getenv("BING_IMAGE_SEARCH_KEY")
    if not api_key:
        print("Set BING_IMAGE_SEARCH_KEY environment variable.")
        sys.exit(1)
    query = f"{title} {product_number}"
    product_img = search_product_image(query, api_key)
    print("Downloaded product image.")

    # 4. Remove background
    product_img_no_bg = remove_background(product_img)
    print("Removed background from product image.")

    # 5. Add text
    final_img = add_text_to_image(product_img_no_bg.convert("RGBA"), title, product_number)
    final_img_path = os.path.join(OUTPUT_DIR, "product_image_final.png")
    final_img.save(final_img_path)
    print(f"Saved final product image: {final_img_path}")

if __name__ == "__main__":
    main()