<?php
// database/migrations/2026_06_05_125718_create_devices_table.php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('devices', function (Blueprint $table) {
            $table->id();
            $table->foreignId('project_id')->constrained('projects')->onDelete('cascade');
            $table->string('device_code', 50)->unique(); // معرف الجهاز في النظام الشبكي

            // تحديث الـ enum لتشمل كافة الأجهزة المولدة من سكريبت البايثون
            $table->enum('type', [
                'camera',
                'switch',
                'router',
                'firewall',
                'patch_panel',
                'ups',
                'server'
            ]);

            $table->integer('cluster_id')->nullable(); // رقم المجموعة التي يخدمها
            $table->float('x')->nullable(); // الإحداثي X
            $table->float('y')->nullable(); // الإحداثي Y
            $table->integer('ports')->nullable(); // عدد المنافذ (للسويتشات والـ Patch Panels)
            $table->string('model')->nullable(); // موديل الجهاز
            $table->string('status')->default('planned'); // planned, installed, active, faulty
            $table->text('notes')->nullable();
            $table->timestamps();

            // Indexes لتحسين سرعة الاستعلامات
            $table->index(['project_id', 'type']);
            $table->index(['project_id', 'cluster_id']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('devices');
    }
};
