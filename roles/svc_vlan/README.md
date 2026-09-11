# svc_vlan Role

Ansible role for deploying and rolling back a service VLAN stack on Ruijie RGOS switches.

## Features

Five independent functional modules, each controlled by a feature toggle:

| Module | Description |
|--------|-------------|
| `vlan` | Create/delete the service VLAN |
| `svi` | Create/delete the VLAN L3 interface (SVI) with primary/secondary IP |
| `port_binding` | Bind/unbind access ports to the service VLAN |
| `aaa` | Configure/remove aaa new-model, radius-server, and authentication method lists |
| `dot1x` | Apply/remove global dot1x authentication and port dot1x port-control |

## Requirements

- `elgintester.rgos` collection (provides `rgos_config` module, cliconf, and terminal plugins)
- `ansible.netcommon` collection (>= 5.2.0)
- Ansible >= 2.16.0

## Role Variables

### Global feature toggles (in `svc_features`)

```yaml
svc_features:
  vlan: true
  svi: true
  port_binding: true
  aaa: true
  dot1x: true
```

Set any module to `false` to skip it. Per-device overrides are supported via `dev.features`.

### Per-device parameters (in `svc_devices`, keyed by inventory hostname)

```yaml
svc_devices:
  my-switch:
    svc_vlan: 100
    svc_vlan_name: "service-vlan-100"      # optional
    svc_svi_ip: "192.168.100.1"            # required if svi enabled
    svc_svi_mask: "255.255.255.0"          # required if svi enabled
    svc_svi_ip_secondary: "10.0.100.1"     # optional
    svc_svi_mask_secondary: "255.255.255.0" # optional
    svc_ports:                               # required if port_binding enabled
      - { name: "TFGigabitEthernet 0/15", short: "TF0/15" }
      - { name: "TFGigabitEthernet 0/16", short: "TF0/16" }
```

### AAA/dot1x shared parameters (in `svc_aaa`)

```yaml
svc_aaa:
  enabled: true
  radius_host: "172.17.99.212"
  radius_key: "your-radius-secret"
  auth_list: "default"
  dot1x_cmd: "dot1x port-control auto"
  dot1x_remove: "no dot1x port-control auto"
  dot1x_auth_cmd: "dot1x authentication default"
  dot1x_auth_remove: "no dot1x authentication"
```

## State Control

Set `svc_vlan_state` to control deploy vs rollback:

- `deployed` (default): apply configuration
- `rolledback`: remove configuration (reverse order: dot1x -> aaa -> port_binding -> svi -> vlan)

## Example Playbook

```yaml
- name: Deploy service VLAN
  hosts: ruijie
  gather_facts: false
  vars_files:
    - svc_vars.yml
  tasks:
    - name: Pre-flight
      ansible.builtin.include_role:
        name: elgintester.rgos.svc_vlan
        tasks_from: _preflight.yml
      vars:
        svc_vlan_state: deployed

    - name: Deploy VLAN
      ansible.builtin.include_role:
        name: elgintester.rgos.svc_vlan
        tasks_from: vlan.yml
      vars:
        svc_vlan_state: deployed
      when: features.vlan | default(true)

    # ... repeat for svi, port_binding, aaa, dot1x ...

    - name: Persist
      ansible.builtin.include_role:
        name: elgintester.rgos.svc_vlan
        tasks_from: _persist.yml
```

## Notes

- RGOS rollback syntax quirks are handled internally: `no switchport access vlan` (no ID), `no aaa authentication dot1x default` (no `group radius`), `no dot1x authentication` (no `default`).
- `aaa new-model` and `aaa authentication login default local` are deliberately kept during rollback to avoid locking out management access.
- All modules are idempotent: running deploy twice reports `changed=0` on the second run.

## License

GPL-3.0-or-later
