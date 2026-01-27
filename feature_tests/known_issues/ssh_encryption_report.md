# SSH Password Encryption: Security vs Token Count Analysis

## Problem Statement
aio ssh stores passwords for remote hosts. These passwords sync across devices via git. The encryption method must:
1. Allow authorized devices to decrypt
2. Prevent attackers with repo access from decrypting
3. Minimize token count (code size)

## Current Implementation
**Method:** XOR with shared 32-byte key (`.sshkey` synced via git)

```python
_kf = Path(DATA_DIR) / '.sshkey'
def _k(): return _kf.read_bytes() if _kf.exists() else (_kf.write_bytes(k := os.urandom(32)) or k)
def _enc(t): k = _k(); return base64.b64encode(bytes(a ^ k[i % 32] for i, a in enumerate(t.encode()))).decode() if t else None
def _dec(e):
    try: k = _k(); return bytes(a ^ k[i % 32] for i, a in enumerate(base64.b64decode(e))).decode() if e else None
    except: return None
```

**Stats:** 102 tokens, 6 lines
**Security:** Shared key - anyone with repo access can decrypt

## Alternatives Tested

### 1. age CLI (per-device encryption)
```python
def _enc(t): return sp.run(['age']+[f'-R={p}'for p in Path(DATA_DIR,'devices').glob('*.pub')]+['-a'],input=t,capture_output=True,text=True).stdout if t else None
def _dec(e):
    try: return sp.run(['age','-d','-i',Path.home()/'.ssh/id_ed25519'],input=e,capture_output=True,text=True).stdout
    except: return None
```

**Stats:** 78 tokens, 4 lines
**Security:** Per-device - only registered devices can decrypt
**Requires:** age binary (~1MB), device pubkey registration

### 2. OpenSSL Symmetric
**Stats:** 105 tokens
**Security:** Shared key (same as current)
**Verdict:** More tokens, no security improvement

### 3. OpenSSL Asymmetric
**Stats:** ~150+ tokens
**Security:** Per-device (RSA only)
**Verdict:** Complex, doesn't support Ed25519 (modern SSH keys)

### 4. GPG
**Stats:** ~120+ tokens
**Security:** Per-device
**Verdict:** Heavy dependency, complex key management

## Comparison Table

| Implementation | Tokens | Lines | Security | Dependencies |
|----------------|--------|-------|----------|--------------|
| **age (ALT4)** | **78** | 4 | per-device | age CLI |
| age (ALT1) | 93 | 6 | per-device | age CLI |
| Current XOR | 102 | 6 | shared | none |
| OpenSSL sym | 105 | 5 | shared | openssl (preinstalled) |
| nacl | 168 | 9 | per-device | pynacl |
| Hybrid | 197 | 12 | per-device | age CLI |

## Functional Test Results
```
Simulated devices: device_A, device_B
Encrypted password: hunter2

device_A decrypt: ✓ 'hunter2'
device_B decrypt: ✓ 'hunter2'
attacker (no key): ✗ cannot decrypt
```

## Why No Preinstalled Tool Works

**The core issue:** Modern SSH keys use Ed25519, which is a *signing* algorithm, not an *encryption* algorithm.

- **Ed25519:** Sign/verify only (cannot encrypt)
- **X25519:** Encryption variant (what age uses internally)
- **RSA:** Can encrypt, but fewer people use RSA keys now
- **OpenSSL:** Can do X25519, but API is complex (~150+ tokens)

`age` was designed specifically to solve this problem - it converts Ed25519 SSH keys to X25519 for encryption automatically.

## Recommendation

### Option A: Keep Current (Simple, Less Secure)
- 102 tokens
- Shared key synced via git
- Repo access = full compromise
- **Use case:** Personal/home lab where repo is private

### Option B: Switch to age (Secure, Fewer Tokens)
- 78 tokens (-24 from current)
- Per-device encryption
- Repo access alone insufficient to decrypt
- **Requires:**
  - Install age on each device (~1MB)
  - Device registration workflow
- **Use case:** Multiple users, higher security needs

### Option C: Hybrid (Future)
- Encrypt shared `.sshkey` with age per-device
- Passwords stay XOR encrypted (fast)
- Only key-wrap uses age
- More complex but separates concerns

## Implementation Path for Option B

1. Add age to install.sh:
   ```bash
   curl -sL https://github.com/FiloSottile/age/releases/.../age-linux-amd64.tar.gz | tar xz
   ```

2. Device registration command:
   ```bash
   aio ssh device add  # copies ~/.ssh/id_ed25519.pub to devices/
   ```

3. Replace _enc/_dec with age version (saves 24 tokens)

4. Re-encrypt existing passwords for all registered devices

## Conclusion

**Surprising finding:** Per-device encryption with `age` is both MORE secure AND FEWER tokens than current shared-key XOR.

The trade-off is the `age` dependency (~1MB binary), which could be bundled with aio install.

## References
- [age - simple file encryption](https://github.com/FiloSottile/age)
- [Why Ed25519 can't encrypt](https://blog.filippo.io/using-ed25519-keys-for-encryption/)
- [X25519 key exchange](https://cr.yp.to/ecdh.html)

## Test Script
See: `ssh_encryption_compare.py` in this directory
