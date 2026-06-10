# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
It searches the mock listings dataset (`data/listings.json`) and returns the listings that match the user's keyword description. Results are ranked by keyword relevance so the best match comes first.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `description` (str): Free-text keywords describing what the user wants. Used to score relevance against each listing's `title`, `description`, and `style_tags`.
- `size` (str): Size string to filter by. Matching is case-insensitive and substring-based, so `"M"` matches a listing sized `"S/M"`. Pass `None` to skip size filtering. Optional parameter (default `None`).
- `max_price` (float): Inclusive price ceiling in dollars. Listings priced above this are excluded. Pass `None` to skip price filtering. Optional parameter (default `None`).

**What it returns:**
<!-- Describe the return value — what fields does a result contain? -->
A `list[dict]` sorted by descending relevance (best match first), with every zero-score listing dropped. Each element is a listing dict with these fields: `id` (str), `title` (str), `description` (str), `category` (str: tops/bottoms/outerwear/shoes/accessories), `style_tags` (list[str]), `size` (str), `condition` (str: excellent/good/fair), `price` (float), `colors` (list[str]), `brand` (str | None), `platform` (str: depop/thredUp/poshmark). Returns `[]` when nothing matches.

**What happens if it fails or returns nothing:**
<!-- What should the agent do if no listings match? -->
The function returns `[]` on no match. The agent does not call `suggest_outfit`. Instead it sets `session["error"]` to a helpful message echoing the parsed filters (e.g. *"No listings matched 'designer ballgown' under $5 in size XXS. Try loosening the price or describing the item differently."*) and returns the session early.

---

### Tool 2: suggest_outfit

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
Takes the listing the user is considering plus the user's wardrobe and asks the LLM (Groq) to suggest 1-2 complete, wearable outfits that combine the new item with specific pieces the user already owns. Handles an empty or minimal wardrobe by giving general styling advice instead.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `new_item` (dict): A single listing dict (top result) from `search_listings`. The tool reads its `title`, `category`, `colors`, `style_tags`, and `description` into the prompt.
- `wardrobe` (dict): A wardrobe dict with an `"items"` key holding a `list[dict]`. Each wardrobe item has `id` (str), `name` (str), `category` (str), `colors` (list[str]), `style_tags` (list[str]), and `notes` (str | None). May be empty (`{"items": []}`).

**What it returns:**
<!-- Describe the return value -->
A non-empty `str` of natural-language styling advice. When the wardrobe has items, it names 1–2 outfits referencing specific wardrobe pieces by `name` plus the new item (e.g. *"Pair the butterfly baby tee with your baggy straight-leg jeans and chunky white sneakers…"*). When the wardrobe is empty, it returns general styling advice for the item (what categories/colors/vibes pair well) rather than references to owned pieces.

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the wardrobe is empty or no outfit can be suggested? -->
If `wardrobe["items"]` is empty, the tool indicates that to the user, branches to the general-styling-advice prompt and still returns a useful non-empty string. If the Groq API call raises (network/auth/rate limit), the tool catches the exception and returns a plain-text fallback such as *"Couldn't generate a styled outfit right now, but this {category} in {colors} works well with neutral basics."* so the agent can still continue. The agent treats any non-empty return as success.

---

### Tool 3: create_fit_card

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
Turns an outfit suggestion plus the item details into a short, shareable description of a complete outfit (Instagram post caption style) for the thrifted find. Uses the LLM at a higher temperature so repeated calls read differently for different inputs.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `outfit` (str): The styling string returned by `suggest_outfit()`. Provides the vibe/context for the caption.
- `new_item` (dict): The same listing dict used in `suggest_outfit`. The tool pulls `title`, `price`, and `platform` to mention each naturally once in the caption.

**What it returns:**
<!-- Describe the return value -->
A `str` of 2–4 sentences usable as a caption. It mentions the item name, price, and platform once each, captures the outfit vibe in specific terms, and sounds casual/authentic rather than like a product description.

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the outfit data is incomplete? -->
If `outfit` is `None`, empty, or whitespace-only, the tool returns a descriptive error string (e.g. *"Can't build a fit card without an outfit suggestion."*) instead of calling the LLM. If the Groq call raises, it catches the exception, indicates what is going on to the user, and returns a simple deterministic fallback caption built from `new_item` fields (e.g. *"Thrifted the {title} for ${price} on {platform}. 🔥"*) so the user always sees a card.

---

### Additional Tools (if any)

<!-- Copy the block above for any tools beyond the required three -->

---

## Planning Loop

**How does your agent decide which tool to call next?**
<!-- Describe the logic your planning loop uses. What does it look at? What conditions change its behavior? How does it know when it's done? -->

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

**How does information from one tool get passed to the next?**
<!-- Describe how your agent stores and accesses state within a session. What data is tracked? How is it passed between tool calls? -->

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

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query (returns `[]`) | Agent stops at the step-3 branch and sets `session["error"]` to a helpful message echoing the parsed filters and offering a concrete next move, e.g. *"No listings matched 'designer ballgown' under $5 in size XXS. Try loosening the price or describing the item differently."* It does not call `suggest_outfit`/`create_fit_card` and returns the session early so the user can resubmit with looser criteria. |
| suggest_outfit | Wardrobe is empty (`wardrobe["items"] == []`) | Not a hard error: the tool indicates the empty wardrobe to the user, branches to the general-styling-advice prompt, and still returns a useful non-empty string about what colors/categories/vibes pair with the item. If the Groq call raises, it catches the exception and returns the deterministic fallback *"Couldn't generate a styled outfit right now, but this {category} in {colors} works well with neutral basics."*, and the agent still continues to `create_fit_card`. |
| create_fit_card | Outfit input is missing or incomplete (`None`/empty/whitespace) | The tool skips the LLM and returns a descriptive string stored in `session["fit_card"]`: *"Can't build a fit card without an outfit suggestion."* If instead the Groq call raises, it catches the exception, indicates what's going on, and returns a simple deterministic caption built from `new_item` (*"Thrifted the {title} for ${price} on {platform}. 🔥"*) so the user always leaves with a usable card rather than a crash. |

