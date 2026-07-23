# 文渊

“文渊”是一套面向大学生和课题组的私有文献知识库与学术报告辅助系统。用户可以上传自己的文献，建立可追溯的检索库，按模板生成报告，核对引用来源，检测私有语料相似度，并在保留历史版本的前提下润色内容。

系统采用前后端分离的模块化单体架构：

- 前端：React、TypeScript、Vite；
- 后端：FastAPI、SQLAlchemy、Alembic；
- 数据库：PostgreSQL、pgvector；
- 文件：本地文件存储，可通过 `FileStorage` 接口替换；
- AI：OpenAI 兼容 LLM/Embedding 接口，并提供可离线运行的本地基线。

## 核心使用流程

```text
注册登录
  → 创建私有知识库
  → 上传并解析文献
  → 检索和核对知识片段
  → 选择模板生成报告
  → 编辑、引用校验和版本保存
  → 私有语料相似度检测
  → 定向润色或向学术助手提问
  → 导出 DOCX
```

## 功能模块

### 账户与个人中心

- 邮箱和密码注册、登录、刷新会话与退出；
- Argon2 密码哈希，Refresh Token 使用 HttpOnly Cookie；
- 普通用户与管理员角色鉴权，用户数据按所有权隔离；
- 编辑昵称、头像地址和个人简介；
- 查看知识库数、文献数、报告数、文件占用和模型任务数；
- 浅色与深色主题切换；
- SMTP 邮箱验证和验证码找回密码；
- 管理员可以禁用账号、恢复账号和重置密码。

新注册账号默认是普通用户。管理员权限需要由服务器维护者显式授予，参见“初始化管理员账号”。

### 私有知识库

- 创建、编辑和删除知识库；
- 上传 PDF、Markdown、TXT；
- 校验扩展名、MIME、文件大小、PDF 文件头和内容哈希；
- 展示等待、处理、成功、失败状态，并支持失败重试；
- 按标题优先、长度兜底的策略切片，保留标题、页码和相邻重叠；
- 自动提取摘要、关键词和敏感词命中；
- 设置文献作者、标题、年份、来源、分类和标签；
- 将单篇文献移动到当前用户的其他知识库；
- 使用 pgvector 执行 Top-K 检索，展示片段、文件名、标题或页码及相似度；
- 删除文献时同步清理文件、片段和向量，已生成报告中的引用证据保留快照。

默认离线向量器是自研的 512 维字符 n-gram 哈希向量器。管理员也可以配置 OpenAI 兼容的第三方 Embedding 服务，并对既有文献重建向量。

### 报告生成与编辑

- 内置文献综述、开题报告等结构化模板；
- 管理员可以新建、编辑、发布和安全删除模板；
- 模板支持章节新增、删除、排序、章节说明、必填输入和生成参数；
- 已发布模板使用不可变版本，旧报告继续引用创建时的模板版本；
- 每个章节分别构造查询、召回证据并生成内容；
- 报告正文按章节保存为 Markdown，引用关系独立保存；
- 生成过程中展示章节进度，失败章节可以单独重试；
- 编辑章节后自动保存为新版本；
- 历史版本按日期展示，可查看、恢复，不覆盖后续历史；
- 点击引用编号可以核对原文、文献名、标题和页码；
- 导出前检查正文编号、引用记录和参考文献是否对应；
- 文献元数据完整时，在 DOCX 文末生成稳定编号的 GB/T 7714 受控参考文献列表。

没有配置外部 LLM 时，系统使用离线证据摘取草稿器。它只组织本次检索得到的原文片段和有效引用，不进行本地模型生成，也不会编造来源。

### 相似度检测与定向润色

- 按句子和段落切分报告；
- 使用字符 2～4 gram TF-IDF 与余弦相似度匹配当前知识库；
- 保存命中文献、原文、分数和报告偏移区间；
- 汇总“高相似文本占比”，不将其表述为权威论文查重率；
- 提供“学术严谨、通俗表达、精简”三种润色风格；
- 先生成润色预览，只有用户确认后才建立新报告版本；
- 润色失败或取消不会覆盖原稿。

### 证据型学术助手

- 提供“严谨导师”和“数据分析专家”两种角色；
- 支持普通对话和修改建议两种模式；
- 每次提问都会读取当前报告或当前章节，并重新检索当前知识库；
- 回答只能引用本次检索结果中能够映射到真实片段的编号；
- 当前只保存页面中的最后一次问答，不持久化聊天记录，也不自动携带之前的问答历史；
- 普通问答不会修改报告，修改建议也需要用户自行确认和编辑。

