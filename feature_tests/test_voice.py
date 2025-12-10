#!/usr/bin/env python3
"""
Voice transcription test file - compare multiple methods
Usage:
  python test_voice.py file <audio.wav>     # Test with audio file
  python test_voice.py mic <duration>       # Test with microphone (default 5s)
  python test_voice.py mic 10 whisper       # Specific method
  python test_voice.py all                  # Real-time streaming methods only

Methods: sherpa, whisper, vosk, fwhisper (faster-whisper)
"""
import sys, os, time

# Latency config: smaller = lower latency, higher CPU
CHUNK_MS = 30  # 30ms chunks for low latency (was 100ms)

# ============== METHOD 1: SHERPA-ONNX (streaming) ==============
def test_sherpa_file(audio_path):
    """Test sherpa-onnx with audio file"""
    print("\n[SHERPA-ONNX] Testing with file...")
    try:
        import sherpa_onnx
        import wave
        import numpy as np

        model_dir = os.path.expanduser('~/.local/share/sherpa-onnx/sherpa-onnx-streaming-zipformer-en-2023-06-26')
        if not os.path.exists(model_dir):
            print("  ERROR: Model not found. Run: aio voice (to auto-download)")
            return None

        recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=f'{model_dir}/tokens.txt',
            encoder=f'{model_dir}/encoder-epoch-99-avg-1-chunk-16-left-128.onnx',
            decoder=f'{model_dir}/decoder-epoch-99-avg-1-chunk-16-left-128.onnx',
            joiner=f'{model_dir}/joiner-epoch-99-avg-1-chunk-16-left-128.onnx',
            num_threads=2, sample_rate=16000, feature_dim=80,
            enable_endpoint_detection=True,
        )

        # Read wav file
        with wave.open(audio_path, 'rb') as wf:
            sample_rate = wf.getframerate()
            channels = wf.getnchannels()
            frames = wf.readframes(wf.getnframes())
            samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
            if channels == 2:
                samples = samples[::2]  # Take left channel

        stream = recognizer.create_stream()
        stream.accept_waveform(sample_rate, samples)

        # Process in chunks
        while recognizer.is_ready(stream):
            recognizer.decode_stream(stream)

        result = recognizer.get_result(stream)
        print(f"  Result: {result}")
        return result
    except Exception as e:
        print(f"  ERROR: {e}")
        return None

def test_sherpa_mic(duration=5):
    """Test sherpa-onnx with microphone - real-time streaming using pasimple"""
    print(f"\n[SHERPA-ONNX] Recording {duration}s from mic (streaming)...")
    try:
        import sherpa_onnx
        from pasimple import PaSimple, PA_STREAM_RECORD, PA_SAMPLE_S16LE
        import numpy as np

        model_dir = os.path.expanduser('~/.local/share/sherpa-onnx/sherpa-onnx-streaming-zipformer-en-2023-06-26')
        if not os.path.exists(model_dir):
            print("  ERROR: Model not found. Run: aio voice (to auto-download)")
            return None

        recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=f'{model_dir}/tokens.txt',
            encoder=f'{model_dir}/encoder-epoch-99-avg-1-chunk-16-left-128.onnx',
            decoder=f'{model_dir}/decoder-epoch-99-avg-1-chunk-16-left-128.onnx',
            joiner=f'{model_dir}/joiner-epoch-99-avg-1-chunk-16-left-128.onnx',
            num_threads=2, sample_rate=16000, feature_dim=80,
            enable_endpoint_detection=True, rule1_min_trailing_silence=2.0, rule2_min_trailing_silence=1.0,
        )

        stream = recognizer.create_stream()
        sample_rate = 48000  # Use native rate, sherpa resamples internally
        chunk_samples = int(CHUNK_MS / 1000 * sample_rate)  # Low latency chunks
        chunk_bytes = chunk_samples * 2  # 2 bytes per int16 sample

        print(f"  Sample rate: {sample_rate}Hz, chunk: {CHUNK_MS}ms (low latency)")
        print("  Speak now! (real-time partial results shown)")

        all_results = []
        last_result = ''

        with PaSimple(PA_STREAM_RECORD, PA_SAMPLE_S16LE, 1, sample_rate) as pa:
            end = time.time() + duration
            while time.time() < end:
                data = pa.read(chunk_bytes)
                samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                stream.accept_waveform(sample_rate, samples)

                while recognizer.is_ready(stream):
                    recognizer.decode_stream(stream)

                result = recognizer.get_result(stream)
                if result and result != last_result:
                    print(f"\r  Partial: {result}", end='', flush=True)
                    last_result = result

                if recognizer.is_endpoint(stream) and result:
                    print(f"\n  [ENDPOINT]: {result}")
                    all_results.append(result)
                    recognizer.reset(stream)
                    last_result = ''

        # Get final result
        final = recognizer.get_result(stream)
        if final:
            all_results.append(final)

        full_text = ' '.join(all_results)
        print(f"\n  Final: {full_text}")
        return full_text
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback; traceback.print_exc()
        return None

