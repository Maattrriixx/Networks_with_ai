<?php

namespace App\Services;

use App\Models\Project;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

class NetworkOptimizerService
{
    protected string $apiUrl;

    public function __construct()
    {
        $this->apiUrl = config('services.network_api.url', 'http://127.0.0.1:8022');
    }

    /**
     * إرسال بيانات المشروع والغرف إلى FastAPI وجلب التوزيع الأمثل للشبكة
     *
     * @param Project $project
     * @return array|null
     */
    public function optimizeProjectNetwork(Project $project): ?array
    {
        $rooms = $project->rooms()->with('corners')->get();

        if ($rooms->isEmpty()) {
            Log::warning("Optimization failed: Project ID {$project->id} has no rooms.");
            return null;
        }

        $roomsData = [];

        foreach ($rooms as $room) {
            $rawType = strtolower(trim($room->type ?? $room->name));
            
            $pyType = match ($rawType) {
                'laboratories'          => 'Laboratory',
                'classroom'             => 'Classroom',
                'administrative office' => 'Office',
                'dr.office'             => 'Office',
                'server room'           => 'Server Room',
                'café'                  => 'Cafe',
                'library'               => 'Library',
                'meeting room'          => 'Meeting Room',
                'lobby'                 => 'Lobby',
                'wc'                    => 'WC',
                'stairs'                => 'Stairs',
                'storage'               => 'Storage',
                default                 => 'other',
            };

            $corners = [];
            $minX = null; $maxX = null;
            $minY = null; $maxY = null;

            foreach ($room->corners as $corner) {
                $cx = (float) $corner->x;
                $cy = (float) $corner->y;
                
                // التعديل الأساسي: إرسال الزوايا كـ قاموس بمفاتيح x و y ليفهمها البايثون
                $corners[] = [
                    'x' => $cx,
                    'y' => $cy
                ];

                if ($minX === null || $cx < $minX) $minX = $cx;
                if ($maxX === null || $cx > $maxX) $maxX = $cx;
                if ($minY === null || $cy < $minY) $minY = $cy;
                if ($maxY === null || $cy > $maxY) $maxY = $cy;
            }

            $width = ($maxX !== null && $minX !== null) ? ($maxX - $minX) : 10.0;
            $height = ($maxY !== null && $minY !== null) ? ($maxY - $minY) : 10.0;
            $xCoord = ($minX !== null) ? $minX : ((float)$room->center_x - ($width / 2));
            $yCoord = ($minY !== null) ? $minY : ((float)$room->center_y - ($height / 2));

            $roomsData[] = [
                'id'       => (int) $room->id,       
                'room_id'  => (int) $room->id,       
                'type'     => $pyType,
                'name'     => $room->name ?? $pyType,
                'x'        => (float) $xCoord,
                'y'        => (float) $yCoord,
                'width'    => (float) $width,
                'height'   => (float) $height,
                'center'   => [
                    'x' => (float) $room->center_x,
                    'y' => (float) $room->center_y
                ],
                'corners'  => $corners
            ];
        }

        $scale = 0.05;
        if ($project->measure_of_draw === '1/50') {
            $scale = 0.02;
        } elseif ($project->measure_of_draw === '1/200') {
            $scale = 0.10;
        }

        try {
            $response = Http::timeout(60)
                ->withHeaders(['Content-Type' => 'application/json'])
                ->post("{$this->apiUrl}/optimize", [
                    'rooms' => $roomsData,
                    'scale' => $scale,
                ]);

            if ($response->successful()) {
                return $response->json();
            }

            Log::error("FastAPI Error response for project {$project->id}: " . $response->body());
            return null;

        } catch (\Exception $e) {
            Log::error("Failed to connect to FastAPI for project {$project->id}: " . $e->getMessage());
            return null;
        }
    }
}