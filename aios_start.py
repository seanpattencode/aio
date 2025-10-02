#!/usr/bin/env python3
import subprocess, sys, socket, webbrowser
from pathlib import Path
sys.path.append('/home/seanpatten/projects/AIOS')
from core import aios_db
commands = {
    "start": lambda: (
        Path.home().joinpath(".aios").mkdir(exist_ok=True),
        (lambda ports: (
            aios_db.write("ports", {"web": ports[0], "api": ports[1]}),
            aios_db.write("aios_pids", {}),
            (lambda sock: (
                [sock.setsockopt(socket.SOL_SOCKET, opt, 1) for opt in [socket.SO_REUSEADDR, socket.SO_REUSEPORT]],
                sock.bind(('', ports[0])),
                sock.listen(5),
                (lambda procs: (
                    sock.close(),
                    aios_db.write("aios_pids", {"api": procs[0].pid, "web": procs[1].pid}),
                    print(f"AIOS started: http://localhost:{ports[0]}"),
                    webbrowser.open(f"http://localhost:{ports[0]}"),
                    subprocess.Popen(["python3", "-c", "from services import context_generator; context_generator.generate()"], cwd="/home/seanpatten/projects/AIOS")
                ))([
                    subprocess.Popen(["python3", "core/aios_api.py", str(ports[1])], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
                    subprocess.Popen(["python3", "services/web/web.py", str(sock.fileno()), str(ports[0]), str(ports[1])], pass_fds=[sock.fileno()])
                ])
            ))(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
        ))([
            (lambda sk: (sk.bind(('', 0)), sk.getsockname()[1], sk.close())[1])(socket.socket()),
            (lambda sk: (sk.bind(('', 0)), sk.getsockname()[1], sk.close())[1])(socket.socket())
        ])
    )[-1],
    "stop": lambda: (
        subprocess.run(["pkill", "-9", "-f", "core/aios_api.py"], stderr=subprocess.DEVNULL),
        subprocess.run(["pkill", "-9", "-f", "services/web/web.py"], stderr=subprocess.DEVNULL),
        aios_db.write("aios_pids", {}),
        print("AIOS stopped")
    )[-1],
    "status": lambda: print(f"PIDs: {aios_db.read('aios_pids')}")
}
commands[(sys.argv + ["start"])[1]]()