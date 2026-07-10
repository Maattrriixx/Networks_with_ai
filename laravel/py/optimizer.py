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
    'Laboratory':          {'density': 1.0, 'min': 4,  'max': 20, 'weight': 2.0},
    'Library':             {'density': 1.0, 'min': 4,  'max': 16, 'weight': 2.0},
    'Classroom':           {'density': 1.0, 'min': 2,  'max': 12, 'weight': 1.5},
    'Meeting Room':        {'density': 1.0, 'min': 2,  'max': 12, 'weight': 1.2},
    'Office':              {'density': 1.0, 'min': 1,  'max': 8,  'weight': 1.0},
    'Cafe':                {'density': 0.5, 'min': 1,  'max': 4,  'weight': 0.5},
    'Lobby':               {'density': 0.3, 'min': 1,  'max': 4,  'weight': 0.5},
    'Server Room':         {'density': 1.5, 'min': 8,  'max': 48, 'weight': 3.0},
    'WC':                  {'density': 0,   'min': 0,  'max': 0,  'weight': 0},
    'Stairs':              {'density': 0,   'min': 0,  'max': 0,  'weight': 0},
    'Storage':             {'density': 0,   'min': 0,  'max': 0,  'weight': 0},
    'other':               {'density': 1.0, 'min': 1,  'max': 4,  'weight': 1.0},
}

CAMERA_REQUIREMENTS = {
    'Laboratory': 2,
    'Library': 2,
    'Classroom': 1,
    'Meeting Room': 1,
    'Cafe': 1,
    'Lobby': 1,
    'Server Room': 2,
    'Office': 0,
    'WC': 0,
    'Stairs': 0,
    'Storage': 0,
    'other': 0,
}

# ============================================================================
# Helpers
# ============================================================================
def get_room_id(r):
    """
    استخرج الـ id الحقيقي للغرفة من الباك بأي شكل جاء:
    - 'id' أو 'room_id' كـ integer أو string
    دايماً يرجع نفس القيمة بالضبط كما هي من الباك
    """
    rid = r.get('id') or r.get('room_id')
    if rid is None:
        raise ValueError(f"Room has no 'id' or 'room_id': {r}")
    return rid

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

def polygon_centroid(corners):
    if len(corners) < 3:
        if not corners:
            return {'x': 0.0, 'y': 0.0}
        return {
            'x': sum(p['x'] for p in corners) / len(corners),
            'y': sum(p['y'] for p in corners) / len(corners),
        }

    signed_area = 0.0
    cx = 0.0
    cy = 0.0
    n = len(corners)
    for i in range(n):
        x1, y1 = corners[i]['x'], corners[i]['y']
        x2, y2 = corners[(i + 1) % n]['x'], corners[(i + 1) % n]['y']
        cross = x1 * y2 - x2 * y1
        signed_area += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross

    if abs(signed_area) < 1e-9:
        return {
            'x': sum(p['x'] for p in corners) / len(corners),
            'y': sum(p['y'] for p in corners) / len(corners),
        }

    signed_area *= 0.5
    return {
        'x': cx / (6.0 * signed_area),
        'y': cy / (6.0 * signed_area),
    }

def point_in_polygon(px, py, corners):
    inside = False
    j = len(corners) - 1
    for i in range(len(corners)):
        xi, yi = corners[i]['x'], corners[i]['y']
        xj, yj = corners[j]['x'], corners[j]['y']
        intersects = ((yi > py) != (yj > py)) and (
            px < (xj - xi) * (py - yi) / ((yj - yi) or 1e-9) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside

def room_bounds(corners):
    xs = [p['x'] for p in corners]
    ys = [p['y'] for p in corners]
    return min(xs), max(xs), min(ys), max(ys)

def point_distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])

def move_towards(point, target, distance):
    dx = target[0] - point[0]
    dy = target[1] - point[1]
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return point
    ratio = min(1.0, distance / length)
    return (point[0] + dx * ratio, point[1] + dy * ratio)

def room_padding(room):
    corners = room.get('corners', [])
    if len(corners) < 3:
        return 16.0
    min_x, max_x, min_y, max_y = room_bounds(corners)
    span = min(max_x - min_x, max_y - min_y)
    return max(12.0, min(30.0, span * 0.12))

