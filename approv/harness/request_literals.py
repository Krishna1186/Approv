"""Conservative literal request checks, added after observed extraction failures.

These rules do not infer suitability. They only recover explicitly named catalogue
titles, sale counts and quantities with explicit per-pack/total wording. Catalogue
names are public vocabulary, never accepted-choice labels.
"""
from decimal import Decimal
import re
from approv.types.core import Channel,Constraint,Quantity,Term

WORDS={'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10}
NUMBER=r'(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)'


def repair_literals(original, interpreted, schema, catalogue_names=()):
    text=original.request
    allowed={a.name for a in schema.attributes}
    constraints={c.attribute:c for c in interpreted.constraints}
    notes=list(interpreted.interpretation_notes)
    changes=[]
    if 'product_name' in allowed:
        matches=[]
        for title in set(catalogue_names):
            if len(title.strip())<4:continue
            for m in re.finditer(r'(?<!\w)'+re.escape(title)+r'(?!\w)',text,re.I):
                if re.search(r'\b(?:not|except|avoid)\s+(?:the\s+)?$',text[max(0,m.start()-18):m.start()],re.I):continue
                matches.append((m.start(),m.end(),title))
        # Nested short titles do not create a second requested product.
        matches=[m for m in matches if not any(a<=m[0] and b>=m[1] and b-a>m[1]-m[0] for a,b,_ in matches)]
        if len({m[2].casefold() for m in matches})==1:
            a,b,title=matches[0]
            constraints['product_name']=Constraint(attribute='product_name',value=Term(surface=title),
                channel=Channel.AGENT_MESSAGE,raw_text=text[a:b])
            changes.append('Grounded product name in original text and public catalogue vocabulary')

    amounts=[]
    # Do not reinterpret the suffix of a comma-formatted or signed number.
    for m in re.finditer(r'(?<![\w.,+\-])(\d+(?:\.\d+)?)\s*(kg|gm|g|ml|l)\b',text,re.I):
        unit=m[2].lower();unit='g' if unit=='gm' else unit
        dimension='mass' if unit in ('g','kg') else 'volume'
        value=Quantity(magnitude=Decimal(m[1]),unit=unit,dimension=dimension)
        after=text[m.end():m.end()+65];before=text[max(0,m.start()-15):m.start()]
        per=bool(re.match(r'\s*(?:per\s+pack|packs?\b|in\s+(?:that|each|one)\s+pack)',after,re.I)
                 or re.search(r'\beach\s*$',before,re.I))
        # Do not cross a sentence or semicolon to find a total qualifier.
        clause=re.split(r'[.;!?]',after,maxsplit=1)[0]
        total=bool(re.search(r'\b(?:altogether|in total|total)\b',clause,re.I))
        amounts.append((m,value,per,total))
    per_pack=[x for x in amounts if x[2]]
    totals=[x for x in amounts if x[3] and not x[2]]
    updates={}
    if len(per_pack)==1:
        match,value,_,_=per_pack[0]
        attribute='net_weight' if value.dimension.value=='mass' else 'net_volume'
        if attribute in allowed:
            constraints[attribute]=Constraint(attribute=attribute,value=value,channel=Channel.AGENT_MESSAGE,
                                               raw_text=match[0])
            updates['quantity_scope']='per_sale_unit'
            changes.append('Grounded amount in explicit per-pack wording')
            if len(totals)==1 and totals[0][1].dimension==value.dimension:
                total=totals[0][1]
                size=value.magnitude*(1000 if value.unit in ('kg','l') else 1)
                amount=total.magnitude*(1000 if total.unit in ('kg','l') else 1)
                if size>0:
                    packs=amount/size
                    if packs==packs.to_integral_value() and 1<=packs<=100:
                        updates['requested_units']=int(packs)
                        changes.append('Derived sale units from explicit total and per-pack amount')
                    else:
                        notes.append('Requested total cannot be met by a whole number of the stated packs')
    def integer(raw):return WORDS[raw.casefold()] if raw.casefold() in WORDS else int(raw)
    counts=list(re.finditer(r'(?<![\w.,+\-])('+NUMBER+r')\s+(?:packs?|bottles?|boxes?)\b',text,re.I))
    counts=[m for m in counts if not re.search(r'\b(?:not|avoid|except)\s*$',text[max(0,m.start()-16):m.start()],re.I)]
    if counts:
        units=integer(counts[-1][1])
        # Only treat a correction as a count when a pack count was explicitly named.
        corrections=list(re.finditer(r'\b(?:make that|make it|change that to)\s+('+NUMBER+r')(?![\w\-]|[.,]\d)',text,re.I))
        if corrections and corrections[-1].start()>counts[-1].start():units=integer(corrections[-1][1])
        if 1<=units<=100:
            if 'requested_units' in updates and updates['requested_units']!=units:
                notes.append('Explicit pack count conflicts with total/per-pack amounts')
            updates['requested_units']=units
            changes.append('Grounded sale count in explicit request wording')
    result=interpreted.model_copy(update={**updates,'constraints':tuple(constraints.values()),'interpretation_notes':tuple(notes)})
    return result,changes
