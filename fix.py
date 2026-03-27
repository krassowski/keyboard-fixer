#!/usr/bin/env python3
"""Intelligently restores a missing letter in text.

Uses aspell's suggestion engine (available on Ubuntu by default).
For each unknown word, fetches aspell's suggestions and picks any
that can be explained by a missing character insertion.

Usage:
    echo "thi i a tet entence" | python3 fix.py
    python3 fix.py "thi i a tet entence"
    python3 fix.py --broken-letter m "otor oil"
    python3 fix.py   # interactive mode
"""

import argparse
import re
import subprocess
import sys


DEFAULT_BROKEN_LETTER = "s"
MAX_MULTI_INSERTIONS = 4
SPECIAL_CASES_S = {}

# Extra vocabulary for developer-oriented text that aspell may not recognize.
DOMAIN_WORDS = {
    "does",
    "just",
    "const",
    "side",
    "these",
    "starting",
    "statusbar",
    "tsconfig",
    "stylesheet",
    "swaps",
}

PRONOUNS = {
    "i", "you", "he", "she", "it", "we", "they",
    "I", "You", "He", "She", "It", "We", "They",
}

PLURALITY_INDICATORS = {
    # number words > 1
    "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen", "twenty", "thirty", "forty",
    "fifty", "sixty", "seventy", "eighty", "ninety", "hundred", "thousand",
    "million", "billion",
    # quantifiers
    "many", "few", "several", "multiple", "various", "numerous",
    "both", "all", "these", "those", "other", "certain", "some",
}

AS_TRIGGER_VERBS = {
    "judge", "judges", "judged", "judging",
    "consider", "considers", "considered", "considering",
    "treat", "treats", "treated", "treating",
    "view", "views", "viewed", "viewing",
    "regard", "regards", "regarded", "regarding",
    "classify", "classifies", "classified", "classifying",
    "rate", "rates", "rated", "rating",
    "deem", "deems", "deemed", "deeming",
    "label", "labels", "labeled", "labeling", "labelled", "labelling",
    "mark", "marks", "marked", "marking",
}

AS_FOLLOWERS = {
    "not", "high", "low", "important", "critical", "urgent", "priority",
    "optional", "necessary", "safe", "unsafe", "risky", "relevant",
    "irrelevant", "acceptable", "unacceptable", "good", "bad", "better",
    "worse", "best", "worst", "major", "minor", "primary", "secondary",
    "top", "key", "essential", "useful", "harmful", "likely", "unlikely",
    "possible", "impossible", "required",
}

THIRD_PERSON_SINGULAR_SUBJECTS = {
    "this", "that", "it", "he", "she",
}

VERB_CONTEXT_FOLLOWERS = {
    "not", "very", "too", "so", "quite", "rather", "really",
    "good", "great", "bad", "better", "worse", "best", "worst",
    "important", "critical", "urgent", "fine", "okay", "ok",
    "to", "for", "with", "at", "in", "on", "about", "like",
}

PRONOUN_FOLLOWERS = {
    "am", "was", "wasn't", "have", "haven't", "had", "hadn't",
    "can", "can't", "could", "couldn't", "do", "don't", "did",
    "didn't", "feel", "felt", "find", "found", "get", "got",
    "go", "going", "guess", "hope", "know", "like", "love",
    "mean", "need", "prefer", "remember", "said", "saw", "see",
    "seen", "suppose", "think", "understand", "want", "went",
    "will", "won't", "would", "wouldn't",
}


def normalize_broken_letter(letter):
    if len(letter) != 1 or not letter.isalpha():
        raise ValueError("broken letter must be a single alphabetic character")
    return letter.lower()


def get_suggestions(word):
    """Ask aspell for suggestions for a misspelled word.
    Returns a list of suggestions, or None if the word is correct."""
    result = subprocess.run(
        ["aspell", "-a"],
        input=f"{word}\n",
        capture_output=True,
        text=True,
    )
    for line in result.stdout.splitlines():
        if line.startswith("*"):
            return None
        if line.startswith("&"):
            parts = line.split(": ", 1)
            if len(parts) == 2:
                return [suggestion.strip() for suggestion in parts[1].split(", ")]
        if line.startswith("#"):
            return []
    return []


