# Copyright (c) 2026 Ruijie RGOS collection contributors
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

"""RGOS 配置文本比较的公共辅助函数。

为什么需要这个模块
------------------
RGOS 的 `show running-config` 和 `show startup-config` 即使配置完全相同，
输出也不是字节一致的，因为 running 输出带有 startup 没有的设备头信息：

    Building configuration...
    Current configuration: 9051 bytes

ansible.netcommon 的 NetworkConfig 已经过滤了 "Building configuration" 和
*Cisco 风格*的 "Current configuration : N bytes"——注意 netcommon 的
DEFAULT_IGNORE_LINES_RE 中冒号前有一个空格。而 RGOS 输出的冒号前没有空格，
所以 netcommon 的正则匹配不到，头信息行会泄漏到解析后的配置中。

后果：running 和 startup 的任何 SHA1 比较永远不会报告"相等"，
导致 `save_when: modified` 的行为和 `save_when: always` 完全一样
（在 D2 刚保存后立即运行 D3 的 validate_03 时观察到此问题）。

以下模式是 RGOS 特有的补充。它们会和调用者提供的 `diff_ignore_lines`
合并，所以用户自定义的模式仍然有效。
"""

# 设备输出装饰和模式标记——它们不是配置，且 netcommon 的
# DEFAULT_IGNORE_LINES_RE 对 RGOS 没有覆盖。
RGOS_CONFIG_IGNORE_LINES = [
    # RGOS 写 "Current configuration: N bytes" 时冒号前没有空格，
    # 和 netcommon 期望的 Cisco 形式不同。两侧灵活的 \s* 既能匹配
    # RGOS，也能兼容 Cisco 的拼写。
    r"Current configuration\s*:\s*\d+\s*bytes",
    # 转储末尾的模式退出标记。它是 CLI 命令，不是配置，
    # 且在两个 show 命令之间可能存在差异。
    r"^end$",
]


def config_ignore_lines(extra=None):
    """返回 RGOS 默认模式和调用者提供的模式合并后的列表。

    NetworkConfig 自己编译纯字符串并添加到模块级的
    DEFAULT_IGNORE_LINES_RE 集合中，所以每次传入新列表都是安全且幂等的。
    """
    patterns = list(RGOS_CONFIG_IGNORE_LINES)
    if extra:
        patterns.extend(extra)
    return patterns
