# Multi-Agent 系统 — 面试必备知识手册

> 基于 SmartRoute 项目实战讲解，面试时可以直接引用。

---

## 一、什么是 Multi-Agent？

### 1.1 核心定义

**Agent（智能体）** = 能自主决策、执行任务的软件实体

**Multi-Agent（多智能体）** = 多个 Agent 协作完成复杂任务

### 1.2 类比理解

| 场景 | 单 Agent | Multi-Agent |
|------|---------|-------------|
| **餐厅** | 一个服务员又点菜又做饭又收银 | 点餐员 + 厨师 + 收银员分工协作 |
| **医院** | 一个医生既诊断又开药又手术 | 分诊医生 + 专科医生 + 药剂师协作 |
| **SmartRoute** | 一个函数做所有事 | 意图解析 + POI 检索 + 路线规划分工 |

---

## 二、为什么需要 Multi-Agent？

### 2.1 单 Agent 的问题

```python
# 单 Agent 做法（所有逻辑堆在一起）
def plan_route(query):
    # 1000 行代码...
    intent = parse_intent(query)      # 意图解析
    pois = search_pois(intent)        # POI 搜索
    route = optimize_route(pois)      # 路线优化
    return route
```

**问题：**
- ❌ 代码耦合，改一个地方影响全局
- ❌ 无法独立测试每个环节
- ❌ 难以替换某个模块（比如换搜索算法）
- ❌ 职责不清晰，新人难以上手

### 2.2 Multi-Agent 的优势

```python
# Multi-Agent 做法（SmartRoute 实际代码）
class IntentParserAgent:        # 只负责意图解析
    def parse(self, query) -> ParsedIntent: ...

class POIRetrieverAgent:        # 只负责 POI 检索
    def retrieve(self, intent) -> list[POI]: ...

class RoutePlannerAgent:        # 只负责路线规划
    def plan(self, intent, pois) -> list[Route]: ...

# 编排
def plan_route(query):
    intent = intent_parser.parse(query)      # Agent 1
    pois = poi_retriever.retrieve(intent)    # Agent 2
    routes = route_planner.plan(intent, pois) # Agent 3
    return routes
```

**优势：**
- ✅ 职责清晰，每个 Agent 只做一件事
- ✅ 可独立测试（Mock 其他 Agent）
- ✅ 易于替换（比如把 POIRetriever 从本地检索换成高德 API）
- ✅ 易于扩展（加新 Agent 不影响旧的）

---

## 三、Multi-Agent 的三种架构模式

### 3.1 Pipeline（流水线）⭐ SmartRoute 用的这个

```
输入 → Agent A → Agent B → Agent C → 输出
```

**特点：**
- 顺序执行，每个 Agent 的输出是下一个的输入
- 简单清晰，适合任务可分解的场景
- 易于调试（看哪个环节出问题）

**SmartRoute 示例：**
```
用户 query → IntentParser → POIRetriever → RoutePlanner → 路线结果
```

**面试回答模板：**
> "我的 SmartRoute 项目用的是 Pipeline 模式。用户输入自然语言，先经过 IntentParserAgent 解析出结构化意图（城市、时间、预算等），然后 POIRetrieverAgent 根据意图召回候选 POI，最后 RoutePlannerAgent 用贪心 TSP 算法生成路线。每个 Agent 独立测试，通过接口协作。"

---

### 3.2 Router（路由）

```
输入 → Router Agent → 决定调用哪个 Agent → 输出
```

**特点：**
- 一个 Router Agent 根据输入决定调用哪个专业 Agent
- 适合有多种任务类型的场景

**示例：**
```python
class RouterAgent:
    def route(self, query):
        if "路线" in query:
            return route_planner_agent
        elif "推荐" in query:
            return recommender_agent
        elif "天气" in query:
            return weather_agent
```

**面试回答模板：**
> "Router 模式适合任务类型多样的场景。比如用户可能问路线、问天气、问推荐，Router Agent 根据意图分类，路由到对应的专业 Agent 处理。"

---

### 3.3 Collaborative（协作）

