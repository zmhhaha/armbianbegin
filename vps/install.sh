#!/usr/bin/env bash
# 国内 VPS 入口机 —— frps + nginx + 通配符证书
#
# 用法（在 VPS 上执行；脚本自己会 sudo，直接 root 跑也行）：
#   sudo bash install.sh stage1     # 只装 frps。备案审核期间就能跑 ✓
#   sudo bash install.sh stage2     # 再装 nginx + 申请通配符证书 + 启用站点。备案通过、80/443 放行后 ✓
#
# 需要的输入（没给会交互式安全读取，不会进 shell 历史）：
#   FRP_TOKEN          必填。隧道共享密钥，从集群 Secret 取，见 README
#   CF_DNS_API_TOKEN   stage2 必填。Cloudflare API Token（Zone → DNS → Edit），用于 DNS-01
#   LE_EMAIL           stage2 必填。Let's Encrypt 通知邮箱
#   BASE_DOMAIN        可选，默认 panghuer.top
#   FRP_VER            可选，默认 0.71.0
#
# 设计文档：../docs/vps-ingress-design.md
set -Eeuo pipefail

FRP_VER="${FRP_VER:-0.71.0}"
BASE_DOMAIN="${BASE_DOMAIN:-panghuer.top}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
STAGE="${1:-}"

# 显式设定 umask：脚本会创建目录与配置文件；若调用者带着 umask 077 进来，
# /etc/frp 会变成 0700 root → 以 frp 用户运行的 frps 打不开配置 ✗
umask 022

log()  { printf '\n\033[1;34m== %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m!! %s\033[0m\n' "$*" >&2; }
die()  { printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "请用 root 运行：sudo bash install.sh ${STAGE:-stage1}"
[[ -n "$STAGE" ]] || die "用法：sudo bash install.sh stage1|stage2"

need_var() {   # need_var NAME "提示语"
  local name="$1" prompt="$2" val
  val="${!name:-}"
  if [[ -z "$val" ]]; then
    [[ -t 0 ]] || die "缺少环境变量 $name（非交互环境必须显式传入）"
    read -rsp "$prompt: " val; echo
  fi
  [[ -n "$val" ]] || die "$name 不能为空"
  printf -v "$name" '%s' "$val"
}

need_var FRP_TOKEN "FRP_TOKEN（从集群 Secret 取，见 README）"

case "$(uname -m)" in
  x86_64|amd64)  FRP_ARCH=amd64 ;;
  aarch64|arm64) FRP_ARCH=arm64 ;;
  *) die "不支持的架构: $(uname -m)" ;;
esac

# ── 系统基础 ────────────────────────────────────────────────────────
base_setup() {
  log "系统基础设置"
  timedatectl set-timezone Asia/Shanghai 2>/dev/null || true
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl tar gettext-base
  apt-get install -y -qq unattended-upgrades >/dev/null 2>&1 \
    || warn "unattended-upgrades 安装失败（不影响主流程）"
}

# ── frps ───────────────────────────────────────────────────────────
install_frps() {
  log "安装 frps ${FRP_VER}（${FRP_ARCH}）"
  if [[ ! -x /usr/local/bin/frps ]] || ! /usr/local/bin/frps --version 2>/dev/null | grep -q "$FRP_VER"; then
    local tmp; tmp="$(mktemp -d)"
    curl -fL --retry 3 \
      "https://github.com/fatedier/frp/releases/download/v${FRP_VER}/frp_${FRP_VER}_linux_${FRP_ARCH}.tar.gz" \
      -o "${tmp}/frp.tgz"
    tar -xzf "${tmp}/frp.tgz" -C "$tmp"
    install -m 0755 "${tmp}/frp_${FRP_VER}_linux_${FRP_ARCH}/frps" /usr/local/bin/frps
    rm -rf "$tmp"
  else
    log "frps ${FRP_VER} 已安装，跳过下载"
  fi

  log "创建专用系统用户 frp（不用 root 跑 ✓）"
  id -u frp >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin frp

  log "渲染 /etc/frp/frps.toml（token 由环境变量注入，不落仓库 ✓）"
  install -d -m 0755 -o root -g root /etc/frp   # 显式权限，不受 umask 影响 ✓
  local rendered; rendered="$(mktemp)"
  FRP_TOKEN="$FRP_TOKEN" envsubst '${FRP_TOKEN}' \
    < "${SCRIPT_DIR}/frps.toml.template" | tr -d '\357\273\277\r' > "$rendered"
  if [[ -f /etc/frp/frps.toml ]] && cmp -s "$rendered" /etc/frp/frps.toml; then
    log "配置未变化，无需重启"
    rm -f "$rendered"
  else
    install -m 0640 -o root -g frp "$rendered" /etc/frp/frps.toml
    rm -f "$rendered"
    NEED_RESTART=1
  fi

  log "注册 systemd 服务（最小权限：非 root、无 capability、只读系统盘）"
  local unit; unit="$(mktemp)"
  cat > "$unit" <<'EOF'
[Unit]
Description=frp server (reverse tunnel entry)
After=network-online.target
Wants=network-online.target

[Service]
User=frp
Group=frp
ExecStart=/usr/local/bin/frps -c /etc/frp/frps.toml
Restart=always
RestartSec=5
LimitNOFILE=1048576

# 加固：端口都 >1024，不需要任何 capability
NoNewPrivileges=yes
CapabilityBoundingSet=
AmbientCapabilities=
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
RestrictAddressFamilies=AF_INET AF_INET6
RestrictNamespaces=yes
LockPersonality=yes

[Install]
WantedBy=multi-user.target
EOF
  if [[ -f /etc/systemd/system/frps.service ]] && cmp -s "$unit" /etc/systemd/system/frps.service; then
    rm -f "$unit"
  else
    install -m 0644 "$unit" /etc/systemd/system/frps.service
    rm -f "$unit"
    systemctl daemon-reload
  fi
  systemctl enable frps >/dev/null 2>&1 || true
  systemctl restart frps

  sleep 2
  systemctl is-active --quiet frps || { journalctl -u frps -n 40 --no-pager; die "frps 启动失败"; }
  log "frps 状态"
  systemctl is-active frps
  ss -ltnp 2>/dev/null | grep -E ':(7000|8080)\b' || warn "没有看到 7000/8080 监听，请查看 journalctl -u frps"
  warn "别忘了在【腾讯云控制台 → 轻量应用服务器 → 防火墙】放行 TCP 7000（80/443 留到 stage2）"
}

