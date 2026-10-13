"""PDF-only mixed text: fixed-width ASCII, existing CJK for other glyphs."""
import hashlib
from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


WINDOWS_FONTS=Path('C:/Windows/Fonts')


def register(path,role):
    name=role+'_'+hashlib.sha256(str(path.resolve()).encode('utf-8')).hexdigest()[:12]
    if name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(name,str(path),subfontIndex=0))
    return name


class PdfFonts:
    def __init__(self,settings):
        cjk=Path(settings.get('font_path',str(WINDOWS_FONTS/'msjh.ttc')))
        if not cjk.is_file():raise ValueError('找不到中文字型。')
        self.cjk=register(cjk,'WorkbookCJK')
        bold=cjk.with_name('msjhbd.ttc')
        self.cjk_bold=register(bold,'WorkbookCJKBold') if bold.is_file() else self.cjk
        mono=WINDOWS_FONTS/'consola.ttf';mono_bold=WINDOWS_FONTS/'consolab.ttf'
        # Courier is a PDF standard fixed-width face; no downloaded fonts needed.
        self.mono=register(mono,'WorkbookMono') if mono.is_file() else 'Courier'
        self.mono_bold=register(mono_bold,'WorkbookMonoBold') if mono.is_file() and mono_bold.is_file() else self.mono if mono.is_file() else 'Courier-Bold'
        self.mono_family='Consolas' if mono.is_file() else 'Courier'

    def runs(self,value,bold=False):
        cjk,mono=(self.cjk_bold,self.mono_bold) if bold else (self.cjk,self.mono)
        result=[]
        for char in str(value):
            face=mono if ' '<=char<='~' else cjk
            if result and result[-1][0]==face:result[-1]=(face,result[-1][1]+char)
            else:result.append((face,char))
        return result

    def width(self,value,size,bold=False):
        return sum(pdfmetrics.stringWidth(text,face,size) for face,text in self.runs(value,bold))

    def metrics(self,size,value=None,bold=False):
        faces={face for face,_ in self.runs(value,bold)} if value is not None else {self.cjk,self.mono}
        values=[pdfmetrics.getAscentDescent(face,size) for face in (faces or {self.cjk})]
        return max(a for a,_ in values),min(d for _,d in values)

    def write(self,text_object,value,size,bold=False,*,horizontal_scale=100,char_space=0):
        text_object.setHorizScale(horizontal_scale);text_object.setCharSpace(char_space)
        advance=None
        for face,text in self.runs(value,bold):
            # Explicit run origins prevent font-switch spacing differences in
            # PDF readers/extractors. Td is relative to the previous line origin,
            # so advance includes horizontal scale and the boundary spacing.
            if advance is not None:text_object.moveCursor(advance,0)
            text_object.setFont(face,size);text_object.textOut(text)
            advance=(pdfmetrics.stringWidth(text,face,size)+char_space*len(text))*horizontal_scale/100
