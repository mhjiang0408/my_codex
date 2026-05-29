---
name: paper-writing
description: Paper writing spec for ai papers
---
# 通用 AI 论文撰写 Spec

> 适用范围：机器学习、LLM、agent、benchmark、dataset、systems、post-training、test-time adaptation、alignment、code intelligence 等 AI 论文。  
> 重点覆盖：章节顺序、定理/图表密度、句子节奏、逻辑连接结构、引用风格、wording 和常用句式。

---

## 0. 总原则：论文不是“方法说明书”，而是“一个可验证主张的证明过程”

### 为什么要这么写

AI 论文的核心任务不是展示作者做了多少模块，而是让读者相信一个中心主张：

> 在某个重要问题设定下，一个新的思想、方法、数据、benchmark、objective 或分析维度确实解决了已有瓶颈。

好的论文通常只围绕一个中心对象展开，例如：

- 一个新 setting；
- 一个新 objective；
- 一个新 benchmark；
- 一个新 scaling dimension；
- 一个新 data construction paradigm；
- 一个新 training / inference mechanism；
- 一个新 system bottleneck 的解决方案。

如果论文同时强调太多对象，读者会不知道该记住什么，reviewer 也很难判断贡献边界。

### 具体应该怎么写

全文每一节都应该回答同一个问题：

```text
This section supports which part of the central claim?
```

推荐主线：

```text
Problem shift
→ Bottleneck
→ Key observation
→ Proposed object
→ Mechanism
→ Evidence
→ Boundary / limitation
```

不要写成：

```text
We built module A.
We built module B.
We built module C.
All modules are useful.
```

要写成：

```text
The field is moving from <old setting> to <new setting>.
This exposes <bottleneck>.
We observe that <key opportunity>.
We propose <method/object>, which addresses the bottleneck by <core mechanism>.
Experiments show <main empirical claim>.
Analysis further shows <why the method works and where it works best>.
```

---

## 1. 章节顺序 Spec

### 1.1 默认章节顺序：problem-first，而不是 method-first

#### 为什么要这么写

读者需要先理解 failure mode，才会关心方法。很多 AI 论文的问题是过早介绍 pipeline，导致方法看起来像“作者想做的工程组合”，而不是“问题自然推出的设计”。

#### 具体应该怎么写

经验型 AI method paper 推荐顺序：

```text
1. Introduction
2. Related Work
3. Problem Setting / Preliminaries
4. Method
5. Experiments
   5.1 Setup
   5.2 Main Results
   5.3 Ablations
   5.4 Scaling / Robustness / Transfer Analysis
   5.5 Fine-Grained or Mechanistic Analysis
6. Limitations
7. Conclusion
```

Benchmark / dataset paper 推荐顺序：

```text
1. Introduction
2. Related Work
3. Benchmark / Dataset Construction
4. Evaluation Protocol
5. Baseline Results
6. Analysis
   6.1 Difficulty / Coverage
   6.2 Contamination / Freshness / Validity
   6.3 Human or Automatic Validation
7. Limitations
8. Conclusion
```

Theory-heavy paper 推荐顺序：

```text
1. Introduction
2. Related Work
3. Problem Setup
4. Main Theoretical Results
5. Proof Sketch / Intuition
6. Algorithmic or Empirical Consequences
7. Experiments, if applicable
8. Limitations and Discussion
```

Systems paper 推荐顺序：

```text
1. Introduction
2. Related Work
3. System Overview
4. Design Challenges
5. System Components
6. Validation / Evaluation
7. Scaling / Cost / Reliability Analysis
8. Limitations
9. Conclusion
```

---

### 1.2 Introduction 使用“五段式漏斗结构”

#### 为什么要这么写

Introduction 的目标是让读者接受：

1. 这个问题重要；
2. 现有方法不够；
3. 你的切入点自然；
4. 你的方法正好解决这个问题；
5. 你的实验确实验证了这个主张。

#### 具体应该怎么写

```text
Paragraph 1: Field shift
Paragraph 2: Bottleneck
Paragraph 3: Key observation / opportunity
Paragraph 4: Method overview
Paragraph 5: Findings and contributions
```

##### Paragraph 1: Field shift

写领域正在从什么走向什么。

```latex
Recent advances in <field/system> have shifted <task> from <old setting>
toward <new setting>.
Unlike <old setting>, <new setting> requires models to <capability list>.
This shift makes <new requirement> a central bottleneck.
```