# ── nginx + 通配符证书 ──────────────────────────────────────────────
install_nginx_and_cert() {
  need_var CF_DNS_API_TOKEN "CF_DNS_API_TOKEN（Cloudflare API Token，Zone:DNS:Edit）"
  need_var LE_EMAIL "Let's Encrypt 通知邮箱"

  log "安装 nginx / certbot / Cloudflare DNS 插件"
  export DEBIAN_FRONTEND=noninteractive
  apt-get install -y -qq nginx certbot python3-certbot-dns-cloudflare

  log "写入 Cloudflare 凭据（600，仅 root 可读）"
  mkdir -p /etc/letsencrypt
  printf 'dns_cloudflare_api_token = %s\n' "$CF_DNS_API_TOKEN" > /etc/letsencrypt/cloudflare.ini
  chmod 600 /etc/letsencrypt/cloudflare.ini

  log "申请通配符证书 *.${BASE_DOMAIN}（DNS-01，不依赖 80/443 对外）"
  if [[ -d "/etc/letsencrypt/live/${BASE_DOMAIN}" ]]; then
    log "证书已存在，跳过申请（续期交给 certbot.timer ✓）"
  else
    certbot certonly --non-interactive --agree-tos -m "$LE_EMAIL" \
      --dns-cloudflare --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini \
      --dns-cloudflare-propagation-seconds 30 \
      -d "${BASE_DOMAIN}" -d "*.${BASE_DOMAIN}"
  fi

  log "安装站点配置"
  local rendered; rendered="$(mktemp)"
  BASE_DOMAIN="$BASE_DOMAIN" envsubst '${BASE_DOMAIN}' \
    < "${SCRIPT_DIR}/nginx/default.conf.template" | tr -d '\357\273\277\r' > "$rendered"
  install -m 0644 "$rendered" "/etc/nginx/sites-available/${BASE_DOMAIN}.conf"
  rm -f "$rendered"
  ln -sf "/etc/nginx/sites-available/${BASE_DOMAIN}.conf" "/etc/nginx/sites-enabled/${BASE_DOMAIN}.conf"
  rm -f /etc/nginx/sites-enabled/default
  mkdir -p /var/www/certbot

  log "校验并加载 nginx"
  nginx -t || die "nginx 配置校验失败（先看上面的报错）"
  systemctl reload nginx || systemctl restart nginx
  sleep 1
  systemctl is-active --quiet nginx || die "nginx 未运行"

  log "本机自检（应该看到 302 = 服务的登录跳转）"
  curl -sk -o /dev/null -w '  https://127.0.0.1 (Host: dsh.%{host}) -> HTTP %{http_code}\n' \
    -H "Host: dsh.${BASE_DOMAIN}" "https://127.0.0.1/" 2>/dev/null \
    || warn "自检请求失败（正常也可能只是对应服务还没接入隧道）"
  warn "确认腾讯云防火墙已放行 TCP 80 与 443，然后去 Cloudflare 把域名改成 A 记录（DNS only）"
}

base_setup
case "$STAGE" in
  stage1) install_frps ;;
  stage2) install_frps; install_nginx_and_cert ;;
  *) die "未知阶段: $STAGE（可用 stage1 / stage2）" ;;
esac

log "完成 ✓ 运维手册见 README.md"