def is_letter_insertion(original, candidate, broken_letter):
    """Return True if candidate equals original with one or more inserted broken letters."""
    original_lower = original.lower()
    candidate_lower = candidate.lower()
    if len(candidate_lower) <= len(original_lower):
        return False

    index_original = 0
    index_candidate = 0
    broken_letter = broken_letter.lower()
    while index_original < len(original_lower) and index_candidate < len(candidate_lower):
        if original_lower[index_original] == candidate_lower[index_candidate]:
            index_original += 1
            index_candidate += 1
        elif candidate_lower[index_candidate] == broken_letter:
            index_candidate += 1
        else:
            return False

    return all(character == broken_letter for character in candidate_lower[index_candidate:])


def split_word_parts(word):
    """Split a token into leading punctuation, alphabetic core, and trailing punctuation."""
    prefix = re.match(r"^([^a-zA-Z]*)", word).group(1)
    suffix = re.search(r"([^a-zA-Z]*)$", word).group(1)
    core = word[len(prefix):len(word) - len(suffix) if suffix else None]
    return prefix, core, suffix


def get_alpha_core(word):
    """Return the alphabetic core of a token, or an empty string if there isn't one."""
    return split_word_parts(word)[1]


def detect_sentence_start(previous_word):
    previous_core = get_alpha_core(previous_word) if previous_word else ""
    if not previous_core:
        return True
    return bool(previous_word and re.search(r"[.!?][\"')\]]*$", previous_word.rstrip()))


def restore_case(word, template):
    if template.isupper():
        return word.upper()
    if template.istitle():
        return word.capitalize()
    return word


def pick_insertion_suggestion(lookup_word, suggestions, broken_letter):
    """Pick the most suitable insertion-based suggestion for the original word casing."""
    matches = [
        suggestion
        for suggestion in suggestions
        if is_letter_insertion(lookup_word, suggestion, broken_letter)
    ]
    if not matches:
        return None

    if lookup_word.islower():
        matches = [suggestion for suggestion in matches if suggestion.islower()]
        if not matches:
            return None

    domain_words_lower = {word.lower() for word in DOMAIN_WORDS}
    domain_matches = [suggestion for suggestion in matches if suggestion.lower() in domain_words_lower]
    if domain_matches:
        return domain_matches[0]

    return matches[0]


def generate_letter_insertions(word, letter, count):
    """Generate all strings formed by inserting `letter` exactly `count` times."""
    states = {word}
    for _ in range(count):
        next_states = set()
        for state in states:
            for index in range(len(state) + 1):
                next_states.add(state[:index] + letter + state[index:])
        states = next_states
    return states


def get_correct_words(words):
    """Return the subset of words aspell considers correct, using one batch call."""
    if not words:
        return set()

    result = subprocess.run(
        ["aspell", "-a"],
        input="\n".join(words) + "\n",
        capture_output=True,
        text=True,
    )

    statuses = []
    for line in result.stdout.splitlines():
        if line.startswith("*"):
            statuses.append(True)
        elif line.startswith("&") or line.startswith("#"):
            statuses.append(False)

    domain_words_lower = {word.lower() for word in DOMAIN_WORDS}
    if len(statuses) != len(words):
        return {word for word in words if word.lower() in domain_words_lower}

    return {
        word
        for word, is_correct in zip(words, statuses)
        if is_correct or word.lower() in domain_words_lower
    }


def score_multi_insertion_candidate(candidate, original, broken_letter, insertions):
    """Score candidates so deterministic and domain-relevant words are preferred."""
    candidate_lower = candidate.lower()
    score = 0
    if candidate_lower in DOMAIN_WORDS:
        score += 100
    if candidate_lower.startswith(broken_letter) and not original.startswith(broken_letter):
        score += 3
    if candidate_lower.endswith(broken_letter):
        score += 1
    score -= insertions
    return score


def find_multi_insertion_candidate(
    lookup_word,
    broken_letter,
    min_insertions=1,
    max_insertions=MAX_MULTI_INSERTIONS,
    only_domain_words=False,
):
    """Find a valid correction by inserting the broken letter multiple times."""
    if not lookup_word.isalpha() or len(lookup_word) < 3:
        return None

    lookup_word = lookup_word.lower()
    best_candidate = None
    best_score = None

    for insertions in range(min_insertions, max_insertions + 1):
        candidates = sorted(generate_letter_insertions(lookup_word, broken_letter, insertions))
        correct_words = get_correct_words(candidates)
        if only_domain_words:
            domain_words_lower = {word.lower() for word in DOMAIN_WORDS}
            correct_words = {candidate for candidate in correct_words if candidate.lower() in domain_words_lower}

        for candidate in sorted(correct_words):
            score = score_multi_insertion_candidate(candidate, lookup_word, broken_letter, insertions)
            if best_score is None or score > best_score or (score == best_score and candidate < best_candidate):
                best_candidate = candidate
                best_score = score

    return best_candidate


