# -*- coding: utf-8 -*-
"""Render the actual Jinja expressions inside the svc_vlan role's modular
task files (vlan / svi / port_binding / aaa / dot1x) with Ansible-like
filters/tests, so the files themselves are what gets verified.

Run from the collection root:  python tests/verify_svc_jinja.py
"""
import io, os, sys, re, yaml, jinja2
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))
OPS  = os.path.normpath(os.path.join(HERE, '..', '..', 'elgin-rgos-ops'))
TASKS = os.path.join(HERE, '..', 'roles', 'svc_vlan', 'tasks')

def load(path):
    with open(path, encoding='utf-8') as fh:
        return yaml.safe_load(fh)

# Sample parameters come from the real svc_vars.yml when it sits next to the
# playbooks (development setup); otherwise a built-in sample keeps this tool
# runnable from the published collection tarball.
try:
    V = load(os.path.join(OPS, 'svc_vars.yml'))
    svc_aaa, svc_devices, svc_features = V['svc_aaa'], V['svc_devices'], V.get('svc_features', {})
    dev1 = svc_devices['s6150-01']
except (OSError, KeyError, TypeError):
    svc_features = {'vlan': True, 'svi': True, 'port_binding': True, 'aaa': True, 'dot1x': True}
    svc_aaa = {'enabled': True, 'radius_host': '172.17.99.212', 'radius_key': '123456',
               'auth_list': 'default', 'dot1x_cmd': 'dot1x port-control auto',
               'dot1x_remove': 'no dot1x port-control auto',
               'dot1x_auth_cmd': 'dot1x authentication default',
               'dot1x_auth_remove': 'no dot1x authentication'}
    dev1 = {'svc_vlan': 100, 'svc_vlan_name': '', 'svc_ip': '92.89.100.1',
            'svc_mask': '255.255.255.0', 'svc_secondary_ip': '',
            'svc_ports': [{'name': 'TFGigabitEthernet 0/15', 'short': 'TF0/15'},
                          {'name': 'TFGigabitEthernet 0/16', 'short': 'TF0/16'}]}

env = jinja2.Environment()
env.filters['regex_search'] = lambda value, pattern: (m.group(0) if (m := re.search(pattern, value)) else None)
env.filters['default'] = lambda value, d='': (d if value is None or value == '' else value)
env.filters['bool'] = bool
env.tests['search'] = lambda value, pattern: bool(re.search(pattern, value))

# Load all five module files (pure task lists, no play wrapper).
mod = {}
for name in ('vlan', 'svi', 'port_binding', 'aaa', 'dot1x'):
    mod[name] = load(os.path.join(TASKS, name + '.yml'))

def task(tasks, name):
    for t in tasks:
        if t.get('name') == name:
            return t
    raise KeyError(name)

def params(t):
    for k, v in t.items():
        if isinstance(v, dict) and k not in ('when', 'loop', 'loop_control', 'vars', 'block', 'rescue'):
            return v
    raise KeyError("no module params in %r" % t)

def rend(expr, ctx):
    return env.from_string(expr).render(**ctx)

def truth(expr, ctx):
    """Evaluate a Jinja expression the way an assert would: render it, then
    judge truthiness."""
    out = rend(expr, ctx).strip()
    if out == 'True':
        return True
    if out == 'False' or out == 'None' or out == '':
        return False
    return bool(out)

def show(label, got, expect=None):
    ok = "" if expect is None else (" OK" if got == expect else "  <<< EXPECTED %r" % (expect,))
    print("  %-60s -> %r%s" % (label, got, ok))

