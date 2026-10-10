"""Versioned provider-language policy; teacher identities remain unchanged."""
import json
from pathlib import Path

from content.textbook_catalog import digest

ENGLISH_AUTO_LANGUAGE_OPTION = "english-auto-v1"
ENGLISH_AUTO_LANGUAGE_POLICY = json.loads((Path(__file__).with_name(
    "textbook_audio_language_policy.v1.json")).read_text(encoding="utf-8"))
ENGLISH_AUTO_LANGUAGE_POLICY_SHA256 = digest(ENGLISH_AUTO_LANGUAGE_POLICY)
