"""Check WAV durations for audio quality analysis."""
import wave, os, struct

d = "/root/app/data/recordings/2026-07-30"
for f in sorted(os.listdir(d)):
    if f.endswith("_outbound.wav"):
        p = os.path.join(d, f)
        try:
            w = wave.open(p, "r")
            frames = w.getnframes()
            rate = w.getframerate()
            dur = frames / rate
            size = os.path.getsize(p)
            # Read first 1000 samples to check for hold-pad DC offset
            raw = w.readframes(min(1000, frames))
            w.close()
            samples = frames
            # Check if file starts with all same sample value (hold-pad)
            first_100 = struct.unpack_from("<100h", raw) if len(raw) >= 200 else []
            const_start = max(abs(s) for s in first_100) if first_100 else 0
            print(f"{f}: {dur:.2f}s, {rate}Hz, {size}B, {samples} smp, const_start={const_start}")
        except Exception as e:
            print(f"{f}: ERROR {e}")
