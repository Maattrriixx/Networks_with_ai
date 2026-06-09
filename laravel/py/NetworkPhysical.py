import json
import math
import random
import numpy as np
from sklearn.cluster import DBSCAN
from collections import defaultdict
import uvicorn


def normalize_type(raw_type: str) -> str:
    """Map the YOLO-detected type (e.g., 'laboratories') to the optimizer types (e.g., 'Laboratory')"""
    t = raw_type.lower().strip()
    if t in ['lab', 'laboratory', 'laboratories']:
        return 'Laboratory'
    if t in ['class', 'classroom']:
        return 'Classroom'
    if t in ['cafe', 'cafeteria', 'café']:
        return 'Cafe'
    if t in ['office', 'administrative office', 'secretary', 'dr.office', 'dr office']:
        return 'Office'       
    if t in ['library']:
        return 'Library'
    if t in ['meeting room', 'meeting', 'conference']:
        return 'Meeting Room' 
    return 'other'

def polygon_area(corners):
    if len(corners) < 3:
        return 0
    area = 0
    n = len(corners)
    for i in range(n):
        x1, y1 = corners[i]['x'], corners[i]['y']
        x2, y2 = corners[(i+1) % n]['x'], corners[(i+1) % n]['y']
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0

def load_rooms_from_list(rooms):
    ids = []; centers = []; types = []; areas = []; corners_list = []
    for r in rooms:
        ids.append(r['id'])
        centers.append([float(r['center']['x']), float(r['center']['y'])])
        raw_type = r.get('type', 'other')
        types.append(normalize_type(raw_type))
        c = r.get('corners', [])
        corners_list.append(c)
        areas.append(polygon_area(c))
    return ids, centers, types, areas, corners_list

def cluster_rooms_advanced(centers, types, areas, scale=0.05, eps=200, min_samples=2):
    sensitive = {'Laboratory', 'Library'}
    sens_idx = [i for i, t in enumerate(types) if t in sensitive]
    reg_idx  = [i for i, t in enumerate(types) if t not in sensitive]

    clusters = {}
    centroids = []
    cid = 0

    for i in sens_idx:
        clusters[cid] = [i]
        centroids.append((centers[i][0], centers[i][1]))
        cid += 1

    if reg_idx:
        reg_centers = [centers[i] for i in reg_idx]
        if len(reg_centers) > 1:
            db = DBSCAN(eps=eps, min_samples=min_samples).fit(reg_centers)
            labels = db.labels_
            temp = defaultdict(list)
            for pos, lbl in enumerate(labels):
                temp[lbl].append(reg_idx[pos])
            for lbl, idxs in temp.items():
                if lbl == -1:
                    for i in idxs:
                        clusters[cid] = [i]
                        centroids.append((centers[i][0], centers[i][1]))
                        cid += 1
                else:
                    clusters[cid] = idxs
                    cx = np.mean([centers[i][0] for i in idxs])
                    cy = np.mean([centers[i][1] for i in idxs])
                    centroids.append((cx, cy))
                    cid += 1
        else:
            i = reg_idx[0]
            clusters[cid] = [i]
            centroids.append((centers[i][0], centers[i][1]))
            cid += 1

    cluster_areas = [sum(areas[i] for i in idxs) * (scale**2) for idxs in clusters.values()]
    return clusters, centroids, cluster_areas

