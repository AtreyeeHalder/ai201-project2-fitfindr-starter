# FitFindr — Starter Kit

This starter kit contains everything you need to begin Project 2.

## What's Included

```
ai201-project2-fitfindr-starter/
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # Wardrobe format + example wardrobe
├── utils/
│   └── data_loader.py         # Helper functions for loading the data
├── planning.md                # Your planning template — fill this out first
└── requirements.txt           # Python dependencies
```

## Setup

```bash
pip install -r requirements.txt
```

Set your Groq API key in a `.env` file (get a free key at [console.groq.com](https://console.groq.com)):
```
GROQ_API_KEY=your_key_here
```

## The Mock Listings Dataset

`data/listings.json` contains 40 mock secondhand listings across categories (tops, bottoms, outerwear, shoes, accessories) and styles (vintage, y2k, grunge, cottagecore, streetwear, and more).

Each listing has: `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, and `platform`.

Load it with:
```python
from utils.data_loader import load_listings
listings = load_listings()
```

## The Wardrobe Schema

`data/wardrobe_schema.json` defines the format your agent uses to represent a user's existing wardrobe. It includes:

- `schema`: field definitions for a wardrobe item
- `example_wardrobe`: a sample wardrobe with 10 items you can use for testing
- `empty_wardrobe`: a starting template for a new user

Load an example wardrobe with:
```python
from utils.data_loader import get_example_wardrobe
wardrobe = get_example_wardrobe()
```

## Where to Start

1. **Read `planning.md` and fill it out before writing any code.**
2. Verify the data loads correctly by running `python utils/data_loader.py`.
3. Build and test each tool individually before connecting them through your planning loop.

Your implementation files go in this same directory. There's no required file structure for your agent code — organize it however makes sense for your design.

---

# FitFindr — Project 2

---

## Tool Inventory

### Tool 1: search_listings

**What it does:**

It searches the mock listings dataset (`data/listings.json`) and returns the listings that match the user's keyword description. Results are ranked by keyword relevance so the best match comes first.

**Input parameters:**

- `description` (str): Free-text keywords describing what the user wants. Used to score relevance against each listing's `title`, `description`, and `style_tags`.
- `size` (str): Size string to filter by. Matching is case-insensitive and substring-based, so `"M"` matches a listing sized `"S/M"`. Pass `None` to skip size filtering. Optional parameter (default `None`).
- `max_price` (float): Inclusive price ceiling in dollars. Listings priced above this are excluded. Pass `None` to skip price filtering. Optional parameter (default `None`).

**What it returns:**

A `list[dict]` sorted by descending relevance (best match first), with every zero-score listing dropped. Each element is a listing dict with these fields: `id` (str), `title` (str), `description` (str), `category` (str: tops/bottoms/outerwear/shoes/accessories), `style_tags` (list[str]), `size` (str), `condition` (str: excellent/good/fair), `price` (float), `colors` (list[str]), `brand` (str | None), `platform` (str: depop/thredUp/poshmark). Returns `[]` when nothing matches.

**What happens if it fails or returns nothing:**

The function returns `[]` on no match. The agent does not call `suggest_outfit`. Instead it sets `session["error"]` to a helpful message echoing the parsed filters (e.g. *"No listings matched 'designer ballgown' under $5 in size XXS. Try loosening the price or describing the item differently."*) and returns the session early.

---

### Tool 2: suggest_outfit

**What it does:**

Takes the listing the user is considering plus the user's wardrobe and asks the LLM (Groq) to suggest 1-2 complete, wearable outfits that combine the new item with specific pieces the user already owns. Handles an empty or minimal wardrobe by giving general styling advice instead.

**Input parameters:**

- `new_item` (dict): A single listing dict (top result) from `search_listings`. The tool reads its `title`, `category`, `colors`, `style_tags`, and `description` into the prompt.
- `wardrobe` (dict): A wardrobe dict with an `"items"` key holding a `list[dict]`. Each wardrobe item has `id` (str), `name` (str), `category` (str), `colors` (list[str]), `style_tags` (list[str]), and `notes` (str | None). May be empty (`{"items": []}`).

**What it returns:**

A non-empty `str` of natural-language styling advice. When the wardrobe has items, it names 1–2 outfits referencing specific wardrobe pieces by `name` plus the new item (e.g. *"Pair the butterfly baby tee with your baggy straight-leg jeans and chunky white sneakers…"*). When the wardrobe is empty, it returns general styling advice for the item (what categories/colors/vibes pair well) rather than references to owned pieces.

**What happens if it fails or returns nothing:**

If `wardrobe["items"]` is empty, the tool indicates that to the user, branches to the general-styling-advice prompt and still returns a useful non-empty string. If the Groq API call raises (network/auth/rate limit), the tool catches the exception and returns a plain-text fallback such as *"Couldn't generate a styled outfit right now, but this {category} in {colors} works well with neutral basics."* so the agent can still continue. The agent treats any non-empty return as success.

---

### Tool 3: create_fit_card

**What it does:**

Turns an outfit suggestion plus the item details into a short, shareable description of a complete outfit (Instagram post caption style) for the thrifted find. Uses the LLM at a higher temperature so repeated calls read differently for different inputs.

**Input parameters:**

- `outfit` (str): The styling string returned by `suggest_outfit()`. Provides the vibe/context for the caption.
- `new_item` (dict): The same listing dict used in `suggest_outfit`. The tool pulls `title`, `price`, and `platform` to mention each naturally once in the caption.

**What it returns:**

A `str` of 2–4 sentences usable as a caption. It mentions the item name, price, and platform once each, captures the outfit vibe in specific terms, and sounds casual/authentic rather than like a product description.

**What happens if it fails or returns nothing:**

If `outfit` is `None`, empty, or whitespace-only, the tool returns a descriptive error string (e.g. *"Can't build a fit card without an outfit suggestion."*) instead of calling the LLM. If the Groq call raises, it catches the exception, indicates what is going on to the user, and returns a simple deterministic fallback caption built from `new_item` fields (e.g. *"Thrifted the {title} for ${price} on {platform}. 🔥"*) so the user always sees a card.

---

## Planning Loop

The loop is a state-driven pipeline with a real conditional branch. After each tool returns, the agent inspects what came back (stored on `session`) and decides whether to continue, exit early, or change which prompt path the next tool takes. The `session` dict is the single source of state passed between steps.

1. **Initialize.** `session = _new_session(query, wardrobe)`. All result fields start as `None`/`[]`, `error` is `None`.

2. **Parse the query.** Extract `description`, `size`, `max_price` from `query` and store them in `session["parsed"]`.
   - `max_price`: regex-match a dollar amount after "under"/"below"/"$" (e.g. `under $30` -> `30.0`); else `None`.
   - `size`: regex-match a size token after the word "size", or a standalone `XS|S|M|L|XL|XXL` token (e.g. `size M` -> `"M"`); else `None`.
   - `description`: the query with the matched price and size phrases stripped out and trimmed (e.g. `"vintage graphic tee"`); falls back to the raw query.

3. **Call `search_listings(description, size, max_price)`** and store the list in `session["search_results"]`.
   **Branch: inspect the result before choosing the next tool:**
   - **If `search_results` is empty:** set `session["error"]` to a helpful message that echoes the parsed filters, and **return the session immediately.** Do not call `suggest_outfit` or `create_fit_card`. (`outfit_suggestion` and `fit_card` stay `None`.)
   - **If `search_results` is non-empty:** set `session["selected_item"] = session["search_results"][0]` (top-ranked) and proceed to step 4.

4. **Call `suggest_outfit(selected_item, wardrobe)`** and store the string in `session["outfit_suggestion"]`. The tool itself inspects `wardrobe["items"]` and picks its prompt path (specific outfits vs. general advice), so the agent does not exit here. `suggest_outfit` is contracted to always return a non-empty string, so the loop proceeds unconditionally.

5. **Call `create_fit_card(outfit_suggestion, selected_item)`** and store the string in `session["fit_card"]`.

6. **Return `session`.** On success `error` is `None`, and `selected_item`, `outfit_suggestion`, and `fit_card` are all populated.

**How it knows it's done:** the pipeline either reaches step 6 (success) or returns early at step 3 (no results). There is no retry/iteration, but exactly 1 pass, with the step-3 branch being the point where the agent responds to what it received instead of blindly continuing.

---

## State Management

A single `session` dict (created by `_new_session()`) is the one source of truth for the whole interaction. Each step writes its output into a named field; the next step reads from that field. Every hand-off is an explicit read/write on `session`. Critically, the item found by `search_listings` flows into `suggest_outfit` (and then `create_fit_card`) via `session["selected_item"]` without the user re-entering it.

| Field | Written by | Read by |
|-------|-----------|---------|
| `query` | `_new_session` (input) | Step 2 parser |
| `parsed` (`{description, size, max_price}`) | Step 2 parser | Step 3 `search_listings` args |
| `search_results` (list[dict]) | Step 3 | Step 3 branch + step 4 selection |
| `selected_item` (dict) | Step 4 selection (`search_results[0]`) | `suggest_outfit`, `create_fit_card` |
| `wardrobe` (dict) | `_new_session` (input) | `suggest_outfit` |
| `outfit_suggestion` (str) | Step 4 | `create_fit_card`, final output |
| `fit_card` (str) | Step 5 | final output |
| `error` (str \| None) | any early-exit step | caller checks first |

The caller (`app.py` / CLI) reads `session["error"]` first: if non-`None`, it shows the error and ignores the (still-`None`) output fields; otherwise it renders `selected_item`, `outfit_suggestion`, and `fit_card`.

---

## Error Handling Per Tool

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query (returns `[]`) | Agent stops at the step-3 branch and sets `session["error"]` to a helpful message echoing the parsed filters and offering a concrete next move, e.g. *"No listings matched 'designer ballgown' under $5 in size XXS. Try loosening the price or describing the item differently."* It does not call `suggest_outfit`/`create_fit_card` and returns the session early so the user can resubmit with looser criteria. |
| suggest_outfit | Wardrobe is empty (`wardrobe["items"] == []`) | Not a hard error: the tool indicates the empty wardrobe to the user, branches to the general-styling-advice prompt, and still returns a useful non-empty string about what colors/categories/vibes pair with the item. If the Groq call raises, it catches the exception and returns the deterministic fallback *"Couldn't generate a styled outfit right now, but this {category} in {colors} works well with neutral basics."*, and the agent still continues to `create_fit_card`. |
| create_fit_card | Outfit input is missing or incomplete (`None`/empty/whitespace) | The tool skips the LLM and returns a descriptive string stored in `session["fit_card"]`: *"Can't build a fit card without an outfit suggestion."* If instead the Groq call raises, it catches the exception, indicates what's going on, and returns a simple deterministic caption built from `new_item` (*"Thrifted the {title} for ${price} on {platform}. 🔥"*) so the user always leaves with a usable card rather than a crash. |

## Examples of Error Handling from Testing

### Test 1: `search_listings` returning zero results

**Code (Terminal):** `python -c "from tools import search_listings; print(search_listings('designer ballgown', size='XXS', max_price=5))"`

**OUTPUT:**

[]

**Screenshot:**

![Test 1 terminal](assets/Test%201%20terminal.png)

**Running full agent in app - user prompt:** designer ballgown under $5, size XXS

**OUTPUT:**

No listings matched 'designer ballgown' under $5 in size XXS. Try loosening the price or describing the item differently.

**Screenshot:**

![Test 1 app](assets/Test%201%20app.png)

### Test 2: `suggest_outfit` with an empty wardrobe

**Code (Terminal):**
```python
python -c "
from tools import search_listings, suggest_outfit
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(suggest_outfit(results[0], get_empty_wardrobe()))
"
```

**OUTPUT:**

Your wardrobe is empty, so here's some general styling advice for this piece instead:

I'm so excited about this Y2K Baby Tee. The butterfly print is adorable and perfect for adding a touch of whimsy to any outfit. Since it's a fitted, cropped tee, it pairs well with high-waisted bottoms like jeans, skirts, or shorts. You can also layer it under cardigans or kimonos for a more relaxed, cottagecore vibe. The pastel colors in the butterfly graphic - white, pink, and purple - are easy to match with neutral shades like beige, black, or blue, but feel free to have fun and experiment with bold, bright hues too.

For example, you could style this tee with high-waisted mom jeans and a pair of chunky sneakers for a casual, retro-inspired look. Or, dress it up with a flowy, white skirt and some strappy sandals for a sweet, summery outfit. Remember, the key to rocking this tee is to balance its sweetness with some edgier or more laid-back pieces. Don't be afraid to mix and match different styles and eras to create a look that's uniquely yours. Have fun and get creative with this cute little tee - I just know you'll come up with something amazing!

**Screenshot:**

![Test 2](assets/Test%202.png)

### Test 3: `create_fit_card` with an empty outfit string

**Code (Terminal):**
```python
python -c "
from tools import search_listings, create_fit_card
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(create_fit_card('', results[0]))
"
```

**OUTPUT:**

Can't build a fit card without an outfit suggestion.

**Screenshot:**

![Test 3](assets/Test%203.png)

---

## Spec Reflection

<!-- one way the spec helped you, one way implementation diverged from it and why -->

---

## AI Usage

**Instance 1**

- *What I gave the AI:*
- *What it produced:*
- *What I changed or overrode:*

**Instance 2**

- *What I gave the AI:*
- *What it produced:*
- *What I changed or overrode:*

---

## Demo Video

Google Drive link:
