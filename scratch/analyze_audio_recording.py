import wave
import numpy as np

def analyze_audio_file(path):
    print("================================================================================")
    print(f"                       DIGITAL AUDIO ANALYSIS REPORT: {path}")
    print("================================================================================")
    with wave.open(path, "rb") as wav:
        n_channels = wav.getnchannels()
        sampwidth = wav.getsampwidth()
        framerate = wav.getframerate()
        n_frames = wav.getnframes()
        
        raw_data = wav.readframes(n_frames)
        data = np.frombuffer(raw_data, dtype=np.int16)
        
        duration = n_frames / framerate
        print(f"File Properties:")
        print(f"  Channels: {n_channels}")
        print(f"  Sample Rate: {framerate} Hz")
        print(f"  Sample Width: {sampwidth} bytes (16-bit PCM)")
        print(f"  Total Duration: {duration:.2f} seconds")
        print(f"  Total Samples: {len(data)}")
        
        # 1. Loudness / Amplitude metrics
        max_amplitude = np.max(np.abs(data))
        rms_amplitude = np.sqrt(np.mean(data.astype(np.float64) ** 2))
        print(f"\nAmplitude & Loudness:")
        print(f"  Peak Amplitude: {max_amplitude} (Max possible: 32767)")
        print(f"  RMS Amplitude: {rms_amplitude:.1f}")
        
        # 2. Silence / Underflow Gaps
        # VoIP underflows produce blocks of exact 0s.
        # Let's count zero-runs longer than 5ms (80 samples at 16kHz)
        zeros = (data == 0)
        zero_runs = []
        current_run = 0
        for val in zeros:
            if val:
                current_run += 1
            else:
                if current_run > 0:
                    zero_runs.append(current_run)
                    current_run = 0
        if current_run > 0:
            zero_runs.append(current_run)
            
        min_run_samples = int(framerate * 0.005) # 5ms
        long_runs = [r for r in zero_runs if r >= min_run_samples]
        
        print(f"\nSilence / Underflow Gaps (> 5ms):")
        print(f"  Total gaps detected: {len(long_runs)}")
        if len(long_runs) > 0:
            total_gap_ms = sum(long_runs) / framerate * 1000.0
            print(f"  Total cumulative gap time: {total_gap_ms:.1f} ms")
            print(f"  Max gap duration: {max(long_runs) / framerate * 1000.0:.1f} ms")
            print(f"  Avg gap duration: {(sum(long_runs) / len(long_runs)) / framerate * 1000.0:.1f} ms")
        else:
            print("  No silent/zero gaps > 5ms detected.")
            
        # 3. Clicks and Pops (Jitter / Discontinuities)
        # Check for sudden first-derivative amplitude jumps (clipping/discontinuity)
        diffs = np.abs(np.diff(data))
        # A jump of > 15000 in a single sample (at 16kHz) represents a severe click
        severe_clicks = np.where(diffs > 15000)[0]
        # A jump of > 8000 is a moderate click/pop
        moderate_clicks = np.where((diffs > 8000) & (diffs <= 15000))[0]
        
        print(f"\nClicks & Pops (Discontinuities):")
        print(f"  Severe clicks (diff > 15000): {len(severe_clicks)}")
        print(f"  Moderate clicks (diff > 8000): {len(moderate_clicks)}")
        
        # 4. Clipping Detection
        clipping_pos = np.where(np.abs(data) >= 32760)[0]
        print(f"\nClipping / Distortion:")
        print(f"  Clipped samples (at max range): {len(clipping_pos)}")
        
        print("================================================================================")

if __name__ == "__main__":
    analyze_audio_file("/Users/surya/Desktop/Data-Edge/scratch/camp-manual_selle-20260611T09561_mixed.wav")
