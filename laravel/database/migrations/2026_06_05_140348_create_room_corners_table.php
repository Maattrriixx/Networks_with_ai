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
        Schema::create('room_corners', function (Blueprint $table) {
            $table->id();
            // ربط الزاوية بالغرفة الخاصة بها، إذا حذفت الغرفة تحذف زواياها تلقائياً
            $table->foreignId('room_id')->constrained('rooms')->onDelete('cascade');

            // إحداثيات النقطة الحالية
            $table->integer('x');
            $table->integer('y');

            // ترتيب الزاوية (مهم جداً للفرونت إند من أجل رسم المضلع بالترتيب الصحيح 0، 1، 2، 3)
            $table->integer('order_index'); 

            $table->timestamps();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('room_corners');
    }
};