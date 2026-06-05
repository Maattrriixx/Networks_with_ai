<?php

namespace App\Http\Controllers;

use App\Models\Project;
use App\Models\Room;
use Illuminate\Http\Request;

class NetworkController extends Controller
{
    public function optimize(Project $project)
    {

        if (!$project->id) {
            return response()->json(['error' => 'not found'], 404);
        }
        $rooms = $project->rooms()->select('id', 'center_x', 'center_y', 'x1', 'x2', 'y1', 'y2', 'type')->get();
        $project->status = 'processing';
        $project->save();
        $untyped = $rooms->whereNull('type')->count();
        if ($untyped > 0) {
            return response()->json(['error' => 'Please classify all rooms before optimization.'], 400);
        }
        $roomsData = $rooms->map(fn($room) => [
            'id'      => (string) $room->id,
            'type'    => $room->type,
            'center'  => ['x' => $room->center_x, 'y' => $room->center_y],
            'corners' => [
                ['x' => $room->x1, 'y' => $room->y1],
                ['x' => $room->x2, 'y' => $room->y1],
                ['x' => $room->x2, 'y' => $room->y2],
                ['x' => $room->x1, 'y' => $room->y2],
            ],
        ])->values();

        try {
            $response = Http::timeout(180)
                ->post('http://127.0.0.1:8021/optimize', [
                    'rooms' => $roomsData,
                    'scale' => 0.05,
                ]);

            if (!$response->successful()) {
                throw new \Exception('Python API error: ' . $response->body());
            }
            $data = $response->json();
            $project->status = 'completed';
            $project->total_device = $data['total_devices'] ;
            $project->save();
        } catch (\Exception $e) {
            return response()->json(['error' => $e->getMessage()], 500);
        }
    }
}
