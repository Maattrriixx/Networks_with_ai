<?php

namespace App\Http\Controllers;

use App\Http\Requests\ForgetPasswordRequest;
use App\Http\Requests\NewPasswordRequest;
use App\Http\Requests\RegisterRequest;
use App\Http\Requests\ResetPasswordRequest;

use App\Models\User;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Hash;
use Illuminate\Support\Facades\Mail;
use Illuminate\Support\Str;

class UserController extends Controller 
{
    public function Get_All_Users()
    {
        $users = User::all();
        return response()->json($users);
    }
    public function Register(RegisterRequest $req)
{
    $valid = $req->validated();
    $user = User::create($valid);
    
    dispatch(function () use ($user) {
        $user->sendEmailVerificationNotification();
    });

    return response()->json([
        'message' => 'successful register, please check your email to verify your account'
    ]);
}
    public function Login(Request $req){
        $user=User::where('email',$req->email)->first();
        if(!$user || !Hash::check($req->password,$user->password)){
            return response()->json([
                'message'=>'Invalid email or password'
            ],401);
        }
        if(!$user->hasVerifiedEmail()){
             return response()->json(['message' => 'Please verify your account first'], 403);
         }
        $token = $user->createToken('auth_token')->plainTextToken;
        return response()->json([
            'access_token' => $token,
        ]);
    }
    public function Logout(Request $req){
        $req->user()->currentAccessToken()->delete;
        return response()->json([
            'message'=>'Logged out successfully'
        ]);
    }


    public function Verify($id,$hash){
        $user=User::find($id);
        if(!$user)
            {
                return response()->json([
                    'message'=>'user not found'
                ]);
            } 
            if(!hash_equals((string)$hash,sha1($user->getEmailForVerification()))){
                return response()->json([
                    'message'=>'invalid verification link ',
                ]);
            }
            if($user->hasVerifiedEmail()){
                return response()->json([
                    'message'=>'Email already verified'
                ]);
            }
            $user->markEmailAsVerified();
             return redirect('http://localhost:5173/Login',);
           
        }
  public function Forget_Password(ForgetPasswordRequest $req)
{  
    $token = Str::random(64);
    
   DB::table('password_reset_tokens')->updateOrInsert(
    ['email' => $req->email],  
    [                         
        'token' => Hash::make($token),
        'created_at' => now(),
    ]
);

        $encryptedEmail = encrypt($req->email);
        $encryptedToken = encrypt($token);
        $resetLink = "http://localhost:5173/NewPassword?token={$encryptedToken}&email={$encryptedEmail}";
    
         $email = $req->email;
    dispatch(function () use ($email, $resetLink) {
        Mail::raw("Reset your password: {$resetLink}", function ($message) use ($email) {
            $message->to($email)
                    ->subject('Password Reset Request');
        });
    });
    
        return response()->json([
        'status' => true,
        'message' => 'Reset link sent successfully',
        'reset_link' => $resetLink
        ]);
    }
   public function New_Password(ResetPasswordRequest $req)
{
    $email = decrypt($req->email);
    $token = decrypt($req->token);

    $resetRecord = DB::table('password_reset_tokens')->where('email', $email)->first();
    if (!$resetRecord) {
        return response()->json([
            'status' => false,
            'message' => 'Invalid email address'
        ], 400);
    }

    if (!Hash::check($token, $resetRecord->token)) {
        return response()->json([
            'status' => false,
            'message' => 'Invalid token'
        ], 400);
    }

    if (now()->subMinutes(30)->gt($resetRecord->created_at)) {
        return response()->json([
            'status' => false,
            'message' => 'Token expired'
        ], 400);
    }

    $user = User::where('email', $email)->first();
    if (!$user) {
        return response()->json([
            'status' => false,
            'message' => 'User not found'
        ], 404);
    }

    $user->password = Hash::make($req->password);
    $user->save();

    DB::table('password_reset_tokens')->where('email', $email)->delete();

    return response()->json([
        'status' => true,
        'message' => 'Password reset successfully'
    ]);
}
}
