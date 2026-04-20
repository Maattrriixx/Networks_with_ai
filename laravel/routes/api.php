<?php

use App\Http\Controllers\IconController;
use App\Http\Controllers\UserController;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Route;


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
Route::delete('/Delete_Account', [UserController::class, 'Delete_Account'])->middleware(['auth:sanctum','throttle:5,30']);

Route::get('/Display_Icon',[IconController::class,'Display_Icon'])->middleware('auth:sanctum');
