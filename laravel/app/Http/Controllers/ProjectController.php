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
    public function getProjectSettings()
{
    return response()->json([
        'available_measures' => ['1/50', '1/100', '1/200'],
        'project_types'      => ['university', 'bank', 'residential', 'commercial']
    ], 200);
}
   public function StoreProject(StoreProject $req)
{
    // البيانات القادمة هنا أصبحت مفلترة ومضمونة ومحتوية على measure_of_draw
    $validated = $req->validated(); 
    
    $userid = Auth::id(); // طريقة أسرع وأقصر لجلب الـ ID
    
    // التحقق من الصورة (تم تأمينه أيضاً في الـ Request لكن زيادة تأكيد)
    if (!$req->hasFile('image')) {
        return response()->json(['error' => 'Image is required'], 422);
    }
    
    $image = $req->file('image');
    $path = $image->store('image', 'public');
    
    $validated['image'] = 'storage/' . $path;
    $validated['user_id'] = $userid;

    // معالجة الصورة المصغرة (Thumbnail)
    $manger = new ImageManager(new Driver());
    $thumb = $manger->read($image)->resize(200, 200);
    $thumbName = 'thumb' . time() . '.jpg';
    $thumbPath = 'thumbnail/' . $thumbName;
    Storage::disk('public')->put($thumbPath, (string) $thumb->toJpeg(80));
    
    $validated['thumbnail'] = 'storage/' . $thumbPath;

    // سيتم حفظ المشروع ومعه مقياس الرسم تلقائياً لأننا أضفناه للـ fillable والـ validation
    $project = Project::create($validated);
    
    return response()->json([
        'message' => 'Project created successfully', 
        'project' => $project
    ], 201);
}


    public function analyzeProject(Project $project)
{
    // 1. التحقق من صلاحية المستخدم
    if ($project->user_id !== Auth::id()) {
        return response()->json(['error' => 'Unauthorized'], 403);
    }

    // 2. تحديث حالة المشروع إلى جاري المعالجة
    $project->status = 'processing';
    $project->save();

    try {
        // 3. تجهيز مسار الصورة الفعلي على السيرفر
        $imagePath = str_replace('storage/', '', $project->image);
        $imageFullPath = Storage::disk('public')->path($imagePath);

        if (!file_exists($imageFullPath)) {
            throw new \Exception('Image file not found');
        }
        

        // 4. إرسال الصورة إلى سيرفر البايثون (FastAPI / Flask)
        $response = Http::timeout(120)
            ->attach('file', file_get_contents($imageFullPath), basename($imageFullPath))
            ->post('http://127.0.0.1:8021/analyze');

        if (!$response->successful()) {
            throw new \Exception('Python API error: ' . $response->body());
        }

        $data = $response->json();

        // 5. حذف الغرف القديمة (سيقوم الـ cascade بحذف زواياها تلقائياً من قاعدة البيانات)
        $project->rooms()->delete();

        $savedRooms = [];

        // 6. البدء في معالجة الغرف القادمة من البايثون وحفظها
        foreach ($data['rooms'] as $roomData) {
            
            // أولاً: إنشاء الغرفة وحفظ بياناتها الأساسية ومركزها
            $room = Room::create([
                'project_id' => $project->id,
                'confidence' => 1.0, // يمكنك استبدالها بـ $roomData['confidence'] إذا كان الموديل يرسلها
                'center_x'   => $roomData['center']['x'],
                'center_y'   => $roomData['center']['y'],
                'type'       => null, // يترك فارغاً ليقوم المستخدم بتحديده لاحقاً
            ]);

            // ثانياً: حفظ الزوايا كاملة لهذه الغرفة بالترتيب الصحيح
            foreach ($roomData['corners'] as $index => $cornerData) {
                $room->corners()->create([
                    'x'           => $cornerData['x'],
                    'y'           => $cornerData['y'],
                    'order_index' => $index // الترتيب المهم جداً للفرونت إند عند الرسم (0, 1, 2, 3)
                ]);
            }

            // شحن الغرفة مع علاقة زواياها المرتّبة لتضمينها في الـ Response النهائي
            $savedRooms[] = $room->load('corners');
        }

        // 7. تحديث بيانات المشروع وحالته إلى مكتمل بنجاح
        $project->num_rooms = count($savedRooms);
        $project->status = 'completed'; 
        $project->save();

        // 8. إرجاع الرد النهائي بنجاح ومعه مصفوفة الغرف الجديدة بداخلها زواياها
        return response()->json([
            'message'            => 'Analysis completed',
            'project'            => $project,
            'num_rooms'          => $data['num_rooms'],
            'rooms'              => $savedRooms,
            'final_image_base64' => $data['final_image_base64'],
        ]);

    } catch (\Exception $e) {
        // 9. في حال حدوث أي خطأ، يتم تحويل حالة المشروع إلى error
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
        $projects = Project::where('user_id',Auth::id())
            ->select('id', 'name', 'type', 'thumbnail')
            ->get();

        return response()->json($projects);
    }
    public function DeleteProject(Project $project){
        if($project->user_id !==Auth::id()){
            return response()->json(['error'=>'Unauthorized'],403);
        }
        $project->delete();
        return response()->json(['message'=>'Project deleted successfully']);
    }


     public function getProjectTopology($projectId)
    {
        // جلب المشروع مع الغرف والأجهزة والأسلاك في استعلام واحد متكامل
        $project = Project::with(['rooms', 'devices', 'connections'])->findOrFail($projectId);

        // إرجاع البيانات كاملة للفرونت إند
        return response()->json([
            'success' => true,
            'message' => 'تم جلب بيانات المخطط الهيكلي للمشروع بنجاح.',
            'project' => [
                'id'               => $project->id,
                'name'             => $project->name,
                'status'           => $project->status,
                'total_device'     => $project->total_device,
                'measure_of_draw'  => $project->measure_of_draw,
                'metadata'         => $project->network_metadata, // الإحصائيات التي حفظناها كـ JSON
                'rooms'            => $project->rooms,            // مصفوفة الغرف ليرسم الجدران
                'devices'          => $project->devices,          // مصفوفة الأجهزة مع الـ x و y والـ room_id
                'connections'      => $project->connections,      // مصفوفة الأسلاك (من وين لـ وين)
            ]
        ], 200);
    }
}
