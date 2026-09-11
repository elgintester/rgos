# Copyright (c) 2026 Ruijie RGOS collection contributors
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = """
name: ruijie
author: Ruijie RGOS collection contributors
short_description: Ruijie RGOS terminal plugin
description:
- Handles CLI prompt detection, paging and privilege escalation for Ruijie
  Networks devices running RGOS (for example RG-S6150 series switches).
- Used automatically by the ansible.netcommon.network_cli connection plugin
  when ansible_network_os is set to elgintester.rgos.ruijie.
"""

import json
import re

from ansible.errors import AnsibleConnectionFailure
from ansible.module_utils.common.text.converters import to_bytes, to_text
from ansible_collections.ansible.netcommon.plugins.plugin_utils.terminal_base import (
    TerminalBase,
)


class TerminalModule(TerminalBase):

    # RGOS 提示符：用户模式 "hostname>"，特权模式 "hostname#"，
    # 配置模式 "hostname(config)#"（最多 3 层嵌套）。
    # 尾部 "$" 锚定是必需的，防止命令输出被误判为提示符。
    terminal_stdout_re = [
        re.compile(rb"[\r\n]?[\w\+\-\.:\/\[\]]+(?:\([^\)]+\)){0,3}(?:[>#]) ?$"),
    ]

    # RGOS 错误签名。
    terminal_stderr_re = [
        re.compile(rb"% ?Error"),
        re.compile(rb"% ?Invalid input", re.I),
        re.compile(rb"% ?Incomplete command", re.I),
        re.compile(rb"% ?Ambiguous command", re.I),
        re.compile(rb"% ?Unknown command", re.I),
        re.compile(rb"% ?Bad secret", re.I),
        re.compile(rb"% ?Can't find"),
    ]

    def on_open_shell(self):
        # 登录后立即禁用分页，否则长命令输出会在 "--More--" 提示符处阻塞会话。
        try:
            self._exec_cli_command(b"terminal length 0")
        except AnsibleConnectionFailure:
            raise AnsibleConnectionFailure(
                "unable to disable paging on Ruijie device"
            )

    def on_become(self, passwd=None):
        """自适应特权提升。

        network_cli 在 ansible_become 为 true 时调用：
        - 提示符已以 '#' 结尾：无需操作，不发送密码
        - 提示符是用户模式 '>'：发送 'enable'，仅在密码提示符实际出现时才回答
        """
        prompt = self._get_prompt()
        if prompt is None:
            raise AnsibleConnectionFailure("unable to get device prompt")
        if prompt.rstrip().endswith(b"#"):
            return
        if not passwd:
            raise AnsibleConnectionFailure(
                "device is in user mode (prompt %r) but no become password was "
                "provided; set ansible_become_password to the level-15 enable "
                "secret" % prompt
            )
        cmd = {"command": "enable"}
        # 正则必须以 ": ?$" 结尾（锚定，最多一个可选空格）：
        # 启用 prompt_retry_check 后，未锚定的正则也会匹配密码被接受后
        # 残留在接收缓冲区中的旧 "Password:" 文本，产生虚假的"密码无效"。
        cmd["prompt"] = r"[\r\n]?(?:.*)[Pp]assword: ?$"
        cmd["answer"] = passwd
        # 设备重新要求密码（密码错误）时快速失败，而不是等待命令超时。
        cmd["prompt_retry_check"] = True
        try:
            self._exec_cli_command(to_bytes(json.dumps(cmd)))
        except AnsibleConnectionFailure as e:
            raise AnsibleConnectionFailure(
                "enable command failed (wrong enable password or prompt not "
                "matched): %s" % to_text(e)
            )
        prompt = self._get_prompt()
        if prompt is None or not prompt.rstrip().endswith(b"#"):
            raise AnsibleConnectionFailure(
                "enable sent but prompt is still %r - the level-15 enable "
                "secret in ansible_become_password is likely wrong" % prompt
            )
        # 某些 RGOS 版本在切换模式时会重置终端参数。
        self._exec_cli_command(b"terminal length 0")

    def on_unbecome(self):
        prompt = self._get_prompt()
        if prompt is None:
            return
        if b"(config" in prompt:
            self._exec_cli_command(b"end")
            self._exec_cli_command(b"disable")
        elif prompt.endswith(b"#"):
            self._exec_cli_command(b"disable")