def try_fix_trailing_apostrophe(core, suffix, broken_letter):
    if not suffix.startswith("'") or core.lower().endswith(broken_letter):
        return None

    candidate = f"{core}'{broken_letter}"
    if get_suggestions(candidate.lower()) is None:
        return candidate + suffix[1:]
    return None


def looks_like_plural_number(word):
    """Return True if word is a numeral greater than 1."""
    try:
        return float(word.replace(",", "")) > 1
    except ValueError:
        return False


def fix_plural(word, previous_word, next_word, broken_letter=DEFAULT_BROKEN_LETTER):
    """Add a trailing 's' when the preceding word clearly demands a plural."""
    if normalize_broken_letter(broken_letter) != DEFAULT_BROKEN_LETTER:
        return None

    prefix, core, suffix = split_word_parts(word)
    if not core or core.lower().endswith("s"):
        return None

    previous_core = get_alpha_core(previous_word) if previous_word else ""
    plural_context = (
        previous_core.lower() in PLURALITY_INDICATORS
        or (previous_word is not None and looks_like_plural_number(previous_word))
    )
    if not plural_context:
        return None

    next_core = get_alpha_core(next_word).lower() if next_word else ""
    if next_core and (next_core in VERB_CONTEXT_FOLLOWERS or next_core.endswith("ly")):
        return None

    # Only pluralize words aspell already considers correct (real singular nouns)
    if get_suggestions(core.lower()) is not None:
        return None

    for plural_suffix in ("s", "es"):
        candidate = core.lower() + plural_suffix
        if get_suggestions(candidate) is None:
            return prefix + restore_case(candidate, core) + suffix

    return None


def fix_as_phrase(word, previous_word, next_word, broken_letter=DEFAULT_BROKEN_LETTER):
    """Replace standalone 'a' with 'as' in judge/consider-like contexts."""
    if normalize_broken_letter(broken_letter) != DEFAULT_BROKEN_LETTER:
        return None

    prefix, core, suffix = split_word_parts(word)
    if core.lower() != "a":
        return None

    previous_core = get_alpha_core(previous_word).lower() if previous_word else ""
    if previous_core not in AS_TRIGGER_VERBS:
        return None

    next_core = get_alpha_core(next_word).lower() if next_word else ""
    if not next_core:
        return None

    if next_core not in AS_FOLLOWERS and not next_core.endswith("ly"):
        return None

    fixed = "As" if core.istitle() else "as"
    return prefix + fixed + suffix


def fix_third_person_s_verb(word, previous_word, next_word, broken_letter=DEFAULT_BROKEN_LETTER):
    """Add a missing third-person singular 's' in simple contexts (e.g. this look -> this looks)."""
    if normalize_broken_letter(broken_letter) != DEFAULT_BROKEN_LETTER:
        return None

    prefix, core, suffix = split_word_parts(word)
    if not core or not core.isalpha() or core.lower().endswith("s"):
        return None

    previous_core = get_alpha_core(previous_word).lower() if previous_word else ""
    if previous_core not in THIRD_PERSON_SINGULAR_SUBJECTS:
        return None

    next_core = get_alpha_core(next_word).lower() if next_word else ""
    if not next_core:
        return None
    if next_core not in VERB_CONTEXT_FOLLOWERS and not next_core.endswith("ly"):
        return None

    candidate = core.lower() + "s"
    if get_suggestions(candidate) is not None:
        return None

    return prefix + restore_case(candidate, core) + suffix


def fix_still(word, previous_word, broken_letter=DEFAULT_BROKEN_LETTER):
    """Replace 'till' with 'still' when preceded by a pronoun and broken letter is s."""
    if normalize_broken_letter(broken_letter) != DEFAULT_BROKEN_LETTER:
        return None
    prefix, core, suffix = split_word_parts(word)
    if core.lower() != "till":
        return None
    previous_core = get_alpha_core(previous_word) if previous_word else ""
    if previous_core not in PRONOUNS:
        return None
    fixed = "Still" if core.istitle() else "still"
    return prefix + fixed + suffix


def fix_standalone_i(word, previous_word, next_word, broken_letter=DEFAULT_BROKEN_LETTER):
    """Resolve standalone lowercase 'i' as either 'is' or 'I' when the broken letter is s."""
    if normalize_broken_letter(broken_letter) != DEFAULT_BROKEN_LETTER:
        return None

    prefix, core, suffix = split_word_parts(word)
    if core != "i":
        return None

    next_core = get_alpha_core(next_word) if next_word else ""
    sentence_start = detect_sentence_start(previous_word)
    if sentence_start or next_core.lower() in PRONOUN_FOLLOWERS:
        return prefix + "I" + suffix

    return prefix + "is" + suffix


