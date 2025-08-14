import os
import sys
import random
import requests
import re
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from pdf2image import convert_from_path
from PyPDF2 import PdfReader
from rembg import remove
from duckduckgo_search import DDGS  # NEW
import pytesseract

# --- CONFIGURATION ---
PDF_PATH = "manual.pdf"  # Path to your PDF file
OUTPUT_DIR = "output_images"
FONT_PATH = "OpenSans-Bold.ttf"  # Adjust as needed

# --- PDF PROCESSING ---
def extract_pages(pdf_path):
    reader = PdfReader(pdf_path)
    num_pages = len(reader.pages)
    if num_pages < 6:
        raise ValueError("PDF must have at least 6 pages.")

    # Helper to check if a page is blank
    def is_blank(page):
        text = page.extract_text()
        return not text or not text.strip()

    # Always include the first page if not blank
    pages_to_extract = []
    if not is_blank(reader.pages[0]):
        pages_to_extract.append(0)

    # Select 4 random, evenly spaced non-blank pages (excluding first)
    interval = (num_pages - 1) // 4
    candidates = [i for i in range(1, num_pages)]
    selected = []
    for i in range(4):
        idx = min(1 + i * interval, num_pages - 1)
        # Find the next non-blank page from idx
        for j in range(idx, num_pages):
            if not is_blank(reader.pages[j]):
                if j not in selected:
                    selected.append(j)
                break
    pages_to_extract += selected
    return pages_to_extract

def save_pages_as_images(pdf_path, pages, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    images = convert_from_path(pdf_path, first_page=1, last_page=max(pages)+1)
    saved_paths = []
    for i, page_num in enumerate(pages):
        img = images[page_num]
        img_path = os.path.join(output_dir, f"page_{page_num+1}.png")
        img.save(img_path)
        saved_paths.append(img_path)
    return saved_paths

# --- INTERNET IMAGE SEARCH (using DuckDuckGo, no API key needed) ---
def search_product_image(query):
    with DDGS() as ddgs:
        results = ddgs.images(query, max_results=20)
        results = list(results)
        for result in results:
            img_url = result.get("image")
            title = (result.get("title") or "").lower()
            # Filter out likely manual/diagram images by keywords in title
            if any(word in title for word in ["diagram", "schematic", "instruction", "wiring", "circuit"]):
                continue
            if result.get("width", 0) < 200 or result.get("height", 0) < 200:
                continue
            try:
                response = requests.get(img_url, timeout=10)
                response.raise_for_status()
                img = Image.open(BytesIO(response.content)).convert("RGB")
                # Use pytesseract to check for significant text in the image
                text = pytesseract.image_to_string(img)
                if len(text.strip()) > 10:
                    continue
                img.verify()
                img = Image.open(BytesIO(response.content))
                return img
            except Exception:
                continue
        raise Exception("No valid image found in search results.")

def search_brand_logo(brand_name):
    # Search for the brand logo using DuckDuckGo
    with DDGS() as ddgs:
        results = ddgs.images(f"{brand_name} logo", max_results=10)
        results = list(results)
        for result in results:
            img_url = result.get("image")
            if result.get("width", 0) < 100 or result.get("height", 0) < 100:
                continue
            try:
                response = requests.get(img_url, timeout=10)
                response.raise_for_status()
                img = Image.open(BytesIO(response.content)).convert("RGBA")
                # Use pytesseract to check for significant text in the image (skip if too much text)
                text = pytesseract.image_to_string(img)
                if len(text.strip()) > 20:
                    continue
                img.verify()
                img = Image.open(BytesIO(response.content)).convert("RGBA")
                return img
            except Exception:
                continue
        raise Exception("No valid logo image found.")

# --- REMOVE BACKGROUND (using rembg) ---
def remove_background(img):
    # Remove background using rembg
    img_no_bg = remove(img)
    img_no_bg = img_no_bg.convert("RGBA")

    from PIL import ImageDraw, ImageFilter

    # Get alpha channel and bounding box of the object
    alpha = img_no_bg.split()[-1]
    bbox = alpha.getbbox()
    if not bbox:
        return img_no_bg

    # Crop to object for easier shadow placement
    obj = img_no_bg.crop(bbox)
    obj_w, obj_h = obj.size

    # Shadow parameters
    shadow_height = max(18, obj_h // 18)
    shadow_width = int(obj_w * 0.8)
    shadow_offset_y = shadow_height // 6  # raise the shadow a bit more
    shadow_alpha = 110  # max shadow opacity
    feather = max(2, shadow_height // 8)  # just a tiny feather

    # Create a new canvas with extra space at the bottom for the shadow
    extra_bottom = shadow_height + feather + shadow_offset_y
    canvas_h = obj_h + extra_bottom
    canvas_w = obj_w
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (255, 255, 255, 0))

    # Create a shadow image with a tiny feather
    shadow_img_w = shadow_width + feather * 2
    shadow_img_h = shadow_height + feather * 2
    shadow = Image.new("L", (shadow_img_w, shadow_img_h), 0)
    ellipse_box = [feather, feather, feather + shadow_width, feather + shadow_height]
    ImageDraw.Draw(shadow).ellipse(ellipse_box, fill=shadow_alpha)
    if feather > 0:
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=feather))

    # Convert shadow to RGBA with black color and alpha from the mask
    shadow_rgba = Image.new("RGBA", (shadow_img_w, shadow_img_h), (0, 0, 0, 0))
    shadow_rgba.putalpha(shadow)

    # Position shadow: centered horizontally, slightly behind and below the object
    shadow_x = (canvas_w - shadow_img_w) // 2
    shadow_y = obj_h - shadow_height // 3 + shadow_offset_y

    # Paste shadow and then object
    canvas.paste(shadow_rgba, (shadow_x, shadow_y), shadow_rgba)
    canvas.paste(obj, (0, 0), obj)

    return canvas

