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
        Schema::create('rooms', function (Blueprint $table) {
            $table->id();
            // ربط الغرفة بالمشروع
            $table->foreignId('project_id')->constrained()->onDelete('cascade');

            $table->float('confidence')->default(1.0);
            
            // مراكز الغرف المحسوبة من البايثون
            $table->float('center_x')->nullable();
            $table->float('center_y')->nullable();

            // تصنيفات الغرف
            $table->enum('type', [
                'laboratories',
                'classroom',
                'administrative office',
                'server room',
                'café',
                'lobby',
                'dr.office',
                'library',
                'meeting room',
                'wc',
                'Stairs',
                'Storage',
                'other',
            ])->nullable();

            $table->timestamps();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('rooms');
    }
};