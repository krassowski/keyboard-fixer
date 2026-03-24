# keyboard-fixer
My keyboard iz mizzing an "s" and hardwarde problemz require zoftware zolutionz

## Batch fixer

```bash
python3 fix.py 'thi i a tet'
```

## Live evdev fixer

There is also a Linux-only live fixer in [evdev_fix.py](evdev_fix.py). It uses only the Python standard library plus the existing [fix.py](fix.py) logic.

It works by:

1. grabbing a physical keyboard from `/dev/input/event*`
2. buffering typed words
3. fixing them with a one-word delay
4. re-injecting corrected text through `/dev/uinput`

That one-word delay is intentional so standalone `i` can become either `is` or `I` based on the next word.

Example usage:

```bash
python3 evdev_fix.py --list-devices
sudo python3 evdev_fix.py /dev/input/by-id/usb-...-event-kbd
```

Notes:

1. This is meant for plain text typing, not shortcut-heavy workflows.
2. You usually need root, or equivalent permissions for `/dev/input/event*` and `/dev/uinput`.
3. If `/dev/uinput` does not exist, load it with `sudo modprobe uinput`.
