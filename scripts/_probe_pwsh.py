# -*- coding: utf-8 -*-
import os, shutil, subprocess, time, tempfile, sys
sys.path.insert(0, os.path.abspath('python'))

PWSH = shutil.which('pwsh') or shutil.which('powershell')
print('exe:', PWSH)

def run(cmd, timeout=20):
    prefix = "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false);$OutputEncoding=[Console]::OutputEncoding;"
    argv = [PWSH, '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', prefix + cmd]
    t0 = time.time()
    p = subprocess.run(argv, cwd=os.path.abspath('runtime'), capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL)
    print('rc', p.returncode, 'time', round(time.time()-t0,2))
    for label, b in (('out', p.stdout), ('err', p.stderr)):
        try: text = b.decode('utf-8')
        except UnicodeDecodeError: text = b.decode('gbk', 'replace')
        print(label, repr(text[:300]))

run("Get-ChildItem -Name | Select-Object -First 6")
run("Write-Output '中文输出测试'; Write-Error '错误示例'")
run("cmd /c exit 3")
run("Start-Sleep -Seconds 5", timeout=1)