def generate_grid_candidates(corners, count, padding, area='full'):
    if len(corners) < 3:
        return []

    min_x, max_x, min_y, max_y = room_bounds(corners)
    left = min_x + padding
    right = max_x - padding
    top = min_y + padding
    bottom = max_y - padding

    if right <= left:
        left, right = min_x, max_x
    if bottom <= top:
        top, bottom = min_y, max_y

    width = max(1.0, right - left)
    height = max(1.0, bottom - top)

    if area == 'upper':
        bottom = top + max(height * 0.45, min(36.0, height))
    elif area == 'lower':
        top = bottom - max(height * 0.45, min(36.0, height))
    elif area == 'left':
        right = left + max(width * 0.45, min(36.0, width))
    elif area == 'right':
        left = right - max(width * 0.45, min(36.0, width))

    target = max(4, count * 3)
    cols = max(2, math.ceil(math.sqrt(target * max(width, 1.0) / max(height, 1.0))))
    rows = max(2, math.ceil(target / cols))

    xs = np.linspace(left, right, cols)
    ys = np.linspace(top, bottom, rows)

    candidates = []
    for y in ys:
        for x in xs:
            if point_in_polygon(float(x), float(y), corners):
                candidates.append((float(x), float(y)))
    return candidates

def select_spread_points(candidates, count, centroid, edge_bias=0.0):
    if count <= 0 or not candidates:
        return []

    remaining = list(dict.fromkeys((round(x, 3), round(y, 3)) for x, y in candidates))
    centroid_tuple = (centroid['x'], centroid['y'])
    selected = []

    first = max(remaining, key=lambda p: point_distance(p, centroid_tuple) + edge_bias)
    selected.append(first)
    remaining.remove(first)

    while remaining and len(selected) < count:
        def score(candidate):
            min_sep = min(point_distance(candidate, s) for s in selected)
            return min_sep + point_distance(candidate, centroid_tuple) * edge_bias
        best = max(remaining, key=score)
        selected.append(best)
        remaining.remove(best)

    return [(float(x), float(y)) for x, y in selected]

def fallback_spiral_points(center, count, step=16.0):
    if count <= 0:
        return []
    points = []
    for idx in range(count):
        if idx == 0:
            points.append((center['x'], center['y']))
            continue
        angle = idx * 2.399963229728653
        radius = step * math.sqrt(idx)
        points.append((
            center['x'] + radius * math.cos(angle),
            center['y'] + radius * math.sin(angle),
        ))
    return points

def distribute_room_devices(room, count, purpose='outlet'):
    if count <= 0:
        return []

    corners = room.get('corners', [])
    center = room.get('center') or polygon_centroid(corners)
    if len(corners) < 3:
        return fallback_spiral_points(center, count)

    padding = room_padding(room)
    centroid_tuple = (center['x'], center['y'])

    if purpose == 'camera':
        inset = padding + 6.0
        corner_candidates = [
            move_towards((c['x'], c['y']), centroid_tuple, inset)
            for c in corners
        ]
        candidates = [
            p for p in corner_candidates
            if point_in_polygon(p[0], p[1], corners)
        ]
        candidates.extend(generate_grid_candidates(corners, count, padding, area='upper'))
        selected = select_spread_points(candidates, count, center, edge_bias=0.15)
    else:
        candidates = generate_grid_candidates(corners, count, padding, area='full')
        selected = select_spread_points(candidates, count, center, edge_bias=0.35)

    if len(selected) < count:
        extra = fallback_spiral_points(center, count - len(selected), step=padding)
        selected.extend(extra)

    return [(round(x, 2), round(y, 2)) for x, y in selected[:count]]

def choose_cluster_anchor_room(cluster_indices, rooms):
    cluster_rooms = [rooms[idx] for idx in cluster_indices]
    server_rooms = [room for room in cluster_rooms if room['type'] == 'Server Room']
    if server_rooms:
        return max(server_rooms, key=lambda room: (room['ports'] + room['cameras'], room['area_m2']))
    return max(
        cluster_rooms,
        key=lambda room: (
            room['ports'] + room['cameras'],
            room['density_weight'],
            room['area_m2'],
        ),
    )