好的句式：

```latex
As <systems/models> move from <A> to <B>, the training and evaluation objectives must also change.
```

```latex
Unlike <traditional task>, <new task> requires <persistent capability> rather than <localized capability>.
```

避免：

```latex
Recently, large language models have achieved great success in many domains.
```

这类句子太泛，信息密度低，除非下一句立刻进入具体 setting。

##### Paragraph 2: Bottleneck

解释为什么现有方法不能解决新问题。

```latex
However, existing <methods/data/benchmarks> primarily <what they do>,
which limits their ability to <desired capability>.
In particular, they often <failure mode 1>, <failure mode 2>, or <failure mode 3>.
```

关键是写清楚：不是“别人不够好”，而是“旧范式和新需求之间存在结构性错配”。

推荐句式：

```latex
While <prior approach> provides <benefit>, it still compresses <important process>
into <insufficient representation>.
```

```latex
This creates a mismatch between <what models are trained/evaluated on>
and <what deployment actually requires>.
```

##### Paragraph 3: Key observation / opportunity

提出你的核心观察。

```latex
A natural opportunity is <observation>.
Although <resource/signal/phenomenon> is abundant, it is not directly usable because <noise/risk>.
This raises the question: can <raw resource> be converted into <useful signal>?
```

好的问题句：

```latex
This raises a natural question: can <source of signal> be filtered, organized, or scaled into <desired supervision/evaluation>?
```

注意：问题句不要太多，1--2 个足够，而且必须和后面的实验设计对应。

##### Paragraph 4: Method overview

只写核心机制，不写实现细节。

```latex
We introduce <Name>, a <framework/method/benchmark> for <goal>.
<Name> builds on <key observation> and introduces <mechanism 1> and <mechanism 2>.
The goal is not merely to <shallow goal>, but to <deeper goal>.
```

推荐句式：

```latex
The goal of <Name> is not simply to <surface-level action>, but to <core scientific objective>.
```

```latex
Unlike <prior methods>, <Name> preserves/controls/exposes <critical signal>.
```

##### Paragraph 5: Findings and contributions

先写主要发现，再列 contributions。

```latex
Our experiments show that <main result>.
Further analysis reveals that <mechanistic finding>.
Together, these results suggest that <central claim>.
```

Contribution 需要写成可验证主张，而不是模块清单。

```latex
Our contributions are:
\begin{itemize}
    \item We introduce <Name>, a <method/benchmark/framework> that <core function>.
    \item We show that <empirical claim>, using <controlled setup>.
    \item We analyze <dimension/mechanism>, demonstrating that <deeper finding>.
\end{itemize}
```

避免：

```latex
We propose module A.
We propose module B.
We conduct experiments.
```

更好：

```latex
We identify <dimension> as a scaling/evaluation/training axis and show that it predicts <capability>.
```

---

## 2. Abstract Spec：5--6 句完成完整论文叙事

### 为什么要这么写

Abstract 是 reviewer 对论文的第一印象。它不应该是背景堆叠，也不应该是结果列表。好的 abstract 通常在 5--6 句内完成：问题、缺口、方法、机制、结果、意义。

### 具体应该怎么写

#### 推荐结构

```text
Sentence 1: Field trend / problem setting
Sentence 2: Bottleneck / gap
Sentence 3: Method / object introduced
Sentence 4: Key mechanism or design
Sentence 5: Main empirical or theoretical result
Sentence 6: Broader implication or scope
```

#### 模板

```latex
Recent progress in <field> has shifted <old paradigm> toward <new paradigm>,
where models must <capability 1>, <capability 2>, and <capability 3>.

However, existing <datasets/methods/benchmarks/training objectives> remain limited by
<bottleneck>, making it difficult to <desired outcome>.

In this work, we introduce <Name>, a <method/benchmark/framework> for <task/setting>.

<Name> addresses this challenge by <mechanism 1> and <mechanism 2>, enabling <core benefit>.

Experiments on <benchmarks/settings> show that <Name> <main result>,
with the largest gains on <where the mechanism should matter most>.

These results suggest that <central implication>, providing a path toward <broader goal>.
```

#### 注意事项

- 第一句要尽快进入具体 problem setting。
- Abstract 中的每个 claim 都应该能在正文某个表、图或分析中找到证据。
- 不要在 abstract 里提出正文没有验证的宏大结论。
- 不要写 “extensive experiments demonstrate the superiority of our method” 这类泛泛表述。

