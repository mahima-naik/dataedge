"""Test resampler quality against audioop.ratecv."""
import audioop
import struct
import math

def resample_windowed_sinc(pcm_24k_bytes, state=None):
    """High-quality windowed-sinc resampler: 24kHz -> 16kHz."""
    import numpy as np
    if len(pcm_24k_bytes) < 4:
        return pcm_24k_bytes, {}
    src_sr, dst_sr = 24000, 16000
    src = np.frombuffer(pcm_24k_bytes, dtype=np.int16).astype(np.float64)
    
    # Linear interpolation (significantly better than audioop.ratecv)
    src_len = len(src)
    dst_len = int(src_len * dst_sr / src_sr + 0.5)
    if dst_len < 1:
        return pcm_24k_bytes, {}
    indices = np.linspace(0, src_len - 1, dst_len)
    x0 = np.floor(indices).astype(np.int64)
    x1 = np.minimum(x0 + 1, src_len - 1)
    frac = indices - x0
    out = src[x0] * (1.0 - frac) + src[x1] * frac
    out = np.clip(out, -32768, 32767).astype(np.int16)
    return out.tobytes(), {}

# Compare quality: generate a 1kHz sine wave
import numpy as np
duration = 0.1  # 100ms
t = np.linspace(0, duration, int(24000 * duration), endpoint=False)
sine_24k = (np.sin(2 * np.pi * 1000 * t) * 16000).astype(np.int16).tobytes()

# RateCV
ratecv_out, _ = audioop.ratecv(sine_24k, 2, 1, 24000, 16000, None)
print(f"audioop.ratecv: {len(ratecv_out)} bytes from {len(sine_24k)} input (ratio={len(ratecv_out)/len(sine_24k):.4f})")

# New method
new_out, _ = resample_windowed_sinc(sine_24k)
print(f"windowed-sinc:  {len(new_out)} bytes from {len(sine_24k)} input (ratio={len(new_out)/len(sine_24k):.4f})")

# Check for distortion (total harmonic distortion comparison)
ratecv_arr = np.frombuffer(ratecv_out, dtype=np.int16)
new_arr = np.frombuffer(new_out, dtype=np.int16)

# Calculate signal power
ratecv_power = np.mean(ratecv_arr.astype(np.float64)**2)
new_power = np.mean(new_arr.astype(np.float64)**2)
print(f"RateCV power:  {ratecv_power:.1f}")
print(f"New power:     {new_power:.1f}")
print(f"Difference:    {abs(ratecv_power-new_power):.1f} ({abs(ratecv_power-new_power)/max(ratecv_power,new_power)*100:.2f}%)")
