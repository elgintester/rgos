#!/usr/bin/python
# Copyright (c) 2026 Ruijie RGOS collection contributors
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = """
module: rgos_config
author: Ruijie RGOS collection contributors
short_description: Manage the configuration of Ruijie devices running RGOS
description:
- Pushes configuration to Ruijie Networks devices running RGOS over the
  ansible.netcommon network_cli connection, using this collection's cliconf
  plugin for diffing.
- Only the lines that actually differ from the running configuration are
  sent, so repeated runs are idempotent and C(--check) works.
- Supports C(save_when) to persist changes with RGOS C(write), which removes
  the need for a separate save task.
- This module is the RGOS-native replacement for
  C(ansible.netcommon.cli_config). Prefer it on Ruijie devices.
version_added: 0.2.0
options:
  lines:
    description:
      - The ordered set of configuration commands to push to the device.
      - Lines are compared against the running configuration and only the
        differing ones are sent.
      - Each line must mirror the device representation. When I(parents) is
        used, do NOT indent the lines yourself - indentation is derived from
        the number of parents.
    type: list
    elements: str
    aliases:
      - commands
  parents:
    description:
      - The ordered set of parent commands that put the device into the
        context I(lines) belong to, for example
        C(interface TFGigabitEthernet 0/15).
      - Nesting depth equals the number of parents, and RGOS presents one
        space of indentation per level in C(show running-config), so the
        candidate is built with one leading space per parent.
    type: list
    elements: str
  src:
    description:
      - A configuration file or Jinja2 template on the control node. Its
        rendered content is used as the candidate configuration.
      - Mutually exclusive with I(lines) and I(content).
    type: str
  content:
    description:
      - Configuration text used directly as the candidate, rather than a file
        path.
      - This is the recommended way to apply templated configuration - render
        with C(ansible.builtin.template) or write the block inline in the
        playbook. Indentation must match how the device presents these lines
        in C(show running-config).
      - Mutually exclusive with I(lines) and I(src).
      - Takes precedence over I(src) if both are somehow present.
    type: str
  before:
    description:
      - Commands pushed before the candidate, regardless of the diff result.
      - Not sent in check mode.
    type: list
    elements: str
  after:
    description:
      - Commands pushed after the candidate, regardless of the diff result.
      - Not sent in check mode.
    type: list
    elements: str
  match:
    description:
      - How candidate lines are matched against the running configuration.
      - C(line) matches each line individually, C(strict) also respects
        position, C(exact) requires an identical block, C(none) pushes
        everything unconditionally.
    type: str
    default: line
    choices:
      - line
      - strict
      - exact
      - none
  replace:
    description:
      - C(line) pushes only the differing lines. C(block) pushes the whole
        parent block when any line inside it differs.
    type: str
    default: line
    choices:
      - line
      - block
  diff_ignore_lines:
    description:
      - Lines in the running configuration to ignore while diffing. Use this
        for volatile content such as timestamps or counters that would
        otherwise make every run report a change.
    type: list
    elements: str
  backup:
    description:
      - Create a backup of the running configuration on the control node
        before any change is applied.
    type: bool
    default: false
  backup_options:
    description:
      - Where the backup file is written. Only used when I(backup) is true.
    type: dict
    suboptions:
      filename:
        description:
          - Backup file name. Defaults to C(<hostname>_config.<date>@<time>).
        type: str
      dir_path:
        description:
          - Directory to write the backup into. Created when missing. Defaults
            to a C(backup) folder next to the playbook or role.
        type: path
  save_when:
    description:
      - When to persist the running configuration with the RGOS C(write)
        command.
      - C(never) leaves changes in running-config only, so a device reboot
        reverts them. This is the default and the safest choice.
      - C(always) saves on every run, even when nothing changed.
      - C(changed) saves only when this task pushed something to the device.
      - C(modified) saves whenever the running configuration differs from the
        persisted one, comparing both by SHA1 - so it also catches changes
        made outside Ansible, and makes a standalone "ensure the device is
        saved" task meaningful.
      - The C(changed) and C(modified) semantics match cisco.ios ios_config,
        so playbooks ported from Cisco behave the same way.
    type: str
    default: never
    choices:
      - always
      - never
      - modified
      - changed
notes:
  - RGOS has no candidate datastore and no commit or rollback. Every accepted
    line takes effect immediately, so a run that fails partway through may
    leave earlier lines applied. Validate before pushing and keep I(backup)
    enabled for changes that matter.
  - Requires privilege escalation for configuration mode. Set
    C(ansible_become=true) (and C(ansible_become_password) when the account
    lands in user mode) in your inventory variables.
"""

