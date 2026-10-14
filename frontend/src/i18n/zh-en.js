// Reviewed, local UI translations. User text and model responses are not translated.
const glossary = `
峰值负荷 (kWh)|Peak Load (kWh)
峰值时间|Peak Time
谷值负荷 (kWh)|Valley Load (kWh)
谷值时间|Valley Time
峰谷差 (kWh)|Peak-to-Valley Difference (kWh)
平均负荷 (kWh)|Mean Load (kWh)
1小时|1 Hour
1天|1 Day
图表仅使用后端返回的带噪 buckets，不请求真实未加噪结果。|The chart displays only noisy time bins returned by the backend. Unprotected results are not requested.
控制数据库仅保存用户、会话、申请、审批、Grant、预算、任务和审计；园区能源数据保存在只读 Parquet 中。|The control database stores only users, sessions, requests, approvals, grants, budgets, tasks, and audit records. Park energy data remain in read-only Parquet files.
原始数据由数据提供方本地保存，平台仅支持授权后的受控统计查询。|Raw data remain with each data owner. The platform supports only authorized statistical queries.
Party 与 Compute 节点状态|Party and Compute Node Status
条安全审计记录|Security Audit Records
结果或状态|Result or Status
真实 decision/status|Recorded decision/status
Agent 快捷操作|Agent Quick Actions
节点|Node
接入|Integration
或|or
与|and
返回带噪统计结果|Release Privacy-Protected Statistics
返回带噪结果|Release Privacy-Protected Result
剩余预算|Remaining Budget
消耗预算|Budget Consumed
快捷操作|Quick Actions
总览数据加载失败|Failed to load overview
身份验证失败|Authentication failed
历史任务状态加载失败|Failed to load task status
历史会话加载失败|Failed to load conversation history
正在加载会话|Loading conversation
任务会话关联失败|Failed to link task and conversation
会话暂时无法持久化|Conversation cannot be saved at this time
当前授权可选|Available under this grant
当前授权可执行|Queries allowed by this grant
必须选择时间粒度|A time resolution is required
隐私预算未变化|Privacy budget unchanged
当前任务已按本轮明确参数核对|Current task checked against the supplied parameters
当前任务尚不能提交|Current task is not ready for submission
当前任务暂不能提交|Current task cannot be submitted yet
当前任务可提交|Current task is ready to submit
当前任务未发生改变|Current task is unchanged
智能解析暂不可用|AI query parsing is unavailable
请稍后重试或使用右侧参数编辑功能|Try again later or edit the parameters on the right
已识别本轮参数|Parameters identified
已更新任务|Task updated
已更新字段|Updated Fields
或展开参数设置当前任务|Or expand the parameters to configure the task
安全提醒|Security Notice
普通对话|Conversation
没有匹配的会话|No matching conversations
你可以通过自然语言创建第一个隐私查询任务|Describe a task to prepare your first private query
本地界面已清理|Local interface cleared
退出请求失败|Sign-out request failed
已完成审批|Approval Complete
本地受控统计|Controlled Local Statistics
贡献度裁剪与本地统计|Contribution Clipping and Local Statistics
秘密份额|Secret Shares
执行失败|Execution Failed
预计参与方|Expected Participants
计算时间|Computation Time
用时|Duration
最近计算任务|Recent Computation Tasks
节点资源监控|Node Resource Monitor
通信与安全事件|Communication and Security Events
本阶段仅展示任务阶段与计数|This stage shows only task stages and counts
任务注册到|Register task with
并下发园区|and dispatch to parks
份额提交至|Submit shares to
节点状态|Node Status
服务标识|Service ID
策略变更记录|Policy Changes
操作用户或主体|User or Actor
主体角色|Actor Role
简短说明|Brief Description
关联授权|Related Grant
审计追溯与报告中心|Audit and Reporting
所选记录未关联可用的任务和预算审计数据|No task or budget audit data are linked to this record
审计记录加载失败|Failed to load audit records
以下内容来自本地安全审计表|The following records come from the local security audit table
允许或完成|Allowed or Completed
拒绝或失败|Denied or Failed
已消费授权记录|Used Grant Records
真实任务状态|Recorded Task Status
审批历史加载失败|Failed to load approval history
性能测试记录加载失败|Failed to load benchmark records
暂无可导出的真实性能测试结果|No measured benchmark results available for export
本申请仅包含此查询类型|This request contains only this query type
可取消查询类型|Query types may be deselected
以收紧本次批准范围|to narrow the approved scope
该功能暂不可用|This feature is unavailable
校验并转换|Validate and Convert
校验与转换已完成|Validation and conversion complete
导入失败|Import failed
活动版本加载失败|Failed to load active version
数据库直连|Direct Database Connection
新增外部数据源|Add External Data Source
查询继续使用|Queries continue to use
确认回滚到只读基线数据|Restore the read-only baseline data
当前导入版本仍会保留|The imported version will be retained
确认回滚到|Restore version
启用后|After activation
该园区后续查询将使用此数据快照|Subsequent queries for this park will use this snapshot
可确认启用|Ready for Activation
更新账号失败|Failed to update account
更新账号状态失败|Failed to update account status
原有会话已撤销|Previous sessions revoked
的会话已撤销|sessions revoked
请填写查询参数后点击|Enter the query parameters and click
但获取结果失败|but the result could not be retrieved
只返回带噪统计值|Only noisy statistics are returned
不请求真实未加噪结果|Does not request unprotected results
请确认后点击|Review and click
身份验证通过|Authenticated
告警事件|Alert Events
较昨日|Compared with Yesterday
今日隐私查询|Private Queries Today
当前園区|Current Park
当前园区|Current Park
当前计算模式|Current Computation Mode
当前使用|Currently Using
默认隐私预算|Default Privacy Budget
匹配的功能页|Matching Feature Page
未找到与|No match for
已接收问题|Question received
打开结果明细|Open Result Details
解释内容已复制|Explanation copied
正在打开执行日志|Opening execution log
保护机制|Privacy Mechanism
平台仅支持授权后的受控统计查询|The platform supports only authorized statistical queries
风险结论|Risk Assessment
演示授权|Demo Grant
演示模式仅展示任务结构|Demo mode shows task structure only
演示任务状态|Demo Task Status
时间周期切换|Change Period
正在执行真实协议|Executing the benchmark protocol
指标已更新|Metrics updated
已配置|Configured
已连接|Connected
白名单|Allowlist
模型服务|Model Service
外部模型|External Model
平台安全|Platform Security
安全摘要|Safe Summary
强制|Enforced
在线节点|Online Nodes
接入数据方|Connected Data Owners
可调节负荷|Flexible Load
储能可用容量|Available Storage Capacity
生成中|Generating
进行中|In Progress
准备中|Preparing
等待选择|Awaiting Selection
不代表业务数据授权|Does not grant access to operational data
本次涉及|Involved Nodes
核心总数|Core Node Count
平均延迟|Mean Latency
平均响应|Mean Response
平均|Average
申请记录|Request Records
发起人|Requester
请说明业务目的|Describe the business purpose
不少于|At least
密码至少|Minimum password length:
且两次输入必须一致|The two entries must match
并确认两次密码一致|and ensure both passwords match
下划线或连字符|Underscore or Hyphen
位字母|Letters
个字符|Characters
数字|Digits
点|Dot
到期时间|Expiry
到期|Expires
本次预计消耗|Estimated Budget Cost
结论|Conclusion
发布|Release
交互轮次|Conversation Turns
预留|Reserved
审计功能|Audit Features
离线开发模式不提供审计记录|Offline development mode has no audit records
离线开发模式不生成业务报表|Offline development mode has no operational reports
离线开发模式不提供系统运行状态|Offline development mode has no runtime status
请连接后端审计接口|Connect to the backend audit endpoint
请至少选择一个|Select at least one
预算必须大于|Budget must be greater than
且不超过|and at most
本阶段仅展示任务阶段与计数|This stage shows only task stages and counts
份额提交至|Submit shares to
聚合|Aggregation
运行节点|Running Nodes
组件|Components
申请|Request
查询|Query
会话|Session
解释|Interpretation
解析|Parsing
解读请求|Interpretation Request
核验|Validate
前往|Go to
统计|Statistics
选择|Select
文件|File
最近|Recent
最多|Up to
更早|Earlier
条记录|Records
个时间桶|Time Bins
个后端带噪时间桶的负荷折线图|Noisy time bins returned by the backend
个数据提供方|Data Owners
个数据方|Data Owners
小时|Hours
秒|Seconds
页|Page
行|Rows
项|Items
约|Approximately
户|Households
日|Days
个|Items
各|Each
您|You
身份验证通过，欢迎|Signed in. Welcome,
风险预警|Risk Alerts
后端暂未提供风险预警接口；预算不足或任务失败会在智能查询工作台直接提示。|A risk-alert endpoint is not available. Budget and task errors are shown in the query workspace.
园区智能电表聚合数据|Park Smart-Meter Aggregate Data
园区家庭用电半小时粒度数据，仅支持受控隐私统计查询。|Half-hourly household electricity data. Access is limited to authorized private statistical queries.
家庭级贡献裁剪、秘密共享与分布式差分隐私；不提供原始数据下载。|Household-level clipping, secret sharing, and distributed differential privacy. Raw data cannot be downloaded.
支持查询|Supported Queries
申请使用|Request Access
工作台|Workspace
查看当前隐私预算|View Current Budget
正在聆听|Listening
授权|Grant
天|Days
当前授权未开放时间粒度|Time resolution is unavailable under this grant
暂不能提交|Cannot Submit Yet
暂无可用授权，请先完成数据使用申请与审批。请修改后重试。|No active grants. Complete a data-use request and obtain approval, then try again.
当前没有可用授权，请先完成数据使用申请与审批。请修改后重试。|No active grants. Complete a data-use request and obtain approval, then try again.
执行阶段由后端任务状态实时驱动|Execution stages reflect live backend task status
核验 Grant 与预算|Validate Grant and Budget
园区本地统计|Local Park Statistics
秘密份额生成|Secret Share Generation
完成|Complete
尚未提交查询任务。请填写查询参数后点击「提交隐私查询」。|No query submitted. Enter the parameters and click Submit Private Query.
提交任务后将在此展示实际请求参数|Submitted request parameters will appear here
桶数|Bin Count
各查询类型任务数量|Tasks by Query Type
任务数|Task Count
各园区参与次数|Participation by Park
参与次数|Participation Count
最近真实任务|Recent Tasks
暂无真实任务|No recorded tasks
最近真实授权使用记录|Recent Grant Usage
下载当前版本未开放|Download is unavailable in this version
依赖可信执行方|Requires a Trusted Executor
结合多方安全计算|Combined with Secure Multiparty Computation
当前系统采用的设计|Implemented System Design
该表为方法学说明，不代表当前在线实验测量结果。隐私效用及攻击实验指标由离线实验脚本生成，不属于在线业务统计。|This table describes the methods, not live measurements. Privacy utility and attack metrics come from offline experiments, separate from operational statistics.
仅 TIME_SERIES 可设置|Available only for TIME_SERIES
下方阶段耗时合计|Sum of Stage Durations Below
本次涉及 / 核心总数|Involved / Total Core Nodes
平均响应|Mean Response Time
待测试|Not Tested
秘密共享传输|Secret Share Transmission
安全聚合计算|Secure Aggregation
测试|Benchmark
共|Total
条|Records
完成性能测试后展示真实跨节点通信链路|Inter-node communication links appear after a benchmark completes
通信开销统计口径：统计 Benchmark 执行期间跨节点业务请求与响应的 UTF-8 字节数，不含 HTTP/TCP/IP 头与浏览器静态资源流量。|Communication counts UTF-8 bytes in inter-node benchmark requests and responses. It excludes HTTP/TCP/IP headers and browser assets.
请修改后重试|Adjust and try again
未生成任何查询参数，未创建任务，隐私预算未变化。|No query parameters or tasks were created. The privacy budget is unchanged.
请先完成一次查询|Complete a query first
预算不足或任务失败会在智能查询工作台直接提示|Budget and task errors appear in the query workspace
请稍候|Please wait
不属于在线业务统计|Separate from operational statistics
请求已拒绝|Request Refused
未修改当前任务参数|Current task parameters are unchanged
当前任务可进入提交确认|Current task is ready for confirmation
请至少选择一个园区|Select at least one park
参数已同步至当前任务|Parameters synchronized with the current task
请先在左侧描述查询需求|Describe the query in the conversation first
创建失败|Creation Failed
该审批已完成|This approval has been completed
来自待审批列表|From Pending Approvals
来自审批历史|From Approval History
至少保留一种允许的查询类型|Keep at least one allowed query type
请查看安全错误摘要|See the safe error summary
请查看错误提示|See the error message
任务成功率|Task Success Rate
任务和审计|Tasks and Audit
总预算|Total Budget
已消耗|Consumed
已用|Used
消耗占比|Budget Usage
本次预计消耗|Estimated Cost
使用前剩余|Available Before Query
使用后剩余|Available After Query
剩余余额合计|Total Remaining Allowance
结果已返回|Result Received
未创建任务|No task created
未生成任何查询参数|No query parameters generated
请填写完整账号信息|Complete the account information
不能停用当前账号|The current account cannot be disabled
园区管理员必须绑定园区|A data owner must be assigned to a park
该账号的现有登录会话将全部失效|All existing sessions for this account will be invalidated
重置后|After reset
节点运行正常|Node is operating normally
节点当前离线|Node is offline
后端暂未提供通信量统计与安全事件接口|Communication statistics and security event endpoints are not available
状态检查时间|Status Checked At
系统维护记录|Maintenance Records
暂无系统维护记录|No maintenance records
暂无系统运行状态|No runtime status
暂无安全策略摘要|No security policy summary
暂无策略变更记录|No policy change records
暂无节点状态|No node status
暂无节点数据|No node data
暂无参与园区|No participating parks
暂无参与方|No participants
暂无真实系统事件|No recorded system events
当前系统依赖与运行状态|Dependencies and Runtime Status
规划功能|Planned Feature
规划中的接入能力|Planned Integration
以上状态只读|These statuses are read-only
由部署环境配置|Configured at Deployment
仅支持|Supports Only
原始数据下载|Raw Data Download
原始数据保留本地|Raw Data Remain Local
当前后端未提供风险评估字段|The backend does not provide a risk assessment field
文件超过导入大小上限|File exceeds the import size limit
未记录校验错误|No validation errors recorded
未禁用|Not Disabled
未启动后续计算|No downstream computation started
最近导入|Latest Import
最近返回记录，最多 50 条|Most recent records (up to 50)
申请到期时间|Request Expiry
监控加载失败|Failed to load monitoring data
监控数据加载失败|Failed to load monitoring data
监控任务|Monitor Task
未找到相关功能|No matching feature
尝试使用其他关键词|Try other keywords
关闭全局搜索|Close Search
全局搜索|Global Search
请查看报告|View the report
未知事件|Unknown Event
未知原因|Unknown Reason
当前版本未开放|Unavailable in this Version
数据导出中|Exporting Data
导出功能开发中|Export is under development
报告导出中|Exporting Report
报告功能开发中|Report export is under development
我的审计|My Audit
查看全部预警记录|View All Alerts
待补充|Incomplete
待执行|Awaiting Execution
未获得麦克风权限，请允许浏览器访问麦克风后重试。|Microphone permission is required. Allow access and try again.
未检测到语音，请重试。|No speech detected. Try again.
未检测到可用麦克风。|No microphone detected.
语音识别暂时不可用，请使用文字输入。|Speech recognition is unavailable. Type your question instead.
当前浏览器暂不支持语音输入，请使用 Chrome 或 Edge。|Voice input is not supported by this browser. Use Chrome or Edge.
语音输入需要 HTTPS 或 localhost 安全环境。|Voice input requires HTTPS or localhost.
面向能源可信数据空间的多方安全协同与隐私保护平台|GridShield: Secure Collaborative Energy Data Analysis
面向能源可信数据空间的|Trusted Energy Data Space
多方安全协同与隐私保护平台|Secure Collaboration and Privacy Protection
系统总览|Overview
数据目录|Data Catalog
我的申请|My Requests
新建申请|New Request
我的授权|My Grants
授权查询|Authorized Queries
任务与计算|Tasks and Computation
报表中心|Reports
性能测试|Performance Tests
待我审批|Pending Approvals
审批历史|Approval History
本园区授权|Park Grants
数据接入|Data Import
安全策略中心|Security Policies
申请审计|Request Audit
审批审计|Approval Audit
授权审计|Grant Audit
查询和预算审计|Query and Budget Audit
全部申请|All Requests
全部授权|All Grants
账号与权限|Accounts and Permissions
安全审计|Security Audit
系统设置|Settings
搜索功能|Search features
收起导航|Collapse navigation
展开导航|Expand navigation
通知中心|Notifications
全部标记为已读|Mark all as read
全部通知已标记为已读|All notifications marked as read
退出登录|Sign out
个人设置|Profile settings
当前用户|Current user
数据分析员|Analyst
园区管理员|Data Owner
审计员|Auditor
系统管理员|Administrator
身份认证|Sign in
登录平台以访问已授权的数据空间|Sign in to access authorized data
账号角色与园区权限由平台统一管理|Account roles and park permissions are managed by the platform
用户名和密码|Username and password
请输入用户名和密码|Enter your username and password
用户名或账号|Username or account
用户名|Username
密码|Password
隐藏密码|Hide password
显示密码|Show password
正在登录|Signing in
登录|Sign in
在线服务|Online Services
在线园区|Online Parks
剩余总隐私预算|Remaining Privacy Budget
任务统计|Task Statistics
总控 / 园区 / 计算节点|Control / Parks / Compute Nodes
数据提供方|Data Owners
全链路业务流程|End-to-End Workflow
数据源接入|Data Integration
多源异构数据安全接入|Secure integration of heterogeneous data
可信身份验证|Authentication
后端会话与角色权限控制|Sessions and role-based access control
权限与隐私预算校验|Authorization and Budget Checks
权限识别与预算充足性检查|Access and available budget checks
分布式差分隐私计算|Distributed Differential Privacy
多方安全协同计算|Secure collaborative computation
大模型解释与报告|AI Interpretation and Reporting
结果释义与可视化报告|Result interpretation and visualization
区块链审计存证|Blockchain Audit Trail
全过程存证不可篡改|Tamper-evident process records
数据不出域|Data Remain Local
多方安全计算|Secure Multiparty Computation
智能可信交互|AI-Assisted Interaction
跨域协同|Cross-Domain Collaboration
隐私计算|Privacy-Preserving Computation
全程可审计|Auditable Workflow
近7日隐私查询趋势|Privacy Queries: Last 7 Days
跨主体协同任务分布|Collaborative Task Distribution
近 7 日暂无任务数据|No tasks in the last 7 days
近7日|Last 7 Days
暂无任务分布数据|No task distribution data
系统健康度|System Health
最近任务|Recent Tasks
查看全部任务|View all tasks
总控服务|Control Plane
前端网关|Frontend Gateway
园区业务概览|Park Overview
本园区有效授权|Active Park Grants
当前数据版本|Current Data Version
最近数据导入|Recent Data Imports
延迟|Latency
版本|Version
详情|Details
成功 / 失败 · 平均|Completed / Failed · Average
总任务数|Total Tasks
任务成功率|Task Success Rate
平均任务耗时|Average Task Duration
平均执行时间|Average Execution Time
剩余隐私预算|Remaining Privacy Budget
隐私预算使用情况|Privacy Budget Usage
隐私预算消耗|Privacy Budget Consumption
隐私预算|Privacy Budget
预算未变化|Budget unchanged
使用目的|Purpose
数据使用申请|Data-Use Requests
选择数据园区、查询类型、时间范围和可接受的隐私预算上限。|Select parks, query types, the time range, and privacy budget limits.
前端校验用于操作提示；后端会再次校验数据资产范围、审批归属和全部授权条件。|Frontend checks provide guidance. The backend validates asset scope, approval ownership, and all grant conditions.
请说明业务目的，不少于 5 个字符|Describe the purpose (at least 5 characters)
申请范围|Requested Scope
申请园区|Requested Parks
查询类型|Query Type
开始时间|Start Time
结束时间|End Time
时序粒度|Time Resolution
仅申请 TIME_SERIES 时使用|Required only for TIME_SERIES queries
单次 epsilon 上限|Maximum ε per Query
累计 epsilon|Total ε Allowance
授权到期时间|Grant Expiry
保存草稿|Save Draft
保存并提交审批|Save and Submit
申请编号|Request ID
申请人|Requester
用途|Purpose
审批进度|Approval Progress
操作|Actions
撤销|Withdraw
申请已撤销|Request withdrawn
申请已提交|Request submitted
申请草稿已保存|Draft saved
申请已保存并提交多方审批|Request saved and submitted for approval
保存申请失败|Failed to save request
申请操作失败|Request action failed
当前申请状态|Current Request Status
申请内容|Request Details
附条件批准|Approve with Conditions
批准|Approve
拒绝|Reject
理由/附加条件|Reason / Additional Conditions
附加条件|Additional Conditions
理由|Reason
核对申请范围后作出园区独立决定|Review the scope and make an independent decision for this park
提交审批决定|Submit Decision
审批决定已提交|Decision submitted
提交审批失败|Failed to submit decision
拒绝申请时必须填写理由|Provide a reason when rejecting a request
返回审批列表|Back to Approvals
审批详情|Approval Details
审批编号|Approval ID
审批决定|Approval Decision
待处理审批|Pending Approvals
授权编号|Grant ID
有效授权|Active Grants
使用此授权查询|Query with This Grant
授权范围|Grant Scope
授权单次上限|Maximum ε per Query
授权用户|Grantee
授权列表|Grant List
授权记录|Grant Records
当前授权的隐私预算已耗尽|This grant has no remaining privacy budget
当前授权未生效|This grant is not active
当前没有可用授权|No grants are available
请先完成数据使用申请与多方审批|Complete a data-use request and obtain approval first
请先完成数据使用申请与审批|Complete a data-use request and obtain approval first
当前授权不满足此任务|The selected grant does not cover this task
请按授权范围调整参数或选择符合条件的授权|Adjust the query to the grant scope or select another valid grant
请选择其他有效授权|Select another active grant
授权提示|Grant Guidance
允许查询类型|Allowed Query Types
支持查询类型|Supported Query Types
允许开始时间|Allowed Start Time
允许结束时间|Allowed End Time
支持时间粒度|Supported Time Resolutions
请按上方提示修改参数|Adjust the parameters using the guidance above
尚未提交查询任务|No query has been submitted
尚未提交任务|No task has been submitted
尚未执行|Not executed
任务结果视图|Task Results
任务结果|Task Results
任务状态|Task Status
任务编号|Task ID
创建时间|Created At
执行时间|Execution Time
执行日志|Execution Log
查看执行日志|View Execution Log
任务执行失败|Task execution failed
任务已完成|Task completed
任务执行中|Task running
任务正在执行|Task is running
任务执行状态|Execution Status
执行中任务|Running Tasks
查询结果|Query Results
查询状态|Query Status
当前查询范围|Current Query Scope
参与园区|Participating Parks
参与数据方|Participating Data Owners
计算模式|Computation Mode
隐私计算模式|Privacy Mode
分布式差分隐私|Distributed DP
中心差分隐私|Central DP
本地差分隐私|Local DP
秘密共享|Secret Sharing
明文对照|Plaintext Baseline
求和|Sum
计数|Count
均值|Average
时间序列|Time Series
时间粒度|Time Resolution
时间范围|Time Range
时间桶数量|Number of Time Bins
时间桶|Time Bins
提交隐私查询|Submit Private Query
提交任务|Submit Task
编辑参数|Edit Parameters
收起参数|Collapse Parameters
参数与模式校验|Parameter and Mode Validation
权限与预算校验|Authorization and Budget Checks
权限与预算校验未通过|Authorization or budget check failed
创建与分发|Creation and Dispatch
本地裁剪与聚合|Local Clipping and Aggregation
园区本地计算|Local Park Computation
生成并传输份额|Share Generation and Transmission
节点聚合|Node Aggregation
结果重构|Result Reconstruction
结果返回|Result Release
非串通节点安全聚合|Aggregation by Non-Colluding Nodes
非串通节点聚合|Aggregation by Non-Colluding Nodes
总控重构与定点解码|Reconstruction and Fixed-Point Decoding
带噪聚合|Noisy Aggregate
带噪总用电量|Privacy-Protected Total Consumption
带噪平均用电量|Privacy-Protected Mean Consumption
负荷时间序列图|Privacy-Protected Load Time Series
负荷率|Load Factor
峰谷差|Peak-to-Valley Difference
平均负荷|Mean Load
峰值|Peak Load
谷值|Valley Load
总负荷|Total Load
放大图表|Zoom In
缩小图表|Zoom Out
重置图表缩放|Reset Zoom
图表缩放控制|Chart Zoom Controls
当前缩放比例|Current Zoom
可横向滚动的时间序列图|Horizontally Scrollable Time Series
悬停数据点查看精确值|Hover over a data point for its value
横向滚动浏览|Scroll horizontally
图表仅使用后端返回的带噪|The chart uses only the noisy data returned by the backend
后端未返回带噪时间桶数据|The backend returned no noisy time bins
后端返回结果为空或查询类型未知|The result is empty or the query type is unknown
隐私处理|Privacy Processing
隐私保护单位|Privacy Unit
噪声机制|Noise Mechanism
敏感度|Sensitivity
后处理|Post-Processing
家庭级隐私保护|Household-Level Privacy
分布式拉普拉斯机制|Distributed Laplace Mechanism
分布式向量拉普拉斯机制|Distributed Vector Laplace Mechanism
非负后处理|Nonnegative Post-Processing
负荷指标后处理|Load-Metric Post-Processing
无噪声机制|No Noise Mechanism
智能隐私查询|AI-Assisted Private Queries
对话工作区|Conversation
推荐问题|Suggested Questions
请输入您的问题|Enter your question
请输入问题|Enter a question
发送问题|Send
语音输入|Voice Input
开始语音输入|Start Voice Input
停止语音输入|Stop Voice Input
新建会话|New Conversation
历史会话|Conversation History
搜索会话|Search Conversations
关闭历史会话|Close History
你好，请描述需要分析的能源数据任务。我会将自然语言需求转换为受授权和隐私预算约束的计算任务。|Describe your energy analysis task. I will prepare a query constrained by your grant and privacy budget.
你好，请描述需要分析的能源数据任务。|Describe your energy analysis task.
查询三园区总负荷|Query the total load of all three parks
分析小时负荷趋势|Analyze hourly load trends
解释上一次查询|Explain the previous query
解释预算|Explain the budget
修改查询范围|Change Query Scope
生成趋势分析|Generate Trend Analysis
生成智能解读|Generate AI Interpretation
智能解读|AI Interpretation
智能解读已生成|AI interpretation generated
正在生成智能解读|Generating AI interpretation
解读生成失败|Failed to generate interpretation
模型服务不可用|Model service unavailable
正在解析查询意图并核验任务约束|Parsing intent and checking task constraints
正在生成查询计划|Preparing the query plan
已生成结构化查询任务|Structured query prepared
已生成查询参数草案|Draft query parameters prepared
请确认后提交|Review and submit
请进行最终确认|Confirm before submitting
当前任务|Current Task
任务概述|Task Summary
计算计划已复制到剪贴板|Computation plan copied
复制计划|Copy Plan
缺少参数|Missing Parameters
需要补充或调整参数|Parameters need to be completed or adjusted
已更新当前任务|Current task updated
已识别任务|Task identified
本结果已通过|This result is protected by
仅返回|Returns only
带噪统计结果|Noisy statistics
不包含任何园区局部明文或秘密份额|Contains no park-level plaintext statistics or secret shares
任务执行完成后展示隐私保护说明与执行元数据|Privacy information and execution metadata appear after task completion
分布式隐私计算执行流程|Distributed Private Computation Workflow
分布式隐私计算监控|Distributed Computation Monitor
当前任务执行拓扑|Current Execution Topology
当前阶段|Current Stage
整体进度|Overall Progress
刷新监控|Refresh Monitor
阶段耗时拆解|Stage Durations
阶段总耗时|Total Stage Duration
参与节点|Participating Nodes
已提交份额数|Submitted Shares
秘密份额数|Number of Shares
计算节点状态|Compute Node Status
节点资源与网络|Node Resources and Network
平均节点响应|Mean Node Response
网络错误|Network Error
隐私保护方法原理对比|Privacy Method Comparison
方法学说明|Methodology
核心机制|Core Mechanism
信任假设|Trust Assumption
本地扰动|Local Perturbation
中心扰动|Central Perturbation
分布式扰动|Distributed Perturbation
直接聚合|Direct Aggregation
数据方本地加噪|Local Noise Addition
聚合后统一加噪|Noise Addition after Aggregation
非串通聚合|Non-Colluding Aggregation
多方共同贡献噪声|Shared Noise Contribution
依赖可信聚合方|Requires a Trusted Aggregator
不依赖中心查看原值|The central service does not read raw values
不增加隐私扰动|No Privacy Noise
无隐私聚合|Aggregation without DP
性能测试参数|Benchmark Parameters
开始测试|Run Benchmark
测试中|Running Benchmark
测试状态|Benchmark Status
基准数据|Benchmark Data
标准三方能源数据基准集|Three-Party Energy Benchmark Dataset
合成能源负荷数据|Synthetic Energy Load Data
通信量|Communication Volume
通信总量|Total Communication
通信开销分布|Communication Breakdown
通信开销统计口径|Communication Measurement
跨节点通信字节|Inter-Node Bytes
最近测试记录|Recent Benchmarks
性能测试已完成|Benchmark completed
性能测试失败|Benchmark failed
基准测试预算独立于业务隐私预算|Benchmark budgets are independent of operational privacy budgets
隐私效用及攻击实验指标由离线实验脚本生成|Privacy utility and attack metrics are generated by offline experiments
方法|Method
平均相对误差|Mean Relative Error
误差区间|Error Interval
运行状态摘要|Runtime Summary
系统依赖与运行状态|Dependencies and Runtime Status
运行依赖与安全基线|Dependencies and Security Baseline
当前生效安全基线|Active Security Baseline
当前生效配置|Active Configuration
安全基线|Security Baseline
安全模式|Security Mode
双因素认证|Two-Factor Authentication
证书管理|Certificate Management
密码存储|Password Storage
哈希存储|Hashed Storage
会话安全|Session Security
账号初始化策略|Account Initialization
授权强制校验|Grant Enforcement
控制数据库|Control Database
仅控制平面元数据|Control-plane metadata only
数据资产存储|Data Asset Storage
只读挂载|Read-Only Mount
原始数据由数据提供方本地保存|Raw data are retained locally by each data owner
未实现能力不会显示为已启用|Unimplemented features are not shown as enabled
不声称已接入区块链存证|Blockchain anchoring is not implemented
账号列表|Account List
账号名|Account Name
账号|Account
搜索账号|Search Accounts
全部角色|All Roles
全部状态|All Statuses
新建账号|New Account
创建账号|Create Account
编辑账号|Edit Account
角色|Role
绑定园区|Assigned Park
所属园区|Assigned Park
初始密码|Initial Password
新密码|New Password
确认新密码|Confirm New Password
确认密码|Confirm Password
重置密码|Reset Password
撤销会话|Revoke Sessions
保存修改|Save Changes
账号已创建|Account created
账号权限已更新|Account permissions updated
账号已启用|Account enabled
账号已停用|Account disabled
密码已重置|Password reset
现有会话已撤销|Existing sessions revoked
最近登录|Last Sign-In
安全事件|Security Events
最近安全审计|Recent Security Audit
事件类型|Event Type
事件或主体|Event or Actor
事件|Event
操作者|Actor
操作主体|Actor
目标账号|Target Account
关联对象|Related Object
决定|Decision
原因|Reason
申请追溯详情|Request Trace
任务追溯详情|Task Trace
审计关键词|Audit Keywords
审计记录摘要|Audit Summary
审计记录数|Audit Record Count
审计记录|Audit Records
审计说明|Audit Information
任务与预算审计报告|Task and Budget Audit Report
报告导出|Export Report
导出结果|Export Results
查询与预算统计报告|Query and Budget Report
本园区数据资产|Park Data Assets
数据资产|Data Assets
资产编号|Asset ID
资产说明|Asset Description
资产目录|Asset Catalog
当前活动数据版本|Active Data Version
数据版本历史|Data Version History
完整快照导入|Full Snapshot Import
上传并校验|Upload and Validate
上传中|Uploading
上传人|Uploaded By
上传时间|Uploaded At
导入编号|Import ID
有效行|Valid Rows
总行数|Total Rows
重复记录|Duplicate Records
错误行|Invalid Rows
行数|Rows
源文件|Source File
安全文件名|Safe Filename
最近校验报告|Latest Validation Report
回滚到基线|Restore Baseline
回滚至此|Restore This Version
数据版本已启用|Data version activated
数据版本回滚完成|Data version restored
校验通过|Validation Passed
未通过校验|Validation Failed
文件不会自动启用|Uploaded files are not activated automatically
原有版本仍可回滚|Previous versions remain available for rollback
仅园区管理员可以导入数据|Only data owners can import data
安全导入|Secure Import
访问控制|Access Control
数据范围|Data Scope
更新时间|Updated At
创建与分发|Creation and Dispatch
已创建|Created
任务分发中|Dispatching
本地计算中|Computing Locally
秘密共享中|Sharing
节点聚合中|Aggregating
结果重构中|Reconstructing
已完成|Completed
已批准|Approved
待审批|Pending Approval
待处理|Pending
处理中|Processing
待执行|Pending Execution
待生成|Not Generated
已启用|Enabled
未启用|Not Enabled
已禁用|Disabled
停用|Disable
启用|Enable
在线|Online
离线|Offline
正常|Healthy
失败|Failed
成功|Successful
状态|Status
数据方|Data Owner
提供方|Provider
参与方|Participants
计算节点|Compute Node
安全计算节点|Secure Compute Node
总控|Control Plane
园区|Park
主体验证|Identity Verification
开始时间必须早于结束时间|Start time must precede end time
请选择当前用户的有效授权|Select an active grant belonging to the current user
请完整填写用途，并至少选择一个园区和一种查询类型|Enter the purpose and select at least one park and one query type
申请开始时间必须早于结束时间|The requested start time must precede the end time
授权到期时间必须晚于当前时间|Grant expiry must be in the future
查询时间超出授权范围|Query time is outside the grant scope
单次 epsilon 必须大于 0 且不超过 5|Per-query epsilon must be greater than 0 and at most 5
累计 epsilon 不能小于单次 epsilon 上限|Total epsilon must be at least the per-query limit
申请 TIME_SERIES 时必须选择时序粒度|Select a time resolution for TIME_SERIES
epsilon 超出授权可用额度|Epsilon exceeds the grant's available allowance
请选择时间粒度|Select a time resolution
请选择园区|Select a park
请至少选择一个园区|Select at least one park
请选择任务|Select a task
请选择一个任务查看执行流程|Select a task to view its execution workflow
请选择一个任务查看执行拓扑|Select a task to view its topology
请选择一个任务查看状态|Select a task to view its status
请选择|Select
请稍后重试|Please try again later
正在加载系统总览|Loading overview
正在加载系统运行状态|Loading runtime status
正在加载数据目录|Loading catalog
正在加载申请|Loading requests
正在加载审批详情|Loading approval details
正在加载审批|Loading approvals
正在加载授权|Loading grants
正在加载审计记录|Loading audit records
正在加载真实报表|Loading reports
正在加载性能测试记录|Loading benchmarks
正在加载账号|Loading accounts
正在读取活动版本|Loading active version
正在加载本园区数据资产|Loading park data assets
正在加载安全策略|Loading security policies
正在加载监控数据|Loading monitoring data
正在创建任务并校验隐私预算|Creating task and checking the privacy budget
加载中|Loading
暂无任务记录|No task records
暂无最近搜索|No recent searches
暂无任务|No tasks
暂无数据资产|No data assets
暂无申请记录|No request records
暂无申请|No requests
暂无授权使用记录|No grant usage records
暂无本园区相关授权|No grants for this park
暂无可用授权|No available grants
暂无授权|No grants
暂无图表数据|No chart data
暂无时间序列图表数据|No time-series data
暂无安全审计事件|No security audit events
暂无查询和预算审计记录|No query or budget audit records
暂无报表数据|No report data
暂无导入版本|No imported versions
暂无校验报告|No validation report
暂无性能测试记录|No benchmark records
暂无性能测试数据|No benchmark data
暂无预算数据|No budget data
暂无通信数据|No communication data
暂无历史会话|No conversation history
暂无匹配账号|No matching accounts
暂无记录|No records
暂无数据|No data
未知错误|Unknown error
未知状态|Unknown status
未绑定|Unassigned
未选择|Not selected
未记录|Not recorded
未配置|Not configured
未确认|Not confirmed
重新加载|Reload
查看详情|View Details
查看授权|View Grant
查看审批|View Approval
查看错误|View Error
查看全部事件记录|View All Events
查看全部安全事件|View All Security Events
查看授权范围|View Grant Scope
查看|View
刷新|Refresh
提交|Submit
保存|Save
取消|Cancel
确定|Confirm
关闭|Close
返回|Back
编辑|Edit
复制|Copy
重置|Reset
下载|Download
上传|Upload
搜索结果|Search Results
搜索功能|Search Features
搜索|Search
常用功能|Common Features
最近搜索|Recent Searches
未找到相关功能|No matching features
请尝试其他关键词|Try other keywords
时间|Time
日期|Date
分钟|Minutes
小时|Hours
剩余|Remaining
累计|Cumulative
上限|Limit
预算|Budget
消耗|Consumed
平均|Average
总额|Total
字节数|Bytes
进度|Progress
内存|Memory
响应时间|Response Time
检查延迟|Check Latency
健康度|Health
运行状态|Runtime Status
类型|Type
记录|Records
数据粒度|Data Resolution
说明|Description
参数|Parameters
单次|Per Query
创建失败|Creation failed
连接失败|Connection failed
未命名节点|Unnamed node
用户|User
安全聚合|Secure Aggregation
任务|Task
结果|Result
总|Total
昨天|Yesterday
今天|Today
无附加说明|No additional details
无异常事件|No abnormal events
无|None
是|Yes
否|No
`;

export const translations = Object.fromEntries(glossary.trim().split('\n').map(line => {
  const separator = line.indexOf('|');
  return [line.slice(0, separator), line.slice(separator + 1)];
}));
