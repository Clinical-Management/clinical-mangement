"""Deterministic safety nets around the AI interviewer.

The model is instructed to flag red-flag symptoms and never give medical advice;
these rules make sure that holds even if the model misses something.
NOTE: the Hindi/Marathi phrase lists should be reviewed by native-speaking clinicians.
"""

import re

RED_FLAGS: dict[str, dict] = {
    "chest_pain": {
        "label": "Severe chest pain",
        "phrases": [
            "chest pain", "pain in my chest", "pain in chest", "chest tightness", "tightness in my chest",
            "crushing chest", "pressure in my chest",
            "सीने में दर्द", "छाती में दर्द", "seene mein dard", "seene me dard", "chhati mein dard",
            "छातीत दुख", "छातीत वेदना", "chhatit dukh",
        ],
    },
    "breathing_difficulty": {
        "label": "Breathing difficulty",
        "phrases": [
            "can't breathe", "cannot breathe", "can not breathe", "difficulty breathing", "trouble breathing",
            "shortness of breath", "short of breath", "breathless", "gasping",
            "सांस लेने में तकलीफ", "साँस लेने में तकलीफ", "सांस नहीं ले पा", "साँस फूल", "सांस फूल",
            "saans lene mein takleef", "saans phool",
            "श्वास घेण्यास त्रास", "श्वास घेता येत नाही", "दम लागत", "धाप लाग", "dam lagto",
        ],
    },
    "stroke_signs": {
        "label": "Possible stroke signs",
        "phrases": [
            "face drooping", "face is drooping", "slurred speech", "can't speak properly", "weakness on one side",
            "one side of my body", "can't move my arm", "can't move my leg", "sudden numbness",
            "चेहरा टेढ़ा", "बोलने में दिक्कत", "लकवा", "एक तरफ कमजोरी", "एक तरफ सुन्न",
            "चेहरा वाकडा", "बोलताना अडखळ", "अर्धांगवायू", "एका बाजूला अशक्तपणा",
        ],
    },
    "heavy_bleeding": {
        "label": "Heavy bleeding",
        "phrases": [
            "heavy bleeding", "bleeding heavily", "bleeding a lot", "won't stop bleeding", "bleeding won't stop",
            "vomiting blood", "coughing up blood", "blood in vomit",
            "बहुत खून", "ज्यादा खून", "ज़्यादा खून", "खून की उल्टी", "खून बंद नहीं",
            "खूप रक्तस्राव", "रक्ताची उलटी", "रक्त थांबत नाही", "खूप रक्त",
        ],
    },
    "loss_of_consciousness": {
        "label": "Fainting / seizure",
        "phrases": [
            "fainted", "passed out", "unconscious", "seizure", "convulsion", "fits",
            "बेहोश", "दौरा पड़", "मिर्गी", "बेशुद्ध", "झटके", "फिट आली",
        ],
    },
    "self_harm": {
        "label": "Thoughts of self-harm",
        "phrases": [
            "kill myself", "suicide", "end my life", "want to die",
            "आत्महत्या", "मरना चाहता", "मरना चाहती", "जीव द्यावासा", "मरावेसे वाटते",
        ],
    },
}

RED_FLAG_CODES = tuple(RED_FLAGS)

# Negations near a phrase ("no chest pain", "सीने में दर्द नहीं है") suppress a rule match
_NEGATIONS = re.compile(r"\b(no|not|never|without|don't|dont|didn't|nahi|nahin)\b|नहीं|नही|नाही|नको", re.IGNORECASE)


def _phrase_pattern(phrase: str) -> re.Pattern:
    # Word boundaries for Latin-script phrases so "fits" doesn't match "benefits"
    escaped = re.escape(phrase)
    return re.compile(rf"\b{escaped}\b" if phrase.isascii() else escaped, re.IGNORECASE)


_RULES = [(code, [_phrase_pattern(p) for p in rule["phrases"]]) for code, rule in RED_FLAGS.items()]


def detect_red_flags(text: str) -> list[dict]:
    found = []
    for code, patterns in _RULES:
        for pattern in patterns:
            match = pattern.search(text)
            if not match:
                continue
            start, end = match.span()
            if _NEGATIONS.search(text[max(0, start - 15) : end + 15]):
                continue
            found.append({"code": code, "evidence": text[max(0, start - 30) : end + 30].strip()})
            break
    return found


# Replies that give medicine/dose advice or name a diagnosis are never shown to the patient
_ADVICE_PATTERNS = [
    re.compile(r"\b\d+(\.\d+)?\s?(mg|mcg|ml|gm)\b", re.IGNORECASE),
    re.compile(
        r"\b(take|use|start|try)\s+(a |an |the |some |your )?"
        r"(tablet|tablets|pill|pills|medicine|medication|capsule|syrup|paracetamol|ibuprofen|antibiotic|crocin|dolo|painkiller)",
        re.IGNORECASE,
    ),
    re.compile(r"\byou (probably |likely |may |might |could )?(have|be suffering from) (a |an )?\w+ (infection|disease|syndrome|disorder|attack)\b", re.IGNORECASE),
    re.compile(r"\bdiagnos(is|ed|e)\b", re.IGNORECASE),
    re.compile(r"(दवा|दवाई|गोली)\s*(लें|लीजिए|लीजिये|खाएं|खाइए)"),
    re.compile(r"(औषध|गोळी|गोळ्या)\s*(घ्या|घ्यावी|घ्यावे)"),
]


def gives_medical_advice(reply: str) -> bool:
    return any(p.search(reply) for p in _ADVICE_PATTERNS)
