import tools
from tools import search_listings, suggest_outfit, create_fit_card

# --- search_listings ---------------------------------------------------------

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0

def test_search_empty_results():
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []   # empty list, no exception

def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


# --- suggest_outfit ---------------------------------------------------------

# A minimal fake Groq client so tests never make a real API call.
class _FakeMessage:
    content = "Pair it with your jeans and white sneakers for an easy look."

class _FakeChoice:
    message = _FakeMessage()

class _FakeCompletion:
    choices = [_FakeChoice()]

class _FakeClient:
    class chat:
        class completions:
            @staticmethod
            def create(*args, **kwargs):
                return _FakeCompletion()


SAMPLE_ITEM = {
    "title": "Y2K Baby Tee — Butterfly Print",
    "category": "tops",
    "colors": ["white", "pink"],
    "style_tags": ["y2k", "graphic tee"],
    "description": "Cute fitted baby tee.",
}


def test_suggest_outfit_empty_wardrobe(monkeypatch):
    """Empty wardrobe must not crash, returns a non-empty advice string."""
    monkeypatch.setattr(tools, "_get_groq_client", lambda: _FakeClient())
    result = suggest_outfit(SAMPLE_ITEM, {"items": []})
    assert isinstance(result, str)
    assert result.strip() != ""


def test_suggest_outfit_api_failure_returns_fallback(monkeypatch):
    """If the Groq call raises, return the deterministic non-empty fallback."""
    def _boom():
        raise RuntimeError("network down")
    monkeypatch.setattr(tools, "_get_groq_client", _boom)

    result = suggest_outfit(SAMPLE_ITEM, {"items": []})
    assert isinstance(result, str)
    assert result.strip() != ""
    # Fallback echoes the item's category and colors.
    assert "tops" in result
    assert "white" in result


# --- create_fit_card --------------------------------------------------------

CARD_ITEM = {
    "title": "Y2K Baby Tee — Butterfly Print",
    "price": 18.0,
    "platform": "depop",
}

SAMPLE_OUTFIT = "Pair the baby tee with baggy jeans and chunky white sneakers."


def test_create_fit_card_empty_outfit_returns_error(monkeypatch):
    """Empty/whitespace outfit must not crash or call the LLM."""
    # If the LLM were called, this would blow up — proving we short-circuit.
    def _should_not_be_called():
        raise AssertionError("LLM should not be called for an empty outfit")
    monkeypatch.setattr(tools, "_get_groq_client", _should_not_be_called)

    for bad in ("", "   ", None):
        result = create_fit_card(bad, CARD_ITEM)
        assert isinstance(result, str)
        assert result.strip() != ""
        assert "outfit" in result.lower()


def test_create_fit_card_api_failure_returns_fallback(monkeypatch):
    """If the Groq call raises, return an indicated deterministic caption."""
    def _boom():
        raise RuntimeError("network down")
    monkeypatch.setattr(tools, "_get_groq_client", _boom)

    result = create_fit_card(SAMPLE_OUTFIT, CARD_ITEM)
    assert isinstance(result, str)
    assert result.strip() != ""
    # Fallback caption is built from the item fields.
    assert "Y2K Baby Tee — Butterfly Print" in result
    assert "depop" in result
    assert "$18" in result