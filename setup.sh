#!/bin/bash
set -e

echo ">>> 配置 pip 源..."
pip config set global.index-url http://nexus.sii.shaipower.online/repository/pypi/simple
pip config set global.trusted-host nexus.sii.shaipower.online

echo ">>> 配置 apt 源..."
cat >/etc/apt/sources.list <<EOF
deb http://nexus.sii.shaipower.online/repository/ubuntu/ jammy main restricted universe multiverse
deb http://nexus.sii.shaipower.online/repository/ubuntu/ jammy-updates main restricted universe multiverse
deb http://nexus.sii.shaipower.online/repository/ubuntu/ jammy-backports main restricted universe multiverse
deb http://nexus.sii.shaipower.online/repository/ubuntu/ jammy-security main restricted universe multiverse
EOF

echo ">>> 更新 apt 缓存..."
apt-get update -y

echo ">>> 安装基础网络工具..."
export DEBIAN_FRONTEND=noninteractive
apt-get install -y \
    openssh-server \
    iputils-ping iputils-tracepath traceroute \
    net-tools iproute2 \
    dnsutils curl wget
    
echo ">>> 设置SSH公钥..."
# 公钥列表，每行一把公钥
PUBKEYS=(
"ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQDdRxnOzOfXJkk1kzXcF2FmPm5+s4SoGcM1IBWUD0sR8vraUiV5C4Ky+ejv6MNDRynFXCEXCDh0bHkuClvRWkf4MdF1vUkQWOBWBf7AjOAl/g4CM5aomt0tP2NseU7s8D4JwbMacQYm12/neywtIL5V/90xB8gba6rJTQJJif3yVkFnTvoaDLRtpUey3aT1iDElL+aPNLMy87p6VqAX2UOpT/ikcktNIoJjgFJoXR4xtsjNq7/bJ4ISnXmVViVh28hyZClO4N+CMG6caZ2igF5vYh9ZLvB6bEeaDtKR4VzUjt7afeohiwM7TGiue/aHs4Z/k9yR3xasllAp68ZKsLrBy0JIq6LEDjKaa5e4veF2k25ZifTcaBIcfFF11WvPaU+HqxTxwyN7yHhvU+X3EkV28l3kxA3MUDMi+nqbmEVHg1xhm/rRQ4w4bFvEZU/kcbJnzgUubKbeUJjnjmzXF1LIUTcBZ7Z1te5V3A+kJsK6AXSd//f4VppaxQwAJ/aoA01tPGptHtvn6hF3+CixM4+XY0gVexCJSPaI9ZH5ElI0OWIFYALK+8fAgQKFnpqPANBO7KMGMYRxIcW7XdNQy2q2Q7kwWjkkEcMu+b6rZr/FSL+xLRfEqaje0wtrH4C6H60KH28AOKmgQui7v2qxDqITImEXcGSjrKHyBRYo87plzw== mhjiang0408@outlook.com",
"ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQDN/bsyGMDi4+6aJqQeCI5nB+69JYZbkbQHkqYQ/mB/L1gEKMSLk6S94x8qmI9kGvKjk/5rI34xTfTDsHcJUEdboKlYdYoepvGATdi6YGTyxAwShbyAvz7dezwame1MC9VQiPvTlHA4uOBDXGv2fXQccAafFZvbburEMt0PfNZADd44FnrrzPr0mPGmxHc1fI6rRKEYeofyCO8wNooNBUMJbk1fU2ACI+8kxwPx5cZcFFnRxMPZDah43Bj/pqFwIMauSwLZo01D+c6RysVwq1MGMMqmEH2/q/8casz+tXhXWkCV4P72tnYf6EmzQwfyug3UjQZkFqefk8lYX9Icn7+HRtYuew+t59FdWpW4ECrqw797sR1kFuyFelCyrY+uj8PCJeQb+CvL6ltIJOz8T42RINqPVgcBgRs0oBpnPDqnelsVy7Uv8GKCnJYQ/pp2Egty5So5o4qmasbnke+xkN1/4zudCtmVoioGkA0kAvaZvbMw+HST5OuMCp0Y4B1fUjc= mhjiang0408@sjtu.edu.cn"
# 可以继续添加更多公钥
)

AUTHORIZED_KEYS="$HOME/.ssh/authorized_keys"

# 创建 .ssh 目录（如果不存在）
mkdir -p "$HOME/.ssh"

# 循环添加公钥，避免重复
for key in "${PUBKEYS[@]}"; do
    grep -qxF "$key" "$AUTHORIZED_KEYS" 2>/dev/null || echo "$key" >> "$AUTHORIZED_KEYS"
done

# 设置权限
chmod 700 "$HOME/.ssh"
chmod 600 "$AUTHORIZED_KEYS"

echo "All public keys installed successfully to $AUTHORIZED_KEYS"


echo ">>> 配置完成！"