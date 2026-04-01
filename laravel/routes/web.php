<?php

use App\Models\Icon;
use Illuminate\Support\Facades\Route;

Route::get('/', function () {
    $icon = Icon::all();
    return view('welcome', compact('icon'));
});
