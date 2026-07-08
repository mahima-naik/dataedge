import wave
import numpy as np

def analyze_timeline(path, name):
    print("================================================================================")
    print(f"               TIMELINE ANALYSIS: {name}")
    print("================================================================================")
    with wave.open(path, "rb") as wav:
        framerate = wav.getframerate()
        n_frames = wav.getnframes()
        raw_data = wav.readframes(n_frames)
        data = np.frombuffer(raw_data, dtype=np.int16)
        duration = n_frames / framerate
        
        # 1. Timeline of silence gaps (> 100ms)
        zeros = (data == 0)
        gaps = []
        in_gap = False
        gap_start = 0
        zero_count = 0
        for i, val in enumerate(zeros):
            if val:
                if not in_gap:
                    in_gap = True
                    gap_start = i
                zero_count += 1
            else:
                if in_gap:
                    if zero_count >= int(framerate * 0.1): # > 100ms
                        gaps.append((gap_start / framerate, i / framerate, zero_count / framerate * 1000.0))
                    in_gap = False
                    zero_count = 0
        if in_gap and zero_count >= int(framerate * 0.1):
            gaps.append((gap_start / framerate, len(zeros) / framerate, zero_count / framerate * 1000.0))
            
        print("Silence Gaps (> 100ms) Timeline:")
        if not gaps:
            print("  None detected.")
        else:
            for start, end, ms in gaps[:20]:
                print(f"  Gap: {start:5.2f}s - {end:5.2f}s | Duration: {ms:6.1f} ms")
            if len(gaps) > 20:
                print(f"  ... and {len(gaps) - 20} more gaps.")

        # 2. Clicks timeline (severe click bursts)
        diffs = np.abs(np.diff(data))
        severe_clicks = np.where(diffs > 15000)[0]
        print("\nSevere Click (Waveform Discontinuity) Timeline:")
        if len(severe_clicks) == 0:
            print("  None detected.")
        else:
            # Group clicks within 100ms to show bursts
            bursts = []
            current_burst_start = None
            last_click_t = -999.0
            click_count = 0
            for idx in severe_clicks:
                t = idx / framerate
                if t - last_click_t > 0.2: # new burst
                    if current_burst_start is not None:
                        bursts.append((current_burst_start, last_click_t, click_count))
                    current_burst_start = t
                    click_count = 1
                else:
                    click_count += 1
                last_click_t = t
            if current_burst_start is not None:
                bursts.append((current_burst_start, last_click_t, click_count))
                
            for start, end, count in bursts[:20]:
                if start == end:
                    print(f"  Single Click at {start:5.2f}s")
                else:
                    print(f"  Click Burst: {start:5.2f}s - {end:5.2f}s | count: {count}")
            if len(bursts) > 20:
                print(f"  ... and {len(bursts) - 20} more bursts.")

if __name__ == "__main__":
    analyze_timeline("/Users/surya/Desktop/Data-Edge/scratch/camp-manual_selle-20260611T09561_mixed.wav", "OLD BUGGY RECORDING (15:26 IST)")
    analyze_timeline("/Users/surya/Desktop/Data-Edge/scratch/camp-manual_data_-20260611T10203_mixed.wav", "NEW POST-DEPLOY RECORDING (15:50 IST)")
