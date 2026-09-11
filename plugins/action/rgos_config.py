# Copyright (c) 2026 Ruijie RGOS collection contributors
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible.errors import AnsibleError
from ansible.module_utils.common.text.converters import to_text
from ansible_collections.ansible.netcommon.plugins.action.network import (
    ActionModule as ActionNetworkModule,
)


class ActionModule(ActionNetworkModule):
    """elgintester.rgos.rgos_config 的 action 插件。

    继承 ansible.netcommon 的 network action 插件，免费获得两个
    控制节点端行为：

    - src：文件/模板在这里读取和渲染，渲染后的文本作为候选配置交给模块
    - backup：模块在 __backup__ 下返回 running 配置，本类把它写入磁盘，
      遵循 backup_options

    设置 _config_module 是启用父类中这两条路径的关键。
    """

    def run(self, tmp=None, task_vars=None):
        del tmp  # 不再使用，保留仅为签名兼容

        self._config_module = True

        # rgos_config 只在 network_cli 上有意义；用清晰的消息失败，
        # 而不是让人困惑的下游错误。
        if self._play_context.connection.split(".")[-1] != "network_cli":
            return {
                "failed": True,
                "msg": "Connection type %s is not valid for the rgos_config "
                "module. Set ansible_connection to "
                "ansible.netcommon.network_cli for this host."
                % self._play_context.connection,
            }

        try:
            return super(ActionModule, self).run(task_vars=task_vars)
        except AnsibleError as exc:
            return {"failed": True, "msg": to_text(exc)}