```
Agent A ←→ Agent B ←→ Agent C（并行/迭代）
```

**特点：**
- 多个 Agent 并行工作或迭代讨论
- 适合需要多视角、多轮讨论的复杂任务
- 实现复杂，通常用 LangGraph/CrewAI 框架

**示例：**
```python
# 多个 Agent 并行研究，汇总结果
results = parallel([
    researcher_agent.search(query),
    analyst_agent.analyze(query),
    writer_agent.draft(query)
])
final = synthesizer_agent.synthesize(results)
```

**面试回答模板：**
> "协作模式适合复杂任务，比如医疗诊断需要影像 Agent、检验 Agent、临床 Agent 共同讨论。但实现复杂度高，通常用 LangGraph 框架管理状态和消息传递。"

---

## 四、Multi-Agent 的关键组件

### 4.1 Agent 本身

每个 Agent 包含：
- **System Prompt**：定义 Agent 的角色和能力
- **Tools**：Agent 可以调用的工具（API、数据库等）
- **Memory**：Agent 的记忆（短期/长期）

```python
class IntentParserAgent:
    def __init__(self):
        self.system_prompt = "你是意图解析专家..."
        self.llm = DeepSeekLLM()  # 工具：LLM
    
    def parse(self, query):
        # 用 LLM 解析意图
        return self.llm.chat(self.system_prompt, query)
```

### 4.2 编排器（Orchestrator）

负责协调多个 Agent 的执行顺序：

```python
class Orchestrator:
    def __init__(self):
        self.agents = {
            "intent": IntentParserAgent(),
            "poi": POIRetrieverAgent(),
            "planner": RoutePlannerAgent(),
        }
    
    def run(self, query):
        intent = self.agents["intent"].parse(query)
        pois = self.agents["poi"].retrieve(intent)
        routes = self.agents["planner"].plan(intent, pois)
        return routes
```

### 4.3 消息传递（Message Passing）

Agent 之间通过消息传递信息：

```python
# 消息格式
message = {
    "from": "IntentParserAgent",
    "to": "POIRetrieverAgent",
    "content": {
        "city": "深圳",
        "duration": 3,
        "budget": 200,
        "preferences": ["咖啡", "景点"]
    }
}
```

---

## 五、Multi-Agent vs 单 Agent vs 普通函数

| 维度 | 普通函数 | 单 Agent | Multi-Agent |
|------|---------|---------|-------------|
| **复杂度** | 低 | 中 | 高 |
| **可维护性** | 差（耦合） | 中 | 好（解耦） |
| **可测试性** | 差 | 中 | 好（独立测试） |
| **可扩展性** | 差 | 中 | 好（加新 Agent） |
| **适用场景** | 简单任务 | 单一复杂任务 | 多步骤复杂任务 |
| **实现成本** | 低 | 中 | 高 |

**面试回答模板：**
> "Multi-Agent 不是银弹，适合任务可分解、需要独立测试和扩展的场景。简单任务用普通函数就够了，单一复杂任务用单 Agent，只有多步骤、多角色的复杂任务才需要 Multi-Agent。"

---

## 六、主流 Multi-Agent 框架

### 6.1 LangGraph

**特点：**
- 基于 LangChain，用图结构编排 Agent
- 支持状态管理、循环、条件分支
- 适合复杂工作流

**示例：**
```python
from langgraph.graph import StateGraph

graph = StateGraph(State)
graph.add_node("intent", intent_agent)
graph.add_node("poi", poi_agent)
graph.add_node("planner", planner_agent)
graph.set_entry_point("intent")
graph.add_edge("intent", "poi")
graph.add_edge("poi", "planner")
```

### 6.2 CrewAI

**特点：**
- 角色扮演式 Multi-Agent
- 定义 Agent 的 Role、Goal、Backstory
- API 简单，快速开发

**示例：**
```python
from crewai import Agent, Task, Crew

researcher = Agent(role="研究员", goal="搜索信息")
writer = Agent(role="作家", goal="撰写报告")

task = Task(description="研究并撰写报告", agents=[researcher, writer])
crew = Crew(agents=[researcher, writer], tasks=[task])
crew.kickoff()
```

