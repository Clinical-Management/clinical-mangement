"""Cheap language guess for replies that must not wait for the AI (e.g. red-flag escalation)."""

import re

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
# Common words / letters that distinguish Marathi from Hindi (both use Devanagari)
_MARATHI = re.compile(r"ळ|आहे|नाही|मला|माझ्या|माझा|माझी|तुम्ही|होत|आहेत|खूप|कसे|झाले|झाला|दुखत")
_HINDI = re.compile(r"है|हैं|मुझे|मेरे|मेरा|मेरी|नहीं|हो रहा|हो रही|बहुत|आप|क्या")


def guess_language(text: str, fallback: str) -> str:
    if not _DEVANAGARI.search(text):
        return fallback
    return "mr" if len(_MARATHI.findall(text)) > len(_HINDI.findall(text)) else "hi"