# ---------------------------------------------------------------- sample data
rc_deployed = """Building configuration...
Current configuration: 9048 bytes
!
aaa new-model
aaa authentication dot1x default group radius
aaa authentication login default local
dot1x authentication default
radius-server host 172.17.99.212 key 7 08354E
vlan 100
interface Vlan 100
 ip address 92.89.100.1 255.255.255.0
interface TFGigabitEthernet 0/15
 switchport access vlan 100
 dot1x port-control auto
interface TFGigabitEthernet 0/16
 switchport access vlan 100
 dot1x port-control auto
end
"""
rc_clean = "Building configuration...\n!\nend\n"
rc_login_conflict = "aaa new-model\naaa authentication login default group radius local\n"
rc_dot1x_conflict = "aaa new-model\naaa authentication dot1x default group radius local none\n"
port_results = [
    {'item': {'name': 'TFGigabitEthernet 0/15', 'short': 'TF0/15'},
     'stdout': "interface TFGigabitEthernet 0/15\n switchport access vlan 100\n dot1x port-control auto\n"},
    {'item': {'name': 'TFGigabitEthernet 0/16', 'short': 'TF0/16'},
     'stdout': "interface TFGigabitEthernet 0/16\n switchport access vlan 100\n dot1x port-control auto\n"},
]
clean_port_results = [
    {'item': {'name': 'TFGigabitEthernet 0/15', 'short': 'TF0/15'},
     'stdout': "interface TFGigabitEthernet 0/15\n switchport access vlan 1\n"},
    {'item': {'name': 'TFGigabitEthernet 0/16', 'short': 'TF0/16'},
     'stdout': "interface TFGigabitEthernet 0/16\n switchport access vlan 1\n"},
]
vlan_probe_deployed = {'failed': False, 'stdout': 'VLAN ID   Name       Type    Status   Ports\n1         default    static  active   TF0/23\n100       MGMT       static  active   TF0/15,TF0/16\n'}
vlan_probe_clean = {'failed': False, 'stdout': 'VLAN ID   Name       Type    Status   Ports\n1         default    static  active   TF0/23\n'}
svi_probe_deployed = {'failed': False, 'stdout': 'interface Vlan 100\n ip address 92.89.100.1 255.255.255.0\n'}
svi_probe_clean = {'failed': True, 'stdout': ''}

# ============================================================== candidate lines
print("== candidate line construction ==")

t = task(mod['vlan'], "[vlan][deploy] Ensure the service VLAN exists")
show("vlan lines (no name)", rend(params(t)['lines'], dict(dev=dev1)), str(["vlan 100"]))
show("vlan lines (named)", rend(params(t)['lines'], dict(dev=dict(dev1, svc_vlan_name='MGMT'))), str(["vlan 100", " name MGMT"]))

t = task(mod['svi'], "[svi][deploy] Ensure the SVI and its addresses")
show("svi lines (no secondary)", rend(params(t)['lines'], dict(dev=dev1)), str(["ip address 92.89.100.1 255.255.255.0"]))
show("svi lines (secondary)", rend(params(t)['lines'], dict(dev=dict(dev1, svc_secondary_ip='92.89.101.1'))),
     str(["ip address 92.89.100.1 255.255.255.0", "ip address 92.89.101.1 255.255.255.0 secondary"]))
show("svi parents", rend(params(t)['parents'], dict(dev=dev1)), "interface Vlan 100")

t = task(mod['aaa'], "[aaa][deploy] Enable AAA/radius (key written only if no radius line exists yet)")
show("aaa lines (radius absent -> key written)", rend(params(t)['lines'], dict(svc_aaa=svc_aaa, radius_already=False)),
     str(['aaa new-model', 'radius-server host 172.17.99.212 key 123456',
          'aaa authentication dot1x default group radius', 'aaa authentication login default local']))
show("aaa lines (radius present -> idempotent, no key)", rend(params(t)['lines'], dict(svc_aaa=svc_aaa, radius_already=True)),
     str(['aaa new-model', 'aaa authentication dot1x default group radius', 'aaa authentication login default local']))

t = task(mod['dot1x'], "[dot1x][deploy] Apply the global dot1x authentication command")
show("dot1x global auth cmd", rend(params(t)['lines'][0], dict(svc_aaa=svc_aaa)), "dot1x authentication default")

