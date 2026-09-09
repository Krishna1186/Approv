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


# --- Shopify D2C catalogues -------------------------------------------------------
#
# A Shopify storefront publishes /products.json unauthenticated: variant trees with SKU,
# option values, price and a stock flag. Size and colour arrive as structured options
# rather than prose, so no extraction step stands between the listing and the check, and
# the merchant is the publisher of record rather than an aggregator.
#
# The inventory item here is the *variant*, not the product. "Size 9, in stock, under
# $150" is a statement about one variant, and a harness that selects products cannot
# express it.

def shopify_evidence(attribute, value, field, dimension=Dimension.NOMINAL):
    from approv.types.core import Money
    typed = Term(surface=str(value)) if dimension is Dimension.NOMINAL else value
    return Evidence(attribute=attribute, value=typed, field_name=field, certainty=Certainty.EXACT,
                    liability=Liability.MERCHANT_GUARANTEED, raw_text=str(value))


def shopify_schema():
    return CategorySchema(category_id='shopify.d2c', version='variant-v1', attributes=(
        AttributeSpec(name='brand', dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
        AttributeSpec(name='size', dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
        AttributeSpec(name='color', dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
        AttributeSpec(name='availability', dimension=Dimension.NOMINAL, criticality=Criticality.HARD),
        AttributeSpec(name='price', dimension=Dimension.MONEY, criticality=Criticality.BOUND),
    ), field_profiles=(
        FieldProfile(field_name='product.vendor', attributes=('brand',), certainty=Certainty.EXACT, liability=Liability.MERCHANT_GUARANTEED),
        FieldProfile(field_name='variant.option_size', attributes=('size',), certainty=Certainty.EXACT, liability=Liability.MERCHANT_GUARANTEED),
        FieldProfile(field_name='variant.option_color', attributes=('color',), certainty=Certainty.EXACT, liability=Liability.MERCHANT_GUARANTEED),
        FieldProfile(field_name='variant.available', attributes=('availability',), certainty=Certainty.EXACT, liability=Liability.MERCHANT_GUARANTEED),
        FieldProfile(field_name='variant.price', attributes=('price',), certainty=Certainty.EXACT, liability=Liability.MERCHANT_GUARANTEED),
    ))


def shopify_variants(raw, currency='USD', description_limit=900):
    """Flatten every brand's products into one variant-level catalogue."""
    import html as htmllib, re as _re
    from approv.types.core import Money
    items = []
    for brand_host, products in raw:
        for product in products:
            names = [o['name'].strip().lower() for o in product.get('options', [])]
            prose = _re.sub(r'<[^>]+>', ' ', htmllib.unescape(product.get('body_html') or ''))
            prose = _re.sub(r'\s+', ' ', prose).strip()
            for variant in product.get('variants', []):
                option = {names[i]: variant.get('option%d' % (i + 1)) for i in range(len(names))
                          if variant.get('option%d' % (i + 1))}
                size = option.get('size'); colour = option.get('color') or option.get('colour')
                price = variant.get('price')
                if price in (None, ''): continue
                evidence = [shopify_evidence('brand', product.get('vendor') or brand_host, 'product.vendor'),
                            shopify_evidence('availability', 'in_stock' if variant.get('available') else 'out_of_stock',
                                             'variant.available'),
                            Evidence(attribute='price', value=Money(amount=Decimal(str(price)), currency=currency),
                                     field_name='variant.price', certainty=Certainty.EXACT,
                                     liability=Liability.MERCHANT_GUARANTEED, raw_text=str(price))]
                if size: evidence.append(shopify_evidence('size', size, 'variant.option_size'))
                if colour: evidence.append(shopify_evidence('color', colour, 'variant.option_color'))
                title = product['title'].strip()
                label = str(variant.get('title') or '').strip()
                details = {'title': title, 'brand': str(product.get('vendor') or ''),
                           'product_type': str(product.get('product_type') or ''),
                           'variant': label, 'price': '%s %s' % (price, currency),
                           'availability': 'in stock' if variant.get('available') else 'out of stock'}
                if size: details['size'] = str(size)
                if colour: details['color'] = str(colour)
                # Long text is withheld from search pages and returned only on inspect.
                if prose: details['description'] = prose[:description_limit]
                items.append(Product(id='%s-%s' % (product['id'], variant['id']),
                    title=title + (' - ' + label if label and label.lower() != 'default title' else ''),
                    details=details, evidence=tuple(evidence),
                    source_url='https://%s/products/%s' % (brand_host, product.get('handle', ''))))
    return tuple(items)


def shopify_inventory(raw, captured_at, currency='USD'):
    items = shopify_variants(raw, currency)
    seen, unique = set(), []
    for item in items:
        if item.id in seen: continue
        seen.add(item.id); unique.append(item)
    return Inventory(source='Shopify storefront /products.json, %d brands' % len(raw),
        source_license='Publisher terms; public unauthenticated endpoint, robots.txt checked per host',
        captured_at=captured_at, schema=shopify_schema(), products=tuple(unique))


def shopify_pack(raw, captured_at, catalogue=10000, cases=90, seed=20260910):
    """Requests with constraints, and answers computed from the merchant's own fields.

    The request wording is generated (DR 0018). The *answer* is not a judgement: it is the
    set of variants whose published size, colour, price and stock flag satisfy what the
    request states, computed here by direct field comparison. Nothing in this function
    imports approv.algebra, so the answer key cannot agree with the checker by
    construction — the failure that killed the second benchmark design in 2026-09.
    """
    from approv.types.core import Money
    inventory = shopify_inventory(raw, captured_at)
    rng = random.Random(seed)
    items = list(inventory.products)

    def field(product, attribute):
        for item in product.evidence:
            if item.attribute == attribute:
                return item.value.amount if attribute == 'price' else str(item.value.surface)
        return None

    groups = defaultdict(list)
    for product in items:
        groups[(product.details.get('brand', ''), product.details['title'])].append(product)
    # A family is only interesting if the shopper could pick the wrong member of it.
    families = [g for g in groups.values() if len(g) >= 4 and any(field(p, 'size') for p in g)]
    rng.shuffle(families)

    keep = {p.id for g in families[:cases * 3] for p in g}
    pool = [p for p in items if p.id not in keep]
    rng.shuffle(pool)
    catalogue_items = [p for g in families[:cases * 3] for p in g] + pool[:max(0, catalogue - len(keep))]
    frozen = Inventory(source=inventory.source, source_license=inventory.source_license,
        captured_at=captured_at, schema=shopify_schema(), products=tuple(catalogue_items))

    tasks = []
    for index, family in enumerate(families):
        if len(tasks) >= cases: break
        sized = [p for p in family if field(p, 'size')]
        if not sized: continue
        title = family[0].details['title']
        brand = family[0].details.get('brand') or ''
        stocked = [p for p in sized if field(p, 'availability') == 'in_stock']
        empty = [p for p in sized if field(p, 'availability') == 'out_of_stock']
        template = ('full', 'budget', 'casual', 'terse', 'impossible')[index % 5]
        # Every template but 'impossible' promises a reachable answer. Drawing the target
        # from an out-of-stock variant would silently turn it into an abstention case and
        # make the template labels describe something other than what they test.
        if template != 'impossible' and not stocked: continue
        target = rng.choice(stocked or sized)
        size = field(target, 'size')
        colour = field(target, 'color')
        price = field(target, 'price')
        # Several constraints at once, on purpose. A single re-read repairs the salient
        # error and leaves the rest, which is the condition under which reporting every
        # finding together is worth more than telling an agent to look again.
        spec = {'size': size, 'availability': 'in_stock'}
        if colour: spec['color'] = colour
        wants = f'{title} in {colour}, size {size}' if colour else f'{title}, size {size}'
        if template == 'full':
            request = f'I want the {wants}. It has to be in stock.'
        elif template == 'budget':
            cap = (price + Decimal('15')).quantize(Decimal('1'))
            spec['price_lte'] = cap
            request = (f'Looking for the {wants}, in stock, and I do not want to go over '
                       f'${cap} for it.')
        elif template == 'casual':
            request = (f'hey can you grab me the {wants}? needs to actually be in stock, '
                       f'not on backorder')
        elif template == 'terse':
            request = f'{wants}, in stock only'
        else:
            if not empty: continue
            target = rng.choice(empty)
            size = field(target, 'size'); colour = field(target, 'color')
            spec = {'size': size, 'availability': 'in_stock'}
            if colour: spec['color'] = colour
            shape = f'{title} in {colour}, size {size}' if colour else f'{title}, size {size}'
            request = (f'One {shape}, in stock. Do not substitute another size or colour, '
                       f'and skip it entirely if you cannot get exactly that.')

        def satisfies(product):
            if field(product, 'size') != spec['size']: return False
            if field(product, 'availability') != 'in_stock': return False
            if 'color' in spec and field(product, 'color') != spec['color']: return False
            if 'price_lte' in spec and (field(product, 'price') or 0) > spec['price_lte']: return False
            return product.details['title'] == title and product.details.get('brand', '') == brand
        accepted = [{'product_id': p.id, 'units': 1} for p in family if satisfies(p)]
        tasks.append({'split': 'dev' if len(tasks) < 15 else 'heldout', 'family': template,
            'case': ShoppingCase(id=f'shop-{index}-{template}', request=request,
                author='Generated request over a real merchant catalogue (DR 0018)',
                cluster=f'shop-family-{index}').model_dump(mode='json'),
            'gold': {'method': 'published_field_rule', 'accepted': accepted,
                     'abstention_correct': not accepted, 'spec': {k: str(v) for k, v in spec.items()},
                     'note': 'Computed from the merchant published size, colour, price and stock '
                             'flag by direct comparison. No relevance judgement, no Approv logic.'}})
    return {'kind': 'shopify_d2c', 'seed': seed, 'inventory': frozen.model_dump(mode='json'),
            'tasks': tasks, 'note': f'{len(frozen.products)} variants from {len(raw)} D2C brands. '
            'Requests are generated; answers are published-field comparisons.'}


def shopify_shopper_pack(raw, captured_at, catalogue=25000, cases=120, seed=20260912):
    """Requests that describe what the shopper wants, without naming the catalogue entry.

    The previous generator quoted the product's exact title in 94% of requests, so the
    agent's search query quoted it too and retrieval succeeded 95% of the time. That
    measured string matching. A shopper who already knows the exact product name is not
    the case worth testing; a shopper who knows what they want is.

    The answer key is the generator's own spec applied to published fields. Approv has to
    re-derive those requirements from the free text with a model and can get it wrong, so
    the key and the checker are independent paths rather than the same computation twice.
    """
    inventory = shopify_inventory(raw, captured_at)
    rng = random.Random(seed)
    items = list(inventory.products)

    def field(product, attribute):
        for item in product.evidence:
            if item.attribute == attribute:
                return item.value.amount if attribute == 'price' else str(item.value.surface)
        return None

    # Group by the words a shopper would actually use: what kind of thing it is.
    kinds = defaultdict(list)
    for product in items:
        kind = (product.details.get('product_type') or '').strip().lower()
        if kind and field(product, 'size') and field(product, 'color'):
            kinds[kind].append(product)
    # A product_type is only a shopper's word for the thing if several products share it.
    # Brands fill that field with names like "the point iii" or "the d'orsay espadrille",
    # which would put the catalogue title back into the request through the side door.
    def generic(members):
        titles = {p.details['title'] for p in members}
        brands = {p.details.get('brand', '') for p in members}
        return len(members) >= 12 and len(titles) >= 4
    usable = [k for k, v in kinds.items() if generic(v)]
    rng.shuffle(usable)

    keep = {p.id for k in usable for p in kinds[k]}
    pool = [p for p in items if p.id not in keep]
    rng.shuffle(pool)
    frozen = Inventory(source=inventory.source, source_license=inventory.source_license,
        captured_at=captured_at, schema=shopify_schema(),
        products=tuple([p for k in usable for p in kinds[k]] + pool[:max(0, catalogue - len(keep))]))
    by_kind = defaultdict(list)
    for product in frozen.products:
        by_kind[(product.details.get('product_type') or '').strip().lower()].append(product)

    tasks = []
    for index, kind in enumerate(usable):
        if len(tasks) >= cases: break
        members = by_kind[kind]
        stocked = [p for p in members if field(p, 'availability') == 'in_stock']
        if not stocked: continue
        template = ('plain', 'budget', 'casual', 'terse', 'impossible')[index % 5]
        target = rng.choice(stocked)
        # Reject the case outright if the shopper's word for the thing is just the
        # product's own name wearing a different hat.
        if kind in target.details['title'].lower(): continue
        colour, size, price = field(target, 'color'), field(target, 'size'), field(target, 'price')
        spec = {'color': colour, 'size': size, 'availability': 'in_stock'}
        if template == 'plain':
            request = f'I need a {colour} {kind} in size {size}. It has to be in stock.'
        elif template == 'budget':
            cap = (price + Decimal('25')).quantize(Decimal('1'))
            spec['price_lte'] = cap
            request = f'Do you have any {kind} in {colour}, size {size}? Nothing over ${cap}, and it needs to be available.'
        elif template == 'casual':
            request = f'hey im after a {kind} — {colour}, size {size}. needs to be in stock, not backordered'
        elif template == 'terse':
            request = f'{kind}, {colour}, size {size}, in stock'
        else:
            # A combination this catalogue cannot fill: correct behaviour is to decline.
            absent = [p for p in members if field(p, 'availability') == 'out_of_stock']
            if not absent: continue
            target = rng.choice(absent)
            colour, size = field(target, 'color'), field(target, 'size')
            spec = {'color': colour, 'size': size, 'availability': 'in_stock'}
            if any(field(p, 'color') == colour and field(p, 'size') == size
                   and field(p, 'availability') == 'in_stock' for p in members): continue
            request = (f'One {kind} in {colour}, size {size}, in stock. Do not substitute a '
                       f'different colour or size — skip it if you cannot get exactly that.')

        def satisfies(product):
            if field(product, 'size') != spec['size']: return False
            if field(product, 'color') != spec['color']: return False
            if field(product, 'availability') != 'in_stock': return False
            if 'price_lte' in spec and (field(product, 'price') or 0) > spec['price_lte']: return False
            return (product.details.get('product_type') or '').strip().lower() == kind
        accepted = [{'product_id': p.id, 'units': 1} for p in members if satisfies(p)]
        tasks.append({'split': 'dev' if len(tasks) < 20 else 'heldout', 'family': template,
            'case': ShoppingCase(id=f'shopper-{index}-{template}', request=request,
                author='Generated request over a real merchant catalogue (DR 0018)',
                cluster=f'kind-{index}').model_dump(mode='json'),
            'gold': {'method': 'published_field_rule', 'accepted': accepted,
                     'abstention_correct': not accepted,
                     'spec': {k: str(v) for k, v in spec.items()}, 'kind': kind,
                     'note': 'Any variant of this product type whose published colour, size, '
                             'stock and price satisfy the request. Several answers may be '
                             'correct, as they would be for a real shopper.'}})
    return {'kind': 'shopify_shopper', 'seed': seed, 'inventory': frozen.model_dump(mode='json'),
            'tasks': tasks, 'note': f'{len(frozen.products)} variants. Requests describe the '
            'item by kind, colour and size and never name the catalogue title.'}


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
