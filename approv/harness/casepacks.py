"""Source-preserving benchmark preparation. No Approv comparisons create labels."""
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import random
import re

from approv.harness.inventory import import_off
from approv.harness.shopping import Inventory, Product, ShoppingCase, canonical, digest
from approv.types.core import AttributeSpec, CategorySchema, Certainty, Criticality, Dimension, Evidence, FieldProfile, Liability, Term


def nominal_schema(names, category):
    return CategorySchema(category_id=category, version="source-v1",
        attributes=tuple(AttributeSpec(name=n, dimension=Dimension.NOMINAL, criticality=Criticality.HARD) for n in names),
        field_profiles=tuple(FieldProfile(field_name=n, attributes=(n,), certainty=Certainty.EXACT,
            liability=Liability.SELLER_STATED) for n in names))


def nominal_evidence(name, value):
    return Evidence(attribute=name, value=Term(surface=value), field_name=name,
        certainty=Certainty.EXACT, liability=Liability.SELLER_STATED, raw_text=value)


def esci_pack(root: Path, dev=10, heldout=30, seed=20260908):
    import pyarrow.parquet as pq
    rows=pq.read_table(root/"shopping_queries_dataset_examples.parquet").to_pylist()
    groups=defaultdict(list)
    for r in rows:
        if r["product_locale"] == "us" and r["small_version"] == 1:
            groups[(r["split"], r["query_id"])].append(r)
    rng=random.Random(seed)
    selected=[]
    for split,n in (("train",dev),("test",heldout)):
        ids=sorted(k for k in groups if k[0]==split)
        selected += rng.sample(ids,n)
    wanted={r["product_id"] for k in selected for r in groups[k]}
    products={}
    for batch in pq.ParquetFile(root/"shopping_queries_dataset_products.parquet").iter_batches(batch_size=32768):
        for p in batch.to_pylist():
            if p["product_locale"] == "us" and p["product_id"] in wanted:
                products[p["product_id"]]=p
    schema=nominal_schema(("brand","color"),"esci.general")
    tasks=[]
    for split,qid in selected:
        source=groups[(split,qid)]
        candidates=[]
        for pid in sorted({r['product_id'] for r in source}):
            p=products[pid]
            details={k.removeprefix("product_"):str(v) for k,v in p.items()
                     if k in ("product_description","product_bullet_point","product_brand","product_color") and v}
            candidates.append(Product(id=pid,title=p['product_title'] or pid,details=details,
                evidence=tuple(nominal_evidence(n,p['product_'+n]) for n in ('brand','color') if p['product_'+n]),
                source_url='https://www.amazon.com/dp/'+pid,raw=p))
        inventory=Inventory(source="Amazon ESCI frozen judged candidate pool",source_license="Apache-2.0",
            captured_at=datetime(2026,9,8,tzinfo=timezone.utc),schema=schema,products=tuple(candidates))
        case=ShoppingCase(id=f"esci-{qid}",request=source[0]['query'],author="Original ESCI customer query",
            cluster=f"esci-{qid}")
        tasks.append(dict(split='dev' if split=='train' else 'heldout',family='human_query',inventory=inventory.model_dump(mode='json'),
            case=case.model_dump(mode='json'),gold={'method':'human_esci','labels':{r['product_id']:r['esci_label'] for r in source},
            'note':'Original relevance labels. Unit counts and abstention are not labelled; abstention is a non-selection, not success.'}))
    return dict(kind='human_esci',seed=seed,tasks=tasks,
        note='Random queries from official reduced US train/test splits. No selection on agent performance or labels.')


