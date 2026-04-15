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
    
Route::post('/Forget_Password', [UserController::class, 'Forget_Password']);
Route::post('/New_Password', [UserController::class, 'New_Password']);


Route::put('/Change_Name', [UserController::class, 'Change_Name'])->middleware('auth:sanctum');
Route::get('/Delete_Account', [UserController::class, 'Delete_Account'])->middleware('auth:sanctum');