# ============== METHOD 2: WHISPER (batch) ==============
def test_whisper_file(audio_path, model_size='base'):
    """Test OpenAI Whisper with audio file"""
    print(f"\n[WHISPER {model_size}] Testing with file...")
    try:
        import whisper

        print("  Loading model...")
        model = whisper.load_model(model_size)

        print("  Transcribing...")
        start = time.time()
        result = model.transcribe(audio_path)
        elapsed = time.time() - start

        text = result['text'].strip()
        print(f"  Result ({elapsed:.2f}s): {text}")
        return text
    except Exception as e:
        print(f"  ERROR: {e}")
        return None

def test_whisper_mic(duration=5, model_size='base'):
    """Test Whisper with microphone recording"""
    print(f"\n[WHISPER {model_size}] Recording {duration}s from mic...")
    try:
        from pasimple import record_wav
        import whisper
        import tempfile

        f = tempfile.mktemp(suffix='.wav')
        print("  Recording... (speak now)")
        record_wav(f, duration)
        print("  Loading model...")
        model = whisper.load_model(model_size)
        print("  Transcribing...")
        start = time.time()
        result = model.transcribe(f)
        elapsed = time.time() - start
        os.unlink(f)

        text = result['text'].strip()
        print(f"  Result ({elapsed:.2f}s): {text}")
        return text
    except Exception as e:
        print(f"  ERROR: {e}")
        return None

# ============== METHOD 3: VOSK (streaming) ==============
def test_vosk_file(audio_path):
    """Test Vosk with audio file"""
    print("\n[VOSK] Testing with file...")
    try:
        import vosk
        import wave
        import json

        vosk.SetLogLevel(-1)
        model = vosk.Model(lang="en-us")

        with wave.open(audio_path, 'rb') as wf:
            rec = vosk.KaldiRecognizer(model, wf.getframerate())
            rec.SetWords(True)

            results = []
            while True:
                data = wf.readframes(4000)
                if len(data) == 0:
                    break
                if rec.AcceptWaveform(data):
                    r = json.loads(rec.Result())
                    if r.get('text'):
                        results.append(r['text'])

            # Final result
            r = json.loads(rec.FinalResult())
            if r.get('text'):
                results.append(r['text'])

        text = ' '.join(results)
        print(f"  Result: {text}")
        return text
    except Exception as e:
        print(f"  ERROR: {e}")
        return None

