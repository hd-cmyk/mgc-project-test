# TCR Agent Prototype

TCR Agent 是一个具备“规划—执行—自愈”闭环的自动化测试智能体，并提供适合课程答辩和现场演示的 Web 控制台。

```text
代码输入
  -> ExecutionPlanner: 生成真实执行计划
  -> TestAgent: 运行测试、语法/合规检查、可选 AI 代码审查
  -> ReportAgent: 汇总问题并判断是否需要修复
  -> FixAgent: 在临时 workspace 执行确定性修复
  -> VerifyAgent: 回归测试并验证修复
```

当前 LangGraph 流程：

```text
START -> TestAgent -> ReportAgent -> maybe FixAgent -> maybe VerifyAgent -> END
```

## Web GUI

启动专业演示控制台：

```bash
.venv/bin/python web.py
```

`web.py` 会优先启动 FastAPI + uvicorn；如果当前离线环境尚未安装这两个依赖，会自动使用具备相同 API 的 Python 标准库服务器，保证 Demo 仍可运行。代码编辑器资源使用 CodeMirror CDN，现场演示前建议确认浏览器可访问 CDN 或提前缓存资源。

浏览器访问：

```text
http://127.0.0.1:8000
```

控制台提供：

- CodeMirror Python 工作区，支持增删、改名、上传和问题行跳转。
- AI 审查、LLM 报告增强、Auto Fix、超时和测试命令配置。
- 由真实 `ExecutionPlanner` 和 LangGraph 节点更新驱动的任务进度。
- 结构化问题清单、测试/合规日志、修复 patch 与回归验证结果。
- 内存任务记录与轮询接口，不需要数据库。

主要接口：

```text
GET  /api/health
GET  /api/example
POST /api/plan
POST /api/runs
GET  /api/runs/{task_id}
```

## 已实现功能

- `TestAgent`
  - 将输入代码写入临时沙箱目录。
  - 自动运行 Python 测试，优先使用 `pytest`，否则回退到 `unittest`。
  - 执行 `py_compile` 语法/合规检查。
  - 可选调用大模型做 AI 代码审查，结果作为 `llm_review` 合规检查输出。

- `ReportAgent`
  - 读取 `TestAgent` 的测试失败、合规问题、AI 审查问题。
  - 生成统一的 `issues` 报告。
  - 可选再次调用大模型，对报告进行摘要、归因和修复建议增强。

- `LLMGateway`
  - 支持 OpenAI-compatible `/chat/completions` 接口。
  - 支持 DeepSeek 或公司内部兼容 OpenAI 格式的大模型网关。
  - 支持 `.env` 配置。

- 入口方式
  - 支持 Project JSON 输入。
  - 支持直接传入现成 `.py` 源码文件和测试文件。
  - 支持根目录 `run.py` 一键启动。

## 项目结构

```text
.
  run.py                              根目录启动入口
  pyproject.toml                      运行依赖与项目配置
  .env.example                        LLM 网关配置模板
  examples/python_bug/
    main.py                           示例源码，故意包含 bug
    test_main.py                      示例测试
    project.json                      JSON 输入示例
    project_ai_review.json            开启 AI 审查的 JSON 输入示例
  src/tcr_agent/
    cli.py                            CLI 参数解析
    graph.py                          LangGraph 编排
    schemas.py                        Agent 输入输出字段定义
    tools.py                          本地沙箱、测试和合规工具
    llm_gateway.py                    大模型网关
    agents/test_agent.py              TestAgent
    agents/report_agent.py            ReportAgent
    agents/ai_code_review.py          AI 代码审查检查项
    templates/ai_code_review_system.md AI 审查 prompt 模板
```

## 环境安装

推荐 Python 3.12。

```bash
cd "/Users/jianghj59/Documents/mgc project"

python3.12 -m venv .venv
source .venv/bin/activate

pip install -e ".[dev]"
```

如果已经有 `.venv`，直接激活即可：

```bash
source .venv/bin/activate
```

运行单元测试：

```bash
python -m unittest tests/test_test_agent.py tests/test_llm_gateway.py tests/test_report_agent.py
```

## LLM 网关配置

复制配置模板：

