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

        // جلب معرفات الغرف التابعة للمشروع
        $projectRoomIds = Room::where('project_id', $project->id)->orderBy('id')->pluck('id')->values()->all();

        $resolveRoomId = function (array $device) use ($projectRoomIds) {
            $mapRoomNumber = function ($candidate) use ($projectRoomIds) {
                if ($candidate === null || $candidate === '') {
                    return null;
                }

                if (!is_numeric($candidate)) {
                    return null;
                }

                $candidate = (int) $candidate;
                
                // التحقق المباشر فقط - إزالة المنطق الخاطئ
                if (in_array($candidate, $projectRoomIds, true)) {
                    return $candidate;
                }

                return null;
            };

            foreach (['room_id', 'room'] as $field) {
                $resolved = $mapRoomNumber($device[$field] ?? null);
                if ($resolved !== null) {
                    return $resolved;
                }
            }

            foreach (['room_name', 'notes'] as $field) {
                $text = strtolower(trim((string) ($device[$field] ?? '')));
                if ($text === '') {
                    continue;
                }

                if (preg_match('/room\s*#?\s*(\d+)/i', $text, $matches)) {
                    $resolved = $mapRoomNumber($matches[1]);
                    if ($resolved !== null) {
                        return $resolved;
                    }
                }
            }

            return $projectRoomIds[0] ?? null;
        };

        // 3. استخدام الـ DB Transaction لضمان حفظ البيانات بشكل سليم
        DB::beginTransaction();
        try {
            // حذف أي أجهزة وتوصيلات قديمة
            Device::where('project_id', $project->id)->delete();
            \App\Models\Connection::where('project_id', $project->id)->delete();

            $devicesSavedCount = 0;
            
            // مصفوفة لربط معرف الجهاز القادم من بايثون بالـ ID الحقيقي
            $deviceMapping = [];
            
            // --- تجميع كافة الأجهزة ---
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

            // ثانياً: دمج الأجهزة المركزية والمستقلة
            if (isset($result['unassigned_devices']) && is_array($result['unassigned_devices'])) {
                foreach ($result['unassigned_devices'] as $device) {
                    $devicesData[] = $device;
                }
            }

            // ================================================================
            // 🔥 التعديل الجديد: تجميع الأجهزة المتشابهة
            // ================================================================
            $groupedDevices = [];
            
            foreach ($devicesData as $device) {
                // تحويل النوع
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

                if (!$dbType) {
                    continue;
                }

                $roomId = $resolveRoomId($device);
                
                // إنشاء مفتاح تجميع فريد
                $groupKey = $dbType . '|' . $roomId . '|' . ($device['cluster_id'] ?? 'null');
                
                if (!isset($groupedDevices[$groupKey])) {
                    // أول جهاز من هذا النوع
                    $groupedDevices[$groupKey] = [
                        'device_ids' => [$device['device_id']],
                        'project_id' => $project->id,
                        'type' => $dbType,
                        'room_id' => $roomId,
                        'cluster_id' => $device['cluster_id'] ?? null,
                        'x' => (float) $device['x'],
                        'y' => (float) $device['y'],
                        'ports' => $device['ports'] ?? null,
                        'model' => $device['model'] ?? $device['subtype'] ?? null,
                        'status' => 'planned',
                        'notes' => $device['notes'] ?? $device['room_name'] ?? null,
                        'quantity' => 1,
                    ];
                } else {
                    // جهاز مكرر - زيادة العدد
                    $groupedDevices[$groupKey]['quantity']++;
                    $groupedDevices[$groupKey]['device_ids'][] = $device['device_id'];
                }
            }

            // ================================================================
            // حفظ الأجهزة المجمعة
            // ================================================================
            foreach ($groupedDevices as $groupKey => $groupedDevice) {
                // حفظ الجهاز المجمع
                $savedDevice = Device::create([
                    'project_id'  => $groupedDevice['project_id'],
                    'device_code' => 'DEV-' . $project->id . '-' . $groupedDevice['device_ids'][0], // أول ID
                    'type'        => $groupedDevice['type'],
                    'room_id'     => $groupedDevice['room_id'],
                    'cluster_id'  => $groupedDevice['cluster_id'],
                    'x'           => $groupedDevice['x'],
                    'y'           => $groupedDevice['y'],
                    'ports'       => $groupedDevice['ports'],
                    'model'       => $groupedDevice['model'],
                    'status'      => $groupedDevice['status'],
                    'notes'       => $groupedDevice['notes'],
                    'quantity'    => $groupedDevice['quantity'], // العدد
                ]);

                // تخزين العلاقة بين كل device_id والـ ID الحقيقي
                foreach ($groupedDevice['device_ids'] as $deviceId) {
                    $deviceMapping[$deviceId] = $savedDevice->id;
                }

                $devicesSavedCount += $groupedDevice['quantity'];
            }

            // 5. تخزين الروابط والأسلاك
            $connectionsData = $result['connections'] ?? [];
            foreach ($connectionsData as $conn) {
                $fromId = $deviceMapping[$conn['from']] ?? null;
                $toId   = $deviceMapping[$conn['to']] ?? null;

                if ($fromId && $toId) {
                    \App\Models\Connection::create([
                        'project_id'     => $project->id,
                        'from_device_id' => $fromId,
                        'to_device_id'   => $toId,
                        'type'           => $conn['type'],
                        'speed'          => $conn['speed'] ?? null,
                        'distance_m'     => (float) $conn['distance_m'],
                        'medium'         => $conn['medium'] ?? 'copper',
                        'notes'          => $conn['notes'] ?? null,
                    ]);
                }
            }

            // 6. تحديث حالة المشروع
            $project->update([
                'status' => 'completed',
                'total_device' => $devicesSavedCount,
                'network_metadata' => isset($result['metadata']) ? json_encode($result['metadata']) : null,
            ]);

            DB::commit();

            return response()->json([
                'success' => true,
                'message' => 'تمت معالجة الشبكة وحفظ الأجهزة المجمعة بنجاح',
                'total_devices_saved' => $devicesSavedCount,
                'grouped_devices_count' => count($groupedDevices),
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