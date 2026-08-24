# SmartRoute 部署与 GitHub 同步

## 1. 推荐协作方式

把 `yara1006/smartroute` 作为主仓库，你的账号 `dingxiangyue313` 建一个同名 fork 或独立仓库。日常开发只维护一份本地代码，通过两个 remote 同步：

```bash
cd /Users/dingxiangyue/Documents/Codex/2026-05-20/files-mentioned-by-the-user-smartroute/smartroute
git init
git branch -M main
git remote add origin git@github.com:yara1006/smartroute.git
git remote add mine git@github.com:dingxiangyue313/smartroute.git
git add .
git commit -m "feat: smart route product demo"
git push -u origin main
git push -u mine main
```

如果你没有 `yara1006/smartroute` 的写权限，就先推到你的 `mine`，再在 GitHub 上提 Pull Request 给队友仓库。

## 2. 服务器首次部署

服务器建议使用 Ubuntu。以下命令中的用户名如果不是 `root`，替换成你的服务器用户名。

```bash
ssh root@42.193.138.163
apt update
apt install -y git nginx python3 python3-venv python3-pip nodejs npm
mkdir -p /opt
cd /opt
git clone https://github.com/yara1006/smartroute.git
cd /opt/smartroute
```

创建后端环境变量：

```bash
nano /opt/smartroute/.env
```

填入：

```bash
DEEPSEEK_API_KEY=你的 DeepSeek Key
DEEPSEEK_CHAT_MODEL=deepseek-chat
DEEPSEEK_ROUTE_MODEL=deepseek-reasoner
DEEPSEEK_BASE_URL=https://api.deepseek.com
AMAP_WEB_SERVICE_KEY=你的高德 Web 服务 Key
```

创建前端生产环境变量：

```bash
nano /opt/smartroute/web/.env.production
```

填入：

```bash
VITE_API_BASE=
VITE_AMAP_KEY=你的高德 JS API Key
VITE_AMAP_SECURITY_JS_CODE=你的高德 JS 安全密钥
```

注意：高德 JS API Key 的域名白名单要包含 `42.193.138.163`。如果后续绑定域名，也要把域名加入白名单。

后端的 `AMAP_WEB_SERVICE_KEY` 必须是高德控制台里“服务平台 = Web服务”的 Key，不能使用“Web端(JS API)”Key。若误用 JS Key，高德 Web 服务会返回：

```text
USERKEY_PLAT_NOMATCH
infocode: 10009
```

验证后端高德 Key：

```bash
cd /opt/smartroute
source .env
curl "https://restapi.amap.com/v5/place/text?keywords=北京金鱼胡同&region=北京&page_size=3&key=$AMAP_WEB_SERVICE_KEY"
```

返回 `status=1` 才说明服务器可调用真实 POI 搜索。

## 3. 构建并启动服务

```bash
cd /opt/smartroute
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
cd web
npm ci
npm run build
cd ..
```

配置 systemd：

```bash
cp /opt/smartroute/deploy/smartroute-api.service.example /etc/systemd/system/smartroute-api.service
systemctl daemon-reload
systemctl enable --now smartroute-api
```

配置 Nginx：

```bash
cp /opt/smartroute/deploy/nginx.conf.example /etc/nginx/sites-available/smartroute
ln -sf /etc/nginx/sites-available/smartroute /etc/nginx/sites-enabled/smartroute
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx
```

访问：

```text
http://42.193.138.163/
```

部署后验证：

```bash
curl http://127.0.0.1:8000/api/health
```

期望看到：

```json
{"amap_web_service":"configured","deepseek":"configured"}
```

真实地点链路验证：

```bash
curl -sS -X POST http://127.0.0.1:8000/api/plan \
  -H 'Content-Type: application/json' \
  -d '{"query":"在北京金鱼胡同附近玩3个小时，帮我规划成一条可执行路线","user_id":"deploy-check","route_context":{"source":"xiaotuan","city_hint":"北京","anchor_text":"北京金鱼胡同"}}'
```

响应中的候选或路线站点应包含 `source: "amap"` 且区域为北京/东城区附近。若高德调用失败，系统应返回失败 trace，不应返回上海本地 POI。

## 4. 自动部署

推荐把自动部署绑定到主仓库 `yara1006/smartroute` 的 `main` 分支。

在服务器上确保脚本可执行：

```bash
chmod +x /opt/smartroute/scripts/server_deploy.sh
```

在 GitHub 仓库的 `Settings -> Secrets and variables -> Actions` 添加：

```text
SERVER_HOST=42.193.138.163
SERVER_USER=root
SERVER_SSH_KEY=服务器 SSH 私钥
APP_DIR=/opt/smartroute
```

以后只要 push 到 `main`，GitHub Actions 会登录服务器执行 `scripts/server_deploy.sh`，自动拉代码、安装依赖、构建前端、重启后端和 Nginx。

## 5. 日常更新

本地开发完成后：

```bash
git status
git add .
git commit -m "fix: describe change"
git push origin main
git push mine main
```

如果 Actions 配好，服务器会自动更新。没配 Actions 时，在服务器执行：

```bash
cd /opt/smartroute
bash scripts/server_deploy.sh
```

如果这是从旧仓库第一次升级，新提交会把旧仓库里误提交的 `web/.env.production` 从 Git 追踪中移除。`scripts/server_deploy.sh` 会尽量在部署前备份并恢复这个文件；如果文件已经丢失，重新按第 2 节创建一次即可。

## 6. 安全边界

- 不提交 `.env`、`web/.env.local`、`web/.env.production`。
- 不把服务器密码、DeepSeek Key、高德 Key 写入 README、代码或提交记录。
- 最好改用 SSH key 登录服务器，并把服务器密码更新一次。
- GitHub Actions 只保存 SSH 私钥到仓库 Secrets，不写入源码。