---

## 3. Related Work Spec：不要堆文献，要构造“问题地图”

### 为什么要这么写

Related Work 的目标不是证明作者读了很多论文，而是让 reader 知道：

- 这个领域有哪些路线；
- 每条路线解决什么；
- 每条路线留下什么 gap；
- 你的工作位于哪里。

### 具体应该怎么写

#### 推荐结构

```text
2.1 Prior work on the general area
2.2 Prior work on the specific bottleneck
2.3 Prior work closest to your method
2.4 Positioning sentence
```

#### 每段内部结构

```latex
<Line of work> studies <problem>.
Representative methods include <A>, <B>, and <C>.
These methods improve <capability>, but they typically assume <assumption>
or focus on <narrower setting>.
In contrast, our work <difference>.
```

#### 好的 positioning 句式

```latex
Our work is complementary to <prior line>: rather than improving <their axis>, we study <your axis>.
```

```latex
In contrast to methods that <prior focus>, we focus on <your focus>.
```

```latex
These works establish <important background>, but leave open whether <your question>.
```

#### 引用规范

- citation 放在 claim 句末尾；
- 不要每个名词后都挂 citation；
- 同一类工作可以合并引用；
- closest prior work 要单独讨论，不能藏在一串 citation 里。

避免：

```latex
A studies X. B studies Y. C studies Z. D studies W.
```

更好：

```latex
Prior work can be grouped into three directions: <A>, <B>, and <C>.
The first direction improves <aspect>, while the second focuses on <aspect>.
However, these methods do not directly address <your gap>.
```

---

## 4. Formalism / Theory Spec：公式要定义核心对象，不要装饰性形式化

### 为什么要这么写

AI 论文中的公式应该降低歧义，而不是增加负担。如果公式没有被后文使用，或者只是把文字换成符号，它会削弱论文可读性。

### 具体应该怎么写

#### 经验型 AI 论文

一般保留 2--5 个核心公式即可：

- problem setting；
- model input/output；
- objective；
- selection / filtering criterion；
- evaluation metric。

模板：

```latex
We model each instance as $x = (c, q, y)$, where $c$ denotes <context>,
$q$ denotes <query>, and $y$ denotes <target output>.
```

```latex
The training objective is
\[
\mathcal{L}(\theta) = \mathbb{E}_{(x,y)\sim\mathcal{D}}
[-\log p_\theta(y|x)].
\]
```

```latex
We accept an instance if
\[
s(x,y) \geq \tau,
\]
where $s$ measures <quality dimension> and $\tau$ is a fixed threshold.
```

#### 理论型 AI 论文

如果有 theorem：

- theorem 前必须定义 setting 和 assumptions；
- theorem statement 不要太长；
- theorem 后写 intuition；
- proof sketch 可以在正文，完整 proof 放 appendix。

模板：

```latex
\begin{assumption}
<Clear condition under which the result holds.>
\end{assumption}

\begin{theorem}
Under Assumption~\ref{...}, <method> guarantees <result>.
\end{theorem}

The theorem shows that <plain-language implication>.
Intuitively, <why the result holds>.
```

#### 避免

```latex
We define many symbols that never appear again.
```

```latex
Theorem 1 claims something that experiments actually support but theory does not prove.
```

---

## 5. 定理、公式、图表密度 Spec

### 为什么要这么写

不同类型的 AI 论文需要不同的 formalism 和图表密度。经验论文中过度形式化会显得装饰性强；理论论文如果 theorem 少或假设不清，则会显得贡献不足。图表也不应该只是“展示更多结果”，而应该承担论证功能。

### 具体应该怎么写

#### 推荐密度

```text
Empirical method paper:
- Theorems: 0
- Definitions: 1--3
- Equations: 2--6
- Algorithms: 0--1
- Figures/Tables in main paper: 5--10

Benchmark / dataset paper:
- Theorems: 0
- Definitions: 1--2
- Equations: 0--4
- Tables/Figures: 6--12

Theory paper:
- Theorems: 2--5 major results
- Lemmas: only when needed for proof structure
- Proof sketches: main paper
- Full proofs: appendix
- Empirical figures: optional, only if they clarify implications

Systems paper:
- Theorems: 0
- Equations: only for metrics/cost/scaling
- System diagrams: 1--2
- Reliability/cost/scaling tables: 2--5
```

#### 总规则

