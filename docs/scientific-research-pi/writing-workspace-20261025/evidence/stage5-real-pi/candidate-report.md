# 2020—2026 年芯片制造新技术：从尺寸缩放到器件、供电与集成协同

## 摘要

<!-- claim:C01 -->
本综述将“最新技术”解释为 2020—2026 年公开研究中的制造与集成方向，而非已经量产的技术清单。获取的摘要支持五条相互关联的主线：高数值孔径极紫外光刻及配套光学，GAA 纳米片与 CFET 结构，背面供电，混合键合与三维集成，以及原子层工艺和二维半导体。它们分别回应图形形成、器件布局、配电、垂直互连和材料界面问题；现有证据不足以给出统一的性能排名或量产时间表。[1] [3] [4] [6] [8] [9] [11] [13] [15]

## 引言

<!-- claim:C02 -->
回答“芯片制造最新技术有哪些”，需要同时考察新结构带来的潜力及其制造约束。纳米片结构的面积收益受到片宽、片间距和栅堆栈厚度约束；背面供电又会改变故障定位的可达性。这意味着，仅列节点名称或晶体管结构，不能完整说明技术进展及其适用条件。本文的问题是：这段时期有哪些可由研究内容支持的新方向，它们解决什么问题，又留下什么验证缺口？[1] [5]

## Scope（范围）

时间范围为 2020 年至检索日 2026 年 10 月 23 日，不包括尚未结束的 2026 年其余时间。重点为先进逻辑芯片的制造与相关集成，涵盖光刻、晶体管结构、配电、键合、刻蚀及二维材料；不企图覆盖全部存储器、功率器件或光子芯片技术。InGaAs 刻蚀作为工艺方法的邻近例子纳入。这里的“新”指该窗口内研究的方向与进展，不声称每项技术都首次诞生于此期间。

## Methods（方法）

使用 Crossref 和 arXiv，开展围绕 GAA/nanosheet、CFET、backside power delivery、high-NA EUV、hybrid bonding、atomic layer etching 和二维材料的英文主题检索，并根据首轮摘要缺失情况补充查询。共保存 18 条实际请求记录，均返回 success；其中包含一次同一查询的重复请求。各请求的 result_count 仅表示适配器返回行数，不是数据库命中总量。按 DOI、标识符及规范化题名去重后保存 83 条文献，逐条筛选，纳入 15 条，排除 68 条，无 uncertain 条目。排除依据包括年份不符、只有题录或补充材料、主题偏离、摘要残缺及目的性主题取舍；这是一篇叙述性综述，并非系统综述。

纳入材料全部只获得摘要，没有获取全文。对其中具有 DOI 的 8 条材料实际进行了 DOI 元数据查询，返回相同 DOI，记为 verified；另外 7 条无 DOI 的 arXiv 来源记录保持 unknown，未完成独立标识符核验。核验不代表科学结论获验证，也不证明同行评审状态。没有观察到来源报错或核验失败，但摘要缺失显著限制了可用证据。引用、筛选与证据链保存在配套结构化文件中。

## Findings（研究发现）

### 图形形成：高 NA EUV 的光学探索与实验分辨率需要分开理解

<!-- claim:C03 -->
光刻证据呈现两种不同层次的进展。一项实验用镜面式 EUV 干涉光刻，在 13.5 nm 波长下得到 HSQ 光刻胶 5 nm 半间距线/空图形；另一项研究设计 0.55 NA 全分面照明器，结合深度强化学习匹配，在仿真中报告透过率超过 35%、均匀性超过 99%。前者证明特定周期图形可以形成，后者研究照明子系统的优化；二者不能合并为商业扫描机已达到某种节点、缺陷率或生产率的证据。这里可比较的是各自验证了哪一环节，而非数值大小。[7] [8]

<!-- claim:C04 -->
2026 年四反射镜同轴高 NA EUV 方案进一步说明，光学方案仍存在工程取舍：研究考察 NA 0.5 和 0.55，但摘要承认视场边缘有数微米残余畸变，扫描会造成模糊，因此转向较小视场的步进方案，并要求检查遮挡对成像的影响。这支持将新投影光学列为研究前沿，却不足以认定其优于现有整机平台或已经适合量产。[6]

