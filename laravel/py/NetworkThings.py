import json
import random
import math
import numpy as np
from sklearn.cluster import DBSCAN
from collections import defaultdict
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------
def polygon_area(corners):
    if len(corners) < 3:
        return 0
    area = 0
    n = len(corners)
    for i in range(n):
        x1, y1 = corners[i]['x'], corners[i]['y']
        x2, y2 = corners[(i + 1) % n]['x'], corners[(i + 1) % n]['y']
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def load_rooms_from_list(rooms):
    room_ids, room_centers, room_types, room_areas, room_corners = [], [], [], [], []
    for room in rooms:
        room_ids.append(room['id'])
        room_centers.append([float(room['center']['x']), float(room['center']['y'])])
        rtype = room.get('type', 'other').lower()
        # Normalize type names
        if rtype in ['lab', 'laboratory']:
            rtype = 'laboratories'
        elif rtype in ['class', 'classroom']:
            rtype = 'classroom'
        elif rtype in ['admin office', 'administrative office']:
            rtype = 'administrative office'
        elif rtype in ['secretary', 'secretariat']:
            rtype = 'secretary'
        elif rtype in ['cafe', 'cafeteria', 'café']:
            rtype = 'café'
        elif rtype in ['lobby', 'entrance']:
            rtype = 'lobby'
        elif rtype in ['dr office', 'dr.office', 'faculty office']:
            rtype = 'dr.office'
        elif rtype in ['library']:
            rtype = 'library'
        elif rtype in ['meeting', 'meeting room', 'conference']:
            rtype = 'meeting room'
        elif rtype in ['wc', 'bathroom', 'toilet']:
            rtype = 'wc'
        elif rtype in ['stairs', 'staircase']:
            rtype = 'Stairs'
        elif rtype in ['storage', 'closet']:
            rtype = 'Storage'
        else:
            rtype = 'other'
        room_types.append(rtype)
        corners = room.get('corners', [])
        area = polygon_area(corners) if corners else 0
        room_areas.append(area)
        room_corners.append(corners)
    return room_ids, room_centers, room_types, room_areas, room_corners


def cluster_rooms_advanced(room_centers, room_types, room_areas, scale_m_per_px=0.05, eps=150, min_samples=2):
    sensitive_types = {'laboratories', 'library', 'café', 'meeting room'}
    sensitive_indices = [i for i, rt in enumerate(room_types) if rt in sensitive_types]
    regular_indices = [i for i, rt in enumerate(room_types) if rt not in sensitive_types]

    clusters = {}
    centroids = []
    current_id = 0

    for idx in sensitive_indices:
        clusters[current_id] = [idx]
        cx, cy = room_centers[idx][0], room_centers[idx][1]
        centroids.append((cx, cy))
        current_id += 1

    if regular_indices:
        regular_centers = [room_centers[i] for i in regular_indices]
        if len(regular_centers) > 1:
            clustering = DBSCAN(eps=eps, min_samples=min_samples).fit(regular_centers)
            labels = clustering.labels_
            temp_clusters = defaultdict(list)
            for pos, label in enumerate(labels):
                orig_idx = regular_indices[pos]
                temp_clusters[label].append(orig_idx)
            for label, indices in temp_clusters.items():
                if label == -1:
                    for idx in indices:
                        clusters[current_id] = [idx]
                        cx, cy = room_centers[idx][0], room_centers[idx][1]
                        centroids.append((cx, cy))
                        current_id += 1
                else:
                    clusters[current_id] = indices
                    cx = np.mean([room_centers[i][0] for i in indices])
                    cy = np.mean([room_centers[i][1] for i in indices])
                    centroids.append((cx, cy))
                    current_id += 1
        else:
            idx = regular_indices[0]
            clusters[current_id] = [idx]
            cx, cy = room_centers[idx][0], room_centers[idx][1]
            centroids.append((cx, cy))
            current_id += 1

    cluster_areas_m2 = []
    for indices in clusters.values():
        total_area_px = sum(room_areas[i] for i in indices)
        area_m2 = total_area_px * (scale_m_per_px ** 2)
        cluster_areas_m2.append(area_m2)
    return clusters, centroids, cluster_areas_m2


