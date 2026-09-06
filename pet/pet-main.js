import { createApp } from 'vue'
import PetApp from './components/PetApp.vue'

// 注意：桌宠窗口必须保持完全透明，不能引入全局 styles.css
// （其 body { background: #0f172a } 会在窗口上铺出深色方块）
// PetApp.vue 使用 scoped 样式，自带所需样式。

createApp(PetApp).mount('#pet-root')
