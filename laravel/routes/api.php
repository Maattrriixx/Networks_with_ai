<?php

use App\Http\Controllers\IconController;
use App\Http\Controllers\ProjectController;
use App\Http\Controllers\UserController;
use App\Http\Controllers\RoomsController;
use App\Models\Project;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Route;
use App\Http\Controllers\DeviceController;



Route::get('/user', function (Request $request) {
    return $request->user();
})->middleware('auth:sanctum');

Route::get('All_Users', [UserController::class, 'Get_All_Users'])->middleware('auth:sanctum');


Route::post('/Register', [UserController::class, 'Register']);
Route::post('/Login', [UserController::class, 'Login'])->middleware('throttle:login');
Route::get('/Logout', [UserController::class, 'Logout'])->middleware('auth:sanctum');

Route::get('/verify/{id}/{hash}', [UserController::class, 'Verify'])
    ->name('verification.verify');

Route::post('/Forget_Password', [UserController::class, 'Forget_Password']);
Route::post('/New_Password', [UserController::class, 'New_Password']);


Route::put('/Change_Name', [UserController::class, 'Change_Name'])->middleware('auth:sanctum');
Route::delete('/Delete_Account', [UserController::class, 'Delete_Account'])->middleware(['auth:sanctum', 'throttle:5,30']);

Route::get('/Display_Icon', [IconController::class, 'Display_Icon'])->middleware('auth:sanctum');



///////////////////project
///////////////////project
///////////////////project
///////////////////project
Route::get('/Get_User_Projects', [ProjectController::class, 'GetUserProjects'])->middleware('auth:sanctum');
Route::get('/Get_All_User_Projects', [ProjectController::class, 'GetAllUserProjects'])->middleware('auth:sanctum');

Route::get('/projects/settings', [ProjectController::class, 'getProjectSettings'])->middleware('auth:sanctum');
Route::post('/create_project', [ProjectController::class, 'StoreProject'])->middleware('auth:sanctum');
Route::post('/projects/{project}/analyze', [ProjectController::class, 'analyzeProject'])->middleware('auth:sanctum');
Route::get('/projects', [ProjectController::class, 'GetUserProjects'])->middleware('auth:sanctum');
Route::get('/projects/{project}/status', function (Project $project) {
    return response()->json(['status' => $project->status]);
})->middleware('auth:sanctum');

Route::delete('/projects/{project}', [ProjectController::class, 'DeleteProject'])->middleware('auth:sanctum');
Route::get('projects/{projectId}/topology', [ProjectController::class, 'getProjectTopology'])->middleware('auth:sanctum');
////////////////////////////room
////////////////////////////room
////////////////////////////room
////////////////////////////room
Route::get('/projects/{project}/rooms', [RoomsController::class, 'getRooms'])->middleware('auth:sanctum');
Route::patch('/rooms/{room}/type', [RoomsController::class, 'updateType'])->middleware('auth:sanctum');
Route::get('rooms/{roomId}/details', [RoomsController::class, 'showRoomWithDevices']);


//////////////////////device
//////////////////////device
//////////////////////device                

Route::post('/projects/{id}/optimize-network', [DeviceController::class, 'runOptimization'])->middleware('auth:sanctum');
