"""Verify resampler output lengths."""
import numpy as np

FILTER_DELAY = 64

def lpf_design(cutoff_hz, num_taps, sr):
    nyq = sr / 2.0
    fc = cutoff_hz / nyq
    n = np.arange(num_taps) - (num_taps - 1) / 2.0
    h = np.sinc(2 * fc * n)
    h *= np.kaiser(num_taps, 5.0)
    h /= h.sum()
    return h.astype(np.float64)

lpf = lpf_design(7200.0, 65, 24000)

for src_len in [480, 479, 481, 960, 100, 50]:
    padded_len = FILTER_DELAY + src_len
    filtered_len = padded_len - (len(lpf) - 1)  # valid convolution
    out_len = int(src_len * 16000 / 24000)
    expected = int(src_len * 2 / 3)
    ok = "OK" if out_len == expected else "MISMATCH"
    print(f"src={src_len:4d} filtered={filtered_len:4d} out={out_len:4d} expected={expected:4d} {ok}")

# Verify total output for 1 second of audio
total_24k = 24000
total_16k_expected = 16000
total_out = 0
remaining = 0
for i in range(0, total_24k, 480):
    chunk = min(480, total_24k - i)
    out = int(chunk * 16000 / 24000)
    total_out += out
print(f"\n1 sec 24kHz -> 16kHz: total_out={total_out}, expected={total_16k_expected}, diff={total_out - total_16k_expected}")

# Also test with the resample function directly
import sys
sys.path.insert(0, "/root/app/backend")
from services.vobiz_bridge.audio import resample_24k_to_16k_numpy

# Generate a test tone
t = np.linspace(0, 0.5, 12000, endpoint=False)
tone = (np.sin(2 * np.pi * 440 * t) * 16000).astype(np.int16).tobytes()

state = None
total = 0
for offset in range(0, len(tone), 960):
    chunk = tone[offset:offset+960]
    out, state = resample_24k_to_16k_numpy(chunk, state)
    total += len(out)
print(f"Resampler 0.5s @ 24kHz -> 16kHz: output={total} bytes ({total//2} samples, expected=8000)")
