<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
   public function up(): void
{
    Schema::create('connections', function (Blueprint $table) {
        $table->id();
        $table->foreignId('project_id')->constrained()->onDelete('cascade');
        
        // الأجهزة المربوطة (تعتمد على الـ device_id القادم من بايثون)
        $table->integer('from_device_id');
        $table->integer('to_device_id');
        
        // تفاصيل السلك
        $table->string('type'); // ethernet, wifi_uplink, fiber...
        $table->string('speed')->nullable(); // 1 Gbps, 10 Gbps
        $table->decimal('distance_m', 8, 2); // طول السلك بالمتر
        $table->string('medium')->default('copper'); // copper, fiber
        $table->string('notes')->nullable();
        $table->timestamps();
    });
}

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('connections');
    }
};
