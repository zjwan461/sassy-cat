# -*- coding: utf-8 -*-
import sys, os, json
sys.path.insert(0, os.path.abspath('python'))
from deepagents.backends import FilesystemBackend
from deepagents.middleware.skills import _list_skills
from agent.constant import WORK_DIR

b = FilesystemBackend(root_dir=WORK_DIR, virtual_mode=False)
skills = _list_skills(b, str(os.path.join(WORK_DIR, 'skills')))
print('count:', len(skills))
for s in skills[:3]:
    print({k: s[k] for k in ('name','path','description') if k in s})
print('ls root:', str(b.ls('.'))[:300])
r = b.read('skills/weather-skill/SKILL.md')
print('read ok:', type(r).__name__, str(r)[:120])
