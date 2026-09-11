# Ruijie RGOS Ansible Collection

用于通过 SSH 管理运行 **RGOS** 的**锐捷网络**设备（如 RG-S6150 系列交换机），基于 [`ansible.netcommon`](https://galaxy.ansible.com/ansible/netcommon) 的 `network_cli` 连接插件。

无需厂商 SDK、Agent 或专有模块。

## 提供的内容

| 插件/模块 | 类型 | 作用 |
|---|---|---|
| `elgintester.rgos.ruijie` | terminal | 提示符检测、分页控制、自适应 `enable` 提权 |
| `elgintester.rgos.ruijie` | cliconf | 读取 running-config、计算 diff、通过 `configure terminal` 下发配置 |
| `elgintester.rgos.rgos_config` | module | RGOS 原生配置下发，支持 `parents`/`lines`、模板、备份、`save_when` |
| `elgintester.rgos.svc_vlan` | role | 业务 VLAN 全流程编排（VLAN/SVI/端口绑定/AAA/dot1x，五模块独立开关） |

## 依赖与系统要求

### 控制节点

| 项目 | 要求 |
|---|---|
| 操作系统 | **Linux**（Ansible 控制节点不支持原生 Windows，可用 WSL2/VM） |
| ansible-core | **>= 2.16**（netcommon 8.x 的要求） |
| ansible.netcommon | **>= 5.2.0**（推荐 8.6.2） |
| Python | paramiko（`network_cli` 的 SSH 后端） |

### 设备端

| 项目 | 要求 |
|---|---|
| 硬件 | 锐捷 RGOS 系列交换机（已验证 RG-S6150-24VS8CQ-X） |
| RGOS | 12.6(4)B0306T1（经典 CLI：`enable` / `configure terminal` / `% Invalid input` 错误风格） |
| 访问 | SSH 可达，有配置权限的账号 |

### 安装

```bash
ansible-galaxy collection install elgintester.rgos
# netcommon 会作为依赖自动拉取
```

Ubuntu/Debian 用 apt 安装 Ansible 时，paramiko 只是 Recommends 不是 Depends，需单独装：

```bash
apt install -y python3-paramiko
```

### Inventory 最小配置

```yaml
# group_vars/ruijie.yml（必须放在 inventory 文件或 playbook 同级目录）
ansible_connection: ansible.netcommon.network_cli
ansible_network_os: elgintester.rgos.ruijie
ansible_user: admin
ansible_password: "<登录密码>"
ansible_become: true
ansible_become_password: "<level-15 enable 密钥>"
```

## Ansible 对接锐捷 RGOS的tips

以下均在真实 RG-S6150 上实测验证，是 Ansible + RGOS 组合特有的问题，不是代码 bug。

### 1. 环境与依赖

1. **控制节点不能原生跑在 Windows 上**——用 Linux、VM 或 WSL2。
2. **Ubuntu 24.04 的 PEP 668**——root 下 `pip3 install ansible` 会被拒绝（externally-managed-environment），优先用 `apt install ansible` 或 venv。
3. **paramiko 不会被 apt 的 ansible 包自动拉取**（只是 Recommends）——没有它 `network_cli` 连接时直接失败。用 `python3 -c "import paramiko"` 检查。
4. **netcommon 版本影响很大**——apt 自带的 netcommon 5.3.0 只有 `default` cliconf，**完全没有 terminal 插件**，任何 network_os 都会报 `network os ... is not supported`。升级到 8.6.2 解决。注意 `ansible-galaxy collection install` 装在 `~/.ansible/collections`，优先级高于 apt 路径，用 `ansible-galaxy collection list` 确认。
5. **ansible-core >= 2.16 配 netcommon 8.x**——netcommon 8.6.2 的 `meta/runtime.yml` 要求 `>=2.16.0`，旧版本会警告或拒绝。

### 2. 连接与 SSH

6. **旧锐捷固件只提供 `ssh-rsa` 主机密钥**——现代 OpenSSH（>= 8.8）会拒绝，手动 `ssh admin@switch` 报 `no matching host key type found. Their offer: ssh-rsa`。但 Ansible 仍然能连，因为 `network_cli` 用 **paramiko**，自己协商算法集。不要从手动 ssh 失败推断"Ansible 连不上"（反之亦然）。
7. **`ansible_network_os` 必须始终设置**——没有它 `cli_command`/`cli_config` 报 `Unable to automatically determine host network os`。
8. **不要手写提权任务**（`cli_command: enable` + `prompt/answer`）——账号已经是特权模式时设备不会出现 Password 提示符，任务会挂起到超时。用 `ansible_become: true` + terminal 插件的 `on_become()`，它会检查当前提示符并自适应。
9. **enable 密码提示符正则必须行尾锚定**——启用 `prompt_retry_check: true` 时，未锚定的 `Password:` 正则会匹配密码被接受后残留在缓冲区中的旧回显文本，产生虚假的"密码无效"。锚定写法：`[\r\n]?(?:.*)[Pp]assword: ?$`。
10. **`reload` 在回答 `y` 后立即断开会话**——Ansible 任务会显示连接错误（或挂到超时），这是预期的。之后用 `show version` 的 uptime 验证重启。

### 3. RGOS 设备行为

11. **接口名因型号而异**——RG-S6150 的 25G 端口是 `TFGigabitEthernet 0/x`（短名 `TF0/x`），不是 `GigabitEthernet`。写 playbook 前务必用 `show interface status` 确认。
12. **RGOS 不存储默认值行**——`switchport mode access` 是默认值，设备不存储这行，所以文本 diff 永远认为它缺失。幂等性门控不能依赖 diff，必须基于实际配置行判断。
13. **RGOS 没有候选数据存储，没有 commit/rollback**——配置立即生效，中途失败可能已应用部分行。破坏性变更前先备份，`rgos_config` 的 `backup: true` + `save_when: modified` 可以帮你。

### 4. Ansible/Jinja 机制

14. **`group_vars` 只在 inventory 或 playbook 同级目录时被加载**——项目根目录的 `group_vars/` 会被 ad-hoc 命令（基于 cwd）拾取，但**不会**被 `ansible-playbook playbooks/xxx.yml`（基于 playbook 目录）拾取。症状是静默回退到默认连接设置（如 `Connection type ssh is not valid for this module`）。把 `group_vars/` 放在 inventory 文件旁边。
15. **`selectattr` + 含元字符的正则在 Ansible 运行时求值不稳定**——`selectattr('stdout', 'search', '(?m)^\\s*...\\s*$')` 这种组合可能计算为空，导致门控失效。用循环 + `when` 方式替代。
16. **netcommon 8.6.2 的 `cli_config` 有个 cosmetic bug**——它把成功警告存成字符串而不是列表，Ansible 会逐字符迭代，每个字符打印一行 `[WARNING]`。无害但吵。用本 collection 的 `rgos_config` 替代，它从一开始就把 `warnings` 保持为列表。

## svc_vlan Role 简述

面向"每台交换机独立业务 VLAN/SVI/IP + 端口绑定 + AAA/radius + dot1x"的生产场景，role 封装了探测、门控、验证和 `write` 持久化。

五个独立功能模块，全局 `svc_features` 开关 + 设备级 `dev.features` 覆盖，参数缺失报错中止，回滚配什么删什么：

| 模块 | 作用 | 必需参数 |
|---|---|---|
| `vlan` | 创建/删除业务 VLAN | `dev.svc_vlan` |
| `svi` | 创建/删除 VLAN 接口 + IP（主/次） | `dev.svc_ip`, `dev.svc_mask` |
| `port_binding` | 端口绑定/解绑到业务 VLAN | `dev.svc_ports`, `dev.svc_vlan` |
| `aaa` | aaa new-model + radius-server + login/dot1x 方法列表 | `svc_aaa.radius_host`, `radius_key`, `auth_list` |
| `dot1x` | 全局 dot1x authentication + 端口 dot1x port-control | `svc_aaa.dot1x_cmd`, `dot1x_auth_cmd`（**依赖 aaa**） |


## 许可证

GNU General Public License v3.0 or later（见 `LICENSE`）。