# ----------------------------------------------------------------------
# Genetic Optimizer
# ----------------------------------------------------------------------
class UniversityGeneticOptimizer:
    def __init__(self, room_centers, room_types, room_areas, clusters, centroids, cluster_areas_m2,
                 scale_m_per_px=0.05, distance_threshold_m=8.0,
                 pop_size=30, generations=80, mutation_rate=0.2, elite_size=5):
        self.room_centers = room_centers
        self.room_types = room_types
        self.room_areas = room_areas
        self.clusters = clusters
        self.cluster_centroids = centroids
        self.cluster_areas_m2 = cluster_areas_m2
        self.n_clusters = len(clusters)
        self.n_rooms = len(room_centers)
        self.scale = scale_m_per_px
        self.dist_thresh = distance_threshold_m

        self.pop_size = pop_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.elite_size = elite_size

        self.requirements = {
            'laboratories': (2, 2, True),
            'classroom': (1, 1, True),
            'administrative office': (1, 0, False),
            'secretary': (1, 0, False),
            'café': (2, 1, True),
            'lobby': (1, 1, False),
            'dr.office': (1, 0, False),
            'library': (2, 2, True),
            'meeting room': (2, 1, True),
            'wc': (0, 0, False),
            'Stairs': (0, 0, False),
            'Storage': (0, 0, False),
            'other': (1, 0, False)
        }
        self.default_req = (1, 0, False)

        self.w_ap = 10
        self.w_camera = 8
        self.w_switch = 20
        self.w_requirement_violation = 100
        self.large_cluster_threshold = 100
        self.extra_ap_reward = -15

    def initialize_population(self):
        return [[random.randint(0, 3) for _ in range(self.n_clusters)] for _ in range(self.pop_size)]

    def coverage_penalty(self, aps_per_cluster):
        ap_positions = []
        for cid, n_aps in enumerate(aps_per_cluster):
            if n_aps > 0:
                cx, cy = self.cluster_centroids[cid]
                ap_positions.append((cx, cy))
        if not ap_positions:
            return self.n_rooms * 200.0
        penalty = 0.0
        for room_idx in range(self.n_rooms):
            rx, ry = self.room_centers[room_idx]
            min_dist = min(math.hypot(rx - ax, ry - ay) for (ax, ay) in ap_positions)
            dist_m = min_dist * self.scale
            if dist_m > self.dist_thresh:
                penalty += (dist_m - self.dist_thresh) * 20
        return penalty

    def requirement_penalty(self, aps_per_cluster):
        max_ap_needed = {}
        for cid, indices in self.clusters.items():
            max_needed = 0
            for idx in indices:
                rtype = self.room_types[idx]
                req = self.requirements.get(rtype, self.default_req)
                max_needed = max(max_needed, req[0])
            max_ap_needed[cid] = max_needed
        penalty = 0.0
        for cid, needed in max_ap_needed.items():
            actual = aps_per_cluster[cid]
            if actual < needed:
                penalty += (needed - actual) * self.w_requirement_violation
        return penalty

    def count_required_cameras_switches(self, aps_per_cluster):
        n_cam = 0
        n_sw = 0
        for cid, indices in self.clusters.items():
            max_cam = 0
            need_switch = False
            for idx in indices:
                rtype = self.room_types[idx]
                req = self.requirements.get(rtype, self.default_req)
                max_cam = max(max_cam, req[1])
                if req[2]:
                    need_switch = True
            n_cam += max_cam
            if need_switch or len(indices) > 1:
                n_sw += 1
        return n_cam, n_sw

    def fitness(self, individual):
        aps_per_cluster = individual
        total_aps = sum(aps_per_cluster)
        coverage_pen = self.coverage_penalty(aps_per_cluster)
        req_pen = self.requirement_penalty(aps_per_cluster)
        n_cam, n_sw = self.count_required_cameras_switches(aps_per_cluster)

        bonus = 0
        for cid, area_m2 in enumerate(self.cluster_areas_m2):
            n_aps = aps_per_cluster[cid]
            if area_m2 > self.large_cluster_threshold:
                if n_aps >= 2:
                    bonus += self.extra_ap_reward * (n_aps - 1)
                elif n_aps == 0:
                    coverage_pen += 500

        cost = coverage_pen + req_pen + self.w_ap * total_aps + self.w_camera * n_cam + self.w_switch * n_sw + bonus
        return cost

    def select_parents(self, population, fitnesses):
        tournament_size = 3
        def tournament():
            candidates = random.sample(list(zip(population, fitnesses)), tournament_size)
            best = min(candidates, key=lambda x: x[1])
            return best[0]
        return tournament(), tournament()

    def crossover(self, p1, p2):
        point = random.randint(1, self.n_clusters - 1)
        c1 = p1[:point] + p2[point:]
        c2 = p2[:point] + p1[point:]
        return c1, c2

    def mutate(self, ind):
        for i in range(self.n_clusters):
            if random.random() < self.mutation_rate:
                ind[i] = random.randint(0, 3)
        return ind

    def run(self):
        population = self.initialize_population()
        best_individual = None
        best_fitness = float('inf')
        for gen in range(self.generations):
            fitnesses = [self.fitness(ind) for ind in population]
            gen_best_idx = np.argmin(fitnesses)
            gen_best_fit = fitnesses[gen_best_idx]
            if gen_best_fit < best_fitness:
                best_fitness = gen_best_fit
                best_individual = population[gen_best_idx].copy()

            elite_indices = np.argsort(fitnesses)[:self.elite_size]
            new_pop = [population[i] for i in elite_indices]
            while len(new_pop) < self.pop_size:
                p1, p2 = self.select_parents(population, fitnesses)
                c1, c2 = self.crossover(p1, p2)
                c1 = self.mutate(c1)
                c2 = self.mutate(c2)
                new_pop.extend([c1, c2])
            population = new_pop[:self.pop_size]

            if gen % 20 == 0:
                print(f"Generation {gen}: Best fitness = {gen_best_fit:.2f}")
        return best_individual, best_fitness


