"""PDF-only mixed text: fixed-width ASCII, existing CJK for other glyphs."""
import hashlib
import struct
from functools import lru_cache
from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


WINDOWS_FONTS=Path('C:/Windows/Fonts')


def register(path,role):
    name=role+'_'+hashlib.sha256(str(path.resolve()).encode('utf-8')).hexdigest()[:12]
    if name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(name,str(path),subfontIndex=0))
    return name


@lru_cache(maxsize=8192)
def glyph_metrics(name,char):
    """Actual TrueType ink bounds at 1 pt; unsupported faces use safe font bounds.

    ReportLab retains the original glyf table and its glyph offsets after loading
    a TTFont. Read just the ten-byte glyph header, including composite bounds,
    rather than parsing a second copy of a CJK font for every exported row.
    """
    try:
        face=pdfmetrics.getFont(name).face
        glyph=face.charToGlyph[ord(char)]
        start,end=face.glyphPos[glyph:glyph+2]
        if start==end:return 0.,0.  # Spaces have advance width but no ink.
        offset,length=face.get_table_pos('glyf')
        if not 0<=start<end<=length or end-start<10:raise ValueError('Invalid glyph bounds')
        _,_,bottom,_,top=struct.unpack_from('>hhhhh',face._ttf_data,offset+start)
        return top/face.unitsPerEm,bottom/face.unitsPerEm
    except (AttributeError,KeyError,IndexError,TypeError,ValueError,struct.error):
        return pdfmetrics.getAscentDescent(name,1)


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

    def ink_metrics(self,size,value,bold=False):
        values=[glyph_metrics(face,char) for face,text in self.runs(value,bold) for char in text]
        return max((a for a,_ in values),default=0)*size,min((d for _,d in values),default=0)*size

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