def fix_word(word, broken_letter=DEFAULT_BROKEN_LETTER):
    """Fix a single word if it's missing the configured letter."""
    broken_letter = normalize_broken_letter(broken_letter)
    prefix, core, suffix = split_word_parts(word)

    if not core:
        return word

    apostrophe_fix = try_fix_trailing_apostrophe(core, suffix, broken_letter)
    if apostrophe_fix is not None:
        return prefix + restore_case(apostrophe_fix, core)

    lookup_word = core + ("'" if suffix.startswith("'") else "")
    trailing_suffix = suffix[1:] if suffix.startswith("'") else suffix
    suggestions = get_suggestions(lookup_word.lower())

    if suggestions is None:
        fixed = find_multi_insertion_candidate(
            lookup_word,
            broken_letter,
            min_insertions=1,
            max_insertions=MAX_MULTI_INSERTIONS,
            only_domain_words=True,
        )
        if fixed is None:
            return word
        fixed = restore_case(fixed.lower(), core)
        return prefix + fixed + trailing_suffix

    fixed = pick_insertion_suggestion(lookup_word, suggestions, broken_letter)
    domain_fallback = find_multi_insertion_candidate(
        lookup_word,
        broken_letter,
        min_insertions=1,
        max_insertions=MAX_MULTI_INSERTIONS,
        only_domain_words=True,
    )
    if domain_fallback is not None and (fixed is None or fixed.lower() not in {word.lower() for word in DOMAIN_WORDS}):
        fixed = domain_fallback
    if fixed is None:
        fixed = find_multi_insertion_candidate(lookup_word, broken_letter)
    if fixed is None:
        return word

    fixed = restore_case(fixed.lower(), core)
    return prefix + fixed + trailing_suffix


def fix_line(line, broken_letter=DEFAULT_BROKEN_LETTER):
    tokens = re.split(r"(\s+)", line)
    fixed_tokens = []

    for index, token in enumerate(tokens):
        if token.isspace():
            fixed_tokens.append(token)
            continue

        previous_word = next((tokens[i] for i in range(index - 1, -1, -1) if not tokens[i].isspace()), None)
        next_word = next((tokens[i] for i in range(index + 1, len(tokens)) if not tokens[i].isspace()), None)

        fixed_still = fix_still(token, previous_word, broken_letter=broken_letter)
        if fixed_still is not None:
            fixed_tokens.append(fixed_still)
            continue
        fixed_as = fix_as_phrase(token, previous_word, next_word, broken_letter=broken_letter)
        if fixed_as is not None:
            fixed_tokens.append(fixed_as)
            continue
        fixed_verb = fix_third_person_s_verb(token, previous_word, next_word, broken_letter=broken_letter)
        if fixed_verb is not None:
            fixed_tokens.append(fixed_verb)
            continue
        fixed_plural = fix_plural(token, previous_word, next_word, broken_letter=broken_letter)
        if fixed_plural is not None:
            fixed_tokens.append(fixed_plural)
            continue
        fixed_i = fix_standalone_i(token, previous_word, next_word, broken_letter=broken_letter)
        fixed_tokens.append(fixed_i if fixed_i is not None else fix_word(token, broken_letter=broken_letter))

    return "".join(fixed_tokens)


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Restore a missing letter in text")
    parser.add_argument("text", nargs="*", help="Text to fix; if omitted, read stdin or use interactive mode")
    parser.add_argument(
        "--broken-letter",
        default=DEFAULT_BROKEN_LETTER,
        help=f"Letter that the keyboard is missing (default: {DEFAULT_BROKEN_LETTER})",
    )
    args = parser.parse_args(argv)
    args.broken_letter = normalize_broken_letter(args.broken_letter)
    return args


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])

    if args.text:
        print(fix_line(" ".join(args.text), broken_letter=args.broken_letter))
    elif not sys.stdin.isatty():
        for line in sys.stdin:
            print(fix_line(line.rstrip("\n"), broken_letter=args.broken_letter))
    else:
        print("Smart letter restorer — type a sentence and press Enter. Ctrl+C to quit.\n")
        try:
            while True:
                line = input("> ")
                print(" ", fix_line(line, broken_letter=args.broken_letter))
        except (KeyboardInterrupt, EOFError):
            print("\nBye!")


if __name__ == "__main__":
    main()