def choose_core_room(rooms):
    server_rooms = [room for room in rooms if room['type'] == 'Server Room']
    if server_rooms:
        return max(server_rooms, key=lambda room: room['area_m2'])

    preferred_types = {'Office', 'Laboratory', 'Library', 'Meeting Room'}
    candidates = [room for room in rooms if room['type'] in preferred_types]
    if candidates:
        return max(candidates, key=lambda room: (room['area_m2'], room['ports'] + room['cameras']))

    return max(rooms, key=lambda room: (room['area_m2'], room['ports'] + room['cameras']))

def layout_in_anchor_room(room, count, zone='lower_left'):
    if count <= 0:
        return []

    corners = room.get('corners', [])
    center = room.get('center') or polygon_centroid(corners)
    if len(corners) < 3:
        return fallback_spiral_points(center, count, step=22.0)

    zone_map = {
        'upper_left': ('upper', 'left'),
        'upper_right': ('upper', 'right'),
        'lower_left': ('lower', 'left'),
        'lower_right': ('lower', 'right'),
    }
    vertical_zone, horizontal_zone = zone_map.get(zone, ('lower', 'left'))

    padding = room_padding(room)
    candidates = generate_grid_candidates(corners, count, padding, area=vertical_zone)
    side_candidates = generate_grid_candidates(corners, count, padding, area=horizontal_zone)
    candidates.extend(side_candidates)
    selected = select_spread_points(candidates, count, center, edge_bias=0.1)

    if len(selected) < count:
        full_candidates = generate_grid_candidates(corners, count, padding, area='full')
        selected.extend(select_spread_points(full_candidates, count - len(selected), center, edge_bias=0.05))

    if len(selected) < count:
        selected.extend(fallback_spiral_points(center, count - len(selected), step=padding + 4.0))

    return [(round(x, 2), round(y, 2)) for x, y in selected[:count]]

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
    if t in ('lobby', 'entrance'):
        return 'Lobby'
    if t in ('server room', 'server'):
        return 'Server Room'
    if t in ('wc', 'bathroom', 'toilet'):
        return 'WC'
    if t in ('stairs', 'staircase'):
        return 'Stairs'
    if t in ('storage', 'closet'):
        return 'Storage'
    return 'other'

def load_rooms(rooms_list, scale=0.05):
    result = []
    for r in rooms_list:
        # استخرج الـ id الحقيقي من الباك بأمان
        rid = get_room_id(r)
        corners = r.get('corners', [])
        area_px = polygon_area(corners)
        area_m2 = area_px * (scale ** 2)
        rtype = normalize_type(r.get('type', 'other'))
        port_cfg = ROOM_PORT_REQUIREMENTS.get(rtype, ROOM_PORT_REQUIREMENTS['other'])
        raw_ports = math.floor(area_m2 * port_cfg['density']) if port_cfg['density'] > 0 else 0
        ports = max(port_cfg['min'], min(port_cfg['max'], raw_ports))
        cameras = CAMERA_REQUIREMENTS.get(rtype, 0)
        center = r.get('center') or polygon_centroid(corners)
        result.append({
            'id': rid,          # الـ id الحقيقي من الباك بالضبط
            'type': rtype,
            'center': center,
            'corners': corners,
            'area_m2': round(area_m2, 2),
            'ports': ports,
            'cameras': cameras,
            'density_weight': port_cfg['weight'],
        })
    return result