EXAMPLES = """
- name: Push lines with a parent context
  elgintester.rgos.rgos_config:
    lines:
      - switchport mode access
      - switchport access vlan 100
    parents: interface TFGigabitEthernet 0/15

- name: Create a VLAN from raw lines (indent children yourself)
  elgintester.rgos.rgos_config:
    lines:
      - vlan 100
      - " name ANSIBLE_TEST"

- name: Push a template and persist it when something changed
  elgintester.rgos.rgos_config:
    src: templates/standard_access.j2
    backup: true
    save_when: modified

- name: Push a rendered block inline (batch changes)
  # content is pre-formatted text, so the caller controls indentation and
  # parents is not used. Ideal for loop-generated batch configuration.
  elgintester.rgos.rgos_config:
    content: |
      vlan 100
       name ANSIBLE_TEST
      vlan 101
       name ANSIBLE_TEST_2
      interface TFGigabitEthernet 0/15
       switchport mode access
       switchport access vlan 100

- name: Push a rendered template file via the template lookup
  elgintester.rgos.rgos_config:
    content: "{{ lookup('ansible.builtin.template', 'templates/access.j2') }}"

- name: Dry run to review what would change
  elgintester.rgos.rgos_config:
    lines:
      - vlan 100
    match: none
  check_mode: true
"""

RETURN = """
commands:
  description: The set of commands that were pushed to the device.
  returned: when the configuration changed
  type: list
  sample: ['vlan 100', 'name ANSIBLE_TEST']
updates:
  description: Alias of I(commands), kept for compatibility with other vendors.
  returned: when the configuration changed
  type: list
saved:
  description: Whether the running configuration was persisted with C(write).
  returned: when save_when triggered a save
  type: bool
  sample: true
backup_path:
  description: Where the backup file was written.
  returned: when I(backup) is true
  type: str
  sample: /playbooks/backup/s6150-01_config.2026-09-07@10:15:00
"""

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_text
from ansible.module_utils.connection import Connection, ConnectionError
from ansible_collections.ansible.netcommon.plugins.module_utils.network.common.config import (
    NetworkConfig,
)
from ansible_collections.elgintester.rgos.plugins.module_utils.rgos import (
    config_ignore_lines,
)


def build_candidate(module):
    """组装候选配置文本。

    优先级是 content > src > lines，和 cisco.ios ios_config 一致，
    这样移植过来的 playbook 行为相同。

    使用 I(parents) 时，候选是父命令后跟缩进的行；不使用时，
    行原样使用，调用者直接控制缩进。
    """
    lines = module.params["lines"]
    parents = module.params["parents"]

    if module.params["content"]:
        # 已渲染的配置文本，通常通过 ansible.builtin.template lookup 产生，
        # 或在 playbook 中内联编写。
        return module.params["content"]

    if module.params["src"]:
        # action 插件已经把 src 读取并渲染到这个参数中。
        return module.params["src"]

    if not lines:
        return ""

    if not parents:
        return "\n".join(lines)

    # RGOS 每嵌套一层显示一个空格缩进，cliconf 插件中的解析器跟踪该层级，
    # 所以精确镜像它。父命令本身也形成层级：两个父命令时第一个在第 0 列，
    # 第二个缩进一个空格，行缩进两个空格。
    block = [
        "%s%s" % (" " * index, parent.strip())
        for index, parent in enumerate(parents)
    ]
    indent = " " * len(parents)
    block.extend("%s%s" % (indent, line.strip()) for line in lines)
    return "\n".join(block)


def run_commands(module, commands, connection):
    for cmd in commands:
        try:
            connection.get(command=cmd)
        except ConnectionError as exc:
            module.fail_json(
                msg="command %r failed: %s" % (cmd, to_text(exc)),
                commands=commands,
            )


