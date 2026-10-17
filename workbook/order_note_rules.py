"""Local order-memo annotations; source records and stored item rules stay intact."""
from .print_style import RED


def flags(notes):
    if notes is None:
        raise ValueError('這份工作進度尚未讀取檢驗單備註，請重新匯入當日資料，或關閉「依備註欄調整」。')
    if not isinstance(notes,list) or any(not isinstance(note,str) for note in notes):
        raise ValueError('檢驗單備註格式不正確，請重新匯入當日資料。')
    parts=[note.strip() for note in notes]
    # '+' is deliberately exact; the three Chinese markers use containment.
    visit=[];urine=[]
    if '+' in parts:visit.append('+')
    if any('補' in note for note in parts):visit.append('補')
    if any('安信' in note for note in parts):urine.append('安信')
    missing=any('缺尿' in note for note in parts)
    if missing:urine.append('no UR')
    return dict(visit_marks=visit,urine_marks=urine,suppress_mab=missing)


def annotation(label):
    return dict(key='NOTE:'+label,label=label,original_label=label,zone='cbc',codes=[],
                machine=None,machines=[],color=RED,bold=True,note_annotation=True,
                placement=dict(print_enabled=True,subregion='',position=None))


def machines(item):
    return item.get('machines',([item['machine']] if item.get('machine') else []))


def apply(prepared,settings):
    """Apply after panel expansion/serial transfer, before PDF geometry and ditto."""
    if not settings.get('apply_order_note_rules',False):
        for row in prepared:row.pop('note_adjustments',None)
        return prepared
    changed_numbering=False
    for row in prepared:
        effects=flags(row.get('order_notes'));row['note_adjustments']=effects
        # Merged rows retain all original-order memos; any missing-urine mark
        # suppresses this printed row's entire shared mab group, including ucr.
        if effects['suppress_mab']:
            changed_numbering=True
            for items in row['zones'].values():
                for item in items:
                    remaining=[group for group in machines(item) if group!='mab']
                    item['machines']=remaining;item['machine']=next(iter(remaining),None)
            for panel in row.get('panel_display',[]):
                if 'transferred_serial_groups' in panel:
                    panel['transferred_serial_groups']=[g for g in panel['transferred_serial_groups'] if g!='mab']
        row['zones']['cbc'].extend(annotation(label) for label in effects['urine_marks'])
    if changed_numbering:
        number=0
        for row in prepared:
            if any('mab' in machines(item) for items in row['zones'].values() for item in items):
                number+=1;row['mab_seq']=number
            else:row['mab_seq']=None
    return prepared