### 器件结构：GAA 与 CFET 的收益依赖可制造的几何和材料窗口

<!-- claim:C05 -->
GAA 纳米片研究的关键并非“堆叠越多越好”。在相同器件高度、占地及光刻刻蚀能力约束下，几何比较发现纳米片的沟道折叠优势有条件成立，例如片间距需小于片宽；考虑栅氧和金属栅厚度后，摘要给出的最小片间距约为 7—8 nm。可靠性综述则把 BTI、热载流子注入和介质击穿列为需要评估的机制。两者关注的终点不同，但共同要求把密度潜力与工艺空间、寄生效应及寿命验证一起考虑；前者对极限缩放的保留意见并不构成对后者可靠性结论的直接反驳。[1] [2]

<!-- claim:C06 -->
CFET 与埋入式电源轨的组合展示了结构协同也会引入新耦合。在一项 3-track 标准单元研究中，电源轨与底部寄生沟道的距离被压到 13 nm 或更小，电源轨的横向场导致衬底漏电；TCAD 显示，降低势垒材料介电常数和 TiN 衬层功函数可抑制该效应。这是特定设计条件下的材料优化线索，不能把 13 nm 当作所有平台的临界值，也不能据此断言 CFET 已完成量产验证。[3]

### 背面供电：配电优化必须连同测试能力评价

<!-- claim:revision_bpd_1 -->
背面供电与埋入式电源轨的设计收益和诊断约束，构成评价这一技术时需要同时考虑的两个方面。现有预印本结合 TCAD 与物理综合构建模型，讨论降低压降、功耗、关键路径延时和电路面积的潜力；故障隔离方法综述章节则指出，背面配电网络形成的阻挡会使多种传统电气故障定位方法失效或性能下降，并评估电子束与原子力探针、X 射线与磁场成像以及锁相热成像的适用性和技术挑战。两类材料分别从电路设计和故障诊断出发，提示配电优化的评价应纳入可测试性：设计指标的改善潜力与诊断手段的适用约束需要共同考察，单凭配电收益尚不足以判断整体技术效果。[4] [5]

<!-- claim:revision_bpd_2 -->
上述比较仅依据固定记录中的摘要证据，其作用限于综合设计目标与诊断问题。设计研究摘要所述改善倍数缺少可核对的完整基线，不能外推为不同平台上的普遍收益；诊断章节摘要也未提供统一的诊断性能数据，不能据此排列各类故障定位方法的优劣。两类材料的方法与评价终点不同，现有记录不足以将配电改善与诊断能力变化纳入同一量化比较，也不足以确定二者的综合收益。因此，本节能够提出配电、电路设计与可测试性应协同评价的判断，但不能据此认定整体制造难题已经解决。[4] [5]

### 三维集成：混合键合把研究重点推向良率与热界面

<!-- claim:C08 -->
混合键合的研究需要同时回答“能否可靠连接”和“热量如何跨界面传递”。YAP+ 在晶圆对晶圆及芯片对晶圆键合模型中纳入套刻偏差、颗粒、铜凹陷、粗糙度、焊盘密度与版图，并以模拟结果检验近解析模型。2026 年的一项实验则通过时域热反射与多层模型，给出低温键合 SiOx 界面热边界电导下限 150 MW/m²/K。前者帮助组织缺陷与版图风险，后者约束局部热界面；模型吻合不等于产线良率标定，介质界面测量也不等于完整三维芯片的热可靠性。它们提供互补证据，尚不能形成统一的堆叠成本或可靠性排序。[11] [12]

### 原子层工艺与二维材料：精确控制和集成演示之间仍有距离

