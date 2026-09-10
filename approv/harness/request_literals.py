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


def recover_noted_values(interpreted, schema, published):
    """Promote an unverified note that is verbatim a value the catalogue publishes.

    The extractor drops a stated requirement into `unverified` when it has no closed list
    to map onto. Colour has 1,146 distinct published values here and product_type 112, both
    past the size at which a vocabulary can be put in a prompt, so the model writes the
    shopper's words into the note field and the attribute goes unconstrained.

    Measured on the fresh corpus: 4 of 7 notes are a verbatim published value of an
    attribute that has no constraint — "Stone Two Tone" and "Pride" and "Tri-Fusion" are
    colours, "in stock" is an availability. One of them, fresh-42, produced every false
    allow in the first gate scoring: the gate cleared three comforters in the wrong colour
    because the colour requirement was sitting in a note nobody read.

    This is not inference. The match is exact under `normalize_term`, which is the same
    identity key the comparison operators use, so a value recovered here is one the engine
    would have compared identically had the model emitted it in the first place. Three
    guards keep it that way:

      * the note must appear in the original request, so nothing is invented;
      * it must match exactly one attribute, because a surface belonging to two attributes
        is ambiguous and guessing which is exactly the inference this avoids;
      * that attribute must be unconstrained, so a recovery can never overwrite or
        contradict something the model did state.

    A recovered value stops being a note, which is the point: it is no longer unread, so it
    no longer fails the verification floor. Anything not recovered stays a note and still
    does.
    """
    from approv.algebra.term import normalize_term

    allowed = {a.name for a in schema.attributes}
    constraints = list(interpreted.constraints)
    held = {c.attribute for c in constraints}
    text = normalize_term(interpreted.request)
    kept, changes = [], []

    for note in interpreted.interpretation_notes:
        surface = normalize_term(str(note))
        if not surface or surface not in text:
            kept.append(note)
            continue
        matches = sorted(a for a, values in published.items()
                         if a in allowed and a not in held and surface in values)
        if len(matches) != 1:
            kept.append(note)
            continue
        attribute = matches[0]
        try:
            candidate = Constraint(attribute=attribute, value=Term(surface=str(note)),
                                   raw_text=str(note), channel=Channel.AGENT_MESSAGE)
        except (TypeError, ValueError):
            kept.append(note)
            continue
        constraints.append(candidate)
        held.add(attribute)
        changes.append({"recovered": attribute, "surface": str(note)})

    if not changes:
        return interpreted, []
    return interpreted.model_copy(update={
        "constraints": tuple(constraints),
        "interpretation_notes": tuple(kept),
    }), changes


def published_values(inventory):
    """attribute -> every value the catalogue publishes for it, as identity keys.

    Separate from `published_vocabulary`, which is capped so it can go in a prompt. This
    one is uncapped because it never reaches a model; it is only ever used to check whether
    a note the model already wrote is a value that exists.
    """
    from approv.algebra.term import normalize_term
    values = {}
    for product in inventory.products:
        for item in product.evidence:
            surface = getattr(item.value, "surface", None)
            if surface is not None:
                values.setdefault(item.attribute, set()).add(normalize_term(surface))
    return values