def test_vosk_mic(duration=5):
    """Test Vosk with microphone - real-time streaming using pasimple"""
    print(f"\n[VOSK] Recording {duration}s from mic (streaming)...")
    try:
        import vosk
        from pasimple import PaSimple, PA_STREAM_RECORD, PA_SAMPLE_S16LE
        import json

        vosk.SetLogLevel(-1)
        model = vosk.Model(lang="en-us")

        sample_rate = 48000  # Use native rate
        rec = vosk.KaldiRecognizer(model, sample_rate)
        rec.SetWords(True)

        chunk_samples = int(CHUNK_MS / 1000 * sample_rate)  # Low latency chunks
        chunk_bytes = chunk_samples * 2

        print(f"  Sample rate: {sample_rate}Hz, chunk: {CHUNK_MS}ms (low latency)")
        print("  Speak now! (real-time partial results shown)")

        all_results = []

        with PaSimple(PA_STREAM_RECORD, PA_SAMPLE_S16LE, 1, sample_rate) as pa:
            end = time.time() + duration
            while time.time() < end:
                data = pa.read(chunk_bytes)
                if rec.AcceptWaveform(data):
                    r = json.loads(rec.Result())
                    if r.get('text'):
                        print(f"\n  [FINAL]: {r['text']}")
                        all_results.append(r['text'])
                else:
                    p = json.loads(rec.PartialResult()).get('partial', '')
                    if p:
                        print(f"\r  Partial: {p}", end='', flush=True)

        # Final result
        r = json.loads(rec.FinalResult())
        if r.get('text'):
            all_results.append(r['text'])

        text = ' '.join(all_results)
        print(f"\n  Final: {text}")
        return text
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback; traceback.print_exc()
        return None

# ============== METHOD 4: FASTER-WHISPER (pseudo-streaming) ==============
def test_fwhisper_file(audio_path, model_size='base'):
    """Test faster-whisper with audio file"""
    print(f"\n[FASTER-WHISPER {model_size}] Testing with file...")
    try:
        from faster_whisper import WhisperModel

        print("  Loading model...")
        model = WhisperModel(model_size, device="cpu", compute_type="int8")

        print("  Transcribing...")
        start = time.time()
        segments, info = model.transcribe(audio_path, beam_size=1, vad_filter=True)
        text = ' '.join(s.text for s in segments).strip()
        elapsed = time.time() - start

        print(f"  Result ({elapsed:.2f}s): {text}")
        return text
    except Exception as e:
        print(f"  ERROR: {e}")
        return None

def test_fwhisper_mic(duration=5, model_size='base'):
    """Test faster-whisper with mic - pseudo-real-time using short segments"""
    print(f"\n[FASTER-WHISPER {model_size}] Recording {duration}s from mic (pseudo-streaming)...")
    try:
        from faster_whisper import WhisperModel
        from pasimple import PaSimple, PA_STREAM_RECORD, PA_SAMPLE_S16LE
        import numpy as np
        import io, wave

        print("  Loading model...")
        model = WhisperModel(model_size, device="cpu", compute_type="int8")

        sample_rate = 16000  # Whisper native rate
        segment_ms = 500  # Process every 500ms for pseudo-real-time
        chunk_samples = int(segment_ms / 1000 * sample_rate)
        chunk_bytes = chunk_samples * 2

        print(f"  Sample rate: {sample_rate}Hz, segment: {segment_ms}ms")
        print("  Speak now! (pseudo-real-time ~500ms latency)")

        all_audio = []
        last_len = 0
        all_text = []

        with PaSimple(PA_STREAM_RECORD, PA_SAMPLE_S16LE, 1, sample_rate) as pa:
            end = time.time() + duration
            while time.time() < end:
                data = pa.read(chunk_bytes)
                all_audio.append(np.frombuffer(data, dtype=np.int16))

                # Transcribe accumulated audio every segment
                audio = np.concatenate(all_audio).astype(np.float32) / 32768.0
                if len(audio) > last_len + chunk_samples:
                    segments, _ = model.transcribe(audio, beam_size=1, vad_filter=True,
                                                   without_timestamps=True, language='en')
                    text = ' '.join(s.text for s in segments).strip()
                    if text:
                        print(f"\r  Partial: {text[-60:]}", end='', flush=True)
                    last_len = len(audio)

        # Final transcription
        audio = np.concatenate(all_audio).astype(np.float32) / 32768.0
        segments, _ = model.transcribe(audio, beam_size=1, vad_filter=True, language='en')
        text = ' '.join(s.text for s in segments).strip()
        print(f"\n  Final: {text}")
        return text
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback; traceback.print_exc()
        return None

