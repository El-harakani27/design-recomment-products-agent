---
name: search-products
description: How to find matching furniture in the store catalog using SQL. Use whenever you need to look up products to recommend for a room - it documents the `catalog` table, the exact vocabulary stored in each column, and the search strategy that works at this catalog size.
---

# Searching the product catalog

You query the catalog by writing SQL and passing it to `run_sql(sql, category)`.

## The one table you can see

There is exactly one relation: **`catalog`**. It is already filtered for you:

- only the **category the shopper picked** before uploading their photo
- only products that are **in stock**

You never need `WHERE category = ...` or `WHERE in_stock = 1`. They are applied
already. There is no way to see other categories or out-of-stock items, and
trying will error rather than return rows — do not attempt it as a fallback.

**After filtering, a category holds only 4–7 products.** This is the single most
important fact about searching here. See [Strategy](#strategy).

## Columns

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT | e.g. `CT-001`. Use this to refer to a product. |
| `sku`, `name`, `brand` | TEXT | |
| `short_description` | TEXT | One line. |
| `description` | TEXT | Two or three sentences of factual product copy. |
| `price` | REAL | **What the customer pays today** — already reflects any sale. Use this one. |
| `list_price`, `on_sale` | REAL, 0/1 | Only for showing a discount. |
| `width_cm`, `depth_cm`, `height_cm` | REAL | **Out of scope — do not filter on these.** See below. |
| `weight_kg` | REAL | Out of scope for matching. Over ~45 kg implies a two-person lift, worth a caveat. |
| `primary_material` | TEXT | Single value. |
| `materials` | TEXT | **Comma-separated list** — match with `LIKE`. |
| `finish` | TEXT | Single value. |
| `colors` | TEXT | Human colour names, e.g. `Natural Oak, Chalk White`. |
| `color_families` | TEXT | **Comma-separated list** — coarser buckets, better for matching. |
| `styles` | TEXT | **Comma-separated list**. |
| `room_types` | TEXT | **Comma-separated list**. |
| `tags` | TEXT | **Comma-separated list** of free keywords. |
| `storage_type` | TEXT | Single value. |
| `drawers`, `shelves` | INTEGER | Counts. |
| `wall_mounted`, `extendable`, `cable_management` | 0/1 | |
| `assembly_minutes` | INTEGER | |
| `attributes` | TEXT | **JSON**, category-specific. See below. |
| `care` | TEXT | Maintenance burden — useful for caveats. |
| `rating`, `reviews_count` | REAL, INTEGER | |
| `lead_time_days` | INTEGER | |
| `image_main`, `product_url` | TEXT | For presenting the result. |

### Exact vocabulary stored in the list columns

Match against these strings. Anything else returns nothing.

- **`styles`** — `scandinavian`, `japandi`, `minimalist`, `mid_century_modern`,
  `industrial`, `contemporary`, `traditional`, `rustic_farmhouse`, `bohemian`,
  `art_deco`, `coastal`, `brutalist_concrete`
- **`color_families`** — `light_wood`, `warm_wood`, `dark_wood`, `white`,
  `off_white`, `beige`, `greige`, `black`, `brass_gold`, `chrome_silver`,
  `glass_clear`, `marble_white`, `concrete_grey`
- **`materials`** / **`primary_material`** — `solid_oak`, `oak_veneer`,
  `solid_ash`, `walnut_veneer`, `solid_pine`, `mango_wood`, `woven_cane`,
  `mdf_lacquer`, `melamine_particleboard`, `powder_coated_steel`,
  `brushed_brass`, `chrome_steel`, `tempered_glass`, `carrara_marble`,
  `travertine`, `micro_cement`, `sintered_stone`, `linen_fabric`
- **`room_types`** — `living_room`, `dining_room`, `entryway`, `hallway`,
  `bedroom`, `home_office`, `studio_apartment`
- **`finish`** — `matte_lacquer`, `satin_lacquer`, `high_gloss`, `natural_oil`,
  `wax_oil`, `powder_coated`, `polished`, `honed`, `veneered`, `raw`
- **`storage_type`** — `none`, `open_shelf`, `drawers`, `closed_doors`,
  `tip_out_flap`, `mixed`

### `attributes` JSON keys, by category

Read with `json_extract(attributes, '$.key')`. A key absent from a row returns
`NULL`, so always allow for that.

| Category | Keys |
|---|---|
| `coffee_table` | `nesting`, `pieces`, `natural_stone`, `tempered`, `shows_fingerprints`, `handwoven`, `handcast`, `two_person_lift` |
| `dining_table` | `seats`, `seats_extended`, `extended_width_cm`, `heat_resistant`, `two_person_lift` |
| `side_table` | `laptop_friendly`, `requires_sofa_clearance_cm`, `natural_stone`, `single_block` |
| `console_table` | `doors`, `soft_close`, `anti_tip_kit_included`, `sofa_back_height_max_cm`, `natural_stone`, `floor_load_check`, `two_person_lift` |
| `tv_unit` | `max_tv_inches`, `max_load_kg`, `doors`, `open_bays`, `ir_transparent_doors`, `requires_solid_wall`, `curved_ends`, `dual_purpose` |
| `shoe_storage` | `capacity_pairs`, `fits_boots`, `max_shoe_size_eu`, `flaps`, `doors`, `mirror`, `ventilated`, `stackable`, `adjustable_shelves`, `seat_height_cm`, `max_seated_load_kg`, `console_height`, `pieces` |

### Price ranges, in-stock, per category

`coffee_table` 249–549 · `dining_table` 279–1299 · `side_table` 79–329 ·
`console_table` 169–629 · `tv_unit` 99–799 · `shoe_storage` 59–269 (EUR)

Use these to sanity-check a budget. If a shopper's budget is under the category
minimum, say so rather than returning nothing.

## Strategy

**Your query is built from the brief you were sent. Never run a blind category dump.**

You are not answering "what TV units does the store sell". You are answering
"which TV unit suits *this* room". The brief you were handed is the input to the
SQL — every clause you write should trace back to a line in it.

The method is two steps: **decide which stored values this room calls for, then
select the products carrying them.**

```sql
SELECT <columns>
FROM catalog
WHERE <values from your mapping, OR'd together>
  AND <values that would clash, excluded>
ORDER BY rating DESC
```

Match broadly inside each group. A room read as "warm modern Scandinavian" is
served by `scandinavian` *or* `japandi` *or* `minimalist` — list every value that
genuinely fits and join them with `OR`. Narrowing to one value is how you end up
with nothing.

Add `WHERE price <= …` only if the shopper stated a budget in words. Do not
infer a ceiling from the photo.

**If the query returns nothing, widen it and run again.** Drop the most
restrictive group — usually materials, then colours — and keep style. Say in your
answer that you widened, and what you dropped. An empty result is never the final
answer; it means the mapping was too tight for a category holding 4–7 rows.

### Size is out of scope for now

Ignore `width_cm`, `depth_cm`, `height_cm` and `weight_kg`. Do not filter on
them, and do not try to reason about whether a piece physically fits.

The brief you receive carries no measurements, and guessing dimensions from a
photo is unreliable enough that a confident wrong answer is worse than none. If
size genuinely decides the recommendation, say so in your written reasoning and
tell the shopper to measure — do not put a number in the SQL.

### What you receive: a design brief

The orchestrator sends a brief in plain language. It deliberately contains **no
database values** — it does not know the vocabulary, and you do. Translating the
brief into stored values is your job and yours alone.

```
CATEGORY: console_table

WHAT THE ROOM IS
Bright, warm, uncluttered living room. Light beige walls, medium oak floor,
beige sofa. Calm and simple - warm modern Scandinavian, natural wood, minimal
decoration.

MATCH OR CONTRAST
Match. The room is already coherent - echo the oak and the neutrals. Do not
introduce a focal point in dark or polished materials.

AVOID
Anything industrial, heavy or high-shine.
```

Each section feeds a different part of your mapping:

| Brief section | Lands in |
|---|---|
| `WHAT THE ROOM IS` | `STYLES`, `COLOURS`, `MATERIALS`, and any `FUNCTION` need it mentions |
| `MATCH OR CONTRAST` | decides whether `COLOURS` echoes the room or opposes it |
| `AVOID` | `AVOID` |

The brief carries no separate list of functional needs. If `WHAT THE ROOM IS`
mentions a problem — clutter on show, nowhere to sit, cables loose — map it to
`FUNCTION` and treat it as a requirement. If it mentions none, leave `FUNCTION`
empty rather than inventing one; a storage constraint nobody asked for is a good
way to exclude the right product.

The brief describes a room in ordinary words. The database stores fixed strings.
The columns will not match on "pale honey-coloured floorboards", only on
`light_wood`. That translation is the whole of Step 1.

If the brief is vague or contradicts itself, say so in your reply rather than
guessing — the orchestrator can send a corrected one.

Common phrasings, and the value they map to:

| The brief is likely to say | Stored value |
|---|---|
| pale / honey / blond / ash floorboards | `light_wood` |
| golden, honey-toned, mid-brown, teak-like | `warm_wood` |
| espresso, wenge, near-black timber | `dark_wood` |
| cool grey, greige, taupe walls | `greige`, `white`, `off_white` |
| black metal, dark steel frames | `black`, `powder_coated_steel` |
| gold, brass accents | `brass_gold` |
| woven, rattan, cane, natural texture | `woven_cane`, `bohemian`, `coastal` |
| exposed brick, raw, warehouse, loft | `industrial`, `brutalist_concrete` |
| plain, undecorated, calm, pared-back | `minimalist`, `scandinavian`, `japandi` |
| ornate, classic, panelled | `traditional`, `art_deco` |

And the recurring problems in `gaps`, which are usually the most useful signal:

| Gap observed | Column that fixes it |
|---|---|
| cables hanging loose | `cable_management = 1` |
| clutter on the floor or surfaces | `storage_type IN ('closed_doors','drawers','tip_out_flap','mixed')` |
| room feels cramped, floor crowded | `wall_mounted = 1` |
| nowhere to sit / put shoes on | `json_extract(attributes, '$.seat_height_cm') IS NOT NULL` |
| no surface to put things down | `storage_type != 'none'` |
| dark, no light bounced around | light `color_families`, `tempered_glass` |
| everything on show, no order | `storage_type` with doors, or `drawers > 0` |

If an observation has no column that represents it — "the room feels unwelcoming",
"the art is badly hung" — do not invent a clause for it. Carry it into your
written reasoning instead. Not every judgement belongs in SQL.

### Step 1 — write the mapping before you write any SQL

Do not go straight from the brief to a query. First commit, in writing, to
which stored values this room calls for. The SQL then falls out of the mapping
almost mechanically, and anyone reading your answer can check your reasoning
instead of reverse-engineering it from a `WHERE` clause.

Produce exactly this, before any tool call:

```
STYLES    → values from the styles vocabulary
COLOURS   → values from color_families
MATERIALS → values from materials
FUNCTION  → column conditions answering the gaps
AVOID     → values that would clash, to exclude
REASONING → one or two lines on why, especially anything non-obvious
```

Rules for the mapping:

- **Only values that exist.** Every name must come from the vocabulary lists
  above. `warm_oak` is not a value; `warm_wood` is. If you cannot find a value
  for an observation, it belongs in `REASONING`, not in the query.
- **List every value that fits, not just the closest one.** These become an `OR`
  group. Three or four style values is normal; one is usually too few.
- **Decide match or contrast, and say which.** A medium oak floor can be echoed
  (`warm_wood`, for a calm continuous look) or deliberately offset (`black`,
  `marble_white`, for definition). Both are defensible. Picking one silently is
  not — put the choice in `REASONING`.
- **Keep `AVOID` short.** Only values that would genuinely fight the room. Every
  entry removes a product from consideration permanently, so an over-long `AVOID`
  list is the fastest way to an empty result.

### Step 2 — turn the mapping into one query

Each mapping group becomes one bracketed `OR` group in the `WHERE` clause,
joined to the others with `AND`. `AVOID` becomes `NOT LIKE`.

```sql
SELECT id, name, price, styles, color_families
FROM catalog
WHERE (styles LIKE '%scandinavian%' OR styles LIKE '%japandi%')
  AND (color_families LIKE '%warm_wood%' OR color_families LIKE '%light_wood%')
  AND styles NOT LIKE '%industrial%'
ORDER BY rating DESC
```

Include the columns you matched on in the `SELECT` list. You need to see what a
product actually carries to write an honest reason for it.

### Step 3 — read the rows, then judge

The query narrows the field; it does not make the decision. A returned product
can still be wrong for the room, and saying so is a better answer than a
confident bad pick. Check the rows against the brief yourself, and look at
`description` and `care` before committing.

**Never invent a product.** Only recommend `id`s that came back from a query.

## Worked example

Working from the `console_table` brief shown above — the bright, warm, calm
living room with a medium oak floor, short on closed storage.

**Step 1 — the mapping.** Note that every value below comes from the vocabulary
lists, and none of them appeared in the brief:

```
STYLES    → scandinavian, japandi, minimalist, contemporary
COLOURS   → warm_wood, light_wood, beige, off_white, white
MATERIALS → solid_oak, solid_ash, mango_wood
FUNCTION  → storage_type IN ('closed_doors','drawers','mixed') OR drawers > 0
            [gaps: "limited decorative storage"]
AVOID     → industrial, brutalist_concrete styles; high_gloss finish
REASONING → Echoing the medium oak floor rather than contrasting it: the room is
            already warm, neutral and calm, and black or polished stone would
            create a focal point it did not ask for. Storage is the only gap a
            console can answer, so it is a requirement rather than a preference.
            Muted green in the palette comes from a plant, not the scheme - not
            mapped. Materials left out of the WHERE clause to avoid over-
            narrowing; used to choose between the rows that come back.
```

**Step 2 — the query:**

```sql
SELECT id, name, price, styles, color_families, primary_material,
       storage_type, drawers, rating
FROM catalog
WHERE (styles LIKE '%scandinavian%' OR styles LIKE '%japandi%'
       OR styles LIKE '%minimalist%' OR styles LIKE '%contemporary%')
  AND (color_families LIKE '%warm_wood%' OR color_families LIKE '%light_wood%'
       OR color_families LIKE '%beige%'  OR color_families LIKE '%off_white%'
       OR color_families LIKE '%white%')
  AND (storage_type IN ('closed_doors','drawers','mixed') OR drawers > 0)
  AND styles NOT LIKE '%industrial%'
  AND styles NOT LIKE '%brutalist_concrete%'
  AND finish != 'high_gloss'
ORDER BY rating DESC
```

Three rows come back — `CN-003`, `CN-001`, `CN-004`. Every clause traces to a
line in the mapping, and every value in it exists in the vocabulary.

**Step 3 — judge.** `CN-001` is solid oak, `scandinavian, japandi, minimalist`,
light wood, with drawers: it answers the storage gap and echoes the floor.
`CN-003` has the higher rating but is `art_deco` with brass — it satisfied the
`contemporary` clause and slipped through, which is exactly the kind of thing you
must catch by reading the rows rather than trusting their order.

## Query patterns

Matching a list column — one bracketed `OR` group per mapping line:

```sql
SELECT id, name, styles, color_families
FROM catalog
WHERE (styles LIKE '%industrial%' OR styles LIKE '%minimalist%')
  AND (color_families LIKE '%black%' OR color_families LIKE '%concrete_grey%')
```

No style, colour-family or material name is a substring of another, so a plain
`LIKE '%value%'` is safe. If you ever need an exact whole-item match, wrap both
sides: `',' || REPLACE(styles, ', ', ',') || ',' LIKE '%,industrial,%'`.

Excluding what clashes:

```sql
SELECT id, name, styles, finish
FROM catalog
WHERE styles NOT LIKE '%industrial%'
  AND finish != 'high_gloss'
```

Free-text across the descriptive columns:

```sql
SELECT id, name, description
FROM catalog
WHERE description LIKE '%cane%' OR tags LIKE '%rattan%' OR materials LIKE '%cane%'
```

Category-specific JSON. A key missing from a row returns `NULL`, and `NULL` fails
every comparison, so wrap it in `COALESCE` when you filter:

```sql
SELECT id, name,
       json_extract(attributes, '$.doors')     AS doors,
       json_extract(attributes, '$.open_bays') AS open_bays
FROM catalog
WHERE COALESCE(json_extract(attributes, '$.doors'), 0) > 0
```

```sql
SELECT id, name,
       json_extract(attributes, '$.capacity_pairs') AS pairs,
       json_extract(attributes, '$.fits_boots')     AS boots
FROM catalog
ORDER BY pairs DESC
```

Seating capacity, counting the extended size:

```sql
SELECT id, name,
       json_extract(attributes, '$.seats')          AS seats,
       json_extract(attributes, '$.seats_extended') AS seats_max
FROM catalog
WHERE COALESCE(json_extract(attributes, '$.seats_extended'),
               json_extract(attributes, '$.seats'), 0) >= 6
```

## Always single-quote string literals

SQLite resolves a double-quoted word as a **column name** first, and only falls
back to treating it as text if no such column exists. Several stored values share
a name with a column — `drawers`, `shelves`, `doors`, `mixed` — so this bites:

```sql
-- WRONG: "drawers" resolves to the drawers column (an integer), so this
-- silently matches nothing whose storage_type is actually 'drawers'
WHERE storage_type IN ("closed_doors", "drawers", "mixed")

-- RIGHT
WHERE storage_type IN ('closed_doors', 'drawers', 'mixed')
```

There is no error either way — the query runs and returns a confidently wrong
ranking. **Single quotes for values, always.**

## Limits

- One statement per call. No `;` inside the SQL.
- `SELECT` or `WITH ... SELECT` only. Any write is rejected.
- Maximum 50 rows returned.
- `catalog` is the only readable relation. Referencing `products` will error.

## Reporting back

For each product you recommend, give its `id` and explain the choice in terms of
**what you saw in the room photo** — the light, the existing pieces, the wall
colour, the space available — set against the product's actual measurements and
materials. Cite the specific column that supports the claim.

The catalog stores facts, not opinions. There is no "why this suits the room"
field, because that judgement is yours to make and defend.

Mention a real drawback where one exists — `care` burden, `assembly_minutes`,
`weight_kg`, `lead_time_days`, or an attribute like `shows_fingerprints` or
`requires_solid_wall`. A recommendation with no caveat reads as a sales pitch.
