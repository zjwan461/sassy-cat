import os, shutil, subprocess
PWSH = shutil.which('powershell')
code = "$OutputEncoding=[Text.Encoding]::UTF8; [Console]::OutputEncoding=[Text.Encoding]::UTF8; Write-Output '中文输出测试'"
p = subprocess.run([PWSH,'-NoLogo','-NoProfile','-NonInteractive','-Command', code], capture_output=True)
print('raw out:', p.stdout.hex())
print('raw err head:', p.stderr.hex()[:80])
print('decode utf8:', p.stdout.decode('utf-8','replace'))
print('decode gbk:', p.stdout.decode('gbk','replace'))
