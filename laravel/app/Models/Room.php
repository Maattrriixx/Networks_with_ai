<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class Room extends Model
{
    use HasFactory;

    // تحديث الـ fillable حسب الأعمدة الجديدة في الـ Migration
    protected $fillable = ['project_id', 'confidence', 'center_x', 'center_y', 'type'];

    // العلاقة الجديدة: الغرفة لها عدة زوايا
    public function corners()
    {
        // تم إضافة orderBy لكي يجلب لك لارافيل الزوايا مرتبة تلقائياً للرسم
        return $this->hasMany(RoomCorner::class)->orderBy('order_index', 'asc');
    }

    // الغرفة تنتمي لمشروع واحد
    public function project()
    {
        return $this->belongsTo(Project::class);
    }
    public function devices()
{
    return $this->hasMany(Device::class);
}
}