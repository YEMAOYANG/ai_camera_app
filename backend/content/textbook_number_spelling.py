"""Exact equivalence for Mandarin page numbers, never fuzzy pronunciation approval."""
import hashlib
import re
import unicodedata

from content.textbook_catalog import digest


SCHEMA = 'mira.textbook.asr-page-number-equivalence.v1'


def _number(value):
    n = int(value)
    digits = '零一二三四五六七八九'
    if n < 10:
        return digits[n]
    if n < 100:
        return (digits[n//10] if n >= 20 else '') + '十' + (digits[n%10] if n%10 else '')
    rest = n % 100
    return digits[n//100] + '百' + ('零'+digits[rest] if 0 < rest < 10 else
        digits[rest//10]+'十'+(digits[rest%10] if rest%10 else '') if rest else '')


def _plain(value):
    return ''.join(c.lower() for c in unicodedata.normalize('NFKC', value) if c.isalnum())


def page_number_equivalence(expected, receipt):
    """Return proof only if the entire utterance matches after bounded conversion."""
    if (not isinstance(expected, str) or not isinstance(receipt, dict)
            or receipt.get('status') != 'succeeded' or receipt.get('completionUsable') is not True
            or not isinstance(receipt.get('transcript'), str)):
        return None
    transcript = receipt['transcript']
    if receipt.get('transcriptSha256') != hashlib.sha256(transcript.encode()).hexdigest():
        return None
    # Restrict this exception to positive page numbers, not decimals, signs,
    # telephone numbers, arithmetic, dates, units or arbitrary homophones.
    pattern = r'(页码)([1-9][0-9]{0,2})(?=[页，。！？；、\s,;!?]|$)|(第)([1-9][0-9]{0,2})(页)'
    normalized, count = re.subn(pattern, lambda m: (m[1] + _number(m[2])) if m[1]
                               else m[3] + _number(m[4]) + m[5], expected)
    if not count or _plain(normalized) != _plain(transcript):
        return None
    return {'schemaVersion': SCHEMA, 'expectedTextSha256': hashlib.sha256(expected.encode()).hexdigest(),
            'normalizedTextSha256': hashlib.sha256(_plain(normalized).encode()).hexdigest(),
            'asrReceipt': receipt, 'asrReceiptSha256': digest(receipt), 'pageNumberOccurrences': count}


def validate_page_number_equivalence(expected, proof):
    if not isinstance(proof, dict) or page_number_equivalence(expected, proof.get('asrReceipt')) != proof:
        raise ValueError('page_number_equivalence_evidence_changed')
    return proof['asrReceipt']
