"""Mirrors lib/action/engine.ts and lib/interactive/logical-viewport.ts of OpenMAIC."""

SET_WIDGET_STATE = "SET_WIDGET_STATE"
HIGHLIGHT_ELEMENT = "HIGHLIGHT_ELEMENT"
ANNOTATE_ELEMENT = "ANNOTATE_ELEMENT"
REVEAL_ELEMENT = "REVEAL_ELEMENT"

WIDGET_ACTION_TO_MESSAGE = {
    "widget_setState": SET_WIDGET_STATE,
    "widget_highlight": HIGHLIGHT_ELEMENT,
    "widget_annotation": ANNOTATE_ELEMENT,
    "widget_reveal": REVEAL_ELEMENT,
}

WIDGET_ACTION_TYPES = frozenset(WIDGET_ACTION_TO_MESSAGE)

INTERACTIVE_WIDTH = 1280
INTERACTIVE_HEIGHT = 720
SLIDE_WIDTH = 1000
SLIDE_HEIGHT = 562.5


def widget_message(action):
    """Build the host message for one teacher widget action."""
    action_type = action.get("type")
    try:
        message_type = WIDGET_ACTION_TO_MESSAGE[action_type]
    except KeyError:
        raise ValueError(f"Unknown widget action type: {action_type!r}") from None

    message = {"type": message_type}
    if action_type == "widget_setState":
        message["state"] = action.get("state")
    elif action_type == "widget_highlight":
        message["target"] = action.get("target")
    elif action_type == "widget_annotation":
        message["target"] = action.get("target")
        message["content"] = action.get("content")
    else:
        message["target"] = action.get("target")
    return message