# ============== METHOD 5: SILERO STT ==============
def test_silero_file(audio_path):
    """Test Silero STT with audio file (Apache 2.0 license)"""
    print("\n[SILERO] Testing with file...")
    try:
        import torch
        import torchaudio
        import wave
        import numpy as np

        device = torch.device('cpu')
        model, decoder, utils = torch.hub.load(
            repo_or_dir='snakers4/silero-models', model='silero_stt',
            language='en', device=device, trust_repo=True
        )

        # Load audio manually to avoid torchcodec dependency
        with wave.open(audio_path, 'rb') as wf:
            sample_rate = wf.getframerate()
            frames = wf.readframes(wf.getnframes())
            audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

        # Resample to 16kHz if needed
        if sample_rate != 16000:
            audio = torch.tensor(audio).unsqueeze(0)
            audio = torchaudio.functional.resample(audio, sample_rate, 16000)
            audio = audio.squeeze(0).numpy()

        start = time.time()
        inp = torch.tensor(audio).unsqueeze(0).to(device)
        output = model(inp)
        text = decoder(output[0].cpu())
        elapsed = time.time() - start

        print(f"  Result ({elapsed:.2f}s): {text}")
        return text
    except Exception as e:
        print(f"  ERROR: {e}")
        return None

def test_silero_mic(duration=5):
    """Test Silero STT with microphone"""
    print(f"\n[SILERO] Recording {duration}s from mic...")
    try:
        import torch
        from pasimple import PaSimple, PA_STREAM_RECORD, PA_SAMPLE_S16LE
        import numpy as np

        device = torch.device('cpu')
        model, decoder, utils = torch.hub.load(
            repo_or_dir='snakers4/silero-models', model='silero_stt',
            language='en', device=device, trust_repo=True
        )

        sample_rate = 16000
        chunk_samples = int(CHUNK_MS / 1000 * sample_rate)
        chunk_bytes = chunk_samples * 2

        print(f"  Sample rate: {sample_rate}Hz, chunk: {CHUNK_MS}ms")
        print("  Speak now!")

        all_audio = []
        with PaSimple(PA_STREAM_RECORD, PA_SAMPLE_S16LE, 1, sample_rate) as pa:
            end = time.time() + duration
            while time.time() < end:
                data = pa.read(chunk_bytes)
                all_audio.append(np.frombuffer(data, dtype=np.int16))

        audio = np.concatenate(all_audio).astype(np.float32) / 32768.0
        inp = torch.tensor(audio).unsqueeze(0)
        output = model(inp)
        text = decoder(output[0].cpu())
        print(f"  Final: {text}")
        return text
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback; traceback.print_exc()
        return None

# ============== METHOD 6: MOONSHINE ONNX ==============
def test_moonshine_file(audio_path, model_name='moonshine/tiny'):
    """Test Moonshine ONNX with audio file (MIT license)"""
    print(f"\n[MOONSHINE {model_name.split('/')[-1]}] Testing with file...")
    try:
        import moonshine_onnx

        start = time.time()
        text = moonshine_onnx.transcribe(audio_path, model_name)
        elapsed = time.time() - start

        result = text[0] if isinstance(text, list) else text
        print(f"  Result ({elapsed:.2f}s): {result}")
        return result
    except Exception as e:
        print(f"  ERROR: {e}")
        return None

def test_moonshine_mic(duration=5, model_name='moonshine/tiny'):
    """Test Moonshine ONNX with microphone"""
    print(f"\n[MOONSHINE {model_name.split('/')[-1]}] Recording {duration}s from mic...")
    try:
        import moonshine_onnx
        from pasimple import record_wav
        import tempfile

        f = tempfile.mktemp(suffix='.wav')
        print("  Recording... (speak now)")
        record_wav(f, duration)

        start = time.time()
        text = moonshine_onnx.transcribe(f, model_name)
        elapsed = time.time() - start
        os.unlink(f)

        result = text[0] if isinstance(text, list) else text
        print(f"  Result ({elapsed:.2f}s): {result}")
        return result
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback; traceback.print_exc()
        return None