# ============================================================== pre-flight asserts
print("== pre-flight asserts (True = proceed, False = abort) ==")

t = task(mod['svi'], "[svi][deploy] Abort if the SVI carries a conflicting primary address")
expr = params(t)['that'][0]
for label, svi, expect in [
    ("SVI missing -> proceed", {'stdout': ''}, True),
    ("SVI has our primary -> proceed", {'stdout': "interface Vlan 100\n ip address 92.89.100.1 255.255.255.0\n"}, True),
    ("SVI has other primary -> ABORT", {'stdout': "interface Vlan 100\n ip address 10.1.1.1 255.255.255.0\n"}, False),
    ("SVI has other secondary only -> proceed (coexists)", {'stdout': "interface Vlan 100\n ip address 10.1.1.1 255.255.255.0 secondary\n"}, True),
    ("SVI has our primary + other secondary -> proceed", {'stdout': "interface Vlan 100\n ip address 92.89.100.1 255.255.255.0\n ip address 10.1.1.1 255.255.255.0 secondary\n"}, True),
]:
    show(label, truth("{{ " + expr + " }}", dict(dev=dev1, svi_before=svi)), expect)

t = task(mod['aaa'], "[aaa][deploy] Abort if management-login auth already conflicts")
expr = params(t)['that'][0]
for label, rc, expect in [
    ("clean -> proceed", {'stdout': rc_clean}, True),
    ("login default local -> proceed", {'stdout': "aaa authentication login default local\n"}, True),
    ("login group radius -> ABORT", {'stdout': rc_login_conflict}, False),
]:
    show(label, truth("{{ " + expr + " }}", dict(rc_before=rc)), expect)

t = task(mod['aaa'], "[aaa][deploy] Abort if dot1x already uses a conflicting method list")
expr = params(t)['that'][0]
for label, rc, expect in [
    ("clean -> proceed", {'stdout': rc_clean}, True),
    ("dot1x group radius -> proceed", {'stdout': rc_deployed}, True),
    ("dot1x group radius local none -> ABORT", {'stdout': rc_dot1x_conflict}, False),
]:
    show(label, truth("{{ " + expr + " }}", dict(svc_aaa=svc_aaa, rc_before=rc)), expect)

# ============================================================== state / gating flags
print("== state flags (deploy gating) ==")

t = task(mod['vlan'], "[vlan] Work out whether the VLAN exists")
expr = params(t)['vlan_exists']
show("vlan_exists (deployed)", truth(expr, dict(dev=dev1, vlan_probe=vlan_probe_deployed)), True)
show("vlan_exists (clean)", truth(expr, dict(dev=dev1, vlan_probe=vlan_probe_clean)), False)
show("vlan_exists must not match vlan 1000", truth(expr, dict(dev=dev1, vlan_probe={'failed': False, 'stdout': 'VLAN ID   Name\n1000      BIG\n'})), False)

t = task(mod['svi'], "[svi] Work out which addresses are already present")
sf = params(t)
ctx = dict(dev=dev1)
show("svi_has_primary (deployed)", truth(sf['svi_has_primary'], dict(ctx, svi_before=svi_probe_deployed)), True)
show("svi_has_primary (clean)", truth(sf['svi_has_primary'], dict(ctx, svi_before=svi_probe_clean)), False)
show("svi_has_secondary (none configured)", truth(sf['svi_has_secondary'], dict(ctx, svi_before=svi_probe_deployed)), False)

# port_binding gating is now a loop (set_fact + when); simulate the loop.
t_init = task(mod['port_binding'], "[port_binding] Initialize ports_in_svc_vlan")
t_loop = task(mod['port_binding'], "[port_binding] Work out which ports are already in the service VLAN")
when_expr = t_loop['when']
set_expr  = params(t_loop)['ports_in_svc_vlan']

