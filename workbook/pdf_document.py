"""Publish one atomic PDF with AC writing cells in its page headers."""
import os
import tempfile
from pathlib import Path

def export(path,rows,date,settings,draft=False,*,renderer=None):
    if renderer is None:
        from .core import export_pdf
        renderer=export_pdf
    from pypdf import PdfReader
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.workbook-',dir=path.parent) as folder:
        staged=Path(folder)/'complete.pdf'
        summary=renderer(staged,rows,date,settings,draft=draft)
        with staged.open('rb') as source:
            if len(PdfReader(source).pages)!=summary['pages']:raise ValueError('PDF 頁數驗證失敗，未發布檔案。')
        os.replace(staged,path)
    return summary