```text
A theorem must correspond to a claim in the abstract or introduction.
An equation must define an object used later.
A table must answer a comparison question.
A figure must support one visual claim.
```

---

## 6. Method Spec：每个模块必须对应一个 failure mode

### 为什么要这么写

复杂 AI 系统论文容易变成工程清单。更好的写法是：先指出 failure mode，再给 design choice，最后说明它为什么解决问题。

### 具体应该怎么写

#### Section opening

```latex
<Name> consists of three components: <A>, <B>, and <C>.
Each component addresses a specific failure mode in <problem setting>.
Figure~\ref{fig:method} provides an overview.
```

#### 每个模块的三句式

```latex
A common failure mode is <failure>.
To address this, we <design choice>.
This enables <benefit> and prevents <undesired behavior>.
```

#### 示例句式

```latex
A key challenge is that <signal> is unavailable or unreliable.
We therefore introduce <module>, which approximates/recovers/filters <signal>.
This provides <model/system> with <useful information> without assuming <strong assumption>.
```

```latex
Naively applying <operation> can lead to <problem>.
We avoid this by <constraint/design>.
This keeps <property> stable across <stages/settings>.
```

#### Method 中不要过早写结果

不推荐：

```latex
This module significantly improves performance.
```

推荐：

```latex
This module is designed to preserve <property>, which we evaluate in Section~\ref{sec:analysis}.
```

---

## 7. Experiment Spec：实验不是“跑 benchmark”，而是回答 research questions

### 为什么要这么写

实验部分应该服务于 Introduction 中提出的问题。每张表、每个 ablation、每个 benchmark 都要对应一个 claim。

### 具体应该怎么写

#### Experiment section opening

```latex
We evaluate <Name> along three questions:
(1) Does <method> improve over strong baselines?
(2) Which component contributes to the gain?
(3) Under what conditions does the method work best?
```

#### Setup 写法

```latex
\paragraph{Baselines.}
We compare against <baseline categories>.
These baselines cover <reason>, allowing us to test whether <claim>.
```

```latex
\paragraph{Benchmarks.}
We evaluate on <benchmarks>.
These benchmarks measure <capability 1>, <capability 2>, and <capability 3>.
```

```latex
\paragraph{Implementation details.}
Unless otherwise specified, all models are trained with <setting>.
We keep <controlled variable> fixed to isolate the effect of <factor>.
```

#### Main results 写法

```latex
The results in Table~\ref{tab:main} show that <main claim>.
Compared with <strong baseline>, <method> improves <metric> by <amount>.
The gain is largest on <benchmark/category>, where success requires <capability>.
In contrast, gains are smaller on <benchmark/category>, suggesting that <boundary>.
```

不要逐行读表：

```latex
On dataset A, method gets 70.1. On dataset B, method gets 55.2.
On dataset C, method gets 61.3.
```

要解释 pattern：

```latex
The improvement is concentrated on tasks that require <mechanism-relevant capability>,
while localized tasks show smaller changes.
This pattern supports our interpretation that <method> primarily improves <capability>.
```

---

## 8. Ablation / Analysis Spec：ablation 要证明机制，不只是删模块

### 为什么要这么写

Ablation 的目的不是展示“每个模块都有用”，而是解释：

- 哪个因素导致 gain；
- gain 在哪里出现；
- 哪些条件下方法失效或饱和。

### 具体应该怎么写

#### Ablation paragraph 模板

```latex
Table~\ref{tab:ablation} isolates the effect of <component>.
Removing <component> reduces performance most on <setting>,
where <component-relevant signal> is required.
This suggests that <component> contributes by <mechanism>,
rather than merely increasing model capacity or training tokens.
```

#### Scaling analysis 模板

```latex
We study <factor> as an independent scaling dimension.
All settings keep <budget> fixed, allowing us to isolate <factor>
rather than confounding it with <number of samples/tokens/compute>.
Performance improves on <tasks>, but saturates on <tasks>.
This suggests that <factor> primarily benefits <condition>.
```

#### Fine-grained analysis 模板

```latex
The fine-grained results in Figure~\ref{fig:analysis} show where the gains arise.
<Method> improves most on <category>, which requires <capability>.
The margin is smaller on <category>, suggesting that <capability> is less central there.
```

---

## 9. Figure / Table Spec：每个图表必须承担一个 claim

### 为什么要这么写

图表不是装饰。好的 AI 论文中，每张图表都回答一个具体问题。如果一张图表不能被概括成一句 claim，它通常不该放在正文。

