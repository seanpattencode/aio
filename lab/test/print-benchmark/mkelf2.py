#!/usr/bin/env python3
"""Ultra-minimal ELF - overlap structures where possible"""
import struct
import os

# Use lowest possible base address
BASE = 0x10000

# Put code directly after ELF header, skip separate program header
# by overlapping them (classic tiny ELF trick)

msg = b"Hello, World!\n"

# Minimal ELF header with program header overlapped
# Entry at byte 24 (inside the ELF header's e_entry field location)

elf = bytearray(128)

# ELF magic + class
elf[0:4] = b'\x7fELF'
elf[4] = 2      # 64-bit
elf[5] = 1      # little endian
elf[6] = 1      # version
# 7-15: padding (we keep it zero)

# e_type (16-17)
struct.pack_into('<H', elf, 16, 2)  # ET_EXEC
# e_machine (18-19)
struct.pack_into('<H', elf, 18, 183)  # EM_AARCH64
# e_version (20-23)
struct.pack_into('<I', elf, 20, 1)

# Code starts at offset 120 (after 64-byte header + 56-byte program header)
CODE_OFF = 64 + 56

# e_entry (24-31)
struct.pack_into('<Q', elf, 24, BASE + CODE_OFF)
# e_phoff (32-39) - program header at offset 64
struct.pack_into('<Q', elf, 32, 64)
# e_shoff (40-47) - no section headers
struct.pack_into('<Q', elf, 40, 0)
# e_flags (48-51)
struct.pack_into('<I', elf, 48, 0)
# e_ehsize (52-53)
struct.pack_into('<H', elf, 52, 64)
# e_phentsize (54-55)
struct.pack_into('<H', elf, 54, 56)
# e_phnum (56-57)
struct.pack_into('<H', elf, 56, 1)
# e_shentsize, e_shnum, e_shstrndx (58-63)
struct.pack_into('<HHH', elf, 58, 0, 0, 0)

# Program header at offset 64
# p_type (64-67)
struct.pack_into('<I', elf, 64, 1)  # PT_LOAD
# p_flags (68-71)
struct.pack_into('<I', elf, 68, 7)  # PF_R|PF_W|PF_X
# p_offset (72-79)
struct.pack_into('<Q', elf, 72, 0)
# p_vaddr (80-87)
struct.pack_into('<Q', elf, 80, BASE)
# p_paddr (88-95)
struct.pack_into('<Q', elf, 88, BASE)

# Code
code = bytes([
    0x20, 0x00, 0x80, 0xD2,  # mov x0, #1
    0x81, 0x00, 0x00, 0x10,  # adr x1, +16
    0xC2, 0x01, 0x80, 0xD2,  # mov x2, #14
    0x08, 0x08, 0x80, 0xD2,  # mov x8, #64
    0x01, 0x00, 0x00, 0xD4,  # svc #0
])

total = CODE_OFF + len(code) + len(msg)

# p_filesz (96-103)
struct.pack_into('<Q', elf, 96, total)
# p_memsz (104-111)
struct.pack_into('<Q', elf, 104, total)
# p_align (112-119)
struct.pack_into('<Q', elf, 112, 4)  # minimal alignment

# Append code and message
elf = bytes(elf[:CODE_OFF]) + code + msg

with open('print_ultra', 'wb') as f:
    f.write(elf)
os.chmod('print_ultra', 0o755)
print(f"Created: {len(elf)} bytes")
