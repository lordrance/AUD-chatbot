# SafeChat-AUD Web（被试端 v1）

研究取向、纯文本、**不**包含虚拟形象或游戏化。仅通过 Vite 代理调用后端 `http://127.0.0.1:8000` 的 `/api/v1`。

## 被试流程（顺序）

1. **`/`** 说明与须知 → 创建会话（`POST /sessions`）或继续未完成会话  
2. **`/consent`** 知情同意（版本号来自 `GET .../state` 的 `expected_consent_version`）  
3. **`/eligibility`** 资格筛查（AUDIT-C 等，`POST .../eligibility`）  
4. **`/baseline`** 基线（`POST .../surveys/baseline`）  
5. **`/randomize`** 随机分组（`POST .../randomize`）  
6. **`/chat`** 聊天（`POST .../chat/turn`）；消息列表缓存在浏览器 `localStorage`；可选快捷短语、跳过、帮助  
7. **`/post-survey`** 后测（`POST .../surveys/post`，schema v2）  
8. **`/thank-you`** 致谢与 debrief；**`/ineligible`** 不符合条件时的说明与资源  

前端**从不**直接调用大模型；阶段与分组以后端为准。

## 本地运行

```bash
# 终端 1：PostgreSQL + API（见仓库根 README）
cd apps/api && uvicorn ...

# 终端 2
cd apps/web
npm install
npm run dev
```

浏览器打开 `http://127.0.0.1:5173`。

## 仍有 TODO（与里程碑一致）

- **7 天随访**：仅文案占位；后端有 `followup/opt-in` 占位，未接业务。  
- **同意书正文**：页面为伦理摘要占位，正式研究需替换为批件批准的完整 PDF/HTML 与版本号常量对齐。  
- **资源与热线**：帮助弹窗为通用说明，请按属地法规与伦理要求替换具体号码与链接。  
- **聊天历史**：刷新页面依赖本地缓存；无 `GET /chat/history` 时无法从服务器重建完整 transcript（与当前 API 一致）。  