# ----------------------------------------------------------------------
# Device generation and connections
# ----------------------------------------------------------------------
def generate_devices(best_aps, clusters, centroids, room_ids, room_types, room_areas, scale=0.05):
    devices = []
    device_id = 0
    requirements = {
        'laboratories': (2, 2, True),
        'classroom': (1, 1, True),
        'administrative office': (1, 0, False),
        'secretary': (1, 0, False),
        'café': (2, 1, True),
        'lobby': (1, 1, False),
        'dr.office': (1, 0, False),
        'library': (2, 2, True),
        'meeting room': (2, 1, True),
        'wc': (0, 0, False),
        'Stairs': (0, 0, False),
        'Storage': (0, 0, False),
        'other': (1, 0, False)
    }
    default_req = (1, 0, False)

    # Access Points
    for cid, n_aps in enumerate(best_aps):
        if n_aps == 0:
            continue
        cx, cy = centroids[cid]
        room_indices = clusters[cid]
        for i in range(n_aps):
            offset_x = (i - (n_aps - 1) / 2) * 30
            offset_y = (i % 2) * 20
            devices.append({
                'device_id': device_id,
                'type': 'Access Point',
                'cluster_id': cid,
                'rooms': [room_ids[idx] for idx in room_indices],
                'x': float(cx + offset_x),
                'y': float(cy + offset_y),
                'notes': f'AP {i+1} for cluster {cid}'
            })
            device_id += 1

    # Cameras and Switches per cluster
    for cid, indices in clusters.items():
        max_cam = 0
        need_switch = False
        for idx in indices:
            rtype = room_types[idx]
            req = requirements.get(rtype, default_req)
            max_cam = max(max_cam, req[1])
            if req[2]:
                need_switch = True
        cx, cy = centroids[cid]
        if max_cam > 0:
            for _ in range(max_cam):
                devices.append({
                    'device_id': device_id,
                    'type': 'Camera',
                    'cluster_id': cid,
                    'x': float(cx - 20),
                    'y': float(cy - 20),
                    'notes': f'Camera for cluster {cid}'
                })
                device_id += 1
        if need_switch or len(indices) > 1:
            devices.append({
                'device_id': device_id,
                'type': 'Switch',
                'cluster_id': cid,
                'x': float(cx + 20),
                'y': float(cy + 20),
                'ports': 24,
                'notes': f'Switch for cluster {cid}'
            })
            device_id += 1

    # Central devices
    all_centers = centroids
    avg_x = sum(c[0] for c in all_centers) / len(all_centers)
    avg_y = sum(c[1] for c in all_centers) / len(all_centers)
    devices.append({'device_id': device_id, 'type': 'Router', 'x': avg_x, 'y': avg_y, 'notes': 'Main Router'})
    device_id += 1
    devices.append({'device_id': device_id, 'type': 'Firewall', 'x': avg_x + 30, 'y': avg_y + 30, 'notes': 'Main Firewall'})
    return devices


