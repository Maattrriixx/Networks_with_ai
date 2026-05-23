<?php

use App\Models\Icon;
use App\Models\Project;
use Illuminate\Support\Facades\Route;

Route::get('/', function () {
    $s= Project::all();
    return view('welcome', compact('s'));
});