def off_stress_pack(path: Path, families=24, seed=20260908):
    """Generated requests over real public products; labels use raw fields, not algebra.

    Scope is deliberately narrow: an explicitly named published product, quantity,
    and sale units. Other products are not interchangeable without explicit consent.
    A case's pool contains the entire OFF export, including missing fields/noisy titles.
    """
    rows=json.loads(path.read_text(encoding='utf-8'))
    if isinstance(rows,dict): rows=rows['products']
    inventory,_=import_off(rows,datetime(2026,9,8,tzinfo=timezone.utc))
    base=inventory.category_schema
    extra=nominal_schema(('product_name',),'off.stress')
    schema=base.model_copy(update={'attributes':base.attributes+extra.attributes,
        'field_profiles':base.field_profiles+(extra.field_profiles[0].model_copy(update={'field_name':'catalogue_product_name'}),)})
    products=[]
    known={}
    # This independent, narrow source parser only accepts literal single quantities.
    # Multipack source rows are retained as distractors but cannot define gold here.
    for p in inventory.products:
        title=p.title.strip()
        products.append(p.model_copy(update={'details':{k:str(p.raw[k]) for k in ('brands','quantity') if p.raw.get(k)},
            'evidence':p.evidence+(nominal_evidence('product_name',title).model_copy(update={'field_name':'catalogue_product_name'}),)}))
        match=re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*(kg|g|gm|ml|l)\s*',str(p.raw.get('quantity','')),re.I)
        if match and len(title)>4:
            amount=Decimal(match[1]);unit=match[2].lower()
            dimension='mass' if unit in ('g','gm','kg') else 'volume'
            normalized=amount*(1000 if unit in ('kg','l') else 1)
            known[p.id]=(title.casefold(),dimension,normalized)
    inventory=Inventory.model_validate({**inventory.model_dump(mode='python'),'category_schema':schema,'products':tuple(products)})
    eligible=sorted(known)
    random.Random(seed).shuffle(eligible)
    # Hold out product-name groups, not merely paraphrases of the same target.
    chosen=[]; seen=set()
    for pid in eligible:
        if known[pid][0] not in seen:
            chosen.append(pid);seen.add(known[pid][0])
        if len(chosen)==families:break
    tasks=[]
    for index,pid in enumerate(chosen):
        product=next(p for p in products if p.id==pid)
        name,dimension,amount=known[pid];unit='g' if dimension=='mass' else 'ml'
        q=f'{amount.normalize():f} {unit}';total=f'{(amount*3).normalize():f} {unit}'
        variants=[
            ('clear',f'Please get one pack of {product.title}, {q} per pack. Keep the named product; no substitutions.',1,amount),
            ('correction',f'I had {product.title} on my list. I was thinking two packs. Actually make that three, each {q}. Please stick to that product.',3,amount),
            ('total',f'For the weekend I need {total} of {product.title} altogether. Use the {q} packs, not another pack size. Work out how many packs that takes.',3,amount),
            ('vague_size',f'Can you get me {product.title}? Just one pack please; I do not mind the pack size. No different product though.',1,None),
            ('impossible',f'One pack of {product.title}, exactly {(amount+Decimal("0.137")):f} {unit} in that pack. Do not substitute another size or product; skip it if unavailable.',1,amount+Decimal('0.137')),
        ]
        for family,request,units,required in variants:
            accepted=[{'product_id':other,'units':units} for other,(othername,dim,qty) in known.items()
                      if othername==name and (required is None or (dim==dimension and qty==required))]
            if required is None:
                accepted=[{'product_id':p.id,'units':units} for p in products if p.title.strip().casefold()==name]
            case=ShoppingCase(id=f'off-{index}-{family}',request=request,author='AI synthetic request; explicitly authorized 2026-09-08',cluster=f'off-name-{index}')
            tasks.append(dict(split='dev' if index<8 else 'heldout',family=family,
                case=case.model_dump(mode='json'),gold={'method':'synthetic_source_rule','accepted':accepted,'abstention_correct':not accepted,
                'note':'Constructed task, exact named product and literal raw quantity. Independent of Approv extraction/algebra. Not human-labelled.'}))
    return dict(kind='synthetic_off',seed=seed,inventory=inventory.model_dump(mode='json'),tasks=tasks,
        note='120 synthetic requests when families=24; real OFF inventory; five templates; name-disjoint dev/heldout. Not representative customer traffic.')


def published_vocabulary(inventory, limit=60):
    """Attribute -> the values this catalogue actually publishes, when that set is small.

    An attribute with thousands of surfaces (brand) stays open; sending it would not fit a
    prompt and a closed list is only useful where it is short enough to choose from.
    """
    from approv.types.core import Term
    seen = {}
    for product in inventory.products:
        for item in product.evidence:
            if isinstance(item.value, Term):
                seen.setdefault(item.attribute, set()).add(item.value.surface.casefold())
    return {k: tuple(sorted(v)) for k, v in seen.items() if len(v) <= limit}


def write_pack(path,pack):
    pack={**pack,'content_hash':digest(pack)}
    with Path(path).open('x',encoding='utf-8') as f:f.write(canonical(pack)+'\n')


