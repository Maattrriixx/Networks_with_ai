<?php

namespace App\Http\Controllers;

use App\Services\NetworkOptimizerService;
use App\Models\Project;
use App\Models\Device;
use App\Models\Room;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;

class DeviceController extends Controller
{
    public function runOptimization($projectId, NetworkOptimizerService $optimizerService)
    {
        $project = Project::findOrFail($projectId);

        // 1. تحديث حالة المشروع إلى جاري المعالجة
        $project->update(['status' => 'processing']);

        // 2. استدعاء سكريبت البايثون وجلب التوزيع الأمثل للشبكة
        $result = $optimizerService->optimizeProjectNetwork($project);

        if (!$result) {
            $project->update(['status' => 'error']);
            return response()->json(['success' => false, 'message' => 'حدث خطأ أثناء معالجة الشبكة من خادم الذكاء الاصطناعي'], 500);
        }

        // جلب معرفات الغرف التابعة للمشروع كخطة بديلة (Fallback) في حال عدم تعيين غرفة لجهاز معين
        $projectRoomIds = Room::where('project_id', $project->id)->pluck('id')->toArray();

        // 3. استخدام الـ DB Transaction لضمان حفظ البيانات بشكل سليم
        DB::beginTransaction();
        try {
            // حذف أي أجهزة وتوصيلات قديمة تم تخزينها مسبقاً لهذا المشروع لتجنب تكرار البيانات
            Device::where('project_id', $project->id)->delete();
            \App\Models\Connection::where('project_id', $project->id)->delete();

            $devicesSavedCount = 0;
            
            // مصفوفة لربط معرف الجهاز القادم من بايثون بالـ ID الحقيقي المتولد في قاعدة البيانات
            $deviceMapping = [];
            
            // --- تجميع كافة الأجهزة القادمة من البايثون باختلاف موقعها في الـ JSON ---
            $devicesData = [];

            // أولاً: سحب الأجهزة الموزعة داخل الغرف
            if (isset($result['rooms']) && is_array($result['rooms'])) {
                foreach ($result['rooms'] as $room) {
                    if (!empty($room['devices']) && is_array($room['devices'])) {
                        foreach ($room['devices'] as $device) {
                            if (!isset($device['room_id'])) {
                                $device['room_id'] = $room['id'];
                            }
                            $devicesData[] = $device;
                        }
                    }
                }
            }

            // ثانياً: دمج الأجهزة المركزية والمستقلة المستخرجة في جذر الـ JSON
            if (isset($result['unassigned_devices']) && is_array($result['unassigned_devices'])) {
                foreach ($result['unassigned_devices'] as $device) {
                    $devicesData[] = $device;
                }
            }
            // ----------------------------------------------------------------------

            // 4. معالجة وحفظ كل جهاز بنجاح بعد عملية التجميع الكاملة
            foreach ($devicesData as $device) {

                // تحويل الأنواع النصية القادمة من بايثون إلى الـ Enum المطابق بقاعدة البيانات
                $rawType = strtolower(trim($device['type']));
                $dbType = match ($rawType) {
                    'data outlet'   => 'data_outlet',
                    'access point'  => 'access_point',
                    'camera'        => 'camera',
                    'access switch' => 'switch',
                    'core switch'   => 'switch',
                    'switch'        => 'switch',
                    'router'        => 'router',
                    'firewall'      => 'firewall',
                    'patch panel'   => 'patch_panel',
                    'ups'           => 'ups',
                    'server'        => 'server',
                    default         => null,
                };

                // تخطي الجهاز في حال ظهر نوع غير مدعوم بحظر الـ Enum
                if (!$dbType) {
                    continue;
                }

                // استخراج معرف الغرفة المباشر الذي أرسله البايثون
                $roomId = $device['room_id'] ?? null;

                // إذا أرجع بايثون المعرف كـ 0 أو فارغ، يتم ربطه تلقائياً بأول غرفة في المشروع كـ Fallback آمن
                if (($roomId === 0 || empty($roomId)) && !empty($projectRoomIds)) {
                    $roomId = $projectRoomIds[0];
                }

                // تخزين الجهاز في قاعدة البيانات والاحتفاظ بالـ Object المتولد
                $savedDevice = Device::create([
                    'project_id'  => $project->id,
                    'device_code' => 'DEV-' . $project->id . '-' . $device['device_id'],
                    'type'        => $dbType,
                    'room_id'     => $roomId,
                    'cluster_id'  => $device['cluster_id'] ?? null,
                    'x'           => (float) $device['x'],
                    'y'           => (float) $device['y'],
                    'ports'       => $device['ports'] ?? null,
                    'model'       => $device['model'] ?? $device['subtype'] ?? null, 
                    'status'      => 'planned',
                    'notes'       => $device['notes'] ?? $device['room_name'] ?? null,
                ]);

                // تخزين العلاقة بين الـ device_id الخاص بالبايثون والـ id الحقيقي لقاعدة البيانات
                $deviceMapping[$device['device_id']] = $savedDevice->id;

                $devicesSavedCount++;
            }

            // 5. تخزين الروابط والأسلاك باستخدام الموديل المخصص Connection بعد جلب الـ IDs الصحيحة
            $connectionsData = $result['connections'] ?? [];
            foreach ($connectionsData as $conn) {
                
                // جلب الـ ID الحقيقي من قاعدة البيانات المقابل للـ من وإلى
                $fromId = $deviceMapping[$conn['from']] ?? null;
                $toId   = $deviceMapping[$conn['to']] ?? null;

                // نقوم بالحفظ فقط إذا وجدنا الأجهزة المقابلة لها في قاعدة البيانات تجنباً لأي خطأ في قيم الـ Foreign Keys
                if ($fromId && $toId) {
                    \App\Models\Connection::create([
                        'project_id'     => $project->id,
                        'from_device_id' => $fromId, // حفظ رقم الـ ID الصحيح (Integer)
                        'to_device_id'   => $toId,   // حفظ رقم الـ ID الصحيح (Integer)
                        'type'           => $conn['type'],
                        'speed'          => $conn['speed'] ?? null,
                        'distance_m'     => (float) $conn['distance_m'],
                        'medium'         => $conn['medium'] ?? 'copper',
                        'notes'          => $conn['notes'] ?? null,
                    ]);
                }
            }

            // 6. تحديث حالة المشروع إلى "مكتمل" وتخزين الـ Metadata الكاملة
            $project->update([
                'status' => 'completed',
                'total_device' => $devicesSavedCount,
                'network_metadata' => isset($result['metadata']) ? json_encode($result['metadata']) : null,
            ]);

            DB::commit();

            return response()->json([
                'success' => true,
                'message' => 'تمت معالجة الشبكة بالذكاء الاصطناعي وحفظ كافة الأجهزة والاتصالات بنجاح ممتد للغرف المركزية والفرعية.',
                'total_devices_saved' => $devicesSavedCount,
                'connections' => $connectionsData,
                'metadata' => $result['metadata'] ?? []
            ], 200);

        } catch (\Exception $e) {
            DB::rollBack();
            $project->update(['status' => 'error']);

            return response()->json([
                'success' => false,
                'message' => 'حدث خطأ أثناء حفظ هندسة الأجهزة والروابط: ' . $e->getMessage()
            ], 500);
        }
    }
}