<!-- claim:C09 -->
原子层刻蚀的可用证据支持“通过分步反应精确控制去除量”，但也显示其材料依赖性。SiO2 研究在近室温下交替使用 SF6 与 Ar 等离子体，报告约 1.4 Å/周期，并观察到单独半反应不刻蚀、顺序组合才发生刻蚀；InGaAs 研究在 350°C 下交替暴露原子氢与氧气，得到 0.095 Å/周期，200 周期后仍保持原子级平滑。材料、反应体系和温度均不同，不能按每周期刻蚀量判断哪种工艺“更先进”，也不能据此估算相同产能。可共同得出的结论限于：循环表面反应能在各自条件下提供细尺度材料去除控制。[9] [10]

<!-- claim:C10 -->
二维半导体证据从材料生长延伸到了功能阵列。逐层外延研究得到 4 英寸 MoS2 晶圆，并将层数控制至 6 层；摘要报告单、双、三层器件的平均室温场效应迁移率约为 80、110、145 cm²/V/s。另一项研究用单层 MoS2 制作 32×32、共 1024 个浮栅晶体管的向量矩阵乘法阵列，报告高良率、低器件差异并演示并行离散信号处理。二者分别支持生长控制与专用电路集成的可行性，却没有形成同平台下的材料—工艺—电路对照，不能把迁移率数值直接转换为阵列能效，也不能把专用阵列演示等同于通用 CMOS 替代。[13] [14]

<!-- claim:C11 -->
二维材料的集成还依赖介质界面。所纳入非晶氮化硼研究报告低于 250°C 的晶圆尺度 ALD 工艺，通过无种子层沉积在二维表面形成均匀介质，并演示 MoS2 相关结构和双栅器件。这为低温介质集成提供一条路线，但摘要不足以证明长期界面稳定性或完整产线兼容性。因此，二维材料的进展应连同沉积与界面工艺理解，单有优良沟道材料并不能完成制造论证。[15]

## Discussion（讨论）

<!-- claim:C12 -->
综合这些证据，本文的解释是：这一时期的研究越来越需要跨层次协同，器件几何、配电、键合版图和材料界面难以单独优化。这是对纳入研究的归纳，而不是某一来源直接证明的产业定律。纳米片的空间约束、CFET 的场诱导漏电，以及混合键合的版图相关良率模型，分别展示了局部改进可能受相邻结构限制的机制；但尚无共同测试平台证明某种技术组合在成本、能效和良率上全面占优。[1] [3] [11]

<!-- claim:C13 -->
证据之间没有形成可以直接合并的性能冲突。光刻研究测图形半间距或模拟照明质量，刻蚀研究测每周期去除量，材料研究测迁移率，键合研究测模型良率或界面热传导；这些终点回答不同问题。尤其是器件几何比较对纳米片缩放的谨慎判断，与可靠性综述将 GAA 视为重要研究方向，并非同一条件、同一终点的相反结果。现有摘要不足以进一步解释不同平台间全部差异，也不足以确定研究演示转化为稳定量产所需的时间。[1] [2] [7] [8] [9] [11] [12] [13]

## Limitations（局限性）

检索只覆盖两个公开适配器、有限英文查询及较小的每次返回上限，使用目的性筛选；没有数据库总命中数，也不能评估召回率。2020—2026 是纳入范围，并不表示每一年、每个子领域都已得到充分覆盖。2026 年材料只是检索当时可取得的部分，不支持完整年度判断。缺少摘要的会议论文被排除，可能使对重要产业进展的覆盖不足。

全部科学证据来自摘要，未获取全文中的工艺细节、统计误差、基线、图表、失效分析或完整限制条件；部分内容来自 arXiv 或明确的预印本，未独立确认同行评审状态。15 条纳入材料中 7 条标识符核验仍为 unknown。相同题名的 arXiv 与 DOI 记录合并保留来源，以 DOI 版本摘要为提取依据；不同版本的细节不混用。DOI 核验仅确认标识符返回一致。以上限制使本文适合识别技术方向和验证问题，不适合提供采购决策、厂商量产排名或工艺节点时间表。

## 结论

