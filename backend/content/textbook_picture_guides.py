"""Read-only, versioned media overlays for exact immutable introductions.

This module never produces media. The operator installs a complete checked pack;
the existing authenticated textbook endpoint only selects shared artifacts.
"""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import re

from content.textbook_catalog import digest, fields, identifier, invalid, text

PACK_PATH = Path(__file__).parent / "textbooks/intro-media-v1/published.json"
HASH = re.compile(r"[0-9a-f]{64}\Z")
IMAGE = re.compile(r"/textbooks/picture-guide-v1/[a-z]+-[0-9a-f]{16}\.png\Z")
AUDIO = re.compile(r"/textbooks/picture-guide-v1/([0-9a-f]{64})\.mp3\Z")


def validate_pack(pack):
    fields(pack, ("schemaVersion", "editionId", "revisionId", "gradeCode", "planSha256", "guides"))
    if (pack["schemaVersion"] != "mira.textbook.picture-guide-pack.v1" or pack["gradeCode"] != "primary_1"
            or any(not identifier(pack[k]) for k in ("editionId", "revisionId"))
            or not isinstance(pack["guides"], dict) or not pack["guides"]
            or not HASH.fullmatch(str(pack["planSha256"]))):
        invalid("图画导学素材包标识无效")
    for key, value in pack["guides"].items():
        fields(value, ("schemaVersion", "gradeCode", "sourceContentSha256", "title", "scenes", "choices", "presentationSha256"))
        if (not identifier(key) or value["schemaVersion"] != "mira.textbook.picture-guide.v1"
                or value["gradeCode"] != pack["gradeCode"] or not HASH.fullmatch(str(value["sourceContentSha256"]))
                or value["presentationSha256"] != digest({k: v for k, v in value.items() if k != "presentationSha256"})):
            invalid("图画导学版本校验失败")
        text(value["title"], 20)
        if not isinstance(value["scenes"], list) or len(value["scenes"]) != 4 or not isinstance(value["choices"], list) or len(value["choices"]) != 3:
            invalid("图画导学环节不完整")
        for segment in value["scenes"] + value["choices"]:
            fields(segment, ("caption", "narration", "art", "audio"))
            text(segment["caption"], 16)
            text(segment["narration"], 200)
            art, audio = segment["art"], segment["audio"]
            fields(art, ("src", "panel", "alt", "sha256"))
            fields(audio, ("src", "sha256", "durationSeconds"))
            text(art["alt"], 80)
            match = AUDIO.fullmatch(str(audio["src"]))
            if (not IMAGE.fullmatch(str(art["src"])) or not HASH.fullmatch(str(art["sha256"]))
                    or not art["src"].endswith(art["sha256"][:16] + ".png")
                    or type(art["panel"]) is not int or not 0 <= art["panel"] <= 3
                    or not match or match[1] != audio["sha256"]
                    or type(audio["durationSeconds"]) not in (int, float) or not 1 < audio["durationSeconds"] < 120):
                invalid("图画导学素材路径或完整性无效")
    return pack


@lru_cache(maxsize=1)
def published_pack():
    return validate_pack(json.loads(PACK_PATH.read_text())) if PACK_PATH.exists() else None


def picture_guide(value, *, edition_id, revision_id, grade_code):
    pack = published_pack()
    if not pack or (edition_id, revision_id, grade_code) != (pack["editionId"], pack["revisionId"], pack["gradeCode"]):
        return None
    guide = pack["guides"].get(value["introductionId"])
    return deepcopy(guide) if guide and guide["sourceContentSha256"] == digest(value) else None
