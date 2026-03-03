.global main
main:
    lea cmd(%rip), %rdi
    mov %rdi, (%rsi)
    sub $8, %rsp
    call execvp
cmd: .asciz "cmd.exe"