# ============== METHOD 7: WHISPER.CPP (pywhispercpp) ==============
def test_whispercpp_file(audio_path, model_size='base.en'):
    """Test whisper.cpp via pywhispercpp (MIT license)"""
    print(f"\n[WHISPER.CPP {model_size}] Testing with file...")
    try:
        from pywhispercpp.model import Model

        model = Model(model_size, print_realtime=False, print_progress=False)

        start = time.time()
        segments = model.transcribe(audio_path)
        text = ' '.join(s.text for s in segments).strip()
        elapsed = time.time() - start

        print(f"  Result ({elapsed:.2f}s): {text}")
        return text
    except Exception as e:
        print(f"  ERROR: {e}")
        return None

def test_whispercpp_mic(duration=5, model_size='base.en'):
    """Test whisper.cpp with microphone"""
    print(f"\n[WHISPER.CPP {model_size}] Recording {duration}s from mic...")
    try:
        from pywhispercpp.model import Model
        from pasimple import record_wav
        import tempfile

        f = tempfile.mktemp(suffix='.wav')
        print("  Recording... (speak now)")
        record_wav(f, duration)

        model = Model(model_size, print_realtime=False, print_progress=False)
        start = time.time()
        segments = model.transcribe(f)
        text = ' '.join(s.text for s in segments).strip()
        elapsed = time.time() - start
        os.unlink(f)

        print(f"  Result ({elapsed:.2f}s): {text}")
        return text
    except Exception as e:
        print(f"  ERROR: {e}")
        return None

# ============== METHOD 8: DISTIL-WHISPER (via faster-whisper) ==============
def test_distil_file(audio_path, model_name='distil-small.en'):
    """Test Distil-Whisper via faster-whisper (MIT license)"""
    print(f"\n[DISTIL-WHISPER {model_name}] Testing with file...")
    try:
        from faster_whisper import WhisperModel

        model = WhisperModel(model_name, device="cpu", compute_type="int8")

        start = time.time()
        segments, info = model.transcribe(audio_path, beam_size=1, vad_filter=True)
        text = ' '.join(s.text for s in segments).strip()
        elapsed = time.time() - start

        print(f"  Result ({elapsed:.2f}s): {text}")
        return text
    except Exception as e:
        print(f"  ERROR: {e}")
        return None

def test_distil_mic(duration=5, model_name='distil-small.en'):
    """Test Distil-Whisper with microphone"""
    print(f"\n[DISTIL-WHISPER {model_name}] Recording {duration}s from mic...")
    try:
        from faster_whisper import WhisperModel
        from pasimple import record_wav
        import tempfile

        f = tempfile.mktemp(suffix='.wav')
        print("  Recording... (speak now)")
        record_wav(f, duration)

        model = WhisperModel(model_name, device="cpu", compute_type="int8")
        start = time.time()
        segments, _ = model.transcribe(f, beam_size=1, vad_filter=True, language='en')
        text = ' '.join(s.text for s in segments).strip()
        elapsed = time.time() - start
        os.unlink(f)

        print(f"  Result ({elapsed:.2f}s): {text}")
        return text
    except Exception as e:
        print(f"  ERROR: {e}")
        return None

