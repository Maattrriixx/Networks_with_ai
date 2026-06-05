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
         Schema::create('projects', function (Blueprint $table) {
            $table->id();
            $table->foreignId('user_id')->constrained('users')->onDelete('cascade');
            $table->string('name');
            $table->enum('type', ['university', 'bank', 'residential', 'commercial'])->default('university');
            $table->text('description')->nullable();
            $table->integer('num_rooms')->default(0);
            $table->string('image');
            $table->string('thumbnail')->nullable();
            $table->integer('total_device')->default(0);
            $table->enum('status', ['draft','saved', 'processing', 'completed', 'error'])->default('draft');
            $table->enum('measure_of_draw',['1/200','1/100','1/50'])->default('1/100');
            $table->timestamps();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('projects');
    }
};
