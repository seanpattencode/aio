#!/usr/bin/env python3
"""Generate minimal ELF binary for aarch64 Linux - just write syscall"""
import struct
import os

BASE = 0x10000  # Lower base = faster loading
EHDR = 64       # ELF header size
PHDR = 56       # Program header size
CODE_OFF = EHDR + PHDR  # Code starts at 120

msg = b"Hello, World!\n"

# AArch64 instructions
def encode():
    code = b''
    # mov x0, #1 (stdout)
    code += struct.pack('<I', 0xD2800020)
    # adr x1, +16 (msg is 16 bytes ahead of this instruction)
    code += struct.pack('<I', 0x10000081)
    # mov x2, #14 (length)
    code += struct.pack('<I', 0xD28001C2)
    # mov x8, #64 (write syscall)
    code += struct.pack('<I', 0xD2800808)
    # svc #0
    code += struct.pack('<I', 0xD4000001)
    return code

code = encode()
total = CODE_OFF + len(code) + len(msg)

# ELF Header (64 bytes)
elf = b'\x7fELF'                      # magic
elf += bytes([2,1,1,0,0,0,0,0,0,0,0,0])  # 64-bit, LE, v1, SYSV, padding
elf += struct.pack('<HHI', 2, 183, 1) # ET_EXEC, EM_AARCH64, v1
elf += struct.pack('<Q', BASE + CODE_OFF)  # e_entry
elf += struct.pack('<Q', EHDR)        # e_phoff
elf += struct.pack('<Q', 0)           # e_shoff (none)
elf += struct.pack('<I', 0)           # e_flags
elf += struct.pack('<HHHHHH', EHDR, PHDR, 1, 0, 0, 0)

# Program Header (56 bytes)
elf += struct.pack('<II', 1, 5)       # PT_LOAD, PF_R|PF_X
elf += struct.pack('<Q', 0)           # p_offset
elf += struct.pack('<QQ', BASE, BASE) # p_vaddr, p_paddr
elf += struct.pack('<QQ', total, total)  # p_filesz, p_memsz
elf += struct.pack('<Q', 0x1000)      # p_align

# Code + data
elf += code + msg

with open('print_tiny', 'wb') as f:
    f.write(elf)
os.chmod('print_tiny', 0o755)
print(f"Created: {len(elf)} bytes")
