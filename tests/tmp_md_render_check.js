// 临时校验：引用块内嵌代码围栏在项目所用 markdown-it 下的渲染结果（用完可删）
const MarkdownIt = require('markdown-it')

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

const sample = '> 🛠️ 调用工具 `pwsh`\n> ```json\n> {"command": "ls -la"}\n> ```\n\n' +
  '> ✅ 结果\n> ```text\n> total 0\n> ----\n> ```\n\n收尾正文。\n'

console.log(md.render(sample))