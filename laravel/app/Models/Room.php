<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class Room extends Model
{
    protected $fillable = [
        'project_id',
        'confidence',
        'x1', 'y1', 'x2', 'y2',
        'center_x', 'center_y',
        'type',
    ];

    public function project()
    {
        return $this->belongsTo(Project::class);
    }

   
    public static function calculateCenter($x1, $y1, $x2, $y2)
    {
        return [
            'x' => ($x1 + $x2) / 2,
            'y' => ($y1 + $y2) / 2
        ];
    }
}