---

## Architecture

<!-- Draw a diagram of your agent showing how the components connect:
     User input → Planning Loop → Tools (search_listings, suggest_outfit, create_fit_card)
                                                                          ↕
                                                                   State / Session
     Show what triggers each tool, how state flows between them, and where error paths branch off.
     ASCII art, a Mermaid diagram (https://mermaid.js.org/syntax/flowchart.html), or an embedded
     sketch are all fine. You'll share this diagram with an AI tool when asking it to implement
     the planning loop and each individual tool. -->

**Mermaid diagram code block:**

```mermaid
flowchart TD
    User([User]) -->|query + wardrobe| Init["run_agent()<br/>_new_session()"]

    Init -->|stores query, wardrobe| Session[("session dict<br/>query | parsed | search_results<br/>selected_item | wardrobe<br/>outfit_suggestion | fit_card | error")]

    Init -->|raw query| Parse["Step 2: parse query (regex)"]
    Parse -->|"writes parsed:<br/>description, size, max_price"| Session

    Parse -->|"description, size, max_price"| Search["Tool: search_listings<br/>(data_loader, no LLM)"]
    Search -->|"writes search_results (list[dict])"| Session

    Search --> Branch{"search_results<br/>empty?"}

    Branch -->|"yes → no matches"| Err["set session['error']<br/>(echoes parsed filters)"]
    Err -->|"return session early<br/>(outputs stay None)"| EndErr([Caller shows error])

    Branch -->|"no → selected_item = search_results[0]"| Suggest["Tool: suggest_outfit<br/>(Groq LLM)"]
    Suggest -->|"selected_item + wardrobe"| Session
    Suggest -->|"writes outfit_suggestion (str)<br/>empty wardrobe → general advice"| Session

    Suggest -->|"outfit_suggestion + selected_item"| Card["Tool: create_fit_card<br/>(Groq LLM, high temp)"]
    Card -->|"writes fit_card (str)"| Session

    Card -->|"return session (error = None)"| EndOk([Caller renders<br/>item, outfit, fit card])

    classDef errPath fill:#ffe0e0,stroke:#c0392b,color:#000;
    classDef okPath fill:#e0ffe0,stroke:#27ae60,color:#000;
    class Err,EndErr errPath;
    class EndOk okPath;
```

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**
- *search_listings():* I will give Claude Code my Tool 1 specification (inputs, return value, failure mode) from planning.md and ask it to implement search_listings() using load_listings from the data loader. To verify the output, I will test it against 3 different queries and write one pytest test per failure mode.
- *suggest_outfit():* I will give Claude Code my Tool 2 specification (inputs, return value, failure mode) from planning.md and ask it to implement search_listings() using load_listings from the data loader. To verify the output, I will test it against 3 different queries and write one pytest test per failure mode.
- *create_fit_card():* I will give Claude Code my Tool 3 specification (inputs, return value, failure mode) from planning.md and ask it to implement search_listings() using load_listings from the data loader. To verify the output, I will test it against 3 different queries and write one pytest test per failure mode.

**Milestone 4 — Planning loop and state management:**

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
<!-- What does the agent do first? Which tool is called? With what input? -->
The agent searches the listings first. It calls the tool search_listings("vintage graphic tee", size="M", max_price=30.0) which returns 3 matching listings sorted by relevance. FitFindr picks the top result: "Faded Band Tee — $22, Depop, Good condition."

**Step 2:**
<!-- What happens next? What was returned from step 1? What tool is called now? -->
Because Step 1 returned a non-empty list, the agent stored the Faded Band Tee as `session["selected_item"]` and now calls `suggest_outfit(new_item=<band tee>, wardrobe=<user's wardrobe>)`. The item flows in from state, so the user never re-enters it. The wardrobe has items, so the tool takes its specific-outfit prompt path and returns: *"Pair this with your wide-leg jeans and platform Docs for a classic 90s grunge look. Roll the sleeves once and tuck the front corner slightly for shape."* This string is saved to `session["outfit_suggestion"]`.

**Step 3:**
<!-- Continue until the full interaction is complete -->
With a non-empty outfit suggestion in hand, the agent calls `create_fit_card(outfit=<suggestion>, new_item=<band tee>)`, passing both the outfit string and the same selected item from state. Run at a higher temperature, it returns a casual caption that names the item, price, and platform once: *"thrifted this faded band tee off depop for $22 and honestly it was made for my wide-legs 🖤 full look in my stories."* This is stored in `session["fit_card"]`, and with `error` still `None` the loop returns the completed session.

**Final output to user:**
<!-- What does the user actually see at the end? -->
Since `session["error"]` is `None`, the caller renders the full result: the matched listing (Faded Band Tee — $22, Depop, good condition), the outfit suggestion pairing it with the user's wide-leg jeans and platform Docs, and the ready-to-post fit card caption.