def main():
    backup_spec = dict(filename=dict(type="str"), dir_path=dict(type="path"))
    argument_spec = dict(
        lines=dict(type="list", elements="str", aliases=["commands"]),
        parents=dict(type="list", elements="str"),
        src=dict(type="str"),
        content=dict(type="str"),
        before=dict(type="list", elements="str"),
        after=dict(type="list", elements="str"),
        match=dict(default="line", choices=["line", "strict", "exact", "none"]),
        replace=dict(default="line", choices=["line", "block"]),
        diff_ignore_lines=dict(type="list", elements="str"),
        backup=dict(type="bool", default=False),
        backup_options=dict(type="dict", options=backup_spec),
        save_when=dict(
            default="never", choices=["always", "never", "modified", "changed"]
        ),
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
        # parents 仅用于推导 lines 的缩进，所以和预格式化文本块
        # （src/content）一起使用没有意义。
        mutually_exclusive=[
            ["lines", "src"],
            ["lines", "content"],
            ["parents", "src"],
            ["parents", "content"],
            ["src", "content"],
        ],
        supports_check_mode=True,
    )

    # required_one_of 无法表达这个规则：save_when 有默认值，所以它
    # 总是被视为"已提供"，检查会变成空操作。手动校验——任务必须要么
    # 变更什么，要么备份什么，要么显式要求持久化设备上已有的配置。
    if (
        not module.params["lines"]
        and not module.params["src"]
        and not module.params["content"]
        and not module.params["backup"]
        and module.params["save_when"] == "never"
    ):
        module.fail_json(
            msg="one of lines, src, content or backup is required; "
            "alternatively set save_when to always, modified or changed to "
            "persist the current device configuration without pushing anything"
        )

    # warnings 从一开始就保持为列表，且只追加。
    # 在这里赋值裸字符串会让 Ansible 逐字符迭代它，每个字符打印一行警告。
    warnings = []
    result = {"changed": False, "warnings": warnings}

    connection = Connection(module._socket_path)

    try:
        capabilities = module.from_json(connection.get_capabilities())
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc, errors="surrogate_then_replace"))

    device_operations = capabilities.get("device_operations", {})

    if module.params["match"] != "line" and not device_operations.get(
        "supports_diff_match"
    ):
        module.fail_json(msg="match is not supported by this platform")

    if module.params["replace"] != "line" and not device_operations.get(
        "supports_diff_replace"
    ):
        module.fail_json(msg="replace is not supported by this platform")

    candidate = build_candidate(module)

    # running 配置总是需要用来做 diff；也复用于备份，所以设备只读一次。
    contents = None
    if candidate or module.params["backup"]:
        try:
            contents = connection.get_config(flags=[])
        except ConnectionError as exc:
            module.fail_json(msg=to_text(exc, errors="surrogate_then_replace"))

    if module.params["backup"]:
        # action 插件弹出 __backup__ 并写入文件，遵循 backup_options。
        result["__backup__"] = contents or ""

    if candidate:
        try:
            response = connection.get_diff(
                candidate=candidate,
                running=contents,
                diff_match=module.params["match"],
                diff_ignore_lines=module.params["diff_ignore_lines"],
                diff_replace=module.params["replace"],
            )
        except ConnectionError as exc:
            module.fail_json(msg=to_text(exc, errors="surrogate_then_replace"))

        config_diff = response.get("config_diff")

        if config_diff:
            commands = config_diff.split("\n")
            result["commands"] = commands
            result["updates"] = commands
            result["changed"] = True

            if not module.check_mode:
                if module.params["before"]:
                    run_commands(module, module.params["before"], connection)
                try:
                    connection.edit_config(candidate=commands, commit=True)
                except ConnectionError as exc:
                    # RGOS 立即应用已接受的行，且没有回滚，
                    # 所以告诉运维人员失败前到底有哪些行通过了——
                    # 那些可能需要回退。
                    module.fail_json(
                        msg=to_text(exc, errors="surrogate_then_replace"),
                        commands=commands,
                        warnings=[
                            "the device may have applied part of the candidate "
                            "before this failure; RGOS has no rollback"
                        ],
                    )
                if module.params["after"]:
                    run_commands(module, module.params["after"], connection)
        elif module.check_mode:
            warnings.append("no changes detected; nothing would be pushed")

    if module.check_mode and not candidate:
        warnings.append("check mode with no candidate: nothing to do")

    save_when = module.params["save_when"]

    # 决定是否持久化，镜像 cisco.ios ios_config 语义，
    # 这样移植过来的 playbook 行为完全一致：
    #   always   - 每次运行都保存
    #   changed  - 仅当本任务推送了什么才保存
    #   modified - 如果 running-config 和 startup-config 不同则保存，
    #              这也覆盖了 Ansible 之外做的变更，使独立的"确保设备已保存"
    #              任务有意义
    #   never    - 只保留在 running-config 中
    should_save = False

    if save_when == "always":
        should_save = True
    elif save_when == "changed" and result["changed"]:
        should_save = True
    elif save_when == "modified":
        if module.check_mode:
            # 比较两种配置是只读且安全的，但报告"会保存"需要知道真实差异。
            warnings.append(
                "check mode: cannot verify startup-config drift without "
                "reading both configurations; the save decision is skipped"
            )
        else:
            try:
                running_text = connection.get_config(source="running", flags=[])
                startup_text = connection.get_config(source="startup", flags=[])
            except ConnectionError as exc:
                # 某些 RGOS 版本可能不以相同方式暴露 startup-config；
                # 不要因为保存决策而让整个任务失败。
                warnings.append(
                    "could not compare running-config with startup-config "
                    "(%s); skipping save_when=modified"
                    % to_text(exc, errors="surrogate_then_replace")
                )
            else:
                # 两侧都用合并了 RGOS 特有忽略行的解析器解析。
                # 没有它们的话，running 输出的设备头（例如
                # "Current configuration: 9051 bytes"，netcommon 内置模式
                # 因为 RGOS 冒号前没有空格而匹配不到）会让两次摘要在每次
                # 比较时都不同，把 save_when=modified 退化为 always-save。
                ignore = config_ignore_lines(
                    module.params["diff_ignore_lines"]
                )
                running_obj = NetworkConfig(
                    indent=1,
                    contents=running_text,
                    ignore_lines=ignore,
                )
                startup_obj = NetworkConfig(
                    indent=1,
                    contents=startup_text,
                    ignore_lines=ignore,
                )
                should_save = running_obj.sha1 != startup_obj.sha1

    if should_save:
        if module.check_mode:
            warnings.append(
                "check mode: configuration would be saved with 'write'"
            )
        else:
            try:
                connection.get(command="write")
            except ConnectionError as exc:
                module.fail_json(
                    msg="failed to save configuration with 'write': %s"
                    % to_text(exc, errors="surrogate_then_replace"),
                    changed=result["changed"],
                )
            result["saved"] = True

    module.exit_json(**result)


if __name__ == "__main__":
    main()
