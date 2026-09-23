"""Derive learner controls from the immutable, reviewed classroom document."""
from __future__ import annotations

from collections import OrderedDict
from html.parser import HTMLParser
import hashlib
import json
import re
from threading import RLock

_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,98}$")
_VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())
_CACHE: OrderedDict[tuple[str, str], dict[int, list[dict[str, str]]]] = OrderedDict()
_LOCK = RLock()


class _Controls(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.nodes = []
        self.stack = []

    def handle_starttag(self, tag, attrs):
        node = {"tag": tag, "attrs": dict(attrs), "parent": self.stack[-1] if self.stack else None}
        self.nodes.append(node)
        if tag not in _VOID:
            self.stack.append(len(self.nodes) - 1)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.stack.pop()

    def handle_endtag(self, tag):
        for pos in range(len(self.stack) - 1, -1, -1):
            if self.nodes[self.stack[pos]]["tag"] == tag:
                del self.stack[pos:]
                break


def controls_for_objective(html: str, objective: dict) -> list[dict[str, str]]:
    """Accept reviewed alternatives in the same button group, never reset/navigation.

    The browser must additionally observe this objective's separate feedback
    changing after a trusted gesture. This grants participation, never a score.
    """
    original = objective["operation"]
    controls = [{"controlSelector": original["controlSelector"], "action": original["action"]}]
    parsed = _Controls()
    parsed.feed(html)
    ids = {}
    duplicates = set()
    for node in parsed.nodes:
        name = node["attrs"].get("id")
        if name in ids:
            duplicates.add(name)
        ids[name] = node
    for name in duplicates:
        ids.pop(name, None)
    exploration = objective.get("exploration") or {}
    reset = (exploration.get("reset") or {}).get("selector")
    for state in exploration.get("states", []):
        for operation in state.get("operations", []):
            selector = operation.get("selector", "")
            if selector.startswith("#") and selector[1:] in ids and selector != reset:
                controls.append({"controlSelector": selector, "action": operation["action"]})
    # Each reviewed state can use a separate choice group. Expand only the
    # direct siblings of those anchors, never their ancestors or all buttons.
    for anchor in list(controls):
        selected = ids.get(anchor["controlSelector"][1:])
        if selected and selected["tag"] == "button" and selected["parent"] is not None:
            parent = parsed.nodes[selected["parent"]]
            if parent["tag"] not in {"html", "body"}:
                for name, node in ids.items():
                    attrs = node["attrs"]
                    if (isinstance(name, str) and _ID.fullmatch(name) and node["tag"] == "button"
                        and node["parent"] == selected["parent"] and "disabled" not in attrs
                        and str(attrs.get("type") or "button").lower() not in {"reset", "submit"}
                        and "#" + name != reset):
                        controls.append({"controlSelector": "#" + name, "action": "click"})
    return [dict(item) for item in dict.fromkeys(tuple(row.items()) for row in controls)]


def reviewed_controls(*, classroom_id: str, content_sha256: str, objectives: list[dict], reader):
    key = (classroom_id, content_sha256)
    with _LOCK:
        cached = _CACHE.get(key)
        if cached is not None:
            _CACHE.move_to_end(key)
            return cached
    classroom = reader(classroom_id)
    content = {"stage": classroom.get("stage"), "scenes": classroom.get("scenes")}
    actual = hashlib.sha256(json.dumps(content, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()).hexdigest()
    if actual != content_sha256 or classroom.get("stage", {}).get("id") != classroom_id:
        raise ValueError("participation classroom differs from published content")
    scenes = {scene["id"]: scene for scene in classroom["scenes"]}
    result = {}
    for objective in objectives:
        scene = scenes[objective["operation"]["sceneId"]]
        if scene["type"] != "interactive" or scene["content"]["type"] != "interactive":
            raise ValueError("participation scene is not interactive")
        result[objective["objectiveIndex"]] = controls_for_objective(scene["content"].get("html", ""), objective)
    with _LOCK:
        _CACHE[key] = result
        while len(_CACHE) > 128:
            _CACHE.popitem(last=False)
    return result
