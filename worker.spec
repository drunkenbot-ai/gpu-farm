# Build on Windows: pyinstaller --noconfirm worker.spec
# The resulting EXE bundles Python and dependencies; users do not install Python.
a = Analysis(['app/worker_tray.py'], pathex=['.'], binaries=[], datas=[], hiddenimports=['pynvml', 'pystray._win32', 'PIL.Image'], hookspath=[])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, name='GPUFarmWorker', console=False)
