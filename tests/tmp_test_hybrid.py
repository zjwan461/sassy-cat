# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.abspath('python'))
from agent.rag.hybrid import tokenize, BM25Index, rrf_fuse

FAIL=[]
def check(n,c,d=''):
    print(('[PASS] ' if c else '[FAIL] ')+n+(f' | {d}' if d else ''))
    if not c: FAIL.append(n)

check('中文二元切分', '知识' in tokenize('知识库检索') and '检索' in tokenize('知识库检索'))
check('英文标识符切分', 'err_4021' in tokenize('ERR_4021 error'))

docs=[
 ('a','本系统错误码 ERR-4021 表示网关超时，请检查上游连接。'),
 ('b','错误处理的一般原则：先记录日志，再分类重试，最后告警。'),
 ('c','网关配置示例：upstream timeout 30s。'),
]
idx=BM25Index(docs)
hits=idx.search('ERR-4021 怎么解决', 3)
check('BM25 精确编号命中第一', hits and hits[0][0]=='a', str(hits[:2]))

fused=rrf_fuse([['b','a'],['a','c']])
check('RRF 双路共同命中排第一', max(fused, key=fused.get)=='a', str(fused))
print('FAILED:', FAIL)
sys.exit(1 if FAIL else 0)
