<?php

use App\Http\Controllers\UserController;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Route;


Route::get('/user', function (Request $request) {
    return $request->user();
})->middleware('auth:sanctum');

Route::get('All_Users', [UserController::class, 'Get_All_Users'])->middleware('auth:sanctum');


Route::post('/Register', [UserController::class, 'Register']);
Route::post('/Login', [UserController::class, 'Login']);
Route::get('/Logout', [UserController::class, 'Logout'])->middleware('auth:sanctum');

Route::get('/verify/{id}/{hash}', [UserController::class, 'Verify'])
    ->name('verification.verify');
    
Route::post('/email/resend', [UserController::class, 'Resend'])
    ->middleware(['auth:sanctum', 'throttle:4,1'])
    ->name('verification.send');

Route::post('/password/forget',[UserController::class,'Reset_Password']);