# ─── Genetic Algorithm ───────────────────────────────────────────────────────
class GeneticOptimizer:
    def __init__(self, clusters, centroids, cluster_areas, room_types, room_centers,
                 scale=0.05, dist_thresh=8.0, pop=30, gens=80, mut=0.2, elite=5):
        self.clusters      = clusters
        self.centroids     = centroids
        self.cluster_areas = cluster_areas
        self.room_types    = room_types
        self.room_centers  = room_centers
        self.scale         = scale
        self.dist_thresh   = dist_thresh
        self.n_clusters    = len(clusters)
        self.pop_size      = pop
        self.generations   = gens
        self.mut_rate      = mut
        self.elite_size    = elite

        # Requirements: (min_AP, min_cam)
        self.req = {
            'Laboratory': (2, 2),
            'Library': (2, 2),
            'Cafe':       (1, 1),
            'Classroom': (1, 1),
            'Office':     (1, 0),
            'other':     (1, 0)
        }
        self.w_ap      = 10
        self.w_cam     = 8
        self.w_sw      = 20
        self.w_req     = 100
        self.large_thresh = 100
        self.bonus_ap  = -15

    def init_pop(self):
        return [[random.randint(0, 3) for _ in range(self.n_clusters)] for _ in range(self.pop_size)]

    def coverage_penalty(self, aps):
        ap_pos = [self.centroids[cid] for cid, n in enumerate(aps) if n > 0]
        if not ap_pos:
            return len(self.room_centers) * 200.0
        pen = 0.0
        for (x, y) in self.room_centers:
            dist_m = min(math.hypot(x - px, y - py) for (px, py) in ap_pos) * self.scale
            if dist_m > self.dist_thresh:
                pen += (dist_m - self.dist_thresh) * 20
        return pen

    def requirement_penalty(self, aps):
        pen = 0.0
        for cid, idxs in self.clusters.items():
            need = max(self.req.get(self.room_types[i], (1, 0))[0] for i in idxs)
            if aps[cid] < need:
                pen += (need - aps[cid]) * self.w_req
        return pen

    def count_cam_sw(self, aps):
        n_cam = n_sw = 0
        for cid, idxs in self.clusters.items():
            max_cam = max(self.req.get(self.room_types[i], (1, 0))[1] for i in idxs)
            n_cam += max_cam
            if len(idxs) > 1 or max_cam > 0:
                n_sw += 1
        return n_cam, n_sw

    def fitness(self, ind):
        total_aps = sum(ind)
        cov_pen   = self.coverage_penalty(ind)
        req_pen   = self.requirement_penalty(ind)
        n_cam, n_sw = self.count_cam_sw(ind)
        bonus = 0.0
        for cid, area in enumerate(self.cluster_areas):
            if area > self.large_thresh:
                if ind[cid] >= 2:
                    bonus += self.bonus_ap * (ind[cid] - 1)
                elif ind[cid] == 0:
                    cov_pen += 500
        return cov_pen + req_pen + self.w_ap * total_aps + self.w_cam * n_cam + self.w_sw * n_sw + bonus

    def select(self, pop, fits):
        def tour():
            cand = random.sample(list(zip(pop, fits)), 3)
            return min(cand, key=lambda x: x[1])[0]
        return tour(), tour()

    def crossover(self, p1, p2):
        pt = random.randint(1, self.n_clusters - 1)
        return p1[:pt] + p2[pt:], p2[:pt] + p1[pt:]

    def mutate(self, ind):
        return [random.randint(0, 3) if random.random() < self.mut_rate else v for v in ind]

    def run(self):
        pop = self.init_pop()
        best_ind, best_fit = None, float('inf')
        for gen in range(self.generations):
            fits = [self.fitness(ind) for ind in pop]
            gb_idx = int(np.argmin(fits))
            if fits[gb_idx] < best_fit:
                best_fit = fits[gb_idx]
                best_ind = pop[gb_idx].copy()
            elite_idx = np.argsort(fits)[:self.elite_size]
            new_pop = [pop[i] for i in elite_idx]
            while len(new_pop) < self.pop_size:
                p1, p2 = self.select(pop, fits)
                c1, c2 = self.crossover(p1, p2)
                new_pop.extend([self.mutate(c1), self.mutate(c2)])
            pop = new_pop[:self.pop_size]
            if gen % 20 == 0:
                print(f"Gen {gen}: best cost = {fits[gb_idx]:.2f}")
        return best_ind, best_fit

