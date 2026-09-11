# Copyright (c) 2026 Ruijie RGOS collection contributors
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = """
name: ruijie
author: Ruijie RGOS collection contributors
short_description: Ruijie RGOS cliconf plugin
description:
- Reads and edits the configuration of Ruijie Networks devices running RGOS
  (for example RG-S6150 series switches) over the ansible.netcommon
  network_cli connection.
- Designed for ansible.netcommon.cli_command / cli_config (the
  network-agnostic modules). Configuration diffs are computed with the
  ansible.netcommon NetworkConfig parser, which tracks RGOS indentation
  levels dynamically (IOS-style, '!' commented, up to two nesting levels on
  the tested RG-S6150), making cli_config idempotent and enabling check mode
  (--check) on supported playbooks.
- RGOS-specific resource modules are not provided yet; validate changes with
  follow-up show commands and asserts when exact verification is required.
"""

import json

from ansible.errors import AnsibleConnectionFailure
from ansible.module_utils.common.text.converters import to_text
from ansible_collections.ansible.netcommon.plugins.module_utils.network.common.config import (
    NetworkConfig,
    dumps,
)
from ansible_collections.ansible.netcommon.plugins.plugin_utils.cliconf_base import (
    CliconfBase,
)
from ansible_collections.elgintester.rgos.plugins.module_utils.rgos import (
    config_ignore_lines,
)


def to_list(val):
    # 把单个值或可迭代对象规范化为普通列表，
    # 这样候选配置始终可以逐行迭代。
    if isinstance(val, (list, tuple, set)):
        return list(val)
    if val is not None:
        return [val]
    return []


