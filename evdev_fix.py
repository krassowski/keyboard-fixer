#!/usr/bin/env python3
"""Live keyboard fixer for Linux evdev/uinput.

This script grabs a physical keyboard device, buffers typed words, fixes them
using the existing spelling logic from fix.py, and injects corrected text back
through uinput. It intentionally delays output by one word so standalone
lowercase "i" can be resolved as either "is" or "I" based on the following
word.

It is designed for plain text entry and assumes a typical Ubuntu system with
access to /dev/input/event* and /dev/uinput.
"""

import argparse
import atexit
import fcntl
import glob
import os
import signal
import struct
import sys
import time

import fix


IOC_NRBITS = 8
IOC_TYPEBITS = 8
IOC_SIZEBITS = 14
IOC_DIRBITS = 2

IOC_NRSHIFT = 0
IOC_TYPESHIFT = IOC_NRSHIFT + IOC_NRBITS
IOC_SIZESHIFT = IOC_TYPESHIFT + IOC_TYPEBITS
IOC_DIRSHIFT = IOC_SIZESHIFT + IOC_SIZEBITS

IOC_NONE = 0
IOC_WRITE = 1

BUS_USB = 0x03
EV_SYN = 0x00
EV_KEY = 0x01
SYN_REPORT = 0

KEY_ESC = 1
KEY_1 = 2
KEY_2 = 3
KEY_3 = 4
KEY_4 = 5
KEY_5 = 6
KEY_6 = 7
KEY_7 = 8
KEY_8 = 9
KEY_9 = 10
KEY_0 = 11
KEY_MINUS = 12
KEY_EQUAL = 13
KEY_BACKSPACE = 14
KEY_TAB = 15
KEY_Q = 16
KEY_W = 17
KEY_E = 18
KEY_R = 19
KEY_T = 20
KEY_Y = 21
KEY_U = 22
KEY_I = 23
KEY_O = 24
KEY_P = 25
KEY_LEFTBRACE = 26
KEY_RIGHTBRACE = 27
KEY_ENTER = 28
KEY_LEFTCTRL = 29
KEY_A = 30
KEY_S = 31
KEY_D = 32
KEY_F = 33
KEY_G = 34
KEY_H = 35
KEY_J = 36
KEY_K = 37
KEY_L = 38
KEY_SEMICOLON = 39
KEY_APOSTROPHE = 40
KEY_GRAVE = 41
KEY_LEFTSHIFT = 42
KEY_BACKSLASH = 43
KEY_Z = 44
KEY_X = 45
KEY_C = 46
KEY_V = 47
KEY_B = 48
KEY_N = 49
KEY_M = 50
KEY_COMMA = 51
KEY_DOT = 52
KEY_SLASH = 53
KEY_RIGHTSHIFT = 54
KEY_LEFTALT = 56
KEY_SPACE = 57
KEY_CAPSLOCK = 58
KEY_F1 = 59
KEY_F12 = 88
KEY_RIGHTCTRL = 97
KEY_RIGHTALT = 100
KEY_HOME = 102
KEY_UP = 103
KEY_PAGEUP = 104
KEY_LEFT = 105
KEY_RIGHT = 106
KEY_END = 107
KEY_DOWN = 108
KEY_PAGEDOWN = 109
KEY_INSERT = 110
KEY_DELETE = 111
KEY_LEFTMETA = 125
KEY_RIGHTMETA = 126

SHIFT_KEYS = {KEY_LEFTSHIFT, KEY_RIGHTSHIFT}
CTRL_KEYS = {KEY_LEFTCTRL, KEY_RIGHTCTRL}
ALT_KEYS = {KEY_LEFTALT, KEY_RIGHTALT}
META_KEYS = {KEY_LEFTMETA, KEY_RIGHTMETA}
MODIFIER_KEYS = SHIFT_KEYS | CTRL_KEYS | ALT_KEYS | META_KEYS | {KEY_CAPSLOCK}
NAVIGATION_KEYS = {
    KEY_ESC, KEY_TAB, KEY_HOME, KEY_UP, KEY_PAGEUP, KEY_LEFT, KEY_RIGHT,
    KEY_END, KEY_DOWN, KEY_PAGEDOWN, KEY_INSERT, KEY_DELETE,
}
LETTER_KEYS = {
    KEY_A, KEY_B, KEY_C, KEY_D, KEY_E, KEY_F, KEY_G, KEY_H, KEY_I, KEY_J,
    KEY_K, KEY_L, KEY_M, KEY_N, KEY_O, KEY_P, KEY_Q, KEY_R, KEY_S, KEY_T,
    KEY_U, KEY_V, KEY_W, KEY_X, KEY_Y, KEY_Z,
}

