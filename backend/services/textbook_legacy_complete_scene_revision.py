"""Read-only legacy-v2 body adapter. Preparation never modifies the runtime."""
import hashlib
import io
from pathlib import Path

from PIL import Image

from content.textbook_complete_scene_revision import _json
from content.textbook_interaction_policy import freeze_interaction_policy
from content.textbook_legacy_complete_scene_revision import (
    document_references, legacy_metadata, mapped_body, validate_legacy_evidence)
from content.textbook_operator_revision import fail, sha_text


def _read(path, expected=None):
    path = Path(path)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        fail('旧版来源必须是明确的本机原始文件')
    raw = path.read_bytes()
    if expected is not None and hashlib.sha256(raw).hexdigest() != expected:
        fail('旧版来源文件原字节摘要变化：' + path.name)
    return raw


def read_legacy_complete_scene_evidence(parent, root, bundle_path):
    """Return exact documents and verified image bytes for immutable archiving."""
    bundle_raw = _read(bundle_path).decode('utf-8')
    bundle, bundle_sha = _json(bundle_raw), sha_text(bundle_raw)
    documents = {key: _read(ref['path'], ref['fileSha256']).decode('utf-8')
                 for key, ref in document_references(bundle).items()}
    if bundle['newPolicy']['canonicalSha256'] != freeze_interaction_policy()['sha256']:
        fail('准备旧版修订时必须采用当前权威互动规则')
    receipts, files = {}, {}
    for asset in bundle['assetAdditions']:
        raw = _read(asset['sourceFilePath'], asset['sourceFileSha256'])
        suffix = Path(asset['reviewUrl']).suffix
        if suffix not in {'.png', '.jpg', '.jpeg', '.webp'} or Path(asset['sourceFilePath']).suffix != suffix:
            fail('旧版图片格式或扩展名不匹配')
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in {'PNG', 'JPEG', 'WEBP'} or min(image.size) < 1:
                fail('旧版素材必须是可读取的图片')
            image.verify()
        receipts[asset['assetKey']] = _read(asset['sourceReceiptPath'], asset['sourceReceiptFileSha256']).decode('utf-8')
        files['complete-scene-media/' + asset['sourceFileSha256'] + suffix] = raw
    body, media = mapped_body(_json(documents['replacementBody']), bundle['assetAdditions'], bundle_sha)
    authoring, summary = legacy_metadata(parent, bundle, bundle_sha, body)
    evidence = {'sourceBundleJson': bundle_raw, 'documents': documents, 'assetReceipts': receipts,
                'authoring': authoring, 'summary': summary, 'media': media}
    validate_legacy_evidence(parent, evidence)
    return evidence, files
