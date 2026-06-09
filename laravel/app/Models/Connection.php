<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class Connection extends Model
{
    // الحقول المسموح بإدخالها وتعديلها في جدول الـ connections
    protected $fillable = [
        'project_id',
        'from_device_id',
        'to_device_id',
        'type',
        'speed',
        'distance_m',
        'medium',
        'notes'
    ];

    // علاقة عكسية: التوصيل ينتمي إلى مشروع معين
    public function project()
    {
        return $this->belongsTo(Project::class);
    }
}   