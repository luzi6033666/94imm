94imm 现维护版。当前仓库已经不再是最初的单一旧爬虫版本，而是包含：

- Django 4.2 应用层改造
- gunicorn + systemd 的应用运行方式
- 多源 crawler 框架
- 去重、坏图清理、关键词过滤
- 生产/灰度都已验证过的一组稳定 cos 源

# 当前技术栈

- Python 3.11+
- Django 4.2
- gunicorn
- PyMySQL
- BeautifulSoup4
- Pillow

依赖见 [requirements.txt](/root/remote_work/mm187/requirements.txt)。

# 当前目录约定

默认部署目录按 `/opt/mm187` 设计，相关文件已经按这个路径写好：

- 应用服务配置：[gunicorn.conf.py](/root/remote_work/mm187/gunicorn.conf.py)
- crawler 服务配置：[deploy/mm187-crawler.service](/root/remote_work/mm187/deploy/mm187-crawler.service)
- crawler 轮转脚本：[cron.sh](/root/remote_work/mm187/cron.sh)
- 应用控制脚本：[run.sh](/root/remote_work/mm187/run.sh)

# 参数配置

主配置文件是 [config.py](/root/remote_work/mm187/config.py)。

主要配置项：

```python
mysql_config = {
    "ENGINE": "django.db.backends.mysql",
    "NAME": "mm",
    "USER": "mm",
    "PASSWORD": "your-password",
    "HOST": "127.0.0.1",
    "PORT": "3306",
}

allow_url = ["your-domain.example", "127.0.0.1"]
cache_time = 300
templates = "zde"
site_name = "爱妹子"
site_url = "https://your-domain.example"
key_word = "爱妹子,美女写真,性感美女,美女图片,高清美女"
description = "每日分享最新最全的美女图片和高清性感美女图片"
email = "admin@example.com"
debug = False
friendly_link = [{"name": "NodeSeek", "link": "https://nodeseek.com"}]
```

# 安装

```bash
git clone https://github.com/luzi6033666/94imm.git
cd 94imm
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

如果使用 MySQL，请确认数据库已创建且 `config.py` 中的连接信息正确。

# 运行应用

当前仓库默认通过 systemd 管理应用服务 `mm187`：

```bash
./run.sh start
./run.sh restart
./run.sh stop
./run.sh status
./run.sh clear
```

`run.sh` 是对 systemd 服务的薄封装，不再直接自己拉起 `uwsgi` 进程。

# 运行 crawler

crawler 服务默认也是 systemd 管理：

- 服务文件：[deploy/mm187-crawler.service](/root/remote_work/mm187/deploy/mm187-crawler.service)
- 执行入口：[cron.sh](/root/remote_work/mm187/cron.sh)

当前默认 live 轮转源：

- `crawler_meirentu.py`
- `crawler_huotumao.py`
- `crawler_coserlab.py`
- `crawler_miaoyinshe.py`
- `crawler_miaohuaying.py`
- `crawler_xiaomiaoshe.py`

健康检查入口：

- [crawler/source_health.py](/root/remote_work/mm187/crawler/source_health.py)

# crawler 特性

当前 crawler 层包含：

- 多源轮转抓取
- 标题 + 首图哈希去重
- 坏图/空页清理
- 关键词过滤
- 目录页跳过
- 每源扫描窗口与成功入库上限分离

公共逻辑：

- [crawler/common.py](/root/remote_work/mm187/crawler/common.py)
- [crawler/dedupe.py](/root/remote_work/mm187/crawler/dedupe.py)
- [crawler/gallery_source.py](/root/remote_work/mm187/crawler/gallery_source.py)

内容过滤脚本：

- [purge_blocked_content.py](/root/remote_work/mm187/purge_blocked_content.py)

空页清理脚本：

- [purge_bad_pages.py](/root/remote_work/mm187/purge_bad_pages.py)

# 关键词过滤

当前会在 crawler 入库前拦截这些明显不应保留的关键词：

- `伪娘`
- `男娘`
- `女装大佬`
- `男扮女装`
- `扶她`
- `futanari`
- `cd变装`

如果历史数据里已经存在命中内容，可执行：

```bash
python3 purge_blocked_content.py
```

# 模板与页面层

当前页面层已经去掉旧版 `dj-pagination` 依赖，使用应用内分页逻辑。

核心文件：

- [images/views.py](/root/remote_work/mm187/images/views.py)
- [templates/zde/index.html](/root/remote_work/mm187/templates/zde/index.html)
- [templates/zde/page.html](/root/remote_work/mm187/templates/zde/page.html)
- [templates/zde/pagination.html](/root/remote_work/mm187/templates/zde/pagination.html)

# 说明

- 仓库里仍然保留了一些 legacy crawler 文件，未必都在默认 live 轮转中。
- 默认 live 轮转只放目前实际验证过相对稳定的源。
- 如果要继续优化图片存储、缩略图或 CDN，参考 [OPTIMIZATION_PLAN.md](/root/remote_work/mm187/OPTIMIZATION_PLAN.md)。
