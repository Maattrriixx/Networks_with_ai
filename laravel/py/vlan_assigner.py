from collections import defaultdict

# ═══════════ VLAN TABLE ═══════════
VLANS = {
    'management': {
        'id': 10, 'name': 'Management',
        'subnet': '10.10.10.0/24', 'gateway': '10.10.10.1',
        'description': 'Network infrastructure & server room',
    },
    'surveillance': {
        'id': 20, 'name': 'Surveillance',
        'subnet': '10.10.20.0/24', 'gateway': '10.10.20.1',
        'description': 'Security cameras & security room',
    },
    'academic': {
        'id': 30, 'name': 'Academic',
        'subnet': '10.10.30.0/24', 'gateway': '10.10.30.1',
        'description': 'Classrooms and Laboratories',
    },
    'administration': {
        'id': 40, 'name': 'Administration',
        'subnet': '10.10.40.0/24', 'gateway': '10.10.40.1',
        'description': 'Administrative offices',
    },
    'faculty': {
        'id': 50, 'name': 'Faculty',
        'subnet': '10.10.50.0/24', 'gateway': '10.10.50.1',
        'description': 'Doctor offices',
    },
    'common': {
        'id': 60, 'name': 'Common-Areas',
        'subnet': '10.10.60.0/24', 'gateway': '10.10.60.1',
        'description': 'Meeting rooms, Library, Café, Lobby',
    },
    'servers': {
        'id': 70, 'name': 'Servers',
        'subnet': '10.10.70.0/24', 'gateway': '10.10.70.1',
        'description': 'Server infrastructure',
    },
}

# ═══════════ MAPPINGS ═══════════
ROOM_TYPE_TO_VLAN_KEY = {
    'laboratory':           'academic',
    'classroom':            'academic',
    'administrative office':'administration',
    'dr.office':            'faculty',
    'security':             'surveillance',
    'meeting room':         'common',
    'library':              'common',
    'café':                 'common',
    'cafe':                 'common',
    'lobby':                'common',
    'server room':          'management',
    'wc':                   None,
    'stairs':               None,
    'storage':              None,
    'other':                None,
}

DEVICE_TYPE_TO_VLAN_KEY = {
    'Camera':       'surveillance',
    'Server':       'servers',
    'Router':       'management',
    'Firewall':     'management',
    'Switch':       'management',
    'Patch Panel':  'management',
    'UPS':          'management',
}

IP_RANGE_BY_DEVICE = {
    'Router':       (2,  10),
    'Firewall':     (2,  10),
    'Switch':       (11, 50),
    'UPS':          (51, 100),
    'Server':       (51, 100),
    'Patch Panel':  (51, 100),
    'Access Point': (101, 150),
    'Camera':       (151, 200),
}
DEFAULT_RANGE = (201, 254)


def resolve_vlan_for_device(device):
    dtype = device.get('type', '')
    if dtype in DEVICE_TYPE_TO_VLAN_KEY:
        return VLANS[DEVICE_TYPE_TO_VLAN_KEY[dtype]]
    if dtype == 'Access Point':
        room_types = device.get('_room_types', [])
        return _vlan_for_ap_rooms(room_types)
    return VLANS['management']


def _vlan_for_ap_rooms(room_types):
    priority = ['academic', 'faculty', 'administration', 'surveillance', 'common']
    found = set()
    for rt in room_types:
        key = ROOM_TYPE_TO_VLAN_KEY.get(rt.lower())
        if key:
            found.add(key)
    for p in priority:
        if p in found:
            return VLANS[p]
    return VLANS['common']


def assign_ip(device, vlan, counters):
    dtype   = device.get('type', 'other')
    vlan_id = vlan['id']
    low, high = IP_RANGE_BY_DEVICE.get(dtype, DEFAULT_RANGE)

    counters[vlan_id][dtype][0] += 1
    offset = counters[vlan_id][dtype][0]
    host = low + offset - 1
    if host > high:
        counters[vlan_id]['_overflow'] = counters[vlan_id].get('_overflow', [0])
        counters[vlan_id]['_overflow'][0] += 1
        host = 200 + counters[vlan_id]['_overflow'][0]

    base = vlan['subnet'].split('/')[0]
    parts = base.split('.')
    ip = f"{parts[0]}.{parts[1]}.{parts[2]}.{host}"

    prefix = int(vlan['subnet'].split('/')[1])
    mask_int = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
    subnet_mask = '.'.join(str((mask_int >> (8 * i)) & 0xFF) for i in [3, 2, 1, 0])

    return ip, subnet_mask, vlan['gateway']

def assign_vlans_and_ips(network_data, rooms_list):
    
    
    room_type_map = {str(r['id']): r.get('type', 'other') for r in rooms_list}

    devices = network_data.get('devices', [])
    counters = defaultdict(lambda: defaultdict(lambda: [0]))
    stats = defaultdict(int)

    for device in devices:
        # APs need room types for VLAN resolution
        if device['type'] == 'Access Point':
            room_ids = [str(r) for r in device.get('rooms', [])]
            device['_room_types'] = [room_type_map.get(rid, 'other') for rid in room_ids]

        vlan = resolve_vlan_for_device(device)
        device['vlan'] = {
            'id': vlan['id'],
            'name': vlan['name'],
            'subnet': vlan['subnet'],
            'gateway': vlan['gateway'],
            'description': vlan['description'],
        }

        ip, mask, gw = assign_ip(device, vlan, counters)
        device['ip'] = ip
        device['subnet_mask'] = mask
        device['gateway'] = gw

        device.pop('_room_types', None)

        stats[vlan['name']] += 1

    network_data['vlans'] = list(VLANS.values())
    if 'metadata' not in network_data:
        network_data['metadata'] = {}
    network_data['metadata']['vlan_distribution'] = dict(stats)

    return network_data, stats