def compute_adaptive_eps(rooms, requested_eps):
    if len(rooms) < 2:
        return requested_eps

    centers = [(r['center']['x'], r['center']['y']) for r in rooms]
    nearest_neighbor_distances = []
    room_spans = []

    for idx, room in enumerate(rooms):
        cx, cy = centers[idx]
        distances = [
            math.hypot(cx - ox, cy - oy)
            for j, (ox, oy) in enumerate(centers)
            if j != idx
        ]
        if distances:
            nearest_neighbor_distances.append(min(distances))

        corners = room.get('corners', [])
        if len(corners) >= 3:
            min_x, max_x, min_y, max_y = room_bounds(corners)
            room_spans.append(max(max_x - min_x, max_y - min_y))

    if not nearest_neighbor_distances:
        return requested_eps

    median_nn = float(np.median(nearest_neighbor_distances))
    avg_span = float(np.mean(room_spans)) if room_spans else 60.0

    lower_bound = max(50.0, avg_span * 1.05)
    upper_bound = max(lower_bound, median_nn * 0.82)

    return max(lower_bound, min(float(requested_eps), upper_bound))

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
# Genetic Algorithm for Access Switches
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
# Device Generation
# ============================================================================
def generate_devices(rooms, clusters, centroids, best_switches, scale=0.05):
    devices = []
    device_id = 0
    room_outlets = {}
    room_cameras = {}

    # Data Outlets and Cameras per room
    for room in rooms:
        # الـ id هون هو نفس الـ id الحقيقي من الباك
        room_id = room['id']
        n_ports = room['ports']
        n_cams = room['cameras']
        outlet_ids = []
        outlet_positions = distribute_room_devices(room, n_ports, purpose='outlet')
        for i, (x, y) in enumerate(outlet_positions):
            devices.append({
                'device_id': device_id,
                'type': 'Data Outlet',
                'room_id': room_id,    # الـ id الحقيقي من الباك
                'x': x,
                'y': y,
                'connectivity': 'wired',
                'notes': f'Data outlet {i+1} in room {room_id}'
            })
            outlet_ids.append(device_id)
            device_id += 1
        room_outlets[room_id] = outlet_ids

        cam_ids = []
        camera_positions = distribute_room_devices(room, n_cams, purpose='camera')
        for j, (x, y) in enumerate(camera_positions):
            devices.append({
                'device_id': device_id,
                'type': 'Camera',
                'room_id': room_id,    # الـ id الحقيقي من الباك
                'x': x,
                'y': y,
                'connectivity': 'wired',
                'notes': f'Camera {j+1} in room {room_id}'
            })
            cam_ids.append(device_id)
            device_id += 1
        room_cameras[room_id] = cam_ids

    # Access Switches and Patch Panels per cluster
    access_switches = []
    patch_panels = []
    for cid, sw_count in enumerate(best_switches):
        if sw_count == 0:
            continue
        total_ports_needed = sum(rooms[idx]['ports'] + rooms[idx]['cameras'] for idx in clusters[cid])
        ports_per_switch = 24
        num_switches_needed = math.ceil(total_ports_needed / ports_per_switch)
        actual_sw_count = max(sw_count, num_switches_needed)
        anchor_room = choose_cluster_anchor_room(clusters[cid], rooms)
        cluster_room_id = anchor_room['id']
        slot_positions = layout_in_anchor_room(anchor_room, actual_sw_count * 2, zone='lower_left')
        if len(slot_positions) < actual_sw_count * 2:
            slot_positions.extend(fallback_spiral_points(anchor_room['center'], actual_sw_count * 2 - len(slot_positions), step=24.0))

        for i in range(actual_sw_count):
            pp_x, pp_y = slot_positions[i * 2]
            sw_x, sw_y = slot_positions[i * 2 + 1]

            pp_id = device_id
            devices.append({
                'device_id': device_id,
                'type': 'Patch Panel',
                'subtype': 'UTP Cat6',
                'ports': ports_per_switch,
                'cluster_id': cid,
                'room_id': cluster_room_id,    # id حقيقي من الباك
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
                'room_id': cluster_room_id,    # id حقيقي من الباك
                'x': round(sw_x, 2),
                'y': round(sw_y, 2),
                'connectivity': 'wired',
                'notes': f'Access switch {i+1} for cluster {cid} ({ports_per_switch} ports, {used_ports} used)'
            })
            access_switches.append(sw_id)
            device_id += 1

    # Core infrastructure - يروح لغرفة السيرفر أو أول غرفة
    core_room = choose_core_room(rooms)
    core_room_id = core_room['id']
    core_positions = layout_in_anchor_room(core_room, 5, zone='lower_right')
    if len(core_positions) < 5:
        core_positions.extend(fallback_spiral_points(core_room['center'], 5 - len(core_positions), step=26.0))
    (core_sw_x, core_sw_y), (router_x, router_y), (firewall_x, firewall_y), (server_x, server_y), (ups_x, ups_y) = core_positions[:5]

    core_sw = {
        'device_id': device_id,
        'type': 'Switch',
        'layer': 'Core',
        'ports': 48,
        'used_ports': len(access_switches),
        'x': round(core_sw_x, 2),
        'y': round(core_sw_y, 2),
        'room_id': core_room_id,    # id حقيقي من الباك
        'connectivity': 'wired',
        'notes': 'Core Switch'
    }
    devices.append(core_sw)
    device_id += 1

    router = {
        'device_id': device_id,
        'type': 'Router',
        'x': round(router_x, 2),
        'y': round(router_y, 2),
        'room_id': core_room_id,    # id حقيقي من الباك
        'connectivity': 'wired',
        'notes': 'Main Router'
    }
    devices.append(router)
    device_id += 1

    firewall = {
        'device_id': device_id,
        'type': 'Firewall',
        'x': round(firewall_x, 2),
        'y': round(firewall_y, 2),
        'room_id': core_room_id,    # id حقيقي من الباك
        'connectivity': 'wired',
        'notes': 'Main Firewall'
    }
    devices.append(firewall)
    device_id += 1

    server = {
        'device_id': device_id,
        'type': 'Server',
        'role': 'DC/DHCP/DNS',
        'x': round(server_x, 2),
        'y': round(server_y, 2),
        'room_id': core_room_id,    # id حقيقي من الباك
        'connectivity': 'wired',
        'notes': 'Main Server'
    }
    devices.append(server)
    device_id += 1

    devices.append({
        'device_id': device_id,
        'type': 'UPS',
        'capacity_kva': 3.0,
        'protects': [core_sw['device_id'], router['device_id'], firewall['device_id'], server['device_id']],
        'x': round(ups_x, 2),
        'y': round(ups_y, 2),
        'room_id': core_room_id,    # id حقيقي من الباك
        'connectivity': 'wired',
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
            'rooms': [],
            'devices': [],
            'connections': [],
            'metadata': {
                'total_rooms': 0,
                'error': 'No rooms provided'
            }
        }

    effective_eps = compute_adaptive_eps(rooms, eps)
    clusters, centroids = cluster_rooms(rooms, eps=effective_eps)
    if not clusters:
        clusters = [[i] for i in range(len(rooms))]
        centroids = [(r['center']['x'], r['center']['y']) for r in rooms]

    ga_wired = WiredGA(clusters, centroids, rooms, scale=scale)
    best_switches, best_cost = ga_wired.run()

    devices, access_switches, patch_panels, outlets, cams, core_sw = generate_devices(
        rooms, clusters, centroids, best_switches, scale
    )
    connections = build_connections(devices, access_switches, patch_panels, outlets, cams, core_sw, scale)

    # ================================================================
    # بناء rooms_map من البيانات الأصلية من الباك بالضبط
    # مع دعم 'id' و 'room_id' وبأي نوع (int أو string)
    # ================================================================
    original_rooms_map = {}
    for r in rooms_list:
        rid = get_room_id(r)
        original_rooms_map[rid] = r

    rooms_map = {}
    for room in rooms:
        rid = room['id']  # هاد هو الـ id الحقيقي من الباك
        original = original_rooms_map.get(rid, {})
        room_entry = original.copy()
        room_entry['id'] = rid           # تأكد إنو 'id' موجود دايماً
        room_entry['room_id'] = rid      # أضف 'room_id' كمان للتوافق مع Laravel
        room_entry['devices'] = []
        rooms_map[rid] = room_entry

    # ================================================================
    # وزّع الأجهزة على الغرف — كل جهاز عنده room_id حقيقي من الباك
    # ================================================================
    unassigned_devices = []
    for device in devices:
        room_id = device.get('room_id')
        if room_id is not None and room_id in rooms_map:
            rooms_map[room_id]['devices'].append(device)
        else:
            unassigned_devices.append(device)

    aggregated_rooms = list(rooms_map.values())

    # ================================================================
    # قائمة مسطحة بكل الأجهزة مع room_id لتسهيل الحفظ بالـ DB
    # ================================================================
    all_devices = devices + unassigned_devices

    device_counts = defaultdict(int)
    for d in devices:
        device_counts[d['type']] += 1
    total_ports_needed = sum(r['ports'] for r in rooms) + sum(r['cameras'] for r in rooms)

    return {
        'rooms': aggregated_rooms,          # كل غرفة ببياناتها الأصلية من الباك + devices[]
        'devices': all_devices,             # كل الأجهزة flat مع room_id حقيقي لكل جهاز
        'unassigned_devices': unassigned_devices,
        'connections': connections,
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
            'clustering_eps': effective_eps,
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
