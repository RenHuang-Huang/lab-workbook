"""Lossless emergency packing: three rows down, then the next column."""
import math
from .print_style import measure_run,run_height
def pack_segments(tokens,width,height,measure,max_lanes=3,start_size=10.5):
    if not tokens:return start_size,[]
    rows=min(3,max_lanes,len(tokens));columns=math.ceil(len(tokens)/rows)
    cell_width=width/columns;size=start_size
    for attempt in range(180):
        padding=min(1.2,cell_width*.12,size/4)
        reserve=min(3,cell_width*.22)*min(1,size/6)
        pieces=[];fits=True
        for runs,has_result in tokens:
            space=reserve if has_result else 0
            measured=sum(measure_run(measure,value,size,ink) for value,ink in runs)
            fits &= measured+space+padding<=cell_width
            pieces.append(dict(runs=runs,width=cell_width,result=space,padding=padding))
        extent=max([size]+[run_height(runs,size) for runs,_ in tokens])
        if fits and extent/72*25.4*1.22<=height/(3 if rows==2 else rows)-.3:
            # draw_packed consumes horizontal lanes; transpose column-major items.
            return size,[[pieces[i] for i in range(row,len(pieces),rows)] for row in range(rows)]
        size*=.9
    raise ValueError('強制排版無法完成，請檢查項目名稱或欄位設定')
