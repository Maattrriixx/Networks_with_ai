<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class Project extends Model
{
    // دمج الحقل الجديد ليقبل الإدخال عبر الـ update
    protected $fillable = [
        'user_id',
        'name',
        'type',
        'description',
        'image',
        'thumbnail',
        'status',
        'num_rooms',
        'total_device',
        'measure_of_draw',
        'network_metadata',
    ];

    // مصفوفة casts واحدة مجمعة بدون أي تكرار لضمان تحويل الـ JSON تلقائياً
    protected $casts = [
        'network_metadata' => 'array',
        'status' => 'string',
        'type' => 'string',
    ];

    public function user()
    {
        return $this->belongsTo(User::class);
    }

    public function rooms()
    {
        return $this->hasMany(Room::class);
    }

    public function getImageUrlAttribute()
    {
        return $this->image_path ? asset('storage/' . $this->image_path) : null;
    }

    public function getThumbnailUrlAttribute()
    {
        return $this->thumbnail_path ? asset('storage/' . $this->thumbnail_path) : null;
    }
    // علاقة المشروع مع الأجهزة التابعة له
    public function devices()
    {
        return $this->hasMany(Device::class);
    }

    // علاقة المشروع مع الأسلاك والتوصيلات التابعة له
    public function connections()
    {
        return $this->hasMany(Connection::class); // تأكد من إنشاء موديل الـ Connection إذا لم تكن قد أنشأته
    }
}
