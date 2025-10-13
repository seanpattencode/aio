#!/usr/bin/env python3
import sys
import subprocess
from pathlib import Path
from PyPDF2 import PdfReader, PdfWriter
from concurrent.futures import ThreadPoolExecutor

def save_page(args):
    reader, page_num, output_dir = args
    writer = PdfWriter()
    writer.add_page(reader.pages[page_num])
    with open(output_dir / f"page_{page_num + 1:04d}.pdf", "wb") as f:
        writer.write(f)

def transcribe_page(pdf_path, output_dir="transcriptions"):
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)

    result = subprocess.run(
        ["claude", "--dangerously-skip-permissions"],
        input=f"Read this file and transcribe it. Remove headers, footers, page numbers, and section labels like 'INTRODUCTION xix'. For any graphs/charts/images, include a description in the format 'Graph: [description]'. If the page is blank or has no meaningful content, return empty <transcription></transcription> tags. Return ONLY the main body text wrapped in <transcription></transcription> tags: {pdf_path}",
        text=True,
        capture_output=True
    )

    txt_path = output_dir / f"{Path(pdf_path).stem}.txt"
    txt_path.write_text(result.stdout)
    return result.stdout

def transcribe_range(start, end, pages_dir="pages", transcriptions_dir="transcriptions", joined_dir="joined", workers=10):
    Path(joined_dir).mkdir(exist_ok=True)

    transcriptions = []
    pages = [f"{pages_dir}/page_{i:04d}.pdf" for i in range(start, end + 1)]

    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = executor.map(lambda p: transcribe_page(p, transcriptions_dir), pages)
        transcriptions = list(results)

    cleaned = [t.replace("<transcription>", "").replace("</transcription>", "").strip() for t in transcriptions]
    joined_text = "\n\n".join(cleaned)
    joined_path = Path(joined_dir) / f"pages_{start:04d}-{end:04d}.txt"
    joined_path.write_text(joined_text)
    print(f"Transcribed pages {start}-{end}, saved to {joined_path}")

def split_pdf(pdf_path, output_dir="pages"):
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)

    reader = PdfReader(pdf_path)
    with ThreadPoolExecutor() as executor:
        executor.map(save_page, [(reader, i, output_dir) for i in range(len(reader.pages))])

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python split_pdf.py <pdf_file> [output_dir]")
        print("   or: python split_pdf.py transcribe <start> <end> [workers]")
        sys.exit(1)

    if sys.argv[1] == "transcribe":
        start = int(sys.argv[2])
        end = int(sys.argv[3])
        workers = int(sys.argv[4]) if len(sys.argv) > 4 else 10
        transcribe_range(start, end, workers=workers)
    else:
        pdf_path = sys.argv[1]
        output_dir = sys.argv[2] if len(sys.argv) > 2 else "pages"
        split_pdf(pdf_path, output_dir)
        print(f"Split {pdf_path} into {output_dir}/")