### 具体应该怎么写

#### 推荐图表密度

对于 8--10 页 AI 主文：

- 1 张 overview figure；
- 1 张 main results table；
- 1--2 张 ablation tables；
- 1--3 张 analysis figures；
- 1 张 qualitative case study 可选；
- 其余细节放 appendix。

#### Figure 1

Figure 1 不要只画 pipeline。它应该同时回答：

- 问题是什么；
- 方法解决哪个 bottleneck；
- 为什么这个方法和主张相关。

#### Caption 模板

```latex
\caption{
Effect of <factor> on <capability>.
We vary <controlled variable> while keeping <fixed variable> fixed.
<Main trend>.
This suggests that <interpretation>.
}
```

#### Main result table caption

```latex
\caption{
Main results on <benchmark group>.
<Method> outperforms <baseline category>, with the largest gains on <task type>.
This indicates that <mechanism> is most useful when <condition>.
}
```

#### Ablation table caption

```latex
\caption{
Ablation of <component>.
Removing <component> reduces performance on <setting>, showing that <component>
contributes to <mechanism> rather than only increasing <confound>.
}
```

#### 避免

```latex
\caption{Results on different benchmarks.}
```

更好：

```latex
\caption{
Comparison across long-horizon and localized benchmarks.
<Method> improves most on tasks requiring <capability>, while gains are smaller on <localized setting>.
}
```

---

## 10. Results Analysis Spec：使用“结论先行 → 证据 → 机制 → 边界”

### 为什么要这么写

reviewer 不想看作者复述表格。他们想知道数字支持了什么科学判断。

### 具体应该怎么写

#### 四句式

```latex
The results in <Table/Figure> show that <claim>.
Compared with <baseline>, <method> <evidence>.
This suggests that <mechanism-level explanation>.
In contrast, <weaker result/boundary>, indicating that <scope>.
```

#### 示例

```latex
The results in Table~\ref{tab:main} show that <method> improves performance
primarily on tasks requiring <capability>.
Compared with <baseline>, it achieves the largest gains on <benchmark>,
where models must <task demand>.
This suggests that <mechanism> helps models <behavior>.
In contrast, gains are smaller on <benchmark>, indicating that <method>
is less beneficial when <condition>.
```

#### 避免

- “The result is significant” 但没有 significance test；
- “This proves” 用于 empirical result；
- “Clearly”；
- “Obviously”；
- 没有解释的数字罗列。

推荐替换：

```text
proves → suggests / indicates / provides evidence that
significant → substantial / consistent / statistically significant
very good → strong / competitive / near-best
bad → limited / weaker / less effective
```

---

## 11. Wording Spec：句子节奏要短、中、转折结合

### 为什么要这么写

AI 论文的信息密度高。长句会让逻辑关系不清楚，尤其是在方法和实验分析中。好的句子通常只表达一个因果关系或一个对比关系。

### 具体应该怎么写

#### 推荐句子长度

- 核心判断句：12--18 words；
- 机制解释句：18--28 words；
- 长句最多包含一个从句；
- 避免一个句子里连续出现 4 个以上抽象名词。

#### 好的节奏

```latex
Raw trajectories are abundant but noisy.
Many contain invalid actions, inconsistent states, or unrecoverable failures.
We therefore apply process-aware filtering before training.
This turns raw interaction traces into more reliable supervision.
```

#### 不好的节奏

```latex
Due to the noisy and heterogeneous nature of the raw trajectories and their potential
state inconsistency, invalid actions, and unrecoverable failures, we introduce a filtering
mechanism that can improve the reliability of the data and make it more useful for training.
```

#### 句式原则

- 一句只讲一个 action；
- 先主干，后修饰；
- 先 claim，后原因；
- 少用 “which” 串联太多信息；
- 少用名词化，更多使用动词。

---

## 12. 常用高质量句式模板

### Field shift

```latex
Recent progress in <field> has shifted <task> from <old paradigm> to <new paradigm>.
```

```latex
As <models/systems> become more capable, <evaluation/training/deployment> must account for <new requirement>.
```

```latex
Unlike <old setting>, <new setting> requires <capability> across <condition>.
```

### Bottleneck

```latex
However, existing <methods/data/benchmarks> remain limited by <bottleneck>.
```

```latex
This creates a mismatch between <training/evaluation signal> and <deployment requirement>.
```

