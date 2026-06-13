"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

# Testing branch path: $env:PYTHONIOENCODING="utf-8"; .\.venv\Scripts\python.exe agent.py
# Prove suggest_outfit was never called: $env:PYTHONIOENCODING="utf-8"; .\.venv\Scripts\python.exe -c "import agent; from utils.data_loader import get_example_wardrobe; called={'n':0}; orig=agent.suggest_outfit; agent.suggest_outfit=lambda *a,**k:(called.__setitem__('n',called['n']+1) or orig(*a,**k)); s=agent.run_agent('designer ballgown size XXS under \$5', get_example_wardrobe()); print('error:', s['error']); print('fit_card:', s['fit_card']); print('suggest_outfit call count:', called['n'])"

import re

from tools import search_listings, suggest_outfit, create_fit_card


# ── query parsing ─────────────────────────────────────────────────────────────

# A standalone size token (word-bounded), case-insensitive.
_SIZE_TOKEN = r"(?:XXL|XXS|XL|XS|S|M|L)"

# "size M", "size: M", "in a size L" → captures the token after the word "size".
_SIZE_AFTER_WORD_RE = re.compile(rf"\bsize\b[:\s]*({_SIZE_TOKEN})\b", re.IGNORECASE)

# A bare size token sitting on its own (fallback when "size" isn't written out).
_SIZE_BARE_RE = re.compile(rf"\b({_SIZE_TOKEN})\b")

# A price pattern that only fires on an explicit price cue, so we don't
# treat any stray number (e.g. "501 jeans") as a price ceiling.
_PRICE_CUE_RE = re.compile(
    r"(?:under|below|less than|max|cheaper than|no more than)\s*\$?\s*(\d+(?:\.\d{1,2})?)"
    r"|\$\s*(\d+(?:\.\d{1,2})?)",
    re.IGNORECASE,
)


def _parse_query(query: str) -> dict:
    """
    Extract a free-text `description`, an optional `size`, and an optional
    `max_price` from a natural-language query, per planning.md step 2.

    Returns a dict: {"description": str, "size": str | None, "max_price": float | None}
    The description is the query with the matched price and size phrases stripped
    out; it falls back to the raw query if stripping leaves nothing.
    """
    remaining = query
    size: str | None = None
    max_price: float | None = None

    # 1. max_price — only on an explicit price cue ("under $30", "$30", ...).
    price_match = _PRICE_CUE_RE.search(query)
    if price_match:
        amount = price_match.group(1) or price_match.group(2)
        max_price = float(amount)
        remaining = remaining.replace(price_match.group(0), " ")

    # 2. size — prefer an explicit "size X" phrase, else a bare size token.
    size_match = _SIZE_AFTER_WORD_RE.search(remaining)
    if size_match:
        size = size_match.group(1).upper()
        remaining = remaining.replace(size_match.group(0), " ")
    else:
        bare = _SIZE_BARE_RE.search(remaining)
        if bare:
            size = bare.group(1).upper()
            remaining = remaining[: bare.start()] + " " + remaining[bare.end():]

    # 3. description — what's left, cleaned up; fall back to the raw query.
    description = re.sub(r"\s+", " ", remaining).strip(" ,.-")
    if not description:
        description = query.strip()

    return {"description": description, "size": size, "max_price": max_price}


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.

    TODO — implement this function using the planning loop you designed in planning.md:

        Step 1: Initialize the session with _new_session().

        Step 2: Parse the user's query to extract a description, size, and
                max_price. You can use regex, string splitting, or ask the LLM
                to parse it — document your choice in planning.md.
                Store the result in session["parsed"].

        Step 3: Call search_listings() with the parsed parameters.
                Store results in session["search_results"].
                If no results: set session["error"] to a helpful message and
                return the session early. Do NOT proceed to suggest_outfit
                with empty input.

        Step 4: Select the item to use (e.g., the top result).
                Store it in session["selected_item"].

        Step 5: Call suggest_outfit() with the selected item and wardrobe.
                Store the result in session["outfit_suggestion"].

        Step 6: Call create_fit_card() with the outfit suggestion and selected item.
                Store the result in session["fit_card"].

        Step 7: Return the session.

    Before writing code, complete the Planning Loop and State Management sections
    of planning.md — your implementation should match what you described there.
    """
    # Step 1: Initialize the session.
    session = _new_session(query, wardrobe)

    # Step 2: Parse the query into description / size / max_price.
    session["parsed"] = _parse_query(query)
    parsed = session["parsed"]

    # Step 3: Search the listings, then branch on the result.
    session["search_results"] = search_listings(
        parsed["description"],
        size=parsed["size"],
        max_price=parsed["max_price"],
    )
    if not session["search_results"]:
        # No matches → set a helpful error echoing the parsed filters and
        # return early. Do NOT call suggest_outfit/create_fit_card.
        filters = [f"'{parsed['description']}'"]
        if parsed["max_price"] is not None:
            filters.append(f"under ${parsed['max_price']:g}")
        if parsed["size"] is not None:
            filters.append(f"in size {parsed['size']}")
        session["error"] = (
            f"No listings matched {' '.join(filters)}. "
            f"Try loosening the price or describing the item differently."
        )
        return session

    # Step 4: Select the top-ranked result.
    session["selected_item"] = session["search_results"][0]

    # Step 5: Suggest an outfit (tool picks its own prompt path; always non-empty).
    #         Read wardrobe from the session — it's the single source of truth.
    session["outfit_suggestion"] = suggest_outfit(
        session["selected_item"], session["wardrobe"]
    )

    # Step 6: Build the shareable fit card.
    session["fit_card"] = create_fit_card(
        session["outfit_suggestion"], session["selected_item"]
    )

    # Step 7: Return the completed session (error stays None on success).
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message:     {session2['error']}")
    print(f"fit_card:          {session2['fit_card']}")           # expect: None
    print(f"outfit_suggestion: {session2['outfit_suggestion']}")  # expect: None

