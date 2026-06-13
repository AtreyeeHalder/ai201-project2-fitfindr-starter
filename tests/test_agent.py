r"""tests/test_agent.py — confirm state flows through a COMPLETE interaction.
Run the tests with this code:
$env:PYTHONIOENCODING="utf-8"; .\.venv\Scripts\python.exe -m pytest tests/test_agent.py -v -s
"""
import agent
from utils.data_loader import get_example_wardrobe

QUERY = ("I'm looking for a vintage graphic tee under $30. "
         "I mostly wear baggy jeans and chunky sneakers. "
         "What's out there and how would I style it?")


def test_state_flows_through_complete_interaction(monkeypatch, capsys):
    captured = {}
    real_suggest = agent.suggest_outfit
    real_create = agent.create_fit_card

    # Spies RECORD the args, then CALL THROUGH to the real tools (real LLM call),
    # so this is a genuine complete interaction — not a stub.
    def spy_suggest(new_item, wardrobe):
        captured["item_into_suggest"] = new_item
        return real_suggest(new_item, wardrobe)

    def spy_create(outfit, new_item):
        captured["outfit_into_create"] = outfit
        return real_create(outfit, new_item)

    monkeypatch.setattr(agent, "suggest_outfit", spy_suggest)
    monkeypatch.setattr(agent, "create_fit_card", spy_create)

    session = agent.run_agent(QUERY, get_example_wardrobe())

    # Print, as the instructions ask (run pytest with -s to see this).
    print("\nselected_item:", session["selected_item"])
    print("\noutfit_suggestion:", session["outfit_suggestion"])

    # selected_item is the EXACT dict passed into suggest_outfit.
    assert captured["item_into_suggest"] is session["selected_item"]
    # outfit_suggestion is the EXACT string passed into create_fit_card.
    assert captured["outfit_into_create"] is session["outfit_suggestion"]
    # And the real tool output actually landed on the session.
    assert session["fit_card"] is not None
