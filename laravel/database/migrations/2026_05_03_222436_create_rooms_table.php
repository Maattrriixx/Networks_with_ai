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
            $table->foreignId('project_id')->constrained()->onDelete('cascade');


            $table->float('confidence');


            $table->integer('x1');
            $table->integer('y1');
            $table->integer('x2');
            $table->integer('y2');

            $table->float('center_x')->nullable();
            $table->float('center_y')->nullable();


            $table->enum('type', [
                'laboratories',
                'classroom',
                'administrative office',
                'secretary',
                'café',
                'lobby',
                'dr.office',
                'library',
                'meeting room',
                'wc',
                
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