import ast
def simulate_port_gating(port_results, dev):
    acc = []
    for item in port_results:
        ctx = dict(dev=dev, item=item, ports_in_svc_vlan=acc)
        # when conditions are bare Jinja expressions (no {{ }}), wrap them
        if truth("{{ " + when_expr + " }}", ctx):
            rendered = rend(set_expr, ctx)
            acc = ast.literal_eval(rendered)
    return acc

show("ports_in_svc_vlan (deployed)", str(simulate_port_gating(port_results, dev1)),
     str([p['item'] for p in port_results]))
show("ports_in_svc_vlan (clean)", str(simulate_port_gating(clean_port_results, dev1)), str([]))

t = task(mod['aaa'], "[aaa] Check whether the radius server is already configured")
sf = params(t)
show("radius_already (deployed)", truth(sf['radius_already'], dict(svc_aaa=svc_aaa, rc_before={'stdout': rc_deployed})), True)
show("radius_already (clean)", truth(sf['radius_already'], dict(svc_aaa=svc_aaa, rc_before={'stdout': rc_clean})), False)
show("dot1x_auth_present (deployed)", truth(sf['dot1x_auth_present'], dict(svc_aaa=svc_aaa, rc_before={'stdout': rc_deployed})), True)
show("dot1x_auth_present (clean)", truth(sf['dot1x_auth_present'], dict(svc_aaa=svc_aaa, rc_before={'stdout': rc_clean})), False)

t = task(mod['dot1x'], "[dot1x] Work out whether the global dot1x auth command is applied")
sf = params(t)
show("dot1x_auth_applied (deployed)", truth(sf['dot1x_auth_applied'], dict(svc_aaa=svc_aaa, rc_before={'stdout': rc_deployed})), True)
show("dot1x_auth_applied (clean)", truth(sf['dot1x_auth_applied'], dict(svc_aaa=svc_aaa, rc_before={'stdout': rc_clean})), False)

# ports_with_dot1x is now also a loop; simulate it with the same helper.
t_dot1x_loop = task(mod['dot1x'], "[dot1x] Work out which ports already have dot1x")
dot1x_when = t_dot1x_loop['when']
dot1x_set  = params(t_dot1x_loop)['ports_with_dot1x']

def simulate_dot1x_gating(port_results, svc_aaa):
    acc = []
    for item in port_results:
        ctx = dict(svc_aaa=svc_aaa, item=item, ports_with_dot1x=acc)
        if truth("{{ " + dot1x_when + " }}", ctx):
            rendered = rend(dot1x_set, ctx)
            acc = ast.literal_eval(rendered)
    return acc

show("ports_with_dot1x (deployed)", str(simulate_dot1x_gating(port_results, svc_aaa)),
     str([p['item'] for p in port_results]))
show("ports_with_dot1x (clean)", str(simulate_dot1x_gating(clean_port_results, svc_aaa)), str([]))

# ============================================================== rollback flags
print("== rollback state flags ==")

t = task(mod['svi'], "[svi][rollback] Work out whether the SVI exists")
expr = params(t)['svi_present']
show("svi_present (deployed)", truth(expr, dict(svi_before=svi_probe_deployed)), True)
show("svi_present (clean/failed)", truth(expr, dict(svi_before=svi_probe_clean)), False)

# ============================================================== post-deploy asserts
print("== post-deploy asserts (True = pass) ==")

t = task(mod['vlan'], "[vlan][deploy] Assert the service VLAN exists")
expr = params(t)['that'][0]
show("vlan exists -> pass", truth("{{ " + expr + " }}", dict(dev=dev1, vlan_verify=vlan_probe_deployed)), True)
show("vlan missing -> FAIL", truth("{{ " + expr + " }}", dict(dev=dev1, vlan_verify=vlan_probe_clean)), False)