class Cliconf(CliconfBase):

    def __init__(self, *args, **kwargs):
        super(Cliconf, self).__init__(*args, **kwargs)
        self._device_info = {}

    def get_device_info(self):
        if not self._device_info:
            self._device_info = {"network_os": "ruijie"}
        return self._device_info

    def get_device_operations(self):
        # 能力声明必须和已实现的方法匹配。下面每个设为 True 的能力
        # 都在本插件中有对应实现（见 get_diff / edit_config）；
        # 对未实现的能力声明 True 会在运行时破坏 cli_config，
        # 因为它会调用基类的桩方法，返回 None。
        return {
            "supports_diff_replace": True,       # get_diff 接受 diff_replace line/block
            "supports_commit": False,            # RGOS 立即应用变更
            "supports_rollback": False,          # RGOS 没有回滚点
            "supports_defaults": False,          # 没有 "show running-config all" 等价物
            "supports_onbox_diff": False,        # 设备没有 onbox diff 命令
            "supports_commit_comment": False,
            "supports_multiline_delimiter": False,
            "supports_diff_match": True,         # get_diff 接受 diff_match
            "supports_diff_ignore_lines": True,  # get_diff 接受 diff_ignore_lines
            "supports_generate_diff": True,      # get_diff 在下面实现
            "supports_replace": False,           # RGOS 不支持全配置替换
        }

    def get_option_values(self):
        # get_diff 接受的 diff_match / diff_replace 有效值，
        # 镜像 RGOS 的 IOS 风格 CLI 语义。
        return {
            "format": ["text"],
            "diff_match": ["line", "strict", "exact", "none"],
            "diff_replace": ["line", "block"],
            "output": [],
        }

    def get_config(self, source="running", flags=None, format=None):
        # RGOS 通过 show 命令暴露两种配置，所以两种源都支持。
        # startup-config 用于模块级 save_when: modified 比较
        # （running vs 已持久化的配置）。
        if source == "running":
            cmd = "show running-config"
        elif source == "startup":
            cmd = "show startup-config"
        else:
            raise AnsibleConnectionFailure(
                "fetching configuration from %s is not supported" % source
            )
        if flags:
            cmd += " " + " ".join(to_list(flags))
        return self.send_command(command=cmd)

    def get_diff(
        self,
        candidate=None,
        running=None,
        diff_match="line",
        diff_ignore_lines=None,
        path=None,
        diff_replace="line",
    ):
        """计算候选配置和 running 配置之间的 diff。

        RGOS 配置是 IOS 风格，用 '!' 注释。在 RG-S6150（RGOS 12.6）上，
        running-config 实测使用两层嵌套——全局命令的子命令缩进一个空格，
        孙命令缩进两个空格——所以它不是统一的单空格缩进。

        这不影响 diff 正确性：NetworkConfig.parse() 动态跟踪每一行的实际
        缩进（通过内部的 'indents' 栈），而不是假设固定宽度。indent=1
        构造参数只被 NetworkConfig.add() 消费，而本插件从不调用它。

        返回的 config_diff 只包含实际需要推送的行，这赋予了 cli_config
        幂等性和可用的 check 模式。候选行仍然必须精确镜像设备自己的缩进，
        因为前导空白不同的行会被视为不同的层级。
        """
        diff = {}
        device_operations = self.get_device_operations()
        option_values = self.get_option_values()

        if candidate is None and device_operations["supports_generate_diff"]:
            raise ValueError(
                "candidate configuration is required to generate diff"
            )

        if diff_match not in option_values["diff_match"]:
            raise ValueError(
                "'match' value %s is invalid, valid values are %s"
                % (diff_match, ", ".join(option_values["diff_match"]))
            )

        if diff_replace not in option_values["diff_replace"]:
            raise ValueError(
                "'replace' value %s is invalid, valid values are %s"
                % (diff_replace, ", ".join(option_values["diff_replace"]))
            )

        # 解析候选配置。RGOS 没有 banner 功能，所以候选就是纯配置文本。
        candidate_obj = NetworkConfig(indent=1)
        candidate_obj.load(candidate)

        if running and diff_match != "none":
            # 和 running 配置比较。RGOS 在 'show running-config' 前加了设备头
            # （见 module_utils.rgos），这些根本不是配置；在这里过滤掉，
            # 防止它们污染 diff。调用者提供的易失模式在上面合并。
            running_obj = NetworkConfig(
                indent=1,
                contents=running,
                ignore_lines=config_ignore_lines(diff_ignore_lines),
            )
            configdiffobjs = candidate_obj.difference(
                running_obj,
                path=path,
                match=diff_match,
                replace=diff_replace,
            )
        else:
            # diff_match "none"（或未提供 running 配置）：无条件推送整个候选。
            configdiffobjs = candidate_obj.items

        diff["config_diff"] = (
            dumps(configdiffobjs, "commands") if configdiffobjs else ""
        )
        return diff

    def edit_config(self, candidate=None, commit=True, replace=None, comment=None):
        resp = {}
        operations = self.get_device_operations()
        self.check_edit_config_capability(
            operations, candidate, commit, replace, comment
        )

        # RGOS 立即应用配置（没有候选数据存储），所以 check 模式通过
        # 什么都不发送来实现。cli_config 在 check 模式下已经跳过 edit_config；
        # 这里保证如果其他调用者传 commit=False 也安全。
        if not commit:
            return {"request": [], "response": []}

        results = []
        requests = []
        # 经典 IOS 风格编辑序列：进入配置模式，推送每一行候选，退出配置模式。
        #
        # 'end' 刻意放在 finally 块中发送。如果设备拒绝某一行候选，
        # send_command 会抛出异常（terminal 插件的 terminal_stderr_re 匹配到），
        # 没有 finally 的话会话会停留在配置模式。network_cli 为 play 的其余
        # 部分复用持久连接，所以后续每个任务都会在错误的 CLI 上下文中运行。
        try:
            self.send_command(command="configure terminal")
            for line in to_list(candidate):
                if not isinstance(line, str):
                    line = to_text(line)
                line = line.strip()
                # 跳过空行、注释行和 stray "end"，防止原始配置块
                # 意外提前终止会话。
                if not line or line.startswith("!") or line == "end":
                    continue
                resp = self.send_command(command=line)
                results.append(resp)
                requests.append(line)
        finally:
            try:
                self.send_command(command="end")
            except AnsibleConnectionFailure:
                # 会话已经不可用（超时、断开）。吞掉这个异常，
                # 让调用者看到原始的配置错误，而不是误导性的清理失败。
                pass
        return {"request": requests, "response": results}

    def get_capabilities(self):
        # 通过持久连接报告给 cli_config / cli_command 的能力。
        # get_diff 注册为额外的 rpc，这样模块层可以发现它。
        result = super(Cliconf, self).get_capabilities()
        result["rpc"] += ["get_diff"]
        result["device_info"] = self.get_device_info()
        result["device_operations"] = self.get_device_operations()
        result.update(self.get_option_values())
        return json.dumps(result)
