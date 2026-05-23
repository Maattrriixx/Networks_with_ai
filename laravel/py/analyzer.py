import cv2
import numpy as np
from ultralytics import YOLO
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import json
import io
import base64



MODEL_PATH   = 'best.pt'        
MERGE_DIST   = 15
ROOM_COLOR_BGR = (0, 200, 255)
CORNER_COLOR   = (0, 0, 255)
CORNER_RADIUS  = 4
LINE_THICKNESS = 1
FONT           = cv2.FONT_HERSHEY_SIMPLEX

PALETTE = [
    '#e6194b','#3cb44b','#4363d8','#f58231','#911eb4',
    '#42d4f4','#f032e6','#bfef45','#fabed4','#469990',
    '#dcbeff','#9A6324','#fffac8','#800000','#aaffc3',
]

def _in_poly(px, py, points):
    n, inside, j = len(points), False, len(points) - 1
    for i in range(n):
        xi, yi = points[i]; xj, yj = points[j]
        if ((yi > py) != (yj > py)) and (px < (xj-xi)*(py-yi)/(yj-yi+1e-10)+xi):
            inside = not inside
        j = i
    return inside

def polygon_centroid(points):
    pts = np.array(points, dtype=float)
    x, y = pts[:, 0], pts[:, 1]
    x_ext = np.append(x, x[0]); y_ext = np.append(y, y[0])
    A, Cx, Cy = 0.0, 0.0, 0.0
    for i in range(len(points)):
        c = x_ext[i]*y_ext[i+1] - x_ext[i+1]*y_ext[i]
        A += c; Cx += (x_ext[i]+x_ext[i+1])*c; Cy += (y_ext[i]+y_ext[i+1])*c
    A *= 0.5
    if abs(A) < 1e-6:
        return int(np.mean(x)), int(np.mean(y))
    Cx /= (6*A); Cy /= (6*A)
    if _in_poly(Cx, Cy, points):
        return int(Cx), int(Cy)
    x_min, x_max = int(min(x)), int(max(x))
    y_min, y_max = int(min(y)), int(max(y))
    step = max(1, min(x_max-x_min, y_max-y_min)//20)
    best_pt, best_d = (int(np.mean(x)), int(np.mean(y))), -1
    contour = np.array(points, dtype=np.float32).reshape(-1,1,2)
    for gx in range(x_min, x_max, step):
        for gy in range(y_min, y_max, step):
            if not _in_poly(gx, gy, points): continue
            d = cv2.pointPolygonTest(contour, (float(gx), float(gy)), True)
            if d > best_d: best_d = d; best_pt = (gx, gy)
    return best_pt

def merge_corners(all_corners, threshold):
    unique_pts = {}
    corner_ids = []
    next_id    = 1
    for room_corners in all_corners:
        room_ids = []
        for (cx, cy) in room_corners:
            matched = None
            for uid, (ux, uy) in unique_pts.items():
                if abs(cx - ux) <= threshold and abs(cy - uy) <= threshold:
                    matched = uid
                    break
            if matched is None:
                unique_pts[next_id] = (cx, cy)
                matched  = next_id
                next_id += 1
            room_ids.append(matched)
        corner_ids.append(room_ids)
    return unique_pts, corner_ids

# Loading the model one time when the server starts 

model = YOLO(MODEL_PATH)


def process_image(image_bytes):
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("The image is blurry")

    results = model.predict(img, conf=0.3)

    overlay = img.copy()
    rooms = []
    all_corners = []

    for result in results:
        for box in result.boxes:
            cls = int(box.cls[0])
            if cls == 1:   
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                rooms.append((x1, y1, x2, y2))
                all_corners.append([
                    (x1, y1), (x2, y1), (x2, y2), (x1, y2)
                ])

    unique_pts, corner_ids = merge_corners(all_corners, MERGE_DIST)

  
    for (x1, y1, x2, y2) in rooms:
        cv2.rectangle(overlay, (x1, y1), (x2, y2), ROOM_COLOR_BGR, LINE_THICKNESS)

    for room_idx, ids in enumerate(corner_ids):
        pts = [unique_pts[i] for i in ids]
        mid_x, mid_y = polygon_centroid(pts)

        label = f"{room_idx + 1}"
        fs, ft = 0.55, 1
        (rw, rh), _ = cv2.getTextSize(label, FONT, fs, ft)
        rtx = mid_x - rw // 2
        rty = mid_y + rh // 2

        cv2.rectangle(overlay, (rtx-3, rty-rh-3), (rtx+rw+3, rty+3), (0,0,0), -1)
        cv2.putText(overlay, label, (rtx, rty), FONT, fs, ROOM_COLOR_BGR, ft, cv2.LINE_AA)

    for uid, (px, py) in unique_pts.items():
        cv2.circle(overlay, (px, py), CORNER_RADIUS, CORNER_COLOR, -1)
        num_label = str(uid)
        fs, ft = 0.35, 1
        (tw, th), _ = cv2.getTextSize(num_label, FONT, fs, ft)
        tx, ty = px + CORNER_RADIUS + 3, py - CORNER_RADIUS - 3
        cv2.rectangle(overlay, (tx-1, ty-th-1), (tx+tw+1, ty+1), (0,0,0), -1)
        cv2.putText(overlay, num_label, (tx, ty), FONT, fs, (255,255,255), ft, cv2.LINE_AA)

   
    h, w = img.shape[:2]
    fig, axes = plt.subplots(1, 3, figsize=(30, 10))

    axes[0].imshow(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    axes[0].axis('off')

    axes[1].imshow(cv2.cvtColor(overlay, cv2.COLOR_BGR2RGB))
    axes[1].axis('off')

    ax = axes[2]
    ax.set_xlim(0, w)
    ax.set_ylim(h, 0)
    ax.set_aspect('equal')
    ax.set_facecolor('#1a1a2e')
    ax.axis('off')

    legend_handles = []
    for room_idx, ids in enumerate(corner_ids):
        color = PALETTE[room_idx % len(PALETTE)]
        pts   = [unique_pts[i] for i in ids]
        xs = [p[0] for p in pts] + [pts[0][0]]
        ys = [p[1] for p in pts] + [pts[0][1]]
        ax.plot(xs, ys, color=color, linewidth=1.5)
        ax.fill(xs[:-1], ys[:-1], color=color, alpha=0.15)
        mid_x, mid_y = polygon_centroid(pts)
        ax.text(mid_x, mid_y, f"{room_idx+1}",
                color=color, fontsize=9, fontweight='bold',
                ha='center', va='center',
                bbox=dict(boxstyle='round,pad=0.2', fc='#1a1a2e', ec=color, lw=0.8))
        for (px, py) in pts:
            ax.plot([mid_x, px], [mid_y, py],
                    color=color, linewidth=0.6, linestyle='--', alpha=0.5)
        legend_handles.append(mpatches.Patch(color=color, label=f"{room_idx+1}: corners {ids}"))

    for uid, (px, py) in unique_pts.items():
        ax.scatter(px, py, s=60, color='#ff4444', zorder=5, edgecolors='white', linewidths=0.8)
        ax.text(px + 6, py - 6, str(uid), color='white', fontsize=7)

    ax.legend(handles=legend_handles, loc='upper right',
              fontsize=7, facecolor='#1a1a2e', edgecolor='gray')
    plt.tight_layout()

    
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='#0f0f1a')
    plt.close(fig) 
    buf.seek(0)
    final_image_base64 = base64.b64encode(buf.read()).decode('utf-8')


    rooms_json = []
    for room_idx, ids in enumerate(corner_ids):
        pts = [unique_pts[i] for i in ids]
        mid_x, mid_y = polygon_centroid(pts)
        rooms_json.append({
            "id": f"{room_idx + 1}",
            "num_corners": len(pts),
            "corners": [{"x": int(px), "y": int(py)} for (px, py) in pts],
            "center": {"x": int(mid_x), "y": int(mid_y)}
        })

    
    result = {
        "num_rooms": len(rooms_json),
        "rooms": rooms_json,
        "final_image_base64": final_image_base64
    }
    return result