t = task(mod['svi'], "[svi][deploy] Assert the SVI has the primary address")
expr = params(t)['that'][0]
show("svi primary present -> pass", truth("{{ " + expr + " }}", dict(dev=dev1, svi_verify=svi_probe_deployed)), True)
show("svi primary missing -> FAIL", truth("{{ " + expr + " }}", dict(dev=dev1, svi_verify={'stdout': ''})), False)

t = task(mod['port_binding'], "[port_binding][deploy] Assert every port joined the service VLAN")
expr = params(t)['that'][0]
show("port in vlan table -> pass", truth("{{ " + expr + " }}", dict(item=dev1['svc_ports'][0], vlan_members=vlan_probe_deployed)), True)

t = task(mod['aaa'], "[aaa][deploy] Assert the AAA/radius block was applied")
items = params(t)['that']
vals = [truth("{{ " + item + " }}", dict(svc_aaa=svc_aaa, rc_after_aaa={'stdout': rc_deployed})) for item in items]
show("deployed -> all pass", vals, [True, True, True])
rc_no_radius = rc_deployed.replace("radius-server host 172.17.99.212 key 7 08354E\n", "")
vals = [truth("{{ " + item + " }}", dict(svc_aaa=svc_aaa, rc_after_aaa={'stdout': rc_no_radius})) for item in items]
show("radius missing -> radius assert FAILS", vals, [False, True, True])

t = task(mod['dot1x'], "[dot1x][deploy] Assert dot1x present on each port")
expr = params(t)['that'][0]
results = [{'item': p['item'], 'stdout': p['stdout']} for p in port_results]
show("dot1x on ports -> all pass", [truth("{{ " + expr + " }}", dict(svc_aaa=svc_aaa, item=r)) for r in results], [True, True])

t = task(mod['dot1x'], "[dot1x][deploy] Assert the global dot1x auth command was applied")
expr = params(t)['that'][0]
show("global dot1x auth present -> pass", truth("{{ " + expr + " }}", dict(svc_aaa=svc_aaa, rc_after_dot1x={'stdout': rc_deployed})), True)
show("global dot1x auth missing -> FAIL", truth("{{ " + expr + " }}", dict(svc_aaa=svc_aaa, rc_after_dot1x={'stdout': rc_clean})), False)

# ============================================================== rollback asserts
print("== rollback verification asserts (True = pass) ==")

t = task(mod['vlan'], "[vlan][rollback] Assert the service VLAN was removed")
expr = params(t)['that'][0]
show_vlan_clean = "VLAN ID   Name       Type    Status   Ports\n1         default    static  active   TF0/23\n"
show_vlan_present = "VLAN ID   Name       Type    Status   Ports\n1         default    static  active   TF0/23\n100       MGMT       static  active   TF0/15,TF0/16\n"
for label, vg, expect in [
    ("gone -> pass", {'failed': False, 'stdout': show_vlan_clean}, True),
    ("STILL EXISTS -> FAIL", {'failed': False, 'stdout': show_vlan_present}, False),
]:
    show(label, truth("{{ " + expr + " }}", dict(dev=dev1, vlan_gone=vg)), expect)

t = task(mod['svi'], "[svi][rollback] Assert the SVI addresses are gone")
expr = params(t)['that'][0]
for label, svi, expect in [
    ("empty -> pass", {'stdout': ""}, True),
    ("still has ip -> FAIL", {'stdout': "interface Vlan 100\n ip address 92.89.100.1 255.255.255.0\n"}, False),
]:
    show(label, truth("{{ " + expr + " }}", dict(dev=dev1, svi_after=svi)), expect)

