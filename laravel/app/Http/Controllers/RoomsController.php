<?php

namespace App\Http\Controllers;

use App\Models\Project;
use Illuminate\Http\Request;
use App\Models\Room;
use Illuminate\Support\Facades\Auth;

class RoomsController extends Controller
{

    const ROOM_TYPES = [
        'laboratories',
        'classroom',
        'administrative office',
        'secretary',
        'server room',
        'café',
        'lobby',
        'dr.office',
        'library',
        'meeting room',
        'wc',
    ];




    public function getRooms(Project $project)
    {
        if ($project->user_id !== Auth::id()) {
            return response()->json(['error' => 'Unauthorized'], 403);
        }

        return response()->json([
            'rooms'       => $project->rooms,
            'types'  => self::ROOM_TYPES,
        ]);
    }


    public function updateType(Room $room, Request $request)
    {
        if ($room->project->user_id !== Auth::id()) {
            return response()->json(['error' => 'Unauthorized'], 403);
        }

        $request->validate([
            'type' => 'required|in:' . implode(',', self::ROOM_TYPES)
        ]);

        $room->type = $request->type;
        $room->save();

        return response()->json([
            'message' => 'Room type updated',
            'room'    => $room->type,
        ]);
    }
    public function showRoomWithDevices($roomId)
    {
        // جلب الغرفة مع الأجهزة التابعة لها في استعلام واحد ذكي
        $room = Room::with('devices')->findOrFail($roomId);

        return response()->json([
            'success' => true,
            'data' => $room
        ], 200);
    }
}
