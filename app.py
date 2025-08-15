import os
import sys
import glob
import shutil
import tempfile
from tkinter import Tk, Label, Button, Frame, filedialog, messagebox, PhotoImage
from tkinter.ttk import Style
from PIL import Image, ImageTk
import fitz
import PyPDF2  # <-- Add this import

# Helper to get PDF page count using PyPDF2
def get_pdf_page_count(pdf_path):
    with open(pdf_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        return len(reader.pages)

# Helper to find first PDF in current directory
def find_first_pdf():
    pdfs = glob.glob("*.pdf")
    return pdfs[0] if pdfs else None

# Helper to extract 10 images from PDF (using pdf2image for images, PyPDF2 for page count)
def extract_preview_images(pdf_path):
    total_pages = get_pdf_page_count(pdf_path)
    if total_pages < 1:
        raise Exception("PDF has no pages.")

    selected_indices = [0]
    if total_pages > 1:
        step = (total_pages - 1) / 9
        for i in range(9):
            idx = int(round(1 + i * step))
            idx = min(idx, total_pages - 1)
            selected_indices.append(idx)
    else:
        selected_indices += [0] * 9

    # Remove duplicates while preserving order
    seen = set()
    unique_indices = []
    for idx in selected_indices:
        if idx not in seen:
            unique_indices.append(idx)
            seen.add(idx)
        else:
            for alt in range(total_pages):
                if alt not in seen:
                    unique_indices.append(alt)
                    seen.add(alt)
                    break

    while len(unique_indices) < 10:
        unique_indices.append(0)

    doc = fitz.open(pdf_path)
    images = []
    for i in range(total_pages):
        page = doc.load_page(i)
        pix = page.get_pixmap(dpi=150)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(img)

    return images, unique_indices[:10]

def select_pdf_file():
    pdfs = glob.glob("*.pdf")
    if not pdfs:
        messagebox.showerror("No PDF Found", "No PDF file found in this directory.")
        sys.exit(1)
    root = Tk()
    root.withdraw()
    file = filedialog.askopenfilename(
        title="Select a PDF file",
        filetypes=[("PDF files", "*.pdf")],
        initialdir=os.getcwd()
    )
    root.destroy()
    return file if file else None

def process_pdf(pdf_path):
    root = Tk()
    app = PDFPreviewApp(root, pdf_path)
    root.mainloop()

class PDFPreviewApp:
    def __init__(self, root, pdf_path):
        self.root = root
        self.pdf_path = pdf_path
        self.images, self.page_indices = extract_preview_images(pdf_path)
        self.total_pages = len(self.images)
        self.thumbnails = []
        self.thumbnail_labels = []
        self.selected_pages = list(self.page_indices)
        self.tempdir = tempfile.mkdtemp()
        self.success = False
        self.error_msg = ""
        self.setup_ui()

    def setup_ui(self):
        self.root.title("PDF Preview Generator")
        self.frame = Frame(self.root)
        self.frame.pack(padx=10, pady=10)
        Label(self.frame, text="Click an image to select next page.").pack()
        self.img_frame = Frame(self.frame)
        self.img_frame.pack()
        self.load_thumbnails()
        self.confirm_btn = Button(self.frame, text="Confirm", command=self.on_confirm)
        self.confirm_btn.pack(pady=10)

    def load_thumbnails(self):
        for widget in self.img_frame.winfo_children():
            widget.destroy()
        self.thumbnails.clear()
        self.thumbnail_labels.clear()
        for i, page_idx in enumerate(self.selected_pages):
            img = self.images[page_idx].copy()
            img.thumbnail((120, 160))
            thumb = ImageTk.PhotoImage(img)
            self.thumbnails.append(thumb)
            lbl = Label(self.img_frame, image=thumb, borderwidth=2, relief="groove")
            lbl.grid(row=0, column=i, padx=5, pady=5)
            lbl.bind("<Button-1>", lambda e, idx=i: self.on_thumbnail_click(idx))
            self.thumbnail_labels.append(lbl)

    def on_thumbnail_click(self, idx):
        # Advance to next page (wrap around)
        current_page = self.selected_pages[idx]
        next_page = (current_page + 1) % self.total_pages
        self.selected_pages[idx] = next_page
        self.load_thumbnails()

    def on_confirm(self):
        try:
            base_name = os.path.splitext(os.path.basename(self.pdf_path))[0]
            out_folder = os.path.join(os.getcwd(), f"pdf_preview_images_{base_name}")
            if os.path.exists(out_folder):
                shutil.rmtree(out_folder)
            os.makedirs(out_folder)
            for i, page_idx in enumerate(self.selected_pages):
                img = self.images[page_idx]
                out_path = os.path.join(out_folder, f"page_{i+1}.png")
                img.save(out_path, "PNG")
            self.success = True
            self.error_msg = ""
            self.show_result("Success", f"Images saved to {out_folder}")
        except Exception as e:
            self.success = False
            self.error_msg = str(e)
            self.show_result("Failed", f"Failed to save images: {e}")

    def show_result(self, title, msg):
        result_win = Tk()
        result_win.title(title)
        Label(result_win, text=msg, wraplength=400).pack(padx=20, pady=20)
        Button(result_win, text="OK", command=lambda: self.close_all(result_win)).pack(pady=10)
        result_win.mainloop()

    def close_all(self, win):
        win.destroy()
        self.root.destroy()
        shutil.rmtree(self.tempdir, ignore_errors=True)

def main():
    # Check for required modules
    try:
        import pdf2image
        from PIL import Image
        import PyPDF2
        from Crypto.Cipher import AES
    except ImportError:
        messagebox.showerror("Missing Dependency", "This program requires pdf2image, Pillow, and PyPDF2.")
        sys.exit(1)

    # Ask user: single file or all files
    root = Tk()
    root.withdraw()
    choice = messagebox.askyesno("PDF Preview Generator", "Process ALL PDFs in this folder?\n\nYes = All PDFs\nNo = Select one PDF")
    root.destroy()

    if choice:
        pdfs = glob.glob("*.pdf")
        if not pdfs:
            messagebox.showerror("No PDF Found", "No PDF file found in this directory.")
            sys.exit(1)
        for pdf_path in pdfs:
            process_pdf(pdf_path)
    else:
        pdf_path = select_pdf_file()
        if not pdf_path:
            sys.exit(0)
        process_pdf(pdf_path)

if __name__ == "__main__":
    main()