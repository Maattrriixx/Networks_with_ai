<?php

namespace App\Http\Requests;

use Illuminate\Contracts\Validation\ValidationRule;
use Illuminate\Foundation\Http\FormRequest;
use Illuminate\Contracts\Validation\Validator;
use Illuminate\Http\Exceptions\HttpResponseException;

class StoreProject extends FormRequest
{
    public function authorize(): bool
    {
        return true;
    }

    public function rules(): array
    {
        return [
            'name' => 'required|string|max:255',
            'type' => 'required|in:university,bank,residential,commercial',
            'description' => 'nullable|string',
            'image' => 'required|image|mimes:jpg,png|max:20480',
            'measure_of_draw' => 'required|in:1/200,1/100,1/50',
            
        ];
    }

    public function messages(): array
    {
        return [
            'name.required' => 'Project name is required.',
            'name.string' => 'Project name must be a string.',
            'name.max' => 'Project name cannot exceed 255 characters.',
            'type.required' => 'Project type is required.',
            'type.in' => 'Project type must be: university, bank, residential, commercial, or other.',
            'description.string' => 'Description must be a string.',
            'image.required' => 'Image is required.',
            'image.image' => 'Image must be a valid image.',
            'image.mimes' => 'Image must be a file of type: jpg, png.',
            'image.max' => 'Image cannot exceed 20480 KB.',
            'measure_of_draw.required' => 'Measure of draw is required.',
            'measure_of_draw.in' => 'Measure of draw must be: 1/200, 1/100, or 1/50.',
        ];
    }

    public function failedValidation(Validator $validator)
    {
        throw new HttpResponseException(response()->json([
            'status' => false,
            'errors' => $validator->errors()
        ], 422));
    }
}