# ─── Device generation (with UPS, Server, Patch Panels) ─────────────────────
def generate_devices(best_aps, clusters, centroids, room_ids, room_types, room_areas, scale=0.05):
    devices = []
    device_counter = 0

    # Access Points
    for cid, n_aps in enumerate(best_aps):
        if n_aps == 0:
            continue
        cx, cy = centroids[cid]
        room_indices = clusters[cid]
        for i in range(n_aps):
            offx = (i - (n_aps - 1) / 2) * 30
            offy = (i % 2) * 20
            devices.append({
                'device_id':   device_counter,
                'type':        'Access Point',
                'cluster_id':  cid,
                'rooms':       [room_ids[idx] for idx in room_indices],
                'x':           float(cx + offx),
                'y':           float(cy + offy),
                'notes':       f'AP {i+1} for cluster {cid}',
                'connectivity': 'wireless',
            })
            device_counter += 1

    # Cameras & Access Switches
    req = {
        'Laboratory': (2, 2),
        'Library': (2, 2),
        'Cafe':       (1, 1),
        'Classroom': (1, 1),
        'Office':     (1, 0),
        'other':     (1, 0),
    }
    for cid, idxs in clusters.items():
        max_cam = max(req.get(room_types[i], (1, 0))[1] for i in idxs)
        cx, cy = centroids[cid]

        for cam_i in range(max_cam):
            angle  = (2 * math.pi / max(max_cam, 1)) * cam_i
            spread = 25
            devices.append({
                'device_id':   device_counter,
                'type':        'Camera',
                'cluster_id':  cid,
                'x':           float(cx - 20 + spread * math.cos(angle)),
                'y':           float(cy - 20 + spread * math.sin(angle)),
                'notes':       f'Camera {cam_i+1} for cluster {cid}',
                'connectivity': 'wired',
            })
            device_counter += 1

        if len(idxs) > 1 or max_cam > 0:
            devices.append({
                'device_id':   device_counter,
                'type':        'Switch',
                'cluster_id':  cid,
                'x':           float(cx + 20),
                'y':           float(cy + 20),
                'ports':       24,
                'notes':       f'Switch for cluster {cid}',
                'connectivity': 'wired',
            })
            device_counter += 1

    # Core / Central devices
    all_centers = centroids
    avg_x = sum(c[0] for c in all_centers) / len(all_centers)
    avg_y = sum(c[1] for c in all_centers) / len(all_centers)

    # Core Switch
    devices.append({
        'device_id':   device_counter,
        'type':        'Switch',
        'layer':       'Core',
        'ports':       24,
        'x':           avg_x,
        'y':           avg_y - 30,
        'notes':       'Core Switch',
        'connectivity': 'wired',
        'room':        'Server Room',
    })
    device_counter += 1

    # Router
    devices.append({
        'device_id':   device_counter,
        'type':        'Router',
        'x':           avg_x,
        'y':           avg_y,
        'notes':       'Main Router',
        'connectivity': 'wired',
        'room':        'Server Room',
    })
    device_counter += 1

    # Firewall
    devices.append({
        'device_id':   device_counter,
        'type':        'Firewall',
        'x':           avg_x + 30,
        'y':           avg_y + 30,
        'notes':       'Main Firewall',
        'connectivity': 'wired',
        'room':        'Server Room',
    })
    device_counter += 1

    # Server
    devices.append({
        'device_id':   device_counter,
        'type':        'Server',
        'role':        'DC/DHCP/DNS',
        'x':           avg_x - 40,
        'y':           avg_y - 20,
        'notes':       'Main Server',
        'connectivity': 'wired',
        'room':        'Server Room',
    })
    device_counter += 1

    # UPS
    ups_targets = ['Core Switch', 'Main Router', 'Main Firewall', 'Main Server']
    core_devices = [d for d in devices if d.get('notes') in ups_targets]
    if core_devices:
        devices.append({
            'device_id':    device_counter,
            'type':         'UPS',
            'x':            float(avg_x + 60),
            'y':            float(avg_y - 50),
            'capacity_kva': 3.0,
            'protects':     [d['device_id'] for d in core_devices],
            'notes':        'UPS for Core Infrastructure',
            'connectivity': 'wired',
            'room':         'Server Room',
        })
        device_counter += 1

    return devices

