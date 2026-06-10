import json
import math
import random
import numpy as np
from sklearn.cluster import DBSCAN
from collections import defaultdict
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# ============================================================================
# Room Requirements
# ============================================================================
ROOM_PORT_REQUIREMENTS = {
    'Laboratory':   {'density': 1.0, 'min': 4,  'max': 20, 'weight': 2.0},
    'Library':      {'density': 1.0, 'min': 4,  'max': 16, 'weight': 2.0},
    'Classroom':    {'density': 1.0, 'min': 2,  'max': 12, 'weight': 1.5},
    'Meeting Room': {'density': 1.0, 'min': 2,  'max': 12, 'weight': 1.2},
    'Office':       {'density': 1.0, 'min': 1,  'max': 8,  'weight': 1.0},
    'Cafe':         {'density': 0.5, 'min': 1,  'max': 4,  'weight': 0.5},
    'other':        {'density': 1.0, 'min': 1,  'max': 4,  'weight': 1.0},
}

CAMERA_REQUIREMENTS = {
    'Laboratory': 2, 'Library': 2, 'Classroom': 1,
    'Meeting Room': 1, 'Cafe': 1, 'Office': 0, 'other': 0,
}

AP_REQUIREMENTS = {
    'Laboratory': (2, 2),
    'Library': (2, 2),
    'Classroom': (1, 1),
    'Meeting Room': (1, 1),
    'Cafe': (1, 1),
    'Office': (1, 0),
    'other': (1, 0),
}

# ============================================================================
# Helpers
# ============================================================================
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

def normalize_type(raw):
    t = raw.lower().strip()
    if t in ('lab', 'laboratory', 'laboratories'):
        return 'Laboratory'
    if t in ('class', 'classroom'):
        return 'Classroom'
    if t in ('meeting room', 'meeting', 'conference'):
        return 'Meeting Room'
    if t in ('cafe', 'cafeteria', 'café'):
        return 'Cafe'
    if t in ('office', 'administrative office', 'dr.office', 'dr office', 'secretary'):
        return 'Office'
    if t in ('library',):
        return 'Library'
    return 'other'

def load_rooms(rooms_list, scale=0.05):
    result = []
    for r in rooms_list:
        corners = r.get('corners', [])
        area_px = polygon_area(corners)
        area_m2 = area_px * (scale ** 2)
        rtype = normalize_type(r.get('type', 'other'))
        port_cfg = ROOM_PORT_REQUIREMENTS.get(rtype, ROOM_PORT_REQUIREMENTS['other'])
        raw_ports = math.floor(area_m2 * port_cfg['density']) if port_cfg['density'] > 0 else 0
        ports = max(port_cfg['min'], min(port_cfg['max'], raw_ports))
        cameras = CAMERA_REQUIREMENTS.get(rtype, 0)
        result.append({
            'id': r['id'],
            'type': rtype,
            'center': r['center'],
            'corners': corners,
            'area_m2': round(area_m2, 2),
            'ports': ports,
            'cameras': cameras,
            'density_weight': port_cfg['weight'],
        })
    return result

# ============================================================================
# Clustering
# ============================================================================
def cluster_rooms(rooms, eps=200, min_samples=2):
    centers = [(r['center']['x'], r['center']['y']) for r in rooms]
    if len(centers) < 2:
        return [[0]], centers
    db = DBSCAN(eps=eps, min_samples=min_samples).fit(centers)
    labels = db.labels_
    clusters_dict = defaultdict(list)
    for idx, lbl in enumerate(labels):
        clusters_dict[lbl].append(idx)
    clusters = []
    centroids = []
    for lbl, indices in clusters_dict.items():
        if lbl == -1:
            for i in indices:
                clusters.append([i])
                centroids.append((centers[i][0], centers[i][1]))
        else:
            clusters.append(indices)
            cx = np.mean([centers[i][0] for i in indices])
            cy = np.mean([centers[i][1] for i in indices])
            centroids.append((cx, cy))
    return clusters, centroids

