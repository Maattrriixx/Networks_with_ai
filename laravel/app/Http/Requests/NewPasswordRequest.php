<?php

namespace App\Http\Requests;

use Illuminate\Contracts\Validation\ValidationRule;
use Illuminate\Foundation\Http\FormRequest;
use Illuminate\Http\Exceptions\HttpResponseException;
 use Illuminate\Contracts\Validation\Validator;
class NewPasswordRequest extends FormRequest
{
    /**
     * Determine if the user is authorized to make this request.
     */
    public function authorize(): bool
    {
        return true;
    }

    /**
     * Get the validation rules that apply to the request.
     *
     * @return array<string, ValidationRule|array<mixed>|string>
     */
    public function rules(): array
    {
        return [
            'email' => ['required', 'email'],
            'password' => ['required', 'string', 'min:8', 'confirmed'],
            'token' => ['required'],
        ];
    }
   

protected function failedValidation(Validator $validator)
{
    throw new HttpResponseException(
        response()->json([
            'errors' => $validator->errors()
        ], 422)
    );
}
     
    
    public function messages()
    {
        return [
            'email.required' => 'email is required',
            'email.email' => 'the email is not valid',
            'password.required' => 'password is required',
            'password.string' => 'the password must be a string',
            'password.min' => 'the password must be at least 8 characters',
            'password.confirmed' => 'the password confirmation does not match',
        ];
    }
  
}
