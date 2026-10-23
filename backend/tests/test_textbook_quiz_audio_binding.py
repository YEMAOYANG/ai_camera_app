"""Exact quiz narration binding, without provider calls or database state."""
from copy import deepcopy
import hashlib
import unittest

from core.errors import ApiError
from services.textbook_preview_audio import bind_question_audio


def classroom():
    return {"scenes": [{"id": "scene", "type": "quiz", "actions": [
        {"id": "stem", "type": "speech", "text": "Who is speaking?",
         "audioId": "saved-stem", "audioUrl": "http://localhost/api/classroom-media/book/audio/stem.wav"},
        {"id": "feedback-a", "type": "speech", "text": "This friend is listening. Try again.",
         "audioId": "saved-a", "audioUrl": "/api/classroom-media/book/audio/a.wav"},
        {"id": "feedback-b", "type": "speech", "text": "This friend is speaking.",
         "audioId": "saved-b", "audioUrl": "/api/classroom-media/book/audio/b.wav"},
    ], "content": {"questions": [{"id": "q", "question": "Who is speaking?", "optionFeedback": {
        "A": {"text": "This friend is listening. Try again."},
        "B": {"text": "This friend is speaking."},
    }}]}}]}


class QuizAudioBindingTests(unittest.TestCase):
    def test_binds_exact_stem_and_selected_feedback_with_traceable_identity(self):
        room = classroom()
        bind_question_audio(room)
        question = room["scenes"][0]["content"]["questions"][0]
        self.assertEqual(question["questionAudioUrl"], "/api/classroom-media/book/audio/stem.wav")
        self.assertEqual(question["questionAudioBinding"]["actionId"], "stem")
        for value in ("A", "B"):
            feedback = question["optionFeedback"][value]
            self.assertEqual(feedback["audioBinding"]["questionId"], "q")
            self.assertEqual(feedback["audioBinding"]["optionValue"], value)
            self.assertEqual(feedback["audioBinding"]["ttsRequestId"], "saved-" + value.lower())
            self.assertEqual(feedback["audioBinding"]["sourceTextSha256"],
                             hashlib.sha256(feedback["text"].encode()).hexdigest())
        before = deepcopy(room)
        bind_question_audio(room)
        self.assertEqual(room, before)

    def test_pending_or_nonverbatim_speech_never_binds_by_similarity(self):
        room = classroom()
        room["scenes"][0]["actions"][1]["text"] += " "
        del room["scenes"][0]["actions"][2]["audioUrl"]
        bind_question_audio(room)
        for feedback in room["scenes"][0]["content"]["questions"][0]["optionFeedback"].values():
            self.assertNotIn("audioUrl", feedback)

    def test_duplicate_or_premature_feedback_is_rejected(self):
        for mutation in ("duplicate", "early", "shared-feedback"):
            room = classroom()
            actions = room["scenes"][0]["actions"]
            if mutation == "duplicate":
                actions.append({**actions[1], "id": "duplicate"})
            elif mutation == "early":
                actions.insert(0, actions.pop(1))
            else:
                feedback = room["scenes"][0]["content"]["questions"][0]["optionFeedback"]
                feedback["B"]["text"] = feedback["A"]["text"]
            with self.subTest(mutation=mutation), self.assertRaises(ApiError):
                bind_question_audio(room)

    def test_stale_existing_feedback_audio_or_receipt_fails_closed(self):
        for field, value in (("audioUrl", "/api/classroom-media/book/audio/old.wav"),
                             ("audioBinding", {"ttsRequestId": "wrong"})):
            room = classroom()
            room["scenes"][0]["content"]["questions"][0]["optionFeedback"]["A"][field] = value
            with self.subTest(field=field), self.assertRaises(ApiError):
                bind_question_audio(room)


if __name__ == "__main__":
    unittest.main()