```latex
While <prior work> has made progress on <axis>, it still assumes <limiting assumption>.
```

### Method introduction

```latex
We introduce <Name>, a <method/framework/benchmark> for <goal>.
```

```latex
<Name> addresses this challenge by <mechanism 1> and <mechanism 2>.
```

```latex
The key idea is to <core idea>, rather than <surface-level alternative>.
```

### Contrast with prior work

```latex
In contrast to methods that <prior focus>, we focus on <your focus>.
```

```latex
Our work is complementary to <prior line>: rather than <their axis>, we study <your axis>.
```

```latex
Unlike <baseline>, <method> preserves/controls/exposes <critical signal>.
```

### Results

```latex
The results in Table~\ref{tab:main} show that <method> consistently improves <metric>.
```

```latex
The gains are largest on <task>, where <capability> is essential.
```

```latex
The improvement is smaller on <task>, suggesting that <method> is less critical when <condition>.
```

```latex
Together, these results support our interpretation that <mechanism> drives <capability>.
```

### Limitations

```latex
While <method> demonstrates <main finding>, its effectiveness depends on <assumption>.
```

```latex
When <assumption fails>, <failure mode> may occur.
```

```latex
Thus, our results should be interpreted as evidence for <claim under conditions>,
rather than as a guarantee that <overgeneralized claim>.
```

```latex
Future work should <concrete next step>, <second step>, and <broader validation>.
```

---

## 13. Claim Strength Spec：控制语气，避免过度声称

### 为什么要这么写

reviewer 对过度 claim 非常敏感。AI 论文中的实验通常只能支持条件性结论，而不是绝对证明。

### 具体应该怎么写

#### 强 claim 需要满足

- 多个 benchmark；
- 多个 model 或 setting；
- controlled comparison；
- ablation；
- statistical evidence 或 consistent pattern；
- clear limitation。

#### 语气等级

```text
Weak evidence:
"These results suggest that ..."

Moderate evidence:
"These results indicate that ..."

Strong repeated evidence:
"These results demonstrate that ..."

Theoretical proof:
"We prove that ..."
```

#### 不推荐

```latex
This proves that our method solves long-horizon reasoning.
```

#### 推荐

```latex
These results suggest that <method> improves <capability> under <evaluated setting>.
```

```latex
The consistent gains across <settings> provide evidence that <mechanism> contributes to <capability>.
```

---

## 14. Citation Spec：引用要服务逻辑，不要打断句子

### 为什么要这么写

引用的作用是把你的 claim 放进研究脉络中。过多零散引用会降低可读性；过少引用会让贡献定位不清楚。

### 具体应该怎么写

#### 引用放置

推荐：

```latex
Recent benchmarks have shifted evaluation toward <capability>~\cite{a,b,c}.
```

```latex
Prior work has explored <line of work>, but mainly under <setting>~\cite{a,b}.
```

不推荐：

```latex
Recent benchmarks~\cite{a} have shifted~\cite{b} evaluation toward <capability>~\cite{c}.
```

#### Related Work 中的引用组织

按研究路线分组，而不是按论文逐篇介绍：

```latex
A first line of work studies <A>~\cite{...}.
A second line focuses on <B>~\cite{...}.
Closest to our work, <paper> <does X>.
However, it does not address <your gap>.
```

#### 引用原则

- 领域共识：可以一组 citation；
- closest prior：单独解释；
- benchmark / dataset / model：首次出现时引用；
- controversial claim：必须引用；
- 自己的解释：不要伪装成引用结论。

---

## 15. Related Work 的措辞规范

### 为什么要这么写

Related Work 不能显得攻击前人，也不能显得你的工作只是 incremental。应该采用“承认贡献 + 指出未覆盖问题 + 定位自己”的语气。

### 具体应该怎么写

推荐：

```latex
These methods establish <important foundation>, but they primarily focus on <scope>.
Our work addresses a complementary question: <your question>.
```

```latex
While <prior work> improves <capability>, it does not directly study <your dimension>.
```

```latex
Closest to our work is <prior work>, which <summary>.
We differ in <specific difference>, enabling <benefit>.
```

避免：

```latex
Prior work fails to solve this problem.
```

更好：

```latex
Prior work leaves open whether <specific unresolved question>.
```

---

## 16. Method Wording Spec：少用抽象名词，多用可执行动词

### 为什么要这么写

Method 部分要让读者能复现你的方法。抽象名词过多会让方法显得空泛。

### 推荐动词

