<?php

namespace App\Http\Controllers;

use App\Models\Project;
use App\Models\Room;
use App\Http\Requests\StoreProject;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Storage;
use Intervention\Image\Drivers\Gd\Driver;
use Intervention\Image\Facades\Image;
use Intervention\Image\ImageManager;

class ProjectController extends Controller
{
    public function StoreProject(StoreProject $req)
    {
        $userid = Auth::user()->id;
        $validated = $req->validated();
        $image = $req->file('image');
        if (!$req->hasFile('image')) {
            return response()->json(['error' => 'Image is required'], 422);
        }
        $path = $image->store('image', 'public');
        $validated['image'] = 'storage/' . $path;
        $validated['user_id'] = $userid;

        $manger = new ImageManager(new Driver());
        $thumb = $manger->read($image)->resize(200, 200);
        $thumbName = 'thumb' . time() . '.jpg';
        $thumbPath = 'thumbnail/' . $thumbName;
        Storage::disk('public')->put($thumbPath, (string) $thumb->toJpeg(80));
        $validated['thumbnail'] = 'storage/' . $thumbPath;

        $project = Project::create($validated);
        $project->status = 'saved';
        $project->save();

        return response()->json(['message' => 'Project created successfully', 'project' => $project], 201);
    }


    public function analyzeProject(Project $project)
    {
        if ($project->user_id !== Auth::id()) {
            return response()->json(['error' => 'Unauthorized'], 403);
        }

        $project->status = 'processing';
        $project->save();

        try {
            $imagePath = str_replace('storage/', '', $project->image);
            $imageFullPath = Storage::disk('public')->path($imagePath);

            if (!file_exists($imageFullPath)) {
                throw new \Exception('Image file not found');
            }

            $response = Http::timeout(120)
                ->attach('file', file_get_contents($imageFullPath), basename($imageFullPath))
                ->post('http://127.0.0.1:8021/analyzer');

            if (!$response->successful()) {
                throw new \Exception('Python API error: ' . $response->body());
            }

            $data = $response->json();

            $project->rooms()->delete();

            $savedRooms = [];
            foreach ($data['rooms'] as $room) {
                $savedRooms[] = Room::create([
                    'project_id' => $project->id,
                    'confidence' => 1.0,
                    'x1'         => $room['corners'][0]['x'],
                    'y1'         => $room['corners'][0]['y'],
                    'x2'         => $room['corners'][2]['x'],
                    'y2'         => $room['corners'][2]['y'],
                    'center_x'   => $room['center']['x'],
                    'center_y'   => $room['center']['y'],
                ]);
            }

            $project->status = 'completed';
            $project->save();

            return response()->json([
                'message'            => 'Analysis completed',
                'project'            => $project,
                'num_rooms'          => $data['num_rooms'],
                'rooms'              => $savedRooms,
                'final_image_base64' => $data['final_image_base64'],
            ]);
        } catch (\Exception $e) {
            $project->status = 'error';
            $project->save();

            return response()->json([
                'message' => 'Analysis failed',
                'project' => $project,
                'error'   => $e->getMessage(),
            ], 500);
        }
    }


    public function GetUserProjects()
    {
        $projects = Project::where('user_id', Auth::id())
            ->select('id', 'name', 'type', 'thumbnail')
            ->get();

        return response()->json($projects);
    }
}