INPUT_EVENT = struct.Struct("llHHI")
INT_SIZE = struct.calcsize("i")


def _ioc(direction, kind, number, size):
    return (
        (direction << IOC_DIRSHIFT)
        | (ord(kind) << IOC_TYPESHIFT)
        | (number << IOC_NRSHIFT)
        | (size << IOC_SIZESHIFT)
    )


def _io(kind, number):
    return _ioc(IOC_NONE, kind, number, 0)


def _iow(kind, number, size):
    return _ioc(IOC_WRITE, kind, number, size)


EVIOCGRAB = _iow("E", 0x90, INT_SIZE)
UI_SET_EVBIT = _iow("U", 100, INT_SIZE)
UI_SET_KEYBIT = _iow("U", 101, INT_SIZE)
UI_DEV_CREATE = _io("U", 1)
UI_DEV_DESTROY = _io("U", 2)
UI_DEV_SETUP = _iow("U", 3, struct.calcsize("HHHH80sI"))

KEY_TO_CHARS = {
    KEY_A: ("a", "A"),
    KEY_B: ("b", "B"),
    KEY_C: ("c", "C"),
    KEY_D: ("d", "D"),
    KEY_E: ("e", "E"),
    KEY_F: ("f", "F"),
    KEY_G: ("g", "G"),
    KEY_H: ("h", "H"),
    KEY_I: ("i", "I"),
    KEY_J: ("j", "J"),
    KEY_K: ("k", "K"),
    KEY_L: ("l", "L"),
    KEY_M: ("m", "M"),
    KEY_N: ("n", "N"),
    KEY_O: ("o", "O"),
    KEY_P: ("p", "P"),
    KEY_Q: ("q", "Q"),
    KEY_R: ("r", "R"),
    KEY_S: ("s", "S"),
    KEY_T: ("t", "T"),
    KEY_U: ("u", "U"),
    KEY_V: ("v", "V"),
    KEY_W: ("w", "W"),
    KEY_X: ("x", "X"),
    KEY_Y: ("y", "Y"),
    KEY_Z: ("z", "Z"),
    KEY_1: ("1", "!"),
    KEY_2: ("2", "@"),
    KEY_3: ("3", "#"),
    KEY_4: ("4", "$"),
    KEY_5: ("5", "%"),
    KEY_6: ("6", "^"),
    KEY_7: ("7", "&"),
    KEY_8: ("8", "*"),
    KEY_9: ("9", "("),
    KEY_0: ("0", ")"),
    KEY_MINUS: ("-", "_"),
    KEY_EQUAL: ("=", "+"),
    KEY_LEFTBRACE: ("[", "{"),
    KEY_RIGHTBRACE: ("]", "}"),
    KEY_BACKSLASH: ("\\", "|"),
    KEY_SEMICOLON: (";", ":"),
    KEY_APOSTROPHE: ("'", '"'),
    KEY_GRAVE: ("`", "~"),
    KEY_COMMA: (",", "<"),
    KEY_DOT: (".", ">"),
    KEY_SLASH: ("/", "?"),
    KEY_SPACE: (" ", " "),
    KEY_TAB: ("\t", "\t"),
    KEY_ENTER: ("\n", "\n"),
}

CHAR_TO_KEY = {lower: (code, False) for code, (lower, _) in KEY_TO_CHARS.items()}
CHAR_TO_KEY.update({upper: (code, True) for code, (lower, upper) in KEY_TO_CHARS.items() if upper != lower})

WORD_DELIMITERS = {" ", "\t", "\n", ".", ",", "!", "?", ":", ";", "-", "/", "(", ")", "[", "]", "{", "}"}
SENTENCE_ENDERS = {".", "!", "?"}


