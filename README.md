# keyboard-fixer
My keyboard iz mizzing an "s" and hardwarde problemz require zoftware zolutionz

## Batch fixer

```bash
python3 fix.py 'thi i a tet'
python3 fix.py --broken-letter m 'otor oil'
```

## Live evdev fixer

There is also a Linux-only live fixer in [evdev_fix.py](evdev_fix.py). It uses only the Python standard library plus the existing [fix.py](fix.py) logic.

It works by:

1. grabbing a physical keyboard from `/dev/input/event*`
2. echoing typed characters immediately
3. correcting the current word on space or after a short idle timeout
4. re-injecting corrected text through `/dev/uinput`

By default the idle timeout is 1 second.

Example usage:

```bash
python3 evdev_fix.py --list-devices
# find your keyboard name on the list
sudo python3 evdev_fix.py /dev/input/event20
sudo python3 evdev_fix.py --idle-seconds 1.0 /dev/input/event20
sudo python3 evdev_fix.py --broken-letter m /dev/input/event20
```

Notes:

1. This is meant for plain text typing, not shortcut-heavy workflows.
2. You usually need root, or equivalent permissions for `/dev/input/event*` and `/dev/uinput`.
3. If `/dev/uinput` does not exist, load it with `sudo modprobe uinput`.
