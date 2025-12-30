#!/usr/bin/env python3
# Proot Ubuntu test: python proot_ubuntu.py [create|test|shell|destroy]
import sys, shutil, subprocess as sp, urllib.request, tarfile
from pathlib import Path
ROOT, PROOT = Path.home()/'.cache/aio-proot', Path.home()/'.local/bin/proot'
def run(cmd): return sp.run(f'{PROOT} -r {ROOT}/rootfs -0 -b /dev -b /proc -b /sys -b /etc/resolv.conf -w /root {cmd}', shell=True)
def create():
    ROOT.mkdir(parents=True, exist_ok=True)
    if not PROOT.exists(): print('📥 proot'); urllib.request.urlretrieve('https://proot.gitlab.io/proot/bin/proot', PROOT); PROOT.chmod(0o755)
    if not (ROOT/'rootfs/bin').exists():
        print('📥 Ubuntu 24.04'); urllib.request.urlretrieve('https://cloud-images.ubuntu.com/wsl/releases/24.04/current/ubuntu-noble-wsl-amd64-24.04lts.rootfs.tar.gz', ROOT/'r.tgz')
        (ROOT/'rootfs').mkdir(exist_ok=True); tarfile.open(ROOT/'r.tgz').extractall(ROOT/'rootfs', filter='data')
    print(f'✓ Ready: {ROOT}')
def test():
    create(); shutil.copy(Path(__file__).parent.parent/'aio.py', ROOT/'rootfs/root/')
    print('🧪 aio install'); run('bash -c "echo n | python3 /root/aio.py install"')
    print('🧪 aio deps'); run('python3 /root/aio.py deps')
def destroy(): shutil.rmtree(ROOT, ignore_errors=True); print(f'✓ Removed {ROOT}')
if __name__ == '__main__':
    {'create': create, 'test': test, 'shell': lambda: (create(), run('bash')), 'destroy': destroy}.get(sys.argv[1] if len(sys.argv) > 1 else '', lambda: print('Usage: create|test|shell|destroy'))()
