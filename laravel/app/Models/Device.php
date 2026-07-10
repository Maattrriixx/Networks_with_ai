<?php
// app/Models/Device.php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class Device extends Model
{
    use HasFactory;

    protected $fillable = [
        'project_id',
        'device_code',
        'type',
        'room_id',
        'cluster_id',
        'x',
        'y',
        'ports',
        'model',
        'status',
        'notes',
        'quantity', // إضافة الحقل الجديد
    ];

    protected $casts = [
        'x' => 'float',
        'y' => 'float',
        'ports' => 'integer',
        'quantity' => 'integer',
    ];

    // العلاقات
    public function project()
    {
        return $this->belongsTo(Project::class);
    }

    public function room()
    {
        return $this->belongsTo(Room::class);
    }

    public function connectionsFrom()
    {
        return $this->hasMany(Connection::class, 'from_device_id');
    }

    public function connectionsTo()
    {
        return $this->hasMany(Connection::class, 'to_device_id');
    }
}