# ─── Patch panels & switch ports upgrade ─────────────────────────────────────
def add_patch_and_switch_ports(devices, scale=0.05):
    new_devices = devices.copy()
    switches   = [d for d in new_devices if d['type'] == 'Switch']
    aps        = [d for d in new_devices if d['type'] == 'Access Point']
    cameras    = [d for d in new_devices if d['type'] == 'Camera']

    core_sw  = next((s for s in switches if s.get('layer') == 'Core'), None)
    access_sw = [s for s in switches if s.get('layer') != 'Core']
    if core_sw is None and switches:
        core_sw, access_sw = switches[0], switches[1:]

    dev_count = defaultdict(lambda: {'aps': 0, 'cams': 0})
    for ap in aps:
        if ap.get('cluster_id') is not None:
            dev_count[ap['cluster_id']]['aps'] += 1
    for cam in cameras:
        if cam.get('cluster_id') is not None:
            dev_count[cam['cluster_id']]['cams'] += 1

    next_id = max(d['device_id'] for d in new_devices) + 1
    patch_panels = []

    for sw in access_sw:
        cid = sw['cluster_id']
        cnt = dev_count[cid]
        needed_raw = cnt['aps'] + cnt['cams'] + 1   # +1 uplink
        needed = int(math.ceil(needed_raw * 1.2))   # 20% headroom

        if needed > 24:
            ports_per_switch = 24
            num_switches = 2
            sw['ports'] = ports_per_switch
            sw['used_ports'] = needed_raw // num_switches
            # Create second switch
            sw2 = sw.copy()
            sw2['device_id'] = next_id
            sw2['x'] = sw['x'] + 50
            sw2['y'] = sw['y']
            sw2['notes'] = f'Switch {num_switches} for cluster {cid}'
            sw2['used_ports'] = needed_raw - sw['used_ports']
            new_devices.append(sw2)
            next_id += 1
            # Patch panel per switch
            for cur_sw in [sw, sw2]:
                pp = {
                    'device_id': next_id,
                    'type': 'Patch Panel',
                    'subtype': 'UTP Cat6',
                    'ports': ports_per_switch,
                    'associated_switch': cur_sw['device_id'],
                    'cluster_id': cid,
                    'x': cur_sw['x'] - 50,
                    'y': cur_sw['y'] - 20,
                    'notes': f'Patch panel for switch {cur_sw["device_id"]}',
                    'connectivity': 'wired',
                }
                patch_panels.append(pp)
                next_id += 1
        else:
            port_sizes = [8, 16, 24, 48]
            ports = 48
            for size in port_sizes:
                if size >= needed:
                    ports = size
                    break
            sw['ports'] = ports
            sw['used_ports'] = needed_raw
            patch_panels.append({
                'device_id': next_id,
                'type': 'Patch Panel',
                'subtype': 'UTP Cat6',
                'ports': ports,
                'associated_switch': sw['device_id'],
                'cluster_id': cid,
                'x': sw['x'] - 50,
                'y': sw['y'] - 20,
                'notes': f'Patch panel for switch {sw["device_id"]}',
                'connectivity': 'wired',
            })
            next_id += 1

    new_devices.extend(patch_panels)
    return new_devices