### 管理与内容治理

- 用户列表、账号状态、文献数和报告数；
- LLM、提示词、Embedding 三类版本化预设；
- API Key 加密保存，接口只返回是否已配置，不返回明文；
- LLM 预设可以绑定提示词和 Embedding 预设；
- 提示词支持 system/user/assistant 消息、排序、停用和宏变量；
- 敏感词分组、启停、增删修改和批量导入；
- 文献与报告的待审核、已通过、已限制和已下架状态；
- 内容通过、限制、下架、恢复、封禁用户和彻底删除；
- 公告创建、编辑、发布、置顶和定时下线；
- 管理员操作审计，支持按动作、操作者和时间筛选及 CSV 导出；
- CPU、内存、进程占用和应用日志查看。

受限制或已下架的文献不会参与检索；受限制的报告版本不能导出。关键处置操作会写入审计日志。

## 目录结构

```text
frontend/              React 前端
backend/app/           FastAPI 应用、领域模型、服务和适配器
backend/migrations/    Alembic 数据库迁移
backend/tests/         后端自动化测试
backend/scripts/       管理和回归验证脚本
reference/             题目原始资料
素材/                  本地测试文献，不纳入 Git
validation_artifacts/  脱敏回归产物
compose.yaml           PostgreSQL + pgvector 本地服务
start_all.bat          Windows 一键启动入口
start_all.ps1          PowerShell 一键启动入口
```

## 本地运行

### 环境要求

- Windows PowerShell；
- Python 3.12 或兼容版本；
- Node.js 与 npm；
- Docker Desktop，并启用 Docker Compose。

系统固定使用：

- 前端：`http://localhost:7777`
- 后端：`http://localhost:4396`
- OpenAPI：`http://localhost:4396/docs`
- PostgreSQL：`localhost:5432`

### 一键启动

在仓库根目录双击或运行：

```powershell
.\start_all.bat
```

也可以使用：

```powershell
.\start_all.ps1
```

脚本会依次：

1. 通过 Docker Compose 启动 PostgreSQL 和 pgvector；
2. 首次运行时创建 `backend/.venv` 并安装依赖；
3. 从 `.env.example` 创建 `backend/.env`；
4. 执行全部数据库迁移；
5. 在独立窗口启动后端和前端。

### 手动启动

启动数据库：

```powershell
docker compose -p wenyuan up -d db
```

初始化并启动后端：

```powershell
Set-Location backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item ..\.env.example .env
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\uvicorn.exe app.main:app --reload --port 4396
```

在另一个终端启动前端：

```powershell
Set-Location frontend
npm.cmd install
npm.cmd run dev
```

Vite 开发服务器会把 `/api` 请求转发到 `http://localhost:4396`。

## 初始化管理员账号

先通过注册页面创建账号，然后在 `backend` 目录运行：

```powershell
.\.venv\Scripts\python.exe scripts\set_admin_role.py --email admin@example.com
```

重新登录后即可进入管理控制台。

不建议直接向 `users` 表插入明文密码。账号必须使用应用提供的密码哈希函数，并满足 UUID、角色、状态和唯一邮箱等约束。

## 配置 AI 服务

### 管理员控制台配置

推荐在管理员控制台创建并启用 LLM、提示词和 Embedding 预设。运行时按以下顺序选择 LLM：

1. 管理员启用且密钥有效的数据库 LLM 预设；
2. `backend/.env` 中的外部 LLM 配置；
3. 离线证据摘取模式。

数据库中同一类型只应有一个激活预设。模型由管理员为整个平台统一配置，普通用户只能选择润色风格、助手角色和工作模式。

### 环境变量配置

复制 `.env.example` 为 `backend/.env` 后，可以设置：

```dotenv
LLM_BASE_URL=https://example.com/v1
LLM_API_KEY=your-api-key
LLM_MODEL=your-model-name
LLM_TIMEOUT_SECONDS=300
```

Embedding 的离线维度和相似度参数也可以通过环境变量调整：

```dotenv
EMBEDDING_DIMENSIONS=512
SIMILARITY_THRESHOLD=0.10
SIMILARITY_NGRAM_MIN=2
SIMILARITY_NGRAM_MAX=4
SIMILARITY_MIN_SENTENCE_CHARS=12
```

切换 Embedding 模型或维度后，应在管理员控制台执行文献向量重建，避免混用不同模型生成的向量。