def list_input_devices():
    devices = []
    for device_path in sorted(glob.glob("/dev/input/event*")):
        event_name = os.path.basename(device_path)
        name_path = f"/sys/class/input/{event_name}/device/name"
        try:
            with open(name_path, "r", encoding="utf-8") as handle:
                name = handle.read().strip()
        except OSError:
            name = "unknown"
        devices.append((device_path, name))
    return devices


class UInputKeyboard:
    def __init__(self):
        self.fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        try:
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_KEY)
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_SYN)
            for key_code in range(256):
                fcntl.ioctl(self.fd, UI_SET_KEYBIT, key_code)

            setup = struct.pack(
                "HHHH80sI",
                BUS_USB,
                0x1,
                0x1,
                0x1,
                b"keyboard-fixer virtual keyboard".ljust(80, b"\0"),
                0,
            )
            fcntl.ioctl(self.fd, UI_DEV_SETUP, setup)
            fcntl.ioctl(self.fd, UI_DEV_CREATE)
            time.sleep(0.1)
        except Exception:
            os.close(self.fd)
            raise

    def close(self):
        if self.fd is None:
            return
        try:
            fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        finally:
            os.close(self.fd)
            self.fd = None

    def emit_event(self, event_type, code, value):
        timestamp = time.time()
        seconds = int(timestamp)
        micros = int((timestamp - seconds) * 1_000_000)
        os.write(self.fd, INPUT_EVENT.pack(seconds, micros, event_type, code, value))

    def sync(self):
        self.emit_event(EV_SYN, SYN_REPORT, 0)

    def emit_key(self, code, value):
        self.emit_event(EV_KEY, code, value)
        self.sync()

    def tap_key(self, code):
        self.emit_key(code, 1)
        self.emit_key(code, 0)

    def type_char(self, character):
        mapping = CHAR_TO_KEY.get(character)
        if mapping is None:
            raise ValueError(f"Unsupported character for injection: {character!r}")
        key_code, needs_shift = mapping
        if needs_shift:
            self.emit_key(KEY_LEFTSHIFT, 1)
        self.tap_key(key_code)
        if needs_shift:
            self.emit_key(KEY_LEFTSHIFT, 0)

    def type_text(self, text):
        for character in text:
            self.type_char(character)