# Deterministic published-text extraction. These read *product* evidence only; the
# request side is extracted by the model, so the two sides never share a parser.
#
# Precision is chosen over recall throughout. A false evidence value produces a false
# verdict, and per CLAUDE.md 2.6 a false refuse costs a sale, so every pattern requires
# an explicit statement rather than a bare keyword. Two earlier vocabularies were
# withdrawn after measurement: bare size codes matched "Charlotte's Web" and "full
# refund", and bare material words read "Faux Leather" as leather. Recall is therefore
# low by construction, and this extractor's precision is not measured against hand
# labels — see docs/shopping-harness.md.
GENDER = {'women':'women',"women's":'women','womens':'women','ladies':'women',
          'men':'men',"men's":'men','mens':'men',
          'girls':'girls',"girls'":'girls',"girl's":'girls',
          'boys':'boys',"boys'":'boys',"boy's":'boys',
          'kids':'kids',"kids'":'kids','children':'kids',"children's":'kids',
          'toddler':'toddler','baby':'baby','infant':'baby','newborn':'baby','unisex':'unisex'}
COLOR = {c: c for c in ('black','white','red','blue','green','yellow','pink','purple','brown',
    'orange','silver','gold','navy','beige','teal','maroon','ivory','charcoal')} | {'grey':'gray','gray':'gray'}
# A size counts only where the text marks it as one: an explicit "size" cue, a bracketed
# code, or a bed size bound to bedding. "Large capacity" and "full refund" are not sizes.
_CODE = r'(xxs|xs|s|m|l|xl|xxl|xxxl|2xl|3xl|small|medium|large|x-large|xx-large)'
_BED = r'(twin xl|twin|full|queen|king|california king|cal king)'
SIZE_PATTERNS = (
    re.compile(r'\bsizes?\s*[:\-]?\s*' + _CODE + r'\b', re.I),
    re.compile(r'\(\s*' + _CODE + r'\s*\)', re.I),
    re.compile(r'\b' + _CODE + r'\s+size\b', re.I),
    re.compile(r'\b' + _BED + r'\s+(?:size|bed|mattress|sheets?|comforter|duvet|frame|pad|pillow|quilt|blanket)\b', re.I),
    re.compile(r'\b(?:size|bed|mattress|sheets?|comforter|duvet|frame|pad|quilt|blanket)\s+' + _BED + r'\b', re.I),
)
_SIZE_NORM = {'2xl':'xxl','3xl':'xxxl','x-large':'xl','xx-large':'xxl','cal king':'california king'}
_GENDER_RE = re.compile(r"\b(" + '|'.join(sorted((re.escape(k) for k in GENDER), key=len, reverse=True)) + r")(?![a-z])", re.I)
_COLOR_RE = re.compile(r'\b(' + '|'.join(sorted(COLOR, key=len, reverse=True)) + r')\b', re.I)


def parse_published(text: str) -> dict:
    """Normalized attribute values a published string states unambiguously.

    Two distinct values for one attribute yields none for that attribute: a listing that
    says both "girls" and "boys" has not stated a gender, and ambiguity is not evidence.
    """
    text = text or ''
    found = {}
    for attribute, hits in (
        ('gender_age', {GENDER[m.group(1).casefold()] for m in _GENDER_RE.finditer(text)}),
        ('color', {COLOR[m.group(1).casefold()] for m in _COLOR_RE.finditer(text)}),
        ('size', {_SIZE_NORM.get(v, v) for p in SIZE_PATTERNS for m in p.finditer(text)
                  for v in [m.group(1).casefold()]}),
    ):
        if len(hits) == 1:
            found[attribute] = hits.pop()
    return found


CONSTRAINED = {'gender_age': _GENDER_RE, 'color': _COLOR_RE,
               'size': re.compile('|'.join(p.pattern for p in SIZE_PATTERNS), re.I)}