# --- ADD TEXT TO IMAGE ---
def add_text_to_image(img, title, product_number, brand_logo=None):
    thumb_size = (1140, 1475)
    margin_x = 150  # left/right margin
    margin_y = 300  # top/bottom margin

    # Format product name as title case
    product_name = product_number.title()

    # Top text: "Service Repair Manual" and product name
    top_text = f"Service Repair Manual\n{product_name}"
    bottom_text = "Instant download!"

    # Colors
    royal_blue = (65, 105, 225)
    firetruck_red = (206, 32, 41)

    # Create white background
    bg = Image.new("RGBA", thumb_size, (255, 255, 255, 255))
    img = img.convert("RGBA")
    draw = ImageDraw.Draw(bg)

    # Dynamically fit font for top text (make it as big as possible)
    def fit_font(draw, text, max_width, max_height, font_path, max_font_size):
        font_size = max_font_size
        while font_size > 10:
            font = ImageFont.truetype(font_path, font_size)
            bbox = draw.multiline_textbbox((0, 0), text, font=font)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            if w <= max_width and h <= max_height:
                return font, (w, h)
            font_size -= 1
        return ImageFont.truetype(font_path, 10), (0, 0)

    def fit_singleline_font(draw, text, max_width, max_height, font_path, max_font_size):
        font_size = max_font_size
        while font_size > 10:
            font = ImageFont.truetype(font_path, font_size)
            bbox = draw.textbbox((0, 0), text, font=font)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            if w <= max_width and h <= max_height:
                return font, (w, h)
            font_size -= 1
        return ImageFont.truetype(font_path, 10), (0, 0)

    # Make top text as large as possible, up to 200px tall
    max_top_text_height = 200
    max_bottom_text_height = 100

    top_font, (top_text_w, top_text_h) = fit_font(
        draw, top_text, thumb_size[0] - 2 * margin_x, max_top_text_height, FONT_PATH, 110
    )
    bottom_font, (bottom_text_w, bottom_text_h) = fit_singleline_font(
        draw, bottom_text, thumb_size[0] - 2 * margin_x, max_bottom_text_height, FONT_PATH, 80
    )

    # --- Handle brand logo ---
    logo_h = 0
    logo_margin = 30
    logo_img = None
    if brand_logo is not None:
        # Remove background from logo
        logo_img = remove(brand_logo).convert("RGBA")
        # Resize logo to fit width and max height
        max_logo_width = thumb_size[0] - 2 * margin_x
        max_logo_height = 120
        logo_ratio = logo_img.width / logo_img.height
        if logo_img.width > max_logo_width:
            logo_w = max_logo_width
            logo_h = int(logo_w / logo_ratio)
        else:
            logo_w = logo_img.width
            logo_h = logo_img.height
        if logo_h > max_logo_height:
            logo_h = max_logo_height
            logo_w = int(logo_h * logo_ratio)
        logo_img = logo_img.resize((logo_w, logo_h), Image.LANCZOS)
    else:
        logo_h = 0
        logo_margin = 0

    # Calculate available area for image (centered layout, tight to text)
    available_height = thumb_size[1] - (logo_h + logo_margin + top_text_h + bottom_text_h + 2 * margin_y)
    available_width = thumb_size[0] - 2 * margin_x

    # Resize image to fit
    img_ratio = img.width / img.height
    box_ratio = available_width / available_height
    if img_ratio > box_ratio:
        new_width = available_width
        new_height = int(new_width / img_ratio)
    else:
        new_height = available_height
        new_width = int(new_height * img_ratio)
    img_resized = img.resize((new_width, new_height), Image.LANCZOS)

    # Compute total content height (tight layout)
    spacing = 18  # small space between top text and image, and image and bottom text
    total_content_height = logo_h + logo_margin + top_text_h + spacing + img_resized.height + spacing + bottom_text_h

    # Compute starting y to center all content within the margins
    start_y = margin_y

    # Draw brand logo if available
    if logo_img is not None:
        logo_x = (thumb_size[0] - logo_img.width) // 2
        logo_y = start_y
        bg.paste(logo_img, (logo_x, logo_y), logo_img)
        top_text_y = logo_y + logo_img.height + logo_margin
    else:
        top_text_y = start_y

    # Draw top text (royal blue)
    top_text_x = (thumb_size[0] - top_text_w) // 2
    draw.multiline_text((top_text_x, top_text_y), top_text, font=top_font, fill=royal_blue, align="center")

    # Paste image (centered, tight to top text)
    img_x = (thumb_size[0] - new_width) // 2
    img_y = top_text_y + top_text_h + spacing
    bg.paste(img_resized, (img_x, img_y), img_resized)

    # Draw bottom text (firetruck red)
    bottom_text_x = (thumb_size[0] - bottom_text_w) // 2
    bottom_text_y = img_y + img_resized.height + spacing
    # Ensure at least margin at the bottom
    max_bottom_y = thumb_size[1] - margin_y - bottom_text_h
    if bottom_text_y > max_bottom_y:
        bottom_text_y = max_bottom_y
    draw.text((bottom_text_x, bottom_text_y), bottom_text, font=bottom_font, fill=firetruck_red)

    return bg.convert("RGB")

