#!/usr/bin/env python3
"""Real-time faster-whisper with smart diff display.
Shows transcription updating with minimal backspacing + diff log.
Press 'q', Escape, or Ctrl+C to stop."""

from faster_whisper import WhisperModel
from pasimple import PaSimple, PA_STREAM_RECORD, PA_SAMPLE_S16LE
import numpy as np
import time
import sys
import select
import termios
import tty
import signal

_stop = False
_term_settings = None

def _on_signal(sig, frame):
    global _stop
    _stop = True

def _check_key():
    global _stop
    if select.select([sys.stdin], [], [], 0)[0]:
        if sys.stdin.read(1) in ('q', 'Q', '\x1b'):
            _stop = True
    return _stop

def common_prefix_len(a, b):
    """Find length of common prefix between two strings"""
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            return i
    return min(len(a), len(b))

def smart_backspace_update(old, new):
    """
    Update terminal from old text to new text with minimal backspacing.
    Returns (num_deleted, deleted_str, added_str) for logging.
    """
    plen = common_prefix_len(old, new)
    to_del = len(old) - plen
    to_add = new[plen:]
    deleted = old[plen:]

    if to_del > 0:
        # Backspace, overwrite with spaces, backspace again (destructive backspace)
        sys.stdout.write('\b' * to_del + ' ' * to_del + '\b' * to_del)

    sys.stdout.write(to_add)
    sys.stdout.flush()

    return to_del, deleted, to_add

def main():
    global _stop, _term_settings

    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 30

    print("Loading tiny.en model...")
    model = WhisperModel("tiny.en", device="cpu", compute_type="int8")

    print(f"\n🎤 Recording {duration}s... (q/Esc/Ctrl+C to stop)")
    print("━" * 60)
    print("OUTPUT: ", end="", flush=True)
    # We'll track cursor position - output starts after "OUTPUT: "

    sample_rate = 16000
    chunk_ms = 150
    chunk_bytes = int(sample_rate * chunk_ms / 1000) * 2

    all_audio = []
    displayed = ""  # What's currently shown on screen
    last_text = ""

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    if sys.stdin.isatty():
        _term_settings = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin.fileno())

    diff_log = []  # Store diff operations for display at end

    try:
        with PaSimple(PA_STREAM_RECORD, PA_SAMPLE_S16LE, 1, sample_rate) as pa:
            t0 = time.time()
            end = t0 + duration

            while time.time() < end and not _stop:
                _check_key()
                if _stop:
                    break

                data = pa.read(chunk_bytes)
                all_audio.append(np.frombuffer(data, dtype=np.int16))

                audio = np.concatenate(all_audio).astype(np.float32) / 32768.0
                segments, _ = model.transcribe(
                    audio, beam_size=5, language="en",
                    vad_filter=True, without_timestamps=True
                )
                text = " ".join(s.text for s in segments).strip()

                if text != last_text:
                    elapsed = time.time() - t0

                    # Smart update - only backspace what changed
                    ndel, deleted, added = smart_backspace_update(displayed, text)

                    # Log the diff operation
                    if ndel > 0:
                        diff_log.append(f"[{elapsed:5.1f}s] ←{ndel} '{deleted[:20]}' → '{added[:20]}'")
                    else:
                        diff_log.append(f"[{elapsed:5.1f}s] +'{added[:30]}'")

                    displayed = text
                    last_text = text

    finally:
        if _term_settings:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, _term_settings)

    # Final output
    print("\n" + "━" * 60)
    if _stop:
        print("⏹️  Stopped")
    print(f"✅ Final: {displayed}")

    # Show diff log
    print("\n" + "━" * 60)
    print("DIFF LOG (showing smart backspace operations):")
    print("━" * 60)
    for entry in diff_log[-30:]:  # Last 30 operations
        print(entry)
    print(f"\nTotal updates: {len(diff_log)}")

if __name__ == "__main__":
    main()
