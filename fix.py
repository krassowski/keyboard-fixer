#!/usr/bin/env python3
"""
fix_s.py - Intelligently restores missing 's' characters in text.

Uses aspell's suggestion engine (available on Ubuntu by default).
For each unknown word, fetches aspell's suggestions and picks any
that can be explained by a missing 's' — i.e. the suggestion equals
the word with one 's' inserted somewhere.

Usage:
    echo "thi i a tet entence" | python3 fix_s.py
    python3 fix_s.py "thi i a tet entence"
    python3 fix_s.py   # interactive mode
"""

import sys
import re
import subprocess


PRONOUN_FOLLOWERS = {
    "am", "was", "wasn't", "have", "haven't", "had", "hadn't",
    "can", "can't", "could", "couldn't", "do", "don't", "did",
    "didn't", "feel", "felt", "find", "found", "get", "got",
    "go", "going", "guess", "hope", "know", "like", "love",
    "mean", "need", "prefer", "remember", "said", "saw", "see",
    "seen", "suppose", "think", "understand", "want", "went",
    "will", "won't", "would", "wouldn't",
}

def get_suggestions(word):
    """Ask aspell for suggestions for a misspelled word.
    Returns a list of suggestions, or None if the word is correct."""
    result = subprocess.run(
        ["aspell", "-a"],
        input=f"{word}\n",
        capture_output=True, text=True
    )
    for line in result.stdout.splitlines():
        if line.startswith("*"):
            return None  # word is correct
        if line.startswith("&"):
            # Format: & original count offset: sug1, sug2, ...
            parts = line.split(": ", 1)
            if len(parts) == 2:
                return [s.strip() for s in parts[1].split(", ")]
        if line.startswith("#"):
            return []  # misspelled, no suggestions
    return []

def is_s_insertion(original, candidate):
    """Return True if candidate == original with one or more 's' characters inserted
    (and no other changes)."""
    orig = original.lower()
    cand = candidate.lower()
    if len(cand) <= len(orig):
        return False
    # Walk both strings; every extra character in candidate must be 's'
    i, j = 0, 0
    while i < len(orig) and j < len(cand):
        if orig[i] == cand[j]:
            i += 1
            j += 1
        elif cand[j] == 's':
            j += 1  # skip an inserted 's'
        else:
            return False  # mismatch that isn't an inserted 's'
    # Any remaining characters in candidate must all be 's'
    return all(c == 's' for c in cand[j:])


def split_word_parts(word):
    """Split a token into leading punctuation, alphabetic core, and trailing punctuation."""
    prefix = re.match(r'^([^a-zA-Z]*)', word).group(1)
    suffix = re.search(r'([^a-zA-Z]*)$', word).group(1)
    core = word[len(prefix):len(word)-len(suffix) if suffix else None]
    return prefix, core, suffix


def get_alpha_core(word):
    """Return the alphabetic core of a token, or an empty string if there isn't one."""
    return split_word_parts(word)[1]


def fix_standalone_i(word, previous_word, next_word):
    """Resolve standalone lowercase 'i' as either 'I' or 'is' using local context."""
    prefix, core, suffix = split_word_parts(word)
    if core != 'i':
        return None

    previous_core = get_alpha_core(previous_word) if previous_word else ''
    next_core = get_alpha_core(next_word) if next_word else ''
    sentence_start = not previous_core
    if previous_word and re.search(r'[.!?]["\')\]]*$', previous_word.rstrip()):
        sentence_start = True

    if sentence_start or next_core.lower() in PRONOUN_FOLLOWERS:
        return prefix + 'I' + suffix

    return prefix + 'is' + suffix

def fix_word(word):
    """Fix a single word if it's missing an 's'."""
    prefix, core, suffix = split_word_parts(word)

    if not core:
        return word

    is_upper = core.isupper()
    is_title = core.istitle()
    check = core.lower()

    suggestions = get_suggestions(check)

    if suggestions is None:
        return word  # already correct

    # Pick the first suggestion explainable by a single missing 's'
    fixed = next((s for s in suggestions if is_s_insertion(check, s)), None)

    if fixed is None:
        return word  # can't fix with an 's' insertion

    if is_upper:
        fixed = fixed.upper()
    elif is_title:
        fixed = fixed.capitalize()

    return prefix + fixed + suffix

def fix_line(line):
    tokens = re.split(r'(\s+)', line)
    fixed_tokens = []

    for index, token in enumerate(tokens):
        if token.isspace():
            fixed_tokens.append(token)
            continue

        previous_word = next((tokens[i] for i in range(index - 1, -1, -1) if not tokens[i].isspace()), None)
        next_word = next((tokens[i] for i in range(index + 1, len(tokens)) if not tokens[i].isspace()), None)

        fixed_i = fix_standalone_i(token, previous_word, next_word)
        fixed_tokens.append(fixed_i if fixed_i is not None else fix_word(token))

    return ''.join(fixed_tokens)

def main():
    if len(sys.argv) > 1:
        text = ' '.join(sys.argv[1:])
        print(fix_line(text))
    elif not sys.stdin.isatty():
        for line in sys.stdin:
            print(fix_line(line.rstrip('\n')))
    else:
        print("Smart 's' restorer — type a sentence and press Enter. Ctrl+C to quit.\n")
        try:
            while True:
                line = input("> ")
                print(" ", fix_line(line))
        except (KeyboardInterrupt, EOFError):
            print("\nBye!")

if __name__ == "__main__":
    main()
