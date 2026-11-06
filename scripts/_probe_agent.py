# -*- coding: utf-8 -*-
import asyncio, os, sys
for k in list(os.environ):
    if k.lower() in ('http_proxy','https_proxy','all_proxy','no_proxy'):
        os.environ.pop(k, None)
sys.path.insert(0, os.path.abspath('python'))

import config_loader
from config_loader import AppConfig
import agent.engine as engine
from langchain_openai import ChatOpenAI
from langchain.agents.middleware import SummarizationMiddleware  # noqa

fake = AppConfig({
    'llm': {'activeProfile': 'default', 'profiles': {'default': {
        'provider': 'openai', 'baseUrl': 'http://127.0.0.1:9/v1', 'apiKey': 'x',
        'model': 'gpt-4o-mini', 'contextWindow': 8192, 'maxTokens': 1024,
        'contextCompression': {'enabled': False},
    }}},
    'agent': {'activeProfile': 'default', 'profiles': {'default': {'persona': '', 'memoryWindow': 10, 'recursionLimit': 20}},
              'interruptOn': {'execute': True}},
})
config_loader.current = lambda: fake
engine.config_loader.current = lambda: fake
engine.build_chat_llm = lambda profile: ChatOpenAI(model='gpt-4o-mini', api_key='x', base_url='http://127.0.0.1:9/v1')

async def main():
    await engine.init_db()
    try:
        v, agent = engine.holder.get()
        print('OK agent built version', v)
        # 抽查图节点里是否出现 shell 工具
        nodes = list(getattr(agent, 'nodes', {}) or {})
        print('nodes:', [n for n in nodes if 'tool' in n.lower() or 'model' in n.lower()][:8])
    finally:
        await engine.close_db()

asyncio.run(main())
