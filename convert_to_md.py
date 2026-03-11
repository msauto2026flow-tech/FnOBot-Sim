"""Utility for converting Word/Excel documents to Markdown.

Usage (from repo root):

    python -m fnobot.convert_to_md path/to/file.docx
    python -m fnobot.convert_to_md path/to/file.xlsx

The script will write a `.md` file alongside the input with the same base
name.  For Word documents it preserves paragraph text and simple headings.
For spreadsheets it converts each sheet to a markdown table (using pandas).
"""

import sys
import os
from pathlib import Path


def docx_to_markdown(src: Path, dst: Path):
    from docx import Document

    doc = Document(src)
    lines = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            lines.append("")
            continue
        # naive heading detection: bold/size? just use raw text
        lines.append(text)
    dst.write_text("\n".join(lines), encoding="utf-8")


def xlsx_to_markdown(src: Path, dst: Path):
    import pandas as pd

    xl = pd.ExcelFile(src)
    out_lines = []
    for sheet in xl.sheet_names:
        df = xl.parse(sheet)
        out_lines.append(f"## {sheet}")
        if df.empty:
            out_lines.append("*(empty sheet)*")
        else:
            out_lines.append(df.to_markdown(index=False))
        out_lines.append("\n")
    dst.write_text("\n".join(out_lines), encoding="utf-8")


def pdf_to_markdown(src: Path, dst: Path):
    """Extract text from a PDF and write as plain markdown."""
    from PyPDF2 import PdfReader

    reader = PdfReader(str(src))
    lines = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            lines.append(text)
    dst.write_text("\n\n".join(lines), encoding="utf-8")


def _convert_file(arg: str):
    path = Path(arg)
    if not path.exists():
        print(f"File not found: {path}")
        return
    ext = path.suffix.lower()
    out = path.with_suffix(path.suffix + ".md")
    try:
        if ext in [".docx"]:
            docx_to_markdown(path, out)
            print(f"Converted {path} -> {out}")
        elif ext in [".xlsx", ".xls"]:
            xlsx_to_markdown(path, out)
            print(f"Converted {path} -> {out}")
        elif ext == ".pdf":
            pdf_to_markdown(path, out)
            print(f"Converted {path} -> {out}")
        else:
            print(f"Unsupported file type: {path}")
    except Exception as e:
        print(f"Error converting {path}: {e}")


def watch_directory(directories):
    """Monitor one or more directories and auto-convert new supported files."""
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    import time

    class _Handler(FileSystemEventHandler):
        def on_created(self, event):
            if event.is_directory:
                return
            for ext in (".docx", ".xlsx", ".xls", ".pdf"):
                if event.src_path.lower().endswith(ext):
                    print(f"Detected new file: {event.src_path}")
                    _convert_file(event.src_path)
        # also handle copies that may appear as modifications
        def on_modified(self, event):
            if event.is_directory:
                return
            for ext in (".docx", ".xlsx", ".xls", ".pdf"):
                if event.src_path.lower().endswith(ext):
                    print(f"Detected modified file: {event.src_path}")
                    _convert_file(event.src_path)

    observer = Observer()
    handler = _Handler()
    for d in directories:
        observer.schedule(handler, str(d), recursive=True)
    observer.start()
    print(f"Watching {directories} for new documents... (Ctrl-C to stop)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m fnobot.convert_to_md [--watch <dir> …] <file> [...]")
        sys.exit(1)

    args = sys.argv[1:]
    if args[0] == "--watch":
        dirs = []
        i = 1
        while i < len(args) and not args[i].startswith("-"):
            dirs.append(Path(args[i]))
            i += 1
        if not dirs:
            print("Specify at least one directory to watch after --watch")
            sys.exit(1)
        watch_directory(dirs)
        return

    for arg in args:
        _convert_file(arg)


if __name__ == "__main__":
    main()
