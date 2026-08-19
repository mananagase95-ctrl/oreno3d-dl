# oreno3d-dl

从 oreno3d.com 视频页提取 Iwara 地址，登录后下载 Source 画质。

需要 Python 3.11+。

## 安装

```bash
pip install -e .
```

开发依赖（pytest）：

```bash
pip install -e ".[dev]"
```

## 登录

```bash
oreno3d-dl --login
```

账号写入 `~/.config/oreno3d-dl/config.toml`（权限 0600）。也可用环境变量，且优先于配置文件，不会写盘：

```bash
export IWARA_EMAIL="you@example.com"
export IWARA_PASSWORD="secret"
```

## 用法

URL 文件一行一个地址。空行和 `#` 开头的注释会被忽略。

```bash
oreno3d-dl urls.txt
oreno3d-dl < urls.txt
oreno3d-dl -o /path/to/out urls.txt
oreno3d-dl --force urls.txt
```

地址需为 `https://oreno3d.com/movies/<数字id>`。

## 输出

默认：

```text
./downloads/{作者}/{标题} [{iwaraID}].mp4
```

输出根目录可用 `-o` / `--output` 修改。已存在相同 iwara ID 的成品会打印 `已存在，跳过` 并跳过；`--force` 会重新下载。
