# Playwright 网页抓取API

基于FastAPI的网页抓取服务，使用Playwright和Chromium浏览器。

## 功能特性
- 抓取网页并返回HTML内容
- 内置缓存（1小时有效期）
- 并发控制（最多50个并发请求）
- 自动管理浏览器实例

## API文档

### GET /scrape
抓取指定URL的网页内容

**参数:**
- `url` (必填): 要抓取的URL（必须包含http://或https://）

**响应:**
- 返回网页HTML内容（纯文本格式）
- 400 Bad Request 如果URL格式无效
- 500 Internal Server Error 如果抓取失败

**使用示例:**
```bash
curl "http://localhost:8000/scrape?url=https://example.com"
```

### GET /preload/list
获取所有预加载URL的状态

**响应:**
- JSON格式返回预加载URL列表，包含以下字段：
  - `url`: 预加载URL
  - `last_updated`: 最后更新时间戳
  - `content_length`: 缓存内容长度

**使用示例:**
```bash
curl "http://localhost:8000/preload/list"
```

### POST /preload/update
更新预加载URL配置

**参数:**
- `urls` (必填): 需要预加载的URL列表（JSON数组格式）

**响应:**
- JSON格式返回操作结果，包含：
  - `status`: 操作状态
  - `count`: 当前预加载URL总数
  - `added`: 新增URL数量
  - `removed`: 移除URL数量

**使用示例:**
```bash
curl -X POST -H "Content-Type: application/json" -d '["https://example.com"]' "http://localhost:8000/preload/update"
```

## 安装部署

1. 构建Docker镜像:
```bash
docker build -t playwright-scraper .
```

2. 运行容器:
```bash
docker run -p 8000:8000 playwright-scraper
```

## 配置选项

环境变量:
- `PORT` (默认: 8000) - API服务端口
- `CONCURRENCY_LIMIT` (默认: 50) - 最大并发请求数

## 系统要求
- Python 3.12.9
- Playwright
- Chromium浏览器
- FastAPI框架
- Uvicorn服务器

完整依赖列表请参考[requirements.txt](requirements.txt)