```text
construct
filter
estimate
optimize
sample
retrieve
align
preserve
compose
update
normalize
route
verify
calibrate
aggregate
decompose
```

### 少用或谨慎使用

```text
leverage
facilitate
enhance
empower
utilize
synergize
robustly improve
significantly boost
```

### 示例

不推荐：

```latex
We leverage a sophisticated filtering strategy to enhance data quality.
```

推荐：

```latex
We filter instances whose validation score falls below a fixed threshold.
```

不推荐：

```latex
The module facilitates better reasoning over complex contexts.
```

推荐：

```latex
The module retrieves task-relevant evidence and appends it to the model input.
```

---

## 17. Experiment Wording Spec：数字后面必须有解释

### 为什么要这么写

实验数字本身不是论文贡献。贡献来自你对数字 pattern 的解释。

### 具体应该怎么写

#### 数字句

```latex
<Method> improves <metric> from <a> to <b>.
```

#### 解释句

```latex
The gain is largest on <setting>, where <mechanism-relevant capability> is required.
```

#### 边界句

```latex
In contrast, <method> provides limited gains on <setting>, suggesting that <condition> is less aligned with <mechanism>.
```

#### 总结句

```latex
This pattern supports the view that <method> improves <specific capability> rather than merely increasing <confound>.
```

---

## 18. Captions Spec：caption 要像 mini-result

### 为什么要这么写

很多 reviewer 会先看图和 caption。caption 应该让 reader 不读正文也能知道图表支持什么结论。

### 具体应该怎么写

#### Figure caption 四要素

```text
1. What is compared?
2. What is controlled?
3. What is the main trend?
4. What does it suggest?
```

#### 模板

```latex
\caption{
Effect of <factor> on <capability>.
We compare <settings> while keeping <control variable> fixed.
<Main trend>.
This suggests that <interpretation>.
}
```

#### Table caption 四要素

```text
1. Evaluation setting
2. Baselines / variants
3. Main result
4. Interpretation
```

#### 模板

```latex
\caption{
Main comparison on <benchmarks>.
<Method> outperforms <baseline category>, especially on <task type>.
The results indicate that <mechanism> is most useful for <condition>.
}
```

---

## 19. Limitations Spec：不要写“道歉清单”，要写“适用边界”

### 为什么要这么写

好的 limitation 会提升可信度。它告诉 reviewer：作者知道方法在什么条件下成立，也知道下一步该怎么做。

### 具体应该怎么写

#### 推荐结构

```text
Sentence 1: Main finding remains valid.
Sentence 2: Key dependency / assumption.
Sentence 3: Failure mode when assumption breaks.
Sentence 4: Scope of interpretation.
Sentence 5: Future work.
```

#### 模板

```latex
\paragraph{Limitations.}
While <method> demonstrates <main result>, its effectiveness still depends on <assumption>.
When <assumption fails>, <failure mode> may occur, which can reduce <desired property>.
Thus, our results should be interpreted as evidence for <claim under evaluated setting>,
rather than as a guarantee that <overgeneralized claim>.
Future work should <concrete improvement>, <broader evaluation>, and <additional safety/robustness check>.
```

#### 避免

```latex
Our method has some limitations. First, it may not work in all cases. Second, more experiments are needed.
```

更好：

```latex
The current evaluation covers <scope>, but does not yet test <uncovered setting>.
This limits our ability to conclude that <method> generalizes to <broader setting>.
```

---

## 20. Conclusion Spec：不要重复 abstract，要回到中心主张

### 为什么要这么写

Conclusion 应该让 reader 带走一个清晰 takeaway。它不是 result summary 的压缩版，而是全文主张的收束。

### 具体应该怎么写

#### 推荐结构

```latex
We presented <Name>, a <method/framework/benchmark> for <problem>.
The key idea is that <central idea>.
Experiments show that <main empirical finding>.
Further analysis indicates that <mechanism-level finding>.
These results suggest <broader implication>.
```

#### 最后一段

可以写 future work，但不要引入新 claim。

```latex
Future work should <improve limitation>, <extend scope>, and <test broader generality>.
```

---

## 21. Appendix Spec：appendix 是补充，不是主证据仓库

### 为什么要这么写

主文必须独立成立。如果支持核心 claim 的关键实验只在 appendix，reviewer 会认为主文证据不足。

### 具体应该怎么写

主文放：

- main results；
- key ablations；
- central analysis；
- essential implementation details；
- limitations。