```bash
cp .env.example .env
```

示例配置：

```bash
LLM_GATEWAY_BASE_URL=https://api.deepseek.com
LLM_GATEWAY_API_KEY=your-api-key
LLM_GATEWAY_MODEL=deepseek-v4-pro
LLM_GATEWAY_TIMEOUT_SECONDS=60
LLM_GATEWAY_AUTH_HEADER=authorization
LLM_GATEWAY_VERIFY_SSL=true
LLM_GATEWAY_EXTRA_HEADERS_JSON={}
```

`LLM_GATEWAY_BASE_URL` 可以是：

```text
https://api.deepseek.com
https://api.deepseek.com/v1
https://your-company-gateway/v1
```

程序会自动拼接 `/chat/completions`。如果你的 URL 已经以 `/chat/completions` 结尾，也可以直接使用完整地址。

如果公司网络代理注入了自签名证书，可能会出现：

```text
CERTIFICATE_VERIFY_FAILED: self-signed certificate in certificate chain
```

临时测试可以设置：

```bash
LLM_GATEWAY_VERIFY_SSL=false
```

长期建议把公司 CA 证书安装到系统或 Python/OpenSSL 信任链中。

## 使用方法

### 1. 使用现成 JSON 输入

不启用 AI 审查：

```bash
python run.py --input examples/python_bug/project.json
```

启用 AI 审查：

```bash
python run.py --input examples/python_bug/project_ai_review.json
```

### 2. 直接传入 Python 源码和测试文件

只运行测试、合规检查和本地报告：

```bash
python run.py \
  --code examples/python_bug/main.py \
  --test examples/python_bug/test_main.py \
  --no-report-llm
```

运行完整代码审查任务：

```bash
python run.py \
  --code examples/python_bug/main.py \
  --test examples/python_bug/test_main.py \
  --ai-review
```

这个命令会执行：

```text
pytest 测试
py_compile 合规检查
llm_review AI 代码审查
ReportAgent LLM 报告增强
```

### 3. 只调用一次大模型

如果你只想让 `TestAgent` 做 AI 代码审查，不想让 `ReportAgent` 再调用一次大模型：

```bash
python run.py \
  --code examples/python_bug/main.py \
  --test examples/python_bug/test_main.py \
  --ai-review \
  --no-report-llm
```

### 4. 保存结果

```bash
python run.py \
  --code examples/python_bug/main.py \
  --test examples/python_bug/test_main.py \
  --ai-review > full_review_result.json
```

## 示例测试用例

示例代码：

```python
def add(a, b):
    return a - b
```

示例测试：

```python
self.assertEqual(add(1, 2), 3)
```

预期结果：

- `pytest` 失败，因为实际结果是 `-1`。
- `py_compile` 通过，因为语法没有问题。
- 开启 `--ai-review` 后，`llm_review` 会识别 `return a - b` 是逻辑错误。
- `ReportAgent` 会汇总出来自 `pytest` 和 `llm_review` 的问题。

## 输出字段说明

最终输出是一个 JSON object，主要字段如下：

```text
test_result
  TestAgent 输出

test_result.test_results
  测试执行结果，例如 pytest/unittest

test_result.compliance_results
  合规检查结果，例如 py_compile、llm_review

report_result
  ReportAgent 输出

report_result.issues
  统一问题列表，包含 issue_id、source、severity、evidence、root_cause、recommendation

report_result.warnings
  非致命告警，例如 LLM 调用失败后回退到本地报告
```

`llm_review` 的结果位于：

```text
test_result.compliance_results 中 tool = "llm_review" 的对象
```

如果 `llm_review.status = failed`，说明 AI 审查发现了 `critical` 或 `high` 问题。

如果 `report_result.llm_used = true`，说明 ReportAgent 成功调用了大模型做报告增强。

## 当前限制

- 目前主要支持 Python 文件。
- 当前 FixAgent 使用面向课程 Demo 的确定性修复规则，修改仅发生在临时 workspace。
- AI 审查默认关闭，必须通过 `--ai-review` 或 JSON 配置显式开启。
- `ruff`、`semgrep` 目前仅预留为合规工具扩展点，MVP 中未完整实现。
