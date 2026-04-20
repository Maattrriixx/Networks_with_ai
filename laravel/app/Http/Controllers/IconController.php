<?php

namespace App\Http\Controllers;

use App\Models\Icon;
use Illuminate\Http\Request;

class IconController extends Controller
{
    public function Display_Icon()
    {
        $icons = Icon::select('id', 'name', 'icon')->get();

        $icons->transform(function ($icon) {
            $icon->icon = asset('storage/' . str_replace('\\', '/', $icon->icon));
            return $icon;
        });

        return response()->json(['icons' => $icons]);
    }
}
