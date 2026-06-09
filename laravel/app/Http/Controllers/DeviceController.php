<?php

namespace App\Http\Controllers;

use App\Services\NetworkOptimizerService;
use App\Models\Project;
use App\Models\Device;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;

class DeviceController extends Controller
{
    public function runOptimization($projectId, NetworkOptimizerService $optimizerService)
    {
        $project = Project::findOrFail($projectId);

        // 1. تحديث حالة المشروع إلى جاري المعالجة (لإعطاء مؤشر للفرونت إند)
        $project->update(['status' => 'processing']);

        // 2. استدعاء سكريبت البايثون وجلب التوزيع الأمثل للشبكة
        $result = $optimizerService->optimizeProjectNetwork($project);

        if (!$result) {
            $project->update(['status' => 'error']);
            return response()->json(['success' => false, 'message' => 'حدث خطأ أثناء معالجة الشبكة من خادم الذكاء الاصطناعي'], 500);
        }

        // 3. استخدام الـ DB Transaction لضمان حفظ البيانات بشكل سليم وآمن بالكامل
        DB::beginTransaction();
        try {
            // حذف أي أجهزة قديمة تم تخزينها مسبقاً لهذا المشروع لتجنب التكرار
            Device::where('project_id', $project->id)->delete();

            // [تعديل جديد]: حذف أي توصيلات قديمة مسجلة لهذا المشروع من جدول الـ connections لتجنب التكرار
            DB::table('connections')->where('project_id', $project->id)->delete();

            $devicesSavedCount = 0;
            $devicesData = $result['devices'] ?? [];

            // 4. عمل Loop لمعالجة وحفظ كل جهاز قادم من سكريبت البايثون
            foreach ($devicesData as $device) {

                // تحويل الأنواع النصية المتباعدة من بايثون إلى الـ Enum المطابق في المايجريشن الخاص بك
                $rawType = strtolower(trim($device['type']));
                $dbType = match ($rawType) {
                    'access point' => 'access_point',
                    'camera'       => 'camera',
                    'switch'       => 'switch',
                    'router'       => 'router',
                    'firewall'     => 'firewall',
                    'patch panel'  => 'patch_panel',
                    'ups'          => 'ups',
                    'server'       => 'server',
                    default        => null,
                };

                // تخطي الجهاز في حال ظهر نوع غير متوقع لحماية قاعدة البيانات من الأخطاء
                if (!$dbType) {
                    continue;
                }

                // تخزين الجهاز في قاعدة البيانات
                Device::create([
                    'project_id'  => $project->id,
                    'device_code' => 'DEV-' . $project->id . '-' . $device['device_id'],
                    'type'        => $dbType,
                    'room_id'     => $device['room_id'] ?? null,
                    'cluster_id'  => $device['cluster_id'] ?? null,
                    'x'           => (float) $device['x'],
                    'y'           => (float) $device['y'],
                    'ports'       => $device['ports'] ?? null,
                    'model'       => $device['model'] ?? null,
                    'status'      => 'planned', // الحالة الافتراضية
                    'notes'       => $device['notes'] ?? null,
                ]);

                $devicesSavedCount++;
            }

            // [مكان التعديل الجوهري]: عمل حلقة مخصصة لتخزين الروابط والأسلاك في جدول الـ connections
            $connectionsData = $result['connections'] ?? [];
            foreach ($connectionsData as $conn) {
                DB::table('connections')->insert([
                    'project_id'     => $project->id,
                    'from_device_id' => $conn['from'],
                    'to_device_id'   => $conn['to'],
                    'type'           => $conn['type'],
                    'speed'          => $conn['speed'] ?? null,
                    'distance_m'     => (float) $conn['distance_m'],
                    'medium'         => $conn['medium'] ?? 'copper',
                    'notes'          => $conn['notes'] ?? null,
                    'created_at'     => now(),
                    'updated_at'     => now(),
                ]);
            }

            // 5. تحديث حالة المشروع إلى "مكتمل" وتخزين العدد الإجمالي للأجهزة المكتشفة
            $project->update([
                'status' => 'completed',
                'total_device' => $devicesSavedCount,
                'network_metadata' => $result['metadata'] ?? null,
            ]);

            // اعتماد الحفظ النهائي في قاعدة البيانات للعمليتين معاً (الأجهزة والتوصيلات)
            DB::commit();

            // إرجاع رد نجاح للفرونت إند يحتوي على النتيجة كاملة
            return response()->json([
                'success' => true,
                'message' => 'تمت معالجة الشبكة وحفظ الأجهزة والتوصيلات بنجاح في قاعدة البيانات.',
                'total_devices_saved' => $devicesSavedCount,
                'connections' => $connectionsData,
                'metadata' => $result['metadata'] ?? []
            ], 200);
        } catch (\Exception $e) {
            // في حال حدوث أي خطأ مفاجئ، يتم التراجع عن العمليات لحماية البيانات
            DB::rollBack();

            $project->update(['status' => 'error']);

            return response()->json([
                'success' => false,
                'message' => 'حدث خطأ أثناء حفظ الأجهزة والروابط: ' . $e->getMessage()
            ], 500);
        }
    }


   
}
