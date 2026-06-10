import json
import math
import random
import numpy as np
from sklearn.cluster import DBSCAN
from collections import defaultdict
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# ============================================================================
# Room Requirements (Wired)
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

def point_in_polygon(px, py, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]['x'], poly[i]['y']
        x2, y2 = poly[(i+1) % n]['x'], poly[(i+1) % n]['y']
        if ((y1 > py) != (y2 > py)) and (px < (x2 - x1) * (py - y1) / (y2 - y1) + x1):
            inside = not inside
    return inside

def get_room_for_point(rooms, x, y):
    """Return (room_id, room_name) for the room containing the point, or nearest room."""
    for room in rooms:
        corners = room.get('corners', [])
        if len(corners) >= 3 and point_in_polygon(x, y, corners):
            return room['id'], room['type']
    best_room = None
    best_dist = float('inf')
    for room in rooms:
        cx, cy = room['center']['x'], room['center']['y']
        d = math.hypot(x - cx, y - cy)
        if d < best_dist:
            best_dist = d
            best_room = room
    if best_room:
        return best_room['id'], best_room['type']
    return None, None

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
# Genetic Algorithm for Access Switches (Wired)
# ============================================================================
class WiredGA:
    def __init__(self, clusters, centroids, rooms, scale=0.05, max_cable_m=90.0,
                 ports_per_switch=24, pop=30, gens=80, mut=0.2, elite=5):
        self.clusters = clusters
        self.centroids = centroids
        self.rooms = rooms
        self.scale = scale
        self.max_cable_m = max_cable_m
        self.ports_per_switch = ports_per_switch
        self.n_clusters = len(clusters)
        self.pop_size = pop
        self.generations = gens
        self.mut_rate = mut
        self.elite_size = elite
        
        self.w_switch = 20
        self.w_distance = 10
        self.w_violation = 100
        self.w_density_bonus = -15
        
        self.max_switches_per_cluster = []
        for cid, indices in enumerate(clusters):
            total_ports = sum(self.rooms[i]['ports'] + self.rooms[i]['cameras'] for i in indices)
            needed = math.ceil(total_ports / self.ports_per_switch) + 2
            self.max_switches_per_cluster.append(min(needed, 8))

    def init_pop(self):
        return [[random.randint(0, self.max_switches_per_cluster[i]) 
                 for i in range(self.n_clusters)] 
                for _ in range(self.pop_size)]

    def coverage_penalty(self, individual):
        penalty = 0.0
        for cluster_idx, sw_count in enumerate(individual):
            if sw_count == 0:
                for room_idx in self.clusters[cluster_idx]:
                    penalty += 500.0
                continue
            cx, cy = self.centroids[cluster_idx]
            sw_positions = []
            for i in range(sw_count):
                angle = 2 * math.pi * i / sw_count
                rad = 40
                sw_positions.append((cx + rad * math.cos(angle), cy + rad * math.sin(angle)))
            for room_idx in self.clusters[cluster_idx]:
                rx, ry = self.rooms[room_idx]['center']['x'], self.rooms[room_idx]['center']['y']
                min_dist = min(math.hypot(rx - sx, ry - sy) for (sx, sy) in sw_positions)
                dist_m = min_dist * self.scale
                if dist_m > self.max_cable_m:
                    penalty += (dist_m - self.max_cable_m) * self.w_distance
        return penalty

    def requirement_penalty(self, individual):
        penalty = 0.0
        for cluster_idx, sw_count in enumerate(individual):
            total_ports_needed = sum(self.rooms[room_idx]['ports'] + self.rooms[room_idx]['cameras']
                                     for room_idx in self.clusters[cluster_idx])
            available_ports = sw_count * self.ports_per_switch
            if total_ports_needed > available_ports:
                shortage = total_ports_needed - available_ports
                penalty += shortage * self.w_violation
        return penalty

    def density_bonus(self, individual):
        bonus = 0.0
        for cluster_idx, sw_count in enumerate(individual):
            weights = [self.rooms[room_idx]['density_weight'] for room_idx in self.clusters[cluster_idx]]
            avg_weight = sum(weights) / len(weights) if weights else 1.0
            total_ports_needed = sum(self.rooms[room_idx]['ports'] + self.rooms[room_idx]['cameras']
                                     for room_idx in self.clusters[cluster_idx])
            needed = max(1, math.ceil(total_ports_needed / self.ports_per_switch))
            extra = max(0, sw_count - needed)
            bonus += self.w_density_bonus * extra * avg_weight
        return bonus

    def fitness(self, individual):
        total_switches = sum(individual)
        cov_pen = self.coverage_penalty(individual)
        req_pen = self.requirement_penalty(individual)
        bonus = self.density_bonus(individual)
        return cov_pen + req_pen + self.w_switch * total_switches + bonus

    def select(self, pop, fits):
        def tour():
            cand = random.sample(list(zip(pop, fits)), 3)
            return min(cand, key=lambda x: x[1])[0]
        return tour(), tour()

    def crossover(self, p1, p2):
        if self.n_clusters <= 1:
            return p1[:], p2[:]
        pt = random.randint(1, self.n_clusters - 1)
        return p1[:pt] + p2[pt:], p2[:pt] + p1[pt:]

    def mutate(self, ind):
        return [random.randint(0, self.max_switches_per_cluster[i]) 
                if random.random() < self.mut_rate else v 
                for i, v in enumerate(ind)]

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
# Device Generation (with room_id for every device)
# ============================================================================
def generate_devices(rooms, clusters, centroids, best_switches, scale=0.05):
    devices = []
    device_id = 0
    room_outlets = {}
    room_cameras = {}

    # Generate Data Outlets and Cameras per room
    for room in rooms:
        cx, cy = room['center']['x'], room['center']['y']
        n_ports = room['ports']
        n_cams = room['cameras']
        outlet_ids = []
        for i in range(n_ports):
            angle = (2 * math.pi / max(n_ports, 1)) * i
            x = round(cx + 15 * math.cos(angle), 2)
            y = round(cy + 15 * math.sin(angle), 2)
            devices.append({
                'device_id': device_id,
                'type': 'Data Outlet',
                'room_id': room['id'],
                'room_name': room['type'],
                'x': x,
                'y': y,
                'connectivity': 'wired',
                'notes': f'Data outlet {i+1} in room {room["id"]}'
            })
            outlet_ids.append(device_id)
            device_id += 1
        room_outlets[room['id']] = outlet_ids

        cam_ids = []
        for j in range(n_cams):
            angle = (2 * math.pi / max(n_cams, 1)) * j + math.pi/4
            x = round(cx + 20 * math.cos(angle), 2)
            y = round(cy + 20 * math.sin(angle), 2)
            devices.append({
                'device_id': device_id,
                'type': 'Camera',
                'room_id': room['id'],
                'room_name': room['type'],
                'x': x,
                'y': y,
                'connectivity': 'wired',
                'notes': f'Camera {j+1} in room {room["id"]}'
            })
            cam_ids.append(device_id)
            device_id += 1
        room_cameras[room['id']] = cam_ids

    # Access Switches and Patch Panels per cluster
    access_switches = []
    patch_panels = []
    for cid, sw_count in enumerate(best_switches):
        if sw_count == 0:
            continue
        cx, cy = centroids[cid]
        total_ports_needed = sum(rooms[idx]['ports'] + rooms[idx]['cameras'] for idx in clusters[cid])
        ports_per_switch = 24
        num_switches_needed = math.ceil(total_ports_needed / ports_per_switch)
        actual_sw_count = max(sw_count, num_switches_needed)
        for i in range(actual_sw_count):
            angle = (2 * math.pi / actual_sw_count) * i
            rad = 40
            sw_x = cx + rad * math.cos(angle)
            sw_y = cy + rad * math.sin(angle)
            pp_x = sw_x - 30
            pp_y = sw_y - 20
            pp_room_id, pp_room_name = get_room_for_point(rooms, pp_x, pp_y)
            sw_room_id, sw_room_name = get_room_for_point(rooms, sw_x, sw_y)

            pp_id = device_id
            devices.append({
                'device_id': device_id,
                'type': 'Patch Panel',
                'subtype': 'UTP Cat6',
                'ports': ports_per_switch,
                'cluster_id': cid,
                'room_id': pp_room_id,
                'room_name': pp_room_name,
                'x': round(pp_x, 2),
                'y': round(pp_y, 2),
                'connectivity': 'wired',
                'notes': f'Patch panel for cluster {cid} switch {i+1}'
            })
            patch_panels.append(pp_id)
            device_id += 1
            sw_id = device_id
            used_ports = min(ports_per_switch, total_ports_needed - i*ports_per_switch) if i < actual_sw_count-1 else total_ports_needed - i*ports_per_switch
            devices.append({
                'device_id': device_id,
                'type': 'Switch',
                'layer': 'Access',
                'ports': ports_per_switch,
                'used_ports': used_ports,
                'cluster_id': cid,
                'patch_panel_id': pp_id,
                'room_id': sw_room_id,
                'room_name': sw_room_name,
                'x': round(sw_x, 2),
                'y': round(sw_y, 2),
                'connectivity': 'wired',
                'notes': f'Access switch {i+1} for cluster {cid} ({ports_per_switch} ports, {used_ports} used)'
            })
            access_switches.append(sw_id)
            device_id += 1

    # Core infrastructure - assign to "Server Room" or nearest
    all_centers = [r['center'] for r in rooms]
    core_x = sum(c['x'] for c in all_centers) / len(all_centers)
    core_y = sum(c['y'] for c in all_centers) / len(all_centers)
    
    server_room = None
    for r in rooms:
        if r['type'].lower() == 'server room':
            server_room = r
            break
    if server_room:
        core_room_id, core_room_name = server_room['id'], server_room['type']
    else:
        core_room_id, core_room_name = get_room_for_point(rooms, core_x, core_y)

    core_sw = {
        'device_id': device_id,
        'type': 'Switch',
        'layer': 'Core',
        'ports': 48,
        'used_ports': len(access_switches),
        'x': round(core_x, 2),
        'y': round(core_y - 30, 2),
        'room_id': core_room_id,
        'room_name': core_room_name,
        'connectivity': 'wired',
        'notes': 'Core Switch'
    }
    devices.append(core_sw)
    device_id += 1

    router_room_id, router_room_name = get_room_for_point(rooms, core_x, core_y)
    router = {
        'device_id': device_id,
        'type': 'Router',
        'x': round(core_x, 2),
        'y': round(core_y, 2),
        'room_id': router_room_id,
        'room_name': router_room_name,
        'connectivity': 'wired',
        'notes': 'Main Router'
    }
    devices.append(router)
    device_id += 1

    fw_room_id, fw_room_name = get_room_for_point(rooms, core_x + 30, core_y + 30)
    firewall = {
        'device_id': device_id,
        'type': 'Firewall',
        'x': round(core_x + 30, 2),
        'y': round(core_y + 30, 2),
        'room_id': fw_room_id,
        'room_name': fw_room_name,
        'connectivity': 'wired',
        'notes': 'Main Firewall'
    }
    devices.append(firewall)
    device_id += 1

    srv_room_id, srv_room_name = get_room_for_point(rooms, core_x - 40, core_y - 20)
    server = {
        'device_id': device_id,
        'type': 'Server',
        'role': 'DC/DHCP/DNS',
        'x': round(core_x - 40, 2),
        'y': round(core_y - 20, 2),
        'room_id': srv_room_id,
        'room_name': srv_room_name,
        'connectivity': 'wired',
        'notes': 'Main Server'
    }
    devices.append(server)
    device_id += 1

    ups_room_id, ups_room_name = get_room_for_point(rooms, core_x + 60, core_y - 50)
    devices.append({
        'device_id': device_id,
        'type': 'UPS',
        'capacity_kva': 3.0,
        'protects': [core_sw['device_id'], router['device_id'], firewall['device_id'], server['device_id']],
        'x': round(core_x + 60, 2),
        'y': round(core_y - 50, 2),
        'room_id': ups_room_id,
        'room_name': ups_room_name,
        'connectivity': 'wired',
        'notes': 'UPS for Core Infrastructure'
    })

    return devices, access_switches, patch_panels, room_outlets, room_cameras, core_sw['device_id']