# ============================================================================
# Genetic Algorithm for Wireless APs
# ============================================================================
class WirelessGA:
    def __init__(self, clusters, centroids, rooms, scale=0.05, dist_thresh=8.0,
                 pop=30, gens=80, mut=0.2, elite=5):
        self.clusters = clusters
        self.centroids = centroids
        self.rooms = rooms
        self.scale = scale
        self.dist_thresh = dist_thresh
        self.n_clusters = len(clusters)
        self.pop_size = pop
        self.generations = gens
        self.mut_rate = mut
        self.elite_size = elite
        self.w_ap = 10
        self.w_cam = 8
        self.w_sw = 20
        self.w_req = 100
        self.large_thresh = 100
        self.bonus_ap = -15

    def init_pop(self):
        return [[random.randint(0, 3) for _ in range(self.n_clusters)] for _ in range(self.pop_size)]

    def coverage_penalty(self, aps):
        ap_pos = [self.centroids[cid] for cid, n in enumerate(aps) if n > 0]
        if not ap_pos:
            return len(self.rooms) * 200.0
        pen = 0.0
        for r in self.rooms:
            rx, ry = r['center']['x'], r['center']['y']
            dist_m = min(math.hypot(rx-px, ry-py) for (px,py) in ap_pos) * self.scale
            if dist_m > self.dist_thresh:
                pen += (dist_m - self.dist_thresh) * 20
        return pen

    def requirement_penalty(self, aps):
        pen = 0.0
        for cid, idxs in enumerate(self.clusters):
            need = 0
            for idx in idxs:
                rtype = self.rooms[idx]['type']
                need = max(need, AP_REQUIREMENTS.get(rtype, (1,0))[0])
            if aps[cid] < need:
                pen += (need - aps[cid]) * self.w_req
        return pen

    def count_cam_sw(self, aps):
        n_cam = n_sw = 0
        for cid, idxs in enumerate(self.clusters):
            max_cam = 0
            for idx in idxs:
                rtype = self.rooms[idx]['type']
                max_cam = max(max_cam, AP_REQUIREMENTS.get(rtype, (1,0))[1])
            n_cam += max_cam
            if len(idxs) > 1 or max_cam > 0:
                n_sw += 1
        return n_cam, n_sw

    def fitness(self, ind):
        total_aps = sum(ind)
        cov_pen = self.coverage_penalty(ind)
        req_pen = self.requirement_penalty(ind)
        n_cam, n_sw = self.count_cam_sw(ind)
        bonus = 0.0
        for cid, idxs in enumerate(self.clusters):
            area_m2 = sum(self.rooms[i]['area_m2'] for i in idxs)
            if area_m2 > self.large_thresh:
                if ind[cid] >= 2:
                    bonus += self.bonus_ap * (ind[cid] - 1)
                elif ind[cid] == 0:
                    cov_pen += 500
        return cov_pen + req_pen + self.w_ap*total_aps + self.w_cam*n_cam + self.w_sw*n_sw + bonus

    def select(self, pop, fits):
        def tour():
            cand = random.sample(list(zip(pop, fits)), 3)
            return min(cand, key=lambda x: x[1])[0]
        return tour(), tour()

    def crossover(self, p1, p2):
        # FIX: Handle the case where n_clusters == 1 (avoid empty range)
        if self.n_clusters <= 1:
            return p1[:], p2[:]
        pt = random.randint(1, self.n_clusters - 1)
        return p1[:pt] + p2[pt:], p2[:pt] + p1[pt:]

    def mutate(self, ind):
        return [random.randint(0, 3) if random.random() < self.mut_rate else v for v in ind]

    def run(self):
        pop = self.init_pop()
        best_ind = None
        best_fit = float('inf')
        for gen in range(self.generations):
            fits = [self.fitness(ind) for ind in pop]
            gb_idx = np.argmin(fits)
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
        return best_ind, best_fit

# ============================================================================
# Device Generation
# ============================================================================
def create_optimal_switches(total_ports_needed):
    if total_ports_needed <= 48:
        return [48]
    else:
        return [48] * math.ceil(total_ports_needed / 48)

