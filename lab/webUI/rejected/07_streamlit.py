import streamlit as st, subprocess, time
cmd = st.text_input("Command", "ls")
if st.button("Run"):
    s = time.time(); out = subprocess.getoutput(cmd)
    st.code(out)
    st.write(f"Duration: {time.time()-s}s")