Appendix 放：

- extra benchmark breakdown；
- hyperparameter details；
- prompt templates；
- additional qualitative cases；
- extended proofs；
- dataset documentation；
- compute details；
- failure examples。

---

## 22. 常见坏句式与改写

### 过泛开头

Bad:

```latex
Large language models have achieved remarkable success in many tasks.
```

Good:

```latex
Large language models are increasingly being deployed in <specific setting>,
where they must <specific capability>.
```

### 模块堆叠

Bad:

```latex
We propose three modules: A, B, and C.
```

Good:

```latex
We identify three failure modes in <setting> and design one mechanism for each.
```

### 过度 claim

Bad:

```latex
This proves that our method has strong reasoning ability.
```

Good:

```latex
This suggests that the method improves reasoning in settings that require <specific behavior>.
```

### 冗长方法句

Bad:

```latex
The module reads the input, contextual information, auxiliary metadata, and logs,
then predicts various possible errors and provides suggestions for improvement.
```

Good:

```latex
Given the input, context, metadata, and logs, the module predicts likely failures and repair directions.
```

### 无解释结果

Bad:

```latex
Our method achieves 65.2, outperforming baseline 61.3.
```

Good:

```latex
Our method improves accuracy from 61.3 to 65.2.
The gain is concentrated on <category>, suggesting that <mechanism> is useful when <condition>.
```

---

## 23. 论文级 Checklist

### Central claim

- [ ] Can the paper be summarized in one sentence?
- [ ] Does every section support that sentence?
- [ ] Is the central object clear: setting, method, benchmark, objective, dataset, or system?

### Abstract

- [ ] Does it contain problem, gap, method, mechanism, result, and implication?
- [ ] Are all claims supported in the paper?
- [ ] Does it avoid unsupported broad claims?

### Introduction

- [ ] Does it explain why the problem is important?
- [ ] Does it identify a structural bottleneck?
- [ ] Does the method naturally follow from the bottleneck?
- [ ] Are contributions written as claims rather than module lists?

### Related Work

- [ ] Is prior work organized by research lines?
- [ ] Is the closest prior work discussed specifically?
- [ ] Is your difference precise rather than vague?
- [ ] Are citations placed where they support claims without breaking sentence flow?

### Method

- [ ] Does each component solve a named failure mode?
- [ ] Are inputs, outputs, objectives, and assumptions clear?
- [ ] Are implementation details sufficient but not distracting?
- [ ] Are formulas used later in the paper?

### Experiments

- [ ] Does each experiment answer a research question?
- [ ] Are baselines strong and fair?
- [ ] Are controlled variables stated?
- [ ] Are metrics and evaluation protocols clear?

### Analysis

- [ ] Do result paragraphs follow Claim → Evidence → Mechanism → Boundary?
- [ ] Do you explain why gains happen?
- [ ] Do you identify where gains are smaller?
- [ ] Do ablations test mechanisms rather than merely remove modules?

### Figures and Tables

- [ ] Does every figure/table support one claim?
- [ ] Does every caption state the main trend?
- [ ] Are critical results in the main paper, not only appendix?
- [ ] Can the reader understand the paper by skimming figures and captions?

### Wording

- [ ] Are claims appropriately hedged?
- [ ] Are sentences short enough?
- [ ] Are vague adjectives replaced by measurable statements?
- [ ] Are verbs concrete rather than inflated?

### Limitations

- [ ] Are assumptions stated?
- [ ] Are failure modes discussed?
- [ ] Are future directions concrete?
- [ ] Does the limitation define scope rather than apologize?

### Reproducibility

- [ ] Are datasets, splits, metrics, prompts, hyperparameters, and compute described?
- [ ] Can another researcher reproduce or verify the main claims?
- [ ] Are model/data/code release constraints clearly stated?

---

## 24. 最短可执行版本

写任何 AI 论文段落时，优先套用以下四步：

```text
1. Claim: What should the reader believe?
2. Evidence: What number, figure, theorem, or comparison supports it?
3. Mechanism: Why does this happen?
4. Boundary: When does it not happen or become weaker?
```

对应英文模板：

```latex
The results in <Table/Figure> show that <claim>.
Compared with <baseline>, <method> <evidence>.
This suggests that <mechanism>.
In contrast, <boundary case>, indicating that <scope>.
```

如果一段话不能填进这个结构，通常说明它还不是论文分析，而只是描述。