def generate_devices(rooms, clusters, centroids, best_aps, scale=0.05):
    devices = []
    device_id = 0
    room_outlets = {}
    room_cameras = {}
    room_aps = {}

    for room in rooms:
        cx, cy = room['center']['x'], room['center']['y']
        n_ports = room['ports']
        n_cams = room['cameras']
        outlet_ids = []
        for i in range(n_ports):
            angle = (2 * math.pi / max(n_ports, 1)) * i
            devices.append({
                'device_id': device_id,
                'type': 'Data Outlet',
                'room_id': room['id'],
                'room_type': room['type'],
                'x': round(cx + 15 * math.cos(angle), 2),
                'y': round(cy + 15 * math.sin(angle), 2),
                'connectivity': 'wired',
                'notes': f'Data outlet {i+1} in room {room["id"]}'
            })
            outlet_ids.append(device_id)
            device_id += 1
        room_outlets[room['id']] = outlet_ids

        cam_ids = []
        for j in range(n_cams):
            angle = (2 * math.pi / max(n_cams, 1)) * j + math.pi/4
            devices.append({
                'device_id': device_id,
                'type': 'Camera',
                'room_id': room['id'],
                'room_type': room['type'],
                'x': round(cx + 20 * math.cos(angle), 2),
                'y': round(cy + 20 * math.sin(angle), 2),
                'connectivity': 'wired',
                'notes': f'Camera {j+1} in room {room["id"]}'
            })
            cam_ids.append(device_id)
            device_id += 1
        room_cameras[room['id']] = cam_ids

    for cid, n_aps in enumerate(best_aps):
        if n_aps == 0:
            continue
        cx, cy = centroids[cid]
        room_indices = clusters[cid]
        for i in range(n_aps):
            offx = (i - (n_aps-1)/2) * 30
            offy = (i % 2) * 20
            devices.append({
                'device_id': device_id,
                'type': 'Access Point',
                'cluster_id': cid,
                'rooms': [rooms[idx]['id'] for idx in room_indices],
                'x': round(cx + offx, 2),
                'y': round(cy + offy, 2),
                'connectivity': 'wireless',
                'notes': f'AP {i+1} for cluster {cid}'
            })
            device_id += 1
        for idx in room_indices:
            rid = rooms[idx]['id']
            room_aps[rid] = room_aps.get(rid, 0) + n_aps

    cluster_port_needs = defaultdict(int)
    for cid, idxs in enumerate(clusters):
        for idx in idxs:
            rid = rooms[idx]['id']
            cluster_port_needs[cid] += len(room_outlets.get(rid, []))
            cluster_port_needs[cid] += len(room_cameras.get(rid, []))
            cluster_port_needs[cid] += room_aps.get(rid, 0)

    access_switches = []
    patch_panels = []
    for cid, total_ports in cluster_port_needs.items():
        if total_ports == 0:
            continue
        port_sizes = create_optimal_switches(total_ports)
        cx, cy = centroids[cid]
        for i, ports in enumerate(port_sizes):
            angle = (2 * math.pi / len(port_sizes)) * i
            rad = 40
            sw_x = cx + rad * math.cos(angle)
            sw_y = cy + rad * math.sin(angle)
            pp_id = device_id
            devices.append({
                'device_id': device_id,
                'type': 'Patch Panel',
                'subtype': 'UTP Cat6',
                'ports': ports,
                'cluster_id': cid,
                'x': round(sw_x - 30, 2),
                'y': round(sw_y - 20, 2),
                'connectivity': 'wired',
                'notes': f'Patch panel for cluster {cid} switch {i+1}'
            })
            patch_panels.append(pp_id)
            device_id += 1
            sw_id = device_id
            devices.append({
                'device_id': device_id,
                'type': 'Switch',
                'layer': 'Access',
                'ports': ports,
                'used_ports': total_ports if len(port_sizes) == 1 else (total_ports // len(port_sizes)),
                'cluster_id': cid,
                'patch_panel_id': pp_id,
                'x': round(sw_x, 2),
                'y': round(sw_y, 2),
                'connectivity': 'wired',
                'notes': f'Access switch {i+1} for cluster {cid} ({ports} ports)'
            })
            access_switches.append(sw_id)
            device_id += 1

    all_centers = [r['center'] for r in rooms]
    core_x = sum(c['x'] for c in all_centers) / len(all_centers)
    core_y = sum(c['y'] for c in all_centers) / len(all_centers)

    core_sw = {
        'device_id': device_id,
        'type': 'Switch',
        'layer': 'Core',
        'ports': 48,
        'used_ports': len(access_switches),
        'x': round(core_x, 2),
        'y': round(core_y - 30, 2),
        'connectivity': 'wired',
        'room': 'Server Room',
        'notes': 'Core Switch'
    }
    devices.append(core_sw)
    device_id += 1

    router = {
        'device_id': device_id,
        'type': 'Router',
        'x': round(core_x, 2),
        'y': round(core_y, 2),
        'connectivity': 'wired',
        'room': 'Server Room',
        'notes': 'Main Router'
    }
    devices.append(router)
    device_id += 1

    firewall = {
        'device_id': device_id,
        'type': 'Firewall',
        'x': round(core_x + 30, 2),
        'y': round(core_y + 30, 2),
        'connectivity': 'wired',
        'room': 'Server Room',
        'notes': 'Main Firewall'
    }
    devices.append(firewall)
    device_id += 1

    server = {
        'device_id': device_id,
        'type': 'Server',
        'role': 'DC/DHCP/DNS',
        'x': round(core_x - 40, 2),
        'y': round(core_y - 20, 2),
        'connectivity': 'wired',
        'room': 'Server Room',
        'notes': 'Main Server'
    }
    devices.append(server)
    device_id += 1

    core_ids = [core_sw['device_id'], router['device_id'], firewall['device_id'], server['device_id']]
    devices.append({
        'device_id': device_id,
        'type': 'UPS',
        'capacity_kva': 3.0,
        'protects': core_ids,
        'x': round(core_x + 60, 2),
        'y': round(core_y - 50, 2),
        'connectivity': 'wired',
        'room': 'Server Room',
        'notes': 'UPS for Core Infrastructure'
    })
    return devices, access_switches, patch_panels, room_outlets, room_cameras, core_sw['device_id']

# ============================================================================
# Connection Builder
# ============================================================================
def build_connections(devices, access_switches, patch_panels, room_outlets, room_cameras, core_sw_id, scale=0.05):
    dev_map = {d['device_id']: d for d in devices}
    def dist_m(a_id, b_id):
        a, b = dev_map[a_id], dev_map[b_id]
        return round(math.hypot(a['x']-b['x'], a['y']-b['y']) * scale, 2)

    connections = []
    pp_positions = [(pp, dev_map[pp]['x'], dev_map[pp]['y']) for pp in patch_panels]

    for outlets in room_outlets.values():
        for oid in outlets:
            ox, oy = dev_map[oid]['x'], dev_map[oid]['y']
            best_pp = min(pp_positions, key=lambda p: math.hypot(ox-p[1], oy-p[2]))
            connections.append({
                'from': oid, 'to': best_pp[0],
                'type': 'ethernet', 'cable': 'Cat6 UTP',
                'distance_m': dist_m(oid, best_pp[0]),
                'medium': 'copper',
                'notes': 'Data outlet -> Patch panel'
            })

    for cams in room_cameras.values():
        for cid in cams:
            cx, cy = dev_map[cid]['x'], dev_map[cid]['y']
            best_pp = min(pp_positions, key=lambda p: math.hypot(cx-p[1], cy-p[2]))
            connections.append({
                'from': cid, 'to': best_pp[0],
                'type': 'ethernet', 'cable': 'Cat6 UTP',
                'distance_m': dist_m(cid, best_pp[0]),
                'medium': 'copper',
                'notes': 'Camera -> Patch panel'
            })

    for sw_id in access_switches:
        sw = dev_map[sw_id]
        pp_id = sw.get('patch_panel_id')
        if pp_id:
            connections.append({
                'from': pp_id, 'to': sw_id,
                'type': 'patch_cord', 'cable': 'Cat6 patch cord',
                'distance_m': 0.5, 'medium': 'copper',
                'notes': 'Patch panel -> Access switch'
            })

    for sw_id in access_switches:
        d = dist_m(sw_id, core_sw_id)
        medium = 'fiber' if d > 50 else 'copper'
        connections.append({
            'from': sw_id, 'to': core_sw_id,
            'type': 'ethernet_trunk', 'speed': '1 Gbps',
            'distance_m': d, 'medium': medium,
            'cable': 'Fiber OM3' if medium == 'fiber' else 'Cat6 UTP',
            'notes': 'Access -> Core uplink'
        })

    aps = [d for d in devices if d['type'] == 'Access Point']
    all_switches = [d for d in devices if d['type'] == 'Switch' and d.get('layer') != 'Core'] + [dev_map[core_sw_id]]
    for ap in aps:
        nearest = min(all_switches, key=lambda s: math.hypot(ap['x']-s['x'], ap['y']-s['y']))
        connections.append({
            'from': ap['device_id'], 'to': nearest['device_id'],
            'type': 'wifi_uplink', 'medium': 'copper',
            'distance_m': dist_m(ap['device_id'], nearest['device_id']),
            'notes': 'AP uplink to switch'
        })

    router = next(d for d in devices if d['type'] == 'Router')
    firewall = next(d for d in devices if d['type'] == 'Firewall')
    server = next(d for d in devices if d['type'] == 'Server')
    for frm, to, speed, note in [
        (core_sw_id, router['device_id'], '10 Gbps', 'Core -> Router (primary)'),
        (core_sw_id, router['device_id'], '10 Gbps', 'Core -> Router (redundant)'),
        (router['device_id'], firewall['device_id'], '1 Gbps', 'Router -> Firewall'),
        (firewall['device_id'], server['device_id'], '1 Gbps', 'Firewall -> Server'),
    ]:
        d = dist_m(frm, to)
        connections.append({
            'from': frm, 'to': to,
            'type': 'ethernet_redundant' if 'redundant' in note else 'ethernet',
            'speed': speed,
            'cable': 'Fiber OM3' if d > 30 else 'Cat6 UTP',
            'distance_m': d, 'medium': 'fiber' if d > 30 else 'copper',
            'notes': note
        })

    return connections

# ============================================================================
# Main Optimizer
# ============================================================================
def run_complete_optimizer(rooms_list, scale=0.05, eps=200):
    rooms = load_rooms(rooms_list, scale)
    if not rooms:
        return {
            'devices': [],
            'connections': [],
            'metadata': {
                'total_rooms': 0,
                'error': 'No rooms provided'
            }
        }
    clusters, centroids = cluster_rooms(rooms, eps=eps)
    # Ensure clusters is non-empty (if somehow empty, fallback to per-room clusters)
    if not clusters:
        clusters = [[i] for i in range(len(rooms))]
        centroids = [(r['center']['x'], r['center']['y']) for r in rooms]
    ga_wireless = WirelessGA(clusters, centroids, rooms, scale=scale)
    best_aps, best_cost_w = ga_wireless.run()
    devices, access_switches, patch_panels, outlets, cams, core_sw = generate_devices(
        rooms, clusters, centroids, best_aps, scale
    )
    connections = build_connections(devices, access_switches, patch_panels, outlets, cams, core_sw, scale)
    device_counts = defaultdict(int)
    for d in devices:
        device_counts[d['type']] += 1
    total_ports_needed = sum(r['ports'] for r in rooms) + sum(r['cameras'] for r in rooms) + sum(best_aps)
    return {
        'devices': devices,
        'connections': connections,
        'metadata': {
            'total_rooms': len(rooms),
            'total_devices': len(devices),
            'total_data_outlets': sum(r['ports'] for r in rooms),
            'total_cameras': sum(r['cameras'] for r in rooms),
            'total_aps': sum(best_aps),
            'total_access_switches': len(access_switches),
            'total_patch_panels': len(patch_panels),
            'total_ports_needed': total_ports_needed,
            'wireless_ga_best_cost': best_cost_w,
            'device_breakdown': dict(device_counts),
            'scale_m_per_px': scale,
            'clustering_eps': eps,
        }
    }

# ============================================================================
# FastAPI Endpoint
# ============================================================================
app = FastAPI()

@app.post("/optimize")
async def optimize(request: Request):
    try:
        data = await request.json()
        rooms = data.get('rooms', [])
        scale = float(data.get('scale', 0.05))
        eps = int(data.get('eps', 200))
        if not rooms:
            return JSONResponse(status_code=400, content={"error": "Missing 'rooms' list"})
        result = run_complete_optimizer(rooms, scale, eps)
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

if __name__ == "__main__":
    import uvicorn
uvicorn.run(app, host="0.0.0.0", port=8022)