<!-- claim:C14 -->
在本次获取证据的范围内，2020—2026 年值得关注的芯片制造技术包括高 NA EUV 与配套光学、GAA 纳米片及 CFET、背面供电、混合键合三维集成，以及原子层刻蚀、低温介质沉积和二维半导体集成。回答“最新有哪些”时，应同时给出其证据层级：其中既有光学与器件仿真，也有材料、图形和功能阵列实验；这些成果共同揭示了可研究的制造路径，但尚不足以证明它们均已成熟量产，或存在一条普遍最优路线。[1] [3] [4] [6] [8] [9] [11] [13] [14] [15]

## References（参考文献）

[1] Hei Wong; Kuniyuki Kakushima. On the Vertically Stacked Gate-All-Around Nanosheet and Nanowire Transistor Scaling beyond the 5 nm Technology Node. 2022. DOI: 10.3390/nano12101739.

[2] Miaomiao Wang. A Review of Reliability in Gate-All-Around Nanosheet Devices. 2024. DOI: 10.3390/mi15020269.

[3] Eungyo Jang; Jaehyuk Lim; Changhwan Shin. Buried power rail to suppress substrate leakage in complementary field effect transistor (CFET). 2024. DOI: 10.1088/2632-959x/ada0ce.

[4] Дарья Рыжова; Иван Павлов; Иван Асапов. Buried power rails and backside power distribution for nanometer-scale IC design. 2025. DOI: 10.24108/preprints-3113340.

[5] William Lo; Tom Xianghong Tong. Leading Edge Technologies: Backside Power Delivery. 2023. DOI: 10.31399/asm.tb.edfatr.t56090091.

[6] Tsumoru Shintake. High-NA in-line projector for EUV lithography. 2026. DOI: 10.1117/12.3118526.

[7] Tong Li; Yuqing Chen; Yanqiu Li; Lihui Liu. Design of an all-facet illuminator for high NA EUV lithography exposure tool based on deep reinforcement learning. 2025. http://arxiv.org/abs/2506.15558v1.

[8] Iason Giannopoulos; Iacopo Mochi; Michaela Vockenhuber; Yasin Ekinci; Dimitrios Kazazis. Extreme ultraviolet lithography reaches 5 nm resolution. 2024. http://arxiv.org/abs/2402.18234v1.

[9] Jun Peng; Rakshith Venugopal; Robert Blick; Robert Zierold. Atomic layer etching of SiO$_2$ using sequential SF$_6$ gas and Ar plasma. 2024. http://arxiv.org/abs/2412.20653v1.

[10] Mete M. Bayrak; Anthony J. Ardizzi; Sadhvikas Addamane; Kieran Cleary; Austin J. Minnich. Atomic layer etching of InGaAs using sequential exposures of atomic hydrogen and oxygen gas. 2025. http://arxiv.org/abs/2506.19749v1.

[11] Zhichao Chen; Puneet Gupta. YAP+: Pad-Layout-Aware Yield Modeling and Simulation for Hybrid Bonding. 2025. http://arxiv.org/abs/2511.05506v1.

[12] Xingqiang Zhang; Liu Chang; Liyi Li; Zhe Cheng. Thermal conductance across bonded SiOx-SiOx interfaces in hybrid bonding process. 2026. http://arxiv.org/abs/2601.03106v1.

[13] Qinqin Wang; Jian Tang; Xiaomei Li; Jinpeng Tian; Jing Liang; Na Li; Depeng Ji; Lede Xian. Layer-by-Layer Epitaxy of Multilayer MoS2 Wafers. 2022. DOI: 10.1093/nsr/nwac077.

[14] Guilherme Migliato Marega; Hyun Goo Ji; Zhenyu Wang; Mukesh Tripathi; Aleksandra Radenovic; Andras Kis. Large-Scale Integrated Vector-Matrix Multiplication Processor Based on Monolayer MoS2. 2023. DOI: 10.1038/s41928-023-01064-1.

[15] Cindy Y. Chen; Zheng Sun; Riccardo Torsi; Ke Wang; Jessica Kachian; Bangzhi Liu; Gilbert B. Rayner; Zhihong Chen. Tailoring Amorphous Boron Nitride for High-Performance 2D Electronics. 2023. http://arxiv.org/abs/2312.09136v1.
