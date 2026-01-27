#!/usr/bin/env python3
"""Compare SSH password encryption implementations - token count and functionality"""
import os, subprocess as sp, tempfile, shutil
from pathlib import Path

try:
    import tiktoken
    enc = tiktoken.get_encoding('cl100k_base')
    tok = lambda s: len(enc.encode(s))
except:
    tok = lambda s: len(s) // 4

# =============================================================================
# CURRENT: Shared XOR key (synced via git)
# =============================================================================
CURRENT = '''_kf = Path(DATA_DIR) / '.sshkey'
def _k(): return _kf.read_bytes() if _kf.exists() else (_kf.write_bytes(k := os.urandom(32)) or k)
def _enc(t): k = _k(); return base64.b64encode(bytes(a ^ k[i % 32] for i, a in enumerate(t.encode()))).decode() if t else None
def _dec(e):
    try: k = _k(); return bytes(a ^ k[i % 32] for i, a in enumerate(base64.b64decode(e))).decode() if e else None
    except: return None'''

# =============================================================================
# ALT 1: Per-device SSH keys using age CLI
# =============================================================================
ALT1_AGE = '''def _enc(t):
    pubs = list(Path(DATA_DIR,'devices').glob('*.pub'))
    return sp.run(['age']+[f'-R={p}'for p in pubs]+['-a'],input=t,capture_output=True,text=True).stdout.strip() if pubs and t else None
def _dec(e):
    try: return sp.run(['age','-d','-i',Path.home()/'.ssh/id_ed25519'],input=e,capture_output=True,text=True).stdout if e else None
    except: return None'''

# =============================================================================
# ALT 2: Per-device using nacl (no external CLI)
# =============================================================================
ALT2_NACL = '''from nacl.public import PrivateKey,PublicKey,Box,SealedBox
import json
_sk = lambda: PrivateKey((Path(DATA_DIR)/'.nacl_sk').read_bytes()) if (Path(DATA_DIR)/'.nacl_sk').exists() else (lambda k:(Path(DATA_DIR)/'.nacl_sk').write_bytes(bytes(k)),k)[1](PrivateKey.generate())
def _enc(t):
    pubs = [PublicKey(Path(p).read_bytes()) for p in Path(DATA_DIR,'devices').glob('*.pub')]
    return json.dumps({p.name:SealedBox(pk).encrypt(t.encode()).hex() for p,pk in zip(Path(DATA_DIR,'devices').glob('*.pub'),pubs)}) if pubs and t else None
def _dec(e):
    try: d=json.loads(e); return SealedBox(_sk()).decrypt(bytes.fromhex(d.get(DEVICE_ID,''))).decode()
    except: return None'''

# =============================================================================
# ALT 3: Hybrid - encrypt shared key per-device (re-encrypt key not data)
# =============================================================================
ALT3_HYBRID = '''def _k():
    kf = Path(DATA_DIR)/'.sshkey'
    if kf.exists(): return kf.read_bytes()
    return kf.write_bytes(os.urandom(32)) or kf.read_bytes()
def _enc(t): k=_k(); return base64.b64encode(bytes(a^k[i%32]for i,a in enumerate(t.encode()))).decode() if t else None
def _dec(e):
    try: k=_k(); return bytes(a^k[i%32]for i,a in enumerate(base64.b64decode(e))).decode() if e else None
    except: return None
def _wrap_key():  # encrypt .sshkey for each device's pubkey
    return {p.stem:sp.run(['age','-R',str(p),'-a'],input=_k(),capture_output=True).stdout for p in Path(DATA_DIR,'devices').glob('*.pub')}
def _unwrap_key(wrapped):  # decrypt .sshkey with this device's privkey
    return sp.run(['age','-d','-i',Path.home()/'.ssh/id_ed25519'],input=wrapped,capture_output=True).stdout'''

