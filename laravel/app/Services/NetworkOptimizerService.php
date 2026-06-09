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
        // جلب رابط الـ API من ملف الإعدادات والـ .env
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
        // 1. جلب الغرف التابعة للمشروع مع زواياها
        $rooms = $project->rooms()->with('corners')->get();

        if ($rooms->isEmpty()) {
            Log::warning("Optimization failed: Project ID {$project->id} has no rooms.");
            return null;
        }

        $roomsData = [];

        // 2. إعادة تشكيل البيانات وتجهيز المصلع والمراكز للـ API
        foreach ($rooms as $room) {
            $corners = [];
            foreach ($room->corners as $corner) {
                $corners[] = [
                    'x' => (int) $corner->x,
                    'y' => (int) $corner->y
                ];
            }

            // تحويل الأنواع لتتوافق مع دالة normalize_type في البايثون
            $rawType = trim(strtolower($room->type));
            $pyType = match ($rawType) {
                'laboratories'           => 'Laboratory',
                'classroom'              => 'Classroom',
                'café', 'cafeteria'      => 'Cafe',
                'administrative office',
                'dr.office'              => 'Office',
                'library'                => 'Library',
                'meeting room'           => 'Meeting Room',
                'server room'            => 'server room', 
                default                  => 'other',
            };

            $roomsData[] = [
                'id' => (int) $room->id,
                'type' => $pyType,
                'center' => [
                    'x' => (float) $room->center_x,
                    'y' => (float) $room->center_y
                ],
                'corners' => $corners
            ];
        }

        // 3. تحديد مقياس الرسم (scale)
        $scale = 0.05;
        if ($project->measure_of_draw === '1/50') {
            $scale = 0.02; 
        } elseif ($project->measure_of_draw === '1/200') {
            $scale = 0.10;
        }

        // 4. إرسال طلب الـ HTTP POST إلى سكريبت الـ FastAPI (بدون حقل eps)
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

            // تسجيل الخطأ في حال رد الـ API برمز خطأ
            Log::error("FastAPI Error response for project {$project->id}: " . $response->body());
            return null;
        } catch (\Exception $e) {
            // تسجيل الخطأ في حال كان سكريبت البايثون مطفأ أو الشبكة مقطوعة
            Log::error("Failed to connect to FastAPI Server: " . $e->getMessage());
            return null;
        }
    }
}