# ============== FASTER-WHISPER VARIANTS BENCHMARK ==============
def benchmark_fwhisper(audio_path):
    """Benchmark faster-whisper with different models, beam sizes, and batching"""
    print(f"\n{'='*70}")
    print("FASTER-WHISPER VARIANTS BENCHMARK")
    print(f"{'='*70}")

    import wave
    with wave.open(audio_path, 'rb') as wf:
        duration = wf.getnframes() / wf.getframerate()
    print(f"Audio: {audio_path} ({duration:.2f}s)\n")

    from faster_whisper import WhisperModel

    results = []

    # Test configurations: (name, model, beam_size, compute_type, extra_kwargs)
    # Quick test - only fastest variants
    configs = [
        ("tiny.en beam=1", "tiny.en", 1, "int8", {}),
        ("tiny.en beam=5", "tiny.en", 5, "int8", {}),
        ("base.en beam=1", "base.en", 1, "int8", {}),
        ("distil-small.en", "distil-small.en", 1, "int8", {}),
    ]

    for name, model_name, beam_size, compute_type, kwargs in configs:
        try:
            print(f"Testing: {name:<25}", end=" ", flush=True)

            # Load model
            model = WhisperModel(model_name, device="cpu", compute_type=compute_type)

            # Transcribe
            start = time.time()
            segments, info = model.transcribe(
                audio_path,
                beam_size=beam_size,
                language="en",
                vad_filter=kwargs.get("vad_filter", True),
                without_timestamps=True,
            )
            text = " ".join(s.text for s in segments).strip()
            elapsed = time.time() - start
            rtf = elapsed / duration

            print(f"RTF={rtf:.3f}x  Time={elapsed:.2f}s")
            results.append((name, elapsed, rtf, text[:40] if text else ""))

            del model  # Free memory

        except Exception as e:
            print(f"ERROR: {e}")
            results.append((name, 0, 999, f"ERROR: {e}"))

    # Batched inference (skip for quick test, use --full for complete)
    pass

    # Summary
    print(f"\n{'='*70}")
    print("RESULTS SUMMARY (sorted by RTF - lower is faster)")
    print(f"{'='*70}")
    print(f"{'Config':<30} {'Time':>8} {'RTF':>10} {'Preview'}")
    print(f"{'-'*70}")

    for name, elapsed, rtf, preview in sorted(results, key=lambda x: x[2]):
        if rtf < 999:
            print(f"{name:<30} {elapsed:>7.2f}s {rtf:>9.3f}x {preview[:25]}...")
        else:
            print(f"{name:<30} {'N/A':>8} {'N/A':>10} {preview[:25]}")

    # Best result
    best = min(results, key=lambda x: x[2] if x[2] < 999 else float('inf'))
    print(f"\n🏆 Fastest: {best[0]} (RTF={best[2]:.3f}x, {best[1]:.2f}s)")

# ============== BENCHMARK MODE ==============
def get_audio_duration(audio_path):
    """Get audio file duration in seconds"""
    import wave
    try:
        with wave.open(audio_path, 'rb') as wf:
            return wf.getnframes() / wf.getframerate()
    except:
        import subprocess
        result = subprocess.run(['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
                                '-of', 'csv=p=0', audio_path], capture_output=True, text=True)
        return float(result.stdout.strip()) if result.returncode == 0 else 0

def benchmark(audio_path):
    """Benchmark all methods on an audio file, showing RTF (Real-Time Factor)"""
    print(f"\n{'='*60}")
    print(f"BENCHMARK: {audio_path}")
    duration = get_audio_duration(audio_path)
    print(f"Audio duration: {duration:.2f}s")
    print(f"{'='*60}")

    results = []

    methods = [
        ('sherpa', 'Sherpa-ONNX', lambda: test_sherpa_file(audio_path)),
        ('vosk', 'Vosk', lambda: test_vosk_file(audio_path)),
        ('moonshine', 'Moonshine-tiny', lambda: test_moonshine_file(audio_path, 'moonshine/tiny')),
        ('whispercpp', 'Whisper.cpp', lambda: test_whispercpp_file(audio_path, 'tiny.en')),
        ('distil', 'Distil-Whisper', lambda: test_distil_file(audio_path, 'distil-small.en')),
        ('fwhisper', 'Faster-Whisper', lambda: test_fwhisper_file(audio_path, 'tiny')),
        ('silero', 'Silero STT', lambda: test_silero_file(audio_path)),
    ]

    for key, name, fn in methods:
        print(f"\n--- {name} ---")
        try:
            start = time.time()
            text = fn()
            elapsed = time.time() - start
            rtf = elapsed / duration if duration > 0 else 0
            results.append((name, elapsed, rtf, text[:50] if text else 'ERROR'))
        except Exception as e:
            results.append((name, 0, 0, f'ERROR: {e}'))

    print(f"\n{'='*60}")
    print("RESULTS SUMMARY (lower RTF = faster)")
    print(f"{'='*60}")
    print(f"{'Method':<20} {'Time':>8} {'RTF':>8} {'Preview'}")
    print(f"{'-'*60}")
    for name, elapsed, rtf, preview in sorted(results, key=lambda x: x[2] if x[2] > 0 else 999):
        rtf_str = f"{rtf:.3f}x" if rtf > 0 else "N/A"
        print(f"{name:<20} {elapsed:>7.2f}s {rtf_str:>8} {preview[:30]}...")

