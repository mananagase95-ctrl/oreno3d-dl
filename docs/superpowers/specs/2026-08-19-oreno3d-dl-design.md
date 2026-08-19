# oreno3d-dl 设计

## 目标

做一个本地命令行工具：输入一批 `https://oreno3d.com/movies/...` 地址（一行一个），从每个页面抽出对应的 Iwara 视频，用用户账号登录后下载 **Source** 画质文件。

成功标准：给一份 oreno3d 地址列表，工具能顺序产出 `downloads/作者/标题 [iwaraID].mp4`；已存在的提示并跳过；单条失败不中断整批；全部结束后给出成功 / 跳过 / 失败统计。

## 已确认方向

- 输入：文件和标准输入都支持；给了文件就读文件，否则读 stdin。
- 凭证：环境变量覆盖配置文件，都没有则交互输入并写入配置。
- 输出：默认 `{输出根目录}/{作者}/{标题} [{iwaraID}].mp4`，输出根目录默认 `./downloads`。
- 已存在：用 iwara ID 判断，默认跳过并打印提示；`--force` 才重下。
- 失败：记录原因，继续下一条；`.part` 用于续传。
- 下载：一次只处理一条，顺序执行。
- 实现：纯 Python 调 Iwara 官方 API，不包 yt-dlp，不走浏览器自动化。

## 范围

包含：

- 可安装的 CLI 命令 `oreno3d-dl`
- oreno3d 页面解析（只认视频页上的正式观看链接）
- Iwara 登录、token 续期、Source 下载、`.part` 续传
- 本机配置与环境变量
- 不连网的单元测试（解析、路径、跳过、清晰度选择、输入清洗）

不包含：

- 并发下载
- 从 oreno3d 作者页 / 搜索页批量展开
- Niconico 或其他非 Iwara 源
- GUI
- 下载后转码

## 项目位置与形态

路径：`~/oreno3d-dl`

- Python 3.11+
- `pyproject.toml` 定义包 `oreno3d_dl` 和入口 `oreno3d-dl`
- 运行时依赖：`httpx`、`beautifulsoup4`
- 开发依赖：`pytest`

布局：

```text
oreno3d-dl/
  pyproject.toml
  README.md
  src/oreno3d_dl/
    __init__.py
    cli.py
    config.py
    oreno3d.py
    iwara.py
    store.py
  tests/
    fixtures/
    test_oreno3d.py
    test_store.py
    test_iwara.py
    test_input.py
  docs/superpowers/specs/
```

## 命令行

```text
oreno3d-dl [选项] [URL文件]
```

| 选项 | 行为 |
| --- | --- |
| 位置参数 `URL文件` | 存在则按行读取；省略则读 stdin |
| `-o` / `--output DIR` | 输出根目录，默认 `./downloads` |
| `--force` | 已存在的成品也重新下载 |
| `--login` | 只写入或更新账号，不下载 |

输入规则：

- 去掉首尾空白
- 空行忽略
- `#` 开头的行忽略
- 其余行必须匹配 `https?://(?:www\.)?oreno3d\.com/movies/<数字id>`（允许末尾多余路径或查询串）
- 非法行记入失败清单，不中止整批

## 模块职责

### cli

读参数、读 URL 列表、驱动主循环、打印每条进度和最终汇总。不直接拼下载 URL。

### config

凭证来源，按优先级：

1. `IWARA_EMAIL` 与 `IWARA_PASSWORD` 都存在 → 使用环境变量，不写盘
2. `~/.config/oreno3d-dl/config.toml` 里有 `email` 和 `password` → 使用文件
3. 否则交互输入，写入该文件，权限 `0600`

`config.toml` 只存邮箱和密码。用户 token 另存在 `~/.config/oreno3d-dl/tokens.json`（权限同样 `0600`），避免和人工编辑的配置混在一起。

`--login` 总是进入交互输入并覆盖配置文件里的账号；不自动登出已缓存 token，下次下载时若登录失败再清 token 重登。下载时若设置了环境变量，仍以环境变量为准，配置文件只是兜底。

### oreno3d

`GET` 页面 HTML，只从正式观看入口抽 Iwara 视频链接：

- `a.pop_separate[href*="iwara.tv/video"]`
- `a.video-watch-btn2[href*="iwara.tv/video"]`

链接必须匹配 `https?://(?:www\.)?iwara\.tv/video/([A-Za-z0-9]+)`。作者评论（`blockquote`）和相关视频区域里的链接一律不用，避免把帖子或推荐视频当成目标。

找不到合法视频链接 → 这条失败，原因写「页面没有 Iwara 视频链接」。

### iwara

登录与下载只走官方 HTTP API：

