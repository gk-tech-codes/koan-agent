"""Cost logger plugin — logs token usage after each turn."""

from koan.plugins.hooks import hook


@hook("on_turn_end")
def log_cost(**kwargs):
    usage = kwargs.get("usage")
    if usage:
        total = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        print(f"\033[90m  ⊙ tokens: {total} (in: {usage.get('input_tokens', 0)}, out: {usage.get('output_tokens', 0)})\033[0m")
