import os, sys
sys.path.insert(0, os.path.abspath('python'))
from agent.shell_backend import create_shell_backend
from agent.constant import WORK_DIR
b = create_shell_backend(WORK_DIR)
r = b.execute("Write-Error 'boom'")
print('exit', r.exit_code)
print(repr(r.output[:400]))
