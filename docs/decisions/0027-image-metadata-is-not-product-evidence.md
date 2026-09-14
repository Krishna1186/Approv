# DR 0027: Image metadata is not product evidence

Date: 2026-09-14. Closed the same day. Required by invariant 8: it changes what derivation
proposes, and therefore what findings a comparison can carry.

## What was wrong

Found by the public-feed audit, not by a fixture. Real Shopify feeds publish a
`featured_image` object on every product, and it carries `width`, `height`, `alt`, `src`,
`position` and `aspect_ratio`. The catalogue walk saw a nested object with occupied scalar
fields and did what it does everywhere else: proposed them as product attributes, at
`EXACT` certainty, under `MERCHANT_GUARANTEED` liability.

So a merchant's derived schema acquired a `width` attribute whose value was **2048**, and
its source was a photograph.

This is the dangerous half of the failure taxonomy. A missing attribute is visible — the
partner report shows it as unpublished and nobody guarantees it. A *wrong* attribute is
confident, exact, and merchant-liable, and the shape of the mistake is the one §7 puts
first: an agent asks for a width, an attribute called width exists and is satisfied, and
the record says the merchant delivered what was asked.

## The decision

**A subtree that describes a rendering of the product is not a source of product
attributes.** Image metadata is excluded from derivation at the walk, by path, before any
attribute is proposed — not filtered afterwards in `derive`, because the exclusion is a
fact about what the field *is*, and every consumer of `flatten` needs it to hold.

Excluded: `src`, `width`, `height`, `aspect_ratio`, `position`, `variant_ids`, `updated_at`
and `created_at` beneath an image object, and the image object itself as a value.

`alt` is excluded with them, and it is the only one worth arguing about. Alt text is
merchant-authored prose and sometimes carries a real fact — *"navy linen shirt, size 42"*.
Three reasons it still goes:

1. It is written for accessibility, not as a commitment about the goods. §4 admits
   published *merchant fields* as ground truth because the merchant is answerable for
   them; nobody has ever been asked to stand behind alt text at a returns desk.
2. It describes **one photograph**, which on a multi-variant listing is usually not the
   variant that was ordered. DR 0024 scoped evidence to the ordered line; alt text is
   scoped to whatever the merchandiser featured.
3. It is the residual-risk category §7 names — text nobody is answerable for — sitting
   inside a first-party feed where the rest of the object is guaranteed.

## What this costs

A real published fact occasionally appears only in alt text and is now unread. That is a
coverage loss, not a correctness loss: the attribute reads as unpublished, nothing
guarantees it, and the partner report says so. Losing a guarantee we could have sold is
the error we are willing to make; selling one against a photograph's pixel count is not.

## What it does not decide

Whether an image can ever be evidence *of* anything — a delivered-item photograph in a
dispute is a different artifact and a different question. This rules only on derivation:
image metadata does not become a product attribute.