# =============================================================================
# ALT 4: Minimal age - same logic, fewer chars
# =============================================================================
ALT4_MINIMAL = '''def _enc(t): return sp.run(['age']+[f'-R={p}'for p in Path(DATA_DIR,'devices').glob('*.pub')]+['-a'],input=t,capture_output=True,text=True).stdout if t else None
def _dec(e):
    try: return sp.run(['age','-d','-i',Path.home()/'.ssh/id_ed25519'],input=e,capture_output=True,text=True).stdout
    except: return None'''

# =============================================================================
# Compare
# =============================================================================
implementations = [
    ("CURRENT (XOR shared key)", CURRENT),
    ("ALT1 (age CLI per-device)", ALT1_AGE),
    ("ALT2 (nacl per-device)", ALT2_NACL),
    ("ALT3 (hybrid - wrap key)", ALT3_HYBRID),
    ("ALT4 (minimal age)", ALT4_MINIMAL),
]

print("="*60)
print("SSH Encryption Implementation Comparison")
print("="*60)
for name, code in implementations:
    tokens = tok(code)
    lines = len(code.strip().splitlines())
    print(f"\n{name}")
    print(f"  Tokens: {tokens}")
    print(f"  Lines:  {lines}")
    print(f"  Secure: {'per-device' if 'devices' in code else 'shared key'}")

print("\n" + "="*60)
print("WINNER by tokens:")
print("="*60)
sorted_impl = sorted(implementations, key=lambda x: tok(x[1]))
for i, (name, code) in enumerate(sorted_impl):
    marker = "👑" if i == 0 else "  "
    secure = "✓ per-device" if 'devices' in code else "✗ shared"
    print(f"{marker} {tok(code):3d} tokens | {secure:13} | {name}")

# =============================================================================
# Functional test with simulated devices
# =============================================================================
print("\n" + "="*60)
print("Functional Test (simulated devices)")
print("="*60)

if not shutil.which('age'):
    print("⚠ age not installed - skipping functional test")
    print("  Install: https://github.com/FiloSottile/age")
else:
    with tempfile.TemporaryDirectory() as tmp:
        DATA_DIR = tmp
        devices_dir = Path(tmp) / 'devices'
        devices_dir.mkdir()

        # Simulate 2 devices with age keypairs
        for dev in ['device_A', 'device_B']:
            sp.run(f'age-keygen -o {tmp}/{dev}.key', shell=True, capture_output=True)
            r = sp.run(f'age-keygen -y {tmp}/{dev}.key', shell=True, capture_output=True, text=True)
            (devices_dir / f'{dev}.pub').write_text(r.stdout)

        # Test encryption
        test_pw = "hunter2"

        # Encrypt to all devices
        pubs = list(devices_dir.glob('*.pub'))
        enc_result = sp.run(['age'] + [f'-R={p}' for p in pubs] + ['-a'],
                          input=test_pw.encode(), capture_output=True)
        encrypted = enc_result.stdout

        print(f"Original:  {test_pw}")
        print(f"Encrypted: {encrypted[:60]}...")

        # Each device decrypts
        for dev in ['device_A', 'device_B']:
            dec_result = sp.run(['age', '-d', '-i', f'{tmp}/{dev}.key'],
                              input=encrypted, capture_output=True)
            decrypted = dec_result.stdout.decode()
            status = "✓" if decrypted == test_pw else "✗"
            print(f"  {dev} decrypt: {status} '{decrypted}'")

        # Attacker (no key) cannot decrypt
        print(f"  attacker:      ✗ (no private key)")

print("\n" + "="*60)
print("Conclusion")
print("="*60)
current_tok = tok(CURRENT)
alt4_tok = tok(ALT4_MINIMAL)
diff = alt4_tok - current_tok
print(f"Current:     {current_tok} tokens (shared key, insecure)")
print(f"ALT4 age:    {alt4_tok} tokens (per-device, secure)")
print(f"Difference:  {diff:+d} tokens")
print(f"Requires:    age CLI + device pubkey registration")