# ============== MAIN ==============
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nAvailable methods: sherpa, whisper, vosk, fwhisper, silero, moonshine, whispercpp, distil")
        print("\nExamples:")
        print("  python test_voice.py file /tmp/test_audio.wav")
        print("  python test_voice.py file /tmp/test_audio.wav moonshine")
        print("  python test_voice.py mic 5")
        print("  python test_voice.py mic 10 sherpa")
        print("  python test_voice.py all                  # Real-time streaming only")
        print("  python test_voice.py bench /tmp/test.wav  # Benchmark all methods")
        print("  python test_voice.py fwbench /tmp/test.wav # Faster-whisper variants")
        sys.exit(1)

    mode = sys.argv[1]

    if mode == 'file':
        audio_path = sys.argv[2] if len(sys.argv) > 2 else '/tmp/test_speech.wav'
        method = sys.argv[3] if len(sys.argv) > 3 else 'all'

        if not os.path.exists(audio_path):
            print(f"ERROR: File not found: {audio_path}")
            sys.exit(1)

        print(f"Testing with file: {audio_path}")

        if method in ('all', 'sherpa'):
            test_sherpa_file(audio_path)
        if method in ('all', 'whisper'):
            test_whisper_file(audio_path)
        if method in ('all', 'vosk'):
            test_vosk_file(audio_path)
        if method in ('all', 'fwhisper'):
            test_fwhisper_file(audio_path)
        if method in ('all', 'silero'):
            test_silero_file(audio_path)
        if method in ('all', 'moonshine'):
            test_moonshine_file(audio_path)
        if method in ('all', 'whispercpp'):
            test_whispercpp_file(audio_path)
        if method in ('all', 'distil'):
            test_distil_file(audio_path)

    elif mode == 'mic':
        duration = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        method = sys.argv[3] if len(sys.argv) > 3 else 'sherpa'

        print(f"Testing with microphone ({duration}s)")

        if method in ('all', 'sherpa'):
            test_sherpa_mic(duration)
        if method in ('all', 'whisper'):
            test_whisper_mic(duration)
        if method in ('all', 'vosk'):
            test_vosk_mic(duration)
        if method in ('all', 'fwhisper'):
            test_fwhisper_mic(duration)
        if method in ('all', 'silero'):
            test_silero_mic(duration)
        if method in ('all', 'moonshine'):
            test_moonshine_mic(duration)
        if method in ('all', 'whispercpp'):
            test_whispercpp_mic(duration)
        if method in ('all', 'distil'):
            test_distil_mic(duration)

    elif mode == 'all':
        # Test only real-time streaming methods (30ms latency)
        duration = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        print(f"=== REAL-TIME STREAMING TESTS ({duration}s each, {CHUNK_MS}ms chunks) ===")
        print("Testing SHERPA-ONNX...")
        test_sherpa_mic(duration)
        print("\nTesting VOSK...")
        test_vosk_mic(duration)
        print("\nTesting MOONSHINE...")
        test_moonshine_mic(duration)

    elif mode == 'bench':
        audio_path = sys.argv[2] if len(sys.argv) > 2 else '/tmp/test_speech.wav'
        if not os.path.exists(audio_path):
            print(f"ERROR: File not found: {audio_path}")
            sys.exit(1)
        benchmark(audio_path)

    elif mode == 'fwbench':
        # Record from mic if no file provided or duration given
        if len(sys.argv) > 2 and sys.argv[2].isdigit():
            duration = int(sys.argv[2])
            from pasimple import record_wav
            audio_path = '/tmp/fwbench_recording.wav'
            print(f"🎤 Recording {duration}s... speak now!")
            record_wav(audio_path, duration)
            print("Recording done.\n")
        else:
            audio_path = sys.argv[2] if len(sys.argv) > 2 else '/tmp/test_speech.wav'
            if not os.path.exists(audio_path):
                print(f"ERROR: File not found: {audio_path}")
                sys.exit(1)
        benchmark_fwhisper(audio_path)

    else:
        print(f"Unknown mode: {mode}")
        print("Use: file, mic, all, bench, or fwbench")

if __name__ == '__main__':
    main()
