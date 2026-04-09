<?php

namespace App\Http\Controllers;

use App\Http\Requests\NewPasswordRequest;
use App\Http\Requests\RegisterRequest;
use App\Models\User;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Hash;
use Illuminate\Support\Facades\Password;

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
        $user=User::create($valid);
        $user->sendEmailVerificationNotification();
        
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


// تفعيل الحساب
    public function Verify($id,$hash){
        $user=User::find($id);
        if(!$user)
            {
                return response()->json([
                    'message'=>'bad user'
                ]);
            } 
            if(!hash_equals((string)$hash,sha1($user->getEmailForVerification()))){
                return response()->json([
                    'message'=>'bad hash',
                ]);
            }
            if($user->hasVerifiedEmail()){
                return response()->json([
                    'message'=>'Email already verified'
                ]);
            }
            $user->markEmailAsVerified();
            // return redirect('http://localhost:3000/verification-success');
            return response()->json([
                'message'=>'Email verified successfully'
                ]);
        }

    
}
