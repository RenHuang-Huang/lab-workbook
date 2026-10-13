"""Local AC/PC handwriting sheet, selected from actual items before print folding.

The source codes were verified against the cached Access item dictionary;
neither a print alias of AC nor a panel's *potential* membership selects a row.
"""
import math
import os
from pathlib import Path
from .handwritten import display_work_numbers

AC_CODES=frozenset(('092','0921','09211'))
PC_CODES=frozenset(('093','094','0941'))  # 093 is the dictionary's Glucose PC 1hr.


def column_count(value=5):
    text=str(value).strip()
    if not text.isascii() or not text.isdecimal() or not 1<=int(text)<=10:
        raise ValueError('Glucose AC&PC 填入表每排欄數請輸入 1～10 的整數。')
    return int(text)


def selected_rows(rows):
    def ac(item):
        if str(item.get('type','')).upper()=='G':return False
        name=' '.join(str(item.get('name','')).casefold().split())
        return str(item.get('code','')).strip() in AC_CODES|PC_CODES or name in ('glucose ac','glucose pc','glucose pc 1hr')
    return [row for row in rows if any(ac(item) for item in row.get('source_items',[]))]


def header_plan(rows,settings):
    """Five vertical positions in each of five columns; 25 entries per page."""
    enabled=bool(settings.get('export_glucose_ac',True))
    numbers=[display_work_numbers(row) for row in selected_rows(rows)] if enabled else []
    entries=[dict(page=i//25+1,column=(i%25)//5+1,row=i%5+1,work_numbers=value) for i,value in enumerate(numbers)]
    return dict(enabled=enabled,numbers=numbers,entries=entries,columns=5,rows_per_column=5,capacity=25,
                pages=math.ceil(len(numbers)/25),records=len(numbers),location='header',appended=False)


def draw_header(plan,page,text,line,measure):
    """Use the document's canvas callbacks; no second read or second PDF."""
    if not plan['enabled']:return
    # Keep the number font and the five-by-five order. Only halve the writing
    # line, then center the complete grid (without an extra trailing gutter).
    room=min(22,max(8,max((measure('、'.join(n),11) for n in plan['numbers']),default=8)))
    blank=(34-room)/2
    chunk=plan['numbers'][page*25:(page+1)*25]
    columns=max(1,math.ceil(len(chunk)/5))
    cell=room+1+blank;pitch=cell+3;left=(210-(columns*cell+(columns-1)*3))/2
    title='Glucose AC&PC';title_width=measure(title,9)
    text(title,(210-title_width)/2,8,title_width,9)
    for index,numbers in enumerate(chunk):
        col,row=divmod(index,5);x=left+col*pitch;center=14+row*6
        label='、'.join(numbers)
        text(label,x,center,room,11)
        line(x+room+1,center+1.7,x+cell,center+1.7,'#AAB0B6',.4)
    if not plan['records'] and page==0:
        message='當日無 Glucose AC／PC 項目';message_width=measure(message,8)
        text(message,(210-message_width)/2,14,message_width,8)


def page_plan(rows,settings):
    columns=column_count(settings.get('glucose_ac_columns',5))
    chosen=selected_rows(rows)
    numbers=[display_work_numbers(row) for row in chosen]
    # Keep all work numbers in merge/all mode together beside one writing line.
    pitch=max(8,max((len(n) for n in numbers),default=1)*5+1)
    if pitch>248:raise ValueError('Glucose AC&PC 填入表同筆工作號過多，請改用「只顯示第一個工作號」。')
    rows_per_column=max(1,int(248//pitch));capacity=columns*rows_per_column
    pages=max(1,math.ceil(len(numbers)/capacity))
    return dict(columns=columns,numbers=numbers,pitch=pitch,capacity=capacity,pages=pages)


def export(path,rows,date,settings,*,page_offset=0):
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from .pdf_fonts import PdfFonts
    plan=page_plan(rows,settings)
    columns,numbers,pitch,capacity,pages=(plan[k] for k in ('columns','numbers','pitch','capacity','pages'))
    typefaces=PdfFonts(settings)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.partial.pdf')
    width=190/columns;placements=[]
    try:
        c=canvas.Canvas(str(tmp),pagesize=A4);c.setTitle(f'Glucose AC&PC 填入表 {date}');c.setAuthor('工作簿輸出（本機）')
        def text(value,x,y,size=14,room=None):
            c.saveState();c.setFillColorRGB(.12,.16,.20)
            t=c.beginText(x*mm,A4[1]-y*mm)
            scale=min(100,room*mm/max(.01,typefaces.width(value,size))*100) if room else 100
            typefaces.write(t,value,size,horizontal_scale=scale);c.drawText(t);c.restoreState()
        for page in range(pages):
            text('Glucose AC&PC 填入表',10,16,18)
            text(f'{date}  ·  {len(numbers)} 筆  ·  每排 {columns} 欄',10,24,9)
            chunk=numbers[page*capacity:(page+1)*capacity]
            depth,extra=divmod(len(chunk),columns)
            # Balance columns to use all configured positions when possible,
            # still printing every column top-to-bottom before the next column.
            positions=[(col,line) for col in range(columns) for line in range(depth+(col<extra))]
            for values,(col,line) in zip(chunk,positions):
                x=10+col*width;y=34+line*pitch
                for offset,value in enumerate(values):text(value,x,y+offset*5,14,room=width*.42)
                baseline=y+(len(values)-1)*2.5
                c.setStrokeColorRGB(.55,.58,.62);c.setLineWidth(.5)
                c.line((x+width*.46)*mm,A4[1]-(baseline+.8)*mm,(x+width-2)*mm,A4[1]-(baseline+.8)*mm)
                placements.append(dict(work_numbers=values,page=page_offset+page+1,column=col+1,row=line+1))
            if not chunk:text('當日無 Glucose AC／PC 項目。',10,38,12)
            text('工作號沿用工作簿；由上到下，再往右填寫。',10,289,8)
            text(f'{page_offset+page+1} / {page_offset+pages}',180,289,8)
            c.showPage()
        c.save();os.replace(tmp,path)
    except Exception:
        if tmp.exists():tmp.unlink()
        raise
    return dict(records=len(numbers),pages=pages,columns=columns,order='column_major',entries=placements)
