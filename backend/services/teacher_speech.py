"""Deterministic Chinese ordinal pronunciation for teacher TTS inputs.

Only explicit ordinals change. Written lesson content and the learner's answer
stay untouched; ordinary quantities and mathematical expressions are not read
as ordinals. Normalization never silently truncates a teacher's sentence.
"""
from __future__ import annotations

import re

SPEECH_POLICY_VERSION = 'mira.teacher-speech-ordinals.v1'
MAX_SPEECH_CHARACTERS = 4000
_FULLWIDTH_DIGITS = str.maketrans('０１２３４５６７８９', '0123456789')
_INTEGER_ORDINAL = re.compile(
    r'第\s*([0-9０-９]{1,4})'
    r'(?![0-9０-９]|\s*[.．,，/／+＋\-－−×÷*＊=＝]\s*[0-9０-９])'
)
_TWO_ORDINAL = re.compile(r'第\s*[两兩]')
_DIGITS = '零一二三四五六七八九'


def _chinese_integer(number: int) -> str:
    parts: list[str] = []
    pending_zero = False
    for divisor, unit in ((1000, '千'), (100, '百'), (10, '十'), (1, '')):
        digit, number = divmod(number, divisor)
        if not digit:
            if parts and number:
                pending_zero = True
            continue
        if pending_zero:
            parts.append('零')
            pending_zero = False
        # Ten through nineteen start with 十, while 110 contains 一十.
        if not (divisor == 10 and digit == 1 and not parts):
            parts.append(_DIGITS[digit])
        parts.append(unit)
    return ''.join(parts)


def normalize_teacher_speech(text: str, *, maximum_characters: int = MAX_SPEECH_CHARACTERS) -> str:
    """Say 第2/第２/第两 as 第二, without turning quantities into ordinals.

    Supports explicit Arabic integer ordinals 1..9999. Decimal, fraction,
    compound mathematical and larger numeric identifiers remain verbatim.
    The caller can apply a smaller bound matching its TTS segment limit.
    """
    if not isinstance(text, str):
        raise TypeError('teacher speech must be text')
    if type(maximum_characters) is not int or not 1 <= maximum_characters <= MAX_SPEECH_CHARACTERS:
        raise ValueError('invalid teacher speech character limit')
    if len(text) > maximum_characters:
        raise ValueError('teacher speech exceeds character limit')

    def replace(match: re.Match[str]) -> str:
        number = int(match[1].translate(_FULLWIDTH_DIGITS))
        return '第' + _chinese_integer(number) if 1 <= number <= 9999 else match[0]

    normalized = _TWO_ORDINAL.sub('第二', _INTEGER_ORDINAL.sub(replace, text))
    if len(normalized) > maximum_characters:
        raise ValueError('normalized teacher speech exceeds character limit')
    return normalized
