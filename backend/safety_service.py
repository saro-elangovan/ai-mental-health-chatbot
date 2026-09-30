"""Rule-based safety layer.

Runs BEFORE any AI call. If a message signals possible crisis, a fixed, reviewed
response is returned and the AI model is never asked to reply. This is:
  - fast and free (no API call),
  - predictable (the model cannot improvise on a sensitive topic),
  - testable (see tests/test_safety.py).

Keyword rules can miss unusual wording and can over-trigger. They are a first safety
net, not a clinical tool. Over-triggering is preferred to missing a real crisis.
"""

import re
from dataclasses import dataclass

CRISIS_RESPONSE = (
    "I'm really sorry you're feeling this way, and I'm glad you said something. "
    "What you're going through matters, and you don't have to face it alone.\n\n"
    "I'm an AI chatbot, not an emergency service or a mental-health professional, "
    "so I can't give you the help you may need right now.\n\n"
    "If you might act on these thoughts, or you or someone else is in immediate danger, "
    "please contact your local emergency number right now (for example 112, 911, or 999) "
    "or go to the nearest emergency room.\n\n"
    "Please also reach out to someone you trust, such as a friend, family member, or "
    "teacher, and try not to be alone right now. You can also contact a crisis line:\n"
    "- India: Tele-MANAS 14416\n"
    "- USA: call or text 988\n"
    "- UK and Ireland: Samaritans 116 123\n"
    "- Other countries: findahelpline.com lists free helplines worldwide\n\n"
    "Numbers can change, so please check the one for your area. "
    "If you'd like, I'm still here to talk about how you're feeling."
)

_CRISIS_PATTERNS = [
    r"\bkill\s+(my\s?self|myself)\b",
    r"\b(end|take)\s+my\s+(own\s+)?life\b",
    r"\bsuicid(e|al)\b",
    r"\b(want|wanted|wanna|going)\s+to\s+die\b",
    r"\bwanna\s+die\b",
    r"\b(don't|dont|do\s+not)\s+want\s+to\s+(live|be\s+alive|exist|wake\s+up)\b",
    r"\bbetter\s+off\s+(dead|without\s+me)\b",
    r"\bno\s+(reason|point)\s+(to|in)\s+(live|living|go\s+on|going\s+on)\b",
    r"\bnot\s+worth\s+living\b",
    r"\bwish\s+i\s+(was|were)\s+(dead|never\s+born)\b",
    r"\bend\s+it\s+all\b",
    r"\bcan't\s+go\s+on\b",
    r"\bself[\s-]?harm",
    r"\b(hurt|harm|cut|injur\w*|hurting|harming|cutting)\s+(my\s?self|myself)\b",
    r"\boverdos(e|ing)\s+(on\s+)?(myself|pills|my)\b",
    r"\b(want|going|plan(ning)?)\s+to\s+(kill|hurt|harm)\s+(someone|somebody|them|him|her|people|others)\b",
]

_MEDICAL_PATTERNS = [
    r"\bdo\s+i\s+have\s+(depression|anxiety|bipolar|adhd|ptsd|ocd|schizophrenia|a\s+disorder)\b",
    r"\bam\s+i\s+(depressed|bipolar|schizophrenic|mentally\s+ill)\b",
    r"\bdiagnos(e|is)\b",
    r"\b(prescribe|prescription|dosage|dose)\b",
    r"\b\d+\s?mg\b",
    r"\b(stop|quit|skip|increase|decrease|reduce|change|double)\w*\s+(taking\s+)?(my\s+)?(meds|medication|medicine|pills|antidepressants?)\b",
    r"\b(sertraline|fluoxetine|prozac|zoloft|xanax|alprazolam|diazepam|valium|lexapro|escitalopram|lithium|klonopin)\b",
]

_crisis_re = re.compile("|".join(_CRISIS_PATTERNS), re.IGNORECASE)
_medical_re = re.compile("|".join(_MEDICAL_PATTERNS), re.IGNORECASE)


@dataclass(frozen=True)
class SafetyResult:
    is_crisis: bool
    needs_medical_boundary: bool


def _normalize(text: str) -> str:
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    return re.sub(r"\s+", " ", text).strip()


def check_message(text: str) -> SafetyResult:
    """Classify a user message. Pure function: no I/O, no logging of content."""
    clean = _normalize(text)
    return SafetyResult(
        is_crisis=bool(_crisis_re.search(clean)),
        needs_medical_boundary=bool(_medical_re.search(clean)),
    )