def add_connections(devices):
    switches = [d for d in devices if d['type'] == 'Switch']
    aps = [d for d in devices if d['type'] == 'Access Point']
    cameras = [d for d in devices if d['type'] == 'Camera']
    router = [d for d in devices if d['type'] == 'Router']
    firewall = [d for d in devices if d['type'] == 'Firewall']

    core_switch = None
    access_switches = []
    for sw in switches:
        if 'cluster_id' not in sw:
            core_switch = sw
        else:
            access_switches.append(sw)
    if core_switch is None and switches:
        core_switch = switches[0]
        access_switches = switches[1:]

    connections = []

    for sw in access_switches:
        connections.append({
            'from_device': sw['device_id'],
            'to_device': core_switch['device_id'],
            'type': 'ethernet_trunk',
            'speed': '1 Gbps'
        })

    all_switches = access_switches + ([core_switch] if core_switch else [])

    for ap in aps:
        if all_switches:
            nearest = min(all_switches, key=lambda s: math.hypot(ap['x'] - s['x'], ap['y'] - s['y']))
            dist = math.hypot(ap['x'] - nearest['x'], ap['y'] - nearest['y'])
            connections.append({
                'from_device': ap['device_id'],
                'to_device': nearest['device_id'],
                'type': 'wifi_uplink',
                'distance_px': round(dist, 2)
            })
        elif core_switch:
            dist = math.hypot(ap['x'] - core_switch['x'], ap['y'] - core_switch['y'])
            connections.append({
                'from_device': ap['device_id'],
                'to_device': core_switch['device_id'],
                'type': 'wifi_uplink',
                'distance_px': round(dist, 2)
            })

    for cam in cameras:
        if all_switches:
            nearest = min(all_switches, key=lambda s: math.hypot(cam['x'] - s['x'], cam['y'] - s['y']))
            dist = math.hypot(cam['x'] - nearest['x'], cam['y'] - nearest['y'])
            connections.append({
                'from_device': cam['device_id'],
                'to_device': nearest['device_id'],
                'type': 'ethernet',
                'distance_px': round(dist, 2)
            })
        elif core_switch:
            dist = math.hypot(cam['x'] - core_switch['x'], cam['y'] - core_switch['y'])
            connections.append({
                'from_device': cam['device_id'],
                'to_device': core_switch['device_id'],
                'type': 'ethernet',
                'distance_px': round(dist, 2)
            })

    if core_switch and router:
        connections.append({
            'from_device': core_switch['device_id'],
            'to_device': router[0]['device_id'],
            'type': 'ethernet',
            'speed': '10 Gbps'
        })

    if router and firewall:
        connections.append({
            'from_device': router[0]['device_id'],
            'to_device': firewall[0]['device_id'],
            'type': 'ethernet',
            'speed': '1 Gbps'
        })

    return connections


# ----------------------------------------------------------------------
# Main optimization runner (in-memory)
# ----------------------------------------------------------------------
def run_optimizer(rooms_list, scale_m_per_px=0.05, eps=150):
    room_ids, room_centers, room_types, room_areas, _ = load_rooms_from_list(rooms_list)
    clusters, centroids, cluster_areas = cluster_rooms_advanced(
        room_centers, room_types, room_areas, scale_m_per_px, eps=eps
    )

    ga = UniversityGeneticOptimizer(
        room_centers, room_types, room_areas, clusters, centroids, cluster_areas,
        scale_m_per_px=scale_m_per_px, distance_threshold_m=8.0,
        pop_size=30, generations=80
    )
    best_aps, best_cost = ga.run()

    devices = generate_devices(best_aps, clusters, centroids, room_ids, room_types, room_areas, scale=scale_m_per_px)
    connections = add_connections(devices)

    return {
        "total_rooms": len(room_ids),
        "total_devices": len(devices),
        "devices": devices,
        "connections": connections,
        "metadata": {
            "clustering_method": "dbscan_advanced",
            "eps": eps,
            "scale_m_per_px": scale_m_per_px,
            "best_fitness": float(best_cost),
            "num_clusters": len(clusters)
        }
    }