# ============================================================================
# Connection Builder (unchanged)
# ============================================================================
def build_connections(devices, access_switches, patch_panels, room_outlets, room_cameras, core_sw_id, scale=0.05):
    dev_map = {d['device_id']: d for d in devices}
    def dist_m(a_id, b_id):
        a, b = dev_map[a_id], dev_map[b_id]
        return round(math.hypot(a['x']-b['x'], a['y']-b['y']) * scale, 2)

    connections = []
    pp_positions = [(pp, dev_map[pp]['x'], dev_map[pp]['y']) for pp in patch_panels]

    # Data Outlets -> Patch Panel
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

    # Cameras -> Patch Panel
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

    # Patch Panel -> Access Switch
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

    # Access Switches -> Core Switch
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

    # Core infrastructure links
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
            'rooms': [],
            'metadata': {
                'total_rooms': 0,
                'error': 'No rooms provided'
            }
        }
    clusters, centroids = cluster_rooms(rooms, eps=eps)
    if not clusters:
        clusters = [[i] for i in range(len(rooms))]
        centroids = [(r['center']['x'], r['center']['y']) for r in rooms]

    ga_wired = WiredGA(clusters, centroids, rooms, scale=scale)
    best_switches, best_cost = ga_wired.run()

    devices, access_switches, patch_panels, outlets, cams, core_sw = generate_devices(
        rooms, clusters, centroids, best_switches, scale
    )
    connections = build_connections(devices, access_switches, patch_panels, outlets, cams, core_sw, scale)

    device_counts = defaultdict(int)
    for d in devices:
        device_counts[d['type']] += 1
    total_ports_needed = sum(r['ports'] for r in rooms) + sum(r['cameras'] for r in rooms)
    
    # Return both devices and rooms
    return {
        'devices': devices,
        'connections': connections,
        'rooms': rooms,   # ✅ now rooms list is included
        'metadata': {
            'total_rooms': len(rooms),
            'total_devices': len(devices),
            'total_data_outlets': sum(r['ports'] for r in rooms),
            'total_cameras': sum(r['cameras'] for r in rooms),
            'total_access_switches': len(access_switches),
            'total_patch_panels': len(patch_panels),
            'total_ports_needed': total_ports_needed,
            'wired_ga_best_cost': best_cost,
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