## 配置邮件验证码

邮箱验证和找回密码依赖 SMTP。在 `backend/.env` 中配置：

```dotenv
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your-account
SMTP_PASSWORD=your-password-or-app-token
SMTP_FROM=noreply@example.com
SMTP_USE_TLS=true
```

验证码十分钟内有效，只能使用一次。没有配置 SMTP 时，接口会明确返回邮件服务未配置，不会伪装成发送成功。

## 学生端操作

### 建立知识库

1. 注册并登录；
2. 点击“新建知识库”，填写名称和说明；
3. 上传包含文本层的 PDF、Markdown 或 TXT；
4. 等待状态变为“可以检索”；
5. 使用检索证据台验证结果和来源；
6. 根据需要补充作者、年份、来源、分类和标签。

### 生成报告

1. 进入报告装配台；
2. 选择知识库和报告模板；
3. 填写课题名称、研究目标等模板必填项；
4. 创建生成任务并观察章节进度；
5. 点击引用编号核对证据；
6. 编辑章节或单独重试失败章节；
7. 运行引用完整性检查；
8. 补齐参考文献元数据后导出 DOCX。

### 检测和修改报告

1. 在报告页面运行私有语料相似度检测；
2. 查看高相似片段及真实来源；
3. 在编辑器中选择需要修改的文字；
4. 选择润色风格并生成预览；
5. 确认内容无误后接受润色，系统建立新版本；
6. 必要时从历史版本恢复，恢复操作同样会建立新版本。

## 管理员操作

管理员控制台侧边栏提供：

- 仪表盘：服务器资源、应用日志和运行预设；
- LLM 预设：连接地址、模型、密钥和附加参数；
- 提示词预设：消息编排、宏变量和启用状态；
- Embedding 预设：本地或第三方模型、维度和重建向量；
- 敏感词：分组、词项和启停；
- 报告模板：模板信息、章节、参数和版本发布；
- 内容审核：敏感词命中、审核意见和处置；
- 校园公告：草稿、发布、置顶和下线；
- 用户与用量：账号状态、资源数量和密码重置；
- 审计记录：条件筛选和 CSV 导出。

删除正在被历史报告引用的模板会被拒绝。需要停止使用时，应保留旧版本并发布替代模板。

## 测试和构建

后端：

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\alembic.exe current
```

前端：

```powershell
Set-Location frontend
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run build
```

后端运行时可以重新生成前端 OpenAPI 类型：

```powershell
npm.cmd run api:generate
```

## 数据与隐私边界

- 文献、报告和检索结果按用户隔离；
- API Key 不下发浏览器，不在响应中返回明文；
- 使用外部 LLM 或 Embedding 时，相关文本会发送给管理员配置的第三方服务；
- 第三方是否保存请求取决于相应供应商的隐私和日志政策；
- 应用自身不持久化学术助手的聊天记录；
- 日志不得记录密码、Token、API Key 或完整私有文献正文；
- 本地相似度检测只比较用户选择的私有知识库，不代表权威论文查重结果。

## 当前边界

- PDF 必须包含可提取的文本层，扫描件暂不执行 OCR；
- 不接入公网论文库，不宣称提供权威查重率；
- 学术助手不是连续多轮聊天，每次请求只携带当前报告上下文和本次检索证据；
- 参考文献元数据不完整时拒绝导出，不允许大模型猜测作者、年份或来源；
- 当前 Compose 只启动 PostgreSQL，前端、API 和长任务仍在本机进程中运行；
- 正式公网部署前仍需配置 HTTPS、持久化文件、生产密钥、备份和独立任务 Worker。

## 常见问题

### 数据库启动失败

确认 Docker Desktop 已运行，然后执行：

```powershell
docker compose -p wenyuan ps
docker compose -p wenyuan logs db
```

### 页面能够打开，但 AI 只摘取证据

这是没有可用外部 LLM 时的离线模式。管理员需要启用包含 Base URL、API Key 和模型名称的 LLM 预设，或者配置 `backend/.env`。

### 邮件验证码无法发送

检查 SMTP 配置、端口、TLS 设置和服务商应用专用密码。未配置邮件服务时，后端会返回 `EMAIL_NOT_CONFIGURED`。

### DOCX 导出提示参考文献不完整

在知识库文献列表中补充作者、参考文献标题、出版年份和来源，然后重新执行引用完整性检查。

### 普通用户无法进入管理控制台

确认已运行管理员赋权脚本，并退出后重新登录，使新的角色进入访问令牌。