t = task(mod['port_binding'], "[port_binding][rollback] Assert the service VLAN binding is gone from every port")
expr = params(t)['that'][0]
clean_results = [{'item': p['item'], 'stdout': "interface %s\n switchport access vlan 1\n" % p['item']['name']} for p in port_results]
show("port unbound -> pass", [truth("{{ " + expr + " }}", dict(dev=dev1, item=r)) for r in clean_results], [True, True])
still_results = [{'item': p['item'], 'stdout': "interface %s\n switchport access vlan 100\n" % p['item']['name']} for p in port_results]
show("port still bound -> FAIL", [truth("{{ " + expr + " }}", dict(dev=dev1, item=r)) for r in still_results], [False, False])

t = task(mod['dot1x'], "[dot1x][rollback] Assert dot1x is gone from every port")
expr = params(t)['that'][0]
clean_results = [{'item': p['item'], 'stdout': "interface %s\n switchport access vlan 1\n" % p['item']['name']} for p in port_results]
show("dot1x removed -> all pass", [truth("{{ " + expr + " }}", dict(svc_aaa=svc_aaa, item=r)) for r in clean_results], [True, True])
still_results = [{'item': p['item'], 'stdout': "interface %s\n dot1x port-control auto\n" % p['item']['name']} for p in port_results]
show("dot1x still there -> all FAIL", [truth("{{ " + expr + " }}", dict(svc_aaa=svc_aaa, item=r)) for r in still_results], [False, False])

t = task(mod['aaa'], "[aaa][rollback] Assert the radius server and dot1x method list are gone")
items = params(t)['that']
vals = [truth("{{ " + item + " }}", dict(svc_aaa=svc_aaa, rc_after_aaa_rollback={'stdout': rc_clean})) for item in items]
show("rollback clean -> all pass", vals, [True, True])
vals = [truth("{{ " + item + " }}", dict(svc_aaa=svc_aaa, rc_after_aaa_rollback={'stdout': rc_deployed})) for item in items]
show("still deployed -> all FAIL", vals, [False, False])

# ============================================================== rollback command construction
print("== rollback command construction ==")

t = task(mod['port_binding'], "[port_binding][rollback] Unbind the ports from the service VLAN")
# content is a Jinja template string; render it with a sample context
content = params(t)['content']
rendered = env.from_string(content).render(ports_in_svc_vlan=[p['item'] for p in port_results])
show("unbind content (no vlan id!)", rendered.strip(),
     "interface TFGigabitEthernet 0/15\n no switchport access vlan\n\ninterface TFGigabitEthernet 0/16\n no switchport access vlan")

t = task(mod['aaa'], "[aaa][rollback] Remove the radius server and the dot1x auth list")
show("both present", rend(params(t)['lines'], dict(svc_aaa=svc_aaa, radius_already=True, dot1x_auth_present=True)),
     str(['no radius-server host 172.17.99.212', 'no aaa authentication dot1x default']))
show("radius only", rend(params(t)['lines'], dict(svc_aaa=svc_aaa, radius_already=True, dot1x_auth_present=False)),
     str(['no radius-server host 172.17.99.212']))
show("dot1x list only", rend(params(t)['lines'], dict(svc_aaa=svc_aaa, radius_already=False, dot1x_auth_present=True)),
     str(['no aaa authentication dot1x default']))
show("none present", rend(params(t)['lines'], dict(svc_aaa=svc_aaa, radius_already=False, dot1x_auth_present=False)), str([]))

t = task(mod['dot1x'], "[dot1x][rollback] Remove the global dot1x authentication command")
show("dot1x global remove (no list name!)", rend(params(t)['lines'][0], dict(svc_aaa=svc_aaa)), "no dot1x authentication")

t = task(mod['dot1x'], "[dot1x][rollback] Remove dot1x from the ports")
content = params(t)['content']
rendered = env.from_string(content).render(ports_with_dot1x=[p['item'] for p in port_results], svc_aaa=svc_aaa)
show("dot1x port remove content", rendered.strip(),
     "interface TFGigabitEthernet 0/15\n no dot1x port-control auto\n\ninterface TFGigabitEthernet 0/16\n no dot1x port-control auto")

print("\nALL CHECKS DONE")