def constrained_schema():
    attributes = (
        AttributeSpec(name='brand', dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
        AttributeSpec(name='color', dimension=Dimension.NOMINAL, criticality=Criticality.SOFT),
        AttributeSpec(name='gender_age', dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
        AttributeSpec(name='size', dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
    )
    parsed = ('color', 'gender_age', 'size')
    return CategorySchema(category_id='esci.constrained', version='published-text-v1', attributes=attributes,
        field_profiles=(
            FieldProfile(field_name='product_brand', attributes=('brand',), certainty=Certainty.EXACT, liability=Liability.SELLER_STATED),
            FieldProfile(field_name='product_color', attributes=('color',), certainty=Certainty.EXACT, liability=Liability.SELLER_STATED),
            FieldProfile(field_name='title', attributes=parsed, certainty=Certainty.PARSED, liability=Liability.SELLER_STATED),
            FieldProfile(field_name='prose', attributes=parsed, certainty=Certainty.PARSED, liability=Liability.SELLER_STATED)))


def constrained_product(row, description_limit=1200):
    """One ESCI product with evidence from its structured fields and its published text."""
    title = (row['product_title'] or row['product_id']).strip()
    prose = ' '.join(filter(None, (row.get('product_bullet_point'), row.get('product_description'))))
    evidence = []
    if row.get('product_brand') and str(row['product_brand']).strip():
        evidence.append(nominal_evidence('brand', str(row['product_brand']).strip())
                        .model_copy(update={'field_name': 'product_brand'}))
    # A colour field is an authoritative declaration, but "polar white" and "black patent"
    # are that declaration in a finer vocabulary than the attribute. Widening to the colour
    # family keeps it exact; a value the family vocabulary cannot place is not asserted.
    declared = parse_published(str(row.get('product_color') or '')).get('color')
    if declared:
        evidence.append(nominal_evidence('color', declared).model_copy(update={'field_name': 'product_color'}))
    for field, text in (('title', title), ('prose', prose)):
        for attribute, value in parse_published(text).items():
            evidence.append(Evidence(attribute=attribute, value=Term(surface=value), field_name=field,
                certainty=Certainty.PARSED, liability=Liability.SELLER_STATED, raw_text=text[:400]))
    details = {'title': title}
    if row.get('product_brand'): details['brand'] = str(row['product_brand'])
    if row.get('product_color'): details['color'] = str(row['product_color'])
    if row.get('product_bullet_point'): details['bullet_point'] = str(row['product_bullet_point'])[:description_limit]
    if row.get('product_description'): details['description'] = str(row['product_description'])[:description_limit]
    return Product(id=row['product_id'], title=title, details=details, evidence=tuple(evidence),
        source_url='https://www.amazon.com/dp/' + row['product_id'])


def esci_constrained_pack(root: Path, dev=15, heldout=60, seed=20260909, distractors=4000, exclude=()):
    """Real queries that state a checkable constraint, over one large shared inventory.

    Selection is on the query's surface form only — never on labels, products or agent
    behaviour — so it defines the population Approv claims to serve rather than a
    favourable sample. Requests and labels are original ESCI; nothing here is generated.
    """
    import pyarrow.parquet as pq
    rows = pq.read_table(root / 'shopping_queries_dataset_examples.parquet').to_pylist()
    groups = defaultdict(list)
    for r in rows:
        if r['product_locale'] == 'us' and r['small_version'] == 1:
            groups[(r['split'], r['query_id'])].append(r)
    blocked = set(exclude)
    constrained = {k: v for k, v in groups.items()
                   if k[1] not in blocked and any(p.search(v[0]['query']) for p in CONSTRAINED.values())}
    rng = random.Random(seed)
    selected = []
    for split, n in (('train', dev), ('test', heldout)):
        selected += rng.sample(sorted(k for k in constrained if k[0] == split), n)
    judged = {r['product_id'] for k in selected for r in groups[k]}
    pool = sorted(set(groups) - set(selected))
    rng.shuffle(pool)
    filler, index = set(), 0
    while len(judged) + len(filler) < distractors and index < len(pool):
        filler |= {r['product_id'] for r in groups[pool[index]]} - judged
        index += 1
    wanted = judged | filler
    found = {}
    for batch in pq.ParquetFile(root / 'shopping_queries_dataset_products.parquet').iter_batches(batch_size=32768):
        for p in batch.to_pylist():
            if p['product_locale'] == 'us' and p['product_id'] in wanted:
                found[p['product_id']] = p
    products = tuple(constrained_product(found[pid]) for pid in sorted(found))
    inventory = Inventory(source='Amazon ESCI judged pools, shared catalogue', source_license='Apache-2.0',
        captured_at=datetime(2026, 9, 8, tzinfo=timezone.utc), schema=constrained_schema(), products=products)
    tasks = []
    for split, qid in selected:
        source = groups[(split, qid)]
        case = ShoppingCase(id=f'esci-{qid}', request=source[0]['query'],
            author='Original ESCI customer query', cluster=f'esci-{qid}')
        tasks.append(dict(split='dev' if split == 'train' else 'heldout', family='constrained_query',
            case=case.model_dump(mode='json'),
            gold={'method': 'human_esci', 'labels': {r['product_id']: r['esci_label'] for r in source},
                  'note': 'Original relevance labels over this query judged pool. Unjudged catalogue '
                          'products score as not-exact, which lowers every arm equally and makes only '
                          'the paired difference interpretable. Counts and abstention are unlabelled.'}))
    return dict(kind='esci_constrained', seed=seed, inventory=inventory.model_dump(mode='json'), tasks=tasks,
        note=f'{len(products)} shared products; queries carry >=1 checkable constraint by surface form. '
             'Descriptions truncated to 1200 characters for display. No generated requests or labels.')