def extract_product_number_from_first_page(pdf_path):
    # Convert first page to image
    images = convert_from_path(pdf_path, first_page=1, last_page=2)
    first_page_img = images[0]
    # OCR the image
    text = pytesseract.image_to_string(first_page_img)
    # Adjust the regex as needed for your product number format
    match = re.search(r'\b[A-Z]{2}\d[A-Z]\b', text)
    if match:
        return match.group(0)
    return "Unknown"

# --- MAIN ---
def main():
    # 1. Extract PDF metadata
    reader = PdfReader(PDF_PATH)
    title = reader.metadata.title or "Manual"
    # Try to extract product number from first page text
    product_number = extract_product_number_from_first_page(PDF_PATH)

    # Prompt user if product number is unknown
    if product_number == "Unknown":
        product_number = input("Product number could not be detected. Please enter the product number: ")

    # 2. Extract pages
    pages = extract_pages(PDF_PATH)
    saved_paths = save_pages_as_images(PDF_PATH, pages, OUTPUT_DIR)
    print("Saved PDF pages as images:", saved_paths)

    # 3. Search for product image (no API key needed)
    query = f"{title} {product_number}"
    product_img = search_product_image(query)
    print("Downloaded product image.")

    # 4. Remove background
    product_img_no_bg = remove_background(product_img)
    print("Removed background from product image.")

    # 5. Search for brand logo and remove background
    brand_name = title.split()[0] if title.split() else product_number.split()[0]
    try:
        brand_logo_img = search_brand_logo(brand_name)
        print("Downloaded and processed brand logo.")
    except Exception:
        brand_logo_img = None
        print("Brand logo not found.")

    # 6. Add text and logo
    final_img = add_text_to_image(product_img_no_bg.convert("RGBA"), title, product_number, brand_logo=brand_logo_img)
    final_img_path = os.path.join(OUTPUT_DIR, "product_image_final.png")
    final_img.save(final_img_path)
    print(f"Saved final product image: {final_img_path}")

if __name__ == "__main__":
    main()