1. `POST https://api.iwara.tv/user/login`，JSON `{email, password}` → `token`（用户 token，约 3 周）
2. `POST https://api.iwara.tv/user/token`，`Authorization: Bearer <用户token>` → `accessToken`（媒体 token，约 1 小时）
3. `GET https://api.iwara.tv/video/{id}`，带媒体 token → 标题、作者、`fileUrl`
4. 用 `fileUrl` 的 path 最后一段和查询参数 `expires` 计算  
   `X-Version = sha1("{last_path}_{expires}_mSvL05GfEmeEmsEYfGCnVpEjYgTJraJN")`  
   `GET fileUrl` 并带该头，得到清晰度列表
5. 列表中 `name == "Source"` 的那一项；下载 URL 优先 `src.download`，否则 `src.view`。相对协议 `//` 补成 `https:`

若 Iwara 之后更换 `X-Version` 盐值，只改这一处常量。

Token 处理：

- 启动时读 `tokens.json`
- JWT `exp` 早于现在不到 120 秒视为过期
- 用户 token 过期则重新 login；媒体 token 过期则只打 `/user/token`
- login 返回 `invalidLogin` → 整次任务退出，不继续下视频

视频 API 常见错误映射：

| API 信息 | 用户可见原因 |
| --- | --- |
| `errors.notFound` | 视频不存在或已删除 |
| `errors.privateVideo` | 私密视频，当前账号无权访问 |
| 无 `fileUrl` 且无 Source | 没有 Source 画质 |
| 仅有 `embedUrl` | 外链视频，本工具不下 |

请求带常见浏览器 User-Agent。一次只下一个文件，不加额外并发。

### store

路径与落盘：

- 默认根目录：`./downloads`
- 成品：`{root}/{author}/{title} [{id}].mp4`
- 临时：同路径加后缀 `.part`

作者取 Iwara `user.name`，空则 `unknown`。标题取 `title`，空则用视频 ID。

文件名清洗：替换 `/ \ : * ? " < > |` 和控制字符为 `_`，压缩连续空白，去掉首尾空白和点；单段文件名（不含目录）最长 180 字符，超长截断但必须保留 ` [{id}].mp4`。

已存在判定：在输出根目录下递归查找成品文件，文件名包含 `[{id}]` 且不是 `.part`。标题或作者日后改了，只要 ID 相同仍算已存在。命中时打印：

```text
已存在，跳过: {已有文件路径}
```

`--force`：即使已存在也下载到新的 `.part`，成功后再替换旧成品（旧路径与新路径不同时，删除旧成品，只保留新命名）。

续传：`.part` 已有字节则发 `Range: bytes={size}-`。若服务器不支持 Range（200 且从头开始），丢掉 `.part` 重下。下完后将 `.part` 改名为成品。

## 主循环

1. 解析 CLI，读 URL 列表。列表为空则退出码 2，提示用法。
2. `--login`：写配置后退出 0。
3. 加载凭证并确保媒体 token 可用。登录失败退出 1。
4. 对每一条 oreno3d URL：
   1. 解析出 iwara id
   2. 拉 Iwara 元数据
   3. 已存在且非 `--force` → 计入跳过
   4. 下载 Source 到 `.part` 再改名 → 计入成功
   5. 上述任一步可恢复失败 → 计入失败，继续
5. 打印汇总：`成功 N，跳过 M，失败 K`；失败逐条列出 `oreno3d URL` 和原因。
6. 退出码：有失败为 1，否则 0。

## 错误处理

- 单条网络超时或 5xx：该条失败，不重试整批。
- 下载中途断开：保留 `.part`，该条记失败；用户重跑同一条时续传。
- oreno3d 非 200 或 HTML 无法解析：该条失败。
- 磁盘写满等不可恢复 IO：中止整次任务（与登录失败同类，继续没有意义）。

## 测试

全部不连网。

- oreno3d：fixture 含正式观看按钮时抽出正确 id；评论里的 iwara 帖子 / 相关推荐不得被采用；无链接则失败。
- store：非法字符被替换；`[{id}].mp4` 已存在则跳过；`.part` 不算已下载。
- iwara：假文件列表里必须选 `Source`，不能选 preview / 360 / 540。
- 输入：文件和 stdin；空行与 `#` 注释被丢弃。

真实登录和真实下载只做本地手工验收，不进自动测试。

## 手工验收

1. `pip install -e .`
2. `oreno3d-dl --login` 写入账号
3. 准备含 2～3 条真实 oreno3d 地址的 `urls.txt`（至少一条应能下到 Source）
4. `oreno3d-dl urls.txt`，检查目录和文件名
5. 再跑一次，确认打印「已存在，跳过」
6. 人为打断一次下载，再跑，确认从 `.part` 续传
