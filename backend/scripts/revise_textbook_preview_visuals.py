"""Apply an exact visual patch to a narrated, unpublished local preview.

V1 JSON: schemaVersion=mira.textbook.preview-visual-patch.v1,
expectedSourceSha256, reviewer, basis, changes=[{sceneId,beforeHtmlSha256,html}].
V2 uses mira.textbook.preview-visual-patch.v2 and also accepts slide changes
{sceneId,beforeCanvasSha256,canvas}. Canvas hashes use textbook_catalog.digest
(canonical JSON SHA256). Only content.canvas changes; actions remain untouched.
Images must be already-used, SHA-verified frozen assets, or canonical base64
data:image/svg+xml of exact safe inline SVG bytes from the original lesson HTML.
V3 additionally permits an existing quiz visual to use an already frozen image.
V4 quantity diagrams bind derivedImages to the frozen source and replaced PNG
hashes, sourceSize, count, originalLayout, layout, and rgb-thumbnail-repeat-png.v1.
Each layout has cropBox (left,top,right,bottom), thumbnailSize, canvasSize,
positions and centerWithinThumbnail. The old frozen PNG bytes are verified,
then reproduced to exactly equal complete RGB pixels; the new PNG has its own
deterministic byte hash. Count is shared. Changes use sceneId, questionId, beforeQuestionSha256,
visualImageId and optionImageIds. Only existing image src values are replaced.
V5 changes only an existing quiz option image's alt. Each change contains
sceneId, questionId, optionValue, beforeQuestionSha256, beforeVisualSha256,
beforeAlt, src, imageSha256 and alt. The original image bytes, src, question,
answers and all other fields stay fixed; the new alt is plain text.
Question binding repair uses mira.textbook.preview-question-binding-patch.v1
with sceneId, questionId, actionId and beforeQuestionSha256. It derives only
questionAudioBinding from an existing unique verbatim speech, provided the
question already points to that speech's verified formal audio. No new clip,
question wording, answer or caller-supplied binding is accepted.
Original frozen input, questions, answers, narration plan and receipts are kept.
No generation, TTS, ASR, publication, migrations or database reset.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.config import AppConfig
from core.database import Database
from core.errors import ApiError
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient, OpenMaicFullRuntimeError
from repositories.textbook_repository import TextbookRepository
from services.textbook_preview_service import TextbookPreviewService
from services.textbook_preview_visual_revision import revise_preview_visuals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--key', required=True)
    parser.add_argument('--classroom-directory', type=Path, required=True)
    parser.add_argument('--patch', type=Path, required=True, help='Reviewed visual or exact question-binding patch JSON')
    args = parser.parse_args()
    config = AppConfig.from_env()
    service = TextbookPreviewService(TextbookRepository(Database(config.DATABASE_URL)),
        OpenMaicFullRuntimeClient(config.OPENMAIC_FULL_RUNTIME_INTERNAL_URL,
                                 formal_audio_internal_token=config.INTERNAL_API_TOKEN))
    try:
        result = revise_preview_visuals(service, args.key, args.classroom_directory,
                                       json.loads(args.patch.read_text()))
    except (ApiError, OpenMaicFullRuntimeError) as exc:
        print(json.dumps({'error': exc.code, 'message': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
