"""Variable-height A4 rows. Measurements stay local; no source item is discarded."""
from . import subregions as sr
from .errors import LayoutCapacityError
from .print_style import measure_run,run_height


def wrap_runs(runs,room,size,measure):
    lines=[[]]
    for value,color in runs:
        for char in str(value):
            line=lines[-1]
            if char=='\n':lines.append([]);continue
            trial=[*line,(char,color)]
            if sum(measure_run(measure,c,size,ink) for c,ink in trial)>room+.001 and line:
                lines.append([]);line=lines[-1]
            if measure_run(measure,char,size,color)>room+.001:raise LayoutCapacityError('單字寬度超出子區域，請調整字級或位置')
            line.append((char,color))
    result=[]
    for line in lines:
        packed=[]
        for char,color in line:
            if packed and packed[-1][1]==color:packed[-1]=(packed[-1][0]+char,color)
            else:packed.append((char,color))
        result.append(packed)
    return result


def zone_plan(items,key,layout,columns,width,font_size,segments,measure,seen=None,force=False):
    if not items:return None
    zone=next(z for z,k in sr.ZONE_KEYS.items() if k==key)
    try:groups=sr.arrange(items,zone,layout,expand_vertical=True,columns=columns)
    except LayoutCapacityError:
        if not force:raise
        from .compact_layout import pack_segments
        seen=set() if seen is None else seen;tokens=[]
        for item in items:
            runs,machines=segments(item,seen);seen.update(machines);tokens.append((runs,bool(machines)))
        packed=pack_segments(tokens,width,12,measure,max_lanes=3,start_size=font_size)
        return dict(packed=packed,offset=0,width=width,adult=None,height=12,groups=[dict(size=packed[0])],forced=True)
    count=max(columns,max(g['column'] for g in groups)+1);cw=width/count
    result=[];seen=set() if seen is None else seen;line_counts={};maximum_size=0;single_height=0
    padding=min(1.2,cw*.2)
    for group in groups:
        entries=group['entries'];single=len(entries)==1 and group['options']['display']=='single_max'
        prepared=[];size=entries[0][1].get('font_size',font_size) if len(entries)==1 and entries[0][1].get('key')=='@' else font_size
        for position,item in entries:
            runs,machines=segments(item,seen);seen.update(machines)
            reserve=min(3,cw*.28) if item.get('machines') or item.get('machine') or key in ('e411','other') else 0
            room=cw-padding-reserve
            # Each item occupies one lane; wrapping must never create a fourth.
            widest=sum(measure_run(measure,value,size,ink) for value,ink in runs)
            if widest>room:size=min(size,size*room/widest)
            prepared.append((position,runs,machines,reserve,room))
        if single:
            _,runs,_,_,room=prepared[0]
            entire=sum(measure_run(measure,value,24,ink) for value,ink in runs)
            size=max(size,min(24,24*room/max(entire,.001)))
        if size<min(7.5,font_size)-.001 and not force:
            raise LayoutCapacityError('子區域欄寬不足，請調整簡稱、區域或字級')
        pieces=[]
        for position,runs,machines,reserve,room in prepared:
            lines=[runs]
            pieces.append(dict(position=position,lines=lines,machines=machines,reserve=reserve))
            if not single:line_counts[position]=max(line_counts.get(position,1),len(lines))
            else:single_height=max(single_height,required_height(len(lines),run_height(runs,size)))
        if not single:maximum_size=max(maximum_size,*(run_height(runs,size) for _,runs,_,_,_ in prepared))
        result.append(dict(column=group['column'],pieces=pieces,size=size,single=single))
    peak=max(line_counts,default=0);starts={};lanes=0
    for position in range(1,peak+1):starts[position]=lanes;lanes+=line_counts.get(position,1)
    return dict(groups=result,columns=count,cell_width=cw,padding=padding,starts=starts,lanes=lanes,
                height=max(required_height(lanes,maximum_size),single_height))


def required_height(lines,size):
    # item_text uses a baseline offset; allow its full top bearing at 24 pt too.
    return (3 if lines==2 else lines)*(size/72*25.4*1.16+.3)


def paginate(slots,heights,body,bottom=286,force=False):
    pages=[];page=[];y=body;capacity=bottom-body
    for index,(row,needed) in enumerate(zip(slots,heights)):
        oversized=needed>capacity+.001
        if oversized and not force:
            raise LayoutCapacityError(f"工作號 {row['workno']}：單筆內容超過整張 A4 可用高度，請調整簡稱、區域或使用強制輸出")
        height=min(needed,capacity)
        if page and y+height>bottom+.001:pages.append(page);page=[];y=body
        page.append(dict(index=index,top=y,height=height,needed=needed,oversized=oversized));y+=height
    if page:pages.append(page)
    return pages