### 6.3 SmartRoute（你的项目）

**特点：**
- 轻量级，无框架依赖
- 纯 Python 类实现
- 适合学习和小项目

**示例：**
```python
# 就是普通的 Python 类 + 顺序调用
agents = Agents(
    intent_parser=IntentParserAgent(),
    poi_retriever=POIRetrieverAgent(),
    route_planner=RoutePlannerAgent(),
)
intent = agents.intent_parser.parse(query)
pois = agents.poi_retriever.retrieve(intent)
routes = agents.route_planner.plan(intent, pois)
```

---

## 七、面试常见问题 & 回答

### Q1: 你的 Multi-Agent 是怎么实现的？

**回答：**
> "我的 SmartRoute 项目用的是 Pipeline 模式。定义了 4 个 Agent：RouteIntentRouter 负责判断是否调起路线规划，IntentParser 负责解析自然语言意图，POIRetriever 负责召回候选 POI，RoutePlanner 负责生成路线。每个 Agent 是独立的 Python 类，通过接口协作。编排逻辑在 FastAPI 的 `/api/plan` 端点里，按顺序调用各 Agent。"

### Q2: 为什么用 Multi-Agent 而不是单 Agent？

**回答：**
> "三个原因：第一，职责分离，每个 Agent 只做一件事，代码清晰；第二，可独立测试，比如测试 IntentParser 时 Mock 其他 Agent；第三，易于扩展，比如后来加了 SafetyReviewer Agent 拦截高风险操作，不影响原有流程。"

### Q3: Agent 之间怎么通信？

**回答：**
> "SmartRoute 用的是直接函数调用，因为 Agent 都在同一个进程内。Agent 的输出是 Pydantic 模型（比如 ParsedIntent），作为下一个 Agent 的输入。如果是分布式场景，可以用消息队列（RabbitMQ）或 HTTP API 通信。"

### Q4: 如果某个 Agent 失败了怎么办？

**回答：**
> "SmartRoute 有兜底机制。比如 IntentParser 优先用 DeepSeek LLM，如果 API 不可用就降级为规则解析。POIRetriever 优先用高德 API，失败后用本地 RAG 兜底。每个 Agent 都有 fallback 策略，保证系统可用性。"

### Q5: Multi-Agent 有什么缺点？

**回答：**
> "三个缺点：第一，实现复杂度高，需要设计 Agent 接口和消息格式；第二，调试困难，需要 Trace 机制追踪每个 Agent 的输入输出；第三，性能开销，多个 Agent 串行调用会增加延迟。所以简单任务不建议用 Multi-Agent。"

### Q6: 你知道哪些 Multi-Agent 框架？

**回答：**
> "主流的有 LangGraph 和 CrewAI。LangGraph 基于图结构，适合复杂工作流；CrewAI 基于角色扮演，API 简单。我的 SmartRoute 是轻量级实现，没依赖框架，适合学习。如果项目复杂了，会考虑用 LangGraph 管理状态和循环。"

### Q7: 你的 Agent 有记忆吗？

**回答：**
> "SmartRoute 的 UserProfileManager 就是长期记忆，存储用户偏好和历史反馈。每次规划路线时会读取用户画像，影响 POI 召回和路线排序。短期记忆是对话上下文，目前没实现多轮对话，如果需要可以加。"

---

## 八、一句话总结

**Multi-Agent 就是把复杂任务拆成多个子任务，每个子任务由一个 Agent（类）负责，Agent 之间按顺序（或并行）协作，每个 Agent 可独立测试、替换、扩展。**

---

## 九、推荐学习资源

1. **LangGraph 官方文档**：https://langchain-ai.github.io/langgraph/
2. **CrewAI 官方文档**：https://docs.crewai.com/
3. **知乎：Multi-Agent 核心架构详解**：https://zhuanlan.zhihu.com/p/1986207024686584136
4. **Google Codelab：Multi-Agent 实战**：https://codelabs.developers.google.com/next26/scale-agents

---

*最后更新：2026-08-27*