# ─── Connection builder ───────────────────────────────────────────────────────
def build_connections(devices, scale=0.05):
    dxy = [d for d in devices if 'x' in d and 'y' in d]
    switches  = [d for d in dxy if d['type'] == 'Switch']
    aps       = [d for d in dxy if d['type'] == 'Access Point']
    cameras   = [d for d in dxy if d['type'] == 'Camera']
    routers   = [d for d in dxy if d['type'] == 'Router']
    firewalls = [d for d in dxy if d['type'] == 'Firewall']
    servers   = [d for d in dxy if d['type'] == 'Server']

    core_sw   = next((s for s in switches if s.get('layer') == 'Core'), None)
    access_sw = [s for s in switches if s.get('layer') != 'Core']
    if core_sw is None and switches:
        core_sw, access_sw = switches[0], switches[1:]

    all_switches = access_sw + ([core_sw] if core_sw else [])
    connections  = []

    def dist(a, b):
        return math.hypot(a['x'] - b['x'], a['y'] - b['y']) * scale

    if core_sw:
        for sw in access_sw:
            d_m = dist(sw, core_sw)
            medium = 'fiber' if d_m > 50 else 'copper'
            connections.append({
                'from': sw['device_id'], 'to': core_sw['device_id'],
                'type': 'ethernet_trunk', 'speed': '1 Gbps',
                'distance_m': round(d_m, 2), 'medium': medium,
            })

    for ap in aps:
        cid = ap.get('cluster_id')
        cluster_sws = [s for s in all_switches if s.get('cluster_id') == cid] or all_switches
        nearest = min(cluster_sws, key=lambda s: math.hypot(ap['x'] - s['x'], ap['y'] - s['y']))
        connections.append({
            'from': ap['device_id'], 'to': nearest['device_id'],
            'type': 'wifi_uplink',
            'distance_m': round(dist(ap, nearest), 2), 'medium': 'copper',
        })

    for cam in cameras:
        cid = cam.get('cluster_id')
        cluster_sws = [s for s in all_switches if s.get('cluster_id') == cid] or all_switches
        nearest = min(cluster_sws, key=lambda s: math.hypot(cam['x'] - s['x'], cam['y'] - s['y']))
        connections.append({
            'from': cam['device_id'], 'to': nearest['device_id'],
            'type': 'ethernet',
            'distance_m': round(dist(cam, nearest), 2), 'medium': 'copper',
        })

    if core_sw and routers:
        connections.append({
            'from': core_sw['device_id'], 'to': routers[0]['device_id'],
            'type': 'ethernet', 'speed': '10 Gbps',
            'distance_m': round(dist(core_sw, routers[0]), 2), 'medium': 'fiber',
        })

    if routers and firewalls:
        d_m = dist(routers[0], firewalls[0])
        connections.append({
            'from': routers[0]['device_id'], 'to': firewalls[0]['device_id'],
            'type': 'ethernet', 'speed': '1 Gbps',
            'distance_m': round(d_m, 2), 'medium': 'fiber' if d_m > 30 else 'copper',
        })

    if firewalls and servers:
        connections.append({
            'from': firewalls[0]['device_id'], 'to': servers[0]['device_id'],
            'type': 'ethernet', 'speed': '1 Gbps',
            'distance_m': round(dist(firewalls[0], servers[0]), 2), 'medium': 'copper',
        })

    # Redundant link
    if core_sw and routers:
        connections.append({
            'from': core_sw['device_id'], 'to': routers[0]['device_id'],
            'type': 'ethernet_redundant', 'speed': '10 Gbps',
            'distance_m': round(dist(core_sw, routers[0]), 2), 'medium': 'fiber',
            'notes': 'Redundant/backup link — activate if primary fails',
        })

    return connections

def run_optimizer(rooms_list, scale=0.05, eps=200):
    ids, centers, types, areas, _ = load_rooms_from_list(rooms_list)
    clusters, centroids, cluster_areas = cluster_rooms_advanced(centers, types, areas, scale, eps)

    ga = GeneticOptimizer(clusters, centroids, cluster_areas, types, centers,
                          scale=scale, dist_thresh=8.0, pop=30, gens=80)
    best_aps, best_cost = ga.run()

    devices = generate_devices(best_aps, clusters, centroids, ids, types, areas, scale)
    devices = add_patch_and_switch_ports(devices, scale)

    # Count wired/wireless
    wired = wireless = 0
    for d in devices:
        if d['type'] == 'Access Point':
            d['connectivity'] = 'wireless'
            wireless += 1
        else:
            d['connectivity'] = 'wired'
            wired += 1

    connections = build_connections(devices, scale)

    return {
        'devices': devices,
        'connections': connections,
        'metadata': {
            'wired_devices':    wired,
            'wireless_devices': wireless,
            'patch_panels_count': sum(1 for d in devices if d['type'] == 'Patch Panel'),
            'ups_count':        sum(1 for d in devices if d['type'] == 'UPS'),
            'scale_m_per_px':   scale,
            'clustering_eps':   eps,
            'best_fitness':     float(best_cost),
        },
        'total_devices': len(devices),
    }

