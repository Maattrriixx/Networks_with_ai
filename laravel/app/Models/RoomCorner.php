<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class RoomCorner extends Model
{
    use HasFactory;

    // الأعمدة المسموح بحفظها جماعياً
    protected $fillable = ['room_id', 'x', 'y', 'order_index'];

    // علاقة عكسية: الزاوية تنتمي لغرفة واحدة
    public function room()
    {
        return $this->belongsTo(Room::class);
    }
}