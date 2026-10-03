"""Cheap, deterministic language choice between English and Polish, shared by the detectors."""

import re

# Language is picked from function words, which every sentence has and names don't. Polish
# letters only break a tie, so "Contact Łukasz Wójcik about the invoice" stays English. The lists are disjoint:
# words like "i", "a", "to", "on" exist in both languages.
WORD = re.compile(r"[^\W\d_]+")
POLISH_LETTERS = re.compile(r"[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]")
POLISH_WORDS = frozenset(
    "w z na się nie jest że do jak co po dla czy mój moja moje mam jestem proszę oraz ale tak ten ta przez od "
    "za są być mi mnie ja ty ona my wy oni jego jej ich już tylko jeszcze bardzo może można który która które "
    "gdzie kiedy dlaczego ze we pod nad przy bez jako żeby mój twój nasz wszystkie wszystko".split()
)
ENGLISH_WORDS = frozenset(
    "the and is are of in for you your my it this that with be what how please can me an at from as was were "
    "will would should could have has had do does did not but or if they them their we our he she his her "
    "about which who when where why all any some there here into".split()
)


def guess_language(text: str) -> str:
    """'pl' or 'en'. Unknown or mixed text defaults to English, the language the patterns were written for."""
    words = WORD.findall(text.lower())
    pl = sum(w in POLISH_WORDS for w in words)
    en = sum(w in ENGLISH_WORDS for w in words)
    if pl != en:
        return "pl" if pl > en else "en"
    return "pl" if pl == 0 and POLISH_LETTERS.search(text) else "en"


SENTENCE_END = re.compile(r"(?<=[.!?\n])\s+")


def sentences(text: str) -> list[str]:
    """Split after sentence punctuation or line breaks, keeping every character so the parts join back."""
    parts, start = [], 0
    for m in SENTENCE_END.finditer(text):
        parts.append(text[start : m.end()])
        start = m.end()
    parts.append(text[start:])
    return parts