class LiveKeyboardFixer:
    def __init__(self, device_path):
        self.device_path = device_path
        self.input_fd = os.open(device_path, os.O_RDONLY)
        self.output = UInputKeyboard()
        self.shift_pressed = set()
        self.caps_lock = False
        self.suppressed_releases = {}
        self.current_word = []
        self.current_word_sentence_start = True
        self.pending_word = None
        self.pending_delimiter = ""
        self.pending_sentence_start = True
        self.next_word_sentence_start = True

        fcntl.ioctl(self.input_fd, EVIOCGRAB, 1)

    def close(self):
        try:
            self.flush_all()
        finally:
            try:
                fcntl.ioctl(self.input_fd, EVIOCGRAB, 0)
            finally:
                os.close(self.input_fd)
                self.output.close()

    def track_suppressed_release(self, key_code, value):
        if value == 1:
            self.suppressed_releases[key_code] = self.suppressed_releases.get(key_code, 0) + 1
        elif value == 0 and self.suppressed_releases.get(key_code):
            remaining = self.suppressed_releases[key_code] - 1
            if remaining:
                self.suppressed_releases[key_code] = remaining
            else:
                del self.suppressed_releases[key_code]

    def should_consume_release(self, key_code):
        return self.suppressed_releases.get(key_code, 0) > 0

    def update_modifier_state(self, key_code, value):
        is_pressed = value != 0
        if key_code in SHIFT_KEYS:
            if is_pressed:
                self.shift_pressed.add(key_code)
            else:
                self.shift_pressed.discard(key_code)
        elif key_code == KEY_CAPSLOCK and value == 1:
            self.caps_lock = not self.caps_lock

    def event_to_char(self, key_code):
        chars = KEY_TO_CHARS.get(key_code)
        if chars is None:
            return None

        lower, upper = chars
        if key_code in LETTER_KEYS:
            use_upper = bool(self.shift_pressed) ^ self.caps_lock
            return upper if use_upper else lower
        return upper if self.shift_pressed else lower

    def resolve_word(self, word, sentence_start, next_word):
        previous_token = None if sentence_start else "word"
        fixed_i = fix.fix_standalone_i(word, previous_token, next_word)
        if fixed_i is not None:
            return fixed_i
        return fix.fix_word(word)

    def emit_pending_word(self, next_word=None):
        if self.pending_word is None:
            return
        resolved = self.resolve_word(self.pending_word, self.pending_sentence_start, next_word)
        self.output.type_text(resolved)
        self.output.type_text(self.pending_delimiter)
        self.next_word_sentence_start = self.pending_delimiter in SENTENCE_ENDERS or self.pending_delimiter == "\n"
        self.pending_word = None
        self.pending_delimiter = ""

    def start_word_if_needed(self):
        if not self.current_word:
            self.current_word_sentence_start = self.next_word_sentence_start

    def finish_current_word(self, delimiter):
        if not self.current_word:
            self.emit_pending_word()
            self.output.type_text(delimiter)
            self.next_word_sentence_start = delimiter in SENTENCE_ENDERS or delimiter == "\n"
            return

        completed_word = "".join(self.current_word)
        self.current_word.clear()
        self.emit_pending_word(next_word=completed_word)
        self.pending_word = completed_word
        self.pending_delimiter = delimiter
        self.pending_sentence_start = self.current_word_sentence_start

    def flush_all(self):
        current_word = "".join(self.current_word) if self.current_word else None
        self.emit_pending_word(next_word=current_word)
        if current_word:
            self.output.type_text(current_word)
            self.current_word.clear()
            self.next_word_sentence_start = False

    def flush_before_passthrough(self):
        self.flush_all()

    def handle_printable_key(self, key_code, value):
        character = self.event_to_char(key_code)
        if character is None:
            return False

        if value == 0:
            if self.should_consume_release(key_code):
                self.track_suppressed_release(key_code, value)
                return True
            return False

        if value not in (1, 2):
            return False

        self.track_suppressed_release(key_code, 1)
        if character in WORD_DELIMITERS:
            self.finish_current_word(character)
        else:
            self.start_word_if_needed()
            self.current_word.append(character)
        return True

    def handle_backspace(self, value):
        if value == 0:
            if self.should_consume_release(KEY_BACKSPACE):
                self.track_suppressed_release(KEY_BACKSPACE, value)
                return True
            return False

        if value not in (1, 2):
            return False

        if self.current_word:
            self.track_suppressed_release(KEY_BACKSPACE, 1)
            self.current_word.pop()
            return True

        return False

    def passthrough_key(self, key_code, value):
        self.output.emit_key(key_code, value)

    def run(self):
        while True:
            data = os.read(self.input_fd, INPUT_EVENT.size)
            if len(data) != INPUT_EVENT.size:
                continue

            _, _, event_type, code, value = INPUT_EVENT.unpack(data)

            if event_type != EV_KEY:
                continue

            self.update_modifier_state(code, value)

            if code in MODIFIER_KEYS:
                if self.current_word or self.pending_word is not None:
                    self.track_suppressed_release(code, value)
                    continue
                self.passthrough_key(code, value)
                continue

            if code == KEY_BACKSPACE and self.handle_backspace(value):
                continue

            if self.handle_printable_key(code, value):
                continue

            if code in NAVIGATION_KEYS or code in CTRL_KEYS or code in ALT_KEYS or code in META_KEYS:
                if value == 1:
                    self.flush_before_passthrough()
                self.passthrough_key(code, value)
                continue

            if value == 1:
                self.flush_before_passthrough()
            self.passthrough_key(code, value)


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Live spelling fixer using evdev/uinput")
    parser.add_argument("device", nargs="?", help="Input event device, for example /dev/input/by-id/...-event-kbd")
    parser.add_argument("--list-devices", action="store_true", help="List available /dev/input/event* devices and exit")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])

    if args.list_devices:
        for path, name in list_input_devices():
            print(f"{path}: {name}")
        return 0

    if not args.device:
        print("error: provide a device path or use --list-devices", file=sys.stderr)
        return 2

    if not os.path.exists(args.device):
        print(f"error: device not found: {args.device}", file=sys.stderr)
        return 2

    fixer = LiveKeyboardFixer(args.device)
    atexit.register(fixer.close)

    def stop(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    try:
        fixer.run()
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())