# JDWatch.work 就业信息采集方式调研

日期：2026-09-04

这份笔记记录我对 `jdwatch.work` “为什么能聚合出这么多就业信息”的公开调研结果。

## 结论

`jdwatch.work` 更像是一个**职位聚合站 + 自动化爬虫/抓取管道**，而不是单一公司的招聘页。

它公开展示了：

- 来自多个招聘源的聚合职位；
- 每条职位都有标准化字段，例如 `Company`、`Focus Tech`、`Location`、`Published`、`Crawled`；
- `Apply now` 会跳转到官方 careers page；
- 站点本身自述为 “Job aggregation tool from multiple recruitment sources”。

## 已确认的公开线索

### 1. 站点定位就是多源聚合

主页和职位页都直接把自己描述成多来源聚合工具，而不是单一招聘官网。

- [JDWatch 首页](https://www.jdwatch.work/)
- 代表性职位页：[Tencent 职位示例](https://www.jdwatch.work/jobs/j6zs9mqnf)

### 2. 职位页明确指向官方招聘页

职位详情页里能看到：

- `Apply now`
- `You'll be redirected to the official careers page.`

这说明它不是人工录入职位，而是把外部招聘页内容抓取后再统一展示。

### 3. 页面字段是统一抽取后的结构化结果

公开页面里的职位都被整理成相同模板，例如：

- 公司名
- 技术方向
- 地点
- 发布时间
- 抓取时间

这类结构很像爬虫抓取后做了清洗、分类、去重和索引。

### 4. 公开技术栈指向爬虫系统

`@jdwatch/cli` 的公开说明里，能看到它是一个用于：

- `scrape`
- `validate`
- `interactive`
- `auth`
- `pull`

的 CLI。

同时依赖里出现了 `crawlee`、`playwright`、`cheerio` 这类典型抓取和解析工具。

README 还把它描述成“本地与远程一体化”的抓取工具，命令里包含：

- `scrape`
- `validate`
- `interactive`
- `auth`
- `pull`

这说明它不是单次脚本，而是带配置、鉴权和远程同步的采集系统。

## 我的判断

综合公开页面和 CLI 信息，我认为它的核心链路大概率是：

1. 定时访问多个公司招聘页或 careers page；
2. 用浏览器自动化或网页抓取提取职位列表和详情；
3. 把字段标准化成统一 schema；
4. 做分类、聚合、去重、索引；
5. 在站点里按公司、技术方向、地点、发布时间展示。

也就是说，它“拿到这么多就业信息”的关键，不是某个神秘接口，而是**多源自动化采集**。

## 进一步确认

后来我又看到了站点的日报页，信息更完整：

- 首页明确写了 `Real-time aggregation of the latest and best technical, R&D and design positions from major companies.`
- 日报页会统计每天新增岗位数、公司数、招聘渠道分布和技术方向分布。
- 日报页底部说明：`数据统计以系统采集及岗位官方发布时间（publish_time）为准。`

这几乎把它的工作方式说透了：**系统采集 + 按官方发布时间归档 + 日报汇总**。

## 当前还不完全确定的部分

下面这些点我还没拿到直接公开证据，只能先当作推断：

- 具体抓了哪些招聘源；
- 是否包含登录态来源；
- 是否有自建调度器或队列；
- 是否会把官方页面内容转成自有结构化库后再生成站点索引。

## 参考链接

- [JDWatch 首页](https://www.jdwatch.work/)
- [JDWatch 腾讯职位示例](https://www.jdwatch.work/jobs/j6zs9mqnf)
- [JDWatch 快手职位示例](https://www.jdwatch.work/jobs/j8gkmpzub)
- [JDWatch 阿里职位示例](https://www.jdwatch.work/jobs/j1ohdj8wq)
- [JDWatch 日报页](https://www.jdwatch.work/blog)
- [JDWatch 2026-07-21 日报](https://www.jdwatch.work/blog/2026-07-21-daily)
- [npm: @jdwatch/cli](https://www.npmjs.com/package/%40jdwatch/cli)
