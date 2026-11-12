"""Build-time loader for the courseware game's reusable mechanics.

``catalog.json`` lists the accepted version entry points and example paths;
select from owner-approved versions for new lessons. ``arcade`` is a shared
runtime for custom mechanics, not an independently selectable game.

A page still calls the normal engine, for example::

    K.ready({title: '…', sub: '…', img: '__IMG:cover__'});
    K.game(K.gameTemplates.crane({levels: [
      {name: '…', rounds: [
        {goal: '…', hint: '…', hint2: '…', cars: [1, 2, 3], cargo: {count: 1}, drop: [1]}
      ]},
      {name: '…', rounds: [/* a harder round */]}
    ]}));

Place `#game-goal`, `#game-player` and `#game-target` in the source HTML for
teacher highlights. The template follows the game objects with those anchors.
Each mechanic describes its round fields at the top of its script. All indices
are zero-based. The page still supplies registered pictures and owns its
teacher script, progression, and screenshot acceptance.

The arcade examples live under ``kit/examples/classic-arcade``. Levels own
their data: the two pairing mechanics accept a numeric ``total``, ordered
``pairs`` of semantic IDs, or a ``matches(a, b)`` predicate. ``art.icons`` maps
IDs to registered pictures, and ``cues`` maps level events to recorded cue IDs.
The mechanics themselves do not pick textbook objectives, pictures, or voices.
"""

from pathlib import Path
import re

_MECHANICS = (
    "runner", "lily", "ring", "crane", "parachute", "trace",
    "bumper", "slingshot", "fishing", "slice",
)
_CLASSIC = (
    "fallingTiles", "bubbleMaze", "platformHop", "shadowStage", "tideGates", "windCourier",
    "magnetMarbles", "fireflySwing", "shutterScout", "sortingDepot", "slideMerge", "listenDelivery", "compareSnake",
    "orchardCatch", "shapeBridge", "wordBubbles",
)
_ARCADE = 'arcade'
_CALL = re.compile(r"\bK\.gameTemplates\.([A-Za-z][A-Za-z0-9]*)\s*\(")


def javascript(page_script):
    """Inline the common code and only the mechanics named in the page script."""
    names = set(_CALL.findall(page_script))
    if not names:
        return ""
    unknown = names.difference((*_MECHANICS, *_CLASSIC, _ARCADE))
    if unknown:
        raise ValueError(f"Unknown courseware game template: {', '.join(sorted(unknown))}")
    folder = Path(__file__).parent
    files = (["core", *sorted(names.intersection(_MECHANICS))] if names.intersection(_MECHANICS) else [])
    if _ARCADE in names or names.intersection(_CLASSIC):
        files += ["classic", *sorted(names.intersection(_CLASSIC))]
    return "\n".join((folder / f"{name}.js").read_text(encoding="utf-8") for name in files)


def stylesheet(page_script):
    names = set(_CALL.findall(page_script))
    if _ARCADE in names or names.intersection(_CLASSIC):
        return (Path(__file__).parent / "classic.css").read_text(encoding="utf-8")
    return ""
