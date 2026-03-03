.global _start
.section .rodata
msg: .ascii "Hello, World!\n"

.section .text
_start:
    mov x0, #1
    adr x1, msg
    mov x2, #14
    mov x8, #64
    svc #0
