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
    Schema::table('devices', function (Blueprint $table) {
        // إضافة معرف الغرفة كـ Foreign Key يسمح بأن يكون Null احتياطاً
        $table->foreignId('room_id')->nullable()->after('project_id')->constrained()->onDelete('cascade');
    });
}

public function down(): void
{
    Schema::table('devices', function (Blueprint $table) {
        $table->dropForeign(['room_id']);
        $table->dropColumn('room_id');
    });
}
};
