"""Stable horizontal slots and shared, centered vertical grids."""
from . import subregions as sr
from .errors import LayoutCapacityError

BASE_COLUMNS={'bio':6,'cbc':1,'sendout':1,'e411':1,'other':1}


def column_counts(rows,layout):
    """Use one slot width for the export, independent of a row's missing groups.

    Include three-row overflow columns so a fourth item starts the next column.
    """
    result=dict(BASE_COLUMNS)
    for row in rows:
        if row is None:continue
        for zone,key in sr.ZONE_KEYS.items():
            items=list(row['zones'][key])
            if key=='sendout' and row.get('notes'):items.append({'label':'備註：'+row['notes']})
            try:
                groups=sr.arrange(items,zone,layout)
                result[key]=max(result[key],max((g['column']+1 for g in groups),default=0))
            except LayoutCapacityError:
                # Force-only overflow must not resize every ordinary row.
                pass
            explicit={i.get('placement',{}).get('subregion') for i in row['zones'][key]}-{None,''}
            if not explicit:continue
            stop=max(sr.LETTERS.index(letter) for letter in explicit)+1
            count=sum(letter in explicit or not sr.options(layout,zone,letter)['compact_subregions'] for letter in sr.LETTERS[:stop])
            result[key]=max(result[key],count)
    return result


def lane_center(position,count,height):
    if count==2:return height/2+(position-1.5)*height/3
    return (position-.5)*height/count


def region_grid(groups,key,columns,width,layout):
    """Other uses equal local columns; explicitly reserved empty slots still count."""
    used=max(g['column'] for g in groups)+1
    count=used if key=='other' else max(columns,used)
    zone=next(z for z,k in sr.ZONE_KEYS.items() if k==key)
    spans={g['column']:1 for g in groups} if key=='other' else group_spans(groups,count,zone,layout)
    return count,width/count,spans


def result_reserve(key,width,padding,columns):
    # Preserve a visible writing line before shrinking the label. Narrow Other
    # columns need not reserve the same long blank as a full-width result cell.
    reserve=min(3,width*.28)
    if key=='other' and columns>1:reserve=min(reserve,1.5+padding*.4)
    return reserve


def group_spans(groups,columns,zone,layout):
    """Borrow empty space to the right without moving any subgroup's anchor.

    A dense row can set a larger document-wide column count. Its unused slots
    need not shrink a sparse row's text. Populated groups and explicitly reserved
    empty subregions remain hard boundaries, including empty trailing regions.
    """
    by_letter={g['letter']:g for g in groups}
    barriers={g['column'] for g in groups};column=0
    for letter in sr.LETTERS:
        if letter in by_letter:column=by_letter[letter]['column']+1
        elif not sr.options(layout,zone,letter)['compact_subregions']:
            barriers.add(column);column+=1
    return {g['column']:max(1,min((c for c in barriers if c>g['column']),default=columns)-g['column'])
            for g in groups}
