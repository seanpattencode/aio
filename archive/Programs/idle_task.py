
def run_idle():
    import time
    print("Idle task running - low priority background work")
    time.sleep(0.